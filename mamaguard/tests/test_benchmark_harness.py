"""Dedicated unit tests for the benchmark harness infrastructure.

Covers:
- benchmarks/base.py: Verdict, BenchmarkResult, BenchmarkCase, BenchmarkSuite, MockToolContext
- benchmarks/config.py: clinical thresholds, CATEGORY_WEIGHTS
- benchmarks/runner.py: run_suites, compute_scores, print_report, _needs_fhir
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import unittest

from benchmarks.base import (
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkSuite,
    MockToolContext,
    Verdict,
)
from benchmarks.config import (
    BP_ELEVATED_DIASTOLIC,
    BP_ELEVATED_SYSTOLIC,
    BP_SEVERE_DIASTOLIC,
    BP_SEVERE_SYSTOLIC,
    CATEGORY_WEIGHTS,
    HBA1C_DIABETES,
    HBA1C_POORLY_CONTROLLED,
    PREGNANCY_LOSS_HIGH_RISK,
)
from benchmarks.runner import (
    _needs_fhir,
    compute_scores,
    print_report,
    run_suites,
)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

class TestVerdict(unittest.TestCase):
    def test_values(self):
        self.assertEqual(Verdict.PASS.value, "PASS")
        self.assertEqual(Verdict.FAIL.value, "FAIL")
        self.assertEqual(Verdict.ERROR.value, "ERROR")
        self.assertEqual(Verdict.SKIP.value, "SKIP")

    def test_member_count(self):
        self.assertEqual(len(Verdict), 4)

    def test_identity(self):
        self.assertIs(Verdict("PASS"), Verdict.PASS)


# ---------------------------------------------------------------------------
# BenchmarkResult
# ---------------------------------------------------------------------------

class TestBenchmarkResult(unittest.TestCase):
    def test_defaults(self):
        r = BenchmarkResult(name="t", verdict=Verdict.PASS, score=1.0)
        self.assertEqual(r.elapsed_ms, 0.0)
        self.assertEqual(r.details, {})
        self.assertIsNone(r.error)

    def test_custom_fields(self):
        r = BenchmarkResult(
            name="t", verdict=Verdict.FAIL, score=0.5,
            elapsed_ms=42.0, details={"k": "v"}, error="oops",
        )
        self.assertEqual(r.elapsed_ms, 42.0)
        self.assertEqual(r.details["k"], "v")
        self.assertEqual(r.error, "oops")


# ---------------------------------------------------------------------------
# BenchmarkCase
# ---------------------------------------------------------------------------

class TestBenchmarkCaseSkip(unittest.TestCase):
    """fn=None -> SKIP."""

    def test_skip_verdict(self):
        c = BenchmarkCase(name="skipped", description="d", category="cat")
        r = c.run()
        self.assertEqual(r.verdict, Verdict.SKIP)
        self.assertEqual(r.score, 0.0)
        self.assertIn("reason", r.details)

    def test_skip_elapsed_is_zero(self):
        c = BenchmarkCase(name="s", description="d", category="c")
        r = c.run()
        self.assertEqual(r.elapsed_ms, 0.0)


class TestBenchmarkCasePass(unittest.TestCase):
    """fn returns normally -> result + elapsed."""

    def test_pass_result(self):
        def ok():
            return BenchmarkResult(name="ok", verdict=Verdict.PASS, score=1.0)

        c = BenchmarkCase(name="ok", description="d", category="c", fn=ok)
        r = c.run()
        self.assertEqual(r.verdict, Verdict.PASS)
        self.assertEqual(r.score, 1.0)

    def test_elapsed_is_set(self):
        def slow():
            time.sleep(0.01)
            return BenchmarkResult(name="slow", verdict=Verdict.PASS, score=1.0)

        c = BenchmarkCase(name="slow", description="d", category="c", fn=slow)
        r = c.run()
        self.assertGreater(r.elapsed_ms, 5)

    def test_fn_elapsed_overwrites_result_elapsed(self):
        """run() overwrites whatever elapsed_ms the fn returns."""
        def preset():
            return BenchmarkResult(
                name="p", verdict=Verdict.PASS, score=1.0, elapsed_ms=999,
            )

        c = BenchmarkCase(name="p", description="d", category="c", fn=preset)
        r = c.run()
        self.assertNotEqual(r.elapsed_ms, 999)
        self.assertGreaterEqual(r.elapsed_ms, 0.0)


class TestBenchmarkCaseError(unittest.TestCase):
    """fn raises -> ERROR with traceback."""

    def test_error_verdict(self):
        def boom():
            raise ValueError("broken")

        c = BenchmarkCase(name="boom", description="d", category="c", fn=boom)
        r = c.run()
        self.assertEqual(r.verdict, Verdict.ERROR)
        self.assertEqual(r.score, 0.0)
        self.assertIn("ValueError: broken", r.error)

    def test_error_has_traceback(self):
        def boom():
            raise RuntimeError("trace me")

        c = BenchmarkCase(name="b", description="d", category="c", fn=boom)
        r = c.run()
        self.assertIn("Traceback", r.error)

    def test_error_elapsed_nonzero(self):
        def boom():
            raise Exception("x")

        c = BenchmarkCase(name="b", description="d", category="c", fn=boom)
        r = c.run()
        self.assertGreaterEqual(r.elapsed_ms, 0.0)


# ---------------------------------------------------------------------------
# BenchmarkSuite
# ---------------------------------------------------------------------------

class TestBenchmarkSuiteBasic(unittest.TestCase):
    def test_init(self):
        s = BenchmarkSuite(name="s", description="d")
        self.assertEqual(s.name, "s")
        self.assertEqual(s.description, "d")
        self.assertEqual(s.cases, [])

    def test_add(self):
        s = BenchmarkSuite(name="s", description="d")
        c = BenchmarkCase(name="c", description="d", category="cat")
        s.add(c)
        self.assertEqual(len(s.cases), 1)
        self.assertIs(s.cases[0], c)

    def test_add_multiple(self):
        s = BenchmarkSuite(name="s", description="d")
        for i in range(5):
            s.add(BenchmarkCase(name=f"c{i}", description="d", category="cat"))
        self.assertEqual(len(s.cases), 5)


class TestBenchmarkSuiteDecorator(unittest.TestCase):
    def test_decorator_registers(self):
        s = BenchmarkSuite(name="s", description="d")

        @s.case("test1", description="desc1", category="cat1")
        def fn():
            return BenchmarkResult(name="test1", verdict=Verdict.PASS, score=1.0)

        self.assertEqual(len(s.cases), 1)
        self.assertEqual(s.cases[0].name, "test1")
        self.assertEqual(s.cases[0].description, "desc1")
        self.assertEqual(s.cases[0].category, "cat1")
        self.assertIs(s.cases[0].fn, fn)

    def test_decorator_default_description(self):
        s = BenchmarkSuite(name="s", description="d")

        @s.case("test2")
        def fn():
            return BenchmarkResult(name="test2", verdict=Verdict.PASS, score=1.0)

        self.assertEqual(s.cases[0].description, "test2")

    def test_decorator_default_category(self):
        s = BenchmarkSuite(name="mycat", description="d")

        @s.case("test3")
        def fn():
            return BenchmarkResult(name="test3", verdict=Verdict.PASS, score=1.0)

        self.assertEqual(s.cases[0].category, "mycat")


class TestBenchmarkSuiteRunAll(unittest.TestCase):
    def test_run_all_empty(self):
        s = BenchmarkSuite(name="s", description="d")
        self.assertEqual(s.run_all(), [])

    def test_run_all_collects_results(self):
        s = BenchmarkSuite(name="s", description="d")

        def pass_fn():
            return BenchmarkResult(name="p", verdict=Verdict.PASS, score=1.0)

        def fail_fn():
            return BenchmarkResult(name="f", verdict=Verdict.FAIL, score=0.0)

        s.add(BenchmarkCase(name="p", description="d", category="c", fn=pass_fn))
        s.add(BenchmarkCase(name="f", description="d", category="c", fn=fail_fn))

        results = s.run_all()
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].verdict, Verdict.PASS)
        self.assertEqual(results[1].verdict, Verdict.FAIL)

    def test_run_all_with_error(self):
        s = BenchmarkSuite(name="s", description="d")

        def boom():
            raise Exception("x")

        s.add(BenchmarkCase(name="b", description="d", category="c", fn=boom))
        results = s.run_all()
        self.assertEqual(results[0].verdict, Verdict.ERROR)

    def test_run_all_with_skip(self):
        s = BenchmarkSuite(name="s", description="d")
        s.add(BenchmarkCase(name="sk", description="d", category="c"))
        results = s.run_all()
        self.assertEqual(results[0].verdict, Verdict.SKIP)


# ---------------------------------------------------------------------------
# MockToolContext
# ---------------------------------------------------------------------------

class TestMockToolContext(unittest.TestCase):
    def test_defaults(self):
        ctx = MockToolContext()
        self.assertEqual(ctx.state["fhir_url"], "https://fhir.example.org")
        self.assertEqual(ctx.state["fhir_token"], "bench-token")
        self.assertEqual(ctx.state["patient_id"], "bench-patient-1")

    def test_custom(self):
        ctx = MockToolContext(
            fhir_url="https://custom.fhir", fhir_token="tok", patient_id="p1",
        )
        self.assertEqual(ctx.state["fhir_url"], "https://custom.fhir")
        self.assertEqual(ctx.state["fhir_token"], "tok")
        self.assertEqual(ctx.state["patient_id"], "p1")

    def test_state_is_dict(self):
        ctx = MockToolContext()
        self.assertIsInstance(ctx.state, dict)
        self.assertEqual(len(ctx.state), 3)


# ---------------------------------------------------------------------------
# config.py — clinical thresholds
# ---------------------------------------------------------------------------

class TestClinicalThresholds(unittest.TestCase):
    def test_bp_elevated_systolic(self):
        self.assertEqual(BP_ELEVATED_SYSTOLIC, 140)

    def test_bp_elevated_diastolic(self):
        self.assertEqual(BP_ELEVATED_DIASTOLIC, 90)

    def test_bp_severe_systolic(self):
        self.assertEqual(BP_SEVERE_SYSTOLIC, 160)

    def test_bp_severe_diastolic(self):
        self.assertEqual(BP_SEVERE_DIASTOLIC, 110)

    def test_hba1c_diabetes(self):
        self.assertAlmostEqual(HBA1C_DIABETES, 6.5)

    def test_hba1c_poorly_controlled(self):
        self.assertAlmostEqual(HBA1C_POORLY_CONTROLLED, 9.0)

    def test_pregnancy_loss_high_risk(self):
        self.assertEqual(PREGNANCY_LOSS_HIGH_RISK, 2)

    def test_severe_exceeds_elevated(self):
        self.assertGreater(BP_SEVERE_SYSTOLIC, BP_ELEVATED_SYSTOLIC)
        self.assertGreater(BP_SEVERE_DIASTOLIC, BP_ELEVATED_DIASTOLIC)

    def test_poorly_controlled_exceeds_diabetes(self):
        self.assertGreater(HBA1C_POORLY_CONTROLLED, HBA1C_DIABETES)


class TestCategoryWeights(unittest.TestCase):
    def test_known_categories(self):
        expected = {"e2e", "medagent", "safety", "fhir_tools",
                    "clinical_reasoning", "orchestration", "other"}
        self.assertEqual(set(CATEGORY_WEIGHTS.keys()), expected)

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(CATEGORY_WEIGHTS.values()), 1.0, places=6)

    def test_all_positive(self):
        for cat, w in CATEGORY_WEIGHTS.items():
            self.assertGreater(w, 0.0, f"Weight for {cat} should be > 0")

    def test_e2e_highest(self):
        """e2e should dominate scoring."""
        self.assertEqual(max(CATEGORY_WEIGHTS, key=CATEGORY_WEIGHTS.get), "e2e")


# ---------------------------------------------------------------------------
# runner.py — run_suites
# ---------------------------------------------------------------------------

def _make_suite(name: str, results: list[BenchmarkResult]) -> BenchmarkSuite:
    """Helper: build a suite that returns pre-built results."""
    s = BenchmarkSuite(name=name, description=f"test {name}")
    for r in results:
        def fn(res=r):
            return res
        s.add(BenchmarkCase(name=r.name, description=r.name, category=name, fn=fn))
    return s


class TestRunSuites(unittest.TestCase):
    def test_run_all_suites(self):
        s1 = _make_suite("a", [BenchmarkResult(name="a1", verdict=Verdict.PASS, score=1.0)])
        s2 = _make_suite("b", [BenchmarkResult(name="b1", verdict=Verdict.FAIL, score=0.0)])
        results = run_suites(None, {"a": s1, "b": s2})
        self.assertIn("a", results)
        self.assertIn("b", results)

    def test_filter_by_name(self):
        s1 = _make_suite("a", [BenchmarkResult(name="a1", verdict=Verdict.PASS, score=1.0)])
        s2 = _make_suite("b", [BenchmarkResult(name="b1", verdict=Verdict.FAIL, score=0.0)])
        results = run_suites(["a"], {"a": s1, "b": s2})
        self.assertIn("a", results)
        self.assertNotIn("b", results)

    def test_filter_nonexistent(self):
        s1 = _make_suite("a", [BenchmarkResult(name="a1", verdict=Verdict.PASS, score=1.0)])
        results = run_suites(["nonexistent"], {"a": s1})
        self.assertEqual(results, {})

    def test_empty_suites(self):
        results = run_suites(None, {})
        self.assertEqual(results, {})

    def test_empty_suite_cases(self):
        s = BenchmarkSuite(name="empty", description="d")
        results = run_suites(None, {"empty": s})
        self.assertEqual(results["empty"], [])


# ---------------------------------------------------------------------------
# runner.py — compute_scores
# ---------------------------------------------------------------------------

class TestComputeScoresBasic(unittest.TestCase):
    def test_empty(self):
        scores = compute_scores({})
        self.assertEqual(scores["suites"], {})
        self.assertEqual(scores["categories"], {})
        self.assertEqual(scores["overall_score"], 0)

    def test_single_pass(self):
        results = {"test_suite": [
            BenchmarkResult(name="t", verdict=Verdict.PASS, score=1.0),
        ]}
        scores = compute_scores(results)
        self.assertEqual(scores["suites"]["test_suite"]["total"], 1)
        self.assertEqual(scores["suites"]["test_suite"]["passed"], 1)
        self.assertEqual(scores["suites"]["test_suite"]["failed"], 0)
        self.assertEqual(scores["suites"]["test_suite"]["errors"], 0)
        self.assertEqual(scores["suites"]["test_suite"]["avg_score"], 1.0)
        self.assertEqual(scores["suites"]["test_suite"]["pass_rate"], 1.0)

    def test_single_fail(self):
        results = {"test_suite": [
            BenchmarkResult(name="t", verdict=Verdict.FAIL, score=0.0),
        ]}
        scores = compute_scores(results)
        self.assertEqual(scores["suites"]["test_suite"]["passed"], 0)
        self.assertEqual(scores["suites"]["test_suite"]["failed"], 1)
        self.assertEqual(scores["suites"]["test_suite"]["pass_rate"], 0.0)

    def test_single_error(self):
        results = {"test_suite": [
            BenchmarkResult(name="t", verdict=Verdict.ERROR, score=0.0),
        ]}
        scores = compute_scores(results)
        self.assertEqual(scores["suites"]["test_suite"]["errors"], 1)

    def test_mixed_verdicts(self):
        results = {"s": [
            BenchmarkResult(name="p", verdict=Verdict.PASS, score=1.0),
            BenchmarkResult(name="f", verdict=Verdict.FAIL, score=0.0),
            BenchmarkResult(name="e", verdict=Verdict.ERROR, score=0.0),
            BenchmarkResult(name="sk", verdict=Verdict.SKIP, score=0.0),
        ]}
        scores = compute_scores(results)
        s = scores["suites"]["s"]
        self.assertEqual(s["total"], 4)
        self.assertEqual(s["passed"], 1)
        self.assertEqual(s["failed"], 1)
        self.assertEqual(s["errors"], 1)
        self.assertAlmostEqual(s["avg_score"], 0.25)
        self.assertAlmostEqual(s["pass_rate"], 0.25)


class TestComputeScoresEmpty(unittest.TestCase):
    def test_empty_result_list_skipped(self):
        """Suites with no results are excluded from scoring."""
        results = {"s": []}
        scores = compute_scores(results)
        self.assertNotIn("s", scores["suites"])

    def test_partial_scores(self):
        results = {"s": [
            BenchmarkResult(name="a", verdict=Verdict.PASS, score=0.8),
            BenchmarkResult(name="b", verdict=Verdict.PASS, score=0.6),
        ]}
        scores = compute_scores(results)
        self.assertAlmostEqual(scores["suites"]["s"]["avg_score"], 0.7)


class TestComputeScoresCategoryClassification(unittest.TestCase):
    """Verify the suite name -> category mapping in compute_scores."""

    def _score_category(self, suite_name: str) -> str:
        results = {suite_name: [
            BenchmarkResult(name="t", verdict=Verdict.PASS, score=1.0),
        ]}
        scores = compute_scores(results)
        cats = list(scores["categories"].keys())
        self.assertEqual(len(cats), 1)
        return cats[0]

    def test_e2e_prefix(self):
        self.assertEqual(self._score_category("e2e"), "e2e")

    def test_e2e_with_suffix(self):
        self.assertEqual(self._score_category("e2e_maternal"), "e2e")

    def test_medagent_prefix(self):
        self.assertEqual(self._score_category("medagent"), "medagent")

    def test_medagent_with_suffix(self):
        self.assertEqual(self._score_category("medagent_query"), "medagent")

    def test_fhir_in_name(self):
        self.assertEqual(self._score_category("fhir_maternal"), "fhir_tools")

    def test_fhir_substring(self):
        self.assertEqual(self._score_category("some_fhir_suite"), "fhir_tools")

    def test_clinical_in_name(self):
        self.assertEqual(self._score_category("clinical_reasoning"), "clinical_reasoning")

    def test_llm_clinical_prefix(self):
        self.assertEqual(self._score_category("llm_clinical"), "clinical_reasoning")

    def test_reasoning_in_name(self):
        self.assertEqual(self._score_category("reasoning_trace"), "clinical_reasoning")

    def test_baseline_comparison(self):
        self.assertEqual(self._score_category("baseline_comparison"), "clinical_reasoning")

    def test_safety_in_name(self):
        self.assertEqual(self._score_category("llm_safety"), "safety")

    def test_orchestration_in_name(self):
        self.assertEqual(self._score_category("orchestration"), "orchestration")

    def test_routing_in_name(self):
        self.assertEqual(self._score_category("llm_routing"), "orchestration")

    def test_unknown_name(self):
        self.assertEqual(self._score_category("something_else"), "other")


class TestComputeScoresWeighting(unittest.TestCase):
    def test_single_category_overall(self):
        """One category: overall = that category's average regardless of weight."""
        results = {"e2e": [
            BenchmarkResult(name="t", verdict=Verdict.PASS, score=0.8),
        ]}
        scores = compute_scores(results)
        self.assertAlmostEqual(scores["overall_score"], 0.8)

    def test_two_categories_weighted(self):
        """Two categories: overall is weight-averaged."""
        results = {
            "e2e": [BenchmarkResult(name="e", verdict=Verdict.PASS, score=1.0)],
            "orchestration": [BenchmarkResult(name="o", verdict=Verdict.PASS, score=0.0)],
        }
        scores = compute_scores(results)
        # e2e weight=0.40, orchestration weight=0.05
        # weighted = 1.0*0.40 + 0.0*0.05 = 0.40
        # weight_sum = 0.40 + 0.05 = 0.45
        # overall = 0.40 / 0.45 = 0.889
        self.assertAlmostEqual(scores["overall_score"], 0.889, places=3)

    def test_unknown_category_gets_default_weight(self):
        """Unknown category gets weight 0.1."""
        results = {
            "weird_name": [
                BenchmarkResult(name="w", verdict=Verdict.PASS, score=1.0),
            ],
        }
        scores = compute_scores(results)
        self.assertEqual(scores["categories"]["other"], 1.0)
        self.assertAlmostEqual(scores["overall_score"], 1.0)

    def test_multiple_suites_same_category(self):
        """Two suites mapping to the same category get averaged."""
        results = {
            "fhir_maternal": [
                BenchmarkResult(name="m", verdict=Verdict.PASS, score=1.0),
            ],
            "fhir_pediatric": [
                BenchmarkResult(name="p", verdict=Verdict.PASS, score=0.5),
            ],
        }
        scores = compute_scores(results)
        # Both map to fhir_tools; category avg = (1.0 + 0.5) / 2 = 0.75
        self.assertAlmostEqual(scores["categories"]["fhir_tools"], 0.75)


