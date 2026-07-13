from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from .project import ensure_workspace
from .text_utils import read_text_if_exists, slugify


BLOCK_START = "<!-- vibewiki-agent:start -->"
BLOCK_END = "<!-- vibewiki-agent:end -->"
AGENT_BLOCK = f"""{BLOCK_START}
## VibeWiki Project Memory

This project uses VibeWiki as reviewed project memory.

- At the start of a task, call `vibewiki_brief`, then call `vibewiki_guard` for the task.
- Use `vibewiki_search` and `vibewiki_read` to retrieve only relevant approved memory.
- Candidate memory is unreviewed. Do not request or rely on it unless the user explicitly asks.
- If MCP tools are unavailable, run `vibewiki context --for "<task>" --scope approved --format json --max-items 5 --max-chars 500`.
- Capture useful new knowledge as a candidate; it must be reviewed before becoming trusted memory.
{BLOCK_END}
"""


@dataclass(frozen=True)
class AgentInstallResult:
    project: Path
    rules_path: Path
    descriptor_path: Path
    server_name: str
    server_command: tuple[str, ...]
    rules_changed: bool
    descriptor_changed: bool
    registration: str = "not requested"


def install_agent_bridge(
    project: Path,
    *,
    name: str = "",
    register_codex: bool = False,
) -> AgentInstallResult:
    root = project.resolve()
    ensure_workspace(root)
    server_name = slugify(name or f"vibewiki-{root.name}", "vibewiki")
    module_root = Path(__file__).resolve().parent.parent
    env_command = shutil.which("env") or "/usr/bin/env"
    server_command = (
        env_command,
        f"PYTHONPATH={module_root}",
        sys.executable,
        "-m",
        "vibewiki.cli",
        "--project",
        str(root),
        "mcp",
    )

    rules_path = root / "AGENTS.md"
    original_rules = read_text_if_exists(rules_path)
    next_rules = _upsert_agent_block(original_rules)
    rules_changed = original_rules != next_rules
    if rules_changed:
        rules_path.write_text(next_rules, encoding="utf-8")

    descriptor_path = root / ".vibewiki" / "agent.json"
    descriptor = {
        "version": 1,
        "project": root.name,
        "default_scope": "approved",
        "transport": "stdio",
        "mcpServers": {
            server_name: {
                "command": "vibewiki",
                "args": ["--project", ".", "mcp"],
            }
        },
        "tools": [
            "vibewiki_brief",
            "vibewiki_guard",
            "vibewiki_search",
            "vibewiki_read",
        ],
    }
    descriptor_text = json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n"
    original_descriptor = read_text_if_exists(descriptor_path)
    descriptor_changed = original_descriptor != descriptor_text
    if descriptor_changed:
        descriptor_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor_path.write_text(descriptor_text, encoding="utf-8")

    registration = "not requested"
    if register_codex:
        registration = register_codex_server(server_name, server_command)
    return AgentInstallResult(
        project=root,
        rules_path=rules_path,
        descriptor_path=descriptor_path,
        server_name=server_name,
        server_command=server_command,
        rules_changed=rules_changed,
        descriptor_changed=descriptor_changed,
        registration=registration,
    )


def register_codex_server(name: str, server_command: tuple[str, ...]) -> str:
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI was not found on PATH.")
    existing = subprocess.run(
        [codex, "mcp", "get", name, "--json"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if existing.returncode == 0 and _registration_matches(existing.stdout, server_command):
        return f"already registered as {name}"
    updated = existing.returncode == 0
    if updated:
        removed = subprocess.run(
            [codex, "mcp", "remove", name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if removed.returncode != 0:
            detail = (removed.stderr or removed.stdout).strip()
            raise RuntimeError(f"Could not update Codex MCP server: {detail}")
    added = subprocess.run(
        [codex, "mcp", "add", name, "--", *server_command],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if added.returncode != 0:
        detail = (added.stderr or added.stdout).strip()
        raise RuntimeError(f"Could not register Codex MCP server: {detail}")
    action = "updated registration" if updated else "registered"
    return f"{action} as {name}"


def format_agent_install_result(result: AgentInstallResult) -> str:
    rules_status = "updated" if result.rules_changed else "already current"
    descriptor_status = "updated" if result.descriptor_changed else "already current"
    codex_command = (
        "codex",
        "mcp",
        "add",
        result.server_name,
        "--",
        *result.server_command,
    )
    lines = [
        "VibeWiki agent bridge is ready.",
        f"- rules: {result.rules_path} ({rules_status})",
        f"- descriptor: {result.descriptor_path} ({descriptor_status})",
        f"- MCP server: {shlex.join(result.server_command)}",
        f"- Codex registration: {result.registration}",
    ]
    if result.registration == "not requested":
        lines.extend(
            [
                "",
                "To register it with Codex:",
                shlex.join(codex_command),
            ]
        )
    lines.extend(
        [
            "",
            "Start a new agent session after registration so the MCP tools are discovered.",
        ]
    )
    return "\n".join(lines) + "\n"


def _upsert_agent_block(text: str) -> str:
    clean = text.rstrip()
    start = clean.find(BLOCK_START)
    end = clean.find(BLOCK_END)
    if start >= 0 and end >= start:
        end += len(BLOCK_END)
        before = clean[:start].rstrip()
        after = clean[end:].strip()
        parts = [part for part in [before, AGENT_BLOCK.rstrip(), after] if part]
        return "\n\n".join(parts) + "\n"
    prefix = clean or "# Project Agent Rules"
    return prefix + "\n\n" + AGENT_BLOCK


def _registration_matches(output: str, server_command: tuple[str, ...]) -> bool:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return False
    transport = payload.get("transport", {}) if isinstance(payload, dict) else {}
    if not isinstance(transport, dict) or transport.get("type") != "stdio":
        return False
    registered_args = transport.get("args", [])
    return transport.get("command") == server_command[0] and registered_args == list(
        server_command[1:]
    )
