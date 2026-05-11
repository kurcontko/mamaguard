"""
Benchmark runner — three tiers of evaluation.

Usage:
    # Tier 1 — unit regression (deterministic, mocked FHIR, no LLM)
    python3.11 -m benchmarks.runner

    # Tier 2a — LLM eval with simulated tool output (no real agent)
    python3.11 -m benchmarks.runner --llm

    # Tier 2b — end-to-end real agent vs real HAPI FHIR (the real benchmark)
    python3.11 -m benchmarks.runner --e2e                     # gemini backend
    python3.11 -m benchmarks.runner --e2e --backend vllm      # vllm backend
    python3.11 -m benchmarks.runner --e2e --judge             # + LLM judge

    # Tier 3 — MedAgentBench-style externally comparable methodology
    python3.11 -m benchmarks.runner --medagent --backend vllm

    # Combined
    python3.11 -m benchmarks.runner --e2e --medagent --backend vllm --judge

    # Other flags
    --keep-fhir           don't stop HAPI container after run
    --reset-fhir          wipe and reload FHIR data
    --no-fhir-setup       assume HAPI already running with data loaded
    --suite NAME          run specific suite(s)
    --json                JSON output
    --verbose             show response previews
    --e2e-categories CAT  filter e2e cases to category (maternal, pediatric, sdoh, routing, safety)

Environment:
    BENCH_API_BASE, BENCH_MODEL, BENCH_API_KEY   — vLLM endpoint
    JUDGE_API_BASE, JUDGE_MODEL, JUDGE_API_KEY   — LLM-as-judge (optional)
    GOOGLE_API_KEY                                — required for gemini backend
    HAPI_FHIR_URL, HAPI_CONTAINER_NAME            — HAPI FHIR config
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from benchmarks.base import BenchmarkResult, BenchmarkSuite, Verdict
from benchmarks.clinical_reasoning.bench_ai_factor_comparison import (
    suite as ai_factor_comparison_suite,
)
from benchmarks.clinical_reasoning.bench_baseline_comparison import reasoning_trace_suite
from benchmarks.clinical_reasoning.bench_baseline_comparison import (
    suite as baseline_comparison_suite,
)
from benchmarks.clinical_reasoning.bench_care_plan_synthesis import (
    suite as care_plan_synthesis_suite,
)
from benchmarks.clinical_reasoning.bench_risk_assessment import suite as clinical_suite
from benchmarks.config import CATEGORY_WEIGHTS

# Tier 1 — deterministic unit-regression suites
from benchmarks.fhir_tools.bench_maternal import suite as fhir_maternal_suite
from benchmarks.fhir_tools.bench_pediatric import suite as fhir_pediatric_suite
from benchmarks.fhir_tools.bench_sdoh import suite as fhir_sdoh_suite
from benchmarks.orchestration.bench_routing import suite as orchestration_suite

DETERMINISTIC_SUITES: dict[str, BenchmarkSuite] = {
    "fhir_maternal": fhir_maternal_suite,
    "fhir_pediatric": fhir_pediatric_suite,
    "fhir_sdoh": fhir_sdoh_suite,
    "clinical_reasoning": clinical_suite,
    "reasoning_trace": reasoning_trace_suite,
    "baseline_comparison": baseline_comparison_suite,
    "care_plan_synthesis": care_plan_synthesis_suite,
    "ai_factor_comparison": ai_factor_comparison_suite,
    "orchestration": orchestration_suite,
}


def _build_llm_suites(use_judge: bool = False) -> dict[str, BenchmarkSuite]:
    """Build tier-2a LLM eval suites (no real agent, simulated tool output)."""
    from benchmarks.llm_eval import bench_clinical, bench_routing, bench_safety
    from benchmarks.llm_eval.client import LLMConfig, check_endpoint

    config = LLMConfig.from_env()
    judge_config = LLMConfig.judge_from_env() if use_judge else None

    status = check_endpoint(config)
    if status["status"] != "ok":
        print(f"\n  [!] LLM endpoint check failed: {status.get('error', 'unknown')}")
        print(f"      Endpoint: {config.api_base}\n")
        sys.exit(1)

    available = status.get("models", [])
    if config.model and config.model not in available:
        print(f"\n  [!] Model '{config.model}' not found. Available: {available}\n")
        sys.exit(1)
    if not config.model and available:
        config.model = available[0]
        print(f"  [*] Auto-selected model: {config.model}")

    print(f"  [*] LLM endpoint: {config.api_base} / {config.model}")
    if use_judge:
        print(f"  [*] Judge: {(judge_config.model if judge_config else None) or '(same)'}")
    print()

    return {
        "llm_routing": bench_routing.build_suite(config),
        "llm_clinical": bench_clinical.build_suite(config, judge_config),
        "llm_safety": bench_safety.build_suite(config, judge_config),
    }


def _build_e2e_suites(
    backend: str,
    use_judge: bool,
    e2e_categories: set[str] | None,
    fhir_base_url: str,
) -> dict[str, BenchmarkSuite]:
    """Build tier-2b end-to-end suites (real agent + real HAPI)."""
    from benchmarks.e2e.bench_e2e import build_suite as build_e2e
    from benchmarks.llm_eval.client import LLMConfig

    judge_config = LLMConfig.judge_from_env() if use_judge else None
    return {
        "e2e": build_e2e(
            backend=backend,
            judge_config=judge_config,
            fhir_base_url=fhir_base_url,
            categories=e2e_categories,
        ),
    }


def _build_medagent_suites(
    backend: str,
    use_judge: bool,
    fhir_base_url: str,
    task_types: set[str] | None,
) -> dict[str, BenchmarkSuite]:
    """Build tier-3 MedAgentBench-style suite."""
    from benchmarks.llm_eval.client import LLMConfig
    from benchmarks.medagent.bench_medagent import build_suite as build_ma

    judge_config = LLMConfig.judge_from_env() if use_judge else None
    return {
        "medagent": build_ma(
            backend=backend,
            judge_config=judge_config,
            fhir_base_url=fhir_base_url,
            task_types=task_types,
        ),
    }


def run_suites(
    suite_names: list[str] | None,
    suites: dict[str, BenchmarkSuite],
) -> dict[str, list[BenchmarkResult]]:
    to_run = suites
    if suite_names:
        to_run = {k: v for k, v in suites.items() if k in suite_names}
    return {name: suite.run_all() for name, suite in to_run.items()}


def compute_scores(all_results: dict[str, list[BenchmarkResult]]) -> dict:
    suite_scores = {}
    for suite_name, results in all_results.items():
        if not results:
            continue
        total = len(results)
        passed = sum(1 for r in results if r.verdict == Verdict.PASS)
        failed = sum(1 for r in results if r.verdict == Verdict.FAIL)
        errors = sum(1 for r in results if r.verdict == Verdict.ERROR)
        avg = sum(r.score for r in results) / total if total > 0 else 0
        suite_scores[suite_name] = {
            "total": total, "passed": passed, "failed": failed, "errors": errors,
            "avg_score": round(avg, 3),
            "pass_rate": round(passed / total, 3) if total > 0 else 0,
        }

    category_scores: dict[str, list[float]] = {}
    for suite_name, s in suite_scores.items():
        if suite_name.startswith("e2e"):
            cat = "e2e"
        elif suite_name.startswith("medagent"):
            cat = "medagent"
        elif "fhir" in suite_name:
            cat = "fhir_tools"
        elif (
            suite_name.startswith("llm_clinical")
            or "clinical" in suite_name
            or "reasoning" in suite_name
            or suite_name == "baseline_comparison"
            or suite_name == "care_plan_synthesis"
        ):
            cat = "clinical_reasoning"
        elif "safety" in suite_name:
            cat = "safety"
        elif "orchestration" in suite_name or "routing" in suite_name:
            cat = "orchestration"
        else:
            cat = "other"
        category_scores.setdefault(cat, []).append(s["avg_score"])

    weighted = 0.0
    weight_sum = 0.0
    for cat, cat_scores in category_scores.items():
        w = CATEGORY_WEIGHTS.get(cat, 0.1)
        cat_avg = sum(cat_scores) / len(cat_scores)
        weighted += cat_avg * w
        weight_sum += w

    overall = round(weighted / weight_sum, 3) if weight_sum > 0 else 0
    return {
        "suites": suite_scores,
        "categories": {c: round(sum(v) / len(v), 3) for c, v in category_scores.items()},
        "overall_score": overall,
    }


def print_report(
    all_results: dict[str, list[BenchmarkResult]],
    scores: dict,
    verbose: bool = False,
):
    total_cases = sum(len(r) for r in all_results.values())
    total_passed = sum(s["passed"] for s in scores["suites"].values())
    total_failed = sum(s["failed"] for s in scores["suites"].values())
    total_errors = sum(s["errors"] for s in scores["suites"].values())

    print("\n" + "=" * 72)
    print("  MAMAGUARD BENCHMARK REPORT")
    print("=" * 72)

    for suite_name, results in all_results.items():
        s = scores["suites"].get(suite_name, {})
        print(f"\n--- {suite_name} ({s.get('passed', 0)}/{s.get('total', 0)} passed, "
              f"score: {s.get('avg_score', 0):.1%}) ---")

        for r in results:
            icon = {"PASS": "+", "FAIL": "X", "ERROR": "!", "SKIP": "-"}[r.verdict.value]
            elapsed = f" ({r.elapsed_ms:.0f}ms)" if r.elapsed_ms > 0 else ""
            print(f"  [{icon}] {r.name}: {r.score:.0%}{elapsed}")

            checks = r.details.get("checks", {})
            if r.verdict == Verdict.FAIL:
                failed_bools = {k: v for k, v in checks.items() if isinstance(v, bool) and not v}
                if failed_bools:
                    print(f"      Failed checks: {', '.join(failed_bools.keys())}")

                missed_tools = checks.get("expected_tools_missed") or checks.get("tool_expected")
                if missed_tools and "tool_hit" in checks:
                    print(f"      Tool miss: expected={sorted(checks['tool_expected'])} "
                          f"got={sorted(r.details.get('tools_called', []))}")
                if "forbidden_found" in checks and checks["forbidden_found"]:
                    print(f"      Forbidden: {checks['forbidden_found']}")
                if "answer_must_contain" in checks:
                    missing = [k for k, v in checks["answer_must_contain"].items() if not v]
                    if missing:
                        print(f"      Missing keywords: {missing}")

                judge = r.details.get("judge_scores", {})
                for dim, js in judge.items():
                    print(f"      Judge[{dim}]: {js['score']:.0%} — {js['reasoning'][:80]}")

            if r.verdict == Verdict.ERROR and r.error:
                print(f"      Error: {r.error.splitlines()[0][:160]}")

            if verbose:
                if "response_preview" in r.details:
                    preview = r.details["response_preview"][:200].replace("\n", " ")
                    print(f"      Response: {preview}...")
                if "tools_called" in r.details:
                    print(f"      Tools: {r.details['tools_called']}")

    print(f"\n{'=' * 72}")
    print(f"  SUMMARY: {total_passed}/{total_cases} passed, "
          f"{total_failed} failed, {total_errors} errors")
    print("\n  Category Scores:")
    for cat, cs in scores["categories"].items():
        w = CATEGORY_WEIGHTS.get(cat, 0.1)
        print(f"    {cat:25s} {cs:.1%}  (weight: {w:.0%})")
    print(f"\n  OVERALL SCORE: {scores['overall_score']:.1%}")
    print("=" * 72 + "\n")


# -- HAPI lifecycle -----------------------------------------------------------

def _needs_fhir(args) -> bool:
    return args.e2e or args.medagent or (args.suite and any(
        s.startswith("e2e") or s.startswith("medagent") for s in args.suite
    ))


def _setup_fhir(args):
    """Start HAPI FHIR + load bundles. Returns (server, base_url) or (None, url)."""
    from benchmarks.e2e.fhir_server import HapiFhirServer

    base_url = os.environ.get("HAPI_FHIR_URL", "http://localhost:8090/fhir")

    if args.no_fhir_setup:
        print(f"  [*] --no-fhir-setup: assuming HAPI already running at {base_url}")
        return None, base_url

    server = HapiFhirServer(keep_running=args.keep_fhir)
    print(f"  [*] Starting HAPI FHIR (container: {server.container_name})...")
    server.start()
    if args.reset_fhir:
        print("  [*] --reset-fhir: reloading all bundles")
        server.reset()
    else:
        server.load_all_bundles()
    print(f"  [*] HAPI ready at {server.base_url}")
    return server, server.base_url


def main():
    parser = argparse.ArgumentParser(description="MamaGuard Benchmark Runner")
    parser.add_argument("--suite", type=str, nargs="*",
                        help="Specific suite(s) to run")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show response previews")

    parser.add_argument("--llm", action="store_true",
                        help="Run Tier-2a LLM eval (simulated tool output)")
    parser.add_argument("--e2e", action="store_true",
                        help="Run Tier-2b end-to-end (real agent + real HAPI)")
    parser.add_argument("--medagent", action="store_true",
                        help="Run Tier-3 MedAgentBench-style cases")
    parser.add_argument("--llm-only", action="store_true",
                        help="Skip deterministic unit-regression suites")

    parser.add_argument("--backend", type=str, default="gemini", choices=["gemini", "vllm"],
                        help="Model backend for e2e and medagent (default: gemini)")
    parser.add_argument("--judge", action="store_true", help="Enable LLM-as-judge scoring")

    parser.add_argument("--e2e-categories", type=str, nargs="*",
                        help="Filter e2e cases: maternal pediatric sdoh routing safety")
    parser.add_argument("--medagent-task-types", type=str, nargs="*",
                        help="Filter medagent cases by task type: query action")

    parser.add_argument("--keep-fhir", action="store_true",
                        help="Leave HAPI container running after benchmark")
    parser.add_argument("--reset-fhir", action="store_true",
                        help="Wipe and reload FHIR data on startup")
    parser.add_argument("--no-fhir-setup", action="store_true",
                        help="Skip HAPI setup (assume already running)")

    args = parser.parse_args()

    all_suites: dict[str, BenchmarkSuite] = {}

    # Determine which tiers to run
    any_real = args.e2e or args.medagent
    run_det = not (args.llm_only or (any_real and args.suite is None and not args.llm))
    if args.suite:
        # If user picks specific suites, only those run
        run_det = any(not (s.startswith("llm_") or s.startswith("e2e") or s.startswith("medagent"))
                      for s in args.suite)

    if run_det:
        all_suites.update(DETERMINISTIC_SUITES)

    # Tier 2a
    if args.llm:
        all_suites.update(_build_llm_suites(use_judge=args.judge))

    # Tier 2b + Tier 3 — both need HAPI
    fhir_server = None
    fhir_base_url = os.environ.get("HAPI_FHIR_URL", "http://localhost:8090/fhir")
    if _needs_fhir(args):
        fhir_server, fhir_base_url = _setup_fhir(args)

    if args.e2e:
        e2e_cats = set(args.e2e_categories) if args.e2e_categories else None
        all_suites.update(_build_e2e_suites(
            backend=args.backend,
            use_judge=args.judge,
            e2e_categories=e2e_cats,
            fhir_base_url=fhir_base_url,
        ))

    if args.medagent:
        task_types = set(args.medagent_task_types) if args.medagent_task_types else None
        all_suites.update(_build_medagent_suites(
            backend=args.backend,
            use_judge=args.judge,
            fhir_base_url=fhir_base_url,
            task_types=task_types,
        ))

    try:
        all_results = run_suites(suite_names=args.suite, suites=all_suites)
        scores = compute_scores(all_results)

        if args.json:
            output = {
                "scores": scores,
                "results": {
                    name: [
                        {
                            "name": r.name,
                            "verdict": r.verdict.value,
                            "score": r.score,
                            "elapsed_ms": round(r.elapsed_ms, 1),
                            "details": r.details,
                            "error": r.error,
                        } for r in results
                    ]
                    for name, results in all_results.items()
                },
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            print_report(all_results, scores, verbose=args.verbose)

        total_failed = sum(s["failed"] for s in scores["suites"].values())
        total_errors = sum(s["errors"] for s in scores["suites"].values())
        exit_code = 1 if (total_failed + total_errors) > 0 else 0
    finally:
        if fhir_server is not None:
            fhir_server.stop()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
