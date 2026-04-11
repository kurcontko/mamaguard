"""Unit tests for maternal FHIR tools -- mock FHIR server responses."""

import unittest
from unittest.mock import patch


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


class TestGetBpTrend(unittest.TestCase):
    @patch("mamaguard.shared.tools.maternal._fhir_get")
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

    @patch("mamaguard.shared.tools.maternal._fhir_get")
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

    @patch("mamaguard.shared.tools.maternal._fhir_get")
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

    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_empty_bundle(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = {"resourceType": "Bundle", "entry": []}
        result = get_bp_trend(tool_context=MockToolContext())
        self.assertEqual(result["data"]["count"], 0)
        self.assertFalse(result["clinician_review"]["required"])


class TestGetGlucoseTrend(unittest.TestCase):
    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_normal_hba1c(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_glucose_trend

        def side_effect(fhir_url, token, path, params=None):
            code = params.get("code", "")
            if "4548-4" in code:
                return {
                    "resourceType": "Bundle",
                    "entry": [_make_hba1c_observation("obs1", "2025-06-15", 5.4)],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["data"]["diabetes_range"])
        self.assertFalse(result["clinician_review"]["required"])

    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_elevated_hba1c(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_glucose_trend

        def side_effect(fhir_url, token, path, params=None):
            code = params.get("code", "")
            if "4548-4" in code:
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        _make_hba1c_observation("obs1", "2025-06-15", 6.8),
                        _make_hba1c_observation("obs2", "2025-12-15", 7.2),
                    ],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_glucose_trend(tool_context=MockToolContext())
        self.assertTrue(result["data"]["diabetes_range"])
        self.assertTrue(result["clinician_review"]["required"])


class TestGetPregnancyHistory(unittest.TestCase):
    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_multiple_pregnancies(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        def side_effect(fhir_url, token, path, params=None):
            code = params.get("code", "")
            if "72892002" in code:
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        _make_condition("c1", "72892002", "Normal pregnancy", "resolved", "2015-03-01"),
                    ],
                }
            elif "35999006" in code:
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        _make_condition("c2", "35999006", "Blighted ovum", "resolved", "2012-06-01"),
                        _make_condition("c3", "35999006", "Blighted ovum", "resolved", "2014-01-01"),
                    ],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_pregnancy_history(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["total_count"], 3)
        self.assertEqual(result["data"]["losses"], 2)
        self.assertEqual(result["data"]["live_births"], 1)
        self.assertTrue(result["data"]["high_risk"])
        self.assertTrue(result["clinician_review"]["required"])
        self.assertIn("Recurrent", result["clinician_review"]["reason"])


class TestGetMaternalRiskProfile(unittest.TestCase):
    @patch("mamaguard.shared.tools.maternal.get_pregnancy_history")
    @patch("mamaguard.shared.tools.maternal.get_glucose_trend")
    @patch("mamaguard.shared.tools.maternal.get_bp_trend")
    def test_high_risk_profile(self, mock_bp, mock_glucose, mock_preg):
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        mock_bp.return_value = {
            "status": "success",
            "data": {"alert_elevated": True, "alert_severe": False, "readings": [], "count": 3, "trend": "stable"},
            "clinician_review": {"required": True, "reason": "Elevated BP", "evidence_basis": ["Observation/1"]},
        }
        mock_glucose.return_value = {
            "status": "success",
            "data": {"diabetes_range": True, "poorly_controlled": False, "glucose_readings": [], "hba1c_readings": [], "hba1c_trend": "stable"},
            "clinician_review": {"required": True, "reason": "HbA1c >6.5%", "evidence_basis": ["Observation/2"]},
        }
        mock_preg.return_value = {
            "status": "success",
            "data": {"high_risk": True, "losses": 3, "live_births": 1, "total_count": 4, "pregnancies": []},
            "clinician_review": {"required": True, "reason": "Recurrent loss", "evidence_basis": ["Condition/3"]},
        }

        result = get_maternal_risk_profile(tool_context=MockToolContext())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["risk_level"], "HIGH")
        self.assertGreater(len(result["data"]["risk_factors"]), 0)
        self.assertTrue(result["clinician_review"]["required"])
        # Evidence should aggregate from all sub-results
        self.assertGreaterEqual(len(result["clinician_review"]["evidence_basis"]), 3)


if __name__ == "__main__":
    unittest.main()
