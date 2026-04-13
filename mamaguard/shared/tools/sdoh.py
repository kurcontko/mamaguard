"""
SDOH FHIR tools -- social determinants of health screening + actionable
resource lookup.

Tools:
    get_sdoh_screening    SDOH conditions (Z-codes), coverage, language barriers
    find_sdoh_resources   Z-code/category + ZIP → concrete, callable resources
"""

import logging
import os

import httpx
from google.adk.tools import ToolContext

from ..sdoh_resources import (
    GENERIC_211,
    classify_category,
    curated_resources,
)
from .cache import cached_tool
from .fhir_base import (
    _bundle_resources,
    _clinician_review,
    _coding_display,
    _get_fhir_context,
    _safe_fhir_get,
    _silent_fhir_get,
)

logger = logging.getLogger(__name__)

# External SDOH resource directory -- optional. When set, find_sdoh_resources
# tries this endpoint first (e.g. findhelp.org, 211 API gateway, a state-run
# resource directory). On any failure we fall back to the curated offline
# list in mamaguard/shared/sdoh_resources.py so the agent stays actionable.
_SDOH_API_URL_ENV = "MAMAGUARD_SDOH_API_URL"
_SDOH_API_KEY_ENV = "MAMAGUARD_SDOH_API_KEY"
_SDOH_API_TIMEOUT = 5  # seconds -- short, we have a good fallback

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


@cached_tool
def get_sdoh_screening(tool_context: ToolContext | None = None) -> dict:
    """
    Screen for social determinants of health from FHIR data.

    Checks:
    1. Condition resources for SDOH-related codes (Z55-Z65 equivalents)
    2. Coverage resources for insurance status and gaps
    3. Patient.communication for language barriers

    No external API calls -- uses FHIR data only.
    """
    ctx = _get_fhir_context(tool_context, "get_sdoh_screening")
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
    patient, _err = _safe_fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
    if patient:
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

    # 2. Check all conditions for SDOH-related codes
    sdoh_keywords = [
        "stress", "unemploy", "homeless", "housing", "food",
        "poverty", "education", "social isolation", "abuse",
        "neglect", "refugee", "immigration",
    ]
    for res in _silent_fhir_get(fhir_url, fhir_token, "Condition",
                                params={"patient": patient_id, "_count": "100"}):
        code = res.get("code", {})
        codings = code.get("coding", [])
        condition_text = code.get("text") or _coding_display(codings)

        is_sdoh = any(c.get("code", "") in _SDOH_SNOMED_CODES for c in codings)
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

    # 3. Check insurance coverage
    coverage_bundle, coverage_err = _safe_fhir_get(
        fhir_url, fhir_token, "Coverage",
        params={"beneficiary": f"Patient/{patient_id}", "_count": "10"},
    )
    if coverage_err:
        logger.warning("sdoh_coverage_fetch_failed")
        result["data"]["risk_factors"].append("Unable to check coverage status")
    else:
        coverage_resources = _bundle_resources(coverage_bundle)
        if not coverage_resources:
            result["data"]["risk_factors"].append(
                "No insurance coverage found -- potential uninsured patient"
            )
        for res in coverage_resources:
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

    result["clinician_review"] = _clinician_review(
        clinician_required,
        reason="Insurance coverage gap detected -- may affect medication access and care continuity" if has_coverage_gap else "",
        recommendation="Verify insurance status; consider Medicaid enrollment or community health resources" if has_coverage_gap else "",
        evidence=evidence,
        confidence=0.8,
    )

    return result


# ---------------------------------------------------------------------------
# find_sdoh_resources -- actionable lookup
# ---------------------------------------------------------------------------


