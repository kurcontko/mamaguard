"""Tests for session-level tool response caching.

Covers:
- Cache hit: second call returns cached data without FHIR call
- Cache miss: first call hits FHIR and stores result
- Error bypass: failed results are not cached
- Cache invalidation: per-patient and full clear
- Argument sensitivity: different args cache independently
- Cross-tool isolation: different tools cache independently
- Compound tool caching: get_maternal_risk_profile caches sub-results
- No-context passthrough: None tool_context bypasses cache
"""

import unittest
from unittest.mock import patch

import httpx


class MockToolContext:
    """Minimal mock for google.adk.tools.ToolContext."""

    def __init__(self, fhir_url="", fhir_token="", patient_id="", **extra):
        self.state = {
            "fhir_url": fhir_url,
            "fhir_token": fhir_token,
            "patient_id": patient_id,
            **extra,
        }


def _valid_ctx(**overrides):
    defaults = dict(
        fhir_url="https://fhir.example.org",
        fhir_token="test-token",
        patient_id="patient-42",
    )
    defaults.update(overrides)
    return MockToolContext(**defaults)


PATIENT = {
    "resourceType": "Patient",
    "id": "patient-42",
    "name": [{"use": "official", "given": ["Test"], "family": "User"}],
    "birthDate": "2000-01-01",
    "gender": "female",
}

EMPTY_BUNDLE = {"resourceType": "Bundle", "entry": []}


def _fhir_side_effect(fhir_url, token, path, params=None):
    if path.startswith("Patient/"):
        return PATIENT
    return EMPTY_BUNDLE


# ===========================================================================
# Low-level cache functions
# ===========================================================================

class TestCachePrimitives(unittest.TestCase):
    """Test get_cache, put_cache, invalidate_cache directly."""

    def test_get_cache_empty_state(self):
        from mamaguard.shared.tools.cache import get_cache
        self.assertIsNone(get_cache({}, "tool", "p1"))

    def test_put_and_get(self):
        from mamaguard.shared.tools.cache import get_cache, put_cache
        state = {}
        put_cache(state, "get_patient_summary", "p1", {"status": "success", "data": "x"})
        result = get_cache(state, "get_patient_summary", "p1")
        self.assertEqual(result["data"], "x")

    def test_put_skips_error_result(self):
        from mamaguard.shared.tools.cache import get_cache, put_cache
        state = {}
        put_cache(state, "tool", "p1", {"status": "error", "error_message": "fail"})
        self.assertIsNone(get_cache(state, "tool", "p1"))

    def test_different_patients_isolated(self):
        from mamaguard.shared.tools.cache import get_cache, put_cache
        state = {}
        put_cache(state, "tool", "p1", {"status": "success", "v": 1})
        put_cache(state, "tool", "p2", {"status": "success", "v": 2})
        self.assertEqual(get_cache(state, "tool", "p1")["v"], 1)
        self.assertEqual(get_cache(state, "tool", "p2")["v"], 2)

    def test_different_tools_isolated(self):
        from mamaguard.shared.tools.cache import get_cache, put_cache
        state = {}
        put_cache(state, "tool_a", "p1", {"status": "success", "v": "a"})
        put_cache(state, "tool_b", "p1", {"status": "success", "v": "b"})
        self.assertEqual(get_cache(state, "tool_a", "p1")["v"], "a")
        self.assertEqual(get_cache(state, "tool_b", "p1")["v"], "b")

    def test_extra_args_in_key(self):
        from mamaguard.shared.tools.cache import get_cache, put_cache
        state = {}
        put_cache(state, "get_bp_trend", "p1", {"status": "success", "m": 6}, extra_args=(6,))
        put_cache(state, "get_bp_trend", "p1", {"status": "success", "m": 24}, extra_args=(24,))
        self.assertEqual(get_cache(state, "get_bp_trend", "p1", extra_args=(6,))["m"], 6)
        self.assertEqual(get_cache(state, "get_bp_trend", "p1", extra_args=(24,))["m"], 24)
        self.assertIsNone(get_cache(state, "get_bp_trend", "p1", extra_args=(12,)))

    def test_invalidate_all(self):
        from mamaguard.shared.tools.cache import get_cache, invalidate_cache, put_cache
        state = {}
        put_cache(state, "tool_a", "p1", {"status": "success"})
        put_cache(state, "tool_b", "p2", {"status": "success"})
        invalidate_cache(state)
        self.assertIsNone(get_cache(state, "tool_a", "p1"))
        self.assertIsNone(get_cache(state, "tool_b", "p2"))

    def test_invalidate_by_patient(self):
        from mamaguard.shared.tools.cache import get_cache, invalidate_cache, put_cache
        state = {}
        put_cache(state, "tool", "p1", {"status": "success", "v": 1})
        put_cache(state, "tool", "p2", {"status": "success", "v": 2})
        invalidate_cache(state, patient_id="p1")
        self.assertIsNone(get_cache(state, "tool", "p1"))
        self.assertEqual(get_cache(state, "tool", "p2")["v"], 2)

    def test_invalidate_empty_state_no_error(self):
        from mamaguard.shared.tools.cache import invalidate_cache
        invalidate_cache({})
        invalidate_cache({}, patient_id="p1")


