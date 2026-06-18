from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionPaths:
    session_id: str
    session_dir: Path
    session_md: Path
    diff_patch: Path
    metadata_yaml: Path


@dataclass(frozen=True)
class PatchPaths:
    session_id: str
    patch_dir: Path
    knowledge_patch: Path
    skill_patch: Path
    agent_rule_patch: Path
    questions: Path
    findings_index: Path
    findings_dir: Path
    merge_suggestions: Path
    skilllets_dir: Path
    prompt_patterns_dir: Path
    workflows_dir: Path


@dataclass(frozen=True)
class ReviewPaths:
    session_id: str
    review_file: Path
