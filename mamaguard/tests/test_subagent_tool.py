"""Unit tests for mamaguard.orchestrator.subagent_tool."""

import unittest

from mamaguard.orchestrator.subagent_tool import (
    FORWARDED_STATE_KEYS,
    _filter_state,
)


class TestFilterState(unittest.TestCase):

    def test_keeps_fhir_keys(self):
        state = {
            "fhir_url": "https://f",
            "fhir_token": "t",
            "patient_id": "p1",
            "output_format": "json",
            "smart_ticket": {"sub": "clinician-1"},
            "fhir_context_errors": [],
        }
        self.assertEqual(_filter_state(state), state)

    def test_drops_non_fhir_keys(self):
        state = {
            "fhir_url": "https://f",
            "fhir_token": "t",
            "patient_id": "p1",
            "agent_memory_block": "<memory>stuff</memory>",
            "_memory_injected_for": "p1",
            "quality_check_notes": "x",
            "temp:_adk_grounding_metadata": "y",
        }
        filtered = _filter_state(state)
        self.assertEqual(set(filtered), {"fhir_url", "fhir_token", "patient_id"})
        self.assertNotIn("agent_memory_block", filtered)

    def test_forwarded_set_is_minimal(self):
        # Guardrail: if we add a key here, review whether subagents actually
        # need it. Keep this set small and auditable.
        self.assertLessEqual(len(FORWARDED_STATE_KEYS), 10)


if __name__ == "__main__":
    unittest.main()
