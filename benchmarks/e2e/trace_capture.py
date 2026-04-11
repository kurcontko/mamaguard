"""
Tool-call trace capture via ADK before/after_tool_callback hooks.

Records every tool invocation made during an agent run:
  - Which tool was called (by name)
  - What arguments were passed
  - Which agent made the call
  - How long it took
  - Whether it returned success or error
  - The raw result (for verification)

The trace is attached to the agent's state so it survives across the whole
run. Use `TraceCollector` as a context manager or call `reset()` between runs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """One recorded tool invocation."""
    tool_name: str
    args: dict[str, Any]
    agent_name: str
    started_at: float
    ended_at: float | None = None
    result: Any = None
    error: str | None = None

    @property
    def elapsed_ms(self) -> float:
        if self.ended_at is None:
            return 0.0
        return (self.ended_at - self.started_at) * 1000

    @property
    def success(self) -> bool:
        if self.error is not None:
            return False
        if isinstance(self.result, dict):
            return self.result.get("status") != "error"
        return True


@dataclass
class TraceCollector:
    """Records tool calls for a single benchmark invocation."""
    calls: list[ToolCall] = field(default_factory=list)
    _in_flight: dict[int, ToolCall] = field(default_factory=dict)

    def reset(self) -> None:
        self.calls.clear()
        self._in_flight.clear()

    def before_tool(self, tool, args, tool_context) -> None:
        """ADK before_tool_callback — record call start."""
        call = ToolCall(
            tool_name=getattr(tool, "name", str(tool)),
            args=dict(args) if isinstance(args, dict) else {"_raw": str(args)},
            agent_name=self._agent_name_from_context(tool_context),
            started_at=time.perf_counter(),
        )
        self._in_flight[id(tool_context)] = call
        self.calls.append(call)
        return None

    def after_tool(self, tool, args, tool_context, tool_response) -> None:
        """ADK after_tool_callback — record call end + result."""
        call = self._in_flight.pop(id(tool_context), None)
        if call is None:
            # Callback invoked without a matching before; synthesize entry
            call = ToolCall(
                tool_name=getattr(tool, "name", str(tool)),
                args=dict(args) if isinstance(args, dict) else {},
                agent_name=self._agent_name_from_context(tool_context),
                started_at=time.perf_counter(),
            )
            self.calls.append(call)
        call.ended_at = time.perf_counter()
        call.result = tool_response
        if isinstance(tool_response, dict) and tool_response.get("status") == "error":
            call.error = tool_response.get("error_message", "unknown error")
        return None

    def _agent_name_from_context(self, tool_context) -> str:
        """Extract the invoking agent name from the tool context if possible."""
        for attr in ("agent_name", "_agent_name"):
            name = getattr(tool_context, attr, None)
            if name:
                return str(name)
        agent = getattr(tool_context, "agent", None) or getattr(tool_context, "_agent", None)
        if agent is not None:
            return getattr(agent, "name", str(agent))
        invocation_ctx = getattr(tool_context, "_invocation_context", None) or getattr(tool_context, "invocation_context", None)
        if invocation_ctx is not None:
            inv_agent = getattr(invocation_ctx, "agent", None)
            if inv_agent is not None:
                return getattr(inv_agent, "name", "unknown")
        return "unknown"

    # -- Summary helpers ------------------------------------------------------

    def tool_names_called(self) -> list[str]:
        return [c.tool_name for c in self.calls]

    def unique_tools(self) -> set[str]:
        return set(self.tool_names_called())

    def agents_involved(self) -> set[str]:
        return {c.agent_name for c in self.calls if c.agent_name != "unknown"}

    def errors(self) -> list[ToolCall]:
        return [c for c in self.calls if not c.success]

    def to_dict(self) -> dict:
        return {
            "total_calls": len(self.calls),
            "unique_tools": sorted(self.unique_tools()),
            "agents_involved": sorted(self.agents_involved()),
            "errors": [
                {"tool": c.tool_name, "error": c.error}
                for c in self.errors()
            ],
            "calls": [
                {
                    "tool": c.tool_name,
                    "agent": c.agent_name,
                    "args": c.args,
                    "elapsed_ms": round(c.elapsed_ms, 1),
                    "success": c.success,
                }
                for c in self.calls
            ],
        }
