"""
FHIR tool accuracy benchmarks — SDOH tools.

Tests social determinants screening: language barriers, insurance gaps,
SDOH condition detection.
"""

from unittest.mock import patch

from benchmarks.base import BenchmarkResult, BenchmarkSuite, MockToolContext, Verdict
from benchmarks.fixtures.sdoh import (
    FATIMA_SDOH_CONDITIONS,
    FATIMA_SDOH_COVERAGE,
    FATIMA_SDOH_PATIENT,
    FATIMA_SDOH_PATIENT_ID,
    JAMES_SDOH_CONDITIONS,
    JAMES_SDOH_COVERAGE,
    JAMES_SDOH_PATIENT,
    JAMES_SDOH_PATIENT_ID,
    MARIA_SDOH_CONDITIONS,
    MARIA_SDOH_COVERAGE,
    MARIA_SDOH_PATIENT,
    MARIA_SDOH_PATIENT_ID,
)

suite = BenchmarkSuite(
    name="fhir_sdoh",
    description="SDOH FHIR tool accuracy — language, coverage, social conditions",
)


def _run_sdoh_screening(patient: dict, conditions: dict, coverage: dict, patient_id: str) -> dict:
    from mamaguard.shared.tools.sdoh import get_sdoh_screening

    def side_effect(fhir_url, token, path, params=None):
        if path == f"Patient/{patient_id}":
            return patient
        if path == "Condition":
            return conditions
        if path == "Coverage":
            return coverage
        return {"resourceType": "Bundle", "entry": []}

    with patch("mamaguard.shared.tools.sdoh._fhir_get") as mock:
        mock.side_effect = side_effect
        ctx = MockToolContext(patient_id=patient_id)
        return get_sdoh_screening(tool_context=ctx)


@suite.case("sdoh_maria_uninsured_french", "Detect Maria's language barrier + coverage gap", "fhir_tools")
def bench_sdoh_maria():
    result = _run_sdoh_screening(
        MARIA_SDOH_PATIENT, MARIA_SDOH_CONDITIONS, MARIA_SDOH_COVERAGE, MARIA_SDOH_PATIENT_ID,
    )
    checks = {
        "status_success": result["status"] == "success",
        "language_detected": result["data"]["language"] == "French",
        "language_barrier_risk": any("language" in rf.lower() for rf in result["data"]["risk_factors"]),
        "no_coverage": len(result["data"]["coverage"]) == 0,
        "coverage_gap_risk": any("insurance" in rf.lower() or "coverage" in rf.lower() or "uninsured" in rf.lower()
                                 for rf in result["data"]["risk_factors"]),
        "sdoh_conditions_found": len(result["data"]["sdoh_conditions"]) >= 2,
        "clinician_review": result["clinician_review"]["required"] is True,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="sdoh_maria_uninsured_french",
        verdict=Verdict.PASS if score >= 0.85 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("sdoh_james_no_risk", "No SDOH risk factors for insured English-speaking James", "fhir_tools")
def bench_sdoh_james():
    result = _run_sdoh_screening(
        JAMES_SDOH_PATIENT, JAMES_SDOH_CONDITIONS, JAMES_SDOH_COVERAGE, JAMES_SDOH_PATIENT_ID,
    )
    checks = {
        "status_success": result["status"] == "success",
        "language_english": result["data"]["language"] == "English",
        "no_language_barrier": not any("language" in rf.lower() and "barrier" in rf.lower()
                                       for rf in result["data"]["risk_factors"]),
        "has_coverage": len(result["data"]["coverage"]) >= 1,
        "no_sdoh_conditions": len(result["data"]["sdoh_conditions"]) == 0,
        "no_clinician_review": result["clinician_review"]["required"] is False,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="sdoh_james_no_risk",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("sdoh_fatima_complex", "Detect Fatima's complex SDOH: Arabic + unemployed + food insecurity", "fhir_tools")
def bench_sdoh_fatima():
    result = _run_sdoh_screening(
        FATIMA_SDOH_PATIENT, FATIMA_SDOH_CONDITIONS, FATIMA_SDOH_COVERAGE, FATIMA_SDOH_PATIENT_ID,
    )
    checks = {
        "status_success": result["status"] == "success",
        "language_arabic": result["data"]["language"] == "Arabic",
        "language_barrier": any("language" in rf.lower() for rf in result["data"]["risk_factors"]),
        "sdoh_conditions_found": len(result["data"]["sdoh_conditions"]) >= 2,
        "has_medicaid": len(result["data"]["coverage"]) >= 1,
        "food_insecurity_detected": any("food" in sc["condition"].lower()
                                         for sc in result["data"]["sdoh_conditions"]),
        "unemployment_detected": any("unemploy" in sc["condition"].lower()
                                      for sc in result["data"]["sdoh_conditions"]),
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="sdoh_fatima_complex",
        verdict=Verdict.PASS if score >= 0.85 else Verdict.FAIL,
        score=score,
        details=checks,
    )
