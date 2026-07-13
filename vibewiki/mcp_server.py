from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, TextIO

from . import __version__
from .agent_memory import (
    build_agent_brief,
    guard_agent_task,
    read_agent_memory,
    search_agent_memory,
)
from .text_utils import read_text_if_exists


PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOLS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
}


class McpRequestError(Exception):
    def __init__(self, code: int, message: str, data: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class VibeWikiMcpServer:
    def __init__(self, project: Path) -> None:
        self.project = project.resolve()
        if not (self.project / ".vibewiki").is_dir():
            raise ValueError(
                f"Not a VibeWiki project: {self.project}. Run `vibewiki init` first."
            )

    def handle_message(self, message: object) -> dict[str, Any] | None:
        if not isinstance(message, dict):
            return _error_response(None, -32600, "Invalid Request")
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str) or not method:
            if "id" not in message:
                return None
            return _error_response(request_id, -32600, "Invalid Request")
        notification = "id" not in message
        params = message.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            if notification:
                return None
            return _error_response(request_id, -32602, "Invalid params")

        try:
            result = self._dispatch(method, params)
        except McpRequestError as exc:
            if notification:
                return None
            return _error_response(request_id, exc.code, exc.message, exc.data)
        except (OSError, ValueError) as exc:
            if notification:
                return None
            return _error_response(request_id, -32602, str(exc))
        except Exception as exc:  # pragma: no cover - defensive protocol boundary
            if notification:
                return None
            return _error_response(request_id, -32603, "Internal error", str(exc))
        if notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            requested = str(params.get("protocolVersion", ""))
            protocol = requested if requested in SUPPORTED_PROTOCOLS else PROTOCOL_VERSION
            return {
                "protocolVersion": protocol,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {
                    "name": "vibewiki",
                    "title": "VibeWiki Project Memory",
                    "version": __version__,
                },
                "instructions": (
                    "Start with vibewiki_brief and vibewiki_guard. Search approved memory, "
                    "then read only selected refs. Candidate memory is excluded by default."
                ),
            }
        if method in {
            "notifications/initialized",
            "notifications/cancelled",
            "notifications/roots/list_changed",
        }:
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": _tool_definitions()}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {"resources": _resource_definitions()}
        if method == "resources/read":
            return self._read_resource(params)
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        raise McpRequestError(-32601, f"Method not found: {method}")

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            raise McpRequestError(-32602, "tool name is required")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise McpRequestError(-32602, "tool arguments must be an object")

        if name == "vibewiki_brief":
            payload = build_agent_brief(self.project)
        elif name == "vibewiki_search":
            payload = search_agent_memory(
                self.project,
                _required_string(arguments, "query"),
                include_candidates=_boolean(arguments, "include_candidates", False),
                max_items=_integer(arguments, "max_items", 6),
                kinds=_string_list(arguments, "kinds"),
            )
        elif name == "vibewiki_read":
            payload = read_agent_memory(
                self.project,
                _required_string_list(arguments, "refs"),
                include_candidates=_boolean(arguments, "include_candidates", False),
                max_chars_per_item=_integer(arguments, "max_chars_per_item", 4000),
            )
        elif name == "vibewiki_guard":
            payload = guard_agent_task(
                self.project,
                _required_string(arguments, "task"),
                max_items=_integer(arguments, "max_items", 6),
            )
        else:
            raise McpRequestError(-32602, f"Unknown tool: {name}")
        return _tool_result(payload)

    def _read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise McpRequestError(-32602, "resource uri is required")
        if uri == "vibewiki://project/brief":
            text = json.dumps(build_agent_brief(self.project), ensure_ascii=False, indent=2)
            mime_type = "application/json"
        elif uri == "vibewiki://project/agent-rules":
            text = read_text_if_exists(self.project / "AGENTS.md")
            mime_type = "text/markdown"
        else:
            raise McpRequestError(-32002, f"Resource not found: {uri}")
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": mime_type,
                    "text": text,
                }
            ]
        }


