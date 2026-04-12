"""
End-to-end benchmark suite: real MamaGuard agent + real HAPI FHIR +
real tool dispatch via ADK Runner.

Each case is scored on five axes:
  1. Tool-call correctness: were the expected tools actually invoked?
  2. Agent routing correctness: did the orchestrator delegate to the right
     sub-agent(s)?
  3. Final answer quality: does the text response contain the expected
     clinical information and avoid dangerous content?
  4. 5T format compliance: does the response follow the 5T output framework
     (Talk, Template, Table, Task, Transaction)?
  5. Hallucination detection: are FHIR references in the response backed by
     real resources in the patient bundle?

Optionally, an LLM-as-judge scores the answer against clinical rubrics.
"""

from __future__ import annotations

import logging
from typing import Callable

from benchmarks.base import BenchmarkCase, BenchmarkResult, BenchmarkSuite, Verdict
from benchmarks.e2e.cases import ALL_CASES, E2ECase
from benchmarks.e2e.fhir_bundles import get_bundle_refs
from benchmarks.e2e.runner_harness import MamaGuardHarness
from benchmarks.llm_eval.client import LLMConfig
from benchmarks.llm_eval.judge import (
    RUBRICS,
    check_5t_format,
    extract_fhir_refs,
    judge_response,
)

logger = logging.getLogger(__name__)


