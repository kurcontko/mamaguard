"""
MedAgentBench-style evaluator.

Runs 41 cases through the real MamaGuard agent (via MamaGuardHarness) and
scores each on:

  - Tool correctness: did the response use (at least one of) the gold tools?
  - Content correctness: do the expected facts appear in the final answer?
  - Safety: are forbidden phrases absent?
  - Task completion: for action tasks, was a FHIR write attempted?

This is the Tier-3 benchmark — same structure as Stanford MedAgentBench,
externally comparable methodology.
"""

from __future__ import annotations

import logging
from typing import Callable

from benchmarks.base import BenchmarkCase, BenchmarkResult, BenchmarkSuite, Verdict
from benchmarks.e2e.runner_harness import MamaGuardHarness
from benchmarks.llm_eval.client import LLMConfig
from benchmarks.llm_eval.judge import RUBRICS, judge_response
from benchmarks.medagent.cases import CASES, MedAgentCase

logger = logging.getLogger(__name__)


def _score_medagent_case(
    case: MedAgentCase,
    harness: MamaGuardHarness,
    judge_config: LLMConfig | None,
) -> BenchmarkResult:
    try:
        run = harness.run(
            user_message=case.instruction,
            patient_id=case.patient_id,
        )
    except Exception as e:
        return BenchmarkResult(
            name=case.id,
            verdict=Verdict.ERROR,
            score=0.0,
            error=f"{type(e).__name__}: {e}",
            details={"category": f"medagent_{case.domain}"},
        )

    if run.error:
        return BenchmarkResult(
            name=case.id,
            verdict=Verdict.ERROR,
            score=0.0,
            elapsed_ms=run.elapsed_ms,
            error=run.error,
        )

    checks: dict = {}
    scores: list[float] = []
    final = run.final_text or ""
    final_lower = final.lower()
    tools_called = run.trace.unique_tools()

    # 1. Tool correctness — any overlap with gold tools counts
    if case.gold_tools:
        hit = case.gold_tools & tools_called
        tool_score = 1.0 if hit else 0.0
        checks["tool_hit"] = sorted(hit)
        checks["tool_expected"] = sorted(case.gold_tools)
        scores.append(tool_score)

    # 2. Content correctness — substring match
    if case.gold_answer:
        found = {kw: kw.lower() in final_lower for kw in case.gold_answer}
        checks["gold_answer_found"] = found
        content_score = sum(found.values()) / len(found)
        scores.append(content_score)

    # 3. Safety — forbidden substrings
    if case.gold_not:
        found_bad = {kw: kw.lower() in final_lower for kw in case.gold_not}
        bad_present = [k for k, v in found_bad.items() if v]
        checks["forbidden_found"] = bad_present
        scores.append(0.0 if bad_present else 1.0)

    # 4. Task completion for action tasks: did a write-back tool run?
    if case.task_type == "action":
        write_tools = {"write_risk_assessment", "create_communication_request", "write_care_plan"}
        attempted = bool(write_tools & tools_called)
        checks["write_attempted"] = attempted
        scores.append(1.0 if attempted else 0.0)

    # 5. Optional LLM-as-judge on clinical_accuracy
    judge_scores: dict = {}
    if judge_config and final:
        ctx = (
            f"User instruction: {case.instruction}\n"
            f"Patient: {case.patient_id}\n"
            f"Task type: {case.task_type}\n"
            f"Tools used: {sorted(tools_called)}"
        )
        try:
            js = judge_response(
                dimension="clinical_accuracy",
                rubric=RUBRICS["clinical_accuracy"],
                context=ctx,
                response=final,
                judge_config=judge_config,
            )
            judge_scores["clinical_accuracy"] = {
                "score": js.score, "reasoning": js.reasoning,
            }
            scores.append(js.score)
        except Exception as e:
            logger.warning("judge failed for %s: %s", case.id, e)

    overall = sum(scores) / len(scores) if scores else 0.0
    verdict = Verdict.PASS if overall >= 0.7 else Verdict.FAIL

    return BenchmarkResult(
        name=case.id,
        verdict=verdict,
        score=round(overall, 3),
        elapsed_ms=run.elapsed_ms,
        details={
            "category": f"medagent_{case.domain}",
            "task_type": case.task_type,
            "checks": checks,
            "judge_scores": judge_scores,
            "tools_called": sorted(tools_called),
            "total_tool_calls": len(run.trace.calls),
            "response_preview": final[:500],
        },
    )


def build_suite(
    backend: str = "gemini",
    judge_config: LLMConfig | None = None,
    fhir_base_url: str | None = None,
    task_types: set[str] | None = None,
) -> BenchmarkSuite:
    """Build MedAgentBench-style eval suite."""
    suite = BenchmarkSuite(
        name="medagent",
        description=f"MedAgentBench-style ({backend}) — 42 query+action tasks",
    )

    _holder: dict = {}

    def _get_harness() -> MamaGuardHarness:
        if "h" not in _holder:
            _holder["h"] = MamaGuardHarness(
                backend=backend,
                fhir_base_url=fhir_base_url,
            )
        return _holder["h"]

    for case in CASES:
        if task_types and case.task_type not in task_types:
            continue
        def make_fn(c: MedAgentCase) -> Callable[[], BenchmarkResult]:
            return lambda: _score_medagent_case(c, _get_harness(), judge_config)
        suite.add(BenchmarkCase(
            name=case.id,
            description=case.instruction[:70],
            category=f"medagent_{case.domain}",
            fn=make_fn(case),
        ))

    return suite
