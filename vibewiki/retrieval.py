from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from .events import recorded_by_for_memory
from .llm import chat_completion, clean_chat_response, llm_settings
from .memory_cards import cards_payload, format_card_answer, search_memory_cards
from .project import ensure_workspace
from .text_utils import read_text_if_exists, slugify


DEFAULTS = {
    "retrieval.default_scope": "all",
    "retrieval.agent_scope": "approved",
    "retrieval.search_max_items": "10",
    "retrieval.search_snippet_chars": "500",
    "retrieval.context_max_items": "8",
    "retrieval.context_max_chars_per_item": "700",
    "retrieval.ask_max_items": "8",
    "retrieval.ask_context_chars": "8000",
    "retrieval.format": "yaml",
    "llm.base_url_env": "VIBEWIKI_LLM_BASE_URL",
    "llm.api_key_env": "VIBEWIKI_LLM_API_KEY",
    "llm.model_env": "VIBEWIKI_LLM_MODEL",
    "embedding.enabled": "auto",
    "embedding.cache_dir": ".vibewiki/cache/embeddings",
    "embedding.base_url_env": "VIBEWIKI_EMBEDDING_BASE_URL",
    "embedding.api_key_env": "VIBEWIKI_EMBEDDING_API_KEY",
    "embedding.model_env": "VIBEWIKI_EMBEDDING_MODEL",
}


@dataclass(frozen=True)
class RetrievalConfig:
    default_scope: str
    agent_scope: str
    search_max_items: int
    search_snippet_chars: int
    context_max_items: int
    context_max_chars_per_item: int
    ask_max_items: int
    ask_context_chars: int
    default_format: str
    llm_base_url_env: str
    llm_api_key_env: str
    llm_model_env: str
    embedding_enabled: str
    embedding_cache_dir: Path
    embedding_base_url_env: str
    embedding_api_key_env: str
    embedding_model_env: str


@dataclass(frozen=True)
class MemoryChunk:
    id: str
    status: str
    kind: str
    title: str
    section: str
    source: Path
    text: str


@dataclass(frozen=True)
class SearchResult:
    chunk: MemoryChunk
    score: float
    keyword_score: float
    embedding_score: float | None
    snippet: str


def load_retrieval_config(project: Path) -> RetrievalConfig:
    values = {**DEFAULTS, **_read_flat_config(project / ".vibewiki" / "config.yaml")}
    return RetrievalConfig(
        default_scope=_string(values, "retrieval.default_scope"),
        agent_scope=_string(values, "retrieval.agent_scope"),
        search_max_items=_integer(values, "retrieval.search_max_items"),
        search_snippet_chars=_integer(values, "retrieval.search_snippet_chars"),
        context_max_items=_integer(values, "retrieval.context_max_items"),
        context_max_chars_per_item=_integer(values, "retrieval.context_max_chars_per_item"),
        ask_max_items=_integer(values, "retrieval.ask_max_items"),
        ask_context_chars=_integer(values, "retrieval.ask_context_chars"),
        default_format=_string(values, "retrieval.format"),
        llm_base_url_env=_string(values, "llm.base_url_env"),
        llm_api_key_env=_string(values, "llm.api_key_env"),
        llm_model_env=_string(values, "llm.model_env"),
        embedding_enabled=_string(values, "embedding.enabled"),
        embedding_cache_dir=project / _string(values, "embedding.cache_dir"),
        embedding_base_url_env=_string(values, "embedding.base_url_env"),
        embedding_api_key_env=_string(values, "embedding.api_key_env"),
        embedding_model_env=_string(values, "embedding.model_env"),
    )


