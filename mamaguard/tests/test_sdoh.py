"""Unit tests for SDOH screening + actionable resource lookup tools."""

import os
import unittest
from unittest.mock import MagicMock, patch

import httpx


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="p1"):
        self.state = {"fhir_url": fhir_url, "fhir_token": fhir_token, "patient_id": patient_id}


def _http_status_error(status_code: int, text: str = "") -> httpx.HTTPStatusError:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return httpx.HTTPStatusError("", request=MagicMock(), response=response)


class TestGetSdohScreening(unittest.TestCase):
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
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

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
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

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
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

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_housing_text_match_condition_detected(self, mock_fhir):
        """A condition with no SDOH SNOMED code but matching keyword text is flagged."""
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {"resourceType": "Patient", "id": "p1", "communication": []}
            if path == "Condition":
                return {
                    "resourceType": "Bundle",
                    "entry": [{
                        "resource": {
                            "id": "c-house",
                            "code": {
                                "text": "Homeless and in emergency shelter",
                                "coding": [{"code": "99999999"}],  # not in SNOMED map
                            },
                            "clinicalStatus": {"coding": [{"code": "active"}]},
                        }
                    }],
                }
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
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]["sdoh_conditions"]), 1)
        self.assertIn("Homeless", result["data"]["sdoh_conditions"][0]["condition"])
        # SDOH condition + active coverage -> clinician review NOT required
        # (requirement fires on coverage gap, not on SDOH condition alone)
        self.assertFalse(result["clinician_review"]["required"])
        # Evidence basis still cites the condition for downstream tools
        evidence = " ".join(result["clinician_review"]["evidence_basis"])
        self.assertIn("Condition/c-house", evidence)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_non_sdoh_condition_ignored(self, mock_fhir):
        """A clinical (non-SDOH) condition should not appear in sdoh_conditions."""
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {"resourceType": "Patient", "id": "p1", "communication": []}
            if path == "Condition":
                return {
                    "resourceType": "Bundle",
                    "entry": [{
                        "resource": {
                            "id": "c-htn",
                            "code": {
                                "text": "Essential hypertension",
                                "coding": [{"code": "59621000"}],  # SNOMED: HTN
                            },
                            "clinicalStatus": {"coding": [{"code": "active"}]},
                        }
                    }],
                }
            if path == "Coverage":
                return {
                    "resourceType": "Bundle",
                    "entry": [{
                        "resource": {
                            "id": "cov1", "status": "active",
                            "type": {"text": "Medicaid"},
                        }
                    }],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]["sdoh_conditions"]), 0)
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_english_language_no_barrier(self, mock_fhir):
        """English primary language should record language but not flag a barrier."""
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
                    "entry": [{"resource": {"id": "cov1", "status": "active", "type": {"text": "Medicaid"}}}],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=MockToolContext())
        self.assertEqual(result["data"]["language"], "English")
        # No language-barrier risk factor
        barrier_factors = [f for f in result["data"]["risk_factors"] if "Language barrier" in f]
        self.assertEqual(barrier_factors, [])
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_fetch_exception_swallowed(self, mock_fhir):
        """Patient fetch failure is logged but does not abort the screening."""
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                raise _http_status_error(503, "unavailable")
            if path == "Condition":
                return {"resourceType": "Bundle", "entry": []}
            if path == "Coverage":
                return {
                    "resourceType": "Bundle",
                    "entry": [{"resource": {"id": "cov1", "status": "active", "type": {"text": "Medicaid"}}}],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        # Language stays None when the patient lookup fails
        self.assertIsNone(result["data"]["language"])
        # Coverage path still succeeds
        self.assertEqual(len(result["data"]["coverage"]), 1)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_coverage_fetch_exception_records_risk_factor(self, mock_fhir):
        """Coverage fetch failure surfaces a 'Unable to check coverage' risk factor."""
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {"resourceType": "Patient", "id": "p1", "communication": []}
            if path == "Condition":
                return {"resourceType": "Bundle", "entry": []}
            if path == "Coverage":
                raise httpx.ConnectError("coverage down")
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["coverage"], [])
        self.assertIn("Unable to check coverage status", result["data"]["risk_factors"])
        # No coverage observed -> treat as coverage gap and demand review
        self.assertTrue(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_conditions_fetch_exception_swallowed(self, mock_fhir):
        """Conditions fetch failure is swallowed; sdoh_conditions stays empty."""
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {"resourceType": "Patient", "id": "p1", "communication": []}
            if path == "Condition":
                raise httpx.ConnectError("condition down")
            if path == "Coverage":
                return {
                    "resourceType": "Bundle",
                    "entry": [{"resource": {"id": "cov1", "status": "active", "type": {"text": "Medicaid"}}}],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["sdoh_conditions"], [])

    def test_missing_context_returns_error(self):
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        ctx = MockToolContext(fhir_url="", fhir_token="", patient_id="")
        result = get_sdoh_screening(tool_context=ctx)
        self.assertEqual(result["status"], "error")
        self.assertIn("FHIR context", result["error_message"])
        # Error shape does not include clinician_review (short-circuit before envelope)
        self.assertNotIn("clinician_review", result)


class TestFindSdohResources(unittest.TestCase):
    """Actionable SDOH resource lookup."""

    def setUp(self):
        # Ensure no stale env var leaks the external path into tests
        # that expect the offline fallback.
        self._saved_url = os.environ.pop("MAMAGUARD_SDOH_API_URL", None)
        self._saved_key = os.environ.pop("MAMAGUARD_SDOH_API_KEY", None)

    def tearDown(self):
        if self._saved_url is not None:
            os.environ["MAMAGUARD_SDOH_API_URL"] = self._saved_url
        if self._saved_key is not None:
            os.environ["MAMAGUARD_SDOH_API_KEY"] = self._saved_key

    def test_z590_housing_zip_returns_nonempty_curated(self):
        """Z59.0 + ZIP with no external API → curated housing list."""
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        result = find_sdoh_resources(
            category_or_code="Z59.0",
            zip_code="02139",
            tool_context=MockToolContext(),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["category"], "housing")
        self.assertEqual(result["zip"], "02139")
        self.assertEqual(result["source"], "curated")
        self.assertGreaterEqual(result["resource_count"], 1)
        # Every resource must carry a contact the clinician can act on
        for r in result["resources"]:
            self.assertTrue(r["name"])
            self.assertTrue(r["contact"])
            self.assertEqual(r["zip"], "02139")
        # 211 is a baseline housing resource in our curated list
        names = [r["name"] for r in result["resources"]]
        self.assertTrue(any("211" in n for n in names))
        # Liaison contract: clinician review required
        self.assertTrue(result["clinician_review"]["required"])
        self.assertIn("evidence_basis", result["clinician_review"])

    def test_z5901_specific_code_still_resolves_to_housing(self):
        """Sub-coded Z-codes (Z59.01 = sheltered homelessness) roll up."""
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        result = find_sdoh_resources(
            category_or_code="Z59.01",
            zip_code="02139",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["category"], "housing")
        self.assertGreater(result["resource_count"], 0)

    def test_free_text_food_insecurity_classified(self):
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        result = find_sdoh_resources(
            category_or_code="food insecurity",
            zip_code="10001",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["category"], "food")
        self.assertGreater(result["resource_count"], 0)
        # WIC must show up for food cases (maternal-health relevant)
        names = [r["name"].lower() for r in result["resources"]]
        self.assertTrue(any("wic" in n for n in names))

    def test_unknown_category_falls_back_to_generic_211(self):
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        result = find_sdoh_resources(
            category_or_code="martian colony relocation",
            zip_code="99999",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["source"], "generic_211")
        self.assertEqual(result["resource_count"], 1)
        self.assertIn("211", result["resources"][0]["name"])

    @patch("mamaguard.shared.tools.sdoh._fetch_external_resources")
    def test_external_api_success_preferred_over_curated(self, mock_fetch):
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        os.environ["MAMAGUARD_SDOH_API_URL"] = "https://findhelp.example/api/v1/resources"
        mock_fetch.return_value = [
            {
                "name": "ACME Housing Navigator",
                "contact": "555-1212",
                "url": "https://acme.example/housing",
                "description": "Local housing navigator in ZIP 02139",
                "category": "housing",
                "distance_miles": 1.2,
            }
        ]
        result = find_sdoh_resources(
            category_or_code="Z59.0",
            zip_code="02139",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["source"], "external")
        self.assertEqual(result["resource_count"], 1)
        self.assertEqual(result["resources"][0]["name"], "ACME Housing Navigator")
        mock_fetch.assert_called_once()

    @patch("mamaguard.shared.tools.sdoh._fetch_external_resources")
    def test_external_api_failure_falls_back_to_curated(self, mock_fetch):
        """Graceful degradation when findhelp/211 is down."""
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        os.environ["MAMAGUARD_SDOH_API_URL"] = "https://findhelp.example/api/v1/resources"
        mock_fetch.side_effect = RuntimeError("connection refused")

        result = find_sdoh_resources(
            category_or_code="Z59.0",
            zip_code="02139",
            tool_context=MockToolContext(),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source"], "curated_fallback")
        self.assertGreaterEqual(result["resource_count"], 1)
        # Error surface should land in clinician_review.evidence_basis
        ev = " ".join(result["clinician_review"]["evidence_basis"])
        self.assertIn("connection refused", ev)

    @patch("mamaguard.shared.tools.sdoh._fetch_external_resources")
    def test_external_api_empty_response_falls_back(self, mock_fetch):
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        os.environ["MAMAGUARD_SDOH_API_URL"] = "https://findhelp.example/api/v1/resources"
        mock_fetch.return_value = []  # directory knows nothing about this ZIP

        result = find_sdoh_resources(
            category_or_code="Z59.0",
            zip_code="02139",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["source"], "curated_fallback")
        self.assertGreaterEqual(result["resource_count"], 1)

    def test_missing_input_returns_error(self):
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        result = find_sdoh_resources(
            category_or_code="",
            zip_code="02139",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
