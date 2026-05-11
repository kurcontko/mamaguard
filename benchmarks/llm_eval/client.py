"""
OpenAI-compatible chat completion client for vLLM.

Configure via env vars or pass directly:
    BENCH_API_BASE    — vLLM endpoint (default: http://localhost:8000/v1)
    BENCH_MODEL       — model name served by vLLM
    BENCH_API_KEY     — API key (default: "EMPTY" for local vLLM)
    BENCH_MAX_TOKENS  — max tokens for completion (default: 4096)
    BENCH_TEMPERATURE — temperature (default: 0.0 for deterministic eval)
    BENCH_TOP_P       — top-p nucleus sampling (default: not set)
    BENCH_TIMEOUT     — request timeout in seconds (default: 120)
    BENCH_REASONING_EFFORT — optional reasoning effort for compatible APIs
    BENCH_THINKING    — optional thinking mode: enabled or disabled

    JUDGE_API_BASE    — judge model endpoint (falls back to BENCH_API_BASE)
    JUDGE_MODEL       — judge model name (falls back to BENCH_MODEL)
    JUDGE_API_KEY     — judge API key (falls back to BENCH_API_KEY)
    JUDGE_TOP_P       — judge top-p (default: not set)
    JUDGE_REASONING_EFFORT — optional reasoning effort for compatible APIs
    JUDGE_THINKING    — optional thinking mode: enabled or disabled
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import httpx


@dataclass
class LLMConfig:
    api_base: str
    model: str
    api_key: str = "EMPTY"
    max_tokens: int = 4096
    temperature: float = 0.0
    top_p: float | None = None
    timeout: int = 120
    reasoning_effort: str | None = None
    thinking: str | None = None

    @classmethod
    def from_env(cls, prefix: str = "BENCH") -> LLMConfig:
        top_p_raw = os.environ.get(f"{prefix}_TOP_P")
        thinking_raw = os.environ.get(f"{prefix}_THINKING")
        return cls(
            api_base=os.environ.get(f"{prefix}_API_BASE", "http://localhost:8000/v1"),
            model=os.environ.get(f"{prefix}_MODEL", ""),
            api_key=os.environ.get(f"{prefix}_API_KEY", "EMPTY"),
            max_tokens=int(os.environ.get(f"{prefix}_MAX_TOKENS", "4096")),
            temperature=float(os.environ.get(f"{prefix}_TEMPERATURE", "0.0")),
            top_p=float(top_p_raw) if top_p_raw is not None else None,
            timeout=int(os.environ.get(f"{prefix}_TIMEOUT", "120")),
            reasoning_effort=os.environ.get(f"{prefix}_REASONING_EFFORT") or None,
            thinking=thinking_raw.lower() if thinking_raw else None,
        )

    @classmethod
    def judge_from_env(cls) -> LLMConfig:
        """Load judge config, falling back to BENCH_ vars."""
        top_p_raw = os.environ.get("JUDGE_TOP_P")
        thinking_raw = os.environ.get("JUDGE_THINKING", os.environ.get("BENCH_THINKING"))
        return cls(
            api_base=os.environ.get("JUDGE_API_BASE", os.environ.get("BENCH_API_BASE", "http://localhost:8000/v1")),
            model=os.environ.get("JUDGE_MODEL", os.environ.get("BENCH_MODEL", "")),
            api_key=os.environ.get("JUDGE_API_KEY", os.environ.get("BENCH_API_KEY", "EMPTY")),
            max_tokens=int(os.environ.get("JUDGE_MAX_TOKENS", "1024")),
            temperature=float(os.environ.get("JUDGE_TEMPERATURE", "0.0")),
            top_p=float(top_p_raw) if top_p_raw is not None else None,
            timeout=int(os.environ.get("JUDGE_TIMEOUT", "120")),
            reasoning_effort=os.environ.get("JUDGE_REASONING_EFFORT", os.environ.get("BENCH_REASONING_EFFORT")) or None,
            thinking=thinking_raw.lower() if thinking_raw else None,
        )


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    elapsed_ms: float
    raw: dict


def chat_completion(
    messages: list[dict[str, str]],
    config: LLMConfig | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> LLMResponse:
    """
    Call OpenAI-compatible chat completion endpoint.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        config: LLMConfig (defaults to env-based config).
        tools: Optional tool definitions for function calling.
        tool_choice: Optional tool_choice parameter.

    Returns:
        LLMResponse with content, token counts, and timing.
    """
    if config is None:
        config = LLMConfig.from_env()

    if not config.model:
        raise ValueError(
            "No model specified. Set BENCH_MODEL env var or pass config.model. "
            "Example: BENCH_MODEL=meta-llama/Llama-3.1-70B-Instruct"
        )

    url = f"{config.api_base.rstrip('/')}/chat/completions"

    body: dict = {
        "model": config.model,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }
    if config.top_p is not None:
        body["top_p"] = config.top_p
    if config.reasoning_effort:
        body["reasoning_effort"] = config.reasoning_effort
    if config.thinking:
        body["thinking"] = {"type": config.thinking}
    if tools:
        body["tools"] = tools
    if tool_choice is not None:
        body["tool_choice"] = tool_choice

    headers = {
        "Content-Type": "application/json",
    }
    if config.api_key and config.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {config.api_key}"

    t0 = time.perf_counter()
    resp = httpx.post(
        url,
        json=body,
        headers=headers,
        timeout=config.timeout,
    )
    elapsed = (time.perf_counter() - t0) * 1000

    resp.raise_for_status()
    data = resp.json()

    choice = data["choices"][0]
    message = choice.get("message", {})
    content = message.get("content") or ""

    # Handle tool calls in response
    tool_calls = message.get("tool_calls")
    if tool_calls and not content:
        content = json.dumps(tool_calls)

    usage = data.get("usage", {})

    return LLMResponse(
        content=content,
        model=data.get("model", config.model),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        elapsed_ms=elapsed,
        raw=data,
    )


def check_endpoint(config: LLMConfig | None = None) -> dict:
    """Verify the vLLM endpoint is reachable and return model info."""
    if config is None:
        config = LLMConfig.from_env()

    url = f"{config.api_base.rstrip('/')}/models"
    headers = {}
    if config.api_key and config.api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {config.api_key}"

    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = [m["id"] for m in data.get("data", [])]
        return {"status": "ok", "models": models, "config_model": config.model}
    except httpx.ConnectError:
        return {"status": "error", "error": f"Cannot connect to {config.api_base}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
