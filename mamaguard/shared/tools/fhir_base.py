"""
FHIR base tools -- query a FHIR R4 server on behalf of the patient in context.

Adapted from po-adk-python shared/tools/fhir.py. These tools read FHIR
credentials from tool_context.state (injected by fhir_hook.extract_fhir_context).
"""

import logging

import httpx
from google.adk.tools import ToolContext

from ..smart_tickets import enforce_smart_ticket
from .cache import cached_tool

logger = logging.getLogger(__name__)

_FHIR_TIMEOUT = 15  # seconds


# -- Private helpers ----------------------------------------------------------

def _get_fhir_context(tool_context: ToolContext | None, tool_name: str = ""):
    """
    Read FHIR credentials from session state.
    Returns (fhir_url, fhir_token, patient_id) or error dict.

    When *tool_name* is provided and SMART Permission Tickets are enabled,
    validates that the session ticket grants the required scopes before
    returning credentials.
    """
    if tool_context is None:
        return {
            "status": "error",
            "error_message": "FHIR context is not available -- no tool context provided.",
        }

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


def _safe_fhir_get(fhir_url: str, token: str, path: str, params: dict | None = None):
    """FHIR GET with error handling. Returns (data, None) or (None, error_dict)."""
    try:
        return _fhir_get(fhir_url, token, path, params), None
    except httpx.HTTPStatusError as e:
        return None, _http_error_result(e)
    except Exception as e:
        return None, _connection_error_result(e)


def _bundle_resources(bundle: dict) -> list[dict]:
    """Extract resource dicts from a FHIR Bundle response."""
    return [e.get("resource", {}) for e in bundle.get("entry", [])]


def _silent_fhir_get(fhir_url: str, token: str, path: str, params: dict | None = None) -> list[dict]:
    """FHIR GET returning list of resource dicts, [] on any error."""
    try:
        return _bundle_resources(_fhir_get(fhir_url, token, path, params))
    except Exception:
        return []


def _clinician_review(
    required: bool,
    reason: str = "",
    recommendation: str = "",
    evidence: list | None = None,
    confidence: float = 0.5,
) -> dict:
    """Build a standard clinician_review block."""
    return {
        "required": required,
        "reason": reason,
        "recommendation": recommendation,
        "evidence_basis": evidence or [],
        "confidence": confidence,
    }


# -- Tool: patient summary ---------------------------------------------------

@cached_tool
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
    patient, err = _safe_fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
    if err:
        return err

    names = patient.get("name", [])
    official = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
    given = " ".join(official.get("given", []))
    family = official.get("family", "")
    result["name"] = f"{given} {family}".strip() or "Unknown"
    result["birth_date"] = patient.get("birthDate")
    result["gender"] = patient.get("gender")
    result["contacts"] = [
        {"system": t.get("system"), "value": t.get("value"), "use": t.get("use")}
        for t in patient.get("telecom", [])
    ]

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

    # Active conditions
    result["active_conditions"] = []
    for res in _silent_fhir_get(fhir_url, fhir_token, "Condition",
                                params={"patient": patient_id, "clinical-status": "active", "_count": "50"}):
        code = res.get("code", {})
        onset = res.get("onsetDateTime") or (res.get("onsetPeriod") or {}).get("start")
        result["active_conditions"].append({
            "condition": code.get("text") or _coding_display(code.get("coding", [])),
            "onset": onset,
        })

    # Active medications
    result["active_medications"] = []
    for res in _silent_fhir_get(fhir_url, fhir_token, "MedicationRequest",
                                params={"patient": patient_id, "status": "active", "_count": "50"}):
        med_concept = res.get("medicationCodeableConcept", {})
        med_name = (
            med_concept.get("text")
            or _coding_display(med_concept.get("coding", []))
            or res.get("medicationReference", {}).get("display", "Unknown")
        )
        dosage_list = [d.get("text", "No dosage text") for d in res.get("dosageInstruction", [])]
        result["active_medications"].append({
            "medication": med_name,
            "dosage": dosage_list[0] if dosage_list else "Not specified",
        })

    # Recent vitals (last 10)
    result["recent_vitals"] = []
    for res in _silent_fhir_get(fhir_url, fhir_token, "Observation",
                                params={"patient": patient_id, "category": "vital-signs", "_sort": "-date", "_count": "10"}):
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

        result["recent_vitals"].append({
            "observation": obs_name,
            "value": value,
            "unit": unit,
            "components": components or None,
            "date": res.get("effectiveDateTime"),
        })

    return result


# -- Tool: active medications ------------------------------------------------

@cached_tool
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

    bundle, err = _safe_fhir_get(
        fhir_url, fhir_token, "MedicationRequest",
        params={"patient": patient_id, "status": "active", "_count": "50"},
    )
    if err:
        return err

    medications = []
    for res in _bundle_resources(bundle):
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


# -- Tool: find linked newborn ------------------------------------------------

_CHILD_RELATIONSHIP_CODES = {"CHILD", "SON", "DAU", "NCHILD", "child"}
_LINKED_PATIENT_SYSTEM = "urn:mamaguard:linked-patient-id"


def find_linked_newborn(
    mother_patient_id: str,
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Find newborn Patient resources linked to a maternal patient via FHIR
    RelatedPerson resources.

    Queries RelatedPerson where patient = mother_patient_id and relationship
    indicates a child (CHILD, SON, DAU). Returns linked newborn patient IDs,
    names, and birth dates so the orchestrator can initiate a pediatric
    assessment in the same session.

    Args:
        mother_patient_id: The FHIR Patient ID of the mother.
    """
    ctx = _get_fhir_context(tool_context, "find_linked_newborn")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, _patient_id = ctx
    logger.info(
        "tool_find_linked_newborn mother_patient_id=%s", mother_patient_id,
    )

    bundle, err = _safe_fhir_get(
        fhir_url, fhir_token, "RelatedPerson",
        params={"patient": mother_patient_id, "_count": "50"},
    )
    if err:
        return err

    linked_newborns: list[dict] = []
    for res in _bundle_resources(bundle):

        # Check relationship codes for child types
        is_child = False
        for rel in res.get("relationship", []):
            for coding in rel.get("coding", []):
                if coding.get("code", "") in _CHILD_RELATIONSHIP_CODES:
                    is_child = True
                    break
            if is_child:
                break

        if not is_child:
            continue

        # Extract child Patient ID from identifier
        child_patient_id = None
        for ident in res.get("identifier", []):
            if ident.get("system") == _LINKED_PATIENT_SYSTEM:
                child_patient_id = ident.get("value")
                break

        # Extract name
        names = res.get("name", [])
        name_record = names[0] if names else {}
        given = " ".join(name_record.get("given", []))
        family = name_record.get("family", "")
        child_name = f"{given} {family}".strip() or "Unknown"

        linked_newborns.append({
            "child_patient_id": child_patient_id,
            "name": child_name,
            "birth_date": res.get("birthDate"),
            "gender": res.get("gender"),
            "related_person_id": res.get("id", ""),
        })

    return {
        "status": "success",
        "mother_patient_id": mother_patient_id,
        "count": len(linked_newborns),
        "linked_newborns": linked_newborns,
    }
