# Ecosystem Positioning

VibeWiki is designed to complement the AI coding ecosystem, not replace it.

The project borrows openly from tools that already do important parts of the
workflow well. VibeWiki's job is to add an assured memory lifecycle around those
tools.

## Repository Ingestion

Repomix and Gitingest are strong at turning a repository into compact,
LLM-friendly context. VibeWiki should use that experience instead of rebuilding
every ingestion detail from scratch.

VibeWiki adds:

- project briefs that become part of the Wiki
- follow-up questions and missing verification notes
- a path from repository understanding to source-linked, assured memory

Planned integration shape:

```bash
vibewiki understand --backend local
vibewiki understand --backend repomix
vibewiki understand --backend gitingest
```

## Repository Understanding

DeepWiki, RepoAgent, CodeWiki-style systems, and repo-map approaches are strong
at explaining what a repository looks like right now.

VibeWiki adds:

- evidence from actual work, not only static code
- commands, tests, diffs, and failure modes
- local assurance for ordinary knowledge and human review for risky guidance
- repeated-session updates to the same skilllet or workflow

Short version:

```text
Repo understanding tools explain the codebase.
VibeWiki preserves what developers and agents learned while changing it.
```

## AI Coding Agents

Codex, Claude Code, Cline, Aider, OpenHands, Cursor, and Copilot are execution
surfaces. They help users inspect, edit, test, and review code.

VibeWiki adds:

- a durable record of what worked
- reviewable candidate findings
- project and personal memory
- reusable skilllets, prompt patterns, workflows, and agent rules

VibeWiki should ingest their exported conversations or summaries where possible,
but it should not become another coding agent.

## Agent Instructions And Skills

AGENTS.md, Anthropic-style skills, Cursor rules, and similar instruction files
are becoming standard ways to give agents durable guidance.

VibeWiki adds:

- evidence-backed generation of those instructions
- assurance and review records before promotion
- skill evolution logs
- downgrade paths when something is useful knowledge but not a procedure

The ideal flow is:

```text
successful session -> candidate skilllet -> review -> AGENTS.md / Skill export
```

## Personal Knowledge Tools

Obsidian, Logseq, GitHub Wiki, and Markdown docs are excellent places to store
knowledge.

VibeWiki adds the compiler:

```text
AI collaboration trace -> typed candidate memory -> assurance -> Wiki update
```

The storage should stay boring and portable. The lifecycle is the product.

## Conversation History Readers

[S40911120/recensa](https://github.com/S40911120/recensa) makes Claude Code's
raw JSONL history readable, searchable, and auditable. Its strongest general
design is the separation of source transcripts, a disposable search index, and
durable user curation.

VibeWiki borrows that source-layer discipline:

- original imported conversations remain inspectable
- body search returns evidence from the conversation library
- local pins, tags, titles, and notes stay separate from generated memory
- deletion is guarded and provenance-aware
- a future large-library index can be rebuilt without changing curated state

The projects stop at different boundaries:

```text
Recensa  -> inspect and audit detailed Claude Code transcripts
VibeWiki -> compile conversations from many agents into evolving team memory
```

VibeWiki's local assurance and exception review remain a separate policy layer;
they are not features derived from Recensa. See `docs/research_recensa.md` for
the source review and adaptation decisions.

## Design Principle

VibeWiki should acknowledge the tools it learns from and integrate the best
ones where it makes sense. Its differentiator is not owning every step.

Its differentiator is:

```text
evidence-backed, assurance-first, tool-agnostic, evolving memory
```
