# LLM-Wiki Notes

This note records what VibeWiki should borrow from the emerging LLM Wiki line of
work, and where VibeWiki should stay deliberately different.

## Sources Reviewed

- Retrieval as Reasoning: Self-Evolving Agent-Native Retrieval via LLM-Wiki
  - https://arxiv.org/abs/2605.25480
- WiCER: Wiki-memory Compile, Evaluate, Refine Iterative Knowledge Compilation
  for LLM Wiki Systems
  - https://arxiv.org/abs/2605.07068

## What LLM-Wiki Gets Right

LLM-Wiki argues that retrieval should be an agent-controlled reasoning process,
not a single top-k lookup. Knowledge is compiled into structured Wiki pages with
links, and the agent gets simple tools such as search, read, and link traversal.

This is directly useful for VibeWiki. Project memory should not become a pile of
flat Markdown notes. Agents should be able to:

- search by concept, file, subsystem, error, or command
- read a page with source evidence
- follow links to related bugs, Skills, files, and rules
- stop only after evidence is sufficient

LLM-Wiki also introduces an Error Book for persistent self-correction. This is a
strong fit for VibeWiki because AI coding produces recurring mistakes: wrong
commands, stale benchmark assumptions, broken links, unsupported facts, and
over-generalized rules.

WiCER adds a complementary lesson: compiling raw documents into a Wiki can drop
critical facts. It closes that gap with a compile-evaluate-refine loop where
diagnostic probes reveal missing facts and force the next compilation to preserve
them.

For VibeWiki, those probes should be real project tasks:

- Can an agent rerun the simulator from the Skill?
- Can it explain why a parameter changed?
- Can it find the known issue before repeating a failed fix?
- Can it reproduce a benchmark claim from the recorded command and config?

## How VibeWiki Is Different

VibeWiki should not try to be a generic LLM-Wiki clone.

LLM-Wiki starts from documents and optimizes retrieval. VibeWiki starts from AI
coding sessions and optimizes trust.

The core VibeWiki artifact is a reviewed memory patch:

```text
session evidence -> candidate patch -> human review -> approved project memory
```

The distinctive parts are:

- git diff and changed-file grounding
- commands and verification outputs as first-class evidence
- benchmark configuration capture
- Skill generation for future coding agents
- Agent Rule patches for `AGENTS.md`, `CLAUDE.md`, Cursor rules, and `llms.txt`
- clarification-before-merge instead of silent Wiki mutation

## Best Integration Shape

VibeWiki should become an upstream memory compiler for LLM-Wiki-style systems.

```text
Codex / Claude / Cursor session
        |
        v
VibeWiki capture + distill + review
        |
        v
Approved Wiki / Skill / Agent Rule pages
        |
        v
LLM-Wiki-style search/read/follow traversal or full-context cache
```

This lets the two ideas cooperate:

- VibeWiki keeps project memory trustworthy.
- LLM-Wiki makes that memory easy for agents to traverse.

## Design Ideas To Borrow

### 1. Page Metadata

Approved VibeWiki pages should eventually include lightweight frontmatter:

```yaml
title: CMXMUL vs OFDM Fixed-Point Multiply
aliases:
  - vcmxmul
  - OFDM complex multiply
tags:
  - venus
  - vemu
  - rtl
  - fixed-point
sources:
  - .vibewiki/sessions/...
status: approved
```

This helps search, page selection, and link traversal.

### 2. Bidirectional Links

VibeWiki should generate explicit links between:

- Wiki notes
- Skills
- Agent rules
- source files
- known issues
- raw sessions

Example:

```markdown
Related:
- [[skills/evaluate_fixed_point_cmxmul_replacement]]
- [[docs/wiki/known_issues#vcmxmul-ofdm-error-amplification]]
- `Task_nrOFDMDemodulation.c`
```

### 3. Error Book

Add `.vibewiki/error_book.yaml` later:

```yaml
- id: dangling-link-001
  status: open
  type: dangling_link
  root_cause: Generated a link before checking the target page exists.
  constraint: Do not emit wikilinks unless the target file exists or is created by the same patch.
  verification: run vibewiki validate-links
```

This is a natural extension of VibeWiki's current clarifying questions.

### 4. Diagnostic Probes

For each approved Skill, generate one or more probes:

- expected command exists
- required environment variables are mentioned
- verification command is recorded
- benchmark claims cite config and result
- agent can answer a small task-specific question from the Wiki

This borrows WiCER's compile-evaluate-refine idea but adapts it to engineering
memory.

### 5. Two Retrieval Modes

VibeWiki should support two downstream modes:

- Small memory: export `llms-full.txt` and use full-context or prompt-cache workflows.
- Larger memory: expose `wiki_search` and `wiki_read` over local Markdown.

Do not force vector databases in v0.1.

## Roadmap Impact

Near term:

- Add `vibewiki import-markdown`.
- Add link and source metadata to generated patches.
- Add `vibewiki validate` for dangling links, missing evidence, and unresolved questions.

Medium term:

- Add `.vibewiki/error_book.yaml`.
- Add `vibewiki ask` using local Markdown search/read with citations.
- Add `vibewiki export --format llms-full`.

Later:

- Optional adapter to an external LLM-Wiki implementation if one stabilizes.
- Optional MCP-style tools: `wiki_search`, `wiki_read`, `wiki_follow`.

## Positioning

Suggested public positioning:

> VibeWiki is a trusted ingestion and review layer for LLM-Wiki-style project
> memory. It turns AI coding sessions into approved Wiki pages, reusable Skills,
> and agent rules, then exports them into search/read/traverse formats that
> coding agents can use.

