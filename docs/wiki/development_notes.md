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

## 2026-06-20 Simplified Review UI

Dogfooding the review UI showed that exposing every item-level decision field in
the browser made the product feel harder than reviewing Markdown by hand. The
browser surface should not mirror the CLI.

The review UI is now intentionally smaller:

- submit a candidate
- discard a candidate
- edit the candidate Markdown directly
- write a short revision instruction and let the configured LLM generate a new
  candidate draft

Advanced decisions such as downgrade, merge into an existing slug, edited title,
tags, and summary remain available through `vibewiki review-item`, but they are
not the default browser experience. This keeps human review focused on judgment,
while letting the LLM handle mechanical rewriting.

Verification:

- `python3 -m unittest discover -s tests` passed with 22 tests.

## 2026-06-20 Display-Only Markdown Translation

VibeWiki should be comfortable for Chinese-native reviewers without making the
project memory multilingual and noisy. The storage rule stays simple: candidate
and approved Markdown remain English by default. Translation belongs to the
review display layer.

The review UI now lets a reviewer generate a Chinese Markdown preview for each
candidate. The translated preview is:

- created with the configured OpenAI-compatible chat API
- cached under `.vibewiki/cache/translations/`
- rendered below the English preview
- never written back to the candidate Markdown unless the human explicitly
  edits the source Markdown

This keeps machine-facing memory compact while making human review less tiring.

Verification:

- `python3 -m unittest tests.test_cli_flow.VibeWikiFlowTest.test_review_ui_translation_uses_configured_chat_api_and_cache`
  passed.

## 2026-06-20 Review Plan Triage

Dogfooding a VibeWiki self-review conversation produced 29 raw candidates,
which was too much human review work for a single session. The product rule is
now explicit: a raw observation is audit evidence, not necessarily something a
human should review immediately.

VibeWiki now creates `review_plan.json` beside each patch. The plan is
machine-readable and currently rule-based:

- all raw candidates are preserved
- a small `review_now` batch is shown by default
- lower-priority candidates are hidden until requested
- broad or duplicate-looking candidates can be marked `suggested_discard`
- the review UI shows the plan reason on each card

The self-review patch now triages 29 raw items into 8 default review items, 18
lower-priority items, and 3 suggested-discard items. Future work should let a
configured LLM cluster related candidates, propose merges, and revise the plan
without automatically promoting memory.

Verification:

- `python3 -m unittest discover -s tests` passed with 23 tests.
- `python3 -m vibewiki.cli --project /home/shenyihao/MyProject/VibeWiki review-plan --help`
  passed.

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
