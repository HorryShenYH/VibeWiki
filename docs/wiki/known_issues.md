# Known Issues

Use this page for verified recurring issues, deprecated workarounds, and
important caveats.

## Product-Design Conversations Are Under-Distilled

Status: verified during dogfooding on 2026-06-19.

When the self-review backlog was imported and distilled as a VibeWiki session,
the generated candidate patch captured only shallow generic facts. It did not
reliably extract the main product TODOs, known issues, directions, and tradeoffs
from the design conversation.

Impact: VibeWiki can record the curated backlog manually, but the automatic
distiller still needs better support for product, research, and daily discussion
sessions. This is separate from engineering debug sessions, where command and
evidence heuristics are more naturally structured.

Update on 2026-06-19: partially addressed. The local distiller now extracts
discussion bullets and section summaries into typed candidate findings, and it
avoids generating a broad session-sized skilllet for discussion-like sessions.
Remaining gaps: the rules are still heuristic, review lacks merge conflict
previews and stricter all-items-reviewed gates, and LLM-assisted distillation is
not implemented yet.
