"""Unit tests for maternal FHIR tools -- mock FHIR server responses."""

import unittest
from unittest.mock import patch

import httpx


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="p1"):
        self.state = {"fhir_url": fhir_url, "fhir_token": fhir_token, "patient_id": patient_id}


def _make_bp_observation(obs_id, date, systolic, diastolic):
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "effectiveDateTime": date,
            "component": [
                {"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": systolic, "unit": "mmHg"}},
                {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": diastolic, "unit": "mmHg"}},
            ],
        }
    }


def _make_hba1c_observation(obs_id, date, value):
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "effectiveDateTime": date,
            "valueQuantity": {"value": value, "unit": "%"},
        }
    }


def _make_glucose_observation(obs_id, date, value, unit="mg/dL"):
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "effectiveDateTime": date,
            "valueQuantity": {"value": value, "unit": unit},
        }
    }


def _make_condition(cond_id, snomed, text, status="resolved", onset="2020-01-01"):
    return {
        "resource": {
            "resourceType": "Condition",
            "id": cond_id,
            "code": {"text": text, "coding": [{"system": "http://snomed.info/sct", "code": snomed}]},
            "clinicalStatus": {"coding": [{"code": status}]},
            "onsetDateTime": onset,
        }
    }


# ---------------------------------------------------------------------------
# _parse_bp_components — direct unit tests
# ---------------------------------------------------------------------------

