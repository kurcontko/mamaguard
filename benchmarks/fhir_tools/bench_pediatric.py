"""
FHIR tool accuracy benchmarks — Pediatric tools.

Tests immunization gap detection, developmental screening status,
and care gap identification against known fixture scenarios.
"""

from unittest.mock import patch

from benchmarks.base import BenchmarkResult, BenchmarkSuite, MockToolContext, Verdict
from benchmarks.fixtures.pediatric import (
    BABY_SANTOS_ID,
    BABY_SANTOS_IMMUNIZATIONS,
    BABY_SANTOS_PATIENT,
    BABY_SANTOS_SCREENINGS,
    CHILD_SMITH_ID,
    CHILD_SMITH_IMMUNIZATIONS,
    CHILD_SMITH_PATIENT,
    CHILD_SMITH_SCREENINGS,
    TODDLER_JONES_ID,
    TODDLER_JONES_IMMUNIZATIONS,
    TODDLER_JONES_PATIENT,
    TODDLER_JONES_SCREENINGS,
)

suite = BenchmarkSuite(
    name="fhir_pediatric",
    description="Pediatric FHIR tool accuracy — immunizations, screenings, care gaps",
)


def _run_immunization_gaps(patient: dict, imm_bundle: dict, patient_id: str) -> dict:
    from mamaguard.shared.tools.pediatric import get_immunization_gaps

    def side_effect(fhir_url, token, path, params=None):
        if path == f"Patient/{patient_id}":
            return patient
        if path == "Immunization":
            return imm_bundle
        return {"resourceType": "Bundle", "entry": []}

    with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock:
        mock.side_effect = side_effect
        ctx = MockToolContext(patient_id=patient_id)
        return get_immunization_gaps(tool_context=ctx)  # type: ignore[arg-type]


def _run_developmental_screening(patient: dict, screening_bundle: dict, patient_id: str) -> dict:
    from mamaguard.shared.tools.pediatric import get_developmental_screening_status

    def side_effect(fhir_url, token, path, params=None):
        if path == f"Patient/{patient_id}":
            return patient
        if path == "Observation":
            return screening_bundle
        return {"resourceType": "Bundle", "entry": []}

    with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock:
        mock.side_effect = side_effect
        ctx = MockToolContext(patient_id=patient_id)
        return get_developmental_screening_status(tool_context=ctx)  # type: ignore[arg-type]


# -- Immunization Benchmarks ---------------------------------------------------

@suite.case("imm_newborn_gaps", "Detect missing 2-month vaccines for Baby Santos", "fhir_tools")
def bench_imm_newborn():
    result = _run_immunization_gaps(BABY_SANTOS_PATIENT, BABY_SANTOS_IMMUNIZATIONS, BABY_SANTOS_ID)
    checks = {
        "status_success": result["status"] == "success",
        "has_gaps": result["data"]["has_gaps"] is True or len(result["data"]["due"]) > 0,
        "hepb_dose1_received": any(
            "HepB" in v["vaccine"] for v in result["data"]["received"]
        ),
        "received_count_correct": result["data"]["received_count"] == 1,
    }
    # At 2 months: HepB dose 2 should be due, plus DTaP/IPV/Hib/PCV13/RV dose 1
    overdue_plus_due = len(result["data"]["overdue"]) + len(result["data"]["due"])
    checks["multiple_vaccines_needed"] = overdue_plus_due >= 5

    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="imm_newborn_gaps",
        verdict=Verdict.PASS if score >= 0.8 else Verdict.FAIL,
        score=score,
        details={**checks, "overdue": len(result["data"]["overdue"]), "due": len(result["data"]["due"])},
    )


