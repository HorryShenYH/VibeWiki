from __future__ import annotations

import re
from pathlib import Path

from .models import PatchPaths
from .project import ensure_workspace
from .text_utils import fenced, markdown_bullets, read_text_if_exists, slugify


def latest_session_dir(project: Path) -> Path:
    sessions = sorted((project / ".vibewiki" / "sessions").glob("*"))
    sessions = [item for item in sessions if item.is_dir()]
    if not sessions:
        raise FileNotFoundError("No VibeWiki sessions found. Run `vibewiki capture` first.")
    return sessions[-1]


def parse_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "Preamble"
    sections[current] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def section_has_content(text: str) -> bool:
    clean = text.strip()
    return bool(clean and clean != "Not provided.")


def extract_bullets(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if value and value != "Not provided.":
                items.append(value)
    return items


def _parameter_hints(diff: str) -> list[str]:
    pattern = re.compile(
        r"\b(block|size|lat|latency|freq|frequency|row|lane|tile|buffer|timeout|threshold|config|power|benchmark|seed)\b",
        re.IGNORECASE,
    )
    hints: list[str] = []
    for line in diff.splitlines():
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            continue
        if pattern.search(line):
            hints.append(line[:180])
        if len(hints) >= 5:
            break
    return hints


def _questions(
    *,
    goal: str,
    outcome: str,
    commands: list[str],
    tests: str,
    benchmark: str,
    diff: str,
) -> list[str]:
    questions: list[str] = []
    if not section_has_content(goal):
        questions.append("What was the user-facing goal of this session?")
    if not section_has_content(outcome):
        questions.append("What was finally solved, and what remains unsolved?")
    if not commands:
        questions.append("Which exact commands should a future developer rerun?")
    if not section_has_content(tests):
        questions.append("Which test or verification command proved this change?")
    if section_has_content(benchmark):
        lowered = benchmark.lower()
        missing = [
            label
            for label in ["input", "version", "config", "result"]
            if label not in lowered
        ]
        if missing:
            questions.append(
                "The benchmark note may be incomplete. Please confirm: "
                + ", ".join(missing)
                + "."
            )
    parameter_hints = _parameter_hints(diff)
    if parameter_hints:
        questions.append(
            "The diff appears to change parameters or configuration. Why are these values correct?"
        )
    return questions


def _knowledge_patch(
    *,
    session_id: str,
    goal: str,
    outcome: str,
    commands: list[str],
    tests: str,
    benchmark: str,
    files: list[str],
    questions: list[str],
) -> str:
    evidence = []
    if commands:
        evidence.append("Key commands were recorded.")
    if section_has_content(tests):
        evidence.append("Verification output was recorded.")
    if section_has_content(benchmark):
        evidence.append("Benchmark output was recorded.")
    if files:
        evidence.append("Changed files were captured from git status.")

    status = "verified" if evidence else "uncertain"
    return f"""# Knowledge Patch

Status: candidate
Evidence Status: {status}
Session: {session_id}

## Session Goal

{goal or "Not provided."}

## What Was Solved

{outcome or "Not provided."}

## Important Facts

- This patch was generated from a captured VibeWiki session.
- The final outcome should be treated as project memory only after review.
- Unclear facts must remain candidate or uncertain until answered.

## Files Changed

{markdown_bullets(files)}

## Verified Evidence

{markdown_bullets(evidence)}

## Key Commands

{markdown_bullets(commands)}

## Tests / Verification

{tests or "Not provided."}

## Benchmark Results

{benchmark or "Not provided."}

## Suggested Wiki Updates

Append this reviewed session to `docs/wiki/development_notes.md`.

## Suggested Known Issues Updates

No known issue update is suggested automatically in v0.1.

## Open Questions Before Merge

{markdown_bullets(questions)}
"""


def _skill_patch(
    *,
    session_id: str,
    goal: str,
    commands: list[str],
    tests: str,
    files: list[str],
) -> str:
    skill_name = slugify(goal, fallback=session_id).replace("-", " ").title()
    steps = commands or ["TODO: Add the exact successful command sequence before approving."]
    probes = commands or ["TODO: Add at least one command probe before approving."]
    evidence = []
    if commands:
        evidence.append("Session recorded command evidence.")
    if section_has_content(tests):
        evidence.append("Session recorded verification evidence.")
    if files:
        evidence.append("Session recorded related changed files.")
    confidence = "medium" if evidence and section_has_content(tests) else "low"
    return f"""# Skill Patch

Status: candidate
Session: {session_id}
Confidence: {confidence}

## Skill Name

{skill_name}

## When To Use

Use this when a future task has the same goal or touches the same subsystem.

## When Not To Use

- Do not use this as permanent project guidance until the patch is approved.
- Do not apply this workflow outside its verified subsystem without checking the evidence.
- Do not preserve failed intermediate attempts as recommended steps.

## Environment Requirements

- The project checkout is available locally.
- Relevant environment variables and toolchain versions are known.
- Any uncertain setup details have been answered during review.

## Steps

{markdown_bullets(steps)}

## Probes

{markdown_bullets(probes)}

Expected result:

{tests or "TODO: Add expected probe result before approving this skill."}

## Common Failures

- Missing environment setup.
- Running commands from the wrong project root.
- Reusing a workaround after it has become deprecated.

## Verification

{tests or "TODO: Add verification evidence before approving this skill."}

## Evidence

{markdown_bullets(evidence)}

## Related Files

{markdown_bullets(files)}

## Related Wiki Pages

- `docs/wiki/development_notes.md`

## Evolution Log

- v0.1 candidate: generated from session `{session_id}`.
"""


def _agent_rule_patch(session_id: str, tests: str, questions: list[str]) -> str:
    verification_rule = (
        "Run the verification recorded in the related Skill before claiming success."
        if section_has_content(tests)
        else "Do not claim success until a concrete verification command is recorded."
    )
    uncertainty_rule = (
        "Keep this session's conclusions candidate-only until open questions are answered."
        if questions
        else "This session has no generated open questions, but review is still required."
    )
    return f"""# Agent Rule Patch

Status: candidate
Session: {session_id}

## New Rules

- Read the relevant VibeWiki Skill before repeating this workflow.
- {verification_rule}
- {uncertainty_rule}

## Updated Rules

- After successful AI-assisted debugging, run `vibewiki capture` so the final path can be reviewed.

## Do Not Do

- Do not store failed intermediate attempts as recommended procedures.
- Do not merge uncertain benchmark or parameter claims without human review.

## Verification Required

{tests or "A reviewer must add the verification command before this rule is considered approved."}
"""


def _questions_patch(session_id: str, questions: list[str], parameter_hints: list[str]) -> str:
    return f"""# Clarifying Questions

Session: {session_id}

## Questions

{markdown_bullets(questions)}

## Parameter Hints From Diff

{markdown_bullets(parameter_hints)}
"""


def distill_session(project: Path, session_dir: Path | None = None) -> PatchPaths:
    root = project.resolve()
    ensure_workspace(root)
    selected_session = session_dir or latest_session_dir(root)
    session_id = selected_session.name
    session_md = read_text_if_exists(selected_session / "session.md")
    diff = read_text_if_exists(selected_session / "diff.patch")
    sections = parse_sections(session_md)

    goal = sections.get("Goal", "")
    outcome = sections.get("Final Outcome", "")
    commands = extract_bullets(sections.get("Key Commands", ""))
    tests = sections.get("Tests / Verification", "")
    benchmark = sections.get("Benchmark Results", "")
    files = extract_bullets(sections.get("Changed Files", ""))
    questions = _questions(
        goal=goal,
        outcome=outcome,
        commands=commands,
        tests=tests,
        benchmark=benchmark,
        diff=diff,
    )
    parameter_hints = _parameter_hints(diff)

    patch_dir = root / ".vibewiki" / "patches" / session_id
    patch_dir.mkdir(parents=True, exist_ok=True)

    paths = PatchPaths(
        session_id=session_id,
        patch_dir=patch_dir,
        knowledge_patch=patch_dir / "knowledge_patch.md",
        skill_patch=patch_dir / "skill_patch.md",
        agent_rule_patch=patch_dir / "agent_rule_patch.md",
        questions=patch_dir / "questions.md",
    )
    paths.knowledge_patch.write_text(
        _knowledge_patch(
            session_id=session_id,
            goal=goal,
            outcome=outcome,
            commands=commands,
            tests=tests,
            benchmark=benchmark,
            files=files,
            questions=questions,
        ),
        encoding="utf-8",
    )
    paths.skill_patch.write_text(
        _skill_patch(
            session_id=session_id,
            goal=goal,
            commands=commands,
            tests=tests,
            files=files,
        ),
        encoding="utf-8",
    )
    paths.agent_rule_patch.write_text(
        _agent_rule_patch(session_id=session_id, tests=tests, questions=questions),
        encoding="utf-8",
    )
    paths.questions.write_text(
        _questions_patch(
            session_id=session_id,
            questions=questions,
            parameter_hints=parameter_hints,
        ),
        encoding="utf-8",
    )
    return paths
