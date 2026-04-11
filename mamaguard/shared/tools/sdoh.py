"""
SDOH FHIR tools -- social determinants of health screening.

Tools:
    get_sdoh_screening    SDOH conditions (Z-codes), coverage, language barriers
"""

import logging

import httpx
from google.adk.tools import ToolContext

from .fhir_base import (
    _coding_display,
    _connection_error_result,
    _fhir_get,
    _get_fhir_context,
    _http_error_result,
)

logger = logging.getLogger(__name__)

# SNOMED codes mapping to ICD Z55-Z65 SDOH domains
_SDOH_SNOMED_CODES = {
    "73595000": "stress",
    "160903007": "full_time_employment",
    "160904001": "unemployed",
    "105531004": "housing_problem",
    "Finding of inadequate food supply (finding)": "food_insecurity",
    "423315002": "limited_english",
    "266948004": "no_family_support",
}


def get_sdoh_screening(tool_context: ToolContext = None) -> dict:
    """
    Screen for social determinants of health from FHIR data.

    Checks:
    1. Condition resources for SDOH-related codes (Z55-Z65 equivalents)
    2. Coverage resources for insurance status and gaps
    3. Patient.communication for language barriers

    No external API calls -- uses FHIR data only.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_sdoh_screening patient_id=%s", patient_id)

    result = {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "sdoh_conditions": [],
            "coverage": [],
            "language": None,
            "risk_factors": [],
        },
    }

    # 1. Get patient demographics (for language)
    try:
        patient = _fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
        for comm in patient.get("communication", []):
            lang = comm.get("language", {})
            lang_text = lang.get("text") or _coding_display(lang.get("coding", []))
            if lang_text and lang_text.lower() not in ("english", "en"):
                result["data"]["language"] = lang_text
                result["data"]["risk_factors"].append(
                    f"Language barrier: primary language is {lang_text}"
                )
            elif lang_text:
                result["data"]["language"] = lang_text
    except Exception as e:
        logger.warning("sdoh_patient_fetch_failed: %s", e)

    # 2. Check all conditions for SDOH-related codes
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Condition",
            params={"patient": patient_id, "_count": "100"},
        )
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            code = res.get("code", {})
            codings = code.get("coding", [])
            condition_text = code.get("text") or _coding_display(codings)

            # Check for Z-code equivalent SNOMED codes or text matches
            is_sdoh = False
            for c in codings:
                snomed = c.get("code", "")
                if snomed in _SDOH_SNOMED_CODES:
                    is_sdoh = True
                    break
            # Also check text-based matching for common SDOH conditions
            sdoh_keywords = [
                "stress", "unemploy", "homeless", "housing", "food",
                "poverty", "education", "social isolation", "abuse",
                "neglect", "refugee", "immigration",
            ]
            if not is_sdoh:
                lower_text = condition_text.lower()
                is_sdoh = any(kw in lower_text for kw in sdoh_keywords)

            if is_sdoh:
                result["data"]["sdoh_conditions"].append({
                    "condition": condition_text,
                    "resource_id": res.get("id", ""),
                    "clinical_status": (
                        (res.get("clinicalStatus") or {}).get("coding", [{}])[0].get("code", "")
                    ),
                })
                result["data"]["risk_factors"].append(f"SDOH condition: {condition_text}")
    except Exception as e:
        logger.warning("sdoh_conditions_fetch_failed: %s", e)

    # 3. Check insurance coverage
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Coverage",
            params={"beneficiary": f"Patient/{patient_id}", "_count": "10"},
        )
        entries = bundle.get("entry", [])
        if not entries:
            result["data"]["coverage"] = []
            result["data"]["risk_factors"].append(
                "No insurance coverage found -- potential uninsured patient"
            )
        else:
            for entry in entries:
                res = entry.get("resource", {})
                coverage_type = (res.get("type") or {}).get("text") or _coding_display(
                    (res.get("type") or {}).get("coding", [])
                )
                period = res.get("period", {})
                result["data"]["coverage"].append({
                    "type": coverage_type,
                    "status": res.get("status"),
                    "period_start": period.get("start"),
                    "period_end": period.get("end"),
                    "resource_id": res.get("id", ""),
                })
    except Exception as e:
        logger.warning("sdoh_coverage_fetch_failed: %s", e)
        result["data"]["risk_factors"].append("Unable to check coverage status")

    # Determine clinician review need
    has_coverage_gap = len(result["data"]["coverage"]) == 0
    has_language_barrier = result["data"]["language"] and result["data"]["language"].lower() not in ("english", "en")
    has_sdoh_conditions = len(result["data"]["sdoh_conditions"]) > 0

    clinician_required = has_coverage_gap or (has_sdoh_conditions and has_coverage_gap)

    evidence = []
    if has_coverage_gap:
        evidence.append("No Coverage resources found for patient")
    if has_language_barrier:
        evidence.append(f"Patient primary language: {result['data']['language']}")
    for sc in result["data"]["sdoh_conditions"]:
        evidence.append(f"Condition/{sc['resource_id']} ({sc['condition']})")

    result["clinician_review"] = {
        "required": clinician_required,
        "reason": "Insurance coverage gap detected -- may affect medication access and care continuity" if has_coverage_gap else "",
        "recommendation": "Verify insurance status; consider Medicaid enrollment or community health resources" if has_coverage_gap else "",
        "evidence_basis": evidence,
        "confidence": 0.8,
    }

    return result
