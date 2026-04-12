"""
FHIR base tools -- query a FHIR R4 server on behalf of the patient in context.

Adapted from po-adk-python shared/tools/fhir.py. These tools read FHIR
credentials from tool_context.state (injected by fhir_hook.extract_fhir_context).
"""

import logging

import httpx
from google.adk.tools import ToolContext

from ..smart_tickets import enforce_smart_ticket

logger = logging.getLogger(__name__)

_FHIR_TIMEOUT = 15  # seconds


# -- Private helpers ----------------------------------------------------------

def _get_fhir_context(tool_context: ToolContext, tool_name: str = ""):
    """
    Read FHIR credentials from session state.
    Returns (fhir_url, fhir_token, patient_id) or error dict.

    When *tool_name* is provided and SMART Permission Tickets are enabled,
    validates that the session ticket grants the required scopes before
    returning credentials.
    """
    fhir_url = tool_context.state.get("fhir_url", "").rstrip("/")
    fhir_token = tool_context.state.get("fhir_token", "")
    patient_id = tool_context.state.get("patient_id", "")

    missing = [
        name for name, val in [
            ("fhir_url", fhir_url),
            ("fhir_token", fhir_token),
            ("patient_id", patient_id),
        ]
        if not val
    ]

    if missing:
        return {
            "status": "error",
            "error_message": (
                f"FHIR context is not available -- missing: {', '.join(missing)}. "
                "Ensure the caller includes 'fhir-context' in the A2A message metadata."
            ),
        }

    # SMART Permission Ticket scope enforcement (feature-flagged)
    if tool_name:
        scope_err = enforce_smart_ticket(tool_context.state, tool_name)
        if scope_err is not None:
            return scope_err

    return fhir_url, fhir_token, patient_id


def _fhir_get(fhir_url: str, token: str, path: str, params: dict | None = None) -> dict:
    """Perform an authenticated FHIR GET and return parsed JSON."""
    response = httpx.get(
        f"{fhir_url}/{path}",
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json",
        },
        timeout=_FHIR_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _http_error_result(exc: httpx.HTTPStatusError) -> dict:
    return {
        "status": "error",
        "http_status": exc.response.status_code,
        "error_message": f"FHIR server returned HTTP {exc.response.status_code}: {exc.response.text[:200]}",
    }


def _connection_error_result(exc: Exception) -> dict:
    return {
        "status": "error",
        "error_message": f"Could not reach FHIR server: {exc}",
    }


def _coding_display(codings: list) -> str:
    """Return the first human-readable display text from a list of FHIR codings."""
    for c in codings:
        if c.get("display"):
            return c["display"]
    return "Unknown"


# -- Tool: patient summary ---------------------------------------------------