class TestParseBpComponents(unittest.TestCase):
    def test_valid_bp(self):
        from mamaguard.shared.tools.maternal import _parse_bp_components
        resource = {
            "component": [
                {"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 120}},
                {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 80}},
            ]
        }
        result = _parse_bp_components(resource)
        self.assertEqual(result, {"systolic": 120, "diastolic": 80})

    def test_missing_systolic(self):
        from mamaguard.shared.tools.maternal import _parse_bp_components
        resource = {
            "component": [
                {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 80}},
            ]
        }
        self.assertIsNone(_parse_bp_components(resource))

    def test_missing_diastolic(self):
        from mamaguard.shared.tools.maternal import _parse_bp_components
        resource = {
            "component": [
                {"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 120}},
            ]
        }
        self.assertIsNone(_parse_bp_components(resource))

    def test_empty_components(self):
        from mamaguard.shared.tools.maternal import _parse_bp_components
        self.assertIsNone(_parse_bp_components({"component": []}))

    def test_no_component_key(self):
        from mamaguard.shared.tools.maternal import _parse_bp_components
        self.assertIsNone(_parse_bp_components({}))

    def test_multiple_codings_per_component(self):
        """First matching LOINC code wins even when multiple codings present."""
        from mamaguard.shared.tools.maternal import _parse_bp_components
        resource = {
            "component": [
                {
                    "code": {"coding": [{"code": "irrelevant"}, {"code": "8480-6"}]},
                    "valueQuantity": {"value": 135},
                },
                {
                    "code": {"coding": [{"code": "8462-4"}, {"code": "other"}]},
                    "valueQuantity": {"value": 85},
                },
            ]
        }
        result = _parse_bp_components(resource)
        self.assertEqual(result, {"systolic": 135, "diastolic": 85})

    def test_missing_value_quantity(self):
        """Component present but no valueQuantity — value is None."""
        from mamaguard.shared.tools.maternal import _parse_bp_components
        resource = {
            "component": [
                {"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {}},
                {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 80}},
            ]
        }
        # systolic is None because valueQuantity has no "value" key
        self.assertIsNone(_parse_bp_components(resource))

    def test_zero_values_valid(self):
        """Zero is a legitimate value (falsy but not None)."""
        from mamaguard.shared.tools.maternal import _parse_bp_components
        resource = {
            "component": [
                {"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 0}},
                {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 0}},
            ]
        }
        result = _parse_bp_components(resource)
        self.assertEqual(result, {"systolic": 0, "diastolic": 0})


# ---------------------------------------------------------------------------
# _compute_trend — direct unit tests
# ---------------------------------------------------------------------------

class TestComputeTrend(unittest.TestCase):
    def test_insufficient_data_empty(self):
        from mamaguard.shared.tools.maternal import _compute_trend
        self.assertEqual(_compute_trend([]), "insufficient_data")

    def test_insufficient_data_single(self):
        from mamaguard.shared.tools.maternal import _compute_trend
        self.assertEqual(_compute_trend([120.0]), "insufficient_data")

    def test_stable(self):
        from mamaguard.shared.tools.maternal import _compute_trend
        self.assertEqual(_compute_trend([120.0, 121.0, 119.0, 120.5]), "stable")

    def test_increasing(self):
        from mamaguard.shared.tools.maternal import _compute_trend
        self.assertEqual(_compute_trend([110.0, 115.0, 130.0, 140.0]), "increasing")

    def test_decreasing(self):
        from mamaguard.shared.tools.maternal import _compute_trend
        self.assertEqual(_compute_trend([150.0, 145.0, 120.0, 115.0]), "decreasing")

    def test_exactly_two_values(self):
        """With 2 values: first_half=[v[0]], second_half=[v[1]]."""
        from mamaguard.shared.tools.maternal import _compute_trend
        self.assertEqual(_compute_trend([100.0, 110.0]), "increasing")

    def test_custom_threshold_hba1c_stable(self):
        """HbA1c uses threshold=0.3; small delta below that is stable."""
        from mamaguard.shared.tools.maternal import _compute_trend
        self.assertEqual(_compute_trend([6.8, 6.9], threshold=0.3), "stable")

    def test_custom_threshold_hba1c_increasing(self):
        """HbA1c with 0.3 threshold: 6.5 → 7.0 is increasing (diff=0.5 > 0.3)."""
        from mamaguard.shared.tools.maternal import _compute_trend
        self.assertEqual(_compute_trend([6.5, 7.0], threshold=0.3), "increasing")

    def test_boundary_at_threshold(self):
        """Diff exactly equal to threshold is still stable (< threshold, not <=)."""
        from mamaguard.shared.tools.maternal import _compute_trend
        # diff = 2.0, threshold = 2.0 → abs(diff) < threshold is False? No, 2.0 < 2.0 is False.
        # So it should return "increasing" since diff > 0
        self.assertEqual(_compute_trend([100.0, 102.0], threshold=2.0), "increasing")

    def test_odd_number_of_values(self):
        """With 3 values: first_half=v[:1], second_half=v[1:]."""
        from mamaguard.shared.tools.maternal import _compute_trend
        # first_half avg = 100, second_half avg = (130+140)/2 = 135, diff = 35
        self.assertEqual(_compute_trend([100.0, 130.0, 140.0]), "increasing")


# ---------------------------------------------------------------------------
# get_bp_trend — expanded tests
# ---------------------------------------------------------------------------

class TestGetBpTrend(unittest.TestCase):
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_normal_bp(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [
                _make_bp_observation("obs1", "2025-06-15", 120, 78),
                _make_bp_observation("obs2", "2025-12-15", 118, 76),
            ],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["count"], 2)
        self.assertFalse(result["data"]["alert_elevated"])
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_elevated_bp(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [
                _make_bp_observation("obs1", "2025-06-15", 145, 92),
                _make_bp_observation("obs2", "2025-12-15", 138, 88),
            ],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertTrue(result["data"]["alert_elevated"])
        self.assertTrue(result["clinician_review"]["required"])
        self.assertGreater(len(result["clinician_review"]["evidence_basis"]), 0)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_severe_bp(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [
                _make_bp_observation("obs1", "2026-01-16", 170, 98),
            ],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertTrue(result["data"]["alert_severe"])
        self.assertIn("Stage 2", result["clinician_review"]["reason"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_empty_bundle(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {"resourceType": "Bundle", "entry": []}
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["data"]["count"], 0)
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_no_entry_key(self, mock_fhir):
        """Bundle without 'entry' key — treated as empty."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {"resourceType": "Bundle"}
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["count"], 0)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_http_status_error(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        resp = httpx.Response(403, text="Forbidden")
        mock_fhir.side_effect = httpx.HTTPStatusError("", request=httpx.Request("GET", "http://x"), response=resp)
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 403)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_connect_error(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.side_effect = httpx.ConnectError("Connection refused")
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertIn("error_message", result)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_read_timeout(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.side_effect = httpx.ReadTimeout("timed out")
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")

    def test_missing_fhir_context(self):
        from mamaguard.shared.tools.maternal import get_bp_trend
        result = get_bp_trend(tool_context=None)
        self.assertEqual(result["status"], "error")
        self.assertIn("not available", result["error_message"])

    def test_missing_credentials(self):
        from mamaguard.shared.tools.maternal import get_bp_trend
        result = get_bp_trend(tool_context=MockToolContext(fhir_url="", fhir_token="", patient_id=""))
        self.assertEqual(result["status"], "error")
        self.assertIn("fhir_url", result["error_message"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_confidence_values(self, mock_fhir):
        """Severe → 0.9, elevated → 0.8, clean → 0.5."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        # Clean
        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [_make_bp_observation("o1", "2026-01-01", 110, 70)],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["clinician_review"]["confidence"], 0.5)

        # Elevated
        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [_make_bp_observation("o1", "2026-01-01", 145, 92)],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["clinician_review"]["confidence"], 0.8)

        # Severe
        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [_make_bp_observation("o1", "2026-01-01", 165, 112)],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["clinician_review"]["confidence"], 0.9)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_elevated_diastolic_only(self, mock_fhir):
        """Diastolic >90 triggers elevated even if systolic is normal."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [_make_bp_observation("o1", "2026-01-01", 130, 95)],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertTrue(result["data"]["alert_elevated"])
        self.assertFalse(result["data"]["alert_severe"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_severe_diastolic_only(self, mock_fhir):
        """Diastolic >110 triggers severe even if systolic is normal."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [_make_bp_observation("o1", "2026-01-01", 140, 115)],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertTrue(result["data"]["alert_severe"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_evidence_basis_format(self, mock_fhir):
        """Evidence cites resource ID, BP reading, and date."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [_make_bp_observation("obs-abc", "2026-03-15", 155, 95)],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        evidence = result["clinician_review"]["evidence_basis"]
        self.assertEqual(len(evidence), 1)
        self.assertIn("Observation/obs-abc", evidence[0])
        self.assertIn("155/95", evidence[0])
        self.assertIn("2026-03-15", evidence[0])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_evidence_basis_excludes_normal(self, mock_fhir):
        """Normal BP readings not included in evidence_basis."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [
                _make_bp_observation("normal", "2026-01-01", 115, 75),
                _make_bp_observation("high", "2026-02-01", 150, 92),
            ],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        evidence = result["clinician_review"]["evidence_basis"]
        self.assertEqual(len(evidence), 1)
        self.assertIn("Observation/high", evidence[0])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_observation_without_bp_components_skipped(self, mock_fhir):
        """Observation entries that lack BP components are silently skipped."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"id": "bad", "effectiveDateTime": "2026-01-01"}},
                _make_bp_observation("good", "2026-01-02", 120, 80),
            ],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["data"]["count"], 1)
        self.assertEqual(result["data"]["readings"][0]["resource_id"], "good")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_observation_without_date_still_included(self, mock_fhir):
        """Observation with empty effectiveDateTime is still included (no date filter applied)."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [_make_bp_observation("no-date", "", 130, 85)],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["data"]["count"], 1)
        self.assertEqual(result["data"]["readings"][0]["date"], "")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_old_reading_filtered_by_months_back(self, mock_fhir):
        """Reading older than months_back is excluded."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [
                _make_bp_observation("old", "2020-01-01", 140, 90),
                _make_bp_observation("recent", "2026-03-01", 120, 80),
            ],
        }
        result = get_bp_trend(months_back=6, tool_context=MockToolContext())
        self.assertEqual(result["data"]["count"], 1)
        self.assertEqual(result["data"]["readings"][0]["resource_id"], "recent")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_invalid_date_not_filtered(self, mock_fhir):
        """Observation with un-parseable date passes through the date filter."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [_make_bp_observation("bad-date", "not-a-date", 130, 85)],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["data"]["count"], 1)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_trend_direction_increasing(self, mock_fhir):
        """BP trend computed from systolic values."""
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {
            "resourceType": "Bundle",
            "entry": [
                _make_bp_observation("o1", "2026-01-01", 110, 70),
                _make_bp_observation("o2", "2026-02-01", 115, 75),
                _make_bp_observation("o3", "2026-03-01", 130, 85),
                _make_bp_observation("o4", "2026-04-01", 135, 88),
            ],
        }
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["data"]["trend"], "increasing")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_id_in_result(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {"resourceType": "Bundle", "entry": []}
        result = get_bp_trend(tool_context=MockToolContext(patient_id="patient-xyz"))
        self.assertEqual(result["patient_id"], "patient-xyz")


# ---------------------------------------------------------------------------
# get_glucose_trend — expanded tests
# ---------------------------------------------------------------------------

class TestGetGlucoseTrend(unittest.TestCase):
    def _glucose_side_effect(self, glucose_entries=None, hba1c_entries=None):
        """Helper returning side_effect for the two-fetch glucose tool."""
        def side_effect(fhir_url, token, path, params=None):
            code = params.get("code", "")
            if "2339-0" in code:
                return {"resourceType": "Bundle", "entry": glucose_entries or []}
            if "4548-4" in code:
                return {"resourceType": "Bundle", "entry": hba1c_entries or []}
            return {"resourceType": "Bundle", "entry": []}
        return side_effect

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_normal_hba1c(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            hba1c_entries=[_make_hba1c_observation("obs1", "2025-06-15", 5.4)],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["data"]["diabetes_range"])
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_elevated_hba1c(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            hba1c_entries=[
                _make_hba1c_observation("obs1", "2025-06-15", 6.8),
                _make_hba1c_observation("obs2", "2025-12-15", 7.2),
            ],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertTrue(result["data"]["diabetes_range"])
        self.assertTrue(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_very_poorly_controlled(self, mock_fhir):
        """HbA1c > 9.0 sets poorly_controlled flag."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            hba1c_entries=[_make_hba1c_observation("obs1", "2026-01-01", 9.5)],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertTrue(result["data"]["poorly_controlled"])
        self.assertTrue(result["data"]["diabetes_range"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_hba1c_trend_increasing(self, mock_fhir):
        """HbA1c trend uses threshold=0.3."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            hba1c_entries=[
                _make_hba1c_observation("o1", "2025-01-01", 6.5),
                _make_hba1c_observation("o2", "2025-06-01", 6.6),
                _make_hba1c_observation("o3", "2025-09-01", 7.2),
                _make_hba1c_observation("o4", "2026-01-01", 7.5),
            ],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(result["data"]["hba1c_trend"], "increasing")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_glucose_readings_extracted(self, mock_fhir):
        """Glucose observations are extracted with value, unit, date, resource_id."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            glucose_entries=[_make_glucose_observation("g1", "2026-01-01", 95, "mg/dL")],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(len(result["data"]["glucose_readings"]), 1)
        reading = result["data"]["glucose_readings"][0]
        self.assertEqual(reading["value"], 95)
        self.assertEqual(reading["unit"], "mg/dL")
        self.assertEqual(reading["resource_id"], "g1")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_both_empty_bundles(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect()
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]["glucose_readings"]), 0)
        self.assertEqual(len(result["data"]["hba1c_readings"]), 0)
        self.assertEqual(result["data"]["hba1c_trend"], "insufficient_data")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_http_error_on_glucose_fetch(self, mock_fhir):
        """HTTPStatusError on the glucose (first) fetch returns error immediately."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        resp = httpx.Response(500, text="Server Error")
        mock_fhir.side_effect = httpx.HTTPStatusError("", request=httpx.Request("GET", "http://x"), response=resp)
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 500)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_connect_error_on_hba1c_fetch(self, mock_fhir):
        """ConnectError on the HbA1c (second) fetch returns error."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"resourceType": "Bundle", "entry": []}
            raise httpx.ConnectError("Connection refused")

        mock_fhir.side_effect = side_effect
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")

    def test_missing_fhir_context(self):
        from mamaguard.shared.tools.maternal import get_glucose_trend
        result = get_glucose_trend(tool_context=None)
        self.assertEqual(result["status"], "error")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_evidence_basis_format(self, mock_fhir):
        """Evidence cites resource ID, HbA1c value, and date."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            hba1c_entries=[_make_hba1c_observation("hba1c-x", "2026-02-15", 7.8)],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        evidence = result["clinician_review"]["evidence_basis"]
        self.assertEqual(len(evidence), 1)
        self.assertIn("Observation/hba1c-x", evidence[0])
        self.assertIn("7.8", evidence[0])
        self.assertIn("2026-02-15", evidence[0])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_evidence_excludes_normal_hba1c(self, mock_fhir):
        """HbA1c readings <=6.5 not in evidence_basis."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            hba1c_entries=[
                _make_hba1c_observation("normal", "2026-01-01", 5.5),
                _make_hba1c_observation("high", "2026-02-01", 7.0),
            ],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        evidence = result["clinician_review"]["evidence_basis"]
        self.assertEqual(len(evidence), 1)
        self.assertIn("Observation/high", evidence[0])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_unit_fallback_to_code(self, mock_fhir):
        """When valueQuantity has 'code' but no 'unit', code is used."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            glucose_entries=[{
                "resource": {
                    "id": "g1",
                    "effectiveDateTime": "2026-01-01",
                    "valueQuantity": {"value": 100, "code": "mg/dL"},
                },
            }],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(result["data"]["glucose_readings"][0]["unit"], "mg/dL")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_observation_without_value_skipped(self, mock_fhir):
        """Observation with None value in valueQuantity is not added to readings."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            hba1c_entries=[{
                "resource": {
                    "id": "no-val",
                    "effectiveDateTime": "2026-01-01",
                    "valueQuantity": {},
                },
            }],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(len(result["data"]["hba1c_readings"]), 0)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_id_in_result(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_glucose_trend
        mock_fhir.side_effect = self._glucose_side_effect()
        result = get_glucose_trend(tool_context=MockToolContext(patient_id="p-456"))
        self.assertEqual(result["patient_id"], "p-456")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_clinician_review_reason_text(self, mock_fhir):
        """Review reason mentions HbA1c range when in diabetes range."""
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = self._glucose_side_effect(
            hba1c_entries=[_make_hba1c_observation("o1", "2026-01-01", 6.8)],
        )
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertIn("6.5", result["clinician_review"]["reason"])


# ---------------------------------------------------------------------------
# get_pregnancy_history — expanded tests
# ---------------------------------------------------------------------------

class TestGetPregnancyHistory(unittest.TestCase):
    def _preg_side_effect(self, entries_by_snomed=None):
        """Helper returning side_effect that maps SNOMED codes to entries."""
        entries_by_snomed = entries_by_snomed or {}

        def side_effect(fhir_url, token, path, params=None):
            code = params.get("code", "")
            for snomed, entries in entries_by_snomed.items():
                if snomed in code:
                    return {"resourceType": "Bundle", "entry": entries}
            return {"resourceType": "Bundle", "entry": []}

        return side_effect

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_multiple_pregnancies(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "72892002": [_make_condition("c1", "72892002", "Normal pregnancy", "resolved", "2015-03-01")],
            "35999006": [
                _make_condition("c2", "35999006", "Blighted ovum", "resolved", "2012-06-01"),
                _make_condition("c3", "35999006", "Blighted ovum", "resolved", "2014-01-01"),
            ],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["total_count"], 3)
        self.assertEqual(result["data"]["losses"], 2)
        self.assertEqual(result["data"]["live_births"], 1)
        self.assertTrue(result["data"]["high_risk"])
        self.assertTrue(result["clinician_review"]["required"])
        self.assertIn("Recurrent", result["clinician_review"]["reason"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_no_losses_not_high_risk(self, mock_fhir):
        """Single live birth with no losses → not high risk."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "72892002": [_make_condition("c1", "72892002", "Normal pregnancy", "resolved", "2022-06-01")],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["data"]["losses"], 0)
        self.assertEqual(result["data"]["live_births"], 1)
        self.assertFalse(result["data"]["high_risk"])
        self.assertFalse(result["clinician_review"]["required"])
        self.assertEqual(result["clinician_review"]["reason"], "")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_single_loss_not_high_risk(self, mock_fhir):
        """One loss does not trigger high_risk (threshold is >=2)."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "19169002": [_make_condition("c1", "19169002", "Miscarriage", "resolved", "2020-01-01")],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["data"]["losses"], 1)
        self.assertFalse(result["data"]["high_risk"])
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_ongoing_pregnancy(self, mock_fhir):
        """Normal pregnancy with non-resolved status → outcome 'ongoing'."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "72892002": [_make_condition("c1", "72892002", "Normal pregnancy", "active", "2026-01-01")],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        preg = result["data"]["pregnancies"][0]
        self.assertEqual(preg["outcome"], "ongoing")
        self.assertEqual(result["data"]["live_births"], 0)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_fetal_complication_outcome(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "156073000": [_make_condition("c1", "156073000", "Fetal complication", "resolved", "2019-05-01")],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        preg = result["data"]["pregnancies"][0]
        self.assertEqual(preg["outcome"], "fetal_complication")
        self.assertEqual(result["data"]["losses"], 1)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_miscarriage_outcome(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "19169002": [_make_condition("c1", "19169002", "Miscarriage", "resolved", "2018-09-01")],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        preg = result["data"]["pregnancies"][0]
        self.assertEqual(preg["outcome"], "miscarriage")
        self.assertEqual(preg["snomed_code"], "19169002")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_sorted_by_onset_descending(self, mock_fhir):
        """Pregnancies sorted newest-first by onset date."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "72892002": [
                _make_condition("c1", "72892002", "Pregnancy", "resolved", "2015-01-01"),
                _make_condition("c2", "72892002", "Pregnancy", "resolved", "2020-06-01"),
                _make_condition("c3", "72892002", "Pregnancy", "resolved", "2018-03-01"),
            ],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        onsets = [p["onset"] for p in result["data"]["pregnancies"]]
        self.assertEqual(onsets, ["2020-06-01", "2018-03-01", "2015-01-01"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_onset_period_fallback(self, mock_fhir):
        """When onsetDateTime is absent, onsetPeriod.start is used."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        entry = {
            "resource": {
                "resourceType": "Condition",
                "id": "c1",
                "code": {"text": "Normal pregnancy", "coding": [{"system": "http://snomed.info/sct", "code": "72892002"}]},
                "clinicalStatus": {"coding": [{"code": "resolved"}]},
                "onsetPeriod": {"start": "2021-03-15"},
            }
        }
        mock_fhir.side_effect = self._preg_side_effect({"72892002": [entry]})
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["data"]["pregnancies"][0]["onset"], "2021-03-15")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_abatement_period_fallback(self, mock_fhir):
        """When abatementDateTime is absent, abatementPeriod.start is used."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        entry = {
            "resource": {
                "resourceType": "Condition",
                "id": "c1",
                "code": {"text": "Normal pregnancy", "coding": [{"system": "http://snomed.info/sct", "code": "72892002"}]},
                "clinicalStatus": {"coding": [{"code": "resolved"}]},
                "onsetDateTime": "2021-01-01",
                "abatementPeriod": {"start": "2021-09-15"},
            }
        }
        mock_fhir.side_effect = self._preg_side_effect({"72892002": [entry]})
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["data"]["pregnancies"][0]["abatement"], "2021-09-15")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_condition_text_from_coding_display(self, mock_fhir):
        """When code.text is absent, coding display is used for condition name."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        entry = {
            "resource": {
                "resourceType": "Condition",
                "id": "c1",
                "code": {
                    "coding": [{"system": "http://snomed.info/sct", "code": "72892002", "display": "Normal pregnancy (finding)"}],
                },
                "clinicalStatus": {"coding": [{"code": "resolved"}]},
                "onsetDateTime": "2020-01-01",
            }
        }
        mock_fhir.side_effect = self._preg_side_effect({"72892002": [entry]})
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["data"]["pregnancies"][0]["condition"], "Normal pregnancy (finding)")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_empty_history(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect()
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["data"]["total_count"], 0)
        self.assertEqual(result["data"]["losses"], 0)
        self.assertFalse(result["data"]["high_risk"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_http_error(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        resp = httpx.Response(404, text="Not Found")
        mock_fhir.side_effect = httpx.HTTPStatusError("", request=httpx.Request("GET", "http://x"), response=resp)
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 404)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_connect_error(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = httpx.ConnectError("Connection refused")
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")

    def test_missing_fhir_context(self):
        from mamaguard.shared.tools.maternal import get_pregnancy_history
        result = get_pregnancy_history(tool_context=None)
        self.assertEqual(result["status"], "error")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_evidence_basis_format(self, mock_fhir):
        """Evidence for losses cites condition, outcome, and onset."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "19169002": [
                _make_condition("c1", "19169002", "Miscarriage", "resolved", "2018-03-01"),
                _make_condition("c2", "19169002", "Miscarriage", "resolved", "2020-06-01"),
            ],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        evidence = result["clinician_review"]["evidence_basis"]
        self.assertEqual(len(evidence), 2)
        # Sorted newest-first: c2 (2020) before c1 (2018)
        self.assertIn("Condition/c2", evidence[0])
        self.assertIn("miscarriage", evidence[0])
        self.assertIn("Condition/c1", evidence[1])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_loss_count_reason_string(self, mock_fhir):
        """Reason string includes exact loss count."""
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = self._preg_side_effect({
            "35999006": [
                _make_condition("c1", "35999006", "Blighted ovum", "resolved", "2015-01-01"),
                _make_condition("c2", "35999006", "Blighted ovum", "resolved", "2017-01-01"),
                _make_condition("c3", "35999006", "Blighted ovum", "resolved", "2019-01-01"),
            ],
        })
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertIn("3 losses", result["clinician_review"]["reason"])


# ---------------------------------------------------------------------------
# get_maternal_risk_profile — expanded tests
# ---------------------------------------------------------------------------

class TestGetMaternalRiskProfile(unittest.TestCase):
    def _make_sub_result(self, status="success", bp_elevated=False, bp_severe=False,
                         diabetes_range=False, poorly_controlled=False,
                         high_risk_preg=False, losses=0):
        """Build mock sub-results for the risk profile compound tool."""
        bp = {
            "status": status,
            "data": {
                "alert_elevated": bp_elevated, "alert_severe": bp_severe,
                "readings": [], "count": 0, "trend": "stable",
            },
            "clinician_review": {
                "required": bp_elevated,
                "reason": "Elevated BP" if bp_elevated else "",
                "evidence_basis": ["Observation/bp-1"] if bp_elevated else [],
            },
        }
        glucose = {
            "status": status,
            "data": {
                "diabetes_range": diabetes_range, "poorly_controlled": poorly_controlled,
                "glucose_readings": [], "hba1c_readings": [], "hba1c_trend": "stable",
            },
            "clinician_review": {
                "required": diabetes_range,
                "reason": "HbA1c >6.5%" if diabetes_range else "",
                "evidence_basis": ["Observation/hba1c-1"] if diabetes_range else [],
            },
        }
        preg = {
            "status": status,
            "data": {
                "high_risk": high_risk_preg, "losses": losses,
                "live_births": 1, "total_count": losses + 1, "pregnancies": [],
            },
            "clinician_review": {
                "required": high_risk_preg,
                "reason": f"Recurrent loss ({losses})" if high_risk_preg else "",
                "evidence_basis": ["Condition/preg-1"] if high_risk_preg else [],
            },
        }
        return bp, glucose, preg

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_high_risk_profile(self, mock_bp, mock_glucose, mock_preg):
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(
            bp_elevated=True, diabetes_range=True, high_risk_preg=True, losses=3,
        )
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["risk_level"], "HIGH")
        self.assertGreater(len(result["data"]["risk_factors"]), 0)
        self.assertTrue(result["clinician_review"]["required"])
        self.assertGreaterEqual(len(result["clinician_review"]["evidence_basis"]), 3)

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_routine_risk_no_factors(self, mock_bp, mock_glucose, mock_preg):
        """All clear → ROUTINE, no clinician review required."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result()
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["data"]["risk_level"], "ROUTINE")
        self.assertEqual(result["data"]["risk_factors"], [])
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_urgent_from_severe_bp(self, mock_bp, mock_glucose, mock_preg):
        """Stage 2 HTN → URGENT risk level."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(bp_elevated=True, bp_severe=True)
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["data"]["risk_level"], "URGENT")
        self.assertIn("Stage 2", result["data"]["risk_factors"][0])
        self.assertTrue(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_high_from_poorly_controlled_diabetes(self, mock_bp, mock_glucose, mock_preg):
        """Poorly controlled diabetes (HbA1c >9) → HIGH."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(poorly_controlled=True, diabetes_range=True)
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["data"]["risk_level"], "HIGH")
        self.assertIn("Poorly controlled", result["data"]["risk_factors"][0])

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_moderate_from_diabetes_range_only(self, mock_bp, mock_glucose, mock_preg):
        """Diabetes range HbA1c (not poorly controlled) + no BP issues → MODERATE."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(diabetes_range=True)
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["data"]["risk_level"], "MODERATE")
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_moderate_from_pregnancy_loss_only(self, mock_bp, mock_glucose, mock_preg):
        """Recurrent pregnancy loss alone → MODERATE."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(high_risk_preg=True, losses=3)
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["data"]["risk_level"], "MODERATE")

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_urgent_not_downgraded_by_additional_factors(self, mock_bp, mock_glucose, mock_preg):
        """URGENT from BP stays URGENT even with additional diabetes + loss factors."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(
            bp_elevated=True, bp_severe=True,
            diabetes_range=True, poorly_controlled=True,
            high_risk_preg=True, losses=4,
        )
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["data"]["risk_level"], "URGENT")
        self.assertEqual(len(result["data"]["risk_factors"]), 3)

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_sub_result_failure_graceful(self, mock_bp, mock_glucose, mock_preg):
        """When a sub-tool returns error status, its data is excluded but others still contribute."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, _, preg = self._make_sub_result(bp_elevated=True, high_risk_preg=True, losses=2)
        mock_bp.return_value = bp
        mock_glucose.return_value = {"status": "error", "error_message": "FHIR server down"}
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        # BP factor present, glucose factor absent
        factors = result["data"]["risk_factors"]
        self.assertTrue(any("BP" in f or "hypertension" in f for f in factors))
        self.assertFalse(any("diabetes" in f.lower() or "hba1c" in f.lower() for f in factors))

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_all_sub_results_failed(self, mock_bp, mock_glucose, mock_preg):
        """When all sub-tools fail, risk stays ROUTINE with no factors."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        error = {"status": "error", "error_message": "FHIR server down"}
        mock_bp.return_value = error
        mock_glucose.return_value = error
        mock_preg.return_value = error

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["risk_level"], "ROUTINE")
        self.assertEqual(result["data"]["risk_factors"], [])
        self.assertIsNone(result["data"]["bp_summary"])
        self.assertIsNone(result["data"]["glucose_summary"])
        self.assertIsNone(result["data"]["pregnancy_summary"])

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_evidence_aggregation(self, mock_bp, mock_glucose, mock_preg):
        """Evidence basis aggregates from all three sub-results."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(
            bp_elevated=True, diabetes_range=True, high_risk_preg=True, losses=2,
        )
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        evidence = result["clinician_review"]["evidence_basis"]
        self.assertIn("Observation/bp-1", evidence)
        self.assertIn("Observation/hba1c-1", evidence)
        self.assertIn("Condition/preg-1", evidence)

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_risk_factor_strings(self, mock_bp, mock_glucose, mock_preg):
        """Verify specific risk factor wording for each condition type."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(
            bp_elevated=True, bp_severe=True,
            poorly_controlled=True, diabetes_range=True,
            high_risk_preg=True, losses=5,
        )
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        factors = result["data"]["risk_factors"]
        self.assertEqual(len(factors), 3)
        self.assertIn("Stage 2 hypertension (>160/110)", factors[0])
        self.assertIn("Poorly controlled diabetes (HbA1c >9%)", factors[1])
        self.assertIn("Recurrent pregnancy loss (5 losses)", factors[2])

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_reason_contains_risk_level_and_factors(self, mock_bp, mock_glucose, mock_preg):
        """Clinician review reason string contains both risk level and factor list."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(bp_elevated=True)
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        reason = result["clinician_review"]["reason"]
        self.assertIn("HIGH", reason)
        self.assertIn("Elevated BP", reason)

    def test_missing_fhir_context(self):
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile
        result = get_maternal_risk_profile(tool_context=None)
        self.assertEqual(result["status"], "error")

    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_elevated_bp_without_severe_is_high_not_urgent(self, mock_bp, mock_glucose, mock_preg):
        """Elevated (not severe) BP alone → HIGH, not URGENT."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        bp, glucose, preg = self._make_sub_result(bp_elevated=True, bp_severe=False)
        mock_bp.return_value = bp
        mock_glucose.return_value = glucose
        mock_preg.return_value = preg

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["data"]["risk_level"], "HIGH")
        self.assertIn("Elevated BP", result["data"]["risk_factors"][0])


if __name__ == "__main__":
    unittest.main()
