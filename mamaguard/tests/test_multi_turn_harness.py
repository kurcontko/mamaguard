"""Unit tests for multi-turn harness hardening (task 50).

Tests:
  - Max turns safety valve rejects conversations exceeding the limit
  - Per-turn timeout aborts a hanging turn and reports the error
  - Turn trace aggregation records per-turn diagnostics
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from benchmarks.e2e.runner_harness import (
    MAX_TURNS,
    TURN_TIMEOUT_SECONDS,
    AgentRunResult,
    MamaGuardHarness,
    TurnTrace,
)


class TestMaxTurnsSafetyValve(unittest.TestCase):
    """Max turns cap rejects message lists that exceed the limit."""

    @patch("benchmarks.e2e.runner_harness.build_agent_tree")
    @patch("benchmarks.e2e.runner_harness.Runner")
    @patch("benchmarks.e2e.runner_harness.InMemorySessionService")
    def test_exceeds_max_turns_returns_error(self, _svc, _runner, _tree):
        harness = MamaGuardHarness(backend="gemini")
        messages = [f"msg {i}" for i in range(MAX_TURNS + 1)]
        result = harness.run_multi_turn(messages, patient_id="test-patient", max_turns=MAX_TURNS)
        self.assertIsNotNone(result.error)
        self.assertIn("Exceeded max turns", result.error)
        self.assertEqual(result.final_text, "")
        self.assertEqual(result.event_count, 0)

    @patch("benchmarks.e2e.runner_harness.build_agent_tree")
    @patch("benchmarks.e2e.runner_harness.Runner")
    @patch("benchmarks.e2e.runner_harness.InMemorySessionService")
    def test_custom_max_turns_respected(self, _svc, _runner, _tree):
        harness = MamaGuardHarness(backend="gemini")
        messages = ["a", "b", "c"]
        result = harness.run_multi_turn(messages, patient_id="test-patient", max_turns=2)
        self.assertIsNotNone(result.error)
        self.assertIn("3 messages but limit is 2", result.error)

    @patch("benchmarks.e2e.runner_harness.build_agent_tree")
    @patch("benchmarks.e2e.runner_harness.Runner")
    @patch("benchmarks.e2e.runner_harness.InMemorySessionService")
    def test_at_limit_is_allowed(self, mock_svc, mock_runner_cls, _tree):
        """Exactly max_turns messages should not be rejected."""
        # Set up mocks so the run actually proceeds (even if it does nothing)
        mock_session_svc = MagicMock()
        mock_session_svc.create_session = AsyncMock()
        mock_svc.return_value = mock_session_svc

        async def empty_gen(*args, **kwargs):
            return
            yield  # make it an async generator

        mock_runner = MagicMock()
        mock_runner.run_async = empty_gen
        mock_runner_cls.return_value = mock_runner

        harness = MamaGuardHarness(backend="gemini")
        messages = [f"msg {i}" for i in range(3)]
        result = harness.run_multi_turn(messages, patient_id="test-patient", max_turns=3)
        # Should not have the max-turns error
        self.assertNotEqual(
            result.error and "Exceeded max turns" in result.error,
            True,
        )


class TestPerTurnTimeout(unittest.TestCase):
    """Per-turn timeout aborts a hanging turn."""

    @patch("benchmarks.e2e.runner_harness.build_agent_tree")
    @patch("benchmarks.e2e.runner_harness.Runner")
    @patch("benchmarks.e2e.runner_harness.InMemorySessionService")
    def test_timeout_aborts_turn(self, mock_svc, mock_runner_cls, _tree):
        mock_session_svc = MagicMock()
        mock_session_svc.create_session = AsyncMock()
        mock_svc.return_value = mock_session_svc

        async def slow_gen(*args, **kwargs):
            """Simulate a turn that hangs."""
            await asyncio.sleep(10)  # way longer than our test timeout
            yield  # never reached

        mock_runner = MagicMock()
        mock_runner.run_async = slow_gen
        mock_runner_cls.return_value = mock_runner

        harness = MamaGuardHarness(backend="gemini")
        messages = ["hello", "follow-up"]
        result = harness.run_multi_turn(
            messages, patient_id="test-patient", turn_timeout=0.1,
        )
        self.assertIsNotNone(result.error)
        self.assertIn("timed out", result.error)
        self.assertIn("Turn 0", result.error)
        # Should have recorded a turn trace for the timed-out turn
        self.assertEqual(len(result.turn_traces), 1)
        self.assertEqual(result.turn_traces[0].turn, 0)

    @patch("benchmarks.e2e.runner_harness.build_agent_tree")
    @patch("benchmarks.e2e.runner_harness.Runner")
    @patch("benchmarks.e2e.runner_harness.InMemorySessionService")
    def test_timeout_on_second_turn(self, mock_svc, mock_runner_cls, _tree):
        """First turn completes, second turn times out."""
        mock_session_svc = MagicMock()
        mock_session_svc.create_session = AsyncMock()
        mock_svc.return_value = mock_session_svc

        call_count = 0

        async def mixed_gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First turn completes fast
                event = MagicMock()
                event.content.parts = [MagicMock(text="turn 1 response")]
                yield event
            else:
                # Second turn hangs
                await asyncio.sleep(10)
                yield  # never reached

        mock_runner = MagicMock()
        mock_runner.run_async = mixed_gen
        mock_runner_cls.return_value = mock_runner

        harness = MamaGuardHarness(backend="gemini")
        result = harness.run_multi_turn(
            ["msg1", "msg2"], patient_id="test-patient", turn_timeout=0.1,
        )
        self.assertIsNotNone(result.error)
        self.assertIn("Turn 1", result.error)
        # Two turn traces: one successful, one timed out
        self.assertEqual(len(result.turn_traces), 2)
        self.assertEqual(result.turn_traces[0].turn, 0)
        self.assertEqual(result.turn_traces[1].turn, 1)


class TestTurnTraceAggregation(unittest.TestCase):
    """Turn traces record per-turn diagnostics."""

    @patch("benchmarks.e2e.runner_harness.build_agent_tree")
    @patch("benchmarks.e2e.runner_harness.Runner")
    @patch("benchmarks.e2e.runner_harness.InMemorySessionService")
    def test_turn_traces_populated(self, mock_svc, mock_runner_cls, _tree):
        mock_session_svc = MagicMock()
        mock_session_svc.create_session = AsyncMock()
        mock_svc.return_value = mock_session_svc

        async def gen(*args, **kwargs):
            event = MagicMock()
            event.content.parts = [MagicMock(text="response")]
            yield event

        mock_runner = MagicMock()
        mock_runner.run_async = gen
        mock_runner_cls.return_value = mock_runner

        harness = MamaGuardHarness(backend="gemini")
        result = harness.run_multi_turn(
            ["first", "second", "third"], patient_id="p1",
        )
        self.assertIsNone(result.error)
        self.assertEqual(len(result.turn_traces), 3)
        for i, tt in enumerate(result.turn_traces):
            self.assertEqual(tt.turn, i)
            self.assertIsInstance(tt.elapsed_ms, float)
            self.assertGreaterEqual(tt.elapsed_ms, 0.0)
            self.assertEqual(tt.response_text, "response")

    def test_turn_trace_dataclass_fields(self):
        tt = TurnTrace(
            turn=0, user_message="hello", response_text="hi",
            tool_calls=["tool_a"], event_count=3, elapsed_ms=42.5,
        )
        self.assertEqual(tt.turn, 0)
        self.assertEqual(tt.user_message, "hello")
        self.assertEqual(tt.response_text, "hi")
        self.assertEqual(tt.tool_calls, ["tool_a"])
        self.assertEqual(tt.event_count, 3)
        self.assertAlmostEqual(tt.elapsed_ms, 42.5)


class TestConstants(unittest.TestCase):
    """Verify default constants are sensible."""

    def test_max_turns_default(self):
        self.assertEqual(MAX_TURNS, 10)

    def test_turn_timeout_default(self):
        self.assertEqual(TURN_TIMEOUT_SECONDS, 120.0)

    def test_agent_run_result_has_turn_traces(self):
        from benchmarks.e2e.trace_capture import TraceCollector
        result = AgentRunResult(
            final_text="", trace=TraceCollector(), elapsed_ms=0.0, event_count=0,
        )
        self.assertEqual(result.turn_traces, [])


if __name__ == "__main__":
    unittest.main()
