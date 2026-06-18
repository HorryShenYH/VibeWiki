from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .review import latest_patch_dir
from .text_utils import read_text_if_exists


REQUIRED_SKILL_SECTIONS = [
    "Skill Name",
    "When To Use",
    "When Not To Use",
    "Environment Requirements",
    "Steps",
    "Probes",
    "Common Failures",
    "Verification",
    "Evidence",
    "Related Files",
    "Related Wiki Pages",
    "Evolution Log",
]

CONFIDENCE_VALUES = {"low", "medium", "high"}


@dataclass(frozen=True)
class ValidationFinding:
    severity: str
    code: str
    message: str


@dataclass(frozen=True)
class SkillValidationReport:
    path: Path
    findings: list[ValidationFinding]

    @property
    def errors(self) -> list[ValidationFinding]:
        return [item for item in self.findings if item.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationFinding]:
        return [item for item in self.findings if item.severity == "WARN"]

    def ok(self, strict: bool = False) -> bool:
        if self.errors:
            return False
        if strict and self.warnings:
            return False
        return True

    def render(self) -> str:
        lines = [f"Skill validation: {self.path}"]
        if not self.findings:
            lines.append("OK: no findings")
            return "\n".join(lines)
        for finding in self.findings:
            lines.append(f"{finding.severity}: {finding.code}: {finding.message}")
        return "\n".join(lines)


def parse_markdown_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _has_substantive_text(value: str) -> bool:
    clean = value.strip()
    if not clean:
        return False
    lowered = clean.lower()
    if lowered in {"not provided.", "not provided", "none", "[]"}:
        return False
    return True


def _has_todo(value: str) -> bool:
    return "todo" in value.lower()


def _has_bullet(value: str) -> bool:
    return any(line.strip().startswith("- ") for line in value.splitlines())


def _confidence(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.lower().startswith("confidence:"):
            return line.split(":", 1)[1].strip().lower()
    return ""


def _add(
    findings: list[ValidationFinding],
    severity: str,
    code: str,
    message: str,
) -> None:
    findings.append(ValidationFinding(severity=severity, code=code, message=message))


def validate_skill_text(markdown: str, path: Path | None = None) -> SkillValidationReport:
    target = path or Path("<memory>")
    sections = parse_markdown_sections(markdown)
    findings: list[ValidationFinding] = []

    for section in REQUIRED_SKILL_SECTIONS:
        if section not in sections:
            _add(findings, "ERROR", "missing-section", f"Missing `## {section}`.")
            continue
        if not _has_substantive_text(sections[section]):
            _add(findings, "WARN", "empty-section", f"`## {section}` has no substantive content.")

    confidence = _confidence(markdown)
    if not confidence:
        _add(findings, "WARN", "missing-confidence", "Missing `Confidence: low|medium|high`.")
    elif confidence not in CONFIDENCE_VALUES:
        _add(
            findings,
            "WARN",
            "invalid-confidence",
            "`Confidence:` should be one of low, medium, or high.",
        )
    elif confidence == "low":
        _add(findings, "WARN", "low-confidence", "Skill confidence is low.")

    for section in ["Steps", "Probes", "Verification", "Evidence"]:
        value = sections.get(section, "")
        if _has_todo(value):
            _add(findings, "WARN", "todo", f"`## {section}` still contains TODO content.")

    for section in ["When To Use", "When Not To Use", "Environment Requirements", "Steps", "Probes"]:
        value = sections.get(section, "")
        if _has_substantive_text(value) and not _has_bullet(value):
            _add(
                findings,
                "WARN",
                "missing-bullets",
                f"`## {section}` should contain explicit bullet items.",
            )

    related_files = sections.get("Related Files", "")
    if _has_substantive_text(related_files) and "Not provided" not in related_files:
        lines = [line.strip() for line in related_files.splitlines() if line.strip().startswith("- ")]
        if not lines:
            _add(findings, "WARN", "missing-related-files", "`## Related Files` should list files as bullets.")

    return SkillValidationReport(path=target, findings=findings)


def default_skill_path(project: Path) -> Path:
    patch_dir = latest_patch_dir(project)
    return patch_dir / "skill_patch.md"


def validate_skill_file(path: Path) -> SkillValidationReport:
    markdown = read_text_if_exists(path)
    if not markdown:
        return SkillValidationReport(
            path=path,
            findings=[
                ValidationFinding(
                    severity="ERROR",
                    code="missing-file",
                    message="Skill file does not exist or is empty.",
                )
            ],
        )
    return validate_skill_text(markdown, path=path)

