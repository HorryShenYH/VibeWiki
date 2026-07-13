# Contributing

Thanks for considering a contribution to VibeWiki.

VibeWiki is early. The best contributions make the core loop easier to trust:

```text
capture/import -> distill -> review -> merge -> reuse
```

## Development Setup

```bash
python3 -m pip install -e .
```

Run the test suite:

```bash
PYTHONPATH=. python3.11 tests/test_cli_flow.py
```

If `python3.11` is not available, use any supported Python version from
`pyproject.toml`.

## Contribution Priorities

High-value areas:

- clearer onboarding and examples
- better generic distillation quality
- cleaner separation between core logic and domain-specific examples
- repository-understanding backends such as Repomix or Gitingest
- personal Wiki workflows
- review UI ergonomics
- privacy and safety improvements

Please keep changes focused. VibeWiki should stay local-first, auditable, and
portable.

## Design Expectations

- Generated memory should start as candidate memory.
- Human review should happen before permanent Wiki or skill changes.
- Raw evidence should be preserved when it is safe to do so.
- Uncertain claims should remain visibly uncertain.
- Domain-specific rules should live in examples or plugins when possible.
- Markdown output should stay readable without a special viewer.

## Pull Requests

A good pull request includes:

- a short explanation of the user-facing behavior
- tests for changed behavior
- documentation updates for new commands or concepts
- notes about privacy or migration impact when relevant

Before opening a PR, run:

```bash
PYTHONPATH=. python3.11 tests/test_cli_flow.py
```

## Project Style

The project currently avoids required runtime dependencies. Prefer standard
library code unless a dependency pays for itself clearly.

When adding integrations, prefer optional adapters over mandatory services.
