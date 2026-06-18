from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def is_git_repo(cwd: Path) -> bool:
    return run_git(["rev-parse", "--is-inside-work-tree"], cwd) == "true"


def current_branch(cwd: Path) -> str:
    return run_git(["branch", "--show-current"], cwd) or "unknown"


def git_diff(cwd: Path) -> str:
    return run_git(["diff", "--no-ext-diff"], cwd)


def git_status(cwd: Path) -> str:
    return run_git(["status", "--short"], cwd)


def recent_commit(cwd: Path) -> str:
    return run_git(["log", "-1", "--pretty=format:%H%n%s%n%an%n%aI"], cwd)


def changed_files(cwd: Path) -> list[str]:
    status = git_status(cwd)
    files: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            files.append(path)
    return files

