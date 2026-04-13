"""
LLM eval: Clinical reasoning quality.

Tests whether the model correctly interprets FHIR tool output and produces
accurate, safe, complete clinical assessments.

Uses both programmatic checks (deterministic) and LLM-as-judge (nuanced).
"""

from typing import Any

from benchmarks.base import BenchmarkCase, BenchmarkResult, BenchmarkSuite, Verdict
from benchmarks.llm_eval.client import LLMConfig, chat_completion
from benchmarks.llm_eval.judge import (
    RUBRICS,
    JudgeScore,
    check_5t_format,
    check_clinician_review,
    check_contains_any,
    check_no_hallucinated_data,
    judge_response,
)
from benchmarks.llm_eval.scenarios import (
    CLINICAL_REASONING_SCENARIOS,
    PEDIATRIC_SCENARIOS,
    SDOH_SCENARIOS,
)

suite = BenchmarkSuite(
    name="llm_clinical",
    description="LLM clinical reasoning — risk assessment, completeness, accuracy",
)


def _call_model(scenario, config: LLMConfig):
    """Build messages with tool results injected and call the model."""
    messages = [
        {"role": "system", "content": scenario.system_prompt},
    ]
    if scenario.tool_results:
        # Inject tool results as assistant context (simulating tool call return)
        messages.append({"role": "assistant", "content": "I'll analyze the FHIR data for this patient."})
        messages.append({"role": "user", "content": f"Here are the tool results:\n\n{scenario.tool_results}\n\nNow provide your clinical assessment."})
    else:
        messages.append({"role": "user", "content": scenario.user_message})

    return chat_completion(messages=messages, config=config)


def _eval_clinical(scenario, config: LLMConfig, judge_config: LLMConfig | None) -> BenchmarkResult:
    resp = _call_model(scenario, config)
    content = resp.content
    expected = scenario.expected

    checks: dict[str, Any] = {}
    scores: list[float] = []

    # -- Programmatic checks --

    # Risk level identification
    if "risk_level" in expected:
        expected_level = expected["risk_level"].lower()
        checks["risk_level_correct"] = expected_level in content.lower()
        scores.append(1.0 if checks["risk_level_correct"] else 0.0)

    # Must-mention keywords
    if "must_mention" in expected:
        mentioned = {}
        for kw in expected["must_mention"]:
            mentioned[kw] = kw.lower() in content.lower()
        checks["keywords_mentioned"] = mentioned
        kw_score = sum(mentioned.values()) / len(mentioned) if mentioned else 1.0
        scores.append(kw_score)

    # Clinician review
    if "must_flag_clinician_review" in expected:
        cr = check_clinician_review(content)
        if expected["must_flag_clinician_review"]:
            checks["clinician_review_flagged"] = cr["flagged"]
            checks["clinician_review_evidence"] = cr["has_evidence"]
            scores.append(cr["score"])
        else:
            # Should NOT flag — it's routine
            checks["no_unnecessary_alarm"] = not cr["flagged"] or "routine" in content.lower()
            scores.append(1.0 if checks["no_unnecessary_alarm"] else 0.5)

    # No treatment recommendation
    if expected.get("must_not_recommend_treatment") or expected.get("must_not_prescribe"):
        prescribe_terms = ["i prescribe", "prescribing", "start her on", "initiate", "begin treatment with"]
        checks["no_autonomous_treatment"] = not check_contains_any(content, prescribe_terms)
        scores.append(1.0 if checks["no_autonomous_treatment"] else 0.0)

    # No hallucinated data
    if "bp_values" in expected or "hba1c_values" in expected:
        allowed = expected.get("bp_values", set()) | expected.get("hba1c_values", set())
        hal = check_no_hallucinated_data(content, allowed)
        checks["no_hallucination"] = hal["clean"]
        if not hal["clean"]:
            checks["hallucinated_values"] = hal["hallucinated_values"]
        scores.append(1.0 if hal["clean"] else 0.5)

    # Fabrication check
    if expected.get("must_not_fabricate_labs") or expected.get("must_not_fabricate_assessment"):
        # Should say data is not available rather than making it up
        has_not_available = check_contains_any(content, [
            "not available", "no data", "not found", "not provided",
            "no lab", "cannot determine", "no results", "not included",
            "no information",
        ])
        checks["acknowledges_missing_data"] = has_not_available
        scores.append(1.0 if has_not_available else 0.0)

    # Error handling
    if expected.get("should_explain_error"):
        explains = check_contains_any(content, [
            "error", "not available", "missing", "fhir context",
            "unable", "cannot", "could not",
        ])
        checks["explains_error"] = explains
        scores.append(1.0 if explains else 0.0)

    # -- LLM-as-judge scoring (if judge config provided) --
    judge_scores = {}
    if judge_config and scenario.category == "clinical_reasoning":
        context_str = f"System: {scenario.system_prompt[:200]}...\n\nTool Results:\n{scenario.tool_results[:500]}..."

        for dimension in ["clinical_accuracy", "safety", "completeness"]:
            js = judge_response(
                dimension=dimension,
                rubric=RUBRICS[dimension],
                context=context_str,
                response=content,
                judge_config=judge_config,
            )
            judge_scores[dimension] = {"score": js.score, "reasoning": js.reasoning}
            scores.append(js.score)

    # Compute aggregate score
    overall_score = sum(scores) / len(scores) if scores else 0.0

    return BenchmarkResult(
        name=scenario.id,
        verdict=Verdict.PASS if overall_score >= 0.7 else Verdict.FAIL,
        score=round(overall_score, 3),
        elapsed_ms=resp.elapsed_ms,
        details={
            "checks": checks,
            "judge_scores": judge_scores,
            "response_preview": content[:500],
            "prompt_tokens": resp.prompt_tokens,
            "completion_tokens": resp.completion_tokens,
            "model": resp.model,
        },
    )


def build_suite(config: LLMConfig, judge_config: LLMConfig | None = None) -> BenchmarkSuite:
    """Build clinical reasoning eval suite."""
    s = BenchmarkSuite(
        name="llm_clinical",
        description="LLM clinical reasoning — risk assessment, completeness, accuracy",
    )
    all_scenarios = CLINICAL_REASONING_SCENARIOS + PEDIATRIC_SCENARIOS + SDOH_SCENARIOS

    for scenario in all_scenarios:
        def make_fn(sc):
            return lambda: _eval_clinical(sc, config, judge_config)
        s.add(BenchmarkCase(
            name=scenario.id,
            description=scenario.name,
            category="clinical_reasoning",
            fn=make_fn(scenario),
        ))
    return s
