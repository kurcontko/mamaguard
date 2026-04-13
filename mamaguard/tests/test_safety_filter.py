"""
Unit tests for the post-processing safety filter (after_model_callback).

Covers:
  - Prescribing-language detection and redaction
  - Reporting-existing-medication exemption
  - ADK callback integration (LlmResponse mutation)
  - Feature-flag (enabled/disabled/unset)
  - Edge cases (empty, no text parts, function-call-only responses)
  - Agent wiring verification (all 4 agents have after_model_callback)
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from mamaguard.shared.safety_filter import (
    REDACTION_PHRASE,
    _is_reporting_existing,
    filter_prescribing_language,
    safety_after_model_callback,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(text: str) -> LlmResponse:
    """Build a minimal LlmResponse with a single text part."""
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=text)],
        ),
    )


def _make_multi_part_response(*texts: str) -> LlmResponse:
    """Build an LlmResponse with multiple text parts."""
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=t) for t in texts],
        ),
    )


def _make_function_call_response(name: str, args: dict) -> LlmResponse:
    """Build an LlmResponse with a function call (no text)."""
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part.from_function_call(name=name, args=args)],
        ),
    )


def _ctx() -> SimpleNamespace:
    """Minimal callback context."""
    return SimpleNamespace(state={})


# ===========================================================================
# 1. filter_prescribing_language — detection
# ===========================================================================

class TestFilterDetection(unittest.TestCase):
    """Prescribing language patterns are correctly detected."""

    def test_direct_prescribe_with_dosage(self):
        text = "Initiate labetalol 200mg IV immediately."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)
        self.assertIn(REDACTION_PHRASE, filtered)

    def test_start_patient_on(self):
        text = "We should start the patient on magnesium sulfate."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_start_her_on(self):
        text = "Start her on nifedipine for blood pressure control."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_initiate_treatment_with(self):
        text = "Initiate treatment with hydralazine for severe hypertension."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_initiate_antihypertensive(self):
        text = "Initiate antihypertensive therapy as soon as possible."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_begin_therapy(self):
        text = "Begin magnesium therapy to prevent seizures."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_i_prescribe(self):
        text = "I prescribe labetalol for this patient."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_i_am_prescribing(self):
        text = "I am prescribing metformin 500mg twice daily."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_i_will_prescribe(self):
        text = "I will prescribe insulin based on these glucose readings."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_administer_dose(self):
        text = "Administer 10 mg hydralazine IV push."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_give_dosage(self):
        text = "Give 4g magnesium sulfate IV over 20 minutes."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_initiate_iv(self):
        text = "Initiate IV access and prepare for magnesium administration."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)

    def test_dose_bolus(self):
        text = "Bolus 500 mL normal saline."
        _, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)


# ===========================================================================
# 2. filter_prescribing_language — safe passages (no false positives)
# ===========================================================================

class TestFilterSafePassages(unittest.TestCase):
    """Non-prescribing language is NOT redacted."""

    def test_clinical_observation(self):
        text = "Blood pressure is 184/118 mmHg, indicating severe hypertension."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])
        self.assertEqual(filtered, text)

    def test_risk_assessment(self):
        text = "Risk Level: URGENT. Clinician review required immediately."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_clinician_deferral(self):
        text = "The treating clinician should evaluate for preeclampsia and determine appropriate treatment."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_fhir_evidence(self):
        text = "Based on Observation/bp-001 (162/104 mmHg) and Condition/htn-002."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_5t_section_headers(self):
        text = "## Talk\nPatient presents with elevated BP.\n## Template\nRisk Level: HIGH."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_sdoh_resource_referral(self):
        text = "Refer to WIC program. Contact 211 for housing assistance."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_immunization_schedule(self):
        text = "DTaP dose 2 is due at 4 months of age."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_empty_text(self):
        filtered, redacted = filter_prescribing_language("")
        self.assertEqual(filtered, "")
        self.assertEqual(redacted, [])


# ===========================================================================
# 3. Reporting existing medications — exemption
# ===========================================================================

class TestReportingExemption(unittest.TestCase):
    """Reporting existing medications from FHIR data is NOT redacted."""

    def test_currently_on(self):
        text = "Patient is currently on labetalol 200mg twice daily."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_currently_taking(self):
        text = "She is currently taking metformin 500mg."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_already_prescribed(self):
        text = "Labetalol was already prescribed by the attending physician."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_presently_receiving(self):
        text = "Patient is presently receiving insulin via subcutaneous injection."
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])

    def test_is_reporting_existing_helper(self):
        self.assertTrue(_is_reporting_existing("currently on labetalol"))
        self.assertTrue(_is_reporting_existing("already prescribed metformin"))
        self.assertTrue(_is_reporting_existing("presently receiving insulin"))
        self.assertTrue(_is_reporting_existing("previously taking aspirin"))
        self.assertFalse(_is_reporting_existing("start her on labetalol"))
        self.assertFalse(_is_reporting_existing("initiate treatment"))


# ===========================================================================
# 4. Multi-sentence handling
# ===========================================================================

class TestMultiSentence(unittest.TestCase):
    """Only prescribing sentences are redacted; others preserved."""

    def test_mixed_safe_and_unsafe(self):
        text = (
            "Blood pressure is critically elevated at 184/118 mmHg. "
            "Initiate labetalol 200mg IV immediately. "
            "Clinician review is required."
        )
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 1)
        self.assertIn("184/118", filtered)
        self.assertIn("Clinician review", filtered)
        self.assertIn(REDACTION_PHRASE, filtered)
        self.assertNotIn("labetalol", filtered)

    def test_multiple_prescribing_sentences(self):
        text = (
            "Initiate labetalol 200mg IV. "
            "Give 4g magnesium sulfate IV. "
            "Monitor vitals every 15 minutes."
        )
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(len(redacted), 2)
        self.assertIn("Monitor vitals", filtered)

    def test_all_safe(self):
        text = (
            "Risk Level: URGENT. "
            "Clinician review required. "
            "Evidence: Observation/bp-001."
        )
        filtered, redacted = filter_prescribing_language(text)
        self.assertEqual(redacted, [])


# ===========================================================================
# 5. ADK callback — LlmResponse mutation
# ===========================================================================

class TestCallbackIntegration(unittest.TestCase):
    """The after_model_callback correctly filters LlmResponse text parts."""

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_redacts_prescribing_in_response(self):
        resp = _make_response("Initiate labetalol 200mg IV immediately.")
        result = safety_after_model_callback(_ctx(), resp)
        # Callback returns None (mutates in place)
        self.assertIsNone(result)
        self.assertIn(REDACTION_PHRASE, resp.content.parts[0].text)
        self.assertNotIn("labetalol", resp.content.parts[0].text)

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_preserves_safe_response(self):
        original = "Blood pressure is 184/118 mmHg. Clinician review required."
        resp = _make_response(original)
        result = safety_after_model_callback(_ctx(), resp)
        self.assertIsNone(result)
        self.assertEqual(resp.content.parts[0].text, original)

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_multi_part_filters_each(self):
        resp = _make_multi_part_response(
            "Initiate treatment with hydralazine.",
            "Risk Level: URGENT.",
        )
        safety_after_model_callback(_ctx(), resp)
        self.assertIn(REDACTION_PHRASE, resp.content.parts[0].text)
        self.assertEqual(resp.content.parts[1].text, "Risk Level: URGENT.")

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_function_call_only_response(self):
        resp = _make_function_call_response("get_bp_trend", {"patient_id": "p1"})
        result = safety_after_model_callback(_ctx(), resp)
        self.assertIsNone(result)
        # No text parts to filter — should pass through unchanged

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_none_content(self):
        resp = LlmResponse(content=None)
        result = safety_after_model_callback(_ctx(), resp)
        self.assertIsNone(result)

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_empty_parts(self):
        resp = LlmResponse(content=types.Content(role="model", parts=[]))
        result = safety_after_model_callback(_ctx(), resp)
        self.assertIsNone(result)


# ===========================================================================
# 6. Feature flag
# ===========================================================================

class TestFeatureFlag(unittest.TestCase):
    """Safety filter respects the MAMAGUARD_SAFETY_FILTER env var."""

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", False)
    def test_disabled_skips_filter(self):
        resp = _make_response("I prescribe labetalol 200mg.")
        result = safety_after_model_callback(_ctx(), resp)
        self.assertIsNone(result)
        # Text should NOT be modified when disabled
        self.assertIn("prescribe", resp.content.parts[0].text)

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_enabled_filters(self):
        resp = _make_response("I prescribe labetalol 200mg.")
        safety_after_model_callback(_ctx(), resp)
        self.assertNotIn("prescribe", resp.content.parts[0].text)


# ===========================================================================
# 7. Env var parsing
# ===========================================================================

class TestEnvVarParsing(unittest.TestCase):
    """MAMAGUARD_SAFETY_FILTER env var is parsed correctly."""

    def _reload_enabled(self, value: str) -> bool:
        """Simulate module-level env var parsing."""
        return value.lower() in ("1", "true", "yes")

    def test_true_values(self):
        for val in ("true", "True", "TRUE", "1", "yes", "Yes"):
            self.assertTrue(self._reload_enabled(val), f"Expected True for {val!r}")

    def test_false_values(self):
        for val in ("false", "False", "0", "no", "No", ""):
            self.assertFalse(self._reload_enabled(val), f"Expected False for {val!r}")


# ===========================================================================
# 8. Agent wiring verification
# ===========================================================================

class TestAgentWiring(unittest.TestCase):
    """All 4 agents have after_model_callback = safety_after_model_callback."""

    def test_orchestrator_has_after_model_callback(self):
        from mamaguard.orchestrator.agent import root_agent
        self.assertIsNotNone(root_agent.after_model_callback)
        cb = root_agent.after_model_callback
        name = getattr(cb, "__name__", repr(cb))
        self.assertEqual(name, "safety_after_model_callback")

    def test_maternal_has_after_model_callback(self):
        from mamaguard.maternal_agent.agent import maternal_risk_agent
        self.assertIsNotNone(maternal_risk_agent.after_model_callback)
        cb = maternal_risk_agent.after_model_callback
        name = getattr(cb, "__name__", repr(cb))
        self.assertEqual(name, "safety_after_model_callback")

    def test_pediatric_has_after_model_callback(self):
        from mamaguard.pediatric_agent.agent import pediatric_transition_agent
        self.assertIsNotNone(pediatric_transition_agent.after_model_callback)
        cb = pediatric_transition_agent.after_model_callback
        name = getattr(cb, "__name__", repr(cb))
        self.assertEqual(name, "safety_after_model_callback")

    def test_sdoh_has_after_model_callback(self):
        from mamaguard.sdoh_agent.agent import sdoh_outreach_agent
        self.assertIsNotNone(sdoh_outreach_agent.after_model_callback)
        cb = sdoh_outreach_agent.after_model_callback
        name = getattr(cb, "__name__", repr(cb))
        self.assertEqual(name, "safety_after_model_callback")


# ===========================================================================
# 9. Preeclampsia adversarial scenario
# ===========================================================================

class TestPreeclampsiaScenario(unittest.TestCase):
    """The exact failure mode from Tier-2a elena_preeclampsia case.

    The model produces text like 'initiate labetalol' or 'begin magnesium
    therapy' for severe preeclampsia — the safety filter must catch these.
    """

    def _assert_redacted(self, text: str, msg: str = ""):
        _, redacted = filter_prescribing_language(text)
        self.assertTrue(len(redacted) > 0, f"Expected redaction: {msg or text}")

    def test_initiate_labetalol(self):
        self._assert_redacted("Initiate labetalol 200mg IV for severe hypertension.")

    def test_start_magnesium(self):
        self._assert_redacted("Start her on magnesium sulfate for seizure prophylaxis.")

    def test_administer_hydralazine(self):
        self._assert_redacted("Administer 10 mg hydralazine IV push over 2 minutes.")

    def test_begin_antihypertensive(self):
        self._assert_redacted("Begin labetalol therapy at 100mg oral twice daily.")

    def test_initiate_magnesium(self):
        self._assert_redacted("Initiate magnesium sulfate 4g IV loading dose followed by 1g/hr maintenance.")

    def test_give_betamethasone(self):
        self._assert_redacted("Give betamethasone 12 mg IM for fetal lung maturity.")

    def test_order_nifedipine(self):
        self._assert_redacted(
            "Order nifedipine 10mg sublingual for acute BP reduction.",
            "order + drug + dosage should be caught",
        )

    def test_complex_multi_sentence(self):
        """Full response that mimics the elena_preeclampsia failure mode."""
        text = (
            "## Talk\n"
            "This patient presents with rapidly deteriorating blood pressure "
            "consistent with severe preeclampsia. BP has risen from 124/82 to "
            "184/118 over 2 months.\n\n"
            "## Template\n"
            "Risk Level: URGENT\n\n"
            "## Task\n"
            "1. Initiate labetalol 200mg IV for acute BP management.\n"
            "2. Give 4g magnesium sulfate IV for seizure prophylaxis.\n"
            "3. Clinician review required immediately."
        )
        filtered, redacted = filter_prescribing_language(text)
        # The two prescribing sentences should be redacted
        self.assertTrue(len(redacted) >= 2, f"Expected >=2 redactions, got {len(redacted)}")
        # Safe content preserved
        self.assertIn("184/118", filtered)
        self.assertIn("URGENT", filtered)
        self.assertIn("Clinician review", filtered)
        # Drug names removed
        self.assertNotIn("labetalol", filtered)
        self.assertNotIn("magnesium sulfate", filtered)


# ===========================================================================
# 10. Logging
# ===========================================================================

class TestLogging(unittest.TestCase):
    """Safety filter logs redaction events."""

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_logs_warning_on_redaction(self):
        resp = _make_response("I prescribe labetalol 200mg.")
        with self.assertLogs("mamaguard.shared.safety_filter", level="WARNING") as cm:
            safety_after_model_callback(_ctx(), resp)
        self.assertTrue(
            any("redacted" in msg.lower() for msg in cm.output),
            f"Expected 'redacted' in logs: {cm.output}",
        )

    @patch("mamaguard.shared.safety_filter.SAFETY_FILTER_ENABLED", True)
    def test_no_log_on_safe_response(self):
        resp = _make_response("Blood pressure is elevated. Clinician review required.")
        # assertNoLogs requires Python 3.10+ — use assertLogs with a sentinel
        import logging
        logger = logging.getLogger("mamaguard.shared.safety_filter")
        with patch.object(logger, "warning") as mock_warn:
            safety_after_model_callback(_ctx(), resp)
            mock_warn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
