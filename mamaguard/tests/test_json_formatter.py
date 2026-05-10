"""
Unit tests for the structured JSON output formatter.

Covers:
  - 5T section extraction from markdown
  - Risk level parsing
  - Findings extraction
  - Task item extraction
  - FHIR write-back extraction
  - Disclaimer extraction
  - Full markdown_to_json round-trip
  - output_format metadata detection
  - ADK callback integration (json_output_callback)
  - Orchestrator wiring with JSON mode
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from mamaguard.shared.json_formatter import (
    get_output_format,
    json_output_callback,
    markdown_to_json,
)


# ---------------------------------------------------------------------------
# Sample 5T markdown response (matches orchestrator example output)
# ---------------------------------------------------------------------------

SAMPLE_5T = """\
**Talk** — MULTI-DOMAIN URGENT: Maria (8 weeks postpartum) presents with Stage 2 \
hypertension (BP 162/104, escalating) and HbA1c 7.2%, compounded by no active insurance \
and housing instability.

**Template** — Combined Risk Level: URGENT (elevated: insurance gap + chronic meds)
Maternal: BP 162/104 (Observation/bp-m5), HbA1c 7.2% (Observation/hba1c-m1), \
postpartum ≤12mo.
SDOH: Housing instability (Condition/sdoh-housing-1), no active Coverage.

**Table**
| Metric | Value | Date | Source |
|--------|-------|------|--------|
| BP | 162/104 | 2026-03-20 | Observation/bp-m5 |

**Task**
1. URGENT — Clinician review of BP trend and postpartum HTN | Clinician | Within 24h
2. URGENT — Medicaid re-enrollment | Benefits navigator | Within 48h
3. HIGH — Housing referral | Social worker | 1 week

**Transaction** — RiskAssessment/ra-001 (maternal_risk_agent). Goal/goal-001 + \
CarePlan/cp-001 (sdoh_outreach_agent). CommunicationRequest/comm-002 \
(sdoh_outreach_agent).

