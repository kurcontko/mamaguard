"""
SubagentTool -- AgentTool wrapper with isolated state + optional timeout.

Differences from ADK's AgentTool:
- Only FHIR-scoped state is forwarded to the child session. Parent
  session bleed (output_format, memory_block, per-turn flags, etc.) is
  blocked so specialist agents see only the patient context they need.
- Optional `timeout_seconds` wraps `run_async` in `asyncio.wait_for`, so
  one misbehaving subagent cannot hang the orchestrator.

Parallel dispatch comes for free: when the orchestrator LLM emits multiple
function calls in one turn, ADK's runner already awaits them concurrently.

Architecture note: this is shift #1 from docs/architecture_v3.md.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.tool_context import ToolContext
from typing_extensions import override

logger = logging.getLogger(__name__)


FORWARDED_STATE_KEYS: frozenset[str] = frozenset({
    "fhir_url",
    "fhir_token",
    "patient_id",
    "fhir_context_errors",
    "smart_ticket",
    "output_format",
})


class SubagentTool(AgentTool):
    """AgentTool with FHIR-scoped state isolation and optional timeout."""

    def __init__(
        self,
        agent,
        *,
        timeout_seconds: float | None = 60.0,
        skip_summarization: bool = False,
        include_plugins: bool = True,
    ):
        super().__init__(
            agent=agent,
            skip_summarization=skip_summarization,
            include_plugins=include_plugins,
        )
        self._timeout_seconds = timeout_seconds

    @override
    async def run_async(
        self,
        *,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> Any:
        filtered_state = _filter_state(tool_context.state.to_dict())
        dropped = set(tool_context.state.to_dict()) - set(filtered_state) - {
            k for k in tool_context.state.to_dict() if k.startswith("_adk")
        }
        if dropped:
            logger.info(
                "subagent_state_filtered agent=%s dropped_keys=%s",
                self.agent.name, sorted(dropped),
            )

        scoped = _ScopedToolContext(tool_context, filtered_state)
        coro = super().run_async(args=args, tool_context=scoped)

        if self._timeout_seconds is None:
            return await coro

        try:
            return await asyncio.wait_for(coro, timeout=self._timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(
                "subagent_timeout agent=%s timeout_seconds=%.1f",
                self.agent.name, self._timeout_seconds,
            )
            return (
                f"Subagent {self.agent.name} timed out after "
                f"{self._timeout_seconds:.0f}s. Partial data unavailable; "
                "clinician should review manually."
            )


def _filter_state(state: dict[str, Any]) -> dict[str, Any]:
    """Keep only FHIR-scoped keys; drop everything else."""
    return {k: v for k, v in state.items() if k in FORWARDED_STATE_KEYS}


class _ScopedToolContext:
    """
    Thin proxy around ToolContext that returns a filtered state view.

    AgentTool reads `tool_context.state.to_dict()` once to seed the child
    session. Every other attribute (actions, invocation context, artifact
    service, etc.) is passed through unchanged.
    """

    def __init__(self, inner: ToolContext, filtered_state: dict[str, Any]):
        self._inner = inner
        self._state = _ScopedState(filtered_state)

    @property
    def state(self) -> "_ScopedState":
        return self._state

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


class _ScopedState:
    """Read-only view onto a filtered state dict with `to_dict()` support."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def update(self, other: dict[str, Any]) -> None:
        self._data.update(other)