def search_memory(
    project: Path,
    query: str,
    *,
    scope: str | None = None,
    max_items: int | None = None,
    snippet_chars: int | None = None,
    use_embeddings: bool = True,
    ensure: bool = True,
) -> list[SearchResult]:
    root = project.resolve()
    if ensure:
        ensure_workspace(root)
    config = load_retrieval_config(root)
    selected_scope = scope or config.default_scope
    limit = max_items or config.search_max_items
    snippet_limit = snippet_chars or config.search_snippet_chars
    chunks = collect_memory_chunks(root, scope=selected_scope)
    if not chunks:
        return []

    keyword_scores = _bm25_scores(query, chunks)
    embedding_scores: dict[str, float] = {}
    if use_embeddings:
        try:
            embedding_scores = _embedding_scores(root, config, query, chunks)
        except (OSError, URLError, ValueError, TimeoutError):
            embedding_scores = {}

    important_tokens = _important_query_tokens(query)
    intent_tokens = _intent_tokens(query)
    results: list[SearchResult] = []
    for chunk in chunks:
        keyword_score = keyword_scores.get(chunk.id, 0.0)
        embedding_score = embedding_scores.get(chunk.id)
        score = keyword_score
        if embedding_score is not None:
            score += max(0.0, embedding_score) * 3.0
        score = _apply_important_token_weight(score, chunk, important_tokens)
        score = _apply_intent_weight(score, chunk, intent_tokens)
        if score <= 0:
            continue
        results.append(
            SearchResult(
                chunk=chunk,
                score=score,
                keyword_score=keyword_score,
                embedding_score=embedding_score,
                snippet=_snippet(chunk.text, query, snippet_limit),
            )
        )
    return sorted(results, key=lambda item: item.score, reverse=True)[:limit]


def collect_memory_chunks(project: Path, *, scope: str = "all") -> list[MemoryChunk]:
    root = project.resolve()
    files: list[tuple[Path, str]] = []
    if scope in {"approved", "all"}:
        files.extend((path, "approved") for path in _approved_files(root))
    if scope in {"candidate", "all"}:
        files.extend((path, "candidate") for path in _candidate_files(root))

    chunks: list[MemoryChunk] = []
    seen: set[str] = set()
    for path, status in files:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        text = read_text_if_exists(path)
        if not text.strip():
            continue
        relative = _relative(path, root)
        title = _first_heading(text) or path.stem.replace("-", " ").title()
        kind = _kind_for_path(path, root, text)
        chunks.extend(_chunk_markdown(relative, status, kind, title, path, text))
    return chunks


def format_search_results(results: list[SearchResult], *, verbose: bool = False) -> str:
    if not results:
        return "No matching VibeWiki memory found.\n"
    lines: list[str] = []
    for index, result in enumerate(results, 1):
        chunk = result.chunk
        lines.append(
            f"{index}. [{chunk.status}] {chunk.kind}: {chunk.title}"
            f" ({chunk.section or 'Document'})"
        )
        lines.append(f"   source: {chunk.source}")
        score_line = f"   score: {result.score:.3f} keyword={result.keyword_score:.3f}"
        if result.embedding_score is not None:
            score_line += f" embedding={result.embedding_score:.3f}"
        lines.append(score_line)
        lines.append(f"   snippet: {result.snippet}")
        if verbose:
            lines.append("   text:")
            lines.extend(f"     {line}" for line in result.chunk.text.splitlines())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_context_pack(
    project: Path,
    query: str,
    *,
    scope: str | None = None,
    max_items: int | None = None,
    max_chars_per_item: int | None = None,
    output_format: str = "yaml",
    use_embeddings: bool = True,
) -> str:
    root = project.resolve()
    config = load_retrieval_config(root)
    limit = max_items or config.context_max_items
    item_chars = max_chars_per_item or config.context_max_chars_per_item
    selected_scope = scope or config.agent_scope
    results = search_memory(
        root,
        query,
        scope=selected_scope,
        max_items=limit,
        snippet_chars=item_chars,
        use_embeddings=use_embeddings,
    )
    payload = {
        "query": query,
        "scope": selected_scope,
        "budget": {"max_items": limit, "max_chars_per_item": item_chars},
        "items": [_context_item(result, root, item_chars) for result in results],
    }
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return _to_yaml(payload)


def build_answer_draft(
    project: Path,
    query: str,
    *,
    scope: str | None = None,
    max_items: int | None = None,
    verbose: bool = False,
    use_embeddings: bool = True,
) -> tuple[str, list[SearchResult]]:
    root = project.resolve()
    config = load_retrieval_config(root)
    limit = max_items or config.ask_max_items
    snippet_chars = config.search_snippet_chars if not verbose else config.context_max_chars_per_item
    results = search_memory(
        root,
        query,
        scope=scope,
        max_items=limit,
        snippet_chars=snippet_chars,
        use_embeddings=use_embeddings,
    )
    if not results:
        return "No matching VibeWiki memory found.\n", results

    confidence, reason = _confidence_for_results(results)
    recorders = _recorders_for_results(root, results)
    top = results[0]
    lines = [
        f"结果：{_answer_snippet(top)}",
        f"可信度：{confidence}（{reason}）",
        f"记录人：{', '.join(recorders) if recorders else 'unknown'}",
        f"来源：{_relative(top.chunk.source, root)}",
    ]
    if any(result.chunk.status == "candidate" for result in results):
        lines.append("备注：无 LLM API，以上为检索草稿；含未审核 candidate。")
    else:
        lines.append("备注：无 LLM API，以上为检索草稿。")
    if verbose:
        lines.extend(["", "## Evidence", ""])
        for index, result in enumerate(results, 1):
            chunk = result.chunk
            lines.extend(
                [
                    f"{index}. [{chunk.status}] {chunk.kind}: {chunk.title}",
                    "   recorded_by: "
                    + recorded_by_for_memory(root, chunk.source, section=chunk.section),
                    f"   source: {_relative(chunk.source, root)}",
                    f"   section: {chunk.section or 'Document'}",
                    f"   snippet: {result.snippet}",
                    "",
                ]
            )
            lines.extend(["   text:", *[f"     {line}" for line in chunk.text.splitlines()], ""])
    return "\n".join(lines).rstrip() + "\n", results


