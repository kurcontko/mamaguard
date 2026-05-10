"""Unit tests for pediatric FHIR tools."""

import unittest
from unittest.mock import MagicMock, patch

import httpx


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="child-1"):
        self.state = {"fhir_url": fhir_url, "fhir_token": fhir_token, "patient_id": patient_id}


# A 6-month-old baby born 2025-10-09
PATIENT_6MO = {"resourceType": "Patient", "id": "child-1", "birthDate": "2025-10-09"}
# A 2-year-old born 2024-04-09
PATIENT_2YR = {"resourceType": "Patient", "id": "child-2", "birthDate": "2024-04-09"}
# A newborn (0 months) — only HepB dose 1 is due
PATIENT_NEWBORN = {"resourceType": "Patient", "id": "child-3", "birthDate": "2026-04-12"}
# A 5-year-old (60 months) — past the 36-month review threshold
PATIENT_5YR = {"resourceType": "Patient", "id": "child-4", "birthDate": "2021-04-09"}


def _http_status_error(status_code: int, text: str = "") -> httpx.HTTPStatusError:
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return httpx.HTTPStatusError("", request=MagicMock(), response=response)


class TestComputeAgeMonths(unittest.TestCase):
    """Direct coverage for the age helper -- invalid inputs must return None."""

    def test_none_birthdate(self):
        from mamaguard.shared.tools.pediatric import _compute_age_months

        self.assertIsNone(_compute_age_months(None))

    def test_empty_birthdate(self):
        from mamaguard.shared.tools.pediatric import _compute_age_months

        self.assertIsNone(_compute_age_months(""))

    def test_malformed_birthdate(self):
        from mamaguard.shared.tools.pediatric import _compute_age_months

        self.assertIsNone(_compute_age_months("not-a-date"))

    def test_valid_birthdate_with_time_suffix(self):
        """FHIR birthDate may include a time component; only the date portion matters."""
        from mamaguard.shared.tools.pediatric import _compute_age_months

        # Only the first 10 chars are parsed -- a full ISO datetime must not raise
        self.assertIsNotNone(_compute_age_months("2024-01-01T00:00:00Z"))