AI-generated analysis of synthetic data. Not for clinical use.
"""


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


def _ctx(output_format: str = "markdown") -> SimpleNamespace:
    state = {}
    if output_format != "markdown":
        state["output_format"] = output_format
    return SimpleNamespace(state=state, metadata={})


# ===========================================================================
# 1. markdown_to_json — full round-trip
# ===========================================================================

class TestMarkdownToJson(unittest.TestCase):

    def test_full_5t_conversion(self):
        result = markdown_to_json(SAMPLE_5T)
        self.assertEqual(result["risk_level"], "URGENT")
        self.assertIn("Maria", result["talk"])
        self.assertIsInstance(result["findings"], list)
        self.assertGreater(len(result["findings"]), 0)
        self.assertIsInstance(result["tasks"], list)
        self.assertGreater(len(result["tasks"]), 0)
        self.assertIsInstance(result["fhir_writes"], list)
        self.assertGreater(len(result["fhir_writes"]), 0)
        self.assertIn("Not for clinical use", result["disclaimer"])

    def test_risk_level_extracted(self):
        result = markdown_to_json(SAMPLE_5T)
        self.assertEqual(result["risk_level"], "URGENT")

    def test_tasks_have_priority(self):
        result = markdown_to_json(SAMPLE_5T)
        for task in result["tasks"]:
            self.assertIn("priority", task)
            self.assertIn(task["priority"], {"URGENT", "HIGH", "MODERATE", "ROUTINE"})
            self.assertIn("description", task)

    def test_tasks_have_responsible_and_timeframe(self):
        result = markdown_to_json(SAMPLE_5T)
        # First task: "Clinician review... | Clinician | Within 24h"
        first = result["tasks"][0]
        self.assertEqual(first["priority"], "URGENT")
        self.assertIn("responsible", first)
        self.assertIn("timeframe", first)

    def test_fhir_writes_extracted(self):
        result = markdown_to_json(SAMPLE_5T)
        refs = {w["reference"] for w in result["fhir_writes"]}
        self.assertIn("RiskAssessment/ra-001", refs)
        self.assertIn("CarePlan/cp-001", refs)
        self.assertIn("Goal/goal-001", refs)
        self.assertIn("CommunicationRequest/comm-002", refs)

    def test_fhir_writes_have_structure(self):
        result = markdown_to_json(SAMPLE_5T)
        for w in result["fhir_writes"]:
            self.assertIn("resource_type", w)
            self.assertIn("resource_id", w)
            self.assertIn("reference", w)

    def test_output_is_valid_json(self):
        result = markdown_to_json(SAMPLE_5T)
        # Should be serializable
        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["risk_level"], "URGENT")

    def test_findings_contain_fhir_refs(self):
        result = markdown_to_json(SAMPLE_5T)
        all_findings = " ".join(result["findings"])
        self.assertTrue(
            "Observation/" in all_findings or "Condition/" in all_findings,
            f"Expected FHIR refs in findings, got: {result['findings']}",
        )


# ===========================================================================
# 2. Risk level parsing
# ===========================================================================

class TestRiskLevelParsing(unittest.TestCase):

    def test_urgent(self):
        text = "**Template** — Combined Risk Level: URGENT\n**Task**\n"
        result = markdown_to_json(text)
        self.assertEqual(result["risk_level"], "URGENT")

    def test_high(self):
        text = "**Template** — Risk Level: HIGH\n**Task**\n"
        result = markdown_to_json(text)
        self.assertEqual(result["risk_level"], "HIGH")

    def test_moderate(self):
        text = "**Template** — Combined Risk Level: MODERATE\n**Task**\n"
        result = markdown_to_json(text)
        self.assertEqual(result["risk_level"], "MODERATE")

    def test_routine(self):
        text = "**Template** — Risk Level: ROUTINE\n**Task**\n"
        result = markdown_to_json(text)
        self.assertEqual(result["risk_level"], "ROUTINE")

    def test_unknown_when_missing(self):
        text = "**Talk** — Something\n**Template** — No risk here\n**Task**\n"
        result = markdown_to_json(text)
        self.assertEqual(result["risk_level"], "UNKNOWN")


# ===========================================================================
# 3. Edge cases
# ===========================================================================

class TestEdgeCases(unittest.TestCase):

    def test_empty_input(self):
        result = markdown_to_json("")
        self.assertEqual(result["risk_level"], "UNKNOWN")
        self.assertEqual(result["talk"], "")
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["fhir_writes"], [])

    def test_no_sections(self):
        result = markdown_to_json("Just plain text with no 5T structure.")
        self.assertEqual(result["risk_level"], "UNKNOWN")
        self.assertEqual(result["talk"], "")

    def test_partial_sections(self):
        text = "**Talk** — Summary here.\n**Template** — Risk Level: HIGH\n"
        result = markdown_to_json(text)
        self.assertEqual(result["risk_level"], "HIGH")
        self.assertIn("Summary here", result["talk"])
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["fhir_writes"], [])

    def test_heading_style_sections(self):
        text = "## Talk\nNarrative\n## Template\nRisk Level: MODERATE\n## Task\n1. MODERATE — Do something | Nurse | 1 week\n"
        result = markdown_to_json(text)
        self.assertIn("Narrative", result["talk"])
        self.assertEqual(result["risk_level"], "MODERATE")
        self.assertEqual(len(result["tasks"]), 1)

    def test_transaction_none_text(self):
        text = "**Transaction** — None\n"
        result = markdown_to_json(text)
        self.assertEqual(result["fhir_writes"], [])


# ===========================================================================
# 4. get_output_format
# ===========================================================================

class TestGetOutputFormat(unittest.TestCase):

    def test_default_markdown(self):
        ctx = SimpleNamespace(state={}, metadata={})
        self.assertEqual(get_output_format(ctx), "markdown")

    def test_json_from_state(self):
        ctx = SimpleNamespace(state={"output_format": "json"}, metadata={})
        self.assertEqual(get_output_format(ctx), "json")

    def test_json_from_metadata(self):
        ctx = SimpleNamespace(state={}, metadata={"output_format": "json"})
        self.assertEqual(get_output_format(ctx), "json")

    def test_state_takes_precedence(self):
        ctx = SimpleNamespace(
            state={"output_format": "json"},
            metadata={"output_format": "markdown"},
        )
        self.assertEqual(get_output_format(ctx), "json")

    def test_case_insensitive(self):
        ctx = SimpleNamespace(state={"output_format": "JSON"}, metadata={})
        self.assertEqual(get_output_format(ctx), "json")

    def test_no_metadata_attr(self):
        ctx = SimpleNamespace(state={})
        self.assertEqual(get_output_format(ctx), "markdown")


# ===========================================================================
# 5. json_output_callback — ADK integration
# ===========================================================================

class TestJsonOutputCallback(unittest.TestCase):

    def test_noop_when_markdown(self):
        resp = _make_response(SAMPLE_5T)
        original_text = resp.content.parts[0].text
        result = json_output_callback(_ctx("markdown"), resp)
        self.assertIsNone(result)
        self.assertEqual(resp.content.parts[0].text, original_text)

    def test_converts_to_json_when_json_mode(self):
        resp = _make_response(SAMPLE_5T)
        result = json_output_callback(_ctx("json"), resp)
        self.assertIsNone(result)
        # Output should be valid JSON
        output = resp.content.parts[0].text
        parsed = json.loads(output)
        self.assertEqual(parsed["risk_level"], "URGENT")
        self.assertIn("Maria", parsed["talk"])
        self.assertIsInstance(parsed["findings"], list)
        self.assertIsInstance(parsed["tasks"], list)
        self.assertIsInstance(parsed["fhir_writes"], list)

    def test_json_output_has_single_text_part(self):
        resp = LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text="**Talk** — Part 1."),
                    types.Part(text="**Template** — Risk Level: HIGH"),
                ],
            ),
        )
        json_output_callback(_ctx("json"), resp)
        text_parts = [p for p in resp.content.parts if p.text is not None]
        self.assertEqual(len(text_parts), 1)
        parsed = json.loads(text_parts[0].text)
        self.assertIn("risk_level", parsed)

    def test_noop_on_none_content(self):
        resp = LlmResponse(content=None)
        result = json_output_callback(_ctx("json"), resp)
        self.assertIsNone(result)

    def test_noop_on_empty_parts(self):
        resp = LlmResponse(content=types.Content(role="model", parts=[]))
        result = json_output_callback(_ctx("json"), resp)
        self.assertIsNone(result)

    def test_noop_on_function_call_only(self):
        resp = LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_function_call(
                    name="get_bp_trend", args={"patient_id": "p1"},
                )],
            ),
        )
        result = json_output_callback(_ctx("json"), resp)
        self.assertIsNone(result)


# ===========================================================================
# 6. Orchestrator wiring
# ===========================================================================

class TestOrchestratorJsonWiring(unittest.TestCase):

    def test_orchestrator_callback_chains_json(self):
        """The orchestrator callback should include json_output_callback."""
        from mamaguard.orchestrator.agent import _orchestrator_after_model_callback
        import inspect

        source = inspect.getsource(_orchestrator_after_model_callback)
        self.assertIn("json_output_callback", source)

    def test_json_mode_instruction_not_required(self):
        """JSON mode is handled post-model, no instruction change needed."""
        from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION
        # Instruction produces markdown; callback converts it.
        self.assertIn("5T", ORCHESTRATOR_INSTRUCTION)

    def test_comprehensive_prompt_requests_parallel_dispatch(self):
        """
        Regression: the design promises parallel sub-agent dispatch for
        comprehensive assessments. ADK runs concurrent function calls in
        the same turn in parallel, so the prompt must tell the model to
        emit fan-out calls in one turn — the old wording said
        "sequentially" which forfeited the speedup.
        """
        from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION
        lowered = ORCHESTRATOR_INSTRUCTION.lower()
        self.assertIn("in parallel", lowered)
        self.assertIn("first turn", lowered)
        # Old wording must be gone.
        self.assertNotIn("all three sequentially", lowered)
        self.assertNotIn("sequential", lowered)

    def test_persist_memory_runs_before_json_formatter(self):
        """
        Regression: json_output_callback rewrites the response text into a
        JSON blob, erasing the `**Template**` marker that
        persist_memory_note keys on. persist must run first.
        """
        from mamaguard.orchestrator.agent import _orchestrator_after_model_callback
        import inspect

        source = inspect.getsource(_orchestrator_after_model_callback)
        persist_pos = source.find("persist_memory_note(")
        json_pos = source.find("json_output_callback(")
        self.assertGreaterEqual(persist_pos, 0)
        self.assertGreaterEqual(json_pos, 0)
        self.assertLess(
            persist_pos, json_pos,
            "persist_memory_note must run before json_output_callback — "
            "JSON formatting strips the 5T markdown markers.",
        )


# ===========================================================================
# 7. Confidence extraction
# ===========================================================================

SAMPLE_5T_WITH_CONFIDENCE = """\
**Talk** — MULTI-DOMAIN URGENT: Maria (8 weeks postpartum) presents with Stage 2 \
hypertension (BP 162/104, escalating) and HbA1c 7.2%.

