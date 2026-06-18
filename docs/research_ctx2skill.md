# Ctx2Skill Notes

This note records what VibeWiki should borrow from Ctx2Skill and nearby skill
evolution work.

## Sources Reviewed

- eluckydog/Ctx2Skill- faithful reproduction
  - https://github.com/eluckydog/Ctx2Skill-
- S1s-Z/Ctx2Skill official code
  - https://github.com/S1s-Z/Ctx2Skill
- From Context to Skills: Can Language Models Learn from Context Skillfully?
  - https://arxiv.org/abs/2604.27660
- Trace2Skill: Verifier-Guided Skill Evolution for Long-Context EDA Agents
  - https://arxiv.org/abs/2605.21810
- Anything2Skill: Compiling External Knowledge into Reusable Skills for Agents
  - https://arxiv.org/abs/2606.09316
- SkillsVote: Lifecycle Governance of Agent Skills from Collection,
  Recommendation to Evolution
  - https://arxiv.org/abs/2605.18401

The `eluckydog/Ctx2Skill-` repository is a small MIT-licensed faithful
reproduction with a clean modular layout:

```text
ctx2skill/
  config.py
  core.py
  agents.py
  replay.py
  utils.py
examples/run_ctx2skill.py
tests/test_ctx2skill.py
SKILL.md
```

The official `S1s-Z/Ctx2Skill` repository is research-prototype shaped: a main
`selfplay_loop.py`, prompt files, inference and evaluation scripts, and CL-Bench
reproduction instructions.

## What Ctx2Skill Adds

Ctx2Skill's important idea is not just "summarize context into a skill." It uses
self-play to evolve the skill:

```text
context
  -> Challenger creates probing tasks and rubrics
  -> Reasoner attempts them with the current skills
  -> Judge gives binary feedback
  -> Proposer/Generator turn failures into skill updates
  -> Cross-time Replay selects the most robust skill set
```

The interesting part for VibeWiki is the probe loop. A skill should not be
accepted only because it reads well. It should survive questions that test
whether the skill preserves the useful context.

## What The Reproduction Repo Adds

The `eluckydog/Ctx2Skill-` repo makes the paper easy to study because it splits
the loop into product-friendly pieces:

- `core.py`: orchestrates iterations and stores candidate Reasoner skills
- `agents.py`: defines `Task`, `Verdict`, Challenger, Reasoner, Judge,
  Proposer, and Generator
- `replay.py`: records hard/easy probes and selects the best skill by
  `rho_h * rho_e`
- `utils.py`: keeps prompt templates and OpenAI-compatible API calls
- `tests/test_ctx2skill.py`: tests parsing and replay logic without requiring
  live LLM calls

This is closer to the VibeWiki style than the official single-file research
prototype. We should borrow the modular shape, but keep VibeWiki's evidence and
human-review gates.

## Trace2Skill Is Especially Relevant

Trace2Skill is closer to our Venus/RTL use case. It treats the skill as an
evolvable policy for an EDA agent and mines execution traces for success and
failure lessons.

For VibeWiki, this suggests a future hardware-focused loop:

```text
VibeWiki Skill candidate
  -> run verifier / simulator / benchmark probe
  -> collect dense progress evidence
  -> propose skill mutation
  -> preserve only evidence-backed improvements
```

The "dense verifier feedback" idea is worth borrowing carefully. Hardware tasks
often have sparse pass/fail signals, but intermediate observations can reveal
whether the agent localized the right RTL, reached compile, generated the right
assembly, or compared the right dump.

VibeWiki should not hide this inside a black box. It should store the feedback as
evidence:

```yaml
probes:
  - name: dsl_build
    command: make -C /home/shenyihao/Project/MultiVemu/VEMU/dsl all
    result: pass
  - name: final_vstore_compare
    result: fail
    metrics:
      rmse: 21.59
      relative_rmse: 142.96%
```

## Anything2Skill Adds A Better Skill Contract

Anything2Skill's skill contract is useful for VibeWiki's `Skill Patch`. Instead
of only writing "Steps" and "Verification", a mature VibeWiki Skill should have:

