"""
FHIR AuditEvent generation -- best-effort HIPAA compliance trail.

Every FHIR tool invocation can emit an AuditEvent resource recording which
agent accessed what data, for which patient, and the outcome.  This provides
a defensible audit trail visible when you query ``GET /AuditEvent`` on the
FHIR server during a demo.

Feature-flagged: set ``MAMAGUARD_AUDIT_EVENTS=true`` to enable.
Target: HAPI R4 (read-only servers like SMART R4 will reject the POST;
failures are logged and silently swallowed).
"""

from __future__ import annotations

import functools
import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_AUDIT_TIMEOUT = 3  # seconds -- keep short to avoid blocking tool responses


# -- Feature flag --------------------------------------------------------------

def _is_enabled() -> bool:
    return os.environ.get("MAMAGUARD_AUDIT_EVENTS", "").lower() in ("1", "true", "yes")


# -- AuditEvent builder -------------------------------------------------------

def build_audit_event(
    patient_id: str,
    tool_name: str,
    action: str,
    outcome: str,
) -> dict:
    """Build a FHIR R4 AuditEvent resource.

    Args:
        patient_id: FHIR Patient resource ID.
        tool_name: Name of the tool that was invoked.
        action: FHIR AuditEvent action code -- ``R`` (Read) or ``C`` (Create).
        outcome: FHIR AuditEvent outcome code -- ``0`` (Success), ``4`` (Minor
                 failure), ``8`` (Serious failure), ``12`` (Major failure).
    """
    from mamaguard import MAMAGUARD_VERSION

    return {
        "resourceType": "AuditEvent",
        "type": {
            "system": "http://dicom.nema.org/resources/ontology/DCM",
            "code": "110110",
            "display": "Patient Record",
        },
        "subtype": [
            {
                "system": "http://hl7.org/fhir/restful-interaction",
                "code": "read" if action == "R" else "create",
                "display": "read" if action == "R" else "create",
            }
        ],
        "action": action,
        "recorded": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "purposeOfEvent": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ActReason",
                        "code": "TREAT",
                        "display": "treatment",
                    }
                ]
            }
        ],
        "agent": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://dicom.nema.org/resources/ontology/DCM",
                            "code": "110153",
                            "display": "Source Role ID",
                        }
                    ]
                },
                "who": {
                    "display": f"MamaGuard v{MAMAGUARD_VERSION} -- {tool_name}",
                },
                "name": "MamaGuard",
                "requestor": False,
            }
        ],
        "source": {
            "observer": {
                "display": f"MamaGuard v{MAMAGUARD_VERSION} Healthcare AI Agent",
            },
            "type": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/security-source-type",
                    "code": "4",
                    "display": "Application Server",
                }
            ],
        },
        "entity": [
            {
                "what": {
                    "reference": f"Patient/{patient_id}",
                },
                "type": {
                    "system": "http://terminology.hl7.org/CodeSystem/audit-entity-type",
                    "code": "1",
                    "display": "Person",
                },
                "role": {
                    "system": "http://terminology.hl7.org/CodeSystem/object-role",
                    "code": "1",
                    "display": "Patient",
                },
                "description": f"Tool invocation: {tool_name}",
            }
        ],
    }


# -- POST helper ---------------------------------------------------------------

def post_audit_event(fhir_url: str, token: str, audit_event: dict) -> bool:
    """Best-effort POST of an AuditEvent.  Returns True on success."""
    try:
        response = httpx.post(
            f"{fhir_url}/AuditEvent",
            json=audit_event,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            },
            timeout=_AUDIT_TIMEOUT,
        )
        response.raise_for_status()
        resource_id = response.json().get("id", "unknown")
        logger.info(
            "audit_event_posted id=%s tool=%s patient=Patient/%s outcome=%s",
            resource_id,
            audit_event["entity"][0]["description"],
            audit_event["entity"][0]["what"]["reference"].split("/")[-1],
            audit_event["outcome"],
        )
        return True
    except Exception as exc:
        logger.debug("audit_event_post_failed: %s", exc)
        return False


# -- Convenience ---------------------------------------------------------------

def emit_audit_event(
    fhir_url: str,
    token: str,
    patient_id: str,
    tool_name: str,
    action: str,
    outcome: str,
) -> None:
    """Build and POST an AuditEvent.  No-op when the feature flag is off."""
    if not _is_enabled():
        return
    event = build_audit_event(patient_id, tool_name, action, outcome)
    post_audit_event(fhir_url, token, event)


# -- Decorator -----------------------------------------------------------------

def audited(tool_func):
    """Decorator that emits a FHIR AuditEvent after each tool invocation.

    The wrapped function must accept a ``tool_context`` parameter (keyword
    or last positional) whose ``.state`` dict contains ``fhir_url``,
    ``fhir_token``, and ``patient_id``.
    """

    @functools.wraps(tool_func)
    def wrapper(*args, **kwargs):
        result = tool_func(*args, **kwargs)

        if not _is_enabled():
            return result

        # Extract tool_context from kwargs or positional args.
        tc = kwargs.get("tool_context")
        if tc is None:
            for arg in args:
                if hasattr(arg, "state") and isinstance(getattr(arg, "state", None), dict):
                    tc = arg
                    break
        if tc is None:
            return result

        state = tc.state
        fhir_url = state.get("fhir_url", "")
        fhir_token = state.get("fhir_token", "")
        patient_id = state.get("patient_id", "")
        if not (fhir_url and fhir_token and patient_id):
            return result

        # Derive action code and outcome from result.
        is_write = tool_func.__name__.startswith(("write_", "create_"))
        action = "C" if is_write else "R"

        outcome = "0"  # success
        if isinstance(result, dict):
            status = result.get("status", "")
            if status == "error":
                outcome = "8"
            elif status == "partial":
                outcome = "4"

        emit_audit_event(fhir_url, fhir_token, patient_id, tool_func.__name__, action, outcome)
        return result

    return wrapper
