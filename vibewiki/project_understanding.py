from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .text_utils import read_text_if_exists


IGNORE_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    ".vibewiki",
    ".vibewiki/cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}
TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".py",
    ".rs",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
MANIFEST_NAMES = {
    "Cargo.toml",
    "Makefile",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
}
ENTRYPOINT_NAMES = {
    "app.py",
    "cli.py",
    "index.js",
    "main.go",
    "main.py",
    "main.rs",
    "server.js",
}


@dataclass(frozen=True)
class FileInfo:
    path: str
    suffix: str
    size: int
    lines: int


@dataclass(frozen=True)
class PythonSymbol:
    path: str
    kind: str
    name: str
    line: int


@dataclass(frozen=True)
class ProjectBrief:
    root: Path
    readme_summary: str
    files_scanned: int
    skipped_files: int
    total_lines: int
    extensions: list[tuple[str, int]]
    top_dirs: list[tuple[str, int]]
    manifests: list[str]
    docs: list[str]
    tests: list[str]
    entrypoints: list[str]
    scripts: list[str]
    python_symbols: list[PythonSymbol]
    internal_imports: list[tuple[str, int]]
    notable_files: list[str]
    followups: list[str]


def build_project_brief(
    target: Path,
    *,
    max_files: int = 400,
    max_depth: int = 5,
) -> ProjectBrief:
    root = target.expanduser().resolve()
    files, skipped = _collect_files(root, max_files=max_files, max_depth=max_depth)
    extensions = Counter(info.suffix or "[no extension]" for info in files)
    top_dirs = Counter(_top_dir(info.path) for info in files)
    manifests = _select_paths(files, lambda path: Path(path).name in MANIFEST_NAMES, limit=20)
    docs = _select_paths(files, lambda path: _is_doc_path(path), limit=20)
    tests = _select_paths(files, lambda path: _is_test_path(path), limit=24)
    entrypoints = sorted(set(_entrypoints(root, files)))
    scripts = _project_scripts(root)
    python_symbols = _python_symbols(root, files, limit=60)
    internal_imports = _internal_imports(root, files, limit=20)
    notable_files = _notable_files(files, manifests, entrypoints, docs, tests)
    followups = _followups(files, manifests, docs, tests, entrypoints)
    return ProjectBrief(
        root=root,
        readme_summary=_readme_summary(root),
        files_scanned=len(files),
        skipped_files=skipped,
        total_lines=sum(info.lines for info in files),
        extensions=extensions.most_common(12),
        top_dirs=top_dirs.most_common(12),
        manifests=manifests,
        docs=docs,
        tests=tests,
        entrypoints=entrypoints,
        scripts=scripts,
        python_symbols=python_symbols,
        internal_imports=internal_imports,
        notable_files=notable_files,
        followups=followups,
    )


def render_project_brief_markdown(brief: ProjectBrief) -> str:
    lines = [
        f"# Project Brief: {brief.root.name}",
        "",
        "## Snapshot",
        "",
        f"- Root: `{brief.root}`",
        f"- Files scanned: {brief.files_scanned}",
        f"- Skipped files: {brief.skipped_files}",
        f"- Estimated lines: {brief.total_lines}",
    ]
    if brief.readme_summary:
        lines.extend(["", "## README Signal", "", brief.readme_summary])
    lines.extend(
        [
            "",
            "## Shape",
            "",
            _pairs("File types", brief.extensions),
            "",
            _pairs("Top folders", brief.top_dirs),
            "",
            "## Orientation",
            "",
            _items("Manifests", brief.manifests),
            "",
            _items("Entrypoints", brief.entrypoints),
            "",
            _items("Project scripts", brief.scripts),
            "",
            _items("Docs", brief.docs),
            "",
            _items("Tests", brief.tests),
            "",
            "## Python Surface",
            "",
            _symbols(brief.python_symbols),
            "",
            _pairs("Internal imports", brief.internal_imports),
            "",
            "## First Files To Read",
            "",
            _items("", brief.notable_files),
            "",
            "## Suggested Follow-ups",
            "",
            _items("", brief.followups),
            "",
        ]
    )
    return "\n".join(lines)


