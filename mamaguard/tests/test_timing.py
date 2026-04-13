"""
Unit tests for agent response timing instrumentation.

Covers:
  - before_tool_timing records start time for sub-agent tools
  - before_tool_timing ignores non-agent tools
  - after_tool_timing computes elapsed and stores in state
  - after_tool_timing ignores non-agent tools
  - after_tool_timing handles missing start gracefully
  - format_timing_line formats single and multiple agents
  - inject_timing_callback appends timing to Transaction section
  - inject_timing_callback is no-op when no timing data
  - inject_timing_callback handles missing Transaction section
  - Orchestrator wiring includes timing callbacks
  - JSON mode includes timing data
"""

from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from typing import Any

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from mamaguard.shared.timing import (
    _AGENT_LABELS,
    _STATE_KEY_STARTS,
    _STATE_KEY_TIMINGS,
    after_tool_timing,
    before_tool_timing,
    format_timing_line,
    inject_timing_callback,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _make_context(state: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(state=state or {})


def _make_response(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=text)],
        ),
    )


SAMPLE_5T = """\
**Talk** — Maria presents with elevated BP.

**Template** — Combined Risk Level: URGENT
Maternal: BP 162/104 (Observation/bp-m5).

**Table**
| Metric | Value |
|--------|-------|
| BP | 162/104 |

**Task**
1. URGENT — Clinician review of BP trend | Clinician | 24h

**Transaction** — RiskAssessment/ra-001 (maternal_risk_agent). All require clinician approval.

AI-generated analysis of synthetic data. Not for clinical use.
"""


# ---------------------------------------------------------------------------
# before_tool_timing
# ---------------------------------------------------------------------------

class TestBeforeToolTiming(unittest.TestCase):

    def test_records_start_for_agent_tool(self):
        ctx = _make_context()
        tool = _make_tool("maternal_risk_agent")
        result = before_tool_timing(tool, {}, ctx)
        self.assertIsNone(result)
        starts = ctx.state[_STATE_KEY_STARTS]
        self.assertIn("maternal_risk_agent", starts)
        self.assertIsInstance(starts["maternal_risk_agent"], float)

    def test_ignores_non_agent_tool(self):
        ctx = _make_context()
        tool = _make_tool("find_linked_newborn")
        result = before_tool_timing(tool, {}, ctx)
        self.assertIsNone(result)
        self.assertNotIn(_STATE_KEY_STARTS, ctx.state)

    def test_records_multiple_agents(self):
        ctx = _make_context()
        for name in _AGENT_LABELS:
            before_tool_timing(_make_tool(name), {}, ctx)
        starts = ctx.state[_STATE_KEY_STARTS]
        self.assertEqual(set(starts.keys()), set(_AGENT_LABELS.keys()))

    def test_tool_without_name_attr(self):
        ctx = _make_context()
        tool = object()  # no .name attribute
        result = before_tool_timing(tool, {}, ctx)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# after_tool_timing
# ---------------------------------------------------------------------------

