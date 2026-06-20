# ECC Notes

This note records what VibeWiki can learn from `affaan-m/ECC`.

## Sources Reviewed

- affaan-m/ECC repository
  - https://github.com/affaan-m/ECC
- The Shortform Guide
  - https://github.com/affaan-m/ECC/blob/main/the-shortform-guide.md
- The Longform Guide
  - https://github.com/affaan-m/ECC/blob/main/the-longform-guide.md
- Continuous Learning v2 skill
  - https://github.com/affaan-m/ECC/blob/main/skills/continuous-learning-v2/SKILL.md
- Deprecated Continuous Learning v1 skill
  - https://github.com/affaan-m/ECC/blob/main/skills/continuous-learning/SKILL.md

## What ECC Is

ECC positions itself as a cross-harness agent operating system rather than a
single memory tool. It packages skills, rules, hooks, agents, MCP configs,
commands, installers, and cross-harness adapters for Claude Code, Codex, Cursor,
OpenCode, Gemini, Zed, and related environments.

The useful lesson for VibeWiki is not the sheer number of bundled assets. The
useful lesson is the lifecycle model:

```text
session activity -> observed pattern -> small reusable behavior -> confidence
-> scoped application -> evolution into skills / commands / agents
```

That maps closely to VibeWiki's direction, but VibeWiki should keep a different
center of gravity:

```text
AI conversation -> evidence -> candidate memory -> human review -> approved memory -> reuse
```

ECC optimizes an agent harness. VibeWiki should optimize trustworthy memory
compilation.

## Strong Ideas To Borrow

### 1. Atomic Instincts Before Skills

ECC continuous-learning-v2 does not immediately turn every lesson into a full
skill. It introduces an "instinct": a small learned behavior with a trigger,
action, domain, confidence score, source, scope, and evidence.

This strongly matches VibeWiki's product direction. A conversation often
contains small reusable signals:

- "Use VSCode port forwarding for local review UI on SSH servers."
- "Keep internal candidate Markdown in English; localize only the review UI."
- "Do not promote one-off notes into skilllets."
- "For VEMU F5, check `TARGET_DAG`, `VENUSROW`, and `VENUSLANE` together."

These are not all full skills. VibeWiki should add a smaller unit below
skilllets, tentatively named `instincts` or `micro_rules`.

Suggested schema:

```yaml
id: ssh-review-ui-port-forwarding
status: candidate
scope: project
domain: workflow
confidence: 0.6
trigger: "when reviewing VibeWiki patches on a remote SSH server"
action: "run review-ui on 127.0.0.1 and use VSCode port forwarding"
evidence:
  - .vibewiki/sessions/...
promote_to:
  - skilllet
  - agent_rule
```

### 2. Confidence As Review Metadata, Not Blind Automation

ECC uses confidence scores such as tentative, moderate, strong, and near-certain.
VibeWiki should borrow confidence, but attach it to review decisions instead of
using it to silently control behavior.

Useful VibeWiki interpretation:

- `0.3`: candidate idea, visible in review, not recommended to agents by default
- `0.5`: usable note with evidence, shown in search
- `0.7`: strong reviewed memory, eligible for `context`
- `0.9`: stable rule or mature skill, safe for agent context packs

This lets VibeWiki keep trust while reducing noise.

### 3. Project-Scoped Memory With Global Promotion

ECC v2.1 separates project-scoped instincts from global instincts and promotes
only repeated high-confidence patterns across projects.

VibeWiki needs the same distinction:

- project memory: Venus/VEMU commands, local paths, simulator quirks, repo
  conventions
- personal memory: the user's preferred collaboration style and language mode
- global memory: generic safe practices such as "read before edit" or "cite
  evidence"

This directly addresses a VibeWiki risk: knowledge from one project can pollute
another project if it is promoted too broadly.

### 4. Hooks Are Useful, But Should Stay Opt-In

ECC emphasizes that hooks observe deterministically, while skills are
probabilistic. This is valuable for capture reliability, especially for session
end, pre-compact, or post-command state.

For VibeWiki, hooks should be optional and conservative:

- `vibewiki hook stop`: capture a session summary draft
- `vibewiki hook pre-compact`: save current working context
- `vibewiki hook post-command`: optionally record important commands and exit
  status

Do not enable always-on full observation by default. VibeWiki should protect
privacy and avoid slowing daily work.

### 5. Evolve Small Units Into Larger Units

ECC's `/evolve` idea is important: small instincts can cluster into skills,
commands, or agents later.

VibeWiki should do:

```text
candidate instincts
  -> review
  -> approved micro-memory
  -> repeated use / matching across sessions
  -> suggest skilllet / workflow / agent-rule promotion
```

This preserves the user's earlier product insight: one session should not equal
one skill.

### 6. Install And Doctor UX

ECC invests heavily in install profiles, component selection, doctor/repair, and
"do not stack install methods" warnings. VibeWiki will need the same discipline
when it grows beyond a local CLI.

Near-term VibeWiki equivalent:

- `vibewiki doctor`: check config, API keys, embedding cache, review server
  ports, Git status, and stale candidates
- `vibewiki status`: show sessions, patches, reviews, pending candidates, and
  memory counts
- `vibewiki profile`: minimal/local, team/project, agent-heavy

## What Not To Copy

- Do not become a huge harness bundle. VibeWiki should stay focused on memory.
- Do not auto-promote learned behavior directly into agent rules.
- Do not store raw observations globally by default.
- Do not require hooks, MCPs, plugins, or vector databases for the core loop.
- Do not make "more skills" the success metric; low-noise approved memory is the
  metric.

## Concrete VibeWiki Roadmap Changes

### A. Add `instincts/` As A Candidate Memory Type

Add a new candidate/approved memory class below skilllets:

```text
.vibewiki/patches/<session>/instincts/*.yaml
docs/wiki/instincts.md or .vibewiki/instincts/*.yaml
```

The review UI should support item-level decisions for instincts:

- approve as project instinct
- downgrade to knowledge
- promote to skilllet
- promote to agent rule
- reject/defer

### B. Add Confidence And Scope To Existing Candidates

Extend candidate metadata:

```yaml
scope: project | personal | global
confidence: 0.3 | 0.5 | 0.7 | 0.9
evidence_count: 1
promotion_hint: none | skilllet | workflow | agent_rule
```

### C. Add A Promotion Engine

Add a future `vibewiki evolve` command:

```bash
vibewiki evolve --preview
vibewiki evolve --promote repeated-instinct-id
```

It should cluster repeated reviewed instincts and propose a larger skilllet or
workflow, but still create a reviewable patch rather than mutating approved
memory directly.

### D. Add Optional Hook Capture

Add documented, opt-in hook scripts for Codex/Claude/Cursor where possible.
These hooks should create local candidate session files only; they should not
merge memory.

### E. Add Agent Export Adapters Later

ECC's cross-harness packaging suggests a VibeWiki export layer:

```bash
vibewiki export --target codex
vibewiki export --target claude
vibewiki export --target cursor
vibewiki export --target ecc
```

This would let VibeWiki remain the trusted memory compiler while other harnesses
consume the result.

## Product Positioning Impact

ECC shows there is demand for a complete agent harness layer. VibeWiki should
not compete head-on with that. The sharper positioning is:

> VibeWiki is the review-first memory compiler that can feed systems like ECC,
> LLM-Wiki, Codex skills, Claude skills, and project agent rules.

Chinese:

> ECC 更像 AI Agent 的操作系统；VibeWiki 应该做可信的记忆编译器，把会话里的经验、问题和灵感变成可审查、可演化、可被各种 Agent 复用的项目记忆。
