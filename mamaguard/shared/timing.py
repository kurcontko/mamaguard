"""
Agent response timing instrumentation.

Measures wall-clock time per sub-agent call in the orchestrator and injects
elapsed times into the Transaction section of 5T output.

Usage:
  - ``before_tool_timing`` and ``after_tool_timing`` are wired as
    ``before_tool_callback`` and ``after_tool_callback`` on the orchestrator.
  - ``inject_timing_callback`` is called in the ``after_model_callback`` chain
    to append a timing summary line to the Transaction section.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from google.adk.models.llm_response import LlmResponse

logger = logging.getLogger(__name__)

# Sub-agent names → human-readable labels
_AGENT_LABELS: dict[str, str] = {
    "maternal_risk_agent": "Maternal assessment",
    "pediatric_transition_agent": "Pediatric assessment",
    "sdoh_outreach_agent": "SDOH screening",
}

_STATE_KEY_STARTS = "_agent_timing_starts"
_STATE_KEY_TIMINGS = "_agent_timings"


def before_tool_timing(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
) -> dict | None:
    """Record start time when an AgentTool (sub-agent) is called."""
    tool_name = getattr(tool, "name", "")
    if tool_name not in _AGENT_LABELS:
        return None

    starts = tool_context.state.get(_STATE_KEY_STARTS) or {}
    starts[tool_name] = time.perf_counter()
    tool_context.state[_STATE_KEY_STARTS] = starts
    return None


def after_tool_timing(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: dict,
) -> dict | None:
    """Record elapsed time after a sub-agent call completes."""
    tool_name = getattr(tool, "name", "")
    if tool_name not in _AGENT_LABELS:
        return None

    starts = tool_context.state.get(_STATE_KEY_STARTS) or {}
    start = starts.pop(tool_name, None)
    tool_context.state[_STATE_KEY_STARTS] = starts

    if start is None:
        return None

    elapsed_s = time.perf_counter() - start

    timings = tool_context.state.get(_STATE_KEY_TIMINGS) or []
    timings.append({
        "agent": tool_name,
        "label": _AGENT_LABELS[tool_name],
        "elapsed_s": round(elapsed_s, 1),
    })
    tool_context.state[_STATE_KEY_TIMINGS] = timings

    logger.info("%s completed in %.1fs", _AGENT_LABELS[tool_name], elapsed_s)
    return None


def format_timing_line(timings: list[dict[str, Any]]) -> str:
    """Format timing data as a single summary line.

    Returns empty string if no timing data.
    """
    if not timings:
        return ""

    parts = []
    total = 0.0
    for t in timings:
        elapsed = t.get("elapsed_s", 0.0)
        parts.append(f"{t['label']}: {elapsed:.1f}s")
        total += elapsed
    parts.append(f"Total: {total:.1f}s")
    return "Timing: " + ", ".join(parts) + "."


# Regex to find the Transaction section: matches from **Transaction** through
# continuation lines, stopping at the first blank line or end of text.
_TRANSACTION_RE = re.compile(
    r"(\*\*Transaction\*\*[^\n]*(?:\n[^\n]+)*)",
    re.IGNORECASE,
)


def inject_timing_callback(
    callback_context: Any,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Inject timing summary into the Transaction section of the response.

    Reads ``_agent_timings`` from ``callback_context.state`` (populated by
    ``before_tool_timing`` / ``after_tool_timing``).  Appends a single timing
    line after the Transaction section content.  Returns ``None`` (mutates
    in-place).
    """
    state = getattr(callback_context, "state", None) or {}
    timings = state.get(_STATE_KEY_TIMINGS)

    if not timings:
        return None

    timing_line = format_timing_line(timings)
    if not timing_line:
        return None

    content = llm_response.content
    if content is None or content.parts is None:
        return None

    for part in content.parts:
        if not part.text:
            continue
        m = _TRANSACTION_RE.search(part.text)
        if m:
            insert_pos = m.end()
            part.text = (
                part.text[:insert_pos] + "\n" + timing_line + part.text[insert_pos:]
            )
            return None

    return None
