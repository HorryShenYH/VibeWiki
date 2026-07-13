# Demo

This demo shows the smallest useful VibeWiki loop:

```text
bootstrap project memory -> import a session -> distill candidates -> review
```

It uses only local files and does not require an LLM API.

## 1. Install

From the repository root:

```bash
python3 -m pip install -e .
```

For local development without installation:

```bash
PYTHONPATH=. python3 -m vibewiki.cli --help
```

## 2. Bootstrap A Project Brief

Run the first-time setup wizard. Choose a project Wiki when prompted, then let
VibeWiki generate a first project brief:

```bash
vibewiki setup
vibewiki doctor
```

This produces a Markdown orientation page with:

- repository shape
- manifests
- entrypoints
- docs
- tests
- scripts
- first files to read
- suggested follow-ups

## 3. Import A Sample Coding Session

Use the small Venus example:

```bash
vibewiki import-markdown examples/venus/sample_session.md --session-name demo
```

The imported session is stored under `.vibewiki/sessions/`. VibeWiki keeps the
raw evidence and a normalized session record.

## 4. Distill Candidate Memory

```bash
vibewiki distill
```

This writes candidate patches under `.vibewiki/patches/`, including:

- knowledge patch
- typed findings
- skill patch
- candidate skilllets
- agent rule patch
- clarifying questions

Candidates are not merged into the main Wiki automatically.

## 5. Visualize

Generate the memory dashboard:

```bash
vibewiki dashboard
```

Open `.vibewiki/dashboard.html` to inspect memory status, review backlog, card
types, recent activity, and the next suggested command.

The dashboard defaults to English for demos and includes an in-page `EN / 中文`
switch. To pre-render a Chinese-first file:

```bash
vibewiki dashboard --lang zh
```

## 6. Review

Generate a local HTML board:

```bash
vibewiki doctor
vibewiki review-board
```

Open the generated `review_board.html` under the latest patch directory. The
board shows candidate memory, suggested commands, questions, and review actions.

For an SSH-friendly browser workflow:

```bash
vibewiki review-ui --port 8765
```

Then open `http://127.0.0.1:8765/` after forwarding the port.

## 7. Merge Approved Memory

For the demo, approve and merge the latest patch:

```bash
vibewiki review --approve
vibewiki merge
```

VibeWiki appends approved memory into `docs/wiki/`, `skills/`, and `AGENTS.md`.

## 8. Reuse Memory

Ask the local memory:

```bash
vibewiki ask "how do I run the VEMU comparison?"
vibewiki search "compare_outputs"
vibewiki context --for "run the simulator comparison" --format json
```

`ask` is for humans. `context` is for AI agents.

## What To Notice

The demo is intentionally small. The point is the lifecycle:

```text
evidence -> candidate memory -> review -> durable memory -> reuse
```

VibeWiki is most valuable after real AI coding sessions, where the evidence
contains commands, diffs, tests, caveats, and debugging decisions that would
otherwise disappear into chat history.
