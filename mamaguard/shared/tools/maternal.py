"""
Maternal FHIR tools -- specialized queries for maternal health assessment.

Tools:
    get_bp_trend           Blood pressure readings with trend analysis
    get_glucose_trend      Glucose + HbA1c readings with trend analysis
    get_pregnancy_history  All pregnancies with outcomes and complications
    get_maternal_risk_profile  Compound query combining conditions, obs, meds
"""

import logging
from datetime import datetime, timedelta

from google.adk.tools import ToolContext

from .cache import cached_tool
from .fhir_base import (
    _bundle_resources,
    _clinician_review,
    _coding_display,
    _get_fhir_context,
    _safe_fhir_get,
)

logger = logging.getLogger(__name__)


def _parse_bp_components(resource: dict) -> dict | None:
    """Extract systolic/diastolic from a BP Observation with components."""
    systolic = None
    diastolic = None
    for comp in resource.get("component", []):
        coding = comp.get("code", {}).get("coding", [])
        vq = comp.get("valueQuantity", {})
        for c in coding:
            code = c.get("code", "")
            if code == "8480-6":  # systolic LOINC
                systolic = vq.get("value")
            elif code == "8462-4":  # diastolic LOINC
                diastolic = vq.get("value")
    if systolic is not None and diastolic is not None:
        return {"systolic": systolic, "diastolic": diastolic}
    return None


def _compute_trend(values: list[float], threshold: float = 2.0) -> str:
    """Simple trend: compare first half average to second half average.

    Args:
        values: Numeric readings in chronological order.
        threshold: Minimum absolute difference to consider non-stable.
            Default 2.0 suits BP (mmHg). Use 0.3 for HbA1c (%) where
            a smaller delta is clinically significant.
    """
    if len(values) < 2:
        return "insufficient_data"
    mid = len(values) // 2
    first_half = sum(values[:mid]) / mid
    second_half = sum(values[mid:]) / (len(values) - mid)
    diff = second_half - first_half
    if abs(diff) < threshold:
        return "stable"
    return "increasing" if diff > 0 else "decreasing"


@cached_tool
def get_bp_trend(months_back: int = 24, tool_context: ToolContext | None = None) -> dict:
    """
    Get blood pressure trend for maternal monitoring.

    Queries Observation resources with LOINC code 55284-4 (Blood pressure panel)
    sorted by date. Returns readings, trend direction, and alert flag if any
    reading exceeds 140/90 mmHg.

    Args:
        months_back: How many months of history to retrieve (default 24).
    """
    ctx = _get_fhir_context(tool_context, "get_bp_trend")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_bp_trend patient_id=%s months_back=%d", patient_id, months_back)

    bundle, err = _safe_fhir_get(
        fhir_url, fhir_token, "Observation",
        params={
            "patient": patient_id,
            "code": "http://loinc.org|55284-4",
            "_sort": "-date",
            "_count": "50",
        },
    )
    if err:
        return err

    readings = []
    cutoff = datetime.now() - timedelta(days=months_back * 30)

    for res in _bundle_resources(bundle):
        date_str = res.get("effectiveDateTime", "")
        bp = _parse_bp_components(res)
        if not bp:
            continue

        # Filter by date if we can parse it
        if date_str:
            try:
                obs_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if obs_date.replace(tzinfo=None) < cutoff:
                    continue
            except (ValueError, TypeError):
                pass

        readings.append({
            "date": date_str,
            "systolic": bp["systolic"],
            "diastolic": bp["diastolic"],
            "resource_id": res.get("id", ""),
        })

    # Compute trend and alerts
    systolic_values = [r["systolic"] for r in readings if r["systolic"] is not None]
    has_elevated = any(r["systolic"] > 140 or r["diastolic"] > 90 for r in readings)
    has_severe = any(r["systolic"] > 160 or r["diastolic"] > 110 for r in readings)

    trend = _compute_trend(systolic_values)

    clinician_review_required = has_elevated
    review_reason = ""
    if has_severe:
        review_reason = "Stage 2 hypertension detected (>160/110 mmHg) — immediate review needed"
    elif has_elevated:
        review_reason = "Elevated BP readings detected (>140/90 mmHg) — monitor closely"

    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "readings": readings,
            "count": len(readings),
            "trend": trend,
            "alert_elevated": has_elevated,
            "alert_severe": has_severe,
        },
        "clinician_review": _clinician_review(
            clinician_review_required,
            reason=review_reason,
            recommendation="Review BP management and consider medication adjustment" if has_elevated else "",
            evidence=[
                f"Observation/{r['resource_id']} (BP {r['systolic']}/{r['diastolic']} on {r['date']})"
                for r in readings if r["systolic"] > 140 or r["diastolic"] > 90
            ],
            confidence=0.9 if has_severe else 0.8 if has_elevated else 0.5,
        ),
    }


