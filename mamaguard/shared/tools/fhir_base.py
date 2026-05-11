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

    # Surface SHARP context validation errors first
    context_errors = tool_context.state.get("fhir_context_errors")
    if context_errors:
        return {
            "status": "error",
            "error_message": (
                f"FHIR context failed SHARP validation: {'; '.join(context_errors)}. "
                "Ensure the caller provides valid FHIR credentials in A2A message metadata."
            ),
        }

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


def _codeable_text(codeable: dict | None) -> str:
    """Return display text for a FHIR CodeableConcept-like dict."""
    if not isinstance(codeable, dict):
        return ""
    text = codeable.get("text")
    if text:
        return text
    display = _coding_display(codeable.get("coding", []))
    return "" if display == "Unknown" else display


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


def _search_patient_resources(
    fhir_url: str,
    token: str,
    resource_type: str,
    patient_id: str,
    count: int = 50,
) -> tuple[list[dict], list[str]]:
    """
    Search a patient-scoped FHIR resource using both common patient parameters.

    FHIR resources are inconsistent: some expose `patient`, some expose
    `subject`, and HAPI deployments vary in which aliases are indexed. Trying
    both keeps the planning view portable without hard-coding server behavior.
    """
    resources: list[dict] = []
    seen: set[tuple[str, str]] = set()
    errors: list[str] = []
    successes = 0

    queries = (
        {"patient": patient_id, "_count": str(count)},
        {"subject": f"Patient/{patient_id}", "_count": str(count)},
    )
    for params in queries:
        bundle, err = _safe_fhir_get(fhir_url, token, resource_type, params=params)
        if err:
            errors.append(
                f"{resource_type} via {next(iter(params))}: {err.get('error_message', '')}"
            )
            continue
        successes += 1
        for res in _bundle_resources(bundle):
            key = (res.get("resourceType", resource_type), res.get("id", ""))
            if key in seen:
                continue
            seen.add(key)
            resources.append(res)

    return resources, [] if successes else errors


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


# -- Tool: current plan ------------------------------------------------------

_CURRENT_CAREPLAN_STATUSES = {"draft", "active", "on-hold", "unknown"}
_CURRENT_GOAL_STATUSES = {"proposed", "planned", "accepted", "active", "on-hold"}
_CURRENT_REQUEST_STATUSES = {"draft", "active", "on-hold"}
_CURRENT_RISK_STATUSES = {"registered", "preliminary", "final", "amended", "corrected"}


def get_current_plan(tool_context: ToolContext) -> dict:
    """
    Fetch the patient's current structured plan from FHIR.

    Returns active/draft CarePlans, open Goals, active outreach/referral
    requests, and recent RiskAssessments. Pending in-memory plan approvals are
    separate; callers should also use list_pending_writes when available.
    """
    ctx = _get_fhir_context(tool_context, "get_current_plan")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_current_plan patient_id=%s", patient_id)

    query_errors: list[str] = []

    care_plan_resources, errors = _search_patient_resources(
        fhir_url, fhir_token, "CarePlan", patient_id,
    )
    query_errors.extend(errors)
    goal_resources, errors = _search_patient_resources(
        fhir_url, fhir_token, "Goal", patient_id,
    )
    query_errors.extend(errors)
    communication_resources, errors = _search_patient_resources(
        fhir_url, fhir_token, "CommunicationRequest", patient_id,
    )
    query_errors.extend(errors)
    service_resources, errors = _search_patient_resources(
        fhir_url, fhir_token, "ServiceRequest", patient_id,
    )
    query_errors.extend(errors)
    risk_resources, errors = _search_patient_resources(
        fhir_url, fhir_token, "RiskAssessment", patient_id,
    )
    query_errors.extend(errors)

    care_plans = [
        _summarize_care_plan(res)
        for res in care_plan_resources
        if res.get("status") in _CURRENT_CAREPLAN_STATUSES
    ][:10]
    goals = [
        _summarize_goal(res)
        for res in goal_resources
        if res.get("lifecycleStatus") in _CURRENT_GOAL_STATUSES
    ][:10]
    communications = [
        _summarize_communication_request(res)
        for res in communication_resources
        if res.get("status") in _CURRENT_REQUEST_STATUSES
    ][:10]
    service_requests = [
        _summarize_service_request(res)
        for res in service_resources
        if res.get("status") in _CURRENT_REQUEST_STATUSES
    ][:10]
    risk_assessments = [
        _summarize_risk_assessment(res)
        for res in risk_resources
        if res.get("status") in _CURRENT_RISK_STATUSES
    ][:10]

    total = (
        len(care_plans) + len(goals) + len(communications)
        + len(service_requests) + len(risk_assessments)
    )
    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "current_plan_present": total > 0,
            "care_plans": care_plans,
            "goals": goals,
            "communication_requests": communications,
            "service_requests": service_requests,
            "risk_assessments": risk_assessments,
            "counts": {
                "care_plans": len(care_plans),
                "goals": len(goals),
                "communication_requests": len(communications),
                "service_requests": len(service_requests),
                "risk_assessments": len(risk_assessments),
                "total_current_items": total,
            },
            "query_errors": query_errors,
        },
        "clinician_review": _clinician_review(
            total == 0,
            reason="No active FHIR CarePlan/Goal/Request/RiskAssessment found" if total == 0 else "",
            recommendation=(
                "If clinical planning has occurred outside FHIR, reconcile it into "
                "CarePlan, Goal, CommunicationRequest, ServiceRequest, or RiskAssessment."
                if total == 0 else "Structured plan resources found in FHIR"
            ),
            evidence=[],
            confidence=0.75 if not query_errors else 0.6,
        ),
    }