def answer_question(
    project: Path,
    query: str,
    *,
    scope: str | None = None,
    max_items: int | None = None,
    verbose: bool = False,
    use_embeddings: bool = True,
) -> str:
    root = project.resolve()
    config = load_retrieval_config(root)
    settings = llm_settings(
        base_url_env=config.llm_base_url_env,
        api_key_env=config.llm_api_key_env,
        model_env=config.llm_model_env,
        project=root,
    )
    card_results = search_memory_cards(
        root,
        query,
        scope=scope or config.default_scope,
        max_items=max_items or config.ask_max_items,
    )
    if card_results:
        card_draft = format_card_answer(card_results, root=root, verbose=verbose)
        if not settings:
            return card_draft
        system = (
            "You answer questions using VibeWiki memory cards. "
            "A memory card is a compact project-memory fact with actor, claim, "
            "method, result, confidence, and source. Do not expose chain-of-thought. "
            "Prefer the card meaning over raw snippets. Be direct and short. "
            "Use this format exactly:\n"
            "结果：...\n"
            "可信度：高/中/低（short reason）\n"
            "记录人：...\n"
            "来源：1-3 short source paths\n"
            "If the cards are insufficient, say what is missing in one line."
        )
        user = f"""Question:
{query}

Memory cards:
{cards_payload(card_results, root=root, max_chars=config.ask_context_chars)}

Write only the compact answer. Do not include a separate evidence dump.
"""
        try:
            return clean_chat_response(chat_completion(settings, system=system, user=user)).rstrip() + "\n"
        except RuntimeError as exc:
            return card_draft + f"\nLLM answer failed, so the memory-card draft above was used.\nReason: {exc}\n"

    draft, results = build_answer_draft(
        root,
        query,
        scope=scope,
        max_items=max_items or config.ask_max_items,
        verbose=verbose,
        use_embeddings=use_embeddings,
    )
    if not results:
        return draft

    if not settings:
        return draft

    confidence, reason = _confidence_for_results(results)
    system = (
        "You answer questions using VibeWiki project memory. "
        "Do not reveal chain-of-thought or reasoning traces. "
        "Be direct and short. Default output must be at most 6 lines. "
        "Use this format exactly:\n"
        "结果：...\n"
        "可信度：高/中/低（short reason）\n"
        "记录人：...\n"
        "来源：1-3 short source paths\n"
        "If evidence is insufficient, say what is missing in one line."
    )
    user = f"""Question:
{query}

Confidence hint:
{confidence} - {reason}

Evidence:
{_llm_evidence(results, root, max_chars=config.ask_context_chars)}

Write only the compact answer. Do not add a separate evidence section unless the user explicitly asked for details.
"""
    try:
        return clean_chat_response(chat_completion(settings, system=system, user=user)).rstrip() + "\n"
    except RuntimeError as exc:
        return draft + f"\nLLM answer failed, so the retrieval draft above was used.\nReason: {exc}\n"


def _approved_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for base in [root / "docs" / "wiki", root / "skills"]:
        if base.exists():
            files.extend(path for path in base.rglob("*.md") if path.is_file())
    for path in [root / "AGENTS.md", root / ".vibewiki" / "skill_registry.yaml"]:
        if path.exists():
            files.append(path)
    return sorted(files)