class TestComputeScoresRounding(unittest.TestCase):
    def test_avg_score_rounded(self):
        results = {"s": [
            BenchmarkResult(name="a", verdict=Verdict.PASS, score=1.0),
            BenchmarkResult(name="b", verdict=Verdict.PASS, score=1.0),
            BenchmarkResult(name="c", verdict=Verdict.FAIL, score=0.0),
        ]}
        scores = compute_scores(results)
        self.assertEqual(scores["suites"]["s"]["avg_score"], 0.667)

    def test_pass_rate_rounded(self):
        results = {"s": [
            BenchmarkResult(name="a", verdict=Verdict.PASS, score=1.0),
            BenchmarkResult(name="b", verdict=Verdict.PASS, score=1.0),
            BenchmarkResult(name="c", verdict=Verdict.FAIL, score=0.0),
        ]}
        scores = compute_scores(results)
        self.assertEqual(scores["suites"]["s"]["pass_rate"], 0.667)


# ---------------------------------------------------------------------------
# runner.py — _needs_fhir
# ---------------------------------------------------------------------------

def _make_args(**kwargs) -> argparse.Namespace:
    """Build a minimal args namespace for _needs_fhir."""
    defaults = {"e2e": False, "medagent": False, "suite": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestNeedsFhir(unittest.TestCase):
    def test_no_flags(self):
        self.assertFalse(_needs_fhir(_make_args()))

    def test_e2e_flag(self):
        self.assertTrue(_needs_fhir(_make_args(e2e=True)))

    def test_medagent_flag(self):
        self.assertTrue(_needs_fhir(_make_args(medagent=True)))

    def test_both_flags(self):
        self.assertTrue(_needs_fhir(_make_args(e2e=True, medagent=True)))

    def test_suite_with_e2e(self):
        self.assertTrue(_needs_fhir(_make_args(suite=["e2e"])))

    def test_suite_with_e2e_prefix(self):
        self.assertTrue(_needs_fhir(_make_args(suite=["e2e_maternal"])))

    def test_suite_with_medagent(self):
        self.assertTrue(_needs_fhir(_make_args(suite=["medagent"])))

    def test_suite_with_medagent_prefix(self):
        self.assertTrue(_needs_fhir(_make_args(suite=["medagent_query"])))

    def test_suite_non_fhir(self):
        self.assertFalse(_needs_fhir(_make_args(suite=["fhir_maternal"])))

    def test_suite_mixed(self):
        """One FHIR suite triggers need."""
        self.assertTrue(_needs_fhir(_make_args(suite=["fhir_maternal", "e2e"])))

    def test_suite_empty_list(self):
        self.assertFalse(_needs_fhir(_make_args(suite=[])))


# ---------------------------------------------------------------------------
# runner.py — print_report
# ---------------------------------------------------------------------------

class TestPrintReport(unittest.TestCase):
    def _capture_report(self, all_results, scores, verbose=False):
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            print_report(all_results, scores, verbose=verbose)
        finally:
            sys.stdout = old_stdout
        return buf.getvalue()

    def test_header(self):
        results = {"s": [BenchmarkResult(name="t", verdict=Verdict.PASS, score=1.0)]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("MAMAGUARD BENCHMARK REPORT", out)

    def test_summary_counts(self):
        results = {"s": [
            BenchmarkResult(name="p", verdict=Verdict.PASS, score=1.0),
            BenchmarkResult(name="f", verdict=Verdict.FAIL, score=0.0),
        ]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("1/2 passed", out)
        self.assertIn("1 failed", out)

    def test_pass_icon(self):
        results = {"s": [BenchmarkResult(name="mytest", verdict=Verdict.PASS, score=1.0)]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("[+] mytest", out)

    def test_fail_icon(self):
        results = {"s": [BenchmarkResult(name="mytest", verdict=Verdict.FAIL, score=0.0)]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("[X] mytest", out)

    def test_error_icon(self):
        results = {"s": [BenchmarkResult(
            name="mytest", verdict=Verdict.ERROR, score=0.0, error="boom\nline2",
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("[!] mytest", out)
        self.assertIn("Error: boom", out)

    def test_skip_icon(self):
        results = {"s": [BenchmarkResult(name="mytest", verdict=Verdict.SKIP, score=0.0)]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("[-] mytest", out)

    def test_elapsed_shown(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.PASS, score=1.0, elapsed_ms=123.4,
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("123ms", out)

    def test_elapsed_hidden_when_zero(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.PASS, score=1.0, elapsed_ms=0.0,
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertNotIn("0ms", out)

    def test_overall_score_shown(self):
        results = {"s": [BenchmarkResult(name="t", verdict=Verdict.PASS, score=1.0)]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("OVERALL SCORE:", out)

    def test_failed_checks_shown(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.FAIL, score=0.0,
            details={"checks": {"good_check": True, "bad_check": False}},
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("Failed checks: bad_check", out)

    def test_verbose_response_preview(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.PASS, score=1.0,
            details={"response_preview": "hello world preview text"},
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores, verbose=True)
        self.assertIn("hello world preview text", out)

    def test_verbose_tools_called(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.PASS, score=1.0,
            details={"tools_called": ["tool_a", "tool_b"]},
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores, verbose=True)
        self.assertIn("tool_a", out)

    def test_non_verbose_hides_preview(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.PASS, score=1.0,
            details={"response_preview": "should not appear"},
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores, verbose=False)
        self.assertNotIn("should not appear", out)

    def test_category_scores_shown(self):
        results = {"e2e": [BenchmarkResult(name="t", verdict=Verdict.PASS, score=1.0)]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("Category Scores:", out)
        self.assertIn("e2e", out)

    def test_fail_missing_keywords(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.FAIL, score=0.0,
            details={"checks": {"answer_must_contain": {"vital": True, "dose": False}}},
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("Missing keywords: ['dose']", out)

    def test_fail_forbidden_found(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.FAIL, score=0.0,
            details={"checks": {"forbidden_found": ["bad_word"]}},
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("Forbidden: ['bad_word']", out)

    def test_fail_tool_miss(self):
        results = {"s": [BenchmarkResult(
            name="t", verdict=Verdict.FAIL, score=0.0,
            details={
                "checks": {"expected_tools_missed": True, "tool_expected": {"get_bp_trend"}, "tool_hit": False},
                "tools_called": ["wrong_tool"],
            },
        )]}
        scores = compute_scores(results)
        out = self._capture_report(results, scores)
        self.assertIn("Tool miss:", out)


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------

class TestEndToEndPipeline(unittest.TestCase):
    """Smoke test: build suites -> run -> score -> report."""

    def test_full_pipeline(self):
        s = BenchmarkSuite(name="e2e_smoke", description="smoke test")

        @s.case("case1", category="e2e")
        def c1():
            return BenchmarkResult(name="case1", verdict=Verdict.PASS, score=1.0)

        @s.case("case2", category="e2e")
        def c2():
            return BenchmarkResult(name="case2", verdict=Verdict.FAIL, score=0.5)

        results = run_suites(None, {"e2e_smoke": s})
        scores = compute_scores(results)

        self.assertEqual(scores["suites"]["e2e_smoke"]["total"], 2)
        self.assertEqual(scores["suites"]["e2e_smoke"]["passed"], 1)
        self.assertEqual(scores["suites"]["e2e_smoke"]["failed"], 1)
        self.assertAlmostEqual(scores["suites"]["e2e_smoke"]["avg_score"], 0.75)

        # Report should not raise
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            print_report(results, scores)
        finally:
            sys.stdout = old_stdout
        output = buf.getvalue()
        self.assertIn("OVERALL SCORE:", output)

    def test_all_verdicts_pipeline(self):
        s = BenchmarkSuite(name="fhir_test", description="all verdicts")

        @s.case("pass_case")
        def p():
            return BenchmarkResult(name="pass_case", verdict=Verdict.PASS, score=1.0)

        @s.case("fail_case")
        def f():
            return BenchmarkResult(name="fail_case", verdict=Verdict.FAIL, score=0.0)

        @s.case("error_case")
        def e():
            raise RuntimeError("kaboom")

        s.add(BenchmarkCase(name="skip_case", description="d", category="fhir_test"))

        results = run_suites(None, {"fhir_test": s})
        scores = compute_scores(results)

        self.assertEqual(scores["suites"]["fhir_test"]["total"], 4)
        self.assertEqual(scores["suites"]["fhir_test"]["passed"], 1)
        self.assertEqual(scores["suites"]["fhir_test"]["failed"], 1)
        self.assertEqual(scores["suites"]["fhir_test"]["errors"], 1)
        self.assertAlmostEqual(scores["suites"]["fhir_test"]["avg_score"], 0.25)


if __name__ == "__main__":
    unittest.main()
