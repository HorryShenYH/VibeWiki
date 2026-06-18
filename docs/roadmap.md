# Roadmap

## v0.1: Local Trustworthy Memory

- Python CLI
- local `.vibewiki` workspace
- capture git diff and session notes
- generate candidate patches
- validate Skill Patch quality gates
- human review record
- append-only merge
- import exported session Markdown
- composable skilllets, prompt patterns, and workflows
- skill registry for exact slug/alias reuse and reviewed merge suggestions

## v0.2: GitHub Pull Request Workflow

- `/vibewiki distill` PR comment
- read PR diff and description
- comment candidate Knowledge Patch
- maintainer approval before docs update
- validate links, source references, unresolved questions, and evidence status

## v0.3: Skilllet Evolution System

- Skilllet patch format
- Skilllet versioning
- Skilllet deprecation
- repeated sessions improve existing skilllets by slug
- aliases and registry metadata for controlled cross-session merging
- generated agent rules
- reusable project-specific procedures composed from smaller units
- `When Not To Use`, probes, evidence, confidence, and environment requirements
- skilllet evolution log

## v0.4: Venus Case Study

- VEMU simulation skilllets
- VEMU output mismatch skilllets
- gem5 performance simulation skilllets
- RTL alignment skilllets
- MATLAB gold comparison skilllets
- LDPC benchmark skilllets
- workflows that compose the smaller units into full verification runs
- verifier-style probes for DSL build, Emulator run, dump comparison, and generated assembly markers

## v0.5: Ask

- local Markdown retrieval
- cited answers
- no vector database required at first
- optional Chroma/Qdrant integration later
- LLM-Wiki-style `wiki_search` and `wiki_read` surfaces
- Ctx2Skill-inspired cross-session replay before promoting skill updates

## v1.0: Public Release

- packaged CLI
- GitHub Action
- examples
- docs
- demo video
- Venus case study
