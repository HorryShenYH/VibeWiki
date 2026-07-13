# Ecosystem Positioning

VibeWiki is designed to complement the AI coding ecosystem, not replace it.

The project borrows openly from tools that already do important parts of the
workflow well. VibeWiki's job is to add a reviewed memory lifecycle around those
tools.

## Repository Ingestion

Repomix and Gitingest are strong at turning a repository into compact,
LLM-friendly context. VibeWiki should use that experience instead of rebuilding
every ingestion detail from scratch.

VibeWiki adds:

- project briefs that become part of the Wiki
- follow-up questions and missing verification notes
- a path from repository understanding to reviewed memory

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
- human review before permanent documentation changes
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
- review records before promotion
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
AI collaboration trace -> typed candidate memory -> reviewed Wiki update
```

The storage should stay boring and portable. The lifecycle is the product.

## Design Principle

VibeWiki should acknowledge the tools it learns from and integrate the best
ones where it makes sense. Its differentiator is not owning every step.

Its differentiator is:

```text
evidence-backed, review-first, tool-agnostic, evolving memory
```
