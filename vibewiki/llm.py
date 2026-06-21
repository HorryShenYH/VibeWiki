from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen

OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_MODEL"
MINIMAX_BASE_URL_ENV = "MINIMAX_BASE_URL"
MINIMAX_API_KEY_ENV = "MINIMAX_API_KEY"
MINIMAX_MODEL_ENV = "MINIMAX_MODEL"
MINIMAX_OPENAI_BASE_URL = "https://api.minimaxi.com/v1"


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


def llm_settings(
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
        model = "MiniMax-M1"
    return LLMSettings(
        base_url=base_url or "https://api.openai.com/v1",
        api_key=api_key,
        model=model or "gpt-4.1-mini",
    )


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
    return message["content"].strip()
