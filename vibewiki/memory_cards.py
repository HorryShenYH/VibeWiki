from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from pathlib import Path

from .events import read_events
from .project import ensure_workspace
from .text_utils import read_text_if_exists, slugify


@dataclass(frozen=True)
class MemoryCard:
    id: str
    status: str
    kind: str
    title: str
    subject: str
    actor: str
    claim: str
    method: tuple[str, ...]
    result: str
    confidence: str
    source: Path
    tags: tuple[str, ...]

    def to_dict(self, root: Path | None = None) -> dict[str, object]:
        source = _relative(self.source, root) if root else self.source
        return {
            "id": self.id,
            "status": self.status,
            "kind": self.kind,
            "title": self.title,
            "subject": self.subject,
            "actor": self.actor,
            "claim": self.claim,
            "method": list(self.method),
            "result": self.result,
            "confidence": self.confidence,
            "source": source.as_posix(),
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class MemoryCardResult:
    card: MemoryCard
    score: float


def collect_memory_cards(project: Path, *, scope: str = "all") -> list[MemoryCard]:
    root = project.resolve()
    ensure_workspace(root)
    cards: list[MemoryCard] = []
    for path, status in _memory_files(root, scope=scope):
        text = read_text_if_exists(path)
        if not text.strip():
            continue
        card = _card_from_text(root, path, status, text)
        if card.claim or card.result or card.method:
            cards.append(card)
    return cards


def search_memory_cards(
    project: Path,
    query: str,
    *,
    scope: str = "all",
    max_items: int = 8,
) -> list[MemoryCardResult]:
    cards = collect_memory_cards(project, scope=scope)
    if not cards:
        return []
    query_tokens = _tokens(query)
    important_tokens = _important_query_tokens(query)
    intents = _intent_tokens(query)
    results: list[MemoryCardResult] = []
    for card in cards:
        score = _score_card(card, query_tokens, important_tokens, intents)
        if score > 0:
            results.append(MemoryCardResult(card=card, score=score))
    return sorted(results, key=lambda item: item.score, reverse=True)[:max_items]


def format_memory_cards(
    results_or_cards: list[MemoryCardResult] | list[MemoryCard],
    *,
    root: Path,
    verbose: bool = False,
) -> str:
    if not results_or_cards:
        return "No matching VibeWiki memory cards found.\n"
    lines: list[str] = []
    for index, item in enumerate(results_or_cards, 1):
        if isinstance(item, MemoryCardResult):
            card = item.card
            score = f" score={item.score:.3f}"
        else:
            card = item
            score = ""
        lines.append(f"{index}. [{card.status}] {card.kind}: {card.subject}{score}")
        lines.append(f"   actor: {card.actor}")
        lines.append(f"   claim: {_compact(card.claim or card.result)}")
        if card.method:
            lines.append(f"   method: {'; '.join(card.method[:3])}")
        if card.result:
            lines.append(f"   result: {_compact(card.result)}")
        lines.append(f"   confidence: {card.confidence}")
        lines.append(f"   source: {_relative(card.source, root)}")
        if verbose and card.tags:
            lines.append(f"   tags: {', '.join(card.tags)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def cards_to_json(results_or_cards: list[MemoryCardResult] | list[MemoryCard], *, root: Path) -> str:
    payload: list[dict[str, object]] = []
    for item in results_or_cards:
        if isinstance(item, MemoryCardResult):
            data = item.card.to_dict(root)
            data["score"] = round(item.score, 4)
        else:
            data = item.to_dict(root)
        payload.append(data)
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def format_card_answer(results: list[MemoryCardResult], *, root: Path, verbose: bool = False) -> str:
    if not results:
        return ""
    cards = [result.card for result in results]
    actor = _first_known(card.actor for card in cards)
    confidence, reason = _confidence(cards)
    sources = _sources(cards, root)
    methods = _methods(cards)
    ssh = _first_containing(methods, ["ssh ", "@"])
    matlab = _first_containing(methods, ["matlab -batch", "run_vemu_gold"])
    result = _best_result(cards)
    claim = _first_known(card.claim for card in cards)

    if ssh or matlab:
        answer = f"用户 {actor} 曾经"
        if ssh:
            answer += f"通过 `{ssh}` 到远程 MATLAB/Windows worker"
        else:
            answer += "通过远程 MATLAB/Windows worker"
        if matlab:
            answer += f"，运行 `{matlab}`"
        if result:
            answer += f"，{_plain_result(result)}"
        elif claim:
            answer += f"，{_plain_result(claim)}"
        answer += "。"
    else:
        answer = f"用户 {actor} 曾经记录：{_plain_result(claim or result)}。"

    lines = [
        f"结果：{answer}",
        f"可信度：{confidence}（{reason}）",
        f"记录人：{actor}",
        f"来源：{'; '.join(sources)}",
    ]
    if any(card.status == "candidate" for card in cards):
        lines.append("备注：含未审核 candidate memory cards。")
    if verbose:
        lines.extend(["", "## Memory Cards", ""])
        lines.append(format_memory_cards(results, root=root, verbose=True).rstrip())
    return "\n".join(lines).rstrip() + "\n"


def cards_payload(results: list[MemoryCardResult], *, root: Path, max_chars: int = 6000) -> str:
    payload: list[dict[str, object]] = []
    remaining = max_chars
    for result in results:
        if remaining <= 0:
            break
        data = result.card.to_dict(root)
        data["score"] = round(result.score, 4)
        text = json.dumps(data, ensure_ascii=False)
        remaining -= len(text)
        payload.append(data)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _memory_files(root: Path, *, scope: str) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    if scope in {"approved", "all"}:
        for base in [root / "docs" / "wiki", root / "skills"]:
            if base.exists():
                files.extend((path, "approved") for path in base.rglob("*.md") if path.is_file())
        for path in [root / "AGENTS.md", root / ".vibewiki" / "skill_registry.yaml"]:
            if path.exists():
                files.append((path, "approved"))
    if scope in {"candidate", "all"}:
        patch_root = root / ".vibewiki" / "patches"
        if patch_root.exists():
            for patch_dir in sorted(path for path in patch_root.iterdir() if path.is_dir()):
                for relative in ["findings", "skilllets", "prompt_patterns", "workflows"]:
                    directory = patch_dir / relative
                    if directory.exists():
                        files.extend(
                            (path, "candidate")
                            for path in directory.rglob("*.md")
                            if path.name != "index.md"
                        )
                for name in ["composable_units.md", "merge_suggestions.md"]:
                    path = patch_dir / name
                    if path.exists():
                        files.append((path, "candidate"))
    seen: set[str] = set()
    unique: list[tuple[Path, str]] = []
    for path, status in sorted(files):
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append((path, status))
    return unique


def _card_from_text(root: Path, path: Path, status: str, text: str) -> MemoryCard:
    title = _first_heading(text) or path.stem.replace("-", " ").replace("_", " ").title()
    kind = _field(text, "Kind") or _field(text, "Type") or _kind_for_path(path, root)
    subject = _clean_subject(title)
    actor = _recorded_by_for_source(root, path)
    summary = _section(text, "Summary")
    purpose = _section(text, "Purpose")
    evidence = _section(text, "Evidence From Session")
    claim = (
        _clean_claim(summary)
        or _clean_claim(purpose)
        or _clean_claim(evidence)
        or _first_content_line(text)
    )
    method = tuple(_extract_methods(text))
    result = _extract_result(text)
    confidence = _field(text, "Confidence") or ("medium" if status == "candidate" else "high")
    tags = tuple(_tags(" ".join([title, kind, claim, result, " ".join(method), text])))
    relative = _relative(path, root).as_posix()
    return MemoryCard(
        id=slugify(relative, path.stem),
        status=status,
        kind=kind,
        title=title,
        subject=subject,
        actor=actor,
        claim=claim,
        method=method,
        result=result,
        confidence=confidence,
        source=path,
        tags=tags,
    )


def _extract_methods(text: str) -> list[str]:
    methods: list[str] = []
    patterns = [
        r"ssh\s+[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+",
        r"scp\s+[A-Za-z0-9_./:@~$%{}\"'\\ -]+",
        r"matlab\s+-batch\s+\"[^\"]+\"",
        r"TARGET_DAG=[A-Za-z0-9_./-]+",
        r"VENUSROW=\d+",
        r"VENUSLANE=\d+",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            _append_unique(methods, _compact(match, 120))
    for value in re.findall(r"`([^`]+)`", text):
        if _looks_like_method_code(value):
            _append_unique(methods, _compact(value, 120))
    return _prune_methods(methods)[:8]


def _looks_like_method_code(value: str) -> bool:
    clean = value.strip()
    lowered = clean.lower()
    if not clean or len(clean) > 180:
        return False
    command_prefixes = ("ssh ", "scp ", "matlab ", "make ", "python ", "python3 ", "codex exec")
    if lowered.startswith(command_prefixes):
        return True
    if lowered.startswith(("target_dag=", "venusrow=", "venuslane=")):
        return True
    return "run_vemu_gold" in lowered


def _prune_methods(methods: list[str]) -> list[str]:
    pruned: list[str] = []
    for method in methods:
        if _short_numeric_ssh_host(method) and any(
            other != method and other.startswith(method + ".") for other in methods
        ):
            continue
        _append_unique(pruned, method)
    return pruned


def _extract_result(text: str) -> str:
    candidates: list[str] = []
    for line in text.splitlines():
        clean = _clean_line(line)
        if not clean or clean.lower().startswith(("status:", "kind:", "type:", "session:")):
            continue
        if any(
            marker in clean
            for marker in [
                "修通",
                "跑完",
                "通过",
                "已可用",
                "拉回",
                "验证",
                "完全一致",
                "bit-exact",
                "max_abs_diff",
                "generated",
                "created",
            ]
        ):
            candidates.append(clean)
    return _compact(candidates[0], 260) if candidates else ""


def _score_card(
    card: MemoryCard,
    query_tokens: list[str],
    important_tokens: list[str],
    intents: list[str],
) -> float:
    haystack = _card_text(card).lower()
    tokens = _tokens(haystack)
    if not tokens:
        return 0.0
    score = 0.0
    counts = {token: tokens.count(token) for token in set(tokens)}
    for token in query_tokens:
        count = counts.get(token, 0)
        if count:
            score += 1.0 + math.log(1 + count)
    if important_tokens:
        important_matches = sum(1 for token in important_tokens if token in haystack)
        if important_matches == 0:
            score *= 0.25
        else:
            score += important_matches * 8.0
    if "run" in intents and "matlab" in intents:
        operational = [
            "matlab -batch",
            "ssh ",
            "scp ",
            "remote",
            "worker",
            "agent",
            "run_vemu_gold",
            "artifacts",
            "远程",
            "调用",
            "拉回",
        ]
        matches = sum(1 for marker in operational if marker in haystack)
        score += min(matches, 5) * 5.0
        if card.kind in {"workflow", "prompt_pattern", "skilllet"}:
            score += 3.0
        if _has_concrete_ssh(card):
            score += 14.0
        elif _has_placeholder_ssh(card):
            score -= 4.0
    return score


def _card_text(card: MemoryCard) -> str:
    return " ".join(
        [
            card.kind,
            card.title,
            card.subject,
            card.actor,
            card.claim,
            " ".join(card.method),
            card.result,
            card.source.as_posix(),
            " ".join(card.tags),
        ]
    )


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for value in re.findall(r"[A-Za-z0-9_+./-]{2,}|[\u4e00-\u9fff]{1,}", text.lower()):
        if re.search(r"[\u4e00-\u9fff]", value):
            tokens.append(value)
            if len(value) > 1:
                tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
            continue
        tokens.append(value)
    return tokens


def _important_query_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    for value in re.findall(r"[A-Za-z0-9_./-]{3,}", query.lower()):
        if value not in {"the", "and", "for", "with", "how", "what"}:
            tokens.append(value)
    return tokens


def _intent_tokens(query: str) -> list[str]:
    lowered = query.lower()
    intents: list[str] = []
    if "运行" in query or "怎么跑" in query or "怎么执行" in query or "run" in lowered:
        intents.append("run")
    if "matlab" in lowered:
        intents.append("matlab")
    return intents


def _confidence(cards: list[MemoryCard]) -> tuple[str, str]:
    approved = sum(1 for card in cards if card.status == "approved")
    candidate = sum(1 for card in cards if card.status == "candidate")
    if approved >= 2 and candidate == 0:
        return "高", "多张已审核 memory cards 命中"
    if approved:
        return "中", "有已审核 memory card 命中，但证据可能不完整"
    if candidate >= 2:
        return "中", "多张候选 memory cards 命中，但尚未人工审核"
    return "低", "只命中少量或未审核 memory card"


def _recorded_by_for_source(root: Path, source: Path) -> str:
    session_id = _session_id_for_source(root, source)
    if not session_id:
        return "unknown"
    for event in reversed(read_events(root)):
        if str(event.get("subject", "")) != session_id:
            continue
        if str(event.get("type", "")) in {"capture", "import-markdown", "import-url", "distill"}:
            actor = str(event.get("actor", "")).strip()
            if actor:
                return actor
    return "unknown"


def _session_id_for_source(root: Path, source: Path) -> str:
    relative = _relative(source, root)
    parts = relative.parts
    for marker in [(".vibewiki", "patches"), (".vibewiki", "sessions")]:
        try:
            index = parts.index(marker[0])
        except ValueError:
            continue
        if len(parts) > index + 2 and parts[index + 1] == marker[1]:
            return parts[index + 2]
    return ""


def _kind_for_path(path: Path, root: Path) -> str:
    relative = _relative(path, root).as_posix()
    if "/skilllets/" in relative:
        return "skilllet"
    if "/prompt_patterns/" in relative:
        return "prompt_pattern"
    if "/workflows/" in relative:
        return "workflow"
    if "/findings/" in relative:
        name = path.name.split("__", 1)[0]
        return name if name else "finding"
    if relative.startswith("docs/wiki/"):
        return "wiki"
    return "memory"


def _section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _field(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _clean_subject(title: str) -> str:
    return re.sub(
        r"^(Idea|Issue|Todo|Knowledge|Research Note|Skilllet|Workflow|Prompt Pattern):\s+",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()


def _clean_claim(text: str) -> str:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line and not line.lower().startswith("candidate ")]
    if not lines:
        single = _clean_line(text)
    else:
        single = lines[0]
    single = re.sub(r"^Candidate .*?:\s*", "", single)
    return _compact(single, 260)


def _first_content_line(text: str) -> str:
    for line in text.splitlines():
        clean = _clean_line(line)
        if not clean or clean.startswith("#"):
            continue
        if re.match(r"^[A-Za-z][A-Za-z _-]{1,32}:\s+.+$", clean):
            continue
        return _compact(clean, 260)
    return ""


def _plain_result(text: str) -> str:
    clean = _clean_line(text)
    clean = re.sub(r"^[-–]\s*", "", clean)
    clean = clean.rstrip("。.")
    return _compact(clean, 180)


def _clean_line(line: str) -> str:
    clean = line.strip()
    clean = clean.lstrip("> ").strip()
    clean = clean.lstrip("- ").strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean


def _tags(text: str) -> list[str]:
    lowered = text.lower()
    tags: list[str] = []
    for tag in [
        "matlab",
        "ssh",
        "windows",
        "vemu",
        "venus",
        "vcmxmul",
        "target_dag",
        "artifact",
        "gold",
        "codex",
        "replay",
    ]:
        if tag in lowered:
            tags.append(tag)
    return tags


def _methods(cards: list[MemoryCard]) -> list[str]:
    methods: list[str] = []
    for card in cards:
        for method in card.method:
            _append_unique(methods, method)
    return methods


def _best_result(cards: list[MemoryCard]) -> str:
    results = [card.result for card in cards if card.result]
    if not results:
        return ""
    preferred_markers = [
        "修通",
        "跑完",
        "artifacts",
        "拉回",
        "MATLAB Agent",
        "matlab -batch",
        "验证",
        "golden",
    ]
    for result in results:
        lowered = result.lower()
        if any(marker.lower() in lowered for marker in preferred_markers):
            return result
    for result in results:
        lowered = result.lower()
        if "ssh " not in lowered:
            return result
    return results[0]


def _sources(cards: list[MemoryCard], root: Path) -> list[str]:
    sources: list[str] = []
    for card in cards:
        _append_unique(sources, _relative(card.source, root).as_posix())
        if len(sources) >= 3:
            break
    return sources


def _first_known(values: object) -> str:
    for value in values:
        text = str(value).strip()
        if text and text != "unknown":
            return text
    return "unknown"


def _first_containing(values: list[str], markers: list[str]) -> str:
    exact = []
    for value in values:
        lowered = value.lower()
        if all(marker.lower() in lowered for marker in markers) and "<" not in value:
            exact.append(value)
    if exact:
        return max(exact, key=_method_specificity)
    for value in values:
        lowered = value.lower()
        if any(marker.lower() in lowered for marker in markers):
            return value
    return ""


def _has_concrete_ssh(card: MemoryCard) -> bool:
    return any(
        method.startswith("ssh ")
        and "@" in method
        and "<" not in method
        and not _short_numeric_ssh_host(method)
        for method in card.method
    )


def _has_placeholder_ssh(card: MemoryCard) -> bool:
    return any(method.startswith("ssh ") and "@" in method and "<" in method for method in card.method)


def _method_specificity(value: str) -> int:
    score = len(value)
    host = _ssh_host(value)
    if host:
        if "." in host or ":" in host:
            score += 100
        if _short_numeric_ssh_host(value):
            score -= 100
    return score


def _short_numeric_ssh_host(value: str) -> bool:
    host = _ssh_host(value)
    return bool(host and host.isdigit() and len(host) <= 3)


def _ssh_host(value: str) -> str:
    match = re.search(r"\bssh\s+\S+@([^\s`]+)", value)
    if not match:
        return ""
    return match.group(1).rstrip(".,;:")


def _append_unique(values: list[str], value: str) -> None:
    clean = value.strip()
    if clean and clean not in values:
        values.append(clean)


def _relative(path: Path, root: Path | None) -> Path:
    if root is None:
        return path
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path


def _compact(text: str, limit: int = 220) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."
