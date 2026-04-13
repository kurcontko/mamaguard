"""
Unit tests for the response quality self-check module.

Covers:
  - 5T section detection (all present, partial, none)
  - Clinician review check (HIGH/URGENT with/without mention)
  - Token length estimation
  - Combined run_quality_checks
  - ADK callback integration (logs warnings, never modifies response)
  - Orchestrator wiring verification
"""

from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from mamaguard.shared.quality_check import (
    _CHAR_PER_TOKEN,
    _TOKEN_LIMIT,
    check_5t_sections,
    check_clinician_review,
    check_token_length,
    quality_check_callback,
    run_quality_checks,
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


def _ctx():
    return SimpleNamespace(state={})


# A well-formed 5T response with URGENT risk and clinician review
GOOD_RESPONSE = """\
**Talk** — Maria presents with Stage 2 hypertension (BP 162/104). \
⚠ CLINICIAN REVIEW REQUIRED for medication management.

**Template** — Combined Risk Level: URGENT
Maternal: BP 162/104 (Observation/bp-m5).

**Table**
| Metric | Value |
|--------|-------|
| BP | 162/104 |

**Task**
1. URGENT — Clinician review of BP trend | Clinician | 24h

**Transaction** — RiskAssessment/ra-001 (maternal_risk_agent).

AI-generated analysis of synthetic data. Not for clinical use.
"""

# Response missing Table and Transaction sections
PARTIAL_RESPONSE = """\
**Talk** — Patient assessment complete.

**Template** — Combined Risk Level: ROUTINE
No significant findings.

**Task**
1. ROUTINE — Follow-up in 4 weeks | Clinician | 4 weeks
"""

# Response with HIGH risk but no clinician review mention
NO_REVIEW_RESPONSE = """\
**Talk** — Patient has elevated BP requiring attention.

**Template** — Combined Risk Level: HIGH
BP 150/95 (Observation/bp-m3).

**Table**
| Metric | Value |
|--------|-------|
| BP | 150/95 |

**Task**
1. HIGH — Follow up on BP | Clinician | 1 week

**Transaction** — None.
"""

# Response with ROUTINE risk (no clinician review needed)
ROUTINE_RESPONSE = """\
**Talk** — All findings within normal limits.

**Template** — Combined Risk Level: ROUTINE
No elevated risks.

**Table**
| Metric | Value |
|--------|-------|
| BP | 120/80 |

**Task**
1. ROUTINE — Standard follow-up | Clinician | 3 months

**Transaction** — None.
"""


# ---------------------------------------------------------------------------
# check_5t_sections
# ---------------------------------------------------------------------------

class Test5TSections(unittest.TestCase):

    def test_all_sections_present(self):
        missing = check_5t_sections(GOOD_RESPONSE)
        self.assertEqual(missing, [])

    def test_missing_table_and_transaction(self):
        missing = check_5t_sections(PARTIAL_RESPONSE)
        self.assertIn("table", missing)
        self.assertIn("transaction", missing)
        self.assertNotIn("talk", missing)
        self.assertNotIn("template", missing)
        self.assertNotIn("task", missing)

    def test_empty_text(self):
        missing = check_5t_sections("")
        self.assertEqual(len(missing), 5)

    def test_heading_style_sections(self):
        text = "## Talk\nNarrative\n## Template\nRisk\n## Table\nData\n## Task\nItems\n## Transaction\nWrites"
        missing = check_5t_sections(text)
        self.assertEqual(missing, [])

    def test_bold_style_sections(self):
        text = "**Talk** text\n**Template** text\n**Table** text\n**Task** text\n**Transaction** text"
        missing = check_5t_sections(text)
        self.assertEqual(missing, [])

    def test_case_insensitive(self):
        text = "**talk** — x\n**TEMPLATE** — x\n**Table** x\n**TASK** x\n**transaction** x"
        missing = check_5t_sections(text)
        self.assertEqual(missing, [])


# ---------------------------------------------------------------------------
# check_clinician_review
# ---------------------------------------------------------------------------

class TestClinicianReview(unittest.TestCase):

    def test_urgent_with_review(self):
        self.assertTrue(check_clinician_review(GOOD_RESPONSE))

    def test_high_without_review(self):
        self.assertFalse(check_clinician_review(NO_REVIEW_RESPONSE))

    def test_routine_no_review_ok(self):
        self.assertTrue(check_clinician_review(ROUTINE_RESPONSE))

    def test_moderate_no_review_ok(self):
        text = "Risk Level: MODERATE\nSome findings."
        self.assertTrue(check_clinician_review(text))

    def test_high_with_review(self):
        text = "Risk Level: HIGH\n⚠ CLINICIAN REVIEW REQUIRED"
        self.assertTrue(check_clinician_review(text))

    def test_empty_text(self):
        self.assertTrue(check_clinician_review(""))

    def test_urgent_with_lowercase_review(self):
        text = "URGENT risk. Clinician review recommended."
        self.assertTrue(check_clinician_review(text))


# ---------------------------------------------------------------------------
# check_token_length
# ---------------------------------------------------------------------------

class TestTokenLength(unittest.TestCase):

    def test_short_response(self):
        text = "Short response"
        under, tokens = check_token_length(text)
        self.assertTrue(under)
        self.assertLess(tokens, 100)

    def test_at_limit(self):
        text = "x" * (_TOKEN_LIMIT * _CHAR_PER_TOKEN)
        under, tokens = check_token_length(text)
        self.assertTrue(under)
        self.assertEqual(tokens, _TOKEN_LIMIT)

    def test_over_limit(self):
        text = "x" * ((_TOKEN_LIMIT + 100) * _CHAR_PER_TOKEN)
        under, tokens = check_token_length(text)
        self.assertFalse(under)
        self.assertGreater(tokens, _TOKEN_LIMIT)

    def test_empty(self):
        under, tokens = check_token_length("")
        self.assertTrue(under)
        self.assertEqual(tokens, 0)


# ---------------------------------------------------------------------------
# run_quality_checks (combined)
# ---------------------------------------------------------------------------

class TestRunQualityChecks(unittest.TestCase):

    def test_good_response_no_warnings(self):
        warnings = run_quality_checks(GOOD_RESPONSE)
        self.assertEqual(warnings, [])

    def test_missing_sections_warning(self):
        warnings = run_quality_checks(PARTIAL_RESPONSE)
        section_warnings = [w for w in warnings if "Missing 5T" in w]
        self.assertEqual(len(section_warnings), 1)
        self.assertIn("table", section_warnings[0])
        self.assertIn("transaction", section_warnings[0])

    def test_missing_clinician_review_warning(self):
        warnings = run_quality_checks(NO_REVIEW_RESPONSE)
        review_warnings = [w for w in warnings if "clinician review" in w]
        self.assertEqual(len(review_warnings), 1)

    def test_over_token_limit_warning(self):
        long_text = GOOD_RESPONSE + "x" * ((_TOKEN_LIMIT + 100) * _CHAR_PER_TOKEN)
        warnings = run_quality_checks(long_text)
        token_warnings = [w for w in warnings if "token limit" in w]
        self.assertEqual(len(token_warnings), 1)

    def test_empty_response_warning(self):
        warnings = run_quality_checks("")
        self.assertEqual(len(warnings), 1)
        self.assertIn("empty", warnings[0])

    def test_whitespace_only_warning(self):
        warnings = run_quality_checks("   \n  \n  ")
        self.assertEqual(len(warnings), 1)
        self.assertIn("empty", warnings[0])

    def test_routine_missing_sections_only_section_warning(self):
        """ROUTINE risk with missing sections should warn about sections, not review."""
        warnings = run_quality_checks(ROUTINE_RESPONSE)
        review_warnings = [w for w in warnings if "clinician review" in w]
        self.assertEqual(len(review_warnings), 0)


# ---------------------------------------------------------------------------
# quality_check_callback (ADK integration)
# ---------------------------------------------------------------------------

class TestQualityCheckCallback(unittest.TestCase):

    def test_good_response_no_modification(self):
        resp = _make_response(GOOD_RESPONSE)
        original_text = resp.content.parts[0].text
        result = quality_check_callback(_ctx(), resp)
        self.assertIsNone(result)
        self.assertEqual(resp.content.parts[0].text, original_text)

    def test_bad_response_logs_warning_but_no_modification(self):
        resp = _make_response(NO_REVIEW_RESPONSE)
        original_text = resp.content.parts[0].text
        with self.assertLogs("mamaguard.shared.quality_check", level="WARNING") as cm:
            result = quality_check_callback(_ctx(), resp)
        self.assertIsNone(result)
        self.assertEqual(resp.content.parts[0].text, original_text)
        self.assertTrue(any("Quality check" in msg for msg in cm.output))

    def test_none_content(self):
        resp = LlmResponse(content=None)
        result = quality_check_callback(_ctx(), resp)
        self.assertIsNone(result)

    def test_none_parts(self):
        resp = LlmResponse(content=types.Content(role="model", parts=None))
        result = quality_check_callback(_ctx(), resp)
        self.assertIsNone(result)

    def test_empty_text_parts(self):
        resp = _make_response("")
        result = quality_check_callback(_ctx(), resp)
        self.assertIsNone(result)

    def test_multi_part_response(self):
        resp = LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text="**Talk** — Summary. "),
                    types.Part(text="**Template** — Risk Level: ROUTINE\n"),
                    types.Part(text="**Table**\n| x | y |\n"),
                    types.Part(text="**Task**\n1. ROUTINE — Item\n"),
                    types.Part(text="**Transaction** — None."),
                ],
            ),
        )
        result = quality_check_callback(_ctx(), resp)
        self.assertIsNone(result)

    def test_function_call_only_response(self):
        """Response with no text parts (e.g. tool call) should not warn."""
        resp = LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(function_call=types.FunctionCall(
                    name="get_patient_summary", args={},
                ))],
            ),
        )
        result = quality_check_callback(_ctx(), resp)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Orchestrator wiring verification
# ---------------------------------------------------------------------------

class TestOrchestratorWiring(unittest.TestCase):

    def test_orchestrator_callback_calls_quality_check(self):
        """The orchestrator after_model_callback chain includes quality_check_callback."""
        import inspect
        from mamaguard.orchestrator.agent import _orchestrator_after_model_callback
        source = inspect.getsource(_orchestrator_after_model_callback)
        self.assertIn("quality_check_callback", source)


if __name__ == "__main__":
    unittest.main()
