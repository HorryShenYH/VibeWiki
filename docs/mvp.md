# MVP

## Goal

Build a local CLI that records one successful AI coding session and converts it
into reviewed project memory.

## User Story

A developer uses an AI coding agent to fix a bug, run a simulator, or validate a
benchmark. After the session, they run:

```bash
vibewiki capture
vibewiki distill
vibewiki validate-skill
vibewiki review --approve
vibewiki merge
```

The project receives an approved Wiki note, a reusable Skill draft, and updated
agent guidance.

## v0.1 Commands

- `vibewiki init`: create local memory structure
- `vibewiki capture`: save session notes, git diff, metadata
- `vibewiki distill`: create candidate patches
- `vibewiki validate-skill`: check required Skill sections, probes, evidence,
  confidence, and TODOs
- `vibewiki review`: approve or inspect patches
- `vibewiki merge`: append approved patches to project memory

## Success Criteria

- Works in a normal git project.
- Works without network access.
- Stores the original session evidence.
- Separates candidates from approved knowledge.
- Produces at least one question when context is missing.
- Flags incomplete Skill contracts before review.
- Avoids writing to final docs before review.

## First Real Case

Use a Venus session:

- VEMU simulation run
- gem5 simulation run
- RTL alignment
- MATLAB gold comparison
- LDPC benchmark validation

The demo should show that a future agent can read the generated Skill and avoid
repeating the same mistake.
