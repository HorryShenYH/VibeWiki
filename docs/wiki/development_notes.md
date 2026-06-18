# Development Notes

Reviewed VibeWiki knowledge patches will be appended here.

## 2026-06-19 Self-Review Backlog

The project recorded its own improvement backlog as a dogfooding exercise.

Persistent reviewed notes were added to:

- `docs/improvement_backlog.md`
- `docs/wiki/knowledge.md`
- `docs/wiki/known_issues.md`
- `docs/wiki/todos.md`
- `docs/wiki/ideas.md`
- `docs/wiki/directions.md`

A candidate session patch was generated under `.vibewiki/patches/` for local
review. The patch is intentionally not treated as approved memory yet because it
also exposed a distillation quality gap for product-design conversations.

## 2026-06-19 Discussion Finding Extraction

VibeWiki's local distiller now has an initial path for product, research, and
daily discussion sessions. It can extract typed findings from Markdown headings,
pseudo-headings such as `High priority:`, bullet lists, and short section
summaries.

This improves the self-review dogfood case: the VibeWiki design backlog now
distills into candidate knowledge and todos instead of a single over-specific
session skilllet. Re-distilling a patch directory also clears stale generated
Markdown files from findings and composable-unit directories.

Verification:

- `python3 -m unittest discover -s tests` passed with 19 tests.
- The self-review session was re-distilled and `review_board.html` regenerated.
