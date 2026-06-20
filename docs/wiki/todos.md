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
- Continue item-level review ergonomics. The first CLI-backed
  approve/reject/defer/downgrade/merge/edit path is implemented; next steps are
  form-style review UI, batch decisions, conflict previews, and stricter
  all-items-reviewed gates.

## Medium Priority

- Improve retrieval citations with better section anchors and source snippets.
- Clean up stale embedding cache entries when source files change or disappear.
- Add optional reranking for `search`, `ask`, and `context`.
- Add `wiki_search` and `wiki_read` style machine-facing surfaces for agents.
- Add `export --format llms-full` for compact project context export.
- Add skilllet versioning, deprecation, supersession, conflict detection, and a
  changelog for merged memory units.
- Add CI, package/release workflow, privacy/security docs, and `vibewiki doctor`.

## Lower Priority

- Add optional vector database integration.
- Build a full web app after the CLI/review loop is solid.
- Add multi-user permissions for team-maintained project memory.
- Explore native IDE integration.
