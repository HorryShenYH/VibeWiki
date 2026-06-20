# VibeWiki

Turn AI coding sessions into reviewed project memory.

> Stop solving the same bug twice.

AI coding is fast, but the useful knowledge often disappears into chat logs,
temporary commands, diffs, and test output. VibeWiki captures what actually
worked, turns it into reviewable findings, Wiki patches, composable skilllets,
prompt patterns, workflows, and Agent Rule patches, then feeds that knowledge
back into future development.

In plain words: VibeWiki is a memory layer for AI coding. After Codex, Claude, or
Cursor helps you fix something, VibeWiki turns the messy conversation into
durable memory: facts, issues, todos, ideas, research notes, directions, and
small reusable capability units.

The first version is intentionally local and conservative:

- `vibewiki init` creates the project memory folders.
- `vibewiki capture` records one coding session, including git diff and notes.
- `vibewiki import-markdown` imports an exported Codex, Claude, or Cursor session.
- `vibewiki import-url` imports a shared conversation URL, including ChatGPT share links.
- `vibewiki distill` creates candidate memory patches.
- `vibewiki review-board` renders a local HTML review board for candidate patches.
- `vibewiki review-ui` serves a clickable local review UI for SSH/remote workflows.
- `vibewiki validate-skill` checks Skill Patch quality gates.
- `vibewiki review` records human approval.
- `vibewiki review-item` records item-level approve/reject/defer/downgrade/merge/edit decisions.
- `vibewiki merge` appends approved patches to docs, skills, and agent rules.
- `vibewiki ask` answers human questions from approved and candidate memory.
- `vibewiki context` emits compact YAML/JSON context packs for AI agents.
- `vibewiki search` inspects the retrieved evidence directly.

VibeWiki does not directly mutate your main knowledge base before review. Facts
start as candidates, uncertain claims stay marked, and missing context becomes
questions for a human.

VibeWiki can run in bilingual mode. The default project configuration keeps the
user's working language while adding brief bilingual structure for Wiki pages
and review surfaces:

```yaml
language:
  mode: bilingual
  primary: zh
  secondary: en
```

## What It Does

VibeWiki treats a finished AI conversation as evidence, not as a skill by
itself. One conversation may contain several useful ideas; several conversations
may improve the same idea over time.

It creates reviewable artifacts:

- a Wiki note that explains what changed and why
- findings: knowledge, issues, todos, ideas, research notes, and directions
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
vibewiki review-board
vibewiki validate-skill
vibewiki review --approve
vibewiki merge
```

Or import a saved AI session:

```bash
vibewiki import-markdown ./codex-session.md
vibewiki distill
vibewiki review-board
vibewiki validate-skill
vibewiki review --approve
vibewiki merge
```

Or import a shared ChatGPT conversation link:

```bash
vibewiki import-url "https://chatgpt.com/share/..."
vibewiki distill
vibewiki review-board
vibewiki review --approve
vibewiki merge
```

`import-url` keeps both a readable `raw_session.md` and the original
`raw_source.html`. For ChatGPT share pages, it can extract conversations from
the page data stream instead of only reading the visible login/sidebar shell.
If a page is private, expired, or rendered in a new unsupported format, the raw
HTML is still preserved so the parser can be improved later.

This creates:

```text
.vibewiki/
  config.yaml
  skill_registry.yaml
  sessions/
  patches/
  reviews/
docs/wiki/
  knowledge.md
  known_issues.md
  todos.md
  ideas.md
  research_notes.md
  directions.md
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

`import-markdown` and `import-url` preserve the full original evidence, then
create a normalized `session.md` with detected title, outcome signals, commands,
verification hints, and benchmark hints. Treat the normalized fields as a review
draft, not as final truth.

`review-board` writes a static `review_board.html` beside the selected patch. It
groups findings, candidate skilllets, prompt patterns, workflows, open
questions, merge suggestions, and approve/merge commands into one page so review
does not require opening a directory full of Markdown files one by one.

For remote development over SSH, `review-ui` is usually easier than opening the
static HTML. It starts a local-only server that VSCode Remote-SSH can forward to
your browser:

```bash
vibewiki review-ui --patch-dir .vibewiki/patches/<session> --port 8765
```

Open `http://127.0.0.1:8765/` after forwarding the port. The page keeps review
deliberately small: preview a candidate, submit it, discard it, edit the
candidate Markdown directly, or write a short revision instruction and let the
configured LLM generate a revised candidate. The LLM only rewrites the draft;
the human still decides whether to submit it. Candidate Markdown is previewed as
rendered Markdown by default, and the review surface can switch between Chinese
and English labels while keeping the underlying Markdown memory in English.

