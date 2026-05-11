"""
In-process MamaGuard agent runner harness.

Executes the real agent (with real tool dispatch) using ADK's Runner against
a pre-populated session state. Returns:
  - final text response
  - tool-call trace
  - token usage (if available)
  - elapsed time
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from benchmarks.e2e.agent_factory import build_agent_tree
from benchmarks.e2e.trace_capture import TraceCollector

# Defaults for multi-turn safety
MAX_TURNS = 10
TURN_TIMEOUT_SECONDS = 120.0


@dataclass
class TurnTrace:
    """Per-turn trace snapshot within a multi-turn conversation."""
    turn: int
    user_message: str
    response_text: str
    tool_calls: list[str]
    event_count: int
    elapsed_ms: float


@dataclass
class AgentRunResult:
    """Result of a single agent invocation."""
    final_text: str
    trace: TraceCollector
    elapsed_ms: float
    event_count: int
    error: str | None = None
    events: list[Any] = field(default_factory=list)
    turn_traces: list[TurnTrace] = field(default_factory=list)


class MamaGuardHarness:
    """
    Reusable agent harness for benchmarking.

    Builds one orchestrator tree with trace collectors attached, then lets you
    run it repeatedly against different patient contexts.
    """

    def __init__(self, backend: str = "gemini", fhir_base_url: str | None = None):
        self.backend = backend
        self.fhir_base_url = fhir_base_url or os.environ.get(
            "HAPI_FHIR_URL", "http://localhost:8090/fhir"
        )
        self.trace = TraceCollector()
        self.agent = build_agent_tree(
            backend=backend,
            before_tool_callback=self.trace.before_tool,
            after_tool_callback=self.trace.after_tool,
        )
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            agent=self.agent,
            app_name="mamaguard_bench",
            session_service=self.session_service,
        )

    async def _run_once_async(
        self,
        user_message: str,
        patient_id: str,
        user_id: str = "bench_user",
    ) -> AgentRunResult:
        self.trace.reset()

        session_id = f"bench-{uuid.uuid4().hex[:8]}"
        # Pre-populate session state with FHIR context — this is what the
        # fhir_hook.extract_fhir_context callback normally populates from
        # A2A metadata. Pre-populating bypasses A2A but preserves the same
        # data-flow contract with tools.
        initial_state = {
            "fhir_url": self.fhir_base_url,
            "fhir_token": "bench-no-auth",  # HAPI dev server ignores this
            "patient_id": patient_id,
        }

        await self.session_service.create_session(
            app_name="mamaguard_bench",
            user_id=user_id,
            session_id=session_id,
            state=initial_state,
        )

        msg = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_message)],
        )

        t0 = time.perf_counter()
        events: list[Any] = []
        error: str | None = None
        final_text = ""

        try:
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=msg,
            ):
                events.append(event)
                # Capture the final text response
                content = getattr(event, "content", None)
                if content is not None:
                    parts = getattr(content, "parts", None) or []
                    for part in parts:
                        text = getattr(part, "text", None)
                        if text:
                            final_text = text  # keep the last text part
        except Exception as e:
            error = f"{type(e).__name__}: {e}"

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return AgentRunResult(
            final_text=final_text,
            trace=self.trace,
            elapsed_ms=elapsed_ms,
            event_count=len(events),
            error=error,
            events=events,
        )

    async def _run_multi_turn_async(
        self,
        messages: list[str],
        patient_id: str,
        user_id: str = "bench_user",
        max_turns: int = MAX_TURNS,
        turn_timeout: float = TURN_TIMEOUT_SECONDS,
    ) -> AgentRunResult:
        """Send multiple user messages in sequence within one session.

        The trace accumulates across all turns. The final_text is from the
        last turn only. Elapsed time covers all turns.

        Safety features:
          - max_turns: hard cap on conversation length (default 10)
          - turn_timeout: per-turn timeout in seconds (default 120)
          - turn_traces: per-turn trace snapshots for diagnostics
        """
        if len(messages) > max_turns:
            return AgentRunResult(
                final_text="",
                trace=self.trace,
                elapsed_ms=0.0,
                event_count=0,
                error=f"Exceeded max turns: {len(messages)} messages but limit is {max_turns}",
            )

        self.trace.reset()

        session_id = f"bench-{uuid.uuid4().hex[:8]}"
        initial_state = {
            "fhir_url": self.fhir_base_url,
            "fhir_token": "bench-no-auth",
            "patient_id": patient_id,
        }

        await self.session_service.create_session(
            app_name="mamaguard_bench",
            user_id=user_id,
            session_id=session_id,
            state=initial_state,
        )

        t0 = time.perf_counter()
        all_events: list[Any] = []
        turn_traces: list[TurnTrace] = []
        error: str | None = None
        final_text = ""

        try:
            for turn_idx, user_text in enumerate(messages):
                msg = genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=user_text)],
                )
                turn_text = ""
                turn_events: list[Any] = []
                trace_before = len(self.trace.calls)
                turn_t0 = time.perf_counter()

                async def _consume_turn(new_message, events):
                    nonlocal turn_text
                    async for event in self.runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=new_message,
                    ):
                        events.append(event)
                        content = getattr(event, "content", None)
                        if content is not None:
                            parts = getattr(content, "parts", None) or []
                            for part in parts:
                                text = getattr(part, "text", None)
                                if text:
                                    turn_text = text

                try:
                    await asyncio.wait_for(_consume_turn(msg, turn_events), timeout=turn_timeout)
                except TimeoutError:
                    turn_elapsed = (time.perf_counter() - turn_t0) * 1000
                    turn_tools = [c.tool_name for c in self.trace.calls[trace_before:]]
                    turn_traces.append(TurnTrace(
                        turn=turn_idx,
                        user_message=user_text,
                        response_text=turn_text,
                        tool_calls=turn_tools,
                        event_count=len(turn_events),
                        elapsed_ms=turn_elapsed,
                    ))
                    all_events.extend(turn_events)
                    error = f"TimeoutError: Turn {turn_idx} timed out after {turn_timeout}s"
                    final_text = turn_text
                    break

                turn_elapsed = (time.perf_counter() - turn_t0) * 1000
                turn_tools = [c.tool_name for c in self.trace.calls[trace_before:]]
                turn_traces.append(TurnTrace(
                    turn=turn_idx,
                    user_message=user_text,
                    response_text=turn_text,
                    tool_calls=turn_tools,
                    event_count=len(turn_events),
                    elapsed_ms=turn_elapsed,
                ))
                all_events.extend(turn_events)
                final_text = turn_text
        except Exception as e:
            error = f"{type(e).__name__}: {e}"

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return AgentRunResult(
            final_text=final_text,
            trace=self.trace,
            elapsed_ms=elapsed_ms,
            event_count=len(all_events),
            error=error,
            events=all_events,
            turn_traces=turn_traces,
        )

    def run(
        self,
        user_message: str,
        patient_id: str,
        user_id: str = "bench_user",
    ) -> AgentRunResult:
        """Synchronous wrapper around run_async."""
        return asyncio.run(
            self._run_once_async(user_message, patient_id, user_id)
        )

    def run_multi_turn(
        self,
        messages: list[str],
        patient_id: str,
        user_id: str = "bench_user",
        max_turns: int = MAX_TURNS,
        turn_timeout: float = TURN_TIMEOUT_SECONDS,
    ) -> AgentRunResult:
        """Run a multi-turn conversation. Synchronous wrapper."""
        return asyncio.run(
            self._run_multi_turn_async(
                messages, patient_id, user_id,
                max_turns=max_turns, turn_timeout=turn_timeout,
            )
        )

    async def close(self) -> None:
        """Clean up runner resources."""
        try:
            await self.runner.close()
        except Exception:
            pass
