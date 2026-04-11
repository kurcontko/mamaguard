"""Unit tests for pediatric FHIR tools."""

import unittest
from unittest.mock import patch


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="child-1"):
        self.state = {"fhir_url": fhir_url, "fhir_token": fhir_token, "patient_id": patient_id}


# A 6-month-old baby born 2025-10-09
PATIENT_6MO = {"resourceType": "Patient", "id": "child-1", "birthDate": "2025-10-09"}
# A 2-year-old born 2024-04-09
PATIENT_2YR = {"resourceType": "Patient", "id": "child-2", "birthDate": "2024-04-09"}


class TestGetImmunizationGaps(unittest.TestCase):
    @patch("mamaguard.shared.tools.pediatric._fhir_get")
    def test_newborn_with_gaps(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_6MO
            if path == "Immunization":
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        {"resource": {"vaccineCode": {"text": "HepB"}, "occurrenceDateTime": "2025-10-10", "status": "completed", "id": "imm1"}},
                        {"resource": {"vaccineCode": {"text": "HepB"}, "occurrenceDateTime": "2025-11-10", "status": "completed", "id": "imm2"}},
                    ],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_immunization_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["received_count"], 2)
        self.assertTrue(result["data"]["has_gaps"])
        self.assertTrue(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.pediatric._fhir_get")
    def test_no_immunizations(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_2YR
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_immunization_gaps(tool_context=MockToolContext())
        self.assertTrue(result["data"]["has_gaps"])
        self.assertGreater(len(result["data"]["overdue"]), 0)


class TestGetDevelopmentalScreeningStatus(unittest.TestCase):
    @patch("mamaguard.shared.tools.pediatric._fhir_get")
    def test_screenings_due(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_developmental_screening_status

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_6MO
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_developmental_screening_status(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["data"]["has_gaps"])


class TestGetCareGaps(unittest.TestCase):
    @patch("mamaguard.shared.tools.pediatric._fhir_get")
    def test_with_active_plans(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_care_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path == "CarePlan":
                return {
                    "resourceType": "Bundle",
                    "entry": [{"resource": {"id": "cp1", "title": "Well-child", "status": "active"}}],
                }
            if path == "Goal":
                return {"resourceType": "Bundle", "entry": []}
            if path == "Encounter":
                return {"resourceType": "Bundle", "entry": []}
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_care_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]["active_care_plans"]), 1)


if __name__ == "__main__":
    unittest.main()