class TestAfterToolTiming(unittest.TestCase):

    def test_computes_elapsed(self):
        ctx = _make_context()
        tool = _make_tool("maternal_risk_agent")
        # Simulate before
        before_tool_timing(tool, {}, ctx)
        result = after_tool_timing(tool, {}, ctx, {"status": "ok"})
        self.assertIsNone(result)
        timings = ctx.state[_STATE_KEY_TIMINGS]
        self.assertEqual(len(timings), 1)
        self.assertEqual(timings[0]["agent"], "maternal_risk_agent")
        self.assertEqual(timings[0]["label"], "Maternal assessment")
        self.assertGreaterEqual(timings[0]["elapsed_s"], 0.0)
        self.assertIsInstance(timings[0]["elapsed_s"], float)

    def test_ignores_non_agent_tool(self):
        ctx = _make_context()
        tool = _make_tool("get_patient_summary")
        result = after_tool_timing(tool, {}, ctx, {"status": "ok"})
        self.assertIsNone(result)
        self.assertNotIn(_STATE_KEY_TIMINGS, ctx.state)

    def test_handles_missing_start(self):
        """after_tool without matching before_tool should not crash."""
        ctx = _make_context()
        tool = _make_tool("maternal_risk_agent")
        result = after_tool_timing(tool, {}, ctx, {"status": "ok"})
        self.assertIsNone(result)
        self.assertNotIn(_STATE_KEY_TIMINGS, ctx.state)

    def test_multiple_agents_accumulate(self):
        ctx = _make_context()
        for name in ["maternal_risk_agent", "sdoh_outreach_agent"]:
            tool = _make_tool(name)
            before_tool_timing(tool, {}, ctx)
            after_tool_timing(tool, {}, ctx, {"status": "ok"})
        timings = ctx.state[_STATE_KEY_TIMINGS]
        self.assertEqual(len(timings), 2)
        agents = [t["agent"] for t in timings]
        self.assertIn("maternal_risk_agent", agents)
        self.assertIn("sdoh_outreach_agent", agents)

    def test_clears_start_after_recording(self):
        ctx = _make_context()
        tool = _make_tool("maternal_risk_agent")
        before_tool_timing(tool, {}, ctx)
        after_tool_timing(tool, {}, ctx, {"status": "ok"})
        starts = ctx.state.get(_STATE_KEY_STARTS, {})
        self.assertNotIn("maternal_risk_agent", starts)


# ---------------------------------------------------------------------------
# format_timing_line
# ---------------------------------------------------------------------------

