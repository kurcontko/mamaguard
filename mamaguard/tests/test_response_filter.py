"""
Unit tests for the response post-processor (formatting cleanup).

Covers:
  - Excessive horizontal rules
  - Triple-backtick unwrapping for prose blocks
  - Duplicate header removal
  - Excessive blank line collapsing
  - Leading/trailing rule stripping
  - Clinical content preservation
  - ADK callback integration
  - Orchestrator wiring verification
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from mamaguard.shared.response_filter import (
    clean_formatting,
    response_format_callback,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=text)],
        ),
    )


def _make_multi_part_response(*texts: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=t) for t in texts],
        ),
    )


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(state={})


# ===========================================================================
# 1. Excessive horizontal rules
# ===========================================================================

class TestExcessiveRules(unittest.TestCase):

    def test_three_rules_collapsed_to_one(self):
        text = "Some text\n---\n---\n---\nMore text"
        result = clean_formatting(text)
        self.assertEqual(result.count("---"), 1)
        self.assertIn("Some text", result)
        self.assertIn("More text", result)

    def test_two_rules_collapsed(self):
        text = "Above\n---\n---\nBelow"
        result = clean_formatting(text)
        self.assertEqual(result.count("---"), 1)

    def test_single_rule_preserved(self):
        text = "Above\n---\nBelow"
        result = clean_formatting(text)
        self.assertEqual(result.count("---"), 1)

    def test_asterisk_rules(self):
        text = "A\n***\n***\n***\nB"
        result = clean_formatting(text)
        self.assertIn("A", result)
        self.assertIn("B", result)
        # Collapsed to single ---
        self.assertEqual(result.count("---"), 1)

    def test_underscore_rules(self):
        text = "A\n___\n___\n___\nB"
        result = clean_formatting(text)
        self.assertEqual(result.count("---"), 1)


# ===========================================================================
# 2. Leading/trailing horizontal rules
# ===========================================================================

class TestLeadingTrailingRules(unittest.TestCase):

    def test_leading_rule_stripped(self):
        text = "---\n\nHello world"
        result = clean_formatting(text)
        self.assertFalse(result.startswith("---"))
        self.assertIn("Hello world", result)

    def test_trailing_rule_stripped(self):
        text = "Hello world\n\n---"
        result = clean_formatting(text)
        self.assertFalse(result.rstrip().endswith("---"))
        self.assertIn("Hello world", result)

    def test_both_stripped(self):
        text = "---\nContent here\n---"
        result = clean_formatting(text)
        self.assertNotIn("---", result)
        self.assertIn("Content here", result)


# ===========================================================================
# 3. Fenced code blocks — prose unwrapping
# ===========================================================================

class TestFencedBlocks(unittest.TestCase):

    def test_prose_in_backticks_unwrapped(self):
        text = "Before\n```\nThis is just a sentence.\n```\nAfter"
        result = clean_formatting(text)
        self.assertNotIn("```", result)
        self.assertIn("This is just a sentence.", result)
        self.assertIn("Before", result)
        self.assertIn("After", result)

    def test_code_in_backticks_preserved(self):
        text = "Before\n```python\nimport os\nprint(os.getcwd())\n```\nAfter"
        result = clean_formatting(text)
        self.assertIn("```", result)
        self.assertIn("import os", result)

    def test_long_prose_block_preserved(self):
        # More than 5 lines — heuristic says keep it fenced
        lines = "\n".join(f"Line {i} of prose." for i in range(7))
        text = f"```\n{lines}\n```"
        result = clean_formatting(text)
        self.assertIn("```", result)

    def test_block_with_equals_preserved(self):
        text = "```\nx = 42\n```"
        result = clean_formatting(text)
        self.assertIn("```", result)

    def test_block_with_braces_preserved(self):
        text = '```\n{"key": "value"}\n```'
        result = clean_formatting(text)
        self.assertIn("```", result)

    def test_block_with_parens_preserved(self):
        text = "```\nfunc(arg)\n```"
        result = clean_formatting(text)
        self.assertIn("```", result)


# ===========================================================================
# 4. Duplicate headers
# ===========================================================================

class TestDuplicateHeaders(unittest.TestCase):

    def test_consecutive_duplicate_removed(self):
        text = "## Talk\n## Talk\nContent here"
        result = clean_formatting(text)
        self.assertEqual(result.count("## Talk"), 1)
        self.assertIn("Content here", result)

    def test_non_consecutive_duplicates_preserved(self):
        text = "## Talk\nSome content\n## Talk\nMore content"
        result = clean_formatting(text)
        self.assertEqual(result.count("## Talk"), 2)

    def test_different_headers_preserved(self):
        text = "## Talk\n## Template\nContent"
        result = clean_formatting(text)
        self.assertIn("## Talk", result)
        self.assertIn("## Template", result)


# ===========================================================================
# 5. Excessive blank lines
# ===========================================================================

class TestExcessiveBlanks(unittest.TestCase):

    def test_four_blanks_collapsed(self):
        text = "A\n\n\n\n\nB"
        result = clean_formatting(text)
        # Should be at most 2 blank lines (3 newlines)
        self.assertNotIn("\n\n\n\n", result)
        self.assertIn("A", result)
        self.assertIn("B", result)

    def test_two_blanks_preserved(self):
        text = "A\n\nB"
        result = clean_formatting(text)
        self.assertEqual(result, "A\n\nB")

    def test_three_blanks_preserved(self):
        text = "A\n\n\nB"
        result = clean_formatting(text)
        self.assertEqual(result, "A\n\n\nB")


# ===========================================================================
# 6. Clinical content preservation
# ===========================================================================

class TestClinicalPreservation(unittest.TestCase):
    """Formatting cleanup must NEVER alter clinical content."""

    def test_bp_values_preserved(self):
        text = "BP 162/104 mmHg from Observation/bp-m5."
        self.assertEqual(clean_formatting(text), text)

    def test_hba1c_preserved(self):
        text = "HbA1c 7.2% (Observation/hba1c-m1)."
        self.assertEqual(clean_formatting(text), text)

    def test_risk_levels_preserved(self):
        text = "Risk Level: URGENT. Combined: MULTI-DOMAIN URGENT."
        self.assertEqual(clean_formatting(text), text)

    def test_fhir_references_preserved(self):
        text = "RiskAssessment/ra-001, CarePlan/cp-001, Goal/goal-001."
        self.assertEqual(clean_formatting(text), text)

    def test_medication_names_preserved(self):
        text = "Patient is currently on labetalol 200mg."
        self.assertEqual(clean_formatting(text), text)

    def test_table_preserved(self):
        text = (
            "| Metric | Value |\n"
            "|--------|-------|\n"
            "| BP | 162/104 |\n"
        )
        result = clean_formatting(text)
        self.assertIn("162/104", result)
        self.assertIn("Metric", result)

    def test_disclaimer_preserved(self):
        text = "AI-generated analysis of synthetic data. Not for clinical use."
        self.assertEqual(clean_formatting(text), text)

    def test_full_5t_response_content_preserved(self):
        """A realistic 5T response should have clinical content intact."""
        text = (
            "**Talk** -- Maria presents with Stage 2 hypertension.\n\n"
            "**Template** -- Risk Level: URGENT\n"
            "BP 162/104 (Observation/bp-m5), HbA1c 7.2% (Observation/hba1c-m1).\n\n"
            "**Table**\n"
            "| Metric | Value | Date |\n"
            "|--------|-------|------|\n"
            "| BP | 162/104 | 2026-03-20 |\n\n"
            "**Task**\n"
            "1. URGENT -- Clinician review of BP trend | Within 24h\n\n"
            "**Transaction** -- RiskAssessment/ra-001.\n\n"
            "AI-generated analysis of synthetic data. Not for clinical use."
        )
        result = clean_formatting(text)
        self.assertIn("162/104", result)
        self.assertIn("7.2%", result)
        self.assertIn("URGENT", result)
        self.assertIn("RiskAssessment/ra-001", result)
        self.assertIn("Not for clinical use", result)


# ===========================================================================
# 7. Edge cases
# ===========================================================================

class TestEdgeCases(unittest.TestCase):

    def test_empty_string(self):
        self.assertEqual(clean_formatting(""), "")

    def test_whitespace_only(self):
        result = clean_formatting("   \n\n  ")
        self.assertIsInstance(result, str)

    def test_no_markdown(self):
        text = "Plain text with no markdown at all."
        self.assertEqual(clean_formatting(text), text)

    def test_single_rule_between_sections(self):
        text = "## Talk\nContent\n---\n## Template\nMore"
        result = clean_formatting(text)
        self.assertIn("---", result)
        self.assertIn("## Talk", result)
        self.assertIn("## Template", result)


# ===========================================================================
# 8. ADK callback integration
# ===========================================================================

class TestCallbackIntegration(unittest.TestCase):

    def test_cleans_formatting_in_response(self):
        resp = _make_response("---\n\nHello\n---\n---\n---\nWorld\n\n---")
        result = response_format_callback(_ctx(), resp)
        self.assertIsNone(result)
        text = resp.content.parts[0].text
        self.assertIn("Hello", text)
        self.assertIn("World", text)
        # Leading/trailing rules gone, excessive rules collapsed
        self.assertFalse(text.startswith("---"))

    def test_preserves_clean_response(self):
        original = "Risk Level: URGENT. BP 162/104. Clinician review required."
        resp = _make_response(original)
        response_format_callback(_ctx(), resp)
        self.assertEqual(resp.content.parts[0].text, original)

    def test_multi_part(self):
        resp = _make_multi_part_response(
            "---\nContent\n---",
            "## Talk\n## Talk\nText",
        )
        response_format_callback(_ctx(), resp)
        self.assertNotIn("---", resp.content.parts[0].text)
        self.assertEqual(resp.content.parts[1].text.count("## Talk"), 1)

    def test_none_content(self):
        resp = LlmResponse(content=None)
        result = response_format_callback(_ctx(), resp)
        self.assertIsNone(result)

    def test_empty_parts(self):
        resp = LlmResponse(content=types.Content(role="model", parts=[]))
        result = response_format_callback(_ctx(), resp)
        self.assertIsNone(result)

    def test_function_call_only(self):
        resp = LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_function_call(
                    name="get_bp_trend", args={"patient_id": "p1"},
                )],
            ),
        )
        result = response_format_callback(_ctx(), resp)
        self.assertIsNone(result)


# ===========================================================================
# 9. Orchestrator wiring
# ===========================================================================

class TestOrchestratorWiring(unittest.TestCase):
    """Orchestrator has the combined callback (safety + response filter)."""

    def test_orchestrator_callback_is_combined(self):
        from mamaguard.orchestrator.agent import root_agent
        cb = root_agent.after_model_callback
        self.assertIsNotNone(cb)
        name = getattr(cb, "__name__", repr(cb))
        self.assertEqual(name, "_orchestrator_after_model_callback")

    def test_sub_agents_still_use_safety_only(self):
        """Sub-agents should NOT have the response filter."""
        from mamaguard.maternal_agent.agent import maternal_risk_agent
        from mamaguard.pediatric_agent.agent import pediatric_transition_agent
        from mamaguard.sdoh_agent.agent import sdoh_outreach_agent

        for agent in [maternal_risk_agent, pediatric_transition_agent, sdoh_outreach_agent]:
            cb = agent.after_model_callback
            name = getattr(cb, "__name__", repr(cb))
            self.assertEqual(
                name, "safety_after_model_callback",
                f"{agent.name} should use safety_after_model_callback, got {name}",
            )


if __name__ == "__main__":
    unittest.main()
