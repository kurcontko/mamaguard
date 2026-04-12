"""
Golden-file tests for the liaison ``clinician_review`` contract.

Pins the full ``clinician_review`` dict returned by every read/synthesis
FHIR tool against a committed JSON fixture so wording, confidence, and
evidence-string drift is caught in CI. This complements the *shape* checks
in ``test_agents_in_process.py`` — those assert keys/types; these assert
values.

Tools covered (9 read tools):

    maternal:  get_bp_trend, get_glucose_trend, get_pregnancy_history,
               get_maternal_risk_profile
    pediatric: get_immunization_gaps, get_developmental_screening_status,
               get_care_gaps
    sdoh:      get_sdoh_screening, find_sdoh_resources

Writeback tools (``write_risk_assessment``, ``create_communication_request``,
``write_care_plan``) do not emit ``clinician_review`` and are out of scope.

Refreshing goldens
------------------
Set ``UPDATE_GOLDENS=1`` in the environment and re-run this module to
rewrite every fixture from the current implementation::

    UPDATE_GOLDENS=1 python -m unittest \
        mamaguard.tests.test_clinician_review_golden

Regenerating is an explicit, reviewable act — diff the JSON files to
confirm the drift is intentional before committing.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch


_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "clinician_review"
_UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"


class _MockToolContext:
    """Minimal ADK-compatible tool context with FHIR state."""

    def __init__(
        self,
        fhir_url: str = "https://fhir.example.org",
        fhir_token: str = "tok",
        patient_id: str = "p-golden",
    ):
        self.state = {
            "fhir_url": fhir_url,
            "fhir_token": fhir_token,
            "patient_id": patient_id,
        }


class _GoldenBase(unittest.TestCase):
    """Shared golden-file read/write/assert helper."""

    def _golden_path(self, name: str) -> Path:
        return _FIXTURE_DIR / f"{name}.json"

    def _assert_golden(self, name: str, clinician_review: dict) -> None:
        """Compare ``clinician_review`` against the committed fixture.

        When ``UPDATE_GOLDENS=1`` is set, rewrite the fixture instead of
        asserting. Test still passes in that mode so a full refresh run
        produces a clean sweep that can be reviewed as a single diff.
        """
        path = self._golden_path(name)

        if _UPDATE:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(clinician_review, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return

        self.assertTrue(
            path.exists(),
            f"Golden fixture {path} missing — run with UPDATE_GOLDENS=1 to seed it",
        )
        expected = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            clinician_review,
            expected,
            f"clinician_review drift vs. {path.name}. "
            f"If intentional, rerun with UPDATE_GOLDENS=1 and commit the diff.",
        )


# ---------------------------------------------------------------------------
# Maternal tools
# ---------------------------------------------------------------------------


# Two-reading pattern pinned so _compute_trend is stable (needs len >= 2).
# Severe reading (168/112) trips alert_severe; elevated reading (145/92)
# trips alert_elevated.
_BP_SEVERE_BUNDLE = {
    "resourceType": "Bundle",
    "entry": [
        {
            "resource": {
                "resourceType": "Observation",
                "id": "bp-severe-1",
                "effectiveDateTime": "2026-03-15T10:00:00Z",
                "component": [
                    {
                        "code": {"coding": [{"code": "8480-6"}]},
                        "valueQuantity": {"value": 168},
                    },
                    {
                        "code": {"coding": [{"code": "8462-4"}]},
                        "valueQuantity": {"value": 112},
                    },
                ],
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "id": "bp-elevated-1",
                "effectiveDateTime": "2026-03-20T10:00:00Z",
                "component": [
                    {
                        "code": {"coding": [{"code": "8480-6"}]},
                        "valueQuantity": {"value": 145},
                    },
                    {
                        "code": {"coding": [{"code": "8462-4"}]},
                        "valueQuantity": {"value": 92},
                    },
                ],
            }
        },
    ],
}


_BP_CLEAN_BUNDLE = {
    "resourceType": "Bundle",
    "entry": [
        {
            "resource": {
                "resourceType": "Observation",
                "id": "bp-clean-1",
                "effectiveDateTime": "2026-03-15T10:00:00Z",
                "component": [
                    {
                        "code": {"coding": [{"code": "8480-6"}]},
                        "valueQuantity": {"value": 118},
                    },
                    {
                        "code": {"coding": [{"code": "8462-4"}]},
                        "valueQuantity": {"value": 76},
                    },
                ],
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "id": "bp-clean-2",
                "effectiveDateTime": "2026-03-20T10:00:00Z",
                "component": [
                    {
                        "code": {"coding": [{"code": "8480-6"}]},
                        "valueQuantity": {"value": 120},
                    },
                    {
                        "code": {"coding": [{"code": "8462-4"}]},
                        "valueQuantity": {"value": 78},
                    },
                ],
            }
        },
    ],
}


_GLUCOSE_POOR_HBA1C_BUNDLE = {
    "resourceType": "Bundle",
    "entry": [
        {
            "resource": {
                "resourceType": "Observation",
                "id": "hba1c-1",
                "effectiveDateTime": "2026-02-01",
                "valueQuantity": {"value": 7.2, "unit": "%"},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "id": "hba1c-2",
                "effectiveDateTime": "2026-03-01",
                "valueQuantity": {"value": 7.8, "unit": "%"},
            }
        },
    ],
}


_PREG_LOSS_BUNDLE_MISCARRIAGE = {
    "resourceType": "Bundle",
    "entry": [
        {
            "resource": {
                "resourceType": "Condition",
                "id": "preg-miscarriage-1",
                "code": {"text": "Miscarriage"},
                "clinicalStatus": {"coding": [{"code": "resolved"}]},
                "onsetDateTime": "2024-06-15",
            }
        },
        {
            "resource": {
                "resourceType": "Condition",
                "id": "preg-miscarriage-2",
                "code": {"text": "Miscarriage"},
                "clinicalStatus": {"coding": [{"code": "resolved"}]},
                "onsetDateTime": "2025-02-10",
            }
        },
    ],
}


class TestMaternalGoldens(_GoldenBase):
    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_get_bp_trend_severe(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = _BP_SEVERE_BUNDLE
        # months_back large enough to clear any date cutoff
        result = get_bp_trend(months_back=240, tool_context=_MockToolContext())
        self.assertEqual(result["status"], "success")
        self._assert_golden("get_bp_trend_severe", result["clinician_review"])

    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_get_bp_trend_clean(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.return_value = _BP_CLEAN_BUNDLE
        result = get_bp_trend(months_back=240, tool_context=_MockToolContext())
        self.assertEqual(result["status"], "success")
        self._assert_golden("get_bp_trend_clean", result["clinician_review"])

    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_get_glucose_trend_poorly_controlled(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_glucose_trend

        def side_effect(fhir_url, token, path, params=None):
            code = (params or {}).get("code", "")
            if "4548-4" in code:  # HbA1c LOINC
                return _GLUCOSE_POOR_HBA1C_BUNDLE
            # glucose observations empty — HbA1c alone drives the contract
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_glucose_trend(months_back=240, tool_context=_MockToolContext())
        self.assertEqual(result["status"], "success")
        self._assert_golden(
            "get_glucose_trend_poorly_controlled", result["clinician_review"]
        )

    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_get_pregnancy_history_high_risk(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        def side_effect(fhir_url, token, path, params=None):
            code = (params or {}).get("code", "")
            if "19169002" in code:  # miscarriage SNOMED
                return _PREG_LOSS_BUNDLE_MISCARRIAGE
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_pregnancy_history(tool_context=_MockToolContext())
        self.assertEqual(result["status"], "success")
        self._assert_golden(
            "get_pregnancy_history_high_risk", result["clinician_review"]
        )

    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_get_maternal_risk_profile_urgent(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        def side_effect(fhir_url, token, path, params=None):
            params = params or {}
            code = params.get("code", "")
            if path == "Observation" and "55284-4" in code:
                return _BP_SEVERE_BUNDLE
            if path == "Observation" and "4548-4" in code:
                return _GLUCOSE_POOR_HBA1C_BUNDLE
            if path == "Observation":  # glucose LOINC 2339-0
                return {"resourceType": "Bundle", "entry": []}
            if path == "Condition" and "19169002" in code:
                return _PREG_LOSS_BUNDLE_MISCARRIAGE
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_maternal_risk_profile(tool_context=_MockToolContext())
        self.assertEqual(result["status"], "success")
        self._assert_golden(
            "get_maternal_risk_profile_urgent", result["clinician_review"]
        )


# ---------------------------------------------------------------------------
# Pediatric tools
#
# get_immunization_gaps + get_developmental_screening_status depend on
# patient age via `_compute_age_months` (uses datetime.now() under the hood).
# To keep goldens deterministic we patch that helper in each test.
# ---------------------------------------------------------------------------


class TestPediatricGoldens(_GoldenBase):
    @patch("mamaguard.shared.tools.pediatric._compute_age_months")
    @patch("mamaguard.shared.tools.pediatric._fhir_get")
    def test_get_immunization_gaps_overdue(self, mock_fhir, mock_age):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        # 18-month-old with only HepB #1 on the record → many overdue doses.
        mock_age.return_value = 18

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {
                    "resourceType": "Patient",
                    "id": "child-golden",
                    "birthDate": "2024-10-09",
                }
            if path == "Immunization":
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        {
                            "resource": {
                                "id": "imm-hepb-1",
                                "vaccineCode": {"text": "HepB"},
                                "occurrenceDateTime": "2024-10-10",
                                "status": "completed",
                            }
                        }
                    ],
                }
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_immunization_gaps(tool_context=_MockToolContext(patient_id="child-golden"))
        self.assertEqual(result["status"], "success")
        self._assert_golden(
            "get_immunization_gaps_overdue", result["clinician_review"]
        )

    @patch("mamaguard.shared.tools.pediatric._compute_age_months")
    @patch("mamaguard.shared.tools.pediatric._fhir_get")
    def test_get_developmental_screening_status_due(self, mock_fhir, mock_age):
        from mamaguard.shared.tools.pediatric import (
            get_developmental_screening_status,
        )

        mock_age.return_value = 9  # 9-month visit window

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {
                    "resourceType": "Patient",
                    "id": "child-golden",
                    "birthDate": "2025-07-12",
                }
            return {"resourceType": "Bundle", "entry": []}  # no completed screenings

        mock_fhir.side_effect = side_effect
        result = get_developmental_screening_status(
            tool_context=_MockToolContext(patient_id="child-golden")
        )
        self.assertEqual(result["status"], "success")
        self._assert_golden(
            "get_developmental_screening_status_due", result["clinician_review"]
        )

    @patch("mamaguard.shared.tools.pediatric._fhir_get")
    def test_get_care_gaps_unlabeled_goal(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_care_gaps

        def side_effect(fhir_url, token, path, params=None):
            if path == "CarePlan":
                return {"resourceType": "Bundle", "entry": []}
            if path == "Goal":
                return {
                    "resourceType": "Bundle",
                    "entry": [
                        {
                            "resource": {
                                "id": "goal-unlabeled",
                                "lifecycleStatus": "active",
                                "description": {"text": ""},
                            }
                        }
                    ],
                }
            if path == "Encounter":
                return {"resourceType": "Bundle", "entry": []}
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_care_gaps(tool_context=_MockToolContext(patient_id="child-golden"))
        self.assertEqual(result["status"], "success")
        self._assert_golden("get_care_gaps_unlabeled_goal", result["clinician_review"])


# ---------------------------------------------------------------------------
# SDOH tools
# ---------------------------------------------------------------------------


class TestSdohGoldens(_GoldenBase):
    @patch("mamaguard.shared.tools.sdoh._fhir_get")
    def test_get_sdoh_screening_no_coverage(self, mock_fhir):
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return {
                    "resourceType": "Patient",
                    "id": "p-golden",
                    "communication": [{"language": {"text": "Spanish"}}],
                }
            if path == "Condition":
                return {"resourceType": "Bundle", "entry": []}
            if path == "Coverage":
                return {"resourceType": "Bundle", "entry": []}
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir.side_effect = side_effect
        result = get_sdoh_screening(tool_context=_MockToolContext())
        self.assertEqual(result["status"], "success")
        self._assert_golden(
            "get_sdoh_screening_no_coverage", result["clinician_review"]
        )

    def test_find_sdoh_resources_housing_curated(self):
        """Pin the curated-path contract (no external API configured)."""
        from mamaguard.shared.tools.sdoh import find_sdoh_resources

        # Scrub env so the curated path is exercised.
        saved_url = os.environ.pop("MAMAGUARD_SDOH_API_URL", None)
        saved_key = os.environ.pop("MAMAGUARD_SDOH_API_KEY", None)
        try:
            result = find_sdoh_resources(
                category_or_code="Z59.0",
                zip_code="02139",
                tool_context=_MockToolContext(),
            )
        finally:
            if saved_url is not None:
                os.environ["MAMAGUARD_SDOH_API_URL"] = saved_url
            if saved_key is not None:
                os.environ["MAMAGUARD_SDOH_API_KEY"] = saved_key

        self.assertEqual(result["status"], "success")
        self._assert_golden(
            "find_sdoh_resources_housing_curated", result["clinician_review"]
        )


if __name__ == "__main__":
    unittest.main()
