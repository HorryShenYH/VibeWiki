# AI Agent Integration

VibeWiki gives coding agents a small approved-memory map and lets them retrieve
more only when the task requires it. It does not inject the whole Wiki into
every prompt.

## Quick Start

From a VibeWiki project root:

```bash
vibewiki agent install
```

This command is idempotent. It:

- adds a managed VibeWiki block to `AGENTS.md`
- writes the portable `.vibewiki/agent.json` MCP descriptor
- prints the exact local stdio MCP command for the project
- prints a Codex registration command

Codex users can install and register in one step:

```bash
vibewiki agent install --register-codex
```

Start a new agent session after registration so the client discovers the new
tools. Run `vibewiki doctor` to check the project-side installation.

## Agent Tools

The local MCP server is started with:

```bash
vibewiki --project . mcp
```

It exposes four read-only tools:

| Tool | Purpose |
| --- | --- |
| `vibewiki_brief` | Load a compact project and approved-memory map once per task |
| `vibewiki_guard` | Find known issues, rules, workflows, and verification constraints |
| `vibewiki_search` | Search compact approved memory and return small refs |
| `vibewiki_read` | Read only the selected refs returned by search |

The normal agent flow is:

```text
brief -> guard(task) -> search(query) -> read(selected refs) -> work
```

## Trust Boundary

Agent retrieval is approved-only by default. Candidate memory can be requested
with `include_candidates: true`, but every such response carries an explicit
unreviewed warning. `vibewiki_read` can only open Wiki, skill, workflow, and
candidate files already indexed as VibeWiki memory; it cannot be used as an
arbitrary project file reader.

The MCP server does not expose a write tool. New experience still enters through
capture/import, becomes a candidate, and requires human review before it can be
returned as trusted agent memory.

## Token Behavior

- `vibewiki_brief` returns counts, examples, rules, and navigation rather than
  full documents.
- `vibewiki_search` returns compact claims, methods, confidence, recorder, and
  source refs.
- Reviewed sections keep their original recorder when a merge marker can be
  linked back to the local event ledger.
- `vibewiki_read` is explicit and character-budgeted.
- Stable approved memory remains in local Markdown and can be cached by the
  agent client.
- Keyword retrieval always works locally; embeddings remain optional.

## Clients Without MCP

Use the compatible context-pack path:

```bash
vibewiki context \
  --for "change the authentication client safely" \
  --scope approved \
  --format json \
  --max-items 5 \
  --max-chars 500
```

Scripts can run the same pre-edit safety check used by the MCP tool:

```bash
vibewiki guard --for "change the authentication client safely" --max-items 6
```

`context` now defaults to `retrieval.agent_scope`, which is `approved` in new
projects. Human `ask` and `search` can still inspect candidates when desired.

## Protocol Smoke Test

The server uses newline-delimited JSON-RPC over stdio and writes no non-protocol
text to standard output:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | vibewiki --project . mcp
```

The response should list the four `vibewiki_*` tools.
