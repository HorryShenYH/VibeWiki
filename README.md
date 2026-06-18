# VibeWiki

Turn AI coding sessions into reviewed project memory.

> Stop solving the same bug twice.

AI coding is fast, but the useful knowledge often disappears into chat logs,
temporary commands, diffs, and test output. VibeWiki captures what actually
worked, turns it into reviewable Wiki patches, composable skilllets, prompt
patterns, workflows, and Agent Rule patches, then feeds that knowledge back into
future development.

In plain words: VibeWiki is a memory layer for AI coding. After Codex, Claude, or
Cursor helps you fix something, VibeWiki turns the messy conversation into small
reusable capability units so the next developer or agent can compose them instead
of rediscovering them.

The first version is intentionally local and conservative:

- `vibewiki init` creates the project memory folders.
- `vibewiki capture` records one coding session, including git diff and notes.
- `vibewiki import-markdown` imports an exported Codex, Claude, or Cursor session.
- `vibewiki distill` creates candidate memory patches.
- `vibewiki validate-skill` checks Skill Patch quality gates.
- `vibewiki review` records human approval.
- `vibewiki merge` appends approved patches to docs, skills, and agent rules.

VibeWiki does not directly mutate your main knowledge base before review. Facts
start as candidates, uncertain claims stay marked, and missing context becomes
questions for a human.

## What It Does

VibeWiki treats a finished coding session as evidence, not as a skill by itself.
One session may contain several reusable ideas; several sessions may improve the
same idea over time.

It creates reviewable artifacts:

- a Wiki note that explains what changed and why
- skilllets: small, composable capability units
- prompt patterns: reusable prompts and agent task package shapes
- workflows: larger procedures composed from skilllets
- a compatibility Skill Patch with commands, probes, evidence, and failure modes
- Agent Rules for future coding agents
- clarification questions for anything that is still uncertain

The important bit: it keeps raw evidence, asks for human approval, and only then
merges knowledge into the project.

When approved units are merged, VibeWiki updates `.vibewiki/skill_registry.yaml`.
Later sessions use that registry to update existing skilllets by exact slug or
alias instead of creating duplicates. Lower-confidence keyword overlap becomes a
merge suggestion for review rather than an automatic merge.

## Why This Exists

AI coding agents are powerful, but they forget project-specific lessons:

- the exact command that reproduced a simulator bug
- the row/lane/config setting that made a benchmark valid
- the workaround that should not be repeated later
- the test output that proved a fix
- the reason a parameter changed

VibeWiki gives those lessons a home.

## Install From Source

```bash
cd /path/to/VibeWiki
python3 -m pip install -e .
```

You can also run it directly while developing:

```bash
python3 -m vibewiki.cli --help
```

## Quick Start

In any project you want to give memory:

```bash
vibewiki init
vibewiki capture --goal "Fix simulator mismatch" \
  --outcome "Aligned VEMU output with the reference trace" \
  --command "make run-vemu" \
  --command "python3 compare_outputs.py" \
  --tests "compare_outputs.py passed"
vibewiki distill
vibewiki validate-skill
vibewiki review --approve
vibewiki merge
```

Or import a saved AI session:

```bash
vibewiki import-markdown ./codex-session.md
vibewiki distill
vibewiki validate-skill
vibewiki review --approve
vibewiki merge
```

This creates:

```text
.vibewiki/
  config.yaml
  skill_registry.yaml
  sessions/
  patches/
  reviews/
docs/wiki/
skills/
  skilllets/
  prompt_patterns/
  workflows/
AGENTS.md
```

Use strict validation when you want warnings to block promotion:

```bash
vibewiki validate-skill --strict
```

`import-markdown` preserves the full original file as `raw_session.md`, then
creates a normalized `session.md` with detected title, outcome signals, commands,
verification hints, and benchmark hints. Treat the normalized fields as a review
draft, not as final truth.

## Project Philosophy

1. Trust beats automation.
2. Record the final verified path, not every failed attempt.
3. Keep knowledge out of the main Wiki until a human approves it.
4. Extract small skilllets instead of one oversized session-specific skill.
5. Let repeated sessions evolve the same skilllet by appending evidence.
6. Validate Skill contracts before they become project guidance.
7. Treat agent-facing rules as a first-class output.
8. Start local, then add GitHub PR workflows and retrieval.

## Roadmap

- `v0.1`: local CLI and reviewable memory patch workflow
- `v0.2`: GitHub PR comment workflow
- `v0.3`: Skilllet versioning, deprecation, and cross-session evolution
- `v0.4`: Venus/VEMU/gem5/RTL case study
- `v0.5`: local Markdown retrieval with citations and LLM-Wiki-style search/read
- `v1.0`: CLI, GitHub Action, docs, examples, and demo video

## LLM-Wiki Compatibility

VibeWiki is designed to complement LLM-Wiki-style systems. VibeWiki handles the
trusted ingestion path from AI coding sessions to reviewed project memory; an
LLM-Wiki-style layer can later expose that approved memory through search, read,
link traversal, `llms-full.txt`, or prompt-cache workflows.

See [`docs/research_llm_wiki.md`](docs/research_llm_wiki.md).

## Ctx2Skill-Inspired Direction

VibeWiki can also borrow from Ctx2Skill-style skill evolution. The practical
version is simple: every reusable skilllet should include invocation conditions,
contraindications, probes, evidence, and environment requirements. Later,
VibeWiki can replay skilllet updates against older sessions before promoting
them.

See [`docs/research_ctx2skill.md`](docs/research_ctx2skill.md).

## Killer Demo

Venus is the first serious case study: use VibeWiki to preserve hard-won
knowledge from VEMU simulation, gem5 performance runs, RTL alignment, MATLAB
gold comparisons, compiler backend debugging, and LDPC benchmark validation.

See the first real example in
[`examples/venus/real_sessions/cmxmul_ofdm`](examples/venus/real_sessions/cmxmul_ofdm/README.md).
