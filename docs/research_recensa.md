# Recensa Research Notes

## Project Reviewed

This note covers [S40911120/recensa](https://github.com/S40911120/recensa),
a local, self-hosted reader for Claude Code session transcripts. It does not
cover the unrelated document-review product with the same name.

The source review was performed on 2026-07-14 against the public repository.

## What Recensa Does

Claude Code already writes detailed JSONL transcripts under
`~/.claude/projects/`. Recensa turns those files into a usable history:

- a three-pane session list, transcript reader, and information panel
- full-text search across every indexed session
- readable tool calls, thinking blocks, diffs, and asynchronous call/result pairs
- subagent navigation and fork/compaction reconstruction
- token, model, tool, and file-change statistics
- pins, tags, custom titles, notes, and saved reading position
- live updates while a session is still running

It stays local, binds to loopback by default, makes no telemetry calls, and
treats transcript reading as a read-only operation.

## Strongest Design Ideas

### Source conversations are first-class data

Recensa does not begin by summarizing a session and discarding the trace. The
raw conversation remains available for inspection, search, and audit. Derived
metadata helps navigation but does not replace the source.

This matters to VibeWiki because a memory card is only trustworthy when a person
or agent can return to the conversation that produced it.

### Rebuildable index and durable curation are separate

Recensa stores its disposable search/index state in `viewer.db`. Pins, tags,
renames, notes, and settings live in a separate `flags.db` that an index
rebuild never clears.

The general principle is more important than SQLite:

```text
source transcript -> rebuildable index/derived views
                  -> durable human curation
```

A corrupt cache can be deleted and reconstructed without deleting user intent.

### Progressive disclosure keeps long sessions readable

Tool calls, thinking, system messages, and other noise are folded into landmarks.
Users can read the main conversation first and expand details only when needed.
The reader paginates and virtualizes large sessions instead of loading every
message into the page.

### Search returns a place, not only a result

A full-text hit links back to the exact message in its session. Search therefore
acts as navigation through evidence rather than a detached answer generator.
Its FTS5 trigram tokenizer also makes substring search useful for CJK text.

### Destructive actions have structural guards

Recensa refuses to delete a pinned session, a single subagent, or a member of a
fork/resume chain. It also validates recursive-delete paths stay inside the
configured transcript root.

VibeWiki already uses recoverable Trash and provenance-aware memory removal. A
pin guard adds a simple second layer against accidental deletion.

## VibeWiki Adaptation

VibeWiki should borrow the product model without copying Recensa's entire stack:

1. Keep imported conversations as inspectable source records.
2. Let users open the raw Markdown beside the conversation library.
3. Search conversation bodies, not only generated memory.
4. Keep local pins, tags, renames, and notes separate from generated Wiki data.
5. Prevent deletion of pinned conversations.
6. Show which Wiki blocks and files a conversation produced.
7. Keep derived search data disposable and rebuildable as the library grows.
8. Use progressive disclosure instead of exposing every extraction artifact.

The first implementation remains dependency-free:

- `vibewiki/conversations.py` owns source reading, full-text scanning,
  curation, provenance impact, and deletion guards.
- the control center loads one transcript at a time and renders its Markdown
- local curation lives in ignored
  `.vibewiki/private/conversation_flags.json`
- provenance-aware deletion still moves source and derived artifacts to Trash

A SQLite/FTS index is intentionally deferred until real libraries are large
enough to justify it. The source/derived/curation boundaries are established
now, so that index can be added later without changing the user model.

## What VibeWiki Should Not Copy

- Do not become Claude Code-only; VibeWiki accepts conversations from many agents.
- Do not make transcript viewing the final product; VibeWiki compiles reusable
  project memory and agent context.
- Do not require React, Node, Docker, or SQLite for the basic workflow.
- Do not expose every tool call when a compact source view is enough.
- Do not irreversibly delete a source conversation when recoverable Trash and
  provenance-aware rollback are available.

## Product Boundary

```text
Recensa:  agent transcript -> searchable, auditable session history
VibeWiki: heterogeneous conversations -> source-linked evolving memory -> human and agent reuse
```

They can complement each other. Recensa can remain the deep reader for raw
Claude Code traces, while VibeWiki imports selected conversations or summaries
and maintains the durable knowledge that should survive beyond one session.
