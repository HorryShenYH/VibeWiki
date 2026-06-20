# Todos

Reviewed follow-up tasks, loose ends, and deferred work discovered during
sessions.

## High Priority

- Build a self-hosted demo that uses VibeWiki on VibeWiki itself: import a
  design session, distill candidate memory, open `review_board.html`, approve
  selected units, merge them, then answer questions with `ask` and generate
  compact agent context with `context`.
- Separate generic distillation logic from domain-specific Venus/VEMU rules.
- Continue improving product and research conversation extraction for decisions,
  assumptions, tradeoffs, todos, issues, ideas, open questions, and roadmap
  directions. The first local heading/bullet heuristic is implemented; next
  steps are better precision, LLM-assisted distillation, and review controls.
- Add optional LLM-assisted distillation while keeping deterministic local
  heuristics as the fallback.
- Add an ECC-inspired instinct layer below skilllets: atomic reviewed
  trigger/action memories with scope, confidence, evidence, and later promotion
  into skilllets, workflows, or agent rules.
- Add `vibewiki evolve --preview` to cluster repeated approved instincts into
  larger reusable units without mutating approved memory directly.
- Continue item-level review ergonomics. CLI-backed
  approve/reject/defer/downgrade/merge/edit and the clickable SSH-friendly
  `review-ui` are implemented. The UI is now simplified around submit, discard,
  direct Markdown edits, LLM revision from reviewer instructions, and
  `review_plan.json` pre-review triage that reduces the default queue while
  preserving raw candidates. It also supports cached Markdown translation
  previews through LibreTranslate-compatible APIs, local Argos Translate, or
  explicit LLM opt-in. Next steps are LLM-assisted clustering for the review
  plan, conflict previews, edit history for LLM revisions, richer diffs, and
  stricter visible-items-reviewed gates.

## Medium Priority

- Improve retrieval citations with better section anchors and source snippets.
- Clean up stale embedding cache entries when source files change or disappear.
- Add optional reranking for `search`, `ask`, and `context`.
- Add `wiki_search` and `wiki_read` style machine-facing surfaces for agents.
- Add `export --format llms-full` for compact project context export.
- Improve multilingual behavior beyond the review UI: bilingual section
  aliases, language-aware prompts, optional answer language control, and
  translation cache management/provider health checks.
- Add optional hook capture for session end, pre-compact, and important command
  results, but keep hooks opt-in and candidate-only.
- Add `vibewiki status` and expand `vibewiki doctor` planning around config,
  review servers, stale candidates, embedding cache, and Git state.
- Add skilllet versioning, deprecation, supersession, conflict detection, and a
  changelog for merged memory units.
- Add CI, package/release workflow, privacy/security docs, and `vibewiki doctor`.

## Lower Priority

- Add optional vector database integration.
- Build a full web app after the CLI/review loop is solid.
- Add multi-user permissions for team-maintained project memory.
- Explore native IDE integration.