def serve_mcp(
    project: Path,
    *,
    instream: TextIO | None = None,
    outstream: TextIO | None = None,
) -> None:
    input_stream = instream or sys.stdin
    output_stream = outstream or sys.stdout
    server = VibeWikiMcpServer(project)
    for line in input_stream:
        clean = line.strip()
        if not clean:
            continue
        try:
            payload = json.loads(clean)
        except json.JSONDecodeError as exc:
            _write_message(output_stream, _error_response(None, -32700, "Parse error", str(exc)))
            continue
        if isinstance(payload, list):
            responses = [server.handle_message(item) for item in payload]
            rendered = [item for item in responses if item is not None]
            if rendered:
                _write_message(output_stream, rendered)
            continue
        response = server.handle_message(payload)
        if response is not None:
            _write_message(output_stream, response)


def _tool_definitions() -> list[dict[str, Any]]:
    read_only = {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    return [
        {
            "name": "vibewiki_brief",
            "title": "Read VibeWiki Project Brief",
            "description": (
                "Get a compact map of approved project memory, agent rules, memory types, "
                "and the recommended search/read flow. Call this once when starting a task."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": read_only,
        },
        {
            "name": "vibewiki_search",
            "title": "Search VibeWiki Memory",
            "description": (
                "Search compact project memory. Approved memory is the default. Set "
                "include_candidates only when unreviewed leads are explicitly useful."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "max_items": {"type": "integer", "minimum": 1, "maximum": 12, "default": 6},
                    "kinds": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                    "include_candidates": {"type": "boolean", "default": False},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "annotations": read_only,
        },
        {
            "name": "vibewiki_read",
            "title": "Read Selected VibeWiki Memory",
            "description": (
                "Read exact memory refs returned by vibewiki_search. This cannot read arbitrary "
                "project files and excludes candidate memory by default."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "refs": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                        "maxItems": 6,
                    },
                    "max_chars_per_item": {
                        "type": "integer",
                        "minimum": 300,
                        "maximum": 12000,
                        "default": 4000,
                    },
                    "include_candidates": {"type": "boolean", "default": False},
                },
                "required": ["refs"],
                "additionalProperties": False,
            },
            "annotations": read_only,
        },
        {
            "name": "vibewiki_guard",
            "title": "Check Task Against Project Memory",
            "description": (
                "Find approved warnings, workflows, rules, and relevant context before editing. "
                "Use it to avoid repeating known failures or missing required verification."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "minLength": 1},
                    "max_items": {"type": "integer", "minimum": 1, "maximum": 10, "default": 6},
                },
                "required": ["task"],
                "additionalProperties": False,
            },
            "annotations": read_only,
        },
    ]


def _resource_definitions() -> list[dict[str, Any]]:
    return [
        {
            "uri": "vibewiki://project/brief",
            "name": "VibeWiki project memory brief",
            "title": "Approved Project Memory Brief",
            "description": "Compact project orientation and approved-memory index.",
            "mimeType": "application/json",
        },
        {
            "uri": "vibewiki://project/agent-rules",
            "name": "VibeWiki project agent rules",
            "title": "Project Agent Rules",
            "description": "Reviewed rules that apply before and after project edits.",
            "mimeType": "text/markdown",
        },
    ]


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": False,
    }


def _required_string(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise McpRequestError(-32602, f"{name} must be a non-empty string")
    return value.strip()


def _required_string_list(arguments: dict[str, Any], name: str) -> list[str]:
    values = arguments.get(name)
    if not isinstance(values, list) or not values:
        raise McpRequestError(-32602, f"{name} must be a non-empty array")
    result = [str(value).strip() for value in values if isinstance(value, str) and value.strip()]
    if len(result) != len(values):
        raise McpRequestError(-32602, f"{name} must contain only non-empty strings")
    return result


def _string_list(arguments: dict[str, Any], name: str) -> list[str]:
    values = arguments.get(name, [])
    if values is None:
        return []
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise McpRequestError(-32602, f"{name} must be an array of strings")
    return [value.strip() for value in values if value.strip()]


def _boolean(arguments: dict[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise McpRequestError(-32602, f"{name} must be a boolean")
    return value


def _integer(arguments: dict[str, Any], name: str, default: int) -> int:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise McpRequestError(-32602, f"{name} must be an integer")
    return value


def _error_response(
    request_id: object,
    code: int,
    message: str,
    data: object | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _write_message(stream: TextIO, payload: object) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()
