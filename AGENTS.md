# Project Agent Rules

## Before Editing

- Read relevant docs in `docs/wiki/`.
- Read relevant skilllets, prompt patterns, and workflows in `skills/`.
- Check known issues before repeating an old workaround.

## After Editing

- Run the verification commands required by the touched area.
- Keep uncertain claims out of permanent docs until a human approves them.
- Capture successful sessions with VibeWiki when useful knowledge was created.

<!-- vibewiki-agent:start -->
## VibeWiki Project Memory

This project uses VibeWiki as reviewed project memory.

- At the start of a task, call `vibewiki_brief`, then call `vibewiki_guard` for the task.
- Use `vibewiki_search` and `vibewiki_read` to retrieve only relevant approved memory.
- Candidate memory is unreviewed. Do not request or rely on it unless the user explicitly asks.
- If MCP tools are unavailable, run `vibewiki context --for "<task>" --scope approved --format json --max-items 5 --max-chars 500`.
- Capture useful new knowledge as a candidate; it must be reviewed before becoming trusted memory.
<!-- vibewiki-agent:end -->
