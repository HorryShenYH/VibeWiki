from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import tempfile
import unittest
from pathlib import Path

from vibewiki.agent_install import (
    BLOCK_END,
    BLOCK_START,
    _registration_matches,
    install_agent_bridge,
)
from vibewiki.agent_memory import (
    build_agent_brief,
    guard_agent_task,
    read_agent_memory,
    search_agent_memory,
)
from vibewiki.cli import build_parser, run as run_cli
from vibewiki.mcp_server import VibeWikiMcpServer, serve_mcp
from vibewiki.project import init_project
from vibewiki.retrieval import build_context_pack


class AgentBridgeTest(unittest.TestCase):
    def test_agent_memory_defaults_to_approved_and_reads_selected_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            approved = root / "skills" / "workflows" / "safe-api-retry.md"
            approved.write_text(
                """# Workflow: Safe API Retry

Status: approved
Kind: workflow
Confidence: high

## Summary

POST retries require an idempotency key and bounded exponential backoff.

## Steps

- Add the idempotency key before enabling retries.
- Run the API retry regression tests.
""",
                encoding="utf-8",
            )
            candidate = root / ".vibewiki" / "patches" / "retry-session" / "findings" / "issue__retry.md"
            candidate.parent.mkdir(parents=True)
            candidate.write_text(
                """# Issue: Retry Every Request Forever

Status: candidate
Kind: issue

## Summary

Unreviewed suggestion: retry every failed request without an idempotency key.
""",
                encoding="utf-8",
            )

            approved_search = search_agent_memory(
                root,
                "POST retry idempotency key",
                use_embeddings=False,
            )
            all_search = search_agent_memory(
                root,
                "POST retry idempotency key",
                include_candidates=True,
                max_items=10,
                use_embeddings=False,
            )

            self.assertEqual(approved_search["scope"], "approved")
            self.assertTrue(approved_search["items"])
            self.assertTrue(all(item["status"] == "approved" for item in approved_search["items"]))
            self.assertTrue(any(item["status"] == "candidate" for item in all_search["items"]))

            approved_ref = approved_search["items"][0]["ref"]
            approved_read = read_agent_memory(root, [approved_ref])
            self.assertEqual(approved_read["count"], 1)
            self.assertIn("idempotency key", approved_read["items"][0]["text"])

            candidate_ref = next(item["ref"] for item in all_search["items"] if item["status"] == "candidate")
            denied = read_agent_memory(root, [candidate_ref])
            self.assertEqual(denied["count"], 0)
            self.assertTrue(denied["errors"])
            allowed = read_agent_memory(root, [candidate_ref], include_candidates=True)
            self.assertEqual(allowed["items"][0]["status"], "candidate")

    def test_context_pack_and_guard_use_approved_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            issue = root / "docs" / "wiki" / "auth-timeout.md"
            issue.write_text(
                """# Known Issue: Authentication Timeout

Kind: issue
Confidence: high

## Summary

Retrying an authentication POST without an idempotency key can duplicate sessions.

## Verification

Run the authentication timeout regression test before merge.
""",
                encoding="utf-8",
            )
            candidate = root / ".vibewiki" / "patches" / "auth-session" / "findings" / "idea__retry.md"
            candidate.parent.mkdir(parents=True)
            candidate.write_text(
                """# Idea: Ignore Authentication Timeouts

Status: candidate
Kind: idea

## Summary

Ignore every timeout and continue.
""",
                encoding="utf-8",
            )

            payload = json.loads(
                build_context_pack(
                    root,
                    "authentication timeout retry",
                    output_format="json",
                    use_embeddings=False,
                )
            )
            guard = guard_agent_task(root, "change authentication timeout retries")

            self.assertEqual(payload["scope"], "approved")
            self.assertTrue(payload["items"])
            self.assertTrue(all(item["status"] == "approved" for item in payload["items"]))
            self.assertEqual(guard["scope"], "approved")
            self.assertEqual(guard["status"], "memory_found")
            self.assertTrue(guard["warnings"] or guard["context"])

    def test_approved_section_keeps_the_original_recorder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            session_id = "20260713-api-retry"
            event = {
                "schema": 1,
                "actor": "alice",
                "type": "import-markdown",
                "subject": session_id,
            }
            (root / ".vibewiki" / "events.jsonl").write_text(
                json.dumps(event) + "\n",
                encoding="utf-8",
            )
            (root / "docs" / "wiki" / "api-decisions.md").write_text(
                f"""# API Decisions

<!-- vibewiki:{session_id}:finding:knowledge:idempotent-retry -->
## Idempotent Payment Retry

Every payment retry must reuse the original idempotency token to avoid duplicates.
""",
                encoding="utf-8",
            )

            search = search_agent_memory(
                root,
                "payment retry idempotency token duplicates",
                use_embeddings=False,
            )
            item = next(value for value in search["items"] if value.get("section"))
            read = read_agent_memory(root, [item["ref"]])
            context = json.loads(
                build_context_pack(
                    root,
                    "payment retry idempotency token duplicates",
                    output_format="json",
                    use_embeddings=False,
                )
            )

            self.assertEqual(item["recorded_by"], "alice")
            self.assertEqual(read["items"][0]["recorded_by"], "alice")
            self.assertEqual(context["items"][0]["recorded_by"], "alice")

    def test_agent_brief_and_installer_are_compact_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            (root / "skills" / "skilllets" / "verify-api.md").write_text(
                """# Skilllet: Verify API

Status: approved
Kind: skilllet

## Purpose

Run focused API regression tests before merge.
""",
                encoding="utf-8",
            )

            first = install_agent_bridge(root)
            second = install_agent_bridge(root)
            brief = build_agent_brief(root)
            rules = (root / "AGENTS.md").read_text(encoding="utf-8")
            descriptor = json.loads((root / ".vibewiki" / "agent.json").read_text(encoding="utf-8"))

            self.assertTrue(first.rules_changed)
            self.assertTrue(first.descriptor_changed)
            self.assertFalse(second.rules_changed)
            self.assertFalse(second.descriptor_changed)
            self.assertEqual(rules.count(BLOCK_START), 1)
            self.assertEqual(rules.count(BLOCK_END), 1)
            self.assertEqual(descriptor["default_scope"], "approved")
            self.assertIn("vibewiki_search", descriptor["tools"])
            self.assertEqual(brief["memory"]["default_scope"], "approved")
            self.assertTrue(brief["memory"]["kinds"])
            self.assertLess(len(json.dumps(brief)), 8000)

            command = ("/usr/bin/env", "PYTHONPATH=/tmp/Project With Spaces", "python3", "mcp")
            registration = json.dumps(
                {
                    "transport": {
                        "type": "stdio",
                        "command": command[0],
                        "args": list(command[1:]),
                    }
                }
            )
            self.assertTrue(_registration_matches(registration, command))

    def test_mcp_server_exposes_read_only_memory_tools_and_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            (root / "docs" / "wiki" / "release.md").write_text(
                """# Workflow: Release Verification

Kind: workflow
Confidence: high

## Summary

Run unit tests before publishing a release.
""",
                encoding="utf-8",
            )
            server = VibeWikiMcpServer(root)

            initialized = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                }
            )
            tools = server.handle_message(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            )
            search = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "vibewiki_search",
                        "arguments": {"query": "release unit tests"},
                    },
                }
            )
            resource = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "resources/read",
                    "params": {"uri": "vibewiki://project/brief"},
                }
            )

            self.assertEqual(initialized["result"]["protocolVersion"], "2025-11-25")
            names = {item["name"] for item in tools["result"]["tools"]}
            self.assertEqual(
                names,
                {"vibewiki_brief", "vibewiki_guard", "vibewiki_search", "vibewiki_read"},
            )
            self.assertTrue(all(item["annotations"]["readOnlyHint"] for item in tools["result"]["tools"]))
            self.assertEqual(search["result"]["structuredContent"]["scope"], "approved")
            self.assertTrue(search["result"]["structuredContent"]["items"])
            self.assertEqual(resource["result"]["contents"][0]["mimeType"], "application/json")

    def test_mcp_server_does_not_initialize_an_unrelated_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaisesRegex(ValueError, "Run `vibewiki init` first"):
                VibeWikiMcpServer(root)

            self.assertFalse((root / ".vibewiki").exists())

    def test_stdio_protocol_and_cli_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            }
            output = io.StringIO()
            serve_mcp(root, instream=io.StringIO(json.dumps(request) + "\n"), outstream=output)
            response = json.loads(output.getvalue())
            parser = build_parser()
            mcp_args = parser.parse_args(["--project", str(root), "mcp"])
            agent_args = parser.parse_args(["--project", str(root), "agent", "install"])
            guard_args = parser.parse_args(
                ["--project", str(root), "guard", "--for", "publish a release"]
            )
            guard_output = io.StringIO()
            with redirect_stdout(guard_output):
                guard_code = run_cli(guard_args)

            self.assertEqual(response["id"], 1)
            self.assertIn("tools", response["result"])
            self.assertEqual(mcp_args.subcommand, "mcp")
            self.assertEqual(agent_args.agent_command, "install")
            self.assertEqual(guard_code, 0)
            self.assertEqual(json.loads(guard_output.getvalue())["scope"], "approved")


if __name__ == "__main__":
    unittest.main()
