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

## 2026-06-20 Item-Level Review Decisions

VibeWiki now records per-item review decisions with `vibewiki review-item`.
Supported decisions are:

- `approve`: merge the candidate item normally
- `reject`: skip the candidate during merge
- `defer`: keep the candidate local but skip it during merge
- `downgrade`: write a reusable-unit candidate into the Wiki instead of skills
- `merge`: append a reusable-unit candidate to an existing target slug
- `edit`: merge with reviewer-provided title, summary, tags, or note

The static `review_board.html` now shows item-level commands on each candidate
card and displays recorded decisions. Merge still requires patch-level approval,
but it now respects item-level decisions when deciding which findings and
reusable units become approved memory.

Verification:

- `python3 -m unittest discover -s tests` passed with 20 tests.

## 2026-06-20 Review UI Language And Markdown Preview

VibeWiki now separates storage language from review display language. Candidate
Markdown remains English project memory by default, while the review UI can
switch visible labels, placeholders, and action text between Chinese and
English. The page no longer displays bilingual labels such as `Approve / 批准`.

Candidate cards also render Markdown previews instead of raw source snippets, so
headings, lists, quotes, inline code, and fenced code blocks are easier to read
during review. The raw Markdown source is still available in the expandable
editor and is the only content written back to `.vibewiki/patches/`.

Verification:

- `python3 -m unittest discover -s tests` passed with 21 tests.

## 2026-06-20 Clickable Review UI And Bilingual Mode

The static `review_board.html` was not ergonomic enough for SSH-based
development because it still required copying `review-item` commands. VibeWiki
now provides `vibewiki review-ui`, a local-only HTTP review surface designed for
VSCode Remote-SSH port forwarding.

The review UI lets a human click item decisions directly:

- approve
- reject
- defer
- downgrade
- merge into an existing target
- edit title, summary, tags, or note

VibeWiki also records bilingual Wiki intent in `.vibewiki/config.yaml`:

```yaml
language:
  mode: bilingual
  primary: zh
  secondary: en
```

New project Wiki seed pages now use bilingual headings and short bilingual
descriptions. The policy is to keep the user's natural working language while
adding enough Chinese/English structure for humans and agents to navigate.

## 2026-06-20 Review UI Ergonomics

Dogfooding the first `review-ui` exposed two usability problems: approving an
item did not make the pending queue feel smaller, and editing candidates still
required leaving the browser window.

The review UI now treats item review as a working queue:

- reviewed cards are hidden by default, so approve/reject/defer immediately
  removes them from the visible pending list
- the success message fades away automatically after a short delay
- search and kind filters help narrow large candidate patches
- selected items can be approved, rejected, or deferred in bulk
- each candidate card has an in-window Markdown editor that writes back to the
  candidate file under `.vibewiki/patches/`

The saved Markdown remains candidate memory until a human records item-level or
patch-level approval and runs `merge`.

Verification:

- `python3 -m unittest discover -s tests` passed with 20 tests.
