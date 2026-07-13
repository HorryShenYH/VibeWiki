# MVP

## Goal

Build a local CLI that records one successful AI coding session and converts it
into reviewed, composable project memory.

## User Story

A developer uses an AI coding agent to fix a bug, ship a feature, investigate an
incident, improve tooling, or explore a research idea. After the session, they
run:

```bash
vibewiki capture
vibewiki distill
vibewiki validate-skill
vibewiki review --approve
vibewiki merge
```

If the session was already exported from Codex, Claude, Cursor, or another AI
tool, they can start with:

```bash
vibewiki import-markdown path/to/session.md
```

The project receives approved findings, a Wiki note, reusable skilllets/prompt
patterns/workflows, a compatibility Skill draft, and updated agent guidance.

## v0.1 Commands

- `vibewiki init`: create local memory structure
- `vibewiki capture`: save session notes, git diff, metadata
- `vibewiki import-markdown`: preserve raw exported session Markdown and create
  a normalized session record
- `vibewiki distill`: create candidate patches
- `vibewiki validate-skill`: check required Skill sections, probes, evidence,
  confidence, and TODOs
- `vibewiki review`: approve or inspect patches
- `vibewiki merge`: append approved patches to project memory

## Success Criteria

- Works in a normal git project.
- Works without network access.
- Stores the original session evidence.
- Imports exported Markdown sessions without requiring an LLM.
- Splits a long session into multiple composable units when several reusable
  ideas appear.
- Keeps non-procedural memory as findings: knowledge, issues, todos, ideas,
  research notes, and directions.
- Separates candidates from approved knowledge.
- Produces at least one question when context is missing.
- Flags incomplete Skill contracts before review.
- Avoids writing to final docs before review.

## First Real Case

Use a common API bug-fix session:

- preserve the reason retries were unsafe
- record the verified test command
- capture the reusable retry-policy rule
- keep failed experiments as evidence without promoting them to guidance
- let a future developer or agent retrieve the answer without rereading the chat

The demo should show that useful memory is smaller than the original
conversation and more actionable than a raw transcript.