def _summarize_care_plan(res: dict) -> dict:
    categories = [
        text for text in (_codeable_text(cat) for cat in res.get("category", [])) if text
    ]
    activities = []
    for activity in res.get("activity", [])[:5]:
        detail = activity.get("detail") or {}
        desc = detail.get("description") or (activity.get("reference") or {}).get("display")
        if desc:
            activities.append({
                "description": desc,
                "status": detail.get("status", ""),
            })
    return {
        "resource_id": res.get("id", ""),
        "title": res.get("title") or res.get("description") or (categories[0] if categories else "Unnamed plan"),
        "status": res.get("status", ""),
        "intent": res.get("intent", ""),
        "category": categories,
        "description": res.get("description", ""),
        "created": res.get("created", ""),
        "period_start": (res.get("period") or {}).get("start", ""),
        "period_end": (res.get("period") or {}).get("end", ""),
        "goals": [g.get("reference", "") for g in res.get("goal", []) if g.get("reference")],
        "activities": activities,
    }


def _summarize_goal(res: dict) -> dict:
    target_dates = []
    for target in res.get("target", []):
        due = target.get("dueDate") or (target.get("dueDuration") or {}).get("value")
        if due:
            target_dates.append(str(due))
    return {
        "resource_id": res.get("id", ""),
        "description": _codeable_text(res.get("description")) or "Unnamed goal",
        "lifecycle_status": res.get("lifecycleStatus", ""),
        "achievement_status": _codeable_text(res.get("achievementStatus")),
        "start": res.get("startDate") or (res.get("startCodeableConcept") or {}).get("text", ""),
        "target_due": target_dates,
        "addresses": [
            a.get("reference") or a.get("display") or ""
            for a in res.get("addresses", [])
            if a.get("reference") or a.get("display")
        ],
    }


def _summarize_communication_request(res: dict) -> dict:
    payloads = []
    for payload in res.get("payload", []):
        payloads.append(
            payload.get("contentString")
            or (payload.get("contentReference") or {}).get("display")
            or (payload.get("contentAttachment") or {}).get("title")
            or ""
        )
    return {
        "resource_id": res.get("id", ""),
        "status": res.get("status", ""),
        "priority": res.get("priority", ""),
        "authored_on": res.get("authoredOn", ""),
        "medium": [
            text for text in (_codeable_text(m) for m in res.get("medium", [])) if text
        ],
        "payload": [p for p in payloads if p],
    }


def _summarize_service_request(res: dict) -> dict:
    return {
        "resource_id": res.get("id", ""),
        "status": res.get("status", ""),
        "intent": res.get("intent", ""),
        "priority": res.get("priority", ""),
        "code": _codeable_text(res.get("code")) or "Unnamed request",
        "authored_on": res.get("authoredOn", ""),
        "occurrence": res.get("occurrenceDateTime") or (res.get("occurrencePeriod") or {}).get("start", ""),
        "performer": [
            p.get("display") or p.get("reference") or ""
            for p in res.get("performer", [])
            if p.get("display") or p.get("reference")
        ],
    }


def _summarize_risk_assessment(res: dict) -> dict:
    predictions = []
    for pred in res.get("prediction", [])[:5]:
        probability = pred.get("probabilityDecimal")
        if probability is None:
            probability = (pred.get("probabilityRange") or {}).get("high", {}).get("value")
        predictions.append({
            "outcome": _codeable_text(pred.get("outcome")) or "Unnamed risk",
            "probability": probability,
        })
    return {
        "resource_id": res.get("id", ""),
        "status": res.get("status", ""),
        "occurrence": res.get("occurrenceDateTime") or (res.get("occurrencePeriod") or {}).get("start", ""),
        "predictions": predictions,
        "basis": [
            b.get("reference") or b.get("display") or ""
            for b in res.get("basis", [])
            if b.get("reference") or b.get("display")
        ],
        "mitigation": res.get("mitigation", ""),
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