class TestGetImmunizationGaps(unittest.TestCase):
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
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

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
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

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_newborn_up_to_date_hepb(self, mock_fhir):
        """A newborn (0 months) who received HepB dose 1 has no gaps."""
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_NEWBORN
            if path == "Immunization":
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        {"resource": {"vaccineCode": {"text": "HepB"}, "occurrenceDateTime": "2026-04-12", "status": "completed", "id": "imm-hepb1"}},
                    ],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_immunization_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["data"]["has_gaps"])
        self.assertEqual(len(result["data"]["overdue"]), 0)
        self.assertGreaterEqual(len(result["data"]["up_to_date"]), 1)
        # No overdue -> liaison does NOT demand clinician review
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_id_override_queries_child(self, mock_fhir):
        """Mother-to-child handoff can query a child while session context is mom."""
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        paths = []
        params_seen = []

        def side_effect(fhir_url, token, path, params=None):
            paths.append(path)
            params_seen.append(params)
            if path.startswith("Patient/"):
                return PATIENT_NEWBORN
            if path == "Immunization":
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        {"resource": {"vaccineCode": {"text": "HepB"}, "occurrenceDateTime": "2026-04-12", "status": "completed", "id": "imm-hepb1"}},
                    ],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_immunization_gaps(
            patient_id="child-3",
            tool_context=MockToolContext(patient_id="mother-1"),
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["patient_id"], "child-3")
        self.assertIn("Patient/child-3", paths)
        self.assertIn({"patient": "child-3", "_count": "100"}, params_seen)
        self.assertEqual(result["clinician_review"]["reason"], "")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_missing_birthdate_returns_error(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        mock_fhir.return_value = {"resourceType": "Patient", "id": "child-1"}
        result = get_immunization_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertIn("birthDate", result["error_message"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_invalid_birthdate_returns_error(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        mock_fhir.return_value = {"resourceType": "Patient", "id": "child-1", "birthDate": "not-a-date"}
        result = get_immunization_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertIn("birthDate", result["error_message"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_fetch_http_error(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        mock_fhir.side_effect = _http_status_error(403, "Forbidden")
        result = get_immunization_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 403)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_immunization_fetch_connection_error(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_6MO
            raise httpx.ConnectError("cannot reach server")

        mock_fhir.side_effect = side_effect
        result = get_immunization_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        # ConnectError surfaces as connection error, not http_status
        self.assertNotIn("http_status", result)
        self.assertIn("Could not reach", result["error_message"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_immunization_fetch_http_error(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_6MO
            raise _http_status_error(500, "boom")

        mock_fhir.side_effect = side_effect
        result = get_immunization_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 500)

    def test_missing_context_returns_error(self):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        ctx = MockToolContext(fhir_url="", fhir_token="", patient_id="")
        result = get_immunization_gaps(tool_context=ctx)
        self.assertEqual(result["status"], "error")
        self.assertIn("FHIR context", result["error_message"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_adult_patient_not_applicable(self, mock_fhir):
        """Patient >18 years old: pediatric schedule does not apply; no child vaccines listed."""
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        adult = {"resourceType": "Patient", "id": "gma-1", "birthDate": "1957-04-09"}
        mock_fhir.return_value = adult
        result = get_immunization_gaps(tool_context=MockToolContext(patient_id="gma-1"))
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["data"]["applicable"])
        self.assertFalse(result["data"]["has_gaps"])
        self.assertEqual(result["data"]["overdue"], [])
        self.assertEqual(result["data"]["due"], [])
        # Reason must mention adult schedule so agent doesn't list DTaP/MMR
        self.assertIn("adult", result["data"]["reason"].lower())
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_catchup_enumerates_all_overdue_series(self, mock_fhir):
        """5-year-old with only 4 early vaccines: MMR, Varicella, HepA, PCV13 all overdue by series name."""
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_5YR
            if path == "Immunization":
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        {"resource": {"vaccineCode": {"text": "HepB"}, "occurrenceDateTime": "2021-04-09", "status": "completed", "id": "i1"}},
                        {"resource": {"vaccineCode": {"text": "HepB"}, "occurrenceDateTime": "2021-05-09", "status": "completed", "id": "i2"}},
                        {"resource": {"vaccineCode": {"text": "DTaP"}, "occurrenceDateTime": "2021-06-09", "status": "completed", "id": "i3"}},
                        {"resource": {"vaccineCode": {"text": "IPV"}, "occurrenceDateTime": "2021-06-09", "status": "completed", "id": "i4"}},
                    ],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_immunization_gaps(tool_context=MockToolContext(patient_id="child-4"))
        overdue_series = {o["vaccine"] for o in result["data"]["overdue"]}
        # All these series MUST surface — the agent echoes tool output.
        for series in ("MMR", "Varicella", "PCV13", "HepA"):
            self.assertIn(series, overdue_series, f"missing {series} from overdue list: {overdue_series}")

    def test_normalize_vaccine_cvx_code(self):
        """CVX code mapping: combo vaccine 120 satisfies DTaP, HepB, IPV, and Hib simultaneously."""
        from mamaguard.shared.tools.pediatric import _normalize_vaccine

        vc = {"coding": [{"system": "http://hl7.org/fhir/sid/cvx", "code": "120"}]}
        self.assertEqual(_normalize_vaccine(vc), {"DTaP", "HepB", "IPV", "Hib"})

    def test_normalize_vaccine_mmrv_display(self):
        """MMRV display text satisfies both MMR and Varicella."""
        from mamaguard.shared.tools.pediatric import _normalize_vaccine

        vc = {"coding": [{"display": "MMRV vaccine"}]}
        self.assertEqual(_normalize_vaccine(vc), {"MMR", "Varicella"})

    def test_normalize_vaccine_verbose_display(self):
        """Verbose server display ('Varicella virus vaccine') still resolves to Varicella."""
        from mamaguard.shared.tools.pediatric import _normalize_vaccine

        vc = {"text": "Varicella virus vaccine live"}
        self.assertIn("Varicella", _normalize_vaccine(vc))


class TestGetDevelopmentalScreeningStatus(unittest.TestCase):
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
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
        # 6-month-old is under 36 months -> clinician review required
        self.assertTrue(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_older_than_three_years_no_review_required(self, mock_fhir):
        """Review gating: gaps at >36 months should not trigger clinician_review."""
        from mamaguard.shared.tools.pediatric import get_developmental_screening_status

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_5YR
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_developmental_screening_status(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["data"]["has_gaps"])
        # age_months > 36 short-circuits clinician_review.required even if gaps exist
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_observation_fetch_exception_falls_back_to_empty(self, mock_fhir):
        """Observation fetch failure is swallowed -- function still returns success."""
        from mamaguard.shared.tools.pediatric import get_developmental_screening_status

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return PATIENT_6MO
            raise httpx.ConnectError("observation query failed")

        mock_fhir.side_effect = side_effect
        result = get_developmental_screening_status(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["completed_observations"], [])
        # All milestones up to age show as due since none matched
        self.assertTrue(result["data"]["has_gaps"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_missing_birthdate_returns_error(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_developmental_screening_status

        mock_fhir.return_value = {"resourceType": "Patient", "id": "child-1"}
        result = get_developmental_screening_status(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertIn("birthDate", result["error_message"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_fetch_http_error(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_developmental_screening_status

        mock_fhir.side_effect = _http_status_error(404, "Not Found")
        result = get_developmental_screening_status(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 404)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_fetch_connection_error(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_developmental_screening_status

        mock_fhir.side_effect = httpx.ConnectError("dns failure")
        result = get_developmental_screening_status(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertNotIn("http_status", result)
        self.assertIn("Could not reach", result["error_message"])

    def test_missing_context_returns_error(self):
        from mamaguard.shared.tools.pediatric import get_developmental_screening_status

        ctx = MockToolContext(fhir_url="", fhir_token="", patient_id="")
        result = get_developmental_screening_status(tool_context=ctx)
        self.assertEqual(result["status"], "error")


class TestGetCareGaps(unittest.TestCase):
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
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
        # Empty gaps list -> no clinician review required
        self.assertFalse(result["clinician_review"]["required"])
        self.assertEqual(result["data"]["identified_gaps"], [])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_goal_without_description_is_a_gap(self, mock_fhir):
        """An active goal with no description text should be flagged as a gap."""
        from mamaguard.shared.tools.pediatric import get_care_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path == "CarePlan":
                return {"resourceType": "Bundle", "entry": []}
            if path == "Goal":
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        {"resource": {"id": "g1", "lifecycleStatus": "active", "description": {}}},
                        {
                            "resource": {
                                "id": "g2",
                                "lifecycleStatus": "active",
                                "description": {"text": "Lose 10 lbs"},
                            }
                        },
                    ],
                }
            if path == "Encounter":
                return {"resourceType": "Bundle", "entry": []}
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_care_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        gaps = result["data"]["identified_gaps"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("Goal/g1", gaps[0])
        self.assertIn("active", gaps[0])
        self.assertTrue(result["clinician_review"]["required"])
        # Gap message is surfaced as evidence_basis for the liaison
        self.assertEqual(result["clinician_review"]["evidence_basis"], gaps)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_careplan_fetch_exception_swallowed(self, mock_fhir):
        """CarePlan query failure falls back to empty list without raising."""
        from mamaguard.shared.tools.pediatric import get_care_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path == "CarePlan":
                raise httpx.ConnectError("careplan down")
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_care_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["active_care_plans"], [])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_all_queries_exception_still_success(self, mock_fhir):
        """All three sub-queries failing still returns a usable success envelope."""
        from mamaguard.shared.tools.pediatric import get_care_gaps

        mock_fhir.side_effect = httpx.ConnectError("everything is down")
        result = get_care_gaps(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["active_care_plans"], [])
        self.assertEqual(result["data"]["goals"], [])
        self.assertEqual(result["data"]["recent_encounters"], [])
        self.assertFalse(result["clinician_review"]["required"])

    def test_missing_context_returns_error(self):
        from mamaguard.shared.tools.pediatric import get_care_gaps

        ctx = MockToolContext(fhir_url="", fhir_token="", patient_id="")
        result = get_care_gaps(tool_context=ctx)
        self.assertEqual(result["status"], "error")
        self.assertIn("FHIR context", result["error_message"])


if __name__ == "__main__":
    unittest.main()
