# Security And Privacy

VibeWiki works with sensitive development traces:

- AI coding conversations
- git diffs
- shell commands
- test output
- benchmark output
- project notes
- generated Wiki and skill candidates

Treat these files as project memory, not public logs.

## Local-First Default

VibeWiki is local-first. The core workflow stores data under the project
workspace, mainly in:

```text
.vibewiki/
docs/wiki/
skills/
AGENTS.md
```

The local workflow does not require an LLM API. Optional LLM, embedding, and
translation providers are configured through environment variables.

## What Not To Record

Do not record:

- API keys or tokens
- private credentials
- customer data
- production secrets
- proprietary source snippets that should not enter the target repository
- private URLs or access details that should not be shared with teammates

Use capture fields such as `--things-not-to-record` to preserve this boundary.

## Git Hygiene

Before committing, review:

```text
.vibewiki/sessions/
.vibewiki/patches/
.vibewiki/reviews/
docs/wiki/
skills/
AGENTS.md
```

Some teams may want to commit only reviewed memory and keep raw sessions out of
Git. Others may want full auditability. Choose intentionally.

VibeWiki ignores `.vibewiki/cache/` by default because caches may contain
embedding or translation artifacts.

## Optional Providers

When using optional providers:

- do not commit API keys
- understand what text is sent to the provider
- prefer local or self-hosted providers for sensitive projects
- use review mode before merging generated content

Configured providers may receive snippets of project memory, candidate Markdown,
or retrieved context depending on the command.

## Reporting Security Issues

Please do not open a public issue for a vulnerability involving secret exposure,
remote content handling, or unsafe file writes.

Until a dedicated security contact exists, report privately to the project
maintainer.
