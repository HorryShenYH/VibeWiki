from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .llm import chat_completion, llm_settings
from .project import ensure_workspace
from .retrieval import load_retrieval_config
from .text_utils import read_text_if_exists, utcish_timestamp


def translate_markdown(
    project: Path,
    *,
    markdown: str,
    target_language: str = "zh",
    source_language: str = "en",
    force: bool = False,
) -> str:
    root = project.resolve()
    ensure_workspace(root)
    cache_file = translation_cache_path(
        root,
        markdown=markdown,
        target_language=target_language,
        source_language=source_language,
    )
    if cache_file.exists() and not force:
        cached = read_text_if_exists(cache_file)
        if cached.strip():
            return cached

    config = load_retrieval_config(root)
    settings = llm_settings(
        base_url_env=config.llm_base_url_env,
        api_key_env=config.llm_api_key_env,
        model_env=config.llm_model_env,
    )
    if not settings:
        raise RuntimeError(
            "No LLM API is configured for Markdown translation. Set "
            "VIBEWIKI_LLM_BASE_URL, VIBEWIKI_LLM_API_KEY, and VIBEWIKI_LLM_MODEL."
        )

    system = (
        "You translate Markdown for a VibeWiki review display. "
        "Translate natural-language prose from English to Simplified Chinese. "
        "Preserve Markdown structure, heading levels, lists, tables, links, and code fences. "
        "Do not translate code, commands, file paths, environment variables, API names, "
        "identifiers, model names, metrics, or inline code. "
        "Do not add explanations, notes, or extra sections. Return only Markdown."
    )
    user = f"""Source language: {source_language}
Target language: {target_language}

Markdown:
{markdown}
"""
    translated = chat_completion(settings, system=system, user=user).strip() + "\n"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(translated, encoding="utf-8")
    metadata_path(cache_file).write_text(
        json.dumps(
            {
                "created_at": utcish_timestamp(),
                "source_language": source_language,
                "target_language": target_language,
                "model": settings.model,
                "source_sha256": _source_hash(
                    markdown,
                    target_language=target_language,
                    source_language=source_language,
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return translated


def cached_translation_markdown(
    project: Path,
    *,
    markdown: str,
    target_language: str = "zh",
    source_language: str = "en",
) -> str:
    path = translation_cache_path(
        project.resolve(),
        markdown=markdown,
        target_language=target_language,
        source_language=source_language,
    )
    return read_text_if_exists(path)


def translation_cache_path(
    project: Path,
    *,
    markdown: str,
    target_language: str = "zh",
    source_language: str = "en",
) -> Path:
    digest = _source_hash(
        markdown,
        target_language=target_language,
        source_language=source_language,
    )
    return project / ".vibewiki" / "cache" / "translations" / f"{digest}.md"


def metadata_path(cache_file: Path) -> Path:
    return cache_file.with_suffix(".json")


def _source_hash(markdown: str, *, target_language: str, source_language: str) -> str:
    payload = "\n".join(
        [
            "vibewiki-translation-v1",
            f"source={source_language}",
            f"target={target_language}",
            markdown,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
