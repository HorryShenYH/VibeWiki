# Directions

Reviewed project or research directions that may shape future work.

## Trusted Memory Compiler

VibeWiki should be positioned as a trusted memory compiler for AI conversations,
not merely as a wiki generator or RAG search tool.

The long-term direction is:

- collect raw evidence from conversations and project activity
- distill it into typed candidate memory
- require human review before promotion
- evolve reusable units across related sessions
- expose approved memory through human answers and agent-readable context

## Different From LLM-Wiki

LLM-Wiki is most directly about making existing documentation searchable and
usable by LLMs. VibeWiki's sharper direction is upstream of that: it turns
messy AI collaboration itself into reviewed, evolving project memory. The two
could work together, but VibeWiki should keep its identity around evidence,
review, evolution, and reuse.

## Simple Shared Memory Principles

Source: VibeWiki design conversation, 2026-06-22.

VibeWiki should learn from RAG systems, LLM-facing documentation tools, and
automatic agent memory systems without copying their surface complexity. The
core product should stay small:

- evidence first: memory must point back to where it came from
- review first: durable team memory should be approved or clearly marked as
  candidate
- reuse first: the output should help humans ask better questions and help
  agents start with compact, relevant context

Avoid building a heavy workflow platform. Prefer small append-only records,
plain Markdown, compact JSON/YAML, and commands that can be used from a terminal,
CI job, or future UI.
