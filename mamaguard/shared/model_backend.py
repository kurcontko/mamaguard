"""Model backend selection for production MamaGuard agents."""

from __future__ import annotations

import os
from typing import Any


def build_agent_model() -> Any:
    """Return an ADK-compatible model based on environment configuration.

    Default is Gemini for backward compatibility. Set
    ``MAMAGUARD_MODEL_BACKEND=openai`` to use an OpenAI-compatible endpoint
    such as OpenRouter.
    """
    backend = os.getenv("MAMAGUARD_MODEL_BACKEND", "gemini").strip().lower()

    if backend in {"", "gemini"}:
        return os.getenv("MAMAGUARD_GEMINI_MODEL", "gemini-2.5-flash")

    if backend in {"openai", "openrouter", "litellm", "vllm"}:
        from google.adk.models.lite_llm import LiteLlm

        model = os.getenv("MAMAGUARD_MODEL") or os.getenv("OPENAI_MODEL")
        api_base = (
            os.getenv("MAMAGUARD_OPENAI_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("OPENAI_API_BASE")
        )
        api_key = os.getenv("MAMAGUARD_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

        missing = []
        if not model:
            missing.append("MAMAGUARD_MODEL or OPENAI_MODEL")
        if not api_base:
            missing.append("MAMAGUARD_OPENAI_BASE_URL or OPENAI_BASE_URL")
        if not api_key:
            missing.append("MAMAGUARD_OPENAI_API_KEY or OPENAI_API_KEY")
        if missing:
            raise RuntimeError(
                "OpenAI-compatible model backend requested but missing env vars: "
                + ", ".join(missing)
            )

        lite_model = model if model.startswith("openai/") else f"openai/{model}"
        return LiteLlm(model=lite_model, api_base=api_base, api_key=api_key)

    raise ValueError(
        f"Unsupported MAMAGUARD_MODEL_BACKEND={backend!r}. "
        "Use 'gemini' or 'openai'."
    )

