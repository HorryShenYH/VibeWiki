# Recensa Research Notes

## Scope

Recensa is a hosted document-assurance product for finished DOCX and PDF files.
This review is based on its public product and methodology pages. I did not
find a public source repository during the review, so these notes describe the
published workflow rather than an implementation audit.

Primary references:

- [Methodology](https://recensa.ai/methodology)
- [Issue Ledger](https://recensa.ai/features/issue-ledger)
- [Proof Report](https://recensa.ai/features/proof-report)
- [FAQ](https://recensa.ai/faq)

## What Recensa Gets Right

### Generation and assurance are different jobs

Recensa does not treat one fluent model answer as proof. Independent reviewers
produce structured findings, and an arbiter reconciles them. The useful idea
for VibeWiki is the separation of roles, not the number of models.

### Human attention is organized as an issue ledger

Duplicates are collapsed, disagreement remains visible, and users disposition
one merged list. This is much cheaper to review than raw model transcripts or a
large set of nearly identical cards.

### Incomplete checks are labeled honestly

Recensa reports partial completion when providers, limits, or reviewer quorum
prevent a complete run. It does not turn missing coverage into a polished but
misleading success message.

### Proof is scoped correctly

Its Proof Report records what was reviewed and found. It is explicitly a
structured review artifact, not a guarantee that a document is correct.

### The original remains recoverable

Suggested fixes do not silently overwrite the input. The user keeps final
control and can inspect the source that produced each issue.

## VibeWiki Adaptation

VibeWiki should adopt the assurance discipline while keeping its local-first,
low-token character:

1. Run deterministic local checks after every distillation.
2. Link every candidate to its source conversation and hash the source and
   candidate snapshot.
3. Collapse review work into a compact exception ledger.
4. Ask a human only for reusable skills, memory conflicts, incomplete
   provenance, or suspicious over-distillation.
5. Auto-promote ordinary source-linked knowledge in `knowledge_only` mode.
6. Skip likely duplicate and generic candidates during merge while preserving
   the raw patch for audit.
7. Write a Proof Report after merge with the assurance coverage, decision
   method, output files, and hashes.
8. State `semantic_consistency: not_run` when no semantic reviewer was used.

The implementation lives in `vibewiki/assurance.py`, is exposed through
`vibewiki assure`, and feeds the existing Attention and review views.

## What VibeWiki Should Not Copy

- Do not run three paid models for every imported conversation.
- Do not add a second dashboard solely for assurance.
- Do not make model consensus equivalent to truth.
- Do not force people to disposition ordinary notes one by one.
- Do not hide missing coverage behind a single confidence score.

An optional independent semantic pass can be added later for high-impact
skills or unresolved conflicts. It should be targeted and budgeted, not the
default cost of remembering a conversation.
