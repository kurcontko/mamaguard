"""
FHIR tool accuracy benchmarks — Maternal tools.

Inspired by FHIR-AgentBench: tests whether tools correctly extract,
interpret, and flag clinical data from FHIR resources.
"""

from unittest.mock import patch

from benchmarks.base import BenchmarkResult, BenchmarkSuite, MockToolContext, Verdict
from benchmarks.fixtures.maternal import (
    ELENA_BP_BUNDLE,
    ELENA_HBA1C_BUNDLE,
    ELENA_GLUCOSE_BUNDLE,
    ELENA_PATIENT_ID,
    ELENA_PREGNANCY_BUNDLES,
    MARIA_BP_BUNDLE,
    MARIA_CONDITIONS_BUNDLE,
    MARIA_HBA1C_BUNDLE,
    MARIA_GLUCOSE_BUNDLE,
    MARIA_MEDICATIONS_BUNDLE,
    MARIA_PATIENT,
    MARIA_PATIENT_ID,
    MARIA_PREGNANCY_BUNDLES,
    MARIA_VITALS_BUNDLE,
    SARAH_BP_BUNDLE,
    SARAH_HBA1C_BUNDLE,
    SARAH_GLUCOSE_BUNDLE,
    SARAH_PATIENT_ID,
    SARAH_PREGNANCY_BUNDLES,
)

suite = BenchmarkSuite(
    name="fhir_maternal",
    description="Maternal FHIR tool accuracy — BP, glucose, pregnancy, risk profile",
)


# -- BP Trend Benchmarks ------------------------------------------------------

def _run_bp_trend(bp_bundle: dict, patient_id: str) -> dict:
    from mamaguard.shared.tools.maternal import get_bp_trend

    with patch("mamaguard.shared.tools.maternal._fhir_get") as mock:
        mock.return_value = bp_bundle
        ctx = MockToolContext(patient_id=patient_id)
        return get_bp_trend(tool_context=ctx)


