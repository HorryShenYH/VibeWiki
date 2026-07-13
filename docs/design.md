# VibeWiki Design

## One Sentence

VibeWiki is a project and personal memory framework for AI coding. It can
bootstrap a baseline Wiki from a repository scan, then turn successful Codex,
Claude, Cursor, ChatGPT, or Copilot sessions into reviewed Wiki patches, typed
findings, composable skilllets, prompt patterns, workflows, and agent-facing
rules.

## Core Loop

```text
bootstrap -> capture/import -> distill -> review -> merge -> reuse
```

## Core Model

```text
Project Scan / Session -> Findings -> Promotion -> Skilllets / Patterns / Workflows -> Review -> Merge
```

VibeWiki has two memory scopes:

- `project`: repository-specific facts, commands, caveats, architecture notes,
  build/test workflows, and agent rules
- `personal`: cross-project practices, reusable prompts, research notes,
  instincts, and workflows that should follow the user across repositories

The same review-first pipeline applies to both scopes. Project memory should be
more concrete and evidence-bound; personal memory should be promoted only when a
lesson proves useful beyond one repository.

## Bootstrap And Growth

VibeWiki supports two complementary modes:

- bootstrap memory: run `vibewiki understand` or a project-specific build/test
  skill to produce the first project brief, first-file reading list, and
  baseline commands
- grow memory: import or capture vibe-coding conversations, distill what
  changed, review candidates, and merge approved knowledge or skills back into
  the Wiki

The bootstrap pass gives an AI agent enough orientation to start work without
pretending the Wiki is complete. The growth loop makes the Wiki better every
time the user solves a real problem with AI.

A session is evidence, not a skill. One long session may contain multiple
purposes and reusable ideas. A reusable skilllet should stay small enough to
compose with others, and repeated sessions should improve the same skilllet
rather than creating redundant copies.

Findings are the default memory unit. They can be:

- `knowledge`: durable facts and explanations
- `issue`: discovered problems, caveats, and deferred bugs
- `todo`: follow-up work
- `idea`: sparks that may matter later
- `research_note`: hypotheses, experiments, references, and research context
- `direction`: project or research directions

A finding is promoted to a skilllet only when it is procedural: it has a clear
trigger, inputs, outputs, steps, and verification. This keeps the skill library
useful instead of turning every interesting sentence into a skill.

## Skill Registry

Approved units are indexed in `.vibewiki/skill_registry.yaml` with:

- canonical slug
- kind
- title
- aliases
- keywords
- evidence sessions
- status

Distillation uses the registry before writing patches:

- exact slug or alias match: update the existing unit
- strong keyword overlap: write a merge suggestion for human review
- no match: create a new candidate unit

The registry is intentionally conservative. It should prevent obvious duplicate
skilllets without silently merging two concepts that only look similar.

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

A project bootstrap pass can provide:

- README or manifest summary
- file tree and language shape
- main entrypoints
- build, test, and package scripts
- docs and test locations
- first files to read
- missing verification or documentation follow-ups

## Outputs

VibeWiki creates candidate patches:

- Knowledge Patch: facts and suggested Wiki updates
- Skilllets: small repeatable capability units with evidence and verification
- Prompt Patterns: reusable prompts and agent task package templates
- Workflows: larger procedures composed from skilllets and prompt patterns
- Findings: typed non-skill memory for knowledge, issues, todos, ideas, notes,
  and directions
- Skill Patch: compatibility review entry point for current tooling
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
can become auditable, composable memory that a person can accept or reject.

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
session evidence -> skilllets / patterns / workflows -> structural validation -> human review
```

The later Ctx2Skill-inspired stance:

```text
skilllet -> probes -> failure analysis -> mutation -> cross-session replay -> review
```

See `docs/research_ctx2skill.md` for the current notes.
