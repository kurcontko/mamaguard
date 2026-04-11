"""Unit tests for SDOH screening tool."""

import unittest
from unittest.mock import patch


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="p1"):
        self.state = {"fhir_url": fhir_url, "fhir_token": fhir_token, "patient_id": patient_id}


class TestGetSdohScreening(unittest.TestCase):
    @patch("mamaguard.shared.tools.sdoh._fhir_get")
    def test_no_coverage_detected(self, mock_fhir):
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {
                    "resourceType": "Patient", "id": "p1",
                    "communication": [{"language": {"text": "French"}}],
                }
            if path == "Condition":
                return {"resourceType": "Bundle", "entry": []}
            if path == "Coverage":
                return {"resourceType": "Bundle", "entry": []}
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["language"], "French")
        self.assertEqual(len(result["data"]["coverage"]), 0)
        self.assertTrue(result["clinician_review"]["required"])
        self.assertIn("Language barrier", result["data"]["risk_factors"][0])
        self.assertIn("No insurance", result["data"]["risk_factors"][1])

    @patch("mamaguard.shared.tools.sdoh._fhir_get")
    def test_with_coverage(self, mock_fhir):
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {
                    "resourceType": "Patient", "id": "p1",
                    "communication": [{"language": {"text": "English"}}],
                }
            if path == "Condition":
                return {"resourceType": "Bundle", "entry": []}
            if path == "Coverage":
                return {
                    "resourceType": "Bundle",
                    "entry": [{
                        "resource": {
                            "id": "cov1", "status": "active",
                            "type": {"text": "Medicaid"},
                            "period": {"start": "2025-01-01", "end": "2026-12-31"},
                        }
                    }],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=MockToolContext())
        self.assertEqual(len(result["data"]["coverage"]), 1)
        self.assertEqual(result["data"]["coverage"][0]["type"], "Medicaid")
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.sdoh._fhir_get")
    def test_sdoh_condition_detected(self, mock_fhir):
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {"resourceType": "Patient", "id": "p1", "communication": []}
            if path == "Condition":
                return {
                    "resourceType": "Bundle",
                    "entry": [{
                        "resource": {
                            "id": "c1",
                            "code": {"text": "Stress (finding)", "coding": [{"code": "73595000"}]},
                            "clinicalStatus": {"coding": [{"code": "active"}]},
                        }
                    }],
                }
            if path == "Coverage":
                return {"resourceType": "Bundle", "entry": []}
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=MockToolContext())
        self.assertEqual(len(result["data"]["sdoh_conditions"]), 1)
        self.assertTrue(result["clinician_review"]["required"])


if __name__ == "__main__":
    unittest.main()
