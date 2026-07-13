# General Example

This example shows VibeWiki's smallest useful loop with an ordinary software
bug. It has no domain-specific tools or project assumptions.

Import `sample_session.md`, distill it, review the candidate memory, and then
ask VibeWiki how API retries should behave.

```bash
vibewiki import-markdown examples/general/sample_session.md --session-name demo
vibewiki distill
vibewiki review-board
```
