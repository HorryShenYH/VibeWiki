from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from .models import PatchPaths
from .project import ensure_workspace
from .text_utils import markdown_bullets, read_text_if_exists, slugify


@dataclass(frozen=True)
class ComposableUnitSpec:
    kind: str
    slug: str
    title: str
    purpose: str
    keywords: tuple[str, ...]
    min_matches: int
    when_to_use: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    steps: tuple[str, ...]
    verification: tuple[str, ...]
    related: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComposableUnit:
    kind: str
    slug: str
    title: str
    purpose: str
    when_to_use: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    steps: tuple[str, ...]
    verification: tuple[str, ...]
    evidence: tuple[str, ...]
    related: tuple[str, ...]


COMPOSABLE_UNIT_SPECS = [
    ComposableUnitSpec(
        kind="prompt_pattern",
        slug="remote-matlab-agent-task-package",
        title="Remote MATLAB Agent Task Package",
        purpose="Generate a bounded MATLAB Agent task package from DAG/application context instead of hand-writing one-off prompts.",
        keywords=("MATLAB Agent", "vemu_dag_summary.json", "run_vemu_gold.m", "config_schema.json"),
        min_matches=2,
        when_to_use=(
            "A server-side workflow needs a Windows MATLAB worker to produce reference artifacts.",
            "The prompt should be derived from DAG/application context rather than maintained by hand.",
        ),
        inputs=("DAG summary JSON", "optional project context snippets", "artifact contract"),
        outputs=("task markdown", "agent manifest", "MATLAB gold artifacts"),
        steps=(
            "Summarize the DAG and required artifact contract.",
            "Generate the agent prompt and manifest from current context.",
            "Run the remote MATLAB Agent and pull artifacts back to the server.",
        ),
        verification=(
            "Generated manifest is valid JSON.",
            "Returned artifacts match the required file list.",
        ),
        related=("remote-codex-worker-handoff", "matlab-gold-vemu-compare"),
    ),
    ComposableUnitSpec(
        kind="skilllet",
        slug="windows-ssh-key-for-admin-worker",
        title="Windows SSH Key For Admin Worker",
        purpose="Make non-interactive SSH work for a Windows OpenSSH user that belongs to Administrators.",
        keywords=("administrators_authorized_keys", "Match Group administrators", "sshpass", "authorized_keys"),
        min_matches=2,
        when_to_use=(
            "A Windows worker accepts password login but refuses the user's normal authorized_keys file.",
            "The remote user is in the Windows Administrators group.",
        ),
        inputs=("server public key", "Windows SSH user", "Windows host"),
        outputs=("passwordless SSH login",),
        steps=(
            "Verify password login once without writing the password into project files.",
            "Install the server public key into the administrators authorized_keys location.",
            "Fix Windows OpenSSH ACLs and verify key-only login.",
        ),
        verification=("`ssh <user>@<host>` succeeds without a password prompt.",),
        related=("remote-codex-worker-handoff",),
    ),
    ComposableUnitSpec(
        kind="skilllet",
        slug="remote-codex-worker-handoff",
        title="Remote Codex Worker Handoff",
        purpose="Run Codex inside a remote worker directory and return generated artifacts.",
        keywords=("codex exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "sandbox"),
        min_matches=2,
        when_to_use=(
            "A trusted worker directory is not a git checkout.",
            "The remote Codex process must create files or call local tools such as MATLAB.",
        ),
        inputs=("worker directory", "task prompt", "required artifacts"),
        outputs=("remote artifact files", "execution report"),
        steps=(
            "Use a remote wrapper script to avoid shell quoting problems.",
            "Pass the git-repo check option for non-repository worker directories.",
            "Choose sandbox settings that allow the trusted worker to write artifacts and call tools.",
        ),
        verification=("A minimal Codex prompt can write a file in the worker directory.",),
        related=("remote-matlab-agent-task-package",),
    ),
    ComposableUnitSpec(
        kind="skilllet",
        slug="matlab-nr-demod-reference",
        title="MATLAB NR Demod Reference",
        purpose="Use MATLAB's NR demodulator as the reference for VEMU demod replay cases.",
        keywords=("nrSymbolDemodulate", "nrSymbolModulate", "llr_scale", "QPSK"),
        min_matches=2,
        when_to_use=(
            "A VEMU NR demod task needs MATLAB official reference outputs.",
            "BAS inputs and VEMU softbit outputs must be compared against LLR gold data.",
        ),
        inputs=("BAS demod input", "modulation order", "noise variance or scale convention"),
        outputs=("MATLAB gold JSON", "quantized softbits", "comparison report"),
        steps=(
            "Parse BAS real/imag inputs and modulation metadata.",
            "Run MATLAB `nrSymbolDemodulate` using the chosen modulation.",
            "Quantize MATLAB LLRs into the VEMU softbit convention.",
        ),
        verification=("Existing QPSK BAS aligns after fitting or fixing the LLR scale.",),
        related=("bas-char-signed-int8", "matlab-gold-vemu-compare"),
    ),
    ComposableUnitSpec(
        kind="skilllet",
        slug="bas-char-signed-int8",
        title="BAS Char Signed Int8",
        purpose="Interpret BAS `char` payloads as signed int8 values when comparing VEMU softbits.",
        keywords=("255 -> -1", "signed int8", "char", "-fno-signed-char"),
        min_matches=2,
        when_to_use=(
            "BAS data stores negative int8 values as unsigned byte literals.",
            "A VEMU comparison shows negative expected values becoming large positive values.",
        ),
        inputs=("BAS char arrays", "VEMU output logs"),
        outputs=("signed int8 arrays",),
        steps=(
            "Read BAS char values as byte patterns.",
            "Convert values above 127 by subtracting 256 before comparison.",
            "Avoid relying on C `char` signedness in code built with `-fno-signed-char`.",
        ),
        verification=("A value such as 255 is interpreted as -1.",),
        related=("matlab-nr-demod-reference",),
    ),
    ComposableUnitSpec(
        kind="workflow",
        slug="materialize-vemu-replay-cases",
        title="Materialize VEMU Replay Cases",
        purpose="Turn generated BAS/gold cases into independent VEMU TARGET_DAG directories.",
        keywords=("TARGET_DAG", "generated_bas", "materialize", "DAGRet_demod.log"),
        min_matches=2,
        when_to_use=(
            "Generated BAS cases must be run independently through the VEMU F5-equivalent flow.",
            "A comparison script should map one TARGET_DAG to one MATLAB gold file.",
        ),
        inputs=("generated BAS files", "Task C implementation", "MATLAB reference JSON"),
        outputs=("independent task directories", "VEMU output logs", "comparison result"),
        steps=(
            "Materialize one task directory per modulation/configuration.",
            "Set `TARGET_DAG` to the selected generated case.",
            "Run the F5-equivalent VEMU build and emulator flow.",
        ),
        verification=("The comparison script reads `DAGRet_demod.log` and reports max diff statistics.",),
        related=("matlab-gold-vemu-compare", "vemu-f5-venus-128x16"),
    ),
    ComposableUnitSpec(
        kind="skilllet",
        slug="vemu-f5-venus-128x16",
        title="VEMU F5 Venus 128x16",
        purpose="Run VEMU replay cases with the Venus row/lane configuration known to pass this flow.",
        keywords=("VENUSROW=128", "VENUSLANE=16", "F5", "config.mk"),
        min_matches=2,
        when_to_use=(
            "A replay case should follow the VS Code F5-equivalent VEMU flow.",
            "Other row/lane settings trigger pass or resource failures.",
        ),
        inputs=("VEMU root", "`dsl/config.mk`", "TARGET_DAG"),
        outputs=("built emulator", "DAGRet logs"),
        steps=(
            "Set `VENUSROW=128` and `VENUSLANE=16`.",
            "Set `TARGET_DAG` to the replay case under test.",
            "Run the F5-equivalent build and emulator commands.",
        ),
        verification=("The emulator exits successfully and produces the expected `DAGRet` log.",),
        related=("materialize-vemu-replay-cases",),
    ),
    ComposableUnitSpec(
        kind="skilllet",
        slug="matlab-gold-vemu-compare",
        title="MATLAB Gold VEMU Compare",
        purpose="Compare VEMU logs against MATLAB gold with explicit tolerance and summary counters.",
        keywords=("max_abs_diff", "bad_abs_gt_1", "abs(diff)<=1", "MATLAB gold"),
        min_matches=2,
        when_to_use=(
            "A VEMU implementation must be proven against MATLAB-generated reference data.",
            "Quantized LLR output allows a tolerance such as absolute diff <= 1.",
        ),
        inputs=("VEMU output log", "MATLAB gold JSON", "tolerance"),
        outputs=("max_abs_diff", "bad_abs_gt_1", "pass/fail result"),
        steps=(
            "Load VEMU output and MATLAB gold with the same signedness convention.",
            "Compute per-element absolute differences.",
            "Report maximum difference and count above tolerance.",
        ),
        verification=("A passing case has `bad_abs_gt_1=0` for tolerance 1.",),
        related=("matlab-nr-demod-reference", "bas-char-signed-int8"),
    ),
    ComposableUnitSpec(
        kind="skilllet",
        slug="venus-vector-lut-mask-scatter",
        title="Venus Vector LUT Mask Scatter",
        purpose="Implement a LUT-style vector transform with high parallelism while keeping live vector registers bounded.",
        keywords=("vload", "vseq", "vbrdcst", "MASKREAD_ON", "vshuffle", "寄存器"),
        min_matches=3,
        when_to_use=(
            "A scalar replay implementation must be converted to Venus vector intrinsics.",
            "The input values are quantized enough for exact-level LUT/mask selection.",
        ),
        inputs=("input vector tiles", "quantized levels", "output scatter layout"),
        outputs=("vectorized softbit output",),
        steps=(
            "Process a fixed-size tile instead of keeping whole-output intermediates live.",
            "Generate masks with vector comparisons against quantized levels.",
            "Use masked broadcasts and shuffle/scatter operations to build the output.",
        ),
        verification=("Each target modulation passes the MATLAB gold comparison without register/resource growth.",),
        related=("matlab-gold-vemu-compare",),
    ),
]


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


def _clean_evidence_line(line: str) -> str:
    clean = line.strip().lstrip("> ").strip()
    if not clean or clean.startswith(("<details", "</details", "<summary")):
        return ""
    clean = clean.strip("`")
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > 220:
        clean = clean[:217] + "..."
    return clean


def _keyword_matches(text: str, keyword: str) -> bool:
    lowered_text = text.lower()
    lowered_keyword = keyword.lower()
    return lowered_keyword in lowered_text


def _evidence_lines(markdown: str, keywords: tuple[str, ...], limit: int = 8) -> tuple[str, ...]:
    found: list[str] = []
    for line in reversed(markdown.splitlines()):
        clean = _clean_evidence_line(line)
        if not clean:
            continue
        if any(_keyword_matches(clean, keyword) for keyword in keywords):
            if clean not in found:
                found.append(clean)
        if len(found) >= limit:
            break
    return tuple(reversed(found))


def _detect_composable_units(
    *,
    source_text: str,
    session_id: str,
    goal: str,
    commands: list[str],
    tests: str,
) -> list[ComposableUnit]:
    lowered = source_text.lower()
    units: list[ComposableUnit] = []
    for spec in COMPOSABLE_UNIT_SPECS:
        matches = [keyword for keyword in spec.keywords if keyword.lower() in lowered]
        if len(matches) < spec.min_matches:
            continue
        evidence = _evidence_lines(source_text, spec.keywords)
        verification = spec.verification
        if tests and not evidence:
            evidence = _evidence_lines(tests, spec.keywords)
        units.append(
            ComposableUnit(
                kind=spec.kind,
                slug=spec.slug,
                title=spec.title,
                purpose=spec.purpose,
                when_to_use=spec.when_to_use,
                inputs=spec.inputs,
                outputs=spec.outputs,
                steps=spec.steps,
                verification=verification,
                evidence=evidence,
                related=spec.related,
            )
        )

    if units:
        return units

    fallback_slug = slugify(goal, fallback=session_id)
    fallback_steps = tuple(commands[:5]) or ("Capture the exact reusable steps before approving this skilllet.",)
    return [
        ComposableUnit(
            kind="skilllet",
            slug=fallback_slug,
            title=fallback_slug.replace("-", " ").title(),
            purpose="Candidate reusable capability inferred from this session.",
            when_to_use=("A future task appears to repeat this session's goal.",),
            inputs=("Session context",),
            outputs=("Reusable local guidance",),
            steps=fallback_steps,
            verification=("A reviewer must add concrete verification before merging.",),
            evidence=_evidence_lines(source_text, tuple(commands[:3]), limit=4) if commands else (),
            related=(),
        )
    ]


def _unit_dir_name(kind: str) -> str:
    if kind == "prompt_pattern":
        return "prompt_patterns"
    if kind == "workflow":
        return "workflows"
    return "skilllets"


def _render_composable_unit(unit: ComposableUnit, session_id: str) -> str:
    label = {
        "prompt_pattern": "Prompt Pattern",
        "workflow": "Workflow",
        "skilllet": "Skilllet",
    }.get(unit.kind, "Skilllet")
    confidence = "medium" if unit.evidence else "low"
    return f"""# {label}: {unit.title}

Status: candidate
Kind: {unit.kind}
Session: {session_id}
Confidence: {confidence}

## Purpose

{unit.purpose}

## When To Use

{markdown_bullets(unit.when_to_use)}

## Inputs

{markdown_bullets(unit.inputs)}

## Outputs

{markdown_bullets(unit.outputs)}

## Steps

{markdown_bullets(unit.steps)}

## Verification

{markdown_bullets(unit.verification)}

## Evidence From Session

{markdown_bullets(unit.evidence)}

## Related Units

{markdown_bullets(unit.related)}

## Evolution Log

- Candidate extracted from session `{session_id}`.
"""


def _render_composable_index(session_id: str, units: list[ComposableUnit]) -> str:
    by_kind: dict[str, list[ComposableUnit]] = {"skilllet": [], "prompt_pattern": [], "workflow": []}
    for unit in units:
        by_kind.setdefault(unit.kind, []).append(unit)

    sections = [
        "# Composable Units",
        "",
        f"Session: {session_id}",
        "",
        "This patch treats the session as evidence for multiple small reusable units.",
    ]
    for kind, title in [
        ("skilllet", "Skilllets"),
        ("prompt_pattern", "Prompt Patterns"),
        ("workflow", "Workflows"),
    ]:
        items = [f"`{unit.slug}` - {unit.title}" for unit in by_kind.get(kind, [])]
        sections.extend(["", f"## {title}", "", markdown_bullets(items)])
    return "\n".join(sections) + "\n"


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

- Use this compatibility patch as a review entry point for the session.
- Prefer the generated skilllets, prompt patterns, and workflows for reusable guidance.

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


def _write_composable_units(patch_dir: Path, session_id: str, units: list[ComposableUnit]) -> None:
    for name in ["skilllets", "prompt_patterns", "workflows"]:
        directory = patch_dir / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.md").write_text(
            f"# {name.replace('_', ' ').title()}\n\nGenerated from session `{session_id}`.\n",
            encoding="utf-8",
        )

    for unit in units:
        directory = patch_dir / _unit_dir_name(unit.kind)
        path = directory / f"{unit.slug}.md"
        path.write_text(_render_composable_unit(unit, session_id), encoding="utf-8")

    (patch_dir / "composable_units.md").write_text(
        _render_composable_index(session_id, units),
        encoding="utf-8",
    )


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
    raw_session = read_text_if_exists(selected_session / "raw_session.md")
    source_text = "\n\n".join(
        item for item in [raw_session, session_md, tests, benchmark] if item.strip()
    )
    composable_units = _detect_composable_units(
        source_text=source_text,
        session_id=session_id,
        goal=goal,
        commands=commands,
        tests=tests,
    )
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
        skilllets_dir=patch_dir / "skilllets",
        prompt_patterns_dir=patch_dir / "prompt_patterns",
        workflows_dir=patch_dir / "workflows",
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
    _write_composable_units(patch_dir, session_id, composable_units)
    return paths