def project_brief_to_json(brief: ProjectBrief) -> str:
    payload = {
        "root": str(brief.root),
        "readme_summary": brief.readme_summary,
        "files_scanned": brief.files_scanned,
        "skipped_files": brief.skipped_files,
        "total_lines": brief.total_lines,
        "extensions": brief.extensions,
        "top_dirs": brief.top_dirs,
        "manifests": brief.manifests,
        "docs": brief.docs,
        "tests": brief.tests,
        "entrypoints": brief.entrypoints,
        "scripts": brief.scripts,
        "python_symbols": [symbol.__dict__ for symbol in brief.python_symbols],
        "internal_imports": brief.internal_imports,
        "notable_files": brief.notable_files,
        "followups": brief.followups,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _collect_files(root: Path, *, max_files: int, max_depth: int) -> tuple[list[FileInfo], int]:
    files: list[FileInfo] = []
    skipped = 0
    for path in sorted(root.rglob("*")):
        if len(files) >= max_files:
            skipped += 1
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _ignored(relative) or len(relative.parts) > max_depth:
            skipped += 1
            continue
        if path.suffix and path.suffix.lower() not in TEXT_EXTENSIONS:
            skipped += 1
            continue
        try:
            size = path.stat().st_size
        except OSError:
            skipped += 1
            continue
        if size > 300_000:
            skipped += 1
            continue
        text = read_text_if_exists(path)
        if "\0" in text:
            skipped += 1
            continue
        files.append(
            FileInfo(
                path=relative.as_posix(),
                suffix=path.suffix.lower(),
                size=size,
                lines=len(text.splitlines()),
            )
        )
    return files, skipped


def _ignored(relative: Path) -> bool:
    parts = relative.parts
    for index in range(len(parts)):
        segment = "/".join(parts[: index + 1])
        if parts[index] in IGNORE_DIRS or segment in IGNORE_DIRS:
            return True
    return False


def _readme_summary(root: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "readme.md"):
        text = read_text_if_exists(root / name)
        if text.strip():
            return _first_paragraph(text, limit=700)
    return ""


def _first_paragraph(text: str, *, limit: int) -> str:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    for paragraph in paragraphs:
        compact = " ".join(line.strip() for line in paragraph.splitlines())
        if compact.startswith("#"):
            continue
        return compact[:limit].rstrip()
    return ""


def _select_paths(files: list[FileInfo], predicate: object, *, limit: int) -> list[str]:
    selected: list[str] = []
    for info in files:
        if callable(predicate) and predicate(info.path):
            selected.append(info.path)
        if len(selected) >= limit:
            break
    return selected


def _is_doc_path(path: str) -> bool:
    lower = path.lower()
    return lower.endswith(".md") and (
        lower.startswith("docs/")
        or lower.startswith("wiki/")
        or Path(lower).name in {"readme.md", "agents.md", "contributing.md"}
    )


def _is_test_path(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name.lower()
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")


def _entrypoints(root: Path, files: list[FileInfo]) -> list[str]:
    paths = [info.path for info in files]
    found = [path for path in paths if Path(path).name in ENTRYPOINT_NAMES]
    pyproject = read_text_if_exists(root / "pyproject.toml")
    for script in re.findall(r"^\s*[\w.-]+\s*=\s*\"([\w.]+):([\w_]+)\"", pyproject, re.MULTILINE):
        module = script[0].replace(".", "/") + ".py"
        if module in paths:
            found.append(module)
    package_json = _read_json(root / "package.json")
    if isinstance(package_json, dict):
        main = package_json.get("main")
        if isinstance(main, str) and main in paths:
            found.append(main)
    return found


def _project_scripts(root: Path) -> list[str]:
    scripts: list[str] = []
    pyproject = read_text_if_exists(root / "pyproject.toml")
    for name, target in re.findall(r"^\s*([\w.-]+)\s*=\s*\"([\w.]+:[\w_]+)\"", pyproject, re.MULTILINE):
        scripts.append(f"{name}: {target}")
    package_json = _read_json(root / "package.json")
    if isinstance(package_json, dict) and isinstance(package_json.get("scripts"), dict):
        for name, command in package_json["scripts"].items():
            scripts.append(f"npm {name}: {command}")
    makefile = read_text_if_exists(root / "Makefile")
    for target in re.findall(r"^([A-Za-z0-9_.-]+):(?!=)", makefile, re.MULTILINE):
        if not target.startswith("."):
            scripts.append(f"make {target}")
    return scripts[:24]


def _python_symbols(root: Path, files: list[FileInfo], *, limit: int) -> list[PythonSymbol]:
    symbols: list[PythonSymbol] = []
    for info in files:
        if info.suffix != ".py":
            continue
        text = read_text_if_exists(root / info.path)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                symbols.append(PythonSymbol(info.path, "class", node.name, node.lineno))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(PythonSymbol(info.path, "function", node.name, node.lineno))
            if len(symbols) >= limit:
                return symbols
    return symbols


def _internal_imports(root: Path, files: list[FileInfo], *, limit: int) -> list[tuple[str, int]]:
    module_roots = _module_roots(files)
    counts: Counter[str] = Counter()
    for info in files:
        if info.suffix != ".py":
            continue
        text = read_text_if_exists(root / info.path)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".", 1)[0]
                    if top in module_roots:
                        counts[top] += 1
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".", 1)[0]
                if top in module_roots:
                    counts[top] += 1
    return counts.most_common(limit)