@suite.case("bp_severe_detection", "Detect Stage 2 HTN (>160/110) in Maria's readings", "fhir_tools")
def bench_bp_severe_detection():
    result = _run_bp_trend(MARIA_BP_BUNDLE, MARIA_PATIENT_ID)
    checks = {
        "status_success": result["status"] == "success",
        "alert_severe": result["data"]["alert_severe"] is True,
        "alert_elevated": result["data"]["alert_elevated"] is True,
        "clinician_review_required": result["clinician_review"]["required"] is True,
        "has_evidence": len(result["clinician_review"]["evidence_basis"]) > 0,
        "reading_count": result["data"]["count"] == 6,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="bp_severe_detection",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("bp_trend_increasing", "Detect increasing BP trend in Maria", "fhir_tools")
def bench_bp_trend_increasing():
    result = _run_bp_trend(MARIA_BP_BUNDLE, MARIA_PATIENT_ID)
    trend = result["data"]["trend"]
    checks = {
        "trend_detected": trend in ("increasing", "stable"),  # increasing is ideal
        "trend_is_increasing": trend == "increasing",
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="bp_trend_increasing",
        verdict=Verdict.PASS if checks["trend_is_increasing"] else Verdict.FAIL,
        score=score,
        details={"trend": trend, **checks},
    )


@suite.case("bp_normal_no_alert", "No alerts for Sarah's normal BP", "fhir_tools")
def bench_bp_normal():
    result = _run_bp_trend(SARAH_BP_BUNDLE, SARAH_PATIENT_ID)
    checks = {
        "status_success": result["status"] == "success",
        "no_elevated": result["data"]["alert_elevated"] is False,
        "no_severe": result["data"]["alert_severe"] is False,
        "no_clinician_review": result["clinician_review"]["required"] is False,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="bp_normal_no_alert",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("bp_rapid_deterioration", "Detect rapid BP deterioration in Elena (preeclampsia)", "fhir_tools")
def bench_bp_rapid_deterioration():
    result = _run_bp_trend(ELENA_BP_BUNDLE, ELENA_PATIENT_ID)
    checks = {
        "alert_severe": result["data"]["alert_severe"] is True,
        "clinician_review_required": result["clinician_review"]["required"] is True,
        "trend_increasing": result["data"]["trend"] == "increasing",
        "high_confidence": result["clinician_review"]["confidence"] >= 0.9,
        "evidence_count": len(result["clinician_review"]["evidence_basis"]) >= 2,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="bp_rapid_deterioration",
        verdict=Verdict.PASS if score >= 0.8 else Verdict.FAIL,
        score=score,
        details=checks,
    )


# -- Glucose Trend Benchmarks --------------------------------------------------

def _run_glucose_trend(hba1c_bundle: dict, glucose_bundle: dict, patient_id: str) -> dict:
    from mamaguard.shared.tools.maternal import get_glucose_trend

    def side_effect(fhir_url, token, path, params=None):
        code = params.get("code", "")
        if "4548-4" in code:
            return hba1c_bundle
        return glucose_bundle

    with patch("mamaguard.shared.tools.maternal._fhir_get") as mock:
        mock.side_effect = side_effect
        ctx = MockToolContext(patient_id=patient_id)
        return get_glucose_trend(tool_context=ctx)


@suite.case("glucose_diabetes_detection", "Detect diabetes-range HbA1c in Maria", "fhir_tools")
def bench_glucose_diabetes():
    result = _run_glucose_trend(MARIA_HBA1C_BUNDLE, MARIA_GLUCOSE_BUNDLE, MARIA_PATIENT_ID)
    checks = {
        "status_success": result["status"] == "success",
        "diabetes_range": result["data"]["diabetes_range"] is True,
        "clinician_review": result["clinician_review"]["required"] is True,
        "hba1c_count": len(result["data"]["hba1c_readings"]) == 3,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="glucose_diabetes_detection",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("glucose_normal", "No diabetes flag for Sarah's normal HbA1c", "fhir_tools")
def bench_glucose_normal():
    result = _run_glucose_trend(SARAH_HBA1C_BUNDLE, SARAH_GLUCOSE_BUNDLE, SARAH_PATIENT_ID)
    checks = {
        "status_success": result["status"] == "success",
        "no_diabetes": result["data"]["diabetes_range"] is False,
        "no_review": result["clinician_review"]["required"] is False,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="glucose_normal",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


# -- Pregnancy History Benchmarks -----------------------------------------------

def _run_pregnancy_history(pregnancy_bundles: dict, patient_id: str) -> dict:
    from mamaguard.shared.tools.maternal import get_pregnancy_history

    def side_effect(fhir_url, token, path, params=None):
        code = params.get("code", "")
        for snomed, bundle in pregnancy_bundles.items():
            if snomed in code:
                return bundle
        return {"resourceType": "Bundle", "entry": []}

    with patch("mamaguard.shared.tools.maternal._fhir_get") as mock:
        mock.side_effect = side_effect
        ctx = MockToolContext(patient_id=patient_id)
        return get_pregnancy_history(tool_context=ctx)


@suite.case("pregnancy_recurrent_loss", "Detect recurrent pregnancy loss in Maria", "fhir_tools")
def bench_pregnancy_recurrent_loss():
    result = _run_pregnancy_history(MARIA_PREGNANCY_BUNDLES, MARIA_PATIENT_ID)
    checks = {
        "status_success": result["status"] == "success",
        "total_pregnancies": result["data"]["total_count"] == 6,
        "live_births": result["data"]["live_births"] == 1,
        "losses_detected": result["data"]["losses"] == 5,
        "high_risk_flag": result["data"]["high_risk"] is True,
        "clinician_review": result["clinician_review"]["required"] is True,
        "recurrent_in_reason": "Recurrent" in result["clinician_review"]["reason"],
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="pregnancy_recurrent_loss",
        verdict=Verdict.PASS if score >= 0.85 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("pregnancy_healthy_history", "No high-risk flag for Sarah's single healthy pregnancy", "fhir_tools")
def bench_pregnancy_healthy():
    result = _run_pregnancy_history(SARAH_PREGNANCY_BUNDLES, SARAH_PATIENT_ID)
    checks = {
        "status_success": result["status"] == "success",
        "live_births": result["data"]["live_births"] == 1,
        "no_losses": result["data"]["losses"] == 0,
        "not_high_risk": result["data"]["high_risk"] is False,
        "no_review": result["clinician_review"]["required"] is False,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="pregnancy_healthy_history",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


# -- Compound Risk Profile Benchmarks ------------------------------------------

@suite.case("risk_profile_urgent", "Maria's compound risk profile should be URGENT or HIGH", "fhir_tools")
def bench_risk_profile_urgent():
    from mamaguard.shared.tools.maternal import get_maternal_risk_profile

    with patch("mamaguard.shared.tools.maternal.get_bp_trend") as mock_bp, \
         patch("mamaguard.shared.tools.maternal.get_glucose_trend") as mock_glu, \
         patch("mamaguard.shared.tools.maternal.get_pregnancy_history") as mock_preg:

        mock_bp.return_value = {
            "status": "success",
            "data": {"alert_elevated": True, "alert_severe": True, "readings": [], "count": 6, "trend": "increasing"},
            "clinician_review": {"required": True, "reason": "Stage 2 HTN", "evidence_basis": ["Observation/bp-m5"]},
        }
        mock_glu.return_value = {
            "status": "success",
            "data": {"diabetes_range": True, "poorly_controlled": False, "glucose_readings": [], "hba1c_readings": [], "hba1c_trend": "increasing"},
            "clinician_review": {"required": True, "reason": "HbA1c >6.5%", "evidence_basis": ["Observation/hba1c-m1"]},
        }
        mock_preg.return_value = {
            "status": "success",
            "data": {"high_risk": True, "losses": 5, "live_births": 1, "total_count": 6, "pregnancies": []},
            "clinician_review": {"required": True, "reason": "Recurrent loss", "evidence_basis": ["Condition/preg-m2"]},
        }

        ctx = MockToolContext(patient_id=MARIA_PATIENT_ID)
        result = get_maternal_risk_profile(tool_context=ctx)

    checks = {
        "status_success": result["status"] == "success",
        "risk_urgent": result["data"]["risk_level"] == "URGENT",
        "has_risk_factors": len(result["data"]["risk_factors"]) >= 2,
        "clinician_review": result["clinician_review"]["required"] is True,
        "evidence_aggregated": len(result["clinician_review"]["evidence_basis"]) >= 3,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="risk_profile_urgent",
        verdict=Verdict.PASS if score >= 0.8 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("risk_profile_routine", "Sarah should have ROUTINE risk level", "fhir_tools")
def bench_risk_profile_routine():
    from mamaguard.shared.tools.maternal import get_maternal_risk_profile

    with patch("mamaguard.shared.tools.maternal.get_bp_trend") as mock_bp, \
         patch("mamaguard.shared.tools.maternal.get_glucose_trend") as mock_glu, \
         patch("mamaguard.shared.tools.maternal.get_pregnancy_history") as mock_preg:

        mock_bp.return_value = {
            "status": "success",
            "data": {"alert_elevated": False, "alert_severe": False, "readings": [], "count": 4, "trend": "stable"},
            "clinician_review": {"required": False, "reason": "", "evidence_basis": []},
        }
        mock_glu.return_value = {
            "status": "success",
            "data": {"diabetes_range": False, "poorly_controlled": False, "glucose_readings": [], "hba1c_readings": [], "hba1c_trend": "stable"},
            "clinician_review": {"required": False, "reason": "", "evidence_basis": []},
        }
        mock_preg.return_value = {
            "status": "success",
            "data": {"high_risk": False, "losses": 0, "live_births": 1, "total_count": 1, "pregnancies": []},
            "clinician_review": {"required": False, "reason": "", "evidence_basis": []},
        }

        ctx = MockToolContext(patient_id=SARAH_PATIENT_ID)
        result = get_maternal_risk_profile(tool_context=ctx)

    checks = {
        "risk_routine": result["data"]["risk_level"] == "ROUTINE",
        "no_risk_factors": len(result["data"]["risk_factors"]) == 0,
        "no_review": result["clinician_review"]["required"] is False,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="risk_profile_routine",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )
