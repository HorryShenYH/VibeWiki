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
- typed findings for knowledge, issues, todos, ideas, research notes, and directions
- composable skilllets, prompt patterns, and workflows
- skill registry for exact slug/alias reuse and reviewed merge suggestions
- local search, ask, and compact agent context packs
- quick project understanding with `vibewiki understand`
- optional OpenAI-compatible LLM and embedding APIs with local embedding cache

## v0.2: Bootstrap And Personal Memory

- explicit project vs personal Wiki positioning
- `vibewiki understand --output docs/wiki/project_brief.md` as the standard
  bootstrap step for a new repository
- project brief sections for first files to read, commands, docs, tests, and
  missing follow-ups
- personal VibeWiki workflow for cross-project prompts, instincts, research
  notes, and reusable skilllets
- import/capture flow that can target either a project Wiki or a personal Wiki
- promotion guidance for moving repeated project lessons into personal memory

## v0.3: GitHub Pull Request Workflow

- `/vibewiki distill` PR comment
- read PR diff and description
- comment candidate Knowledge Patch
- maintainer approval before docs update
- validate links, source references, unresolved questions, and evidence status

## v0.4: Skilllet Evolution System

- Skilllet patch format
- Skilllet versioning
- Skilllet deprecation
- repeated sessions improve existing skilllets by slug
- aliases and registry metadata for controlled cross-session merging
- generated agent rules
- reusable project-specific procedures composed from smaller units
- `When Not To Use`, probes, evidence, confidence, and environment requirements
- skilllet evolution log

## v0.5: Real-World Case Studies

- web application bug-fix memory
- release and infrastructure workflows
- data and research investigation notes
- reusable personal knowledge across projects
- shared project memory across multiple developers
- specialized engineering examples packaged without assumptions in the core
- evaluation of recall quality, review cost, and context-token savings

## v0.6: Advanced Ask And Retrieval

- richer local Markdown retrieval
- cited answers with source sections
- no vector database required by default
- optional Chroma/Qdrant integration later
- LLM-Wiki-style `wiki_search` and `wiki_read` surfaces
- Ctx2Skill-inspired cross-session replay before promoting skill updates

## v1.0: Public Release

- packaged CLI
- GitHub Action
- examples
- docs
- demo video
- several domain-independent case studies