**Template** — Combined Risk Level: URGENT (elevated: insurance gap + chronic meds)
Maternal: BP 162/104 (Observation/bp-m5), HbA1c 7.2% (Observation/hba1c-m1).
SDOH: Housing instability (Condition/sdoh-housing-1), no active Coverage.
Overall confidence: 0.75 (MODERATE). Maternal 0.88 (BP 0.9, glucose 0.85, pregnancy 0.9). \
SDOH 0.75 (screening 0.8, resources 0.75, care gaps 0.7). \
Lower confidence: SDOH care gaps (0.7) — limited appointment data.
⚠ CLINICIAN REVIEW REQUIRED: Stage 2 HTN with escalating trend.

**Table**
| Metric | Value | Date | Source |
|--------|-------|------|--------|
| BP | 162/104 | 2026-03-20 | Observation/bp-m5 |

**Task**
1. URGENT — Clinician review of BP trend | Clinician | Within 24h

**Transaction** — RiskAssessment/ra-001 (maternal_risk_agent).

AI-generated analysis of synthetic data. Not for clinical use.
"""


class TestConfidenceExtraction(unittest.TestCase):

    def test_overall_confidence_extracted(self):
        result = markdown_to_json(SAMPLE_5T_WITH_CONFIDENCE)
        self.assertIn("confidence", result)
        self.assertAlmostEqual(result["confidence"]["overall"], 0.75)
        self.assertEqual(result["confidence"]["label"], "MODERATE")

    def test_per_item_confidence_extracted(self):
        result = markdown_to_json(SAMPLE_5T_WITH_CONFIDENCE)
        self.assertIn("confidence", result)
        items = result["confidence"].get("items", {})
        self.assertGreater(len(items), 0)
        # Should capture at least some domain scores
        all_vals = list(items.values())
        self.assertTrue(all(isinstance(v, float) for v in all_vals))

    def test_low_confidence_flags(self):
        result = markdown_to_json(SAMPLE_5T_WITH_CONFIDENCE)
        self.assertIn("confidence", result)
        flags = result["confidence"].get("low_confidence_flags", "")
        self.assertIn("care gaps", flags.lower())

    def test_no_confidence_when_absent(self):
        result = markdown_to_json(SAMPLE_5T)
        self.assertNotIn("confidence", result)

    def test_confidence_in_json_callback(self):
        resp = _make_response(SAMPLE_5T_WITH_CONFIDENCE)
        json_output_callback(_ctx("json"), resp)
        parsed = json.loads(resp.content.parts[0].text)
        self.assertIn("confidence", parsed)
        self.assertAlmostEqual(parsed["confidence"]["overall"], 0.75)

    def test_confidence_high_label(self):
        text = (
            "**Template** — Risk Level: URGENT\n"
            "Overall confidence: 0.90 (HIGH). BP 0.9, glucose 0.85.\n"
            "**Task**\n"
        )
        result = markdown_to_json(text)
        self.assertIn("confidence", result)
        self.assertAlmostEqual(result["confidence"]["overall"], 0.90)
        self.assertEqual(result["confidence"]["label"], "HIGH")

    def test_confidence_low_label(self):
        text = (
            "**Template** — Risk Level: MODERATE\n"
            "Overall confidence: 0.55 (LOW). Limited data available.\n"
            "**Task**\n"
        )
        result = markdown_to_json(text)
        self.assertIn("confidence", result)
        self.assertAlmostEqual(result["confidence"]["overall"], 0.55)
        self.assertEqual(result["confidence"]["label"], "LOW")

    def test_single_domain_confidence(self):
        text = (
            "**Template** — Risk Level: HIGH\n"
            "Confidence: BP trend 0.9, glucose 0.85, pregnancy history 0.9. "
            "Overall confidence: 0.88 (HIGH).\n"
            "**Task**\n"
        )
        result = markdown_to_json(text)
        self.assertIn("confidence", result)
        self.assertAlmostEqual(result["confidence"]["overall"], 0.88)

    def test_confidence_serializes_to_json(self):
        result = markdown_to_json(SAMPLE_5T_WITH_CONFIDENCE)
        # Must be JSON-serializable
        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        self.assertIn("confidence", parsed)
        self.assertAlmostEqual(parsed["confidence"]["overall"], 0.75)


# ===========================================================================
# 8. Prompt confidence instructions
# ===========================================================================

class TestPromptConfidenceInstructions(unittest.TestCase):
    """Verify all agent prompts include confidence scoring instructions."""

    def test_orchestrator_has_confidence_instruction(self):
        from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION
        self.assertIn("Overall Confidence", ORCHESTRATOR_INSTRUCTION)
        self.assertIn("confidence", ORCHESTRATOR_INSTRUCTION.lower())

    def test_maternal_has_confidence_instruction(self):
        from mamaguard.maternal_agent.agent import MATERNAL_INSTRUCTION
        self.assertIn("clinician_review.confidence", MATERNAL_INSTRUCTION)

    def test_pediatric_has_confidence_instruction(self):
        from mamaguard.pediatric_agent.agent import PEDIATRIC_INSTRUCTION
        self.assertIn("clinician_review.confidence", PEDIATRIC_INSTRUCTION)

    def test_sdoh_has_confidence_instruction(self):
        from mamaguard.sdoh_agent.agent import SDOH_INSTRUCTION
        self.assertIn("clinician_review.confidence", SDOH_INSTRUCTION)

    def test_orchestrator_example_has_confidence(self):
        from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION
        self.assertIn("Overall confidence:", ORCHESTRATOR_INSTRUCTION)

    def test_maternal_example_has_confidence(self):
        from mamaguard.maternal_agent.agent import MATERNAL_INSTRUCTION
        self.assertIn("Confidence:", MATERNAL_INSTRUCTION)

    def test_pediatric_example_has_confidence(self):
        from mamaguard.pediatric_agent.agent import PEDIATRIC_INSTRUCTION
        self.assertIn("Confidence:", PEDIATRIC_INSTRUCTION)

    def test_sdoh_example_has_confidence(self):
        from mamaguard.sdoh_agent.agent import SDOH_INSTRUCTION
        self.assertIn("Confidence:", SDOH_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
