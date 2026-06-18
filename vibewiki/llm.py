from __future__ import annotations


class LLMNotConfigured(RuntimeError):
    """Raised when an optional LLM distiller is requested but unavailable."""


def distill_with_llm(*_: object, **__: object) -> None:
    raise LLMNotConfigured(
        "LLM distillation is not wired in v0.1 yet. Use the local distiller."
    )