def _llm_evidence(results: list[SearchResult], root: Path, *, max_chars: int) -> str:
    items: list[dict[str, object]] = []
    remaining = max_chars
    for result in results:
        if remaining <= 0:
            break
        chunk = result.chunk
        text = _truncate(chunk.text, min(remaining, 1200))
        remaining -= len(text)
        items.append(
            {
                "status": chunk.status,
                "type": chunk.kind,
                "title": chunk.title,
                "section": chunk.section,
                "source": _relative(chunk.source, root).as_posix(),
                "recorded_by": recorded_by_for_memory(
                    root,
                    chunk.source,
                    section=chunk.section,
                ),
                "snippet": text,
            }
        )
    return json.dumps(items, ensure_ascii=False, indent=2)


def _confidence_for_results(results: list[SearchResult]) -> tuple[str, str]:
    approved = sum(1 for result in results if result.chunk.status == "approved")
    candidate = sum(1 for result in results if result.chunk.status == "candidate")
    if approved >= 2 and candidate == 0:
        return "高", "多条已审核记忆命中"
    if approved:
        return "中", "有已审核记忆命中，但证据可能不完整"
    if candidate >= 3:
        return "中", "多条候选记忆命中，但尚未人工审核"
    return "低", "只命中少量或未审核记忆"


def _recorders_for_results(root: Path, results: list[SearchResult]) -> list[str]:
    recorders: list[str] = []
    for result in results:
        recorder = recorded_by_for_memory(
            root,
            result.chunk.source,
            section=result.chunk.section,
        )
        if recorder != "unknown" and recorder not in recorders:
            recorders.append(recorder)
    return recorders


def _candidate_files(root: Path) -> list[Path]:
    patch_root = root / ".vibewiki" / "patches"
    if not patch_root.exists():
        return []
    files: list[Path] = []
    for patch_dir in sorted(path for path in patch_root.iterdir() if path.is_dir()):
        for relative in [
            "findings",
            "skilllets",
            "prompt_patterns",
            "workflows",
        ]:
            directory = patch_dir / relative
            if directory.exists():
                files.extend(path for path in directory.rglob("*.md") if path.is_file())
        for name in ["questions.md", "merge_suggestions.md", "composable_units.md"]:
            path = patch_dir / name
            if path.exists():
                files.append(path)
    return sorted(files)


def _chunk_markdown(
    relative: Path,
    status: str,
    kind: str,
    title: str,
    source: Path,
    text: str,
    *,
    max_chars: int = 1800,
) -> list[MemoryChunk]:
    sections: list[tuple[str, list[str]]] = []
    current = "Document"
    lines: list[str] = []
    for line in text.splitlines():
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            if lines:
                sections.append((current, lines))
            current = heading.group(2).strip()
            lines = [line]
            continue
        lines.append(line)
    if lines:
        sections.append((current, lines))

    chunks: list[MemoryChunk] = []
    for section, section_lines in sections:
        body = "\n".join(section_lines).strip()
        if not body:
            continue
        if _metadata_only_chunk(body):
            continue
        for part_index, part in enumerate(_split_long_text(body, max_chars=max_chars), 1):
            suffix = "" if part_index == 1 else f"-{part_index}"
            chunk_id = f"{relative.as_posix()}#{slugify(section, 'document')}{suffix}"
            chunks.append(
                MemoryChunk(
                    id=chunk_id,
                    status=status,
                    kind=kind,
                    title=title,
                    section=section,
                    source=source,
                    text=part,
                )
            )
    return chunks


def _metadata_only_chunk(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return False
    content_lines = [line for line in lines if not line.startswith("#")]
    if not content_lines:
        return False
    metadata = 0
    for line in content_lines:
        if re.match(r"^[A-Za-z][A-Za-z _-]{1,32}:\s+.+$", line):
            metadata += 1
    return metadata == len(content_lines)


def _split_long_text(text: str, *, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if current and current_len + len(block) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        if len(block) > max_chars:
            for start in range(0, len(block), max_chars):
                chunks.append(block[start : start + max_chars])
            continue
        current.append(block)
        current_len += len(block) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text[:max_chars]]


def _bm25_scores(query: str, chunks: list[MemoryChunk]) -> dict[str, float]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return {}
    documents = [_tokens(chunk.text + " " + chunk.title + " " + chunk.section) for chunk in chunks]
    if not documents:
        return {}
    doc_freq: Counter[str] = Counter()
    for tokens in documents:
        for token in set(tokens):
            doc_freq[token] += 1
    avg_len = sum(len(tokens) for tokens in documents) / max(len(documents), 1)
    k1 = 1.5
    b = 0.75
    scores: dict[str, float] = {}
    for chunk, tokens in zip(chunks, documents):
        counts = Counter(tokens)
        score = 0.0
        doc_len = len(tokens) or 1
        for token in query_tokens:
            tf = counts[token]
            if not tf:
                continue
            df = doc_freq[token]
            idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1 - b + b * doc_len / max(avg_len, 1))
            score += idf * (tf * (k1 + 1)) / denom
        if score > 0:
            scores[chunk.id] = score
    return scores


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
        if value in {"the", "and", "for", "with", "how", "what"}:
            continue
        tokens.append(value)
    return tokens


