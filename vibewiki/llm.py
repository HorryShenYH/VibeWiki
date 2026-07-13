from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_MODEL"
MINIMAX_BASE_URL_ENV = "MINIMAX_BASE_URL"
MINIMAX_API_KEY_ENV = "MINIMAX_API_KEY"
MINIMAX_MODEL_ENV = "MINIMAX_MODEL"
MINIMAX_OPENAI_BASE_URL = "https://api.minimaxi.com/v1"
LOCAL_LLM_SETTINGS = Path(".vibewiki/private/llm.json")
PROVIDER_DEFAULTS = {
    "minimax": (MINIMAX_OPENAI_BASE_URL, "MiniMax-M2.7"),
    "openai": ("https://api.openai.com/v1", "gpt-4.1-mini"),
    "compatible": ("", ""),
}


class LLMNotConfigured(RuntimeError):
    """Raised when an optional LLM distiller is requested but unavailable."""


def distill_with_llm(*_: object, **__: object) -> None:
    raise LLMNotConfigured(
        "LLM distillation is not wired in v0.1 yet. Use the local distiller."
    )


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str
    provider: str = "compatible"
    source: str = "environment"


def llm_settings(
    *,
    base_url_env: str,
    api_key_env: str,
    model_env: str,
    project: Path | None = None,
) -> LLMSettings | None:
    environment = _environment_llm_settings(
        base_url_env=base_url_env,
        api_key_env=api_key_env,
        model_env=model_env,
    )
    if environment:
        return environment
    if project is not None:
        return read_local_llm_settings(project)
    return None


def _environment_llm_settings(
    *,
    base_url_env: str,
    api_key_env: str,
    model_env: str,
) -> LLMSettings | None:
    base_url = _env(base_url_env)
    api_key = _env(api_key_env)
    model = _env(model_env)
    using_minimax_alias = False

    if not base_url:
        base_url = _env(OPENAI_BASE_URL_ENV)
        using_minimax_alias = _looks_like_minimax(base_url)
    if not api_key:
        api_key = _env(OPENAI_API_KEY_ENV)
    if not model:
        model = _env(OPENAI_MODEL_ENV)

    if not api_key and _env(MINIMAX_API_KEY_ENV):
        api_key = _env(MINIMAX_API_KEY_ENV)
        using_minimax_alias = True
        if not base_url:
            base_url = _env(MINIMAX_BASE_URL_ENV) or MINIMAX_OPENAI_BASE_URL
        if not model:
            model = _env(MINIMAX_MODEL_ENV)

    if not base_url and not api_key and not model:
        return None
    if _looks_like_minimax(base_url):
        using_minimax_alias = True
    if using_minimax_alias and not model:
        model = "MiniMax-M2.7"
    return LLMSettings(
        base_url=base_url or "https://api.openai.com/v1",
        api_key=api_key,
        model=model or "gpt-4.1-mini",
        provider=_provider_for(base_url),
        source="environment",
    )


def read_local_llm_settings(project: Path) -> LLMSettings | None:
    payload = _read_local_payload(project)
    base_url = _payload_text(payload, "base_url")
    api_key = _payload_text(payload, "api_key")
    model = _payload_text(payload, "model")
    provider = _payload_text(payload, "provider") or _provider_for(base_url)
    if not base_url and not api_key and not model:
        return None
    return LLMSettings(
        base_url=base_url,
        api_key=api_key,
        model=model,
        provider=provider,
        source="local",
    )


def save_local_llm_settings(
    project: Path,
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str = "",
) -> LLMSettings:
    selected_provider = provider if provider in PROVIDER_DEFAULTS else "compatible"
    default_base_url, default_model = PROVIDER_DEFAULTS[selected_provider]
    selected_base_url = base_url.strip() or default_base_url
    selected_model = model.strip() or default_model
    _validate_base_url(selected_base_url)
    if not selected_model:
        raise ValueError("Model name is required.")

    previous = read_local_llm_settings(project)
    selected_api_key = api_key.strip() or (previous.api_key if previous else "")
    path = local_llm_settings_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "provider": selected_provider,
        "base_url": selected_base_url,
        "model": selected_model,
        "api_key": selected_api_key,
    }
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    return LLMSettings(
        base_url=selected_base_url,
        api_key=selected_api_key,
        model=selected_model,
        provider=selected_provider,
        source="local",
    )


def clear_local_llm_settings(project: Path) -> bool:
    path = local_llm_settings_path(project)
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed


def local_llm_settings_path(project: Path) -> Path:
    return project.resolve() / LOCAL_LLM_SETTINGS


def _read_local_payload(project: Path) -> dict[str, object]:
    path = local_llm_settings_path(project)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key, "")
    return str(value).strip() if isinstance(value, str) else ""


def _validate_base_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be a valid http:// or https:// URL.")
    if parsed.username or parsed.password:
        raise ValueError("Do not put credentials in the Base URL.")


def _provider_for(base_url: str) -> str:
    if _looks_like_minimax(base_url):
        return "minimax"
    if "api.openai.com" in base_url.lower():
        return "openai"
    return "compatible"


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _looks_like_minimax(base_url: str) -> bool:
    return "minimaxi.com" in base_url.lower() or "minimax.chat" in base_url.lower()


def chat_completion(
    settings: LLMSettings,
    *,
    system: str,
    user: str,
    timeout: int = 90,
) -> str:
    url = settings.base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        },
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM response did not include choices.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("LLM response did not include message content.")
    return clean_chat_response(message["content"])


def clean_chat_response(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(
        r"<reasoning>.*?</reasoning>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return cleaned.strip()
