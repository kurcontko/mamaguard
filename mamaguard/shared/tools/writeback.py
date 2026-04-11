"""
FHIR write-back tools -- create resources on the FHIR server.

Tools:
    write_risk_assessment        POST RiskAssessment to FHIR
    create_communication_request POST CommunicationRequest to FHIR
"""

import logging
from datetime import datetime, timezone

import httpx
from google.adk.tools import ToolContext

from .fhir_base import _get_fhir_context

logger = logging.getLogger(__name__)

_FHIR_TIMEOUT = 15


def _fhir_post(fhir_url: str, token: str, resource_type: str, body: dict) -> dict:
    """POST a FHIR resource and return the created resource or error."""
    response = httpx.post(
        f"{fhir_url}/{resource_type}",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
        timeout=_FHIR_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def write_risk_assessment(
    risk_type: str,
    probability: float,
    basis: str,
    mitigation: str,
    tool_context: ToolContext = None,
) -> dict:
    """
    Write a RiskAssessment resource to the FHIR server.

    Creates a RiskAssessment documenting a clinical risk identified by MamaGuard.
    This is a bidirectional FHIR write-back demonstrating the agent's ability
    to contribute structured data back to the health record.

    Args:
        risk_type: Type of risk (e.g., "postpartum-hypertensive-crisis",
                   "medication-non-response", "recurrent-pregnancy-loss")
        probability: Estimated probability (0.0 to 1.0)
        basis: Evidence basis for the assessment (free text)
        mitigation: Recommended mitigation (free text)
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info(
        "tool_write_risk_assessment patient_id=%s risk_type=%s probability=%.2f",
        patient_id, risk_type, probability,
    )

    risk_assessment = {
        "resourceType": "RiskAssessment",
        "status": "final",
        "subject": {"reference": f"Patient/{patient_id}"},
        "occurrenceDateTime": datetime.now(timezone.utc).isoformat(),
        "prediction": [
            {
                "outcome": {
                    "text": risk_type,
                },
                "probabilityDecimal": round(probability, 2),
            }
        ],
        "basis": [{"display": basis}],
        "mitigation": mitigation,
        "note": [
            {
                "text": (
                    f"AI-generated risk assessment by MamaGuard. "
                    f"Risk type: {risk_type}. "
                    f"Basis: {basis}. "
                    f"Mitigation: {mitigation}. "
                    f"This assessment requires clinician review."
                ),
            }
        ],
    }

    try:
        created = _fhir_post(fhir_url, fhir_token, "RiskAssessment", risk_assessment)
        resource_id = created.get("id", "unknown")
        logger.info("risk_assessment_created id=%s patient_id=%s", resource_id, patient_id)
        return {
            "status": "success",
            "action": "created",
            "resource_type": "RiskAssessment",
            "resource_id": resource_id,
            "patient_id": patient_id,
            "risk_type": risk_type,
            "probability": probability,
        }
    except httpx.HTTPStatusError as e:
        logger.warning(
            "risk_assessment_write_failed patient_id=%s http_status=%d",
            patient_id, e.response.status_code,
        )
        return {
            "status": "error",
            "action": "write_failed",
            "resource_type": "RiskAssessment",
            "http_status": e.response.status_code,
            "error_message": (
                f"FHIR server rejected RiskAssessment write (HTTP {e.response.status_code}). "
                "This is expected on read-only FHIR servers like SMART R4. "
                "Write-back works on HAPI R4 or other CRUD-enabled servers."
            ),
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "write_failed",
            "resource_type": "RiskAssessment",
            "error_message": f"Could not reach FHIR server: {e}",
        }


def create_communication_request(
    medium: str,
    content: str,
    priority: str = "routine",
    tool_context: ToolContext = None,
) -> dict:
    """
    Create a CommunicationRequest resource on the FHIR server.

    Generates an outreach request for the care team — for example, scheduling
    a follow-up call, sending educational materials, or requesting an interpreter.

    Args:
        medium: Communication medium (e.g., "phone", "email", "sms", "mail")
        content: Message content or purpose (free text)
        priority: Priority level ("routine", "urgent", "asap", "stat")
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info(
        "tool_create_communication_request patient_id=%s medium=%s priority=%s",
        patient_id, medium, priority,
    )

    comm_request = {
        "resourceType": "CommunicationRequest",
        "status": "active",
        "priority": priority,
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": datetime.now(timezone.utc).isoformat(),
        "medium": [
            {
                "text": medium,
            }
        ],
        "payload": [
            {
                "contentString": content,
            }
        ],
        "note": [
            {
                "text": (
                    f"AI-generated outreach request by MamaGuard. "
                    f"Medium: {medium}. Priority: {priority}. "
                    f"This request requires care team review and action."
                ),
            }
        ],
    }

    try:
        created = _fhir_post(fhir_url, fhir_token, "CommunicationRequest", comm_request)
        resource_id = created.get("id", "unknown")
        logger.info("communication_request_created id=%s patient_id=%s", resource_id, patient_id)
        return {
            "status": "success",
            "action": "created",
            "resource_type": "CommunicationRequest",
            "resource_id": resource_id,
            "patient_id": patient_id,
            "medium": medium,
            "priority": priority,
        }
    except httpx.HTTPStatusError as e:
        logger.warning(
            "communication_request_write_failed patient_id=%s http_status=%d",
            patient_id, e.response.status_code,
        )
        return {
            "status": "error",
            "action": "write_failed",
            "resource_type": "CommunicationRequest",
            "http_status": e.response.status_code,
            "error_message": (
                f"FHIR server rejected CommunicationRequest write (HTTP {e.response.status_code}). "
                "Write-back works on HAPI R4 or other CRUD-enabled servers."
            ),
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "write_failed",
            "resource_type": "CommunicationRequest",
            "error_message": f"Could not reach FHIR server: {e}",
        }
