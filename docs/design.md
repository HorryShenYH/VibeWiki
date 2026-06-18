# VibeWiki Design

## One Sentence

VibeWiki is a project memory framework for AI coding. It turns successful
Codex, Claude, Cursor, or Copilot sessions into reviewed Wiki patches,
reusable Skills, and agent-facing rules.

## Core Loop

```text
capture -> distill -> review -> merge -> reuse
```

## Inputs

One AI coding session can provide:

- user goal
- final outcome
- git diff
- changed files
- key commands
- test output
- benchmark output
- AI conversation summary
- user notes
- things that should not be recorded

## Outputs

VibeWiki creates candidate patches:

- Knowledge Patch: facts and suggested Wiki updates
- Skill Patch: repeatable procedure and verification steps
- Agent Rule Patch: rules for future coding agents
- Clarifying Questions: missing context before merge

## Knowledge States

- `candidate`: generated from a session
- `verified`: backed by command, test, benchmark, diff, or commit evidence
- `approved`: accepted by a human reviewer
- `uncertain`: useful but missing proof or scope
- `deprecated`: kept for history but no longer recommended

## Design Correction From The Original Plan

The original plan was broad and exciting, but v0.1 should be narrower:

- Do not start with RAG.
- Do not start with a web UI.
- Do not depend on full chat-log ingestion.
- Do not require an LLM for the first working loop.
- Do not auto-edit the final Wiki.

The first release should prove one thing well: a successful development session
can become an auditable memory patch that a person can accept or reject.

## Non-Goals For v0.1

- semantic merge
- vector database
- multi-user permission model
- full PR bot
- automatic IDE plugin
- autonomous Wiki rewriting

## Future LLM Role

The LLM should improve distillation quality, not own trust. It can summarize,
classify, and ask questions, but the system should preserve evidence and keep
human approval in the loop.

## Relationship To LLM-Wiki

LLM-Wiki-style systems are useful downstream consumers of VibeWiki memory. They
turn structured Wiki pages into agent-traversable knowledge with search, read,
and link-following operations.

VibeWiki should stay focused on the upstream trust problem:

```text
AI coding session -> reviewed memory patch -> approved Wiki / Skill / Agent Rule
```

Then it can export approved memory to LLM-Wiki-like retrieval surfaces:

```text
approved memory -> local Markdown search/read -> llms-full.txt -> future MCP tools
```

See `docs/research_llm_wiki.md` for the current integration notes.

## Relationship To Ctx2Skill

Ctx2Skill-style systems evolve skills from context using generated probes,
reasoner attempts, judge feedback, and replay across earlier cases. VibeWiki can
borrow this after the basic trusted-memory loop works.

The near-term VibeWiki stance:

```text
session evidence -> Skill Patch -> structural validation -> human review
```

The later Ctx2Skill-inspired stance:

```text
Skill Patch -> probes -> failure analysis -> skill mutation -> cross-session replay -> review
```

See `docs/research_ctx2skill.md` for the current notes.
