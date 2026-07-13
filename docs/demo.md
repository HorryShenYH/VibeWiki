# Demo

The complete VibeWiki loop now lives in one browser control center:

```text
conversation -> memory draft -> review -> trusted memory -> reuse
```

It works with local files and does not require an LLM API.

## 1. Install And Open

From the repository root:

```bash
python3 -m pip install -e .
vibewiki ui
```

Open `http://127.0.0.1:8765/`.

For VS Code Remote SSH, forward port `8765` and open the same address in your
local browser.

## 2. Add A Conversation

Choose one entry in the `Add a conversation` panel:

- `Paste`: paste an exported AI conversation or Markdown notes
- `Share link`: import a supported shared conversation URL
- `Quick result`: record a goal, final outcome, commands, and verification

Keep `Generate memory draft now` enabled for the shortest path.

For a small domain-neutral example, use
[`examples/general/sample_session.md`](../examples/general/sample_session.md).

## 3. Review

The new session appears in `Work queue`. Open `Review` to inspect the strongest
candidate items first.

For each candidate you can:

- submit it
- discard it
- edit the Markdown
- ask a configured LLM to revise it
- generate a display-only translation preview

Approve the patch when the useful candidates are ready, then return to the
control center and merge it into trusted memory.

## 4. Reuse

Use `Ask your memory` for a human answer:

```text
How did we make API retries safe?
```

Use `Build AI context` for a compact JSON package:

```text
Change the HTTP client retry policy without reintroducing duplicate writes.
```

The first path helps a developer remember. The second gives a coding agent the
same project memory without another long prompt.

## CLI Equivalent

The UI is the default, but every core operation remains scriptable:

```bash
vibewiki import-markdown examples/general/sample_session.md --session-name demo
vibewiki distill
vibewiki review --approve
vibewiki merge
vibewiki ask "how did we make API retries safe?"
```