For fine-grained review, use the per-item commands shown on each card:

```bash
vibewiki review-item --patch-dir .vibewiki/patches/<session> \
  --item findings/todo__example.md --decision approve
vibewiki review-item --patch-dir .vibewiki/patches/<session> \
  --item skilllets/example.md --decision downgrade --target knowledge
vibewiki review-item --patch-dir .vibewiki/patches/<session> \
  --item skilllets/new-name.md --decision merge --target existing-skilllet
vibewiki review-item --patch-dir .vibewiki/patches/<session> \
  --item findings/idea__example.md --decision edit \
  --title "Reviewed title" --summary "Reviewed summary"
```

Item decisions are stored as JSON under `.vibewiki/reviews/`. During `merge`,
rejected or deferred items are skipped, downgraded items are written to the Wiki,
merged reusable units append to the requested existing slug, and edited items
carry the reviewed title or summary.

VibeWiki also dogfoods this workflow on its own design conversations. See
[`docs/improvement_backlog.md`](docs/improvement_backlog.md) and
[`docs/wiki/`](docs/wiki/) for the current reviewed product memory.

## Reuse Memory

VibeWiki has two reuse entrances:

```bash
vibewiki ask "CloudRIC 能不能说比传统基站省电？"
vibewiki context --for "debug VCMXMUL mismatch"
```

`ask` is for humans. It searches approved memory and candidate patches, then
answers with evidence. If an OpenAI-compatible LLM API is configured, VibeWiki
uses it to write a concise answer. Otherwise it returns a retrieval-based answer
draft with source snippets.

`context` is for AI agents. It returns a compact, machine-readable context pack
so a coding agent can start with relevant facts, skills, warnings, and sources
instead of making the user rewrite a long prompt:

```bash
vibewiki context --for "run VEMU F5" --format json --max-items 5 --max-chars 500
```

`search` shows the raw ranked evidence:

```bash
vibewiki search "VEMU F5 TARGET_DAG"
```

Search covers both reviewed memory and unreviewed patches by default. Results
are marked as `approved` or `candidate`.

Retrieval is local-first. VibeWiki always has a keyword/BM25 fallback. If an
OpenAI-compatible embedding API is configured, it adds semantic retrieval and
caches vectors under `.vibewiki/cache/embeddings/`, which is ignored by Git:

```bash
export VIBEWIKI_EMBEDDING_BASE_URL="https://api.openai.com/v1"
export VIBEWIKI_EMBEDDING_API_KEY="..."
export VIBEWIKI_EMBEDDING_MODEL="text-embedding-3-small"
```

LLM answers use OpenAI-compatible chat completions:

```bash
export VIBEWIKI_LLM_BASE_URL="https://api.openai.com/v1"
export VIBEWIKI_LLM_API_KEY="..."
export VIBEWIKI_LLM_MODEL="gpt-4.1-mini"
```

The same environment variable shape can point at OpenRouter, DeepSeek, local
OpenAI-compatible servers, or other compatible providers.

## Project Philosophy

1. Trust beats automation.
2. Record the final verified path, not every failed attempt.
3. Keep knowledge out of the main Wiki until a human approves it.
4. Extract small skilllets instead of one oversized session-specific skill.
5. Keep non-procedural memory as findings rather than forcing it into skills.
6. Let repeated sessions evolve the same skilllet by appending evidence.
7. Validate Skill contracts before they become project guidance.
8. Treat agent-facing rules as a first-class output.
9. Start local, then add GitHub PR workflows and retrieval.

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

## ECC-Inspired Direction

ECC shows a mature cross-harness agent layer: skills, hooks, agents, rules,
MCPs, installers, and continuous learning. VibeWiki should not become a giant
harness bundle. The useful idea to borrow is smaller: reviewed atomic
`instincts` with scope, confidence, evidence, and a promotion path into
skilllets, workflows, or agent rules.

This keeps VibeWiki positioned as an upstream trusted memory compiler that can
feed systems such as ECC, Codex skills, Claude skills, Cursor rules, and
LLM-Wiki-style retrieval layers.

See [`docs/research_ecc.md`](docs/research_ecc.md).

## Killer Demo

Venus is the first serious case study: use VibeWiki to preserve hard-won
knowledge from VEMU simulation, gem5 performance runs, RTL alignment, MATLAB
gold comparisons, compiler backend debugging, and LDPC benchmark validation.

See the first real example in
[`examples/venus/real_sessions/cmxmul_ofdm`](examples/venus/real_sessions/cmxmul_ofdm/README.md).