def _apply_important_token_weight(
    score: float,
    chunk: MemoryChunk,
    important_tokens: list[str],
) -> float:
    if not important_tokens or score <= 0:
        return score
    haystack = " ".join(
        [
            chunk.title,
            chunk.section,
            chunk.text,
            chunk.source.as_posix(),
        ]
    ).lower()
    matches = sum(1 for token in important_tokens if token in haystack)
    if matches == 0:
        return score * 0.25
    return score + matches * 6.0


def _intent_tokens(query: str) -> list[str]:
    lowered = query.lower()
    intents: list[str] = []
    if "运行" in query or "怎么跑" in query or "怎么执行" in query or "run" in lowered:
        intents.append("run")
    if "matlab" in lowered:
        intents.append("matlab")
    return intents


def _apply_intent_weight(
    score: float,
    chunk: MemoryChunk,
    intent_tokens: list[str],
) -> float:
    if score <= 0 or not intent_tokens:
        return score
    haystack = " ".join(
        [
            chunk.kind,
            chunk.title,
            chunk.section,
            chunk.text,
            chunk.source.as_posix(),
        ]
    ).lower()
    if "run" in intent_tokens and "matlab" in intent_tokens:
        operational_markers = [
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
        matches = sum(1 for marker in operational_markers if marker in haystack)
        if matches:
            score += min(matches, 4) * 4.0
        if chunk.kind in {"workflow", "prompt_pattern", "skilllet"}:
            score += 2.0
    return score


def _embedding_scores(
    project: Path,
    config: RetrievalConfig,
    query: str,
    chunks: list[MemoryChunk],
) -> dict[str, float]:
    settings = _embedding_settings(config)
    if not settings:
        return {}
    base_url, api_key, model = settings
    cache = _EmbeddingCache(config.embedding_cache_dir, model)
    query_vector = _post_embeddings(base_url, api_key, model, [query])[0]
    missing: list[MemoryChunk] = []
    vectors: dict[str, list[float]] = {}
    for chunk in chunks:
        text_hash = _hash_text(chunk.text)
        cached = cache.get(text_hash)
        if cached is None:
            missing.append(chunk)
        else:
            vectors[chunk.id] = cached
    for batch in _batches(missing, 32):
        embedded = _post_embeddings(base_url, api_key, model, [chunk.text for chunk in batch])
        for chunk, vector in zip(batch, embedded):
            text_hash = _hash_text(chunk.text)
            cache.put(
                text_hash,
                {
                    "chunk_id": chunk.id,
                    "source": str(chunk.source),
                    "model": model,
                    "text_hash": text_hash,
                    "vector": vector,
                },
            )
            vectors[chunk.id] = vector
    cache.save()
    return {
        chunk_id: _cosine(query_vector, vector)
        for chunk_id, vector in vectors.items()
        if vector
    }


def _embedding_settings(config: RetrievalConfig) -> tuple[str, str, str] | None:
    enabled = config.embedding_enabled.lower()
    if enabled in {"false", "no", "0", "off"}:
        return None
    base_env = os.getenv(config.embedding_base_url_env, "").strip()
    key = os.getenv(config.embedding_api_key_env, "").strip()
    model = os.getenv(config.embedding_model_env, "text-embedding-3-small").strip()
    if enabled == "auto" and not base_env and not key:
        return None
    base_url = base_env or "https://api.openai.com/v1"
    if not model:
        return None
    return base_url, key, model


def _post_embeddings(
    base_url: str,
    api_key: str,
    model: str,
    inputs: list[str],
    *,
    timeout: int = 60,
) -> list[list[float]]:
    url = base_url.rstrip("/") + "/embeddings"
    body = json.dumps({"model": model, "input": inputs}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Embedding response did not include a data list.")
    vectors: list[list[float]] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
            raise ValueError("Embedding response item did not include an embedding list.")
        vectors.append([float(value) for value in item["embedding"]])
    return vectors


class _EmbeddingCache:
    def __init__(self, directory: Path, model: str) -> None:
        self.directory = directory
        self.model = model
        self.path = directory / "index.jsonl"
        self.entries: dict[str, dict[str, object]] = {}
        self.dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("model") != self.model:
                continue
            text_hash = str(entry.get("text_hash", ""))
            if text_hash:
                self.entries[text_hash] = entry

    def get(self, text_hash: str) -> list[float] | None:
        entry = self.entries.get(text_hash)
        if not entry:
            return None
        vector = entry.get("vector")
        if not isinstance(vector, list):
            return None
        return [float(value) for value in vector]

    def put(self, text_hash: str, entry: dict[str, object]) -> None:
        self.entries[text_hash] = entry
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(entry, ensure_ascii=False) for entry in self.entries.values()]
        self.path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _context_item(result: SearchResult, root: Path, max_chars: int) -> dict[str, object]:
    chunk = result.chunk
    return {
        "id": chunk.id,
        "status": chunk.status,
        "type": chunk.kind,
        "title": chunk.title,
        "section": chunk.section,
        "score": round(result.score, 4),
        "source": _relative(chunk.source, root).as_posix(),
        "recorded_by": recorded_by_for_memory(root, chunk.source, section=chunk.section),
        "text": _truncate(chunk.text, max_chars),
    }


def _answer_snippet(result: SearchResult) -> str:
    text = result.snippet.strip()
    text = re.sub(r"^#+\s*Evidence From Session\s*-?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^Evidence From Session\s*-\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+-\s+-\s+", "；", text)
    text = re.sub(r"\s+-\s+", "；", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 220:
        text = text[:217].rstrip() + "..."
    return text or result.chunk.title


def _snippet(text: str, query: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    query_tokens = _tokens(query)
    lowered = clean.lower()
    first_match = min(
        [lowered.find(token) for token in query_tokens if lowered.find(token) >= 0] or [0]
    )
    start = max(0, first_match - limit // 3)
    snippet = clean[start : start + limit].strip()
    if start > 0:
        snippet = "..." + snippet
    if start + limit < len(clean):
        snippet += "..."
    return snippet


def _truncate(text: str, limit: int) -> str:
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _read_flat_config(path: Path) -> dict[str, str]:
    text = read_text_if_exists(path)
    values: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if ":" not in stripped or stripped.startswith("- "):
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if value == "":
            stack.append((indent, key))
            continue
        prefix = ".".join(item for _, item in stack)
        full_key = f"{prefix}.{key}" if prefix else key
        values[full_key] = value
    return values


def _string(values: dict[str, str], key: str) -> str:
    return values.get(key, DEFAULTS[key])


def _integer(values: dict[str, str], key: str) -> int:
    try:
        return int(values.get(key, DEFAULTS[key]))
    except ValueError:
        return int(DEFAULTS[key])


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _kind_for_path(path: Path, root: Path, text: str) -> str:
    relative = _relative(path, root).as_posix()
    if "/findings/" in relative:
        if "__" in path.stem:
            return path.stem.split("__", 1)[0]
        field = _field(text, "Type")
        return field or "finding"
    if "/skilllets/" in relative:
        return "skilllet"
    if "/prompt_patterns/" in relative:
        return "prompt_pattern"
    if "/workflows/" in relative:
        return "workflow"
    if relative.startswith("docs/wiki/"):
        return "wiki"
    if relative == "AGENTS.md":
        return "agent_rule"
    if relative.endswith("skill_registry.yaml"):
        return "registry"
    if relative.endswith("questions.md"):
        return "question"
    if relative.endswith("merge_suggestions.md"):
        return "merge_suggestion"
    return "memory"


def _field(text: str, name: str) -> str:
    pattern = re.compile(rf"^{re.escape(name)}:\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return path


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _batches(items: list[MemoryChunk], size: int) -> list[list[MemoryChunk]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _to_yaml(value: object, indent: int = 0) -> str:
    lines = _yaml_lines(value, indent)
    return "\n".join(lines) + "\n"


def _yaml_lines(value: object, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_yaml_lines(child, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(child)}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}-")
                lines.extend(_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return lines
    return [f"{prefix}{_yaml_scalar(value)}"]


def _yaml_scalar(value: object) -> str:
    text = str(value)
    if "\n" in text:
        indented = "\n".join(f"    {line}" for line in text.splitlines())
        return "|\n" + indented
    if text == "" or re.search(r"[:#\[\]{}]|^\s|\s$", text):
        return json.dumps(text, ensure_ascii=False)
    return text