@cached_tool
def get_glucose_trend(months_back: int = 24, tool_context: ToolContext | None = None) -> dict:
    """
    Get glucose and HbA1c trend for maternal monitoring.

    Queries Observation resources with LOINC codes:
    - 2339-0 (Glucose [Mass/volume] in Blood)
    - 4548-4 (Hemoglobin A1c/Hemoglobin.total in Blood)

    Args:
        months_back: How many months of history to retrieve (default 24).
    """
    ctx = _get_fhir_context(tool_context, "get_glucose_trend")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_glucose_trend patient_id=%s months_back=%d", patient_id, months_back)

    glucose_readings: list[dict] = []
    hba1c_readings: list[dict] = []

    for loinc_code, target_list in [("2339-0", glucose_readings), ("4548-4", hba1c_readings)]:
        bundle, err = _safe_fhir_get(
            fhir_url, fhir_token, "Observation",
            params={
                "patient": patient_id,
                "code": f"http://loinc.org|{loinc_code}",
                "_sort": "-date",
                "_count": "20",
            },
        )
        if err:
            return err

        for res in _bundle_resources(bundle):
            vq = res.get("valueQuantity", {})
            if vq.get("value") is not None:
                target_list.append({
                    "date": res.get("effectiveDateTime", ""),
                    "value": vq["value"],
                    "unit": vq.get("unit") or vq.get("code", ""),
                    "resource_id": res.get("id", ""),
                })

    # Trend analysis — HbA1c uses a tighter threshold (0.3%) because a small
    # percentage-point shift is clinically meaningful (ADA guidelines).
    hba1c_values = [r["value"] for r in hba1c_readings]
    hba1c_trend = _compute_trend(hba1c_values, threshold=0.3)

    poorly_controlled = any(r["value"] > 6.5 for r in hba1c_readings)
    very_poorly_controlled = any(r["value"] > 9.0 for r in hba1c_readings)

    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "glucose_readings": glucose_readings,
            "hba1c_readings": hba1c_readings,
            "hba1c_trend": hba1c_trend,
            "diabetes_range": poorly_controlled,
            "poorly_controlled": very_poorly_controlled,
        },
        "clinician_review": _clinician_review(
            poorly_controlled,
            reason="HbA1c in diabetes range (>6.5%)" if poorly_controlled else "",
            recommendation="Review glycemic management" if poorly_controlled else "",
            evidence=[
                f"Observation/{r['resource_id']} (HbA1c {r['value']}% on {r['date']})"
                for r in hba1c_readings if r["value"] > 6.5
            ],
            confidence=0.85,
        ),
    }


@cached_tool
def get_pregnancy_history(tool_context: ToolContext | None = None) -> dict:
    """
    Get pregnancy history from FHIR Condition resources.

    Queries Condition resources with SNOMED codes:
    - 72892002 (Normal pregnancy)
    - 35999006 (Blighted ovum)
    - 19169002 (Miscarriage)
    - 156073000 (Fetal complication)

    Returns all pregnancies with outcomes, complications, and dates.
    """
    ctx = _get_fhir_context(tool_context, "get_pregnancy_history")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_pregnancy_history patient_id=%s", patient_id)

    pregnancy_snomeds = ["72892002", "35999006", "19169002", "156073000"]
    pregnancies = []

    for snomed in pregnancy_snomeds:
        bundle, err = _safe_fhir_get(
            fhir_url, fhir_token, "Condition",
            params={
                "patient": patient_id,
                "code": f"http://snomed.info/sct|{snomed}",
                "_count": "50",
            },
        )
        if err:
            return err

        for res in _bundle_resources(bundle):
            code = res.get("code", {})
            clinical_status = (
                (res.get("clinicalStatus") or {}).get("coding", [{}])[0].get("code", "")
            )
            onset = res.get("onsetDateTime") or (res.get("onsetPeriod") or {}).get("start")
            abatement = res.get("abatementDateTime") or (res.get("abatementPeriod") or {}).get("start")

            # Classify outcome
            condition_text = code.get("text") or _coding_display(code.get("coding", []))
            outcome = "unknown"
            if snomed == "72892002":
                outcome = "live_birth" if clinical_status == "resolved" else "ongoing"
            elif snomed == "35999006":
                outcome = "blighted_ovum"
            elif snomed == "19169002":
                outcome = "miscarriage"
            elif snomed == "156073000":
                outcome = "fetal_complication"

            pregnancies.append({
                "condition": condition_text,
                "snomed_code": snomed,
                "clinical_status": clinical_status,
                "outcome": outcome,
                "onset": onset,
                "abatement": abatement,
                "resource_id": res.get("id", ""),
            })

    # Sort by onset date
    pregnancies.sort(key=lambda p: p.get("onset") or "", reverse=True)

    loss_count = sum(1 for p in pregnancies if p["outcome"] in ("blighted_ovum", "miscarriage", "fetal_complication"))
    live_births = sum(1 for p in pregnancies if p["outcome"] == "live_birth")

    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "pregnancies": pregnancies,
            "total_count": len(pregnancies),
            "live_births": live_births,
            "losses": loss_count,
            "high_risk": loss_count >= 2,
        },
        "clinician_review": _clinician_review(
            loss_count >= 2,
            reason=f"Recurrent pregnancy loss ({loss_count} losses)" if loss_count >= 2 else "",
            recommendation="Review obstetric history for recurrent loss etiology" if loss_count >= 2 else "",
            evidence=[
                f"Condition/{p['resource_id']} ({p['condition']} — {p['outcome']}, onset {p['onset']})"
                for p in pregnancies if p["outcome"] in ("blighted_ovum", "miscarriage", "fetal_complication")
            ],
            confidence=0.9,
        ),
    }


