"""
MamaGuard agent factory with swappable model backend.

Supports:
  - "gemini"  — production config (gemini-2.5-flash, requires GOOGLE_API_KEY)
  - "vllm"    — LiteLlm wrapper around OpenAI-compatible vLLM endpoint
                (uses BENCH_API_BASE, BENCH_MODEL, BENCH_API_KEY)

Builds a fresh agent tree so tool-call traces and callbacks can be attached
without contaminating the production module-level root_agent.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from mamaguard.shared.fhir_hook import extract_fhir_context
from mamaguard.shared.tools import (
    create_communication_request,
    find_sdoh_resources,
    get_active_medications,
    get_bp_trend,
    get_care_gaps,
    get_developmental_screening_status,
    get_glucose_trend,
    get_immunization_gaps,
    get_maternal_risk_profile,
    get_patient_summary,
    get_pregnancy_history,
    get_sdoh_screening,
    write_care_plan,
    write_risk_assessment,
)
from mamaguard.maternal_agent.agent import MATERNAL_INSTRUCTION
from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION
from mamaguard.pediatric_agent.agent import PEDIATRIC_INSTRUCTION
from mamaguard.sdoh_agent.agent import SDOH_INSTRUCTION


def build_model(backend: str = "gemini") -> Any:
    """
    Return a model identifier or BaseLlm instance suitable for Agent(model=...).
    """
    if backend == "gemini":
        if not os.environ.get("GOOGLE_API_KEY"):
            raise RuntimeError(
                "GOOGLE_API_KEY not set — required for gemini backend. "
                "Either export GOOGLE_API_KEY or use --backend vllm."
            )
        return "gemini-2.5-flash"

    if backend == "vllm":
        from google.adk.models.lite_llm import LiteLlm

        api_base = os.environ.get("BENCH_API_BASE", "http://localhost:8000/v1")
        model = os.environ.get("BENCH_MODEL", "")
        api_key = os.environ.get("BENCH_API_KEY", "EMPTY")

        if not model:
            raise RuntimeError(
                "BENCH_MODEL not set — required for vllm backend. "
                "Example: export BENCH_MODEL=meta-llama/Llama-3.1-70B-Instruct"
            )

        # LiteLLM routes OpenAI-compatible endpoints via the "openai/" prefix.
        lite_model = model if model.startswith("openai/") else f"openai/{model}"
        return LiteLlm(
            model=lite_model,
            api_base=api_base,
            api_key=api_key,
        )

    raise ValueError(f"Unknown backend: {backend!r}. Use 'gemini' or 'vllm'.")


def build_agent_tree(
    backend: str = "gemini",
    before_tool_callback: Callable | None = None,
    after_tool_callback: Callable | None = None,
) -> Agent:
    """
    Build a fresh MamaGuard agent tree (orchestrator + 3 specialists).

    Args:
        backend: "gemini" or "vllm"
        before_tool_callback: optional ADK before_tool_callback for trace capture
        after_tool_callback: optional ADK after_tool_callback for trace capture

    Returns:
        The orchestrator Agent ready for Runner execution.
    """
    model = build_model(backend)

    common_kwargs: dict[str, Any] = {
        "before_model_callback": extract_fhir_context,
    }
    if before_tool_callback is not None:
        common_kwargs["before_tool_callback"] = before_tool_callback
    if after_tool_callback is not None:
        common_kwargs["after_tool_callback"] = after_tool_callback

    maternal = Agent(
        name="maternal_risk_agent",
        model=model,
        description="Maternal health risk assessment specialist.",
        instruction=MATERNAL_INSTRUCTION,
        tools=[
            get_maternal_risk_profile,
            get_bp_trend,
            get_glucose_trend,
            get_pregnancy_history,
            get_active_medications,
            get_patient_summary,
            write_risk_assessment,
        ],
        **common_kwargs,
    )

    pediatric = Agent(
        name="pediatric_transition_agent",
        model=model,
        description="Pediatric care transition specialist.",
        instruction=PEDIATRIC_INSTRUCTION,
        tools=[
            get_immunization_gaps,
            get_developmental_screening_status,
            get_care_gaps,
            get_patient_summary,
            create_communication_request,
        ],
        **common_kwargs,
    )

    sdoh = Agent(
        name="sdoh_outreach_agent",
        model=model,
        description="Social determinants of health screening specialist.",
        instruction=SDOH_INSTRUCTION,
        tools=[
            get_sdoh_screening,
            get_patient_summary,
            get_care_gaps,
            find_sdoh_resources,
            write_care_plan,
            create_communication_request,
        ],
        **common_kwargs,
    )

    orchestrator = Agent(
        name="mamaguard_orchestrator",
        model=model,
        description="Maternal-pediatric care coordination orchestrator.",
        instruction=ORCHESTRATOR_INSTRUCTION,
        tools=[
            AgentTool(agent=maternal),
            AgentTool(agent=pediatric),
            AgentTool(agent=sdoh),
        ],
        **common_kwargs,
    )

    return orchestrator