@suite.case("imm_toddler_up_to_date", "Toddler Jones mostly up to date at 18 months", "fhir_tools")
def bench_imm_toddler():
    result = _run_immunization_gaps(TODDLER_JONES_PATIENT, TODDLER_JONES_IMMUNIZATIONS, TODDLER_JONES_ID)
    checks = {
        "status_success": result["status"] == "success",
        "many_received": result["data"]["received_count"] >= 18,
        "many_up_to_date": len(result["data"]["up_to_date"]) >= 10,
    }
    # DTaP dose 4 is due at 15 months — may or may not be overdue depending on age calc
    checks["few_overdue"] = len(result["data"]["overdue"]) <= 3

    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="imm_toddler_up_to_date",
        verdict=Verdict.PASS if score >= 0.75 else Verdict.FAIL,
        score=score,
        details={
            **checks,
            "up_to_date_count": len(result["data"]["up_to_date"]),
            "overdue_count": len(result["data"]["overdue"]),
            "due_count": len(result["data"]["due"]),
        },
    )


@suite.case("imm_child_massive_gaps", "Detect massive immunization gaps for 5-year-old lost to follow-up", "fhir_tools")
def bench_imm_child_gaps():
    result = _run_immunization_gaps(CHILD_SMITH_PATIENT, CHILD_SMITH_IMMUNIZATIONS, CHILD_SMITH_ID)
    checks = {
        "status_success": result["status"] == "success",
        "has_gaps": result["data"]["has_gaps"] is True,
        "many_overdue": len(result["data"]["overdue"]) >= 10,
        "clinician_review": result["clinician_review"]["required"] is True,
        "catch_up_recommended": "catch-up" in result["clinician_review"]["recommendation"].lower(),
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="imm_child_massive_gaps",
        verdict=Verdict.PASS if score >= 0.8 else Verdict.FAIL,
        score=score,
        details={**checks, "overdue_count": len(result["data"]["overdue"])},
    )


# -- Developmental Screening Benchmarks ----------------------------------------

@suite.case("dev_newborn_screenings_done", "Baby Santos has newborn screens completed", "fhir_tools")
def bench_dev_newborn():
    result = _run_developmental_screening(BABY_SANTOS_PATIENT, BABY_SANTOS_SCREENINGS, BABY_SANTOS_ID)
    checks = {
        "status_success": result["status"] == "success",
        "observations_found": len(result["data"]["completed_observations"]) >= 2,
        "has_completed_milestones": len(result["data"]["completed"]) >= 1,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="dev_newborn_screenings_done",
        verdict=Verdict.PASS if score >= 0.66 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("dev_toddler_autism_screen_due", "Toddler Jones needs M-CHAT autism screen at 18m", "fhir_tools")
def bench_dev_toddler_autism():
    result = _run_developmental_screening(TODDLER_JONES_PATIENT, TODDLER_JONES_SCREENINGS, TODDLER_JONES_ID)
    checks = {
        "status_success": result["status"] == "success",
        "has_due_screenings": result["data"]["has_gaps"] is True,
    }
    # Check that autism screening is in the due list
    due_names = [s["screening"].lower() for s in result["data"]["due"]]
    checks["autism_screen_due"] = any("autism" in n for n in due_names)

    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="dev_toddler_autism_screen_due",
        verdict=Verdict.PASS if checks["autism_screen_due"] else Verdict.FAIL,
        score=score,
        details={**checks, "due_screenings": due_names},
    )


@suite.case("dev_child_all_missed", "Child Smith has all developmental screenings missed", "fhir_tools")
def bench_dev_child_all_missed():
    result = _run_developmental_screening(CHILD_SMITH_PATIENT, CHILD_SMITH_SCREENINGS, CHILD_SMITH_ID)
    checks = {
        "status_success": result["status"] == "success",
        "has_gaps": result["data"]["has_gaps"] is True,
        "many_due": len(result["data"]["due"]) >= 8,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="dev_child_all_missed",
        verdict=Verdict.PASS if score >= 0.66 else Verdict.FAIL,
        score=score,
        details={**checks, "due_count": len(result["data"]["due"])},
    )
