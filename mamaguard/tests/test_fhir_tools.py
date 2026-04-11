"""Unit tests for FHIR base tools — mock FHIR server responses."""

import json
import unittest
from unittest.mock import MagicMock, patch

import httpx


class MockToolContext:
    """Minimal mock for google.adk.tools.ToolContext."""

    def __init__(self, fhir_url="", fhir_token="", patient_id=""):
        self.state = {
            "fhir_url": fhir_url,
            "fhir_token": fhir_token,
            "patient_id": patient_id,
        }


class TestGetFhirContext(unittest.TestCase):
    """Test _get_fhir_context helper."""

    def test_missing_all_credentials(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = MockToolContext()
        result = _get_fhir_context(ctx)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")
        self.assertIn("fhir_url", result["error_message"])

    def test_missing_token(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = MockToolContext(fhir_url="https://fhir.example.org", patient_id="123")
        result = _get_fhir_context(ctx)
        self.assertIsInstance(result, dict)
        self.assertIn("fhir_token", result["error_message"])

    def test_valid_credentials(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = MockToolContext(
            fhir_url="https://fhir.example.org",
            fhir_token="eyJ...",
            patient_id="patient-42",
        )
        result = _get_fhir_context(ctx)
        self.assertIsInstance(result, tuple)
        self.assertEqual(result, ("https://fhir.example.org", "eyJ...", "patient-42"))


class TestGetPatientSummary(unittest.TestCase):
    """Test get_patient_summary with mocked FHIR responses."""

    PATIENT_RESPONSE = {
        "resourceType": "Patient",
        "id": "patient-42",
        "name": [{"use": "official", "given": ["Maria"], "family": "Gonzalez"}],
        "birthDate": "1976-03-15",
        "gender": "female",
        "telecom": [{"system": "phone", "value": "555-0100", "use": "home"}],
        "address": [{"line": ["123 Main St"], "city": "Boston", "state": "MA", "postalCode": "02101"}],
        "communication": [{"language": {"text": "French", "coding": [{"display": "French"}]}}],
        "maritalStatus": {"text": "Married"},
    }

    CONDITION_BUNDLE = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {"text": "Diabetes mellitus type 2"},
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "onsetDateTime": "2006-01-15",
                }
            }
        ],
    }

    MED_BUNDLE = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "medicationCodeableConcept": {"text": "Metformin 500 MG"},
                    "status": "active",
                    "dosageInstruction": [{"text": "Take 1 tablet daily"}],
                }
            }
        ],
    }

    VITALS_BUNDLE = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {"text": "Blood Pressure"},
                    "effectiveDateTime": "2024-01-15",
                    "status": "final",
                    "component": [
                        {
                            "code": {"text": "Systolic"},
                            "valueQuantity": {"value": 145, "unit": "mmHg"},
                        },
                        {
                            "code": {"text": "Diastolic"},
                            "valueQuantity": {"value": 92, "unit": "mmHg"},
                        },
                    ],
                }
            }
        ],
    }

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_full_summary(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return self.PATIENT_RESPONSE
            if path == "Condition":
                return self.CONDITION_BUNDLE
            if path == "MedicationRequest":
                return self.MED_BUNDLE
            if path == "Observation":
                return self.VITALS_BUNDLE
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir_get.side_effect = side_effect

        ctx = MockToolContext(
            fhir_url="https://fhir.example.org",
            fhir_token="test-token",
            patient_id="patient-42",
        )
        result = get_patient_summary(ctx)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["name"], "Maria Gonzalez")
        self.assertEqual(result["birth_date"], "1976-03-15")
        self.assertEqual(result["gender"], "female")
        self.assertEqual(result["language"], "French")
        self.assertEqual(len(result["active_conditions"]), 1)
        self.assertEqual(result["active_conditions"][0]["condition"], "Diabetes mellitus type 2")
        self.assertEqual(len(result["active_medications"]), 1)
        self.assertEqual(result["active_medications"][0]["medication"], "Metformin 500 MG")
        self.assertEqual(len(result["recent_vitals"]), 1)

    def test_missing_context_returns_error(self):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        ctx = MockToolContext()
        result = get_patient_summary(ctx)
        self.assertEqual(result["status"], "error")


class TestGetActiveMedications(unittest.TestCase):
    """Test get_active_medications with mocked FHIR responses."""

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_returns_medications(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "medicationCodeableConcept": {"text": "Hydrochlorothiazide 25 MG"},
                        "status": "active",
                        "dosageInstruction": [{"text": "Once daily"}],
                        "authoredOn": "2003-05-01",
                        "requester": {"display": "Dr. Smith"},
                    }
                },
                {
                    "resource": {
                        "medicationCodeableConcept": {"text": "Metformin ER 500 MG"},
                        "status": "active",
                        "dosageInstruction": [{"text": "Twice daily with meals"}],
                        "authoredOn": "2006-11-15",
                    }
                },
            ],
        }

        ctx = MockToolContext(
            fhir_url="https://fhir.example.org",
            fhir_token="test-token",
            patient_id="patient-42",
        )
        result = get_active_medications(ctx)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["medications"][0]["medication"], "Hydrochlorothiazide 25 MG")
        self.assertEqual(result["medications"][1]["medication"], "Metformin ER 500 MG")
        self.assertEqual(result["medications"][0]["requester"], "Dr. Smith")


class TestFhirHook(unittest.TestCase):
    """Test FHIR context extraction from payloads."""

    def test_extract_from_message_metadata(self):
        from mamaguard.shared.fhir_hook import extract_fhir_from_payload

        payload = {
            "params": {
                "message": {
                    "metadata": {
                        "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context": {
                            "fhirUrl": "https://fhir.example.org",
                            "fhirToken": "eyJ...",
                            "patientId": "patient-42",
                        }
                    }
                }
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertIn("fhir-context", key)
        self.assertEqual(data["fhirUrl"], "https://fhir.example.org")
        self.assertEqual(data["patientId"], "patient-42")

    def test_extract_from_params_metadata(self):
        from mamaguard.shared.fhir_hook import extract_fhir_from_payload

        payload = {
            "params": {
                "metadata": {
                    "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context": {
                        "fhirUrl": "https://fhir.example.org",
                        "fhirToken": "tok",
                        "patientId": "p1",
                    }
                }
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertIn("fhir-context", key)
        self.assertEqual(data["patientId"], "p1")

    def test_no_fhir_context(self):
        from mamaguard.shared.fhir_hook import extract_fhir_from_payload

        key, data = extract_fhir_from_payload({"params": {"message": {}}})
        self.assertIsNone(key)
        self.assertIsNone(data)

    def test_invalid_payload(self):
        from mamaguard.shared.fhir_hook import extract_fhir_from_payload

        key, data = extract_fhir_from_payload("not a dict")
        self.assertIsNone(key)


if __name__ == "__main__":
    unittest.main()