class TestFormatTimingLine(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(format_timing_line([]), "")

    def test_single_agent(self):
        timings = [{"label": "Maternal assessment", "elapsed_s": 2.3}]
        result = format_timing_line(timings)
        self.assertEqual(result, "Timing: Maternal assessment: 2.3s, Total: 2.3s.")

    def test_multiple_agents(self):
        timings = [
            {"label": "Maternal assessment", "elapsed_s": 2.3},
            {"label": "SDOH screening", "elapsed_s": 1.8},
        ]
        result = format_timing_line(timings)
        self.assertEqual(
            result,
            "Timing: Maternal assessment: 2.3s, SDOH screening: 1.8s, Total: 4.1s.",
        )

    def test_all_three_agents(self):
        timings = [
            {"label": "Maternal assessment", "elapsed_s": 2.3},
            {"label": "Pediatric assessment", "elapsed_s": 1.5},
            {"label": "SDOH screening", "elapsed_s": 1.8},
        ]
        result = format_timing_line(timings)
        self.assertIn("Total: 5.6s", result)

    def test_zero_elapsed(self):
        timings = [{"label": "Maternal assessment", "elapsed_s": 0.0}]
        result = format_timing_line(timings)
        self.assertIn("0.0s", result)


# ---------------------------------------------------------------------------
# inject_timing_callback
# ---------------------------------------------------------------------------

class TestInjectTimingCallback(unittest.TestCase):

    def test_injects_after_transaction(self):
        ctx = _make_context({
            _STATE_KEY_TIMINGS: [
                {"agent": "maternal_risk_agent", "label": "Maternal assessment", "elapsed_s": 2.3},
            ],
        })
        resp = _make_response(SAMPLE_5T)
        result = inject_timing_callback(ctx, resp)
        self.assertIsNone(result)
        text = resp.content.parts[0].text
        self.assertIn("Timing: Maternal assessment: 2.3s, Total: 2.3s.", text)
        # Timing should be after Transaction, before disclaimer
        trans_idx = text.index("**Transaction**")
        timing_idx = text.index("Timing:")
        disclaimer_idx = text.index("AI-generated")
        self.assertGreater(timing_idx, trans_idx)
        self.assertLess(timing_idx, disclaimer_idx)

    def test_no_timing_data_no_op(self):
        ctx = _make_context({})
        resp = _make_response(SAMPLE_5T)
        original = resp.content.parts[0].text
        result = inject_timing_callback(ctx, resp)
        self.assertIsNone(result)
        self.assertEqual(resp.content.parts[0].text, original)

    def test_empty_timings_list_no_op(self):
        ctx = _make_context({_STATE_KEY_TIMINGS: []})
        resp = _make_response(SAMPLE_5T)
        original = resp.content.parts[0].text
        inject_timing_callback(ctx, resp)
        self.assertEqual(resp.content.parts[0].text, original)

    def test_no_transaction_section_no_crash(self):
        ctx = _make_context({
            _STATE_KEY_TIMINGS: [
                {"agent": "maternal_risk_agent", "label": "Maternal assessment", "elapsed_s": 1.0},
            ],
        })
        resp = _make_response("**Talk** — Summary.\n**Template** — Risk: ROUTINE")
        original = resp.content.parts[0].text
        inject_timing_callback(ctx, resp)
        # No Transaction section → text unchanged
        self.assertEqual(resp.content.parts[0].text, original)

    def test_none_content(self):
        ctx = _make_context({
            _STATE_KEY_TIMINGS: [
                {"agent": "maternal_risk_agent", "label": "Maternal assessment", "elapsed_s": 1.0},
            ],
        })
        resp = LlmResponse(content=None)
        result = inject_timing_callback(ctx, resp)
        self.assertIsNone(result)

    def test_none_parts(self):
        ctx = _make_context({
            _STATE_KEY_TIMINGS: [
                {"agent": "maternal_risk_agent", "label": "Maternal assessment", "elapsed_s": 1.0},
            ],
        })
        resp = LlmResponse(content=types.Content(role="model", parts=None))
        result = inject_timing_callback(ctx, resp)
        self.assertIsNone(result)

    def test_multi_agent_timing(self):
        ctx = _make_context({
            _STATE_KEY_TIMINGS: [
                {"agent": "maternal_risk_agent", "label": "Maternal assessment", "elapsed_s": 2.3},
                {"agent": "sdoh_outreach_agent", "label": "SDOH screening", "elapsed_s": 1.8},
            ],
        })
        resp = _make_response(SAMPLE_5T)
        inject_timing_callback(ctx, resp)
        text = resp.content.parts[0].text
        self.assertIn("Maternal assessment: 2.3s", text)
        self.assertIn("SDOH screening: 1.8s", text)
        self.assertIn("Total: 4.1s", text)


# ---------------------------------------------------------------------------
# Orchestrator wiring
# ---------------------------------------------------------------------------

class TestOrchestratorWiring(unittest.TestCase):

    def test_orchestrator_has_timing_callbacks(self):
        from mamaguard.orchestrator.agent import root_agent
        self.assertIsNotNone(root_agent.before_tool_callback)
        self.assertIsNotNone(root_agent.after_tool_callback)

    def test_after_model_chain_includes_timing(self):
        import inspect
        from mamaguard.orchestrator.agent import _orchestrator_after_model_callback
        source = inspect.getsource(_orchestrator_after_model_callback)
        self.assertIn("inject_timing_callback", source)


# ---------------------------------------------------------------------------
# JSON mode timing integration
# ---------------------------------------------------------------------------

class TestJsonTimingIntegration(unittest.TestCase):

    def test_json_output_includes_timing(self):
        from mamaguard.shared.json_formatter import json_output_callback
        import json

        ctx = _make_context({
            "output_format": "json",
            _STATE_KEY_TIMINGS: [
                {"agent": "maternal_risk_agent", "label": "Maternal assessment", "elapsed_s": 2.3},
                {"agent": "sdoh_outreach_agent", "label": "SDOH screening", "elapsed_s": 1.8},
            ],
        })
        resp = _make_response(SAMPLE_5T)
        json_output_callback(ctx, resp)
        data = json.loads(resp.content.parts[0].text)
        self.assertIn("timing", data)
        self.assertEqual(data["timing"]["total_s"], 4.1)
        self.assertEqual(data["timing"]["agents"]["maternal_risk_agent"], 2.3)
        self.assertEqual(data["timing"]["agents"]["sdoh_outreach_agent"], 1.8)

    def test_json_output_no_timing_when_absent(self):
        from mamaguard.shared.json_formatter import json_output_callback
        import json

        ctx = _make_context({"output_format": "json"})
        resp = _make_response(SAMPLE_5T)
        json_output_callback(ctx, resp)
        data = json.loads(resp.content.parts[0].text)
        self.assertNotIn("timing", data)


if __name__ == "__main__":
    unittest.main()
