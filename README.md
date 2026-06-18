# VibeWiki

Turn AI coding sessions into reviewed project memory.

> Stop solving the same bug twice.

AI coding is fast, but the useful knowledge often disappears into chat logs,
temporary commands, diffs, and test output. VibeWiki captures what actually
worked, turns it into reviewable Wiki, Skill, and Agent Rule patches, and feeds
that knowledge back into future development.

In plain words: VibeWiki is a memory layer for AI coding. After Codex, Claude, or
Cursor helps you fix something, VibeWiki saves the final verified path so the
next developer or agent can reuse it instead of rediscovering it.

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

VibeWiki turns one finished coding session into four useful artifacts:

- a Wiki note that explains what changed and why
- a reusable Skill with commands, probes, evidence, and failure modes
- Agent Rules for future coding agents
- clarification questions for anything that is still uncertain

The important bit: it keeps raw evidence, asks for human approval, and only then
merges knowledge into the project.

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
  sessions/
  patches/
  reviews/
docs/wiki/
skills/
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
4. Generate reusable Skills, not just prose documentation.
5. Validate Skill contracts before they become project guidance.
6. Treat agent-facing rules as a first-class output.
7. Start local, then add GitHub PR workflows and retrieval.

## Roadmap

- `v0.1`: local CLI and reviewable memory patch workflow
- `v0.2`: GitHub PR comment workflow
- `v0.3`: Skill versioning and deprecation
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
version is simple: every reusable Skill should include invocation conditions,
contraindications, probes, evidence, and environment requirements. Later,
VibeWiki can replay Skill updates against older sessions before promoting them.

See [`docs/research_ctx2skill.md`](docs/research_ctx2skill.md).

## Killer Demo

Venus is the first serious case study: use VibeWiki to preserve hard-won
knowledge from VEMU simulation, gem5 performance runs, RTL alignment, MATLAB
gold comparisons, compiler backend debugging, and LDPC benchmark validation.

See the first real example in
[`examples/venus/real_sessions/cmxmul_ofdm`](examples/venus/real_sessions/cmxmul_ofdm/README.md).
