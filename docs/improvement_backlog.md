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
- continue product/research conversation extraction for decisions, assumptions,
  tradeoffs, open questions, and roadmap items. A first local heading/bullet
  heuristic exists, but precision, LLM support, and review controls remain open.
- add optional LLM distillation for better findings, skilllets, questions, and
  merge suggestions
- keep local heuristics as fallback

### Instincts And Skill Evolution

Research into ECC suggests VibeWiki should add a memory unit smaller than a
skilllet: an instinct or micro-rule. It should capture one trigger, one action,
scope, confidence, domain, and evidence. This would let VibeWiki preserve useful
lessons without over-promoting every observation into a skill.

Needed improvements:

- add `instincts/` as a candidate memory type
- add `scope: project|personal|global` and confidence metadata to candidates
- let the review UI approve, reject, defer, downgrade, or promote instincts
- add `vibewiki evolve --preview` to cluster reviewed instincts into proposed
  skilllets, workflows, or agent rules
- promote project instincts to personal/global only after repeated
  evidence-backed use across projects

### Review Experience

`review-board` supports a CLI-backed item-decision loop, and `review-ui` now
provides a first interactive review queue for SSH/browser workflows. Each
candidate can be reviewed at item level:

- approve or reject a finding
- downgrade a candidate skilllet to knowledge
- merge a candidate skilllet into an existing skilllet
- mark a candidate as deferred
- edit title, tags, and summary before merge

Implemented UI improvements:

- hide reviewed cards by default so approving an item shrinks the visible queue
- auto-dismiss success messages
- search and kind filters for large patches
- batch approve/reject/defer for selected items
- in-window Markdown editing for candidate files under `.vibewiki/patches/`
- Chinese/English UI label switching without showing both languages at once
- rendered Markdown previews for candidate cards

Remaining improvements: show merge previews/conflicts, add richer candidate
diffs, support safer edit history, and optionally require all items to be
explicitly reviewed before merge.

### Bilingual Wiki Mode

VibeWiki should support Chinese/English mixed work as a first-class mode. The
initial configuration now records:

- `language.mode: bilingual`
- `language.primary: zh`
- `language.secondary: en`

Remaining improvements:

- language-aware distillation prompts and LLM calls
- bilingual section aliases for retrieval
- optional `ask --language zh|en|bilingual`
- answer/display language controls outside the review UI
- better templates for public docs and project Wikis that keep machine-facing
  memory compact while allowing localized display

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