@cached_tool
def get_maternal_risk_profile(tool_context: ToolContext | None = None) -> dict:
    """
    Get comprehensive maternal risk profile — compound query.

    Combines data from multiple FHIR resource types to produce a structured
    risk summary. Calls get_bp_trend, get_glucose_trend, and get_pregnancy_history
    internally and synthesizes the results.
    """
    ctx = _get_fhir_context(tool_context, "get_maternal_risk_profile")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_maternal_risk_profile patient_id=%s", patient_id)

    # Gather sub-results
    bp_result = get_bp_trend(months_back=24, tool_context=tool_context)
    glucose_result = get_glucose_trend(months_back=24, tool_context=tool_context)
    pregnancy_result = get_pregnancy_history(tool_context=tool_context)

    # Compute overall risk level
    risk_factors = []
    risk_level = "ROUTINE"

    if bp_result.get("status") == "success":
        bp_data = bp_result.get("data", {})
        if bp_data.get("alert_severe"):
            risk_factors.append("Stage 2 hypertension (>160/110)")
            risk_level = "URGENT"
        elif bp_data.get("alert_elevated"):
            risk_factors.append("Elevated BP (>140/90)")
            if risk_level not in ("URGENT",):
                risk_level = "HIGH"

    if glucose_result.get("status") == "success":
        glucose_data = glucose_result.get("data", {})
        if glucose_data.get("poorly_controlled"):
            risk_factors.append("Poorly controlled diabetes (HbA1c >9%)")
            if risk_level not in ("URGENT",):
                risk_level = "HIGH"
        elif glucose_data.get("diabetes_range"):
            risk_factors.append("Diabetes range HbA1c (>6.5%)")
            if risk_level == "ROUTINE":
                risk_level = "MODERATE"

    if pregnancy_result.get("status") == "success":
        preg_data = pregnancy_result.get("data", {})
        if preg_data.get("high_risk"):
            risk_factors.append(f"Recurrent pregnancy loss ({preg_data.get('losses', 0)} losses)")
            if risk_level == "ROUTINE":
                risk_level = "MODERATE"

    clinician_required = risk_level in ("URGENT", "HIGH")

    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "bp_summary": bp_result.get("data") if bp_result.get("status") == "success" else None,
            "glucose_summary": glucose_result.get("data") if glucose_result.get("status") == "success" else None,
            "pregnancy_summary": pregnancy_result.get("data") if pregnancy_result.get("status") == "success" else None,
        },
        "clinician_review": _clinician_review(
            clinician_required,
            reason=f"Risk level: {risk_level}. Factors: {'; '.join(risk_factors)}" if clinician_required else "",
            recommendation="Comprehensive maternal risk review recommended" if clinician_required else "",
            evidence=(
                bp_result.get("clinician_review", {}).get("evidence_basis", [])
                + glucose_result.get("clinician_review", {}).get("evidence_basis", [])
                + pregnancy_result.get("clinician_review", {}).get("evidence_basis", [])
            ),
            confidence=0.85,
        ),
    }