# ===========================================================================
# @cached_tool decorator — get_patient_summary
# ===========================================================================

class TestCachedGetPatientSummary(unittest.TestCase):
    """Verify get_patient_summary caches across calls."""

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_cache_hit_skips_fhir(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        mock_fhir_get.side_effect = _fhir_side_effect
        ctx = _valid_ctx()

        # First call — hits FHIR
        r1 = get_patient_summary(ctx)
        self.assertEqual(r1["status"], "success")
        first_call_count = mock_fhir_get.call_count

        # Second call — should use cache, no additional FHIR calls
        r2 = get_patient_summary(ctx)
        self.assertEqual(r2["status"], "success")
        self.assertEqual(mock_fhir_get.call_count, first_call_count)

        # Same result object
        self.assertEqual(r1, r2)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_different_patients_miss_cache(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        mock_fhir_get.side_effect = _fhir_side_effect

        ctx1 = _valid_ctx(patient_id="p1")
        ctx2 = _valid_ctx(patient_id="p2")

        get_patient_summary(ctx1)
        count_after_first = mock_fhir_get.call_count

        get_patient_summary(ctx2)
        # Different patient → cache miss → more FHIR calls
        self.assertGreater(mock_fhir_get.call_count, count_after_first)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_error_result_not_cached(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        mock_fhir_get.side_effect = httpx.ConnectError("down")
        ctx = _valid_ctx()

        r1 = get_patient_summary(ctx)
        self.assertEqual(r1["status"], "error")
        count1 = mock_fhir_get.call_count

        # Second call should try again (not cached)
        r2 = get_patient_summary(ctx)
        self.assertEqual(r2["status"], "error")
        self.assertGreater(mock_fhir_get.call_count, count1)

    def test_none_context_bypasses_cache(self):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        result = get_patient_summary(None)
        self.assertEqual(result["status"], "error")

    def test_missing_patient_id_bypasses_cache(self):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        result = get_patient_summary(MockToolContext())
        self.assertEqual(result["status"], "error")


# ===========================================================================
# @cached_tool decorator — get_active_medications
# ===========================================================================

class TestCachedGetActiveMedications(unittest.TestCase):

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_cache_hit(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = EMPTY_BUNDLE
        ctx = _valid_ctx()

        r1 = get_active_medications(ctx)
        self.assertEqual(r1["status"], "success")
        count1 = mock_fhir_get.call_count

        r2 = get_active_medications(ctx)
        self.assertEqual(r2, r1)
        self.assertEqual(mock_fhir_get.call_count, count1)


# ===========================================================================
# @cached_tool decorator — maternal tools with args
# ===========================================================================

class TestCachedMaternalTools(unittest.TestCase):

    @patch("mamaguard.shared.tools.maternal._safe_fhir_get")
    def test_bp_trend_cached(self, mock_safe):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_safe.return_value = (EMPTY_BUNDLE, None)
        ctx = _valid_ctx()

        r1 = get_bp_trend(months_back=24, tool_context=ctx)
        self.assertEqual(r1["status"], "success")
        count1 = mock_safe.call_count

        r2 = get_bp_trend(months_back=24, tool_context=ctx)
        self.assertEqual(r2, r1)
        self.assertEqual(mock_safe.call_count, count1)

    @patch("mamaguard.shared.tools.maternal._safe_fhir_get")
    def test_bp_trend_different_months_miss(self, mock_safe):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_safe.return_value = (EMPTY_BUNDLE, None)
        ctx = _valid_ctx()

        get_bp_trend(months_back=6, tool_context=ctx)
        count1 = mock_safe.call_count

        get_bp_trend(months_back=24, tool_context=ctx)
        self.assertGreater(mock_safe.call_count, count1)

    @patch("mamaguard.shared.tools.maternal._safe_fhir_get")
    def test_glucose_trend_cached(self, mock_safe):
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_safe.return_value = (EMPTY_BUNDLE, None)
        ctx = _valid_ctx()

        r1 = get_glucose_trend(tool_context=ctx)
        count1 = mock_safe.call_count

        r2 = get_glucose_trend(tool_context=ctx)
        self.assertEqual(r2, r1)
        self.assertEqual(mock_safe.call_count, count1)

    @patch("mamaguard.shared.tools.maternal._safe_fhir_get")
    def test_pregnancy_history_cached(self, mock_safe):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_safe.return_value = (EMPTY_BUNDLE, None)
        ctx = _valid_ctx()

        r1 = get_pregnancy_history(tool_context=ctx)
        count1 = mock_safe.call_count

        r2 = get_pregnancy_history(tool_context=ctx)
        self.assertEqual(r2, r1)
        self.assertEqual(mock_safe.call_count, count1)


# ===========================================================================
# Compound tool — get_maternal_risk_profile caches sub-calls
# ===========================================================================

class TestCachedCompoundTool(unittest.TestCase):
    """get_maternal_risk_profile calls bp_trend, glucose_trend, pregnancy_history.
    After calling the compound tool, individual sub-tool calls should hit cache."""

    @patch("mamaguard.shared.tools.maternal._safe_fhir_get")
    def test_sub_tools_cached_after_compound(self, mock_safe):
        from mamaguard.shared.tools.maternal import (
            get_bp_trend,
            get_glucose_trend,
            get_maternal_risk_profile,
            get_pregnancy_history,
        )

        mock_safe.return_value = (EMPTY_BUNDLE, None)
        ctx = _valid_ctx()

        # Compound call — internally calls all 3 sub-tools
        profile = get_maternal_risk_profile(tool_context=ctx)
        self.assertEqual(profile["status"], "success")
        count_after_compound = mock_safe.call_count

        # Individual calls should all hit cache
        get_bp_trend(months_back=24, tool_context=ctx)
        get_glucose_trend(months_back=24, tool_context=ctx)
        get_pregnancy_history(tool_context=ctx)
        self.assertEqual(mock_safe.call_count, count_after_compound)


# ===========================================================================
# Pediatric tools caching
# ===========================================================================

class TestCachedPediatricTools(unittest.TestCase):

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_care_gaps_cached(self, mock_fhir_get):
        from mamaguard.shared.tools.pediatric import get_care_gaps

        mock_fhir_get.return_value = EMPTY_BUNDLE
        ctx = _valid_ctx()

        r1 = get_care_gaps(tool_context=ctx)
        self.assertEqual(r1["status"], "success")
        count1 = mock_fhir_get.call_count

        r2 = get_care_gaps(tool_context=ctx)
        self.assertEqual(r2, r1)
        self.assertEqual(mock_fhir_get.call_count, count1)


# ===========================================================================
# SDOH screening caching
# ===========================================================================

class TestCachedSdohScreening(unittest.TestCase):

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_sdoh_screening_cached(self, mock_fhir_get):
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        mock_fhir_get.side_effect = _fhir_side_effect
        ctx = _valid_ctx()

        r1 = get_sdoh_screening(tool_context=ctx)
        self.assertEqual(r1["status"], "success")
        count1 = mock_fhir_get.call_count

        r2 = get_sdoh_screening(tool_context=ctx)
        self.assertEqual(r2, r1)
        self.assertEqual(mock_fhir_get.call_count, count1)


# ===========================================================================
# Cross-tool isolation with shared context
# ===========================================================================

class TestCrossTool(unittest.TestCase):
    """Different tools on same patient have separate cache entries."""

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_summary_and_medications_independent(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import (
            get_active_medications,
            get_patient_summary,
        )

        mock_fhir_get.side_effect = _fhir_side_effect
        ctx = _valid_ctx()

        r_summary = get_patient_summary(ctx)
        r_meds = get_active_medications(ctx)

        # Both succeed independently
        self.assertEqual(r_summary["status"], "success")
        self.assertEqual(r_meds["status"], "success")

        # Results are different (different tool names, different data)
        self.assertIn("name", r_summary)
        self.assertIn("count", r_meds)


# ===========================================================================
# Cache invalidation with decorator
# ===========================================================================

class TestCacheInvalidationWithDecorator(unittest.TestCase):

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_invalidate_forces_re_fetch(self, mock_fhir_get):
        from mamaguard.shared.tools.cache import invalidate_cache
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        mock_fhir_get.side_effect = _fhir_side_effect
        ctx = _valid_ctx()

        # First call populates cache
        get_patient_summary(ctx)
        count1 = mock_fhir_get.call_count

        # Invalidate
        invalidate_cache(ctx.state, patient_id="patient-42")

        # Should re-fetch
        get_patient_summary(ctx)
        self.assertGreater(mock_fhir_get.call_count, count1)


# ===========================================================================
# Shared state across sub-agents (simulated comprehensive assessment)
# ===========================================================================

class TestComprehensiveAssessmentCaching(unittest.TestCase):
    """Simulates orchestrator calling maternal + sdoh sub-agents sequentially.
    Both call get_patient_summary — second should hit cache."""

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_shared_state_caches_across_agents(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        mock_fhir_get.side_effect = _fhir_side_effect

        # Same state dict shared across sub-agents (as in ADK AgentTool)
        shared_state = {
            "fhir_url": "https://fhir.example.org",
            "fhir_token": "test-token",
            "patient_id": "patient-42",
        }

        # "Maternal agent" calls get_patient_summary
        ctx_maternal = MockToolContext()
        ctx_maternal.state = shared_state
        r1 = get_patient_summary(ctx_maternal)
        count1 = mock_fhir_get.call_count

        # "SDOH agent" calls get_patient_summary with same state
        ctx_sdoh = MockToolContext()
        ctx_sdoh.state = shared_state
        r2 = get_patient_summary(ctx_sdoh)

        # No additional FHIR calls
        self.assertEqual(mock_fhir_get.call_count, count1)
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