def _score_case(
    case: E2ECase,
    harness: MamaGuardHarness,
    judge_config: LLMConfig | None,
) -> BenchmarkResult:
    """Run one e2e case and score it."""
    try:
        run = harness.run(
            user_message=case.user_message,
            patient_id=case.patient_id,
        )
    except Exception as e:
        return BenchmarkResult(
            name=case.id,
            verdict=Verdict.ERROR,
            score=0.0,
            error=f"{type(e).__name__}: {e}",
            details={"category": case.category},
        )

    if run.error:
        return BenchmarkResult(
            name=case.id,
            verdict=Verdict.ERROR,
            score=0.0,
            elapsed_ms=run.elapsed_ms,
            error=run.error,
            details={"category": case.category, "trace": run.trace.to_dict()},
        )

    checks: dict = {}
    scores: list[float] = []
    final = run.final_text or ""
    final_lower = final.lower()

    # -- 1. Tool-call correctness --------------------------------------------
    tools_called = run.trace.unique_tools()
    if case.expected_tools:
        expected_hit = case.expected_tools & tools_called
        tool_score = len(expected_hit) / len(case.expected_tools)
        checks["expected_tools_called"] = sorted(expected_hit)
        checks["expected_tools_missed"] = sorted(case.expected_tools - tools_called)
        scores.append(tool_score)

    # Any tool errors?
    tool_errors = run.trace.errors()
    checks["tool_errors"] = [
        {"tool": c.tool_name, "error": c.error} for c in tool_errors
    ]
    # Don't penalize for expected error cases (e.g., write to read-only server)
    if not tool_errors:
        scores.append(1.0)
    else:
        # Soft penalty for unexpected errors
        scores.append(max(0.0, 1.0 - 0.5 * len(tool_errors) / max(1, len(run.trace.calls))))

    # Runaway loops?
    if len(run.trace.calls) > case.max_tool_calls:
        checks["too_many_tool_calls"] = len(run.trace.calls)
        scores.append(0.0)
    else:
        scores.append(1.0)

    # -- 2. Agent routing correctness ----------------------------------------
    if case.expected_agents:
        agents_seen = run.trace.agents_involved()
        # Also check the text response for agent references since
        # AgentTool calls may not always attribute correctly
        agents_hit = {a for a in case.expected_agents if a in agents_seen}
        routing_score = len(agents_hit) / len(case.expected_agents) if case.expected_agents else 1.0
        checks["expected_agents_seen"] = sorted(agents_hit)
        checks["expected_agents_missed"] = sorted(case.expected_agents - agents_hit)
        scores.append(routing_score)

    # -- 3. Final answer content checks --------------------------------------
    if case.answer_must_contain:
        contains = {kw: kw.lower() in final_lower for kw in case.answer_must_contain}
        checks["answer_must_contain"] = contains
        contains_score = sum(contains.values()) / len(contains)
        scores.append(contains_score)

    if case.answer_must_not_contain:
        forbidden = {kw: kw.lower() in final_lower for kw in case.answer_must_not_contain}
        checks["answer_forbidden_present"] = {k: v for k, v in forbidden.items() if v}
        if any(forbidden.values()):
            scores.append(0.0)  # strict: any forbidden phrase is a fail
        else:
            scores.append(1.0)

    # -- 4. 5T format compliance (deterministic) --------------------------------
    if final:
        five_t = check_5t_format(final)
        checks["5t_format"] = five_t["sections"]
        checks["5t_sections_present"] = five_t["count"]
        scores.append(five_t["score"])

    # -- 5. Hallucination detection (FHIR ref verification) -------------------
    if final:
        bundle_refs = get_bundle_refs(case.patient_id)
        # Also accept refs that appeared in tool call results — the agent may
        # echo resource IDs returned by tools (e.g. a newly written CarePlan).
        tool_result_refs: set[str] = set()
        for call in run.trace.calls:
            if isinstance(call.result, dict):
                tool_result_refs.update(extract_fhir_refs(str(call.result)))
        valid_refs = bundle_refs | tool_result_refs

        cited_refs = extract_fhir_refs(final)
        fabricated = [r for r in cited_refs if r not in valid_refs]
        checks["hallucination"] = {
            "cited_refs": cited_refs,
            "fabricated_refs": fabricated,
            "valid_ref_count": len(valid_refs),
        }
        if cited_refs:
            halluc_score = max(0.0, 1.0 - len(fabricated) / len(cited_refs))
        else:
            # No refs cited — not a hallucination, neutral score
            halluc_score = 1.0
        scores.append(halluc_score)

    # -- 6. LLM-as-judge (optional) ------------------------------------------
    judge_scores: dict = {}
    if judge_config and final:
        context_str = (
            f"User: {case.user_message}\n"
            f"Patient: {case.patient_id}\n"
            f"Tool calls: {sorted(tools_called)}"
        )
        for dim in case.rubric_dimensions:
            if dim not in RUBRICS:
                continue
            try:
                js = judge_response(
                    dimension=dim,
                    rubric=RUBRICS[dim],
                    context=context_str,
                    response=final,
                    judge_config=judge_config,
                )
                judge_scores[dim] = {"score": js.score, "reasoning": js.reasoning}
                scores.append(js.score)
            except Exception as e:
                logger.warning("judge call failed for %s/%s: %s", case.id, dim, e)

    overall = sum(scores) / len(scores) if scores else 0.0
    verdict = Verdict.PASS if overall >= 0.7 else Verdict.FAIL

    return BenchmarkResult(
        name=case.id,
        verdict=verdict,
        score=round(overall, 3),
        elapsed_ms=run.elapsed_ms,
        details={
            "category": case.category,
            "checks": checks,
            "judge_scores": judge_scores,
            "tools_called": sorted(tools_called),
            "total_tool_calls": len(run.trace.calls),
            "response_preview": final[:500],
            "patient": case.patient_id,
        },
    )


def build_suite(
    backend: str = "gemini",
    judge_config: LLMConfig | None = None,
    fhir_base_url: str | None = None,
    categories: set[str] | None = None,
) -> BenchmarkSuite:
    """Build the e2e suite. Harness is created lazily on first run."""
    suite = BenchmarkSuite(
        name="e2e",
        description=f"End-to-end MamaGuard ({backend}) vs real HAPI FHIR",
    )

    # Lazy harness: create on first case so that benchmark suite construction
    # is cheap and doesn't fail if no backend is configured.
    _harness_holder: dict = {}

    def _get_harness() -> MamaGuardHarness:
        if "h" not in _harness_holder:
            _harness_holder["h"] = MamaGuardHarness(
                backend=backend,
                fhir_base_url=fhir_base_url,
            )
        return _harness_holder["h"]

    for case in ALL_CASES:
        if categories and case.category not in categories:
            continue
        def make_fn(c: E2ECase) -> Callable[[], BenchmarkResult]:
            return lambda: _score_case(c, _get_harness(), judge_config)
        suite.add(BenchmarkCase(
            name=case.id,
            description=case.name,
            category=f"e2e_{case.category}",
            fn=make_fn(case),
        ))

    return suite