def _fetch_external_resources(
    api_url: str,
    api_key: str,
    category: str,
    zip_code: str,
) -> list[dict]:
    """
    Call an external resource directory (findhelp.org / 211 gateway).

    Expected contract: GET {api_url}?category={category}&zip={zip_code}
    returning `{ "resources": [ {name, contact, url, description, ...} ] }`.

    Kept intentionally minimal: real integrations will customize the
    query shape, but every integration we've looked at publishes
    category + ZIP as the primary lookup. Errors propagate -- caller
    decides whether to fall back.
    """
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = httpx.get(
        api_url,
        params={"category": category, "zip": zip_code},
        headers=headers,
        timeout=_SDOH_API_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    resources = payload.get("resources") or payload.get("results") or []
    # Normalize to our internal shape. Accept either findhelp-ish or
    # 211-ish field names so either directory works without a new tool.
    normalized: list[dict] = []
    for r in resources:
        if not isinstance(r, dict):
            continue
        normalized.append({
            "name": r.get("name") or r.get("program_name") or "Unnamed resource",
            "contact": (
                r.get("contact")
                or r.get("phone")
                or r.get("phone_number")
                or ""
            ),
            "url": r.get("url") or r.get("website") or "",
            "description": r.get("description") or r.get("summary") or "",
            "category": category,
            "distance_miles": r.get("distance_miles") or r.get("distance"),
            "address": r.get("address") or r.get("street_address"),
        })
    return normalized


def find_sdoh_resources(
    category_or_code: str,
    zip_code: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Look up concrete SDOH resources for a Z-code / category + ZIP.

    Primary path: external directory set via `MAMAGUARD_SDOH_API_URL`
    (e.g. findhelp.org or a 211 API gateway). Falls back to a curated
    offline list of national hotlines and federal programs whenever the
    API is unconfigured, down, times out, or returns zero resources --
    so the SDOH agent is *always* actionable.

    Args:
        category_or_code: ICD-10 Z-code (e.g. "Z59.0"), SNOMED code, or a
            plain-English category ("housing", "food", "transportation").
        zip_code: Patient ZIP -- used verbatim by the external directory;
            ignored by the offline fallback beyond being echoed back.

    Returns:
        {
            "status": "success",
            "category": "housing",
            "zip": "02139",
            "source": "external"|"curated"|"curated_fallback"|"generic_211",
            "resources": [ {name, contact, url, description, category}, ... ],
            "clinician_review": { required, reason, evidence_basis, ... },
        }
    """
    if not category_or_code:
        return {
            "status": "error",
            "error_message": "category_or_code is required",
        }

    category = classify_category(category_or_code)
    normalized_zip = (zip_code or "").strip()

    logger.info(
        "tool_find_sdoh_resources input=%s category=%s zip=%s",
        category_or_code, category, normalized_zip,
    )

    api_url = os.environ.get(_SDOH_API_URL_ENV, "").strip()
    api_key = os.environ.get(_SDOH_API_KEY_ENV, "").strip()

    resources: list[dict] = []
    source = ""
    external_error: str | None = None

    # 1. Try external directory if configured.
    if api_url and category:
        try:
            resources = _fetch_external_resources(
                api_url, api_key, category, normalized_zip,
            )
            if resources:
                source = "external"
            else:
                external_error = "external directory returned zero resources"
        except Exception as e:
            external_error = f"{type(e).__name__}: {e}"
            logger.warning(
                "sdoh_external_lookup_failed category=%s zip=%s err=%s",
                category, normalized_zip, external_error,
            )

    # 2. Curated offline fallback.
    if not resources and category:
        resources = curated_resources(category)
        source = "curated_fallback" if external_error else "curated"

    # 3. Generic 211 if still empty (unknown category).
    if not resources:
        resources = [dict(GENERIC_211)]
        source = "generic_211"
        if not category:
            category = "general"

    # Stamp every resource with the ZIP so the agent can echo it back to
    # the clinician without re-assembling the context later.
    for r in resources:
        r.setdefault("zip", normalized_zip)

    evidence = [f"Input: {category_or_code}"]
    if normalized_zip:
        evidence.append(f"ZIP: {normalized_zip}")
    evidence.append(f"Resolved category: {category}")
    evidence.append(f"Resource source: {source}")
    if external_error:
        evidence.append(f"External lookup error: {external_error}")

    return {
        "status": "success",
        "category": category,
        "zip": normalized_zip,
        "source": source,
        "resource_count": len(resources),
        "resources": resources,
        "clinician_review": _clinician_review(
            True,
            reason=(
                "SDOH resource referral recommended -- clinician should "
                "review match and initiate outreach."
            ),
            recommendation=(
                "Record the selected resource on a FHIR CarePlan + Goal "
                "via write_care_plan so the care team has a trackable "
                "intervention tied to the patient record."
            ),
            evidence=evidence,
            confidence=0.75 if source in ("external", "curated") else 0.6,
        ),
    }