def get_patient_summary(tool_context: ToolContext) -> dict:
    """
    Fetches a comprehensive summary of the current patient from the FHIR server.
    Returns demographics, active conditions, active medications, and recent vitals.
    No arguments required -- the patient identity comes from the session context.
    """
    ctx = _get_fhir_context(tool_context, "get_patient_summary")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_patient_summary patient_id=%s", patient_id)

    result = {"status": "success", "patient_id": patient_id}

    # Demographics
    try:
        patient = _fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
        names = patient.get("name", [])
        official = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
        given = " ".join(official.get("given", []))
        family = official.get("family", "")
        result["name"] = f"{given} {family}".strip() or "Unknown"
        result["birth_date"] = patient.get("birthDate")
        result["gender"] = patient.get("gender")

        contacts = [
            {"system": t.get("system"), "value": t.get("value"), "use": t.get("use")}
            for t in patient.get("telecom", [])
        ]
        result["contacts"] = contacts

        addrs = patient.get("address", [])
        if addrs:
            a = addrs[0]
            result["address"] = ", ".join(filter(None, [
                " ".join(a.get("line", [])),
                a.get("city"), a.get("state"), a.get("postalCode"), a.get("country"),
            ]))

        result["language"] = None
        for comm in patient.get("communication", []):
            lang = comm.get("language", {})
            result["language"] = lang.get("text") or _coding_display(lang.get("coding", []))
            break

        result["marital_status"] = (patient.get("maritalStatus") or {}).get("text")
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    # Active conditions
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Condition",
            params={"patient": patient_id, "clinical-status": "active", "_count": "50"},
        )
        conditions = []
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            code = res.get("code", {})
            onset = res.get("onsetDateTime") or (res.get("onsetPeriod") or {}).get("start")
            conditions.append({
                "condition": code.get("text") or _coding_display(code.get("coding", [])),
                "onset": onset,
            })
        result["active_conditions"] = conditions
    except Exception:
        result["active_conditions"] = []

    # Active medications
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "MedicationRequest",
            params={"patient": patient_id, "status": "active", "_count": "50"},
        )
        medications = []
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            med_concept = res.get("medicationCodeableConcept", {})
            med_name = (
                med_concept.get("text")
                or _coding_display(med_concept.get("coding", []))
                or res.get("medicationReference", {}).get("display", "Unknown")
            )
            dosage_list = [d.get("text", "No dosage text") for d in res.get("dosageInstruction", [])]
            medications.append({
                "medication": med_name,
                "dosage": dosage_list[0] if dosage_list else "Not specified",
            })
        result["active_medications"] = medications
    except Exception:
        result["active_medications"] = []

    # Recent vitals (last 10)
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Observation",
            params={"patient": patient_id, "category": "vital-signs", "_sort": "-date", "_count": "10"},
        )
        vitals = []
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            code = res.get("code", {})
            obs_name = code.get("text") or _coding_display(code.get("coding", []))

            value, unit = None, None
            if "valueQuantity" in res:
                vq = res["valueQuantity"]
                value = vq.get("value")
                unit = vq.get("unit") or vq.get("code")
            elif "valueCodeableConcept" in res:
                value = (res["valueCodeableConcept"].get("text")
                         or _coding_display(res["valueCodeableConcept"].get("coding", [])))

            components = []
            for comp in res.get("component", []):
                comp_code = comp.get("code") or {}
                comp_name = comp_code.get("text") or _coding_display(comp_code.get("coding", []))
                comp_vq = comp.get("valueQuantity", {})
                components.append({
                    "name": comp_name,
                    "value": comp_vq.get("value"),
                    "unit": comp_vq.get("unit") or comp_vq.get("code"),
                })

            vitals.append({
                "observation": obs_name,
                "value": value,
                "unit": unit,
                "components": components or None,
                "date": res.get("effectiveDateTime"),
            })
        result["recent_vitals"] = vitals
    except Exception:
        result["recent_vitals"] = []

    return result


# -- Tool: active medications ------------------------------------------------

def get_active_medications(tool_context: ToolContext) -> dict:
    """
    Retrieves the patient's current active medication list from the FHIR server.
    Returns medication names, dosage instructions, and prescribing dates.
    No arguments required.
    """
    ctx = _get_fhir_context(tool_context, "get_active_medications")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_active_medications patient_id=%s", patient_id)

    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "MedicationRequest",
            params={"patient": patient_id, "status": "active", "_count": "50"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    medications = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        med_concept = res.get("medicationCodeableConcept", {})
        med_name = (
            med_concept.get("text")
            or _coding_display(med_concept.get("coding", []))
            or res.get("medicationReference", {}).get("display", "Unknown")
        )
        dosage_list = [d.get("text", "No dosage text") for d in res.get("dosageInstruction", [])]
        medications.append({
            "medication": med_name,
            "status": res.get("status"),
            "dosage": dosage_list[0] if dosage_list else "Not specified",
            "authored_on": res.get("authoredOn"),
            "requester": (res.get("requester") or {}).get("display"),
        })

    return {
        "status": "success",
        "patient_id": patient_id,
        "count": len(medications),
        "medications": medications,
    }