- invocation conditions
- contraindications
- action moves
- workflow steps
- constraints
- output specification
- supporting evidence
- confidence
- version and lifecycle state

This fits our `VCMXMUL` example well. The Skill should say when to use the
explicit OFDM path, when not to use all-`cmxmul`, and what evidence supports that
rule.

## SkillsVote Adds Governance

SkillsVote highlights a practical danger: raw trajectories are noisy and
indiscriminate updates can pollute future context. VibeWiki already agrees with
this through human review, but SkillsVote suggests richer lifecycle governance:

- skill attribution: did a successful run use this skill, agent exploration, or
  environment luck?
- skill recommendation: expose only the relevant skills for the task
- evidence-gated updates: update skills only after reusable successful evidence
- environment requirements: track toolchain, repo, simulator, hardware config

## Concrete VibeWiki Changes

### 1. Add Probes To Skills

Extend Skill Patch with a `Probes` section:

```markdown
## Probes

- name: dsl_build
  command: make -C /path/to/VEMU/dsl all
  success: build passes and resource check passes
- name: emulator_run
  command: Debug/Emulator test.hex -w -j... -b...
  success: exit code 0
- name: numerical_compare
  command: compare baseline and candidate VSTORE dumps as signed int8
  success: relative RMSE below project threshold
```

### 2. Add Contraindications

Add a required `When Not To Use` section. This is the missing half of many agent
skills.

Example:

```markdown
## When Not To Use

- Do not replace OFDM/FFT explicit fixed-point complex multiply with all-cmxmul
  unless final-output error has been measured and accepted.
```

### 3. Add Skill Evolution Records

Each skill should keep a lightweight evolution log:

```yaml
skill_id: venus.fixed_point_cmxmul
version: 0.2
parent: 0.1
change_reason: final VSTORE RMSE showed all-cmxmul is unsafe
evidence:
  - .vibewiki/sessions/...
decision: keep explicit path as default
```

### 4. Add Cross-Session Replay

Borrow Ctx2Skill's Cross-time Replay, but adapt it to engineering memory:

```text
Before promoting a Skill update:
  replay it against old sessions/probes
  reject if it fixes the new case but breaks old approved guidance
```

For Venus, replay can be simple at first:

- rerun recorded validation commands if available
- re-check expected files and assembly markers
- re-run local validators on stored dumps when rerunning is expensive

### 5. Add Skill Quality Gates

Before a Skill Patch can be approved, check:

- has invocation conditions
- has contraindications
- has at least one verification command or probe
- cites evidence paths
- has no unsupported universal claims
- has environment requirements when commands depend on local setup

### 6. Add A Replay-Friendly Probe Model

Ctx2Skill's Cross-Time Replay records one hard failure and one easy success per
iteration, then chooses the candidate skill that handles both. VibeWiki can
adapt this with deterministic engineering probes:

```python
class Probe:
    name: str
    command: str
    expected: str
    kind: Literal["hard", "easy", "regression"]
```

For v0.1, probes can remain Markdown/YAML. Later, `vibewiki replay` can rerun or
re-score them before a Skill update is promoted.

### 7. Do Not Import The Whole Loop Yet

Do not embed Ctx2Skill's full multi-agent self-play loop into VibeWiki v0.1. It
is expensive, API-dependent, and autonomous by design, while VibeWiki's first
promise is trusted, reviewable project memory.

Use the Ctx2Skill shape this way instead:

```text
v0.1: generate skill contract + probes
v0.2: validate skill structure and evidence
v0.3: replay probes across sessions
v0.4+: optional self-play skill evolution
```

## Positioning Impact

Ctx2Skill reinforces VibeWiki's direction:

> VibeWiki is not just a Wiki generator. It is a governed skill compiler for AI
> coding sessions.

The short-term product shape should remain conservative:

```text
import session -> generate skill candidate -> validate structure -> human review
```

The medium-term research shape can become more ambitious:

```text
skill candidate -> probes -> failure analysis -> skill mutation -> replay -> review
```

That gives VibeWiki a clear bridge from practical open-source tool to publishable
research system.
