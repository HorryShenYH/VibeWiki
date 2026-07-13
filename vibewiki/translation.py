from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from .llm import chat_completion, llm_settings
from .project import ensure_workspace
from .retrieval import load_retrieval_config
from .text_utils import read_text_if_exists, utcish_timestamp


TRANSLATION_PROVIDER_ENV = "VIBEWIKI_TRANSLATION_PROVIDER"
TRANSLATION_BASE_URL_ENV = "VIBEWIKI_TRANSLATION_BASE_URL"
TRANSLATION_API_KEY_ENV = "VIBEWIKI_TRANSLATION_API_KEY"

LANGUAGE_LABELS = {
    "zh": "Chinese",
    "zh-Hans": "Simplified Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
}


@dataclass(frozen=True)
class TranslationProvider:
    name: str
    model: str = ""


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

    protected, placeholders = _protect_markdown(markdown)
    provider = _select_provider()
    translated = _translate_with_provider(
        root,
        protected,
        provider=provider,
        target_language=target_language,
        source_language=source_language,
    )
    translated = _restore_markdown(translated, placeholders).strip() + "\n"
    _write_translation_cache(
        cache_file,
        translated,
        markdown=markdown,
        provider=provider,
        target_language=target_language,
        source_language=source_language,
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


def language_label(language: str) -> str:
    return LANGUAGE_LABELS.get(language, language)


def _select_provider() -> TranslationProvider:
    requested = os.getenv(TRANSLATION_PROVIDER_ENV, "auto").strip().lower() or "auto"
    if requested == "auto":
        if os.getenv(TRANSLATION_BASE_URL_ENV, "").strip():
            return TranslationProvider("libretranslate", _translation_base_url())
        if importlib.util.find_spec("argostranslate") is not None:
            return TranslationProvider("argos", "argostranslate")
        raise RuntimeError(
            "No free translation provider is configured. Set "
            "VIBEWIKI_TRANSLATION_PROVIDER=libretranslate with "
            "VIBEWIKI_TRANSLATION_BASE_URL, install Argos Translate, or set "
            "VIBEWIKI_TRANSLATION_PROVIDER=llm if you explicitly want to spend LLM tokens."
        )
    if requested in {"libre", "libretranslate", "libre-translate"}:
        return TranslationProvider("libretranslate", _translation_base_url())
    if requested in {"argos", "argostranslate", "local"}:
        return TranslationProvider("argos", "argostranslate")
    if requested == "llm":
        return TranslationProvider("llm", "configured-chat-api")
    raise RuntimeError(
        "Unknown translation provider "
        f"`{requested}`. Expected auto, libretranslate, argos, or llm."
    )


def _translate_with_provider(
    project: Path,
    markdown: str,
    *,
    provider: TranslationProvider,
    target_language: str,
    source_language: str,
) -> str:
    if provider.name == "libretranslate":
        return _translate_with_libretranslate(
            markdown,
            target_language=target_language,
            source_language=source_language,
        )
    if provider.name == "argos":
        return _translate_with_argos(
            markdown,
            target_language=target_language,
            source_language=source_language,
        )
    if provider.name == "llm":
        return _translate_with_llm(
            project,
            markdown,
            target_language=target_language,
            source_language=source_language,
        )
    raise RuntimeError(f"Unsupported translation provider: {provider.name}")


def _translate_with_libretranslate(
    markdown: str,
    *,
    target_language: str,
    source_language: str,
) -> str:
    base_url = _translation_base_url()
    if not base_url:
        raise RuntimeError(
            "LibreTranslate requires VIBEWIKI_TRANSLATION_BASE_URL, "
            "for example http://127.0.0.1:5000."
        )
    return _post_libretranslate(
        base_url,
        markdown,
        target_language=target_language,
        source_language=source_language,
        api_key=os.getenv(TRANSLATION_API_KEY_ENV, "").strip(),
    )


def _post_libretranslate(
    base_url: str,
    markdown: str,
    *,
    target_language: str,
    source_language: str,
    api_key: str = "",
    timeout: int = 60,
) -> str:
    url = base_url.rstrip("/") + "/translate"
    payload = {
        "q": markdown,
        "source": source_language or "auto",
        "target": target_language,
        "format": "text",
    }
    if api_key:
        payload["api_key"] = api_key
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"LibreTranslate request failed: {exc}") from exc
    translated = data.get("translatedText")
    if not isinstance(translated, str):
        raise RuntimeError("LibreTranslate response did not include translatedText.")
    return translated


def _translate_with_argos(
    markdown: str,
    *,
    target_language: str,
    source_language: str,
) -> str:
    try:
        from argostranslate import translate  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Argos Translate is not installed. Install `argostranslate` and its "
            "language package, or use LibreTranslate."
        ) from exc
    try:
        return translate.translate(markdown, source_language, target_language)
    except Exception as exc:  # pragma: no cover - depends on optional package internals
        raise RuntimeError(
            "Argos Translate failed. Make sure the required language package is installed."
        ) from exc


def _translate_with_llm(
    project: Path,
    markdown: str,
    *,
    target_language: str,
    source_language: str,
) -> str:
    config = load_retrieval_config(project)
    settings = llm_settings(
        base_url_env=config.llm_base_url_env,
        api_key_env=config.llm_api_key_env,
        model_env=config.llm_model_env,
        project=project,
    )
    if not settings:
        raise RuntimeError(
            "No LLM API is configured. Open Model API in the VibeWiki control "
            "center, set the VIBEWIKI_LLM_* environment variables, or use a "
            "free translation provider instead."
        )
    system = (
        "You translate Markdown for a VibeWiki review display. "
        f"Translate natural-language prose from {source_language} to {target_language}. "
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
    return chat_completion(settings, system=system, user=user)


def _write_translation_cache(
    cache_file: Path,
    translated: str,
    *,
    markdown: str,
    provider: TranslationProvider,
    target_language: str,
    source_language: str,
) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(translated, encoding="utf-8")
    metadata_path(cache_file).write_text(
        json.dumps(
            {
                "created_at": utcish_timestamp(),
                "source_language": source_language,
                "target_language": target_language,
                "provider": provider.name,
                "model": provider.model,
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


def _translation_base_url() -> str:
    return os.getenv(TRANSLATION_BASE_URL_ENV, "").strip()


def _protect_markdown(markdown: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = f"VIBEWIKI_PLACEHOLDER_{len(placeholders)}"
        placeholders[token] = match.group(0)
        return token

    protected = re.sub(r"```.*?```", replace, markdown, flags=re.DOTALL)
    protected = re.sub(r"`[^`\n]+`", replace, protected)
    return protected, placeholders


def _restore_markdown(markdown: str, placeholders: dict[str, str]) -> str:
    restored = markdown
    for token, value in placeholders.items():
        restored = restored.replace(token, value)
    return restored


def _source_hash(markdown: str, *, target_language: str, source_language: str) -> str:
    payload = "\n".join(
        [
            "vibewiki-translation-v2",
            f"source={source_language}",
            f"target={target_language}",
            markdown,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