def _module_roots(files: list[FileInfo]) -> set[str]:
    roots: set[str] = set()
    for info in files:
        path = Path(info.path)
        if info.suffix != ".py":
            continue
        if path.name == "__init__.py" and len(path.parts) >= 2:
            roots.add(path.parts[0])
        elif len(path.parts) == 1:
            roots.add(path.stem)
    return roots


def _notable_files(
    files: list[FileInfo],
    manifests: list[str],
    entrypoints: list[str],
    docs: list[str],
    tests: list[str],
) -> list[str]:
    candidates: list[str] = []
    candidates.extend(manifests[:5])
    candidates.extend(entrypoints[:8])
    candidates.extend(docs[:8])
    candidates.extend(tests[:6])
    candidates.extend(info.path for info in files if info.path in {"AGENTS.md", "docs/design.md"})
    return _dedupe(candidates)[:20]


def _followups(
    files: list[FileInfo],
    manifests: list[str],
    docs: list[str],
    tests: list[str],
    entrypoints: list[str],
) -> list[str]:
    followups: list[str] = []
    if not manifests:
        followups.append("Add or identify a manifest file so agents can see dependencies and commands quickly.")
    if not docs:
        followups.append("Add a short README or docs entry that explains the project purpose and main workflow.")
    if not tests:
        followups.append("Add or document the quickest verification command for future changes.")
    if not entrypoints:
        followups.append("Mark the main entrypoint in README/AGENTS so a new agent knows where execution begins.")
    if len(files) >= 400:
        followups.append("Increase --max-files or narrow --target for a deeper scan of this repository.")
    if not followups:
        followups.append("Use this brief as the first context pack before asking an AI agent to edit the project.")
    return followups


def _pairs(title: str, pairs: list[tuple[str, int]]) -> str:
    if not pairs:
        return f"### {title}\n\n- Not found."
    lines = [f"### {title}", ""]
    lines.extend(f"- `{name}`: {count}" for name, count in pairs)
    return "\n".join(lines)


def _items(title: str, items: list[str]) -> str:
    lines: list[str] = []
    if title:
        lines.extend([f"### {title}", ""])
    if not items:
        lines.append("- Not found.")
    else:
        lines.extend(f"- `{item}`" for item in items)
    return "\n".join(lines)


def _symbols(symbols: list[PythonSymbol]) -> str:
    if not symbols:
        return "- Not found."
    return "\n".join(
        f"- `{symbol.path}:{symbol.line}` {symbol.kind} `{symbol.name}`" for symbol in symbols
    )


def _top_dir(path: str) -> str:
    parts = Path(path).parts
    return parts[0] if len(parts) > 1 else "."


def _read_json(path: Path) -> object:
    text = read_text_if_exists(path)
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
