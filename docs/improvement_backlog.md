# Improvement Backlog

This page records VibeWiki's current product gaps and next directions. It is a
curated memory note from the VibeWiki self-review conversation on 2026-06-19.

## Current Assessment

VibeWiki is now a usable MVP with a full loop:

```text
capture/import -> distill -> review-board -> review -> merge -> search/ask/context
```

It is not yet a mature open-source product. The strongest part is the trusted
memory-compilation concept. The weakest parts are general distillation quality,
plugin boundaries, public demo readiness, and review/edit ergonomics.

Dogfooding note: this backlog was also imported as a VibeWiki session on
2026-06-19. The generated candidate patch and review board are useful evidence,
but the current local distiller extracted the product-design discussion too
shallowly. That confirms that product/research conversations need better
distillation than the original coding-session heuristics.

## Innovation

VibeWiki is a trusted memory compiler for AI conversations:

```text
AI conversation -> evidence -> candidate memory -> human review -> approved memory -> reuse
```

Its distinct traits are:

- evidence-first memory with raw sessions, commands, tests, diffs, and sources
- review-first promotion, where generated memory starts as candidate
- findings-first classification into knowledge, issues, todos, ideas,
  research notes, and directions
- skilllets, prompt patterns, and workflows instead of one skill per session
- reusable memory through `search`, `ask`, and compact agent `context`

## High Priority Improvements

### Self-Hosted Demo

VibeWiki should manage its own design and development conversations. The project
should include a reviewed self-bootstrap example that demonstrates:

- importing or capturing a VibeWiki design session
- distilling typed findings and candidate units
- rendering `review_board.html`
- approving and merging selected memory
- answering questions with `vibewiki ask`
- generating an agent pack with `vibewiki context`

### General Distillation Quality

The current distiller is too heuristic and contains several Venus/VEMU-specific
rules in core code. That helped the killer demo, but it is not a clean
open-source boundary.

Needed improvements:

- separate generic distillation logic from domain rule packs
- make Venus/VEMU rules an example pack or plugin
- add product/research conversation extraction for decisions, assumptions,
  tradeoffs, open questions, and roadmap items
- add optional LLM distillation for better findings, skilllets, questions, and
  merge suggestions
- keep local heuristics as fallback

### Review Experience

`review-board` is useful but still read-only. The next useful step is to record
human decisions at item level:

- approve or reject a finding
- downgrade a candidate skilllet to knowledge
- merge a candidate skilllet into an existing skilllet
- mark a candidate as deferred
- edit title, tags, and summary before merge

## Medium Priority Improvements

### Retrieval And Reuse Quality

`search`, `ask`, and `context` are present, but retrieval is still v0.1.

Needed improvements:

- better section anchors and source citations
- stale embedding cache cleanup
- optional reranking
- more compact context budgets
- `wiki_search` and `wiki_read` style surfaces for agents
- `export --format llms-full`

### Merge And Versioning

Current merge is append-only, which is safe but can become noisy.

Needed improvements:

- skilllet versioning
- deprecation and supersession records
- conflict detection when updating existing skilllets
- changelog for merged memory units
- replay older sessions before promoting a skill update

### Public Release Readiness

The project needs stronger packaging and presentation before broad release:

- CI running tests
- PyPI or install instructions with a release tag
- short demo video or GIF
- privacy/security documentation
- `vibewiki doctor` for environment and API configuration
- clearer comparison with LLM-Wiki and Ctx2Skill

## Lower Priority Improvements

- optional vector database integration
- full web app
- multi-user permissions
- native IDE plugin

## Positioning

English:

> VibeWiki is a trusted memory compiler for AI conversations.

Chinese:

> VibeWiki 把人与 AI 协作中产生的经验、灵感、问题和技能，编译成可审查、可演化、可复用的项目记忆。
