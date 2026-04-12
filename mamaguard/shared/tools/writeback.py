"""
FHIR write-back tools -- create resources on the FHIR server.

Tools:
    write_risk_assessment        POST RiskAssessment to FHIR
    create_communication_request POST CommunicationRequest to FHIR
    write_care_plan              POST CarePlan + Goal pair tied to an SDOH resource
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
    ctx = _get_fhir_context(tool_context, "write_risk_assessment")
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
    ctx = _get_fhir_context(tool_context, "create_communication_request")
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


# ---------------------------------------------------------------------------
# write_care_plan -- tie an SDOH resource match to a FHIR CarePlan + Goal
# ---------------------------------------------------------------------------


def write_care_plan(
    category: str,
    goal_description: str,
    resource_name: str,
    resource_contact: str,
    resource_url: str = "",
    z_code: str = "",
    tool_context: ToolContext = None,
) -> dict:
    """
    Create a linked FHIR Goal + CarePlan documenting an SDOH referral.

    The Goal encodes *what* we want to achieve for the patient (e.g.
    "secure emergency shelter placement within 7 days"). The CarePlan
    references the Goal and carries the concrete resource details in
    an activity detail, so a care navigator can pick it up and call the
    referenced organization.

    Both resources are POSTed to the FHIR server. On a read-only server
    (SMART R4 sandbox) the write returns a structured error so the agent
    can degrade gracefully. On HAPI R4 both resources are created.

    Args:
        category: Resolved SDOH category -- "housing", "food",
            "transportation", "interpreter", etc. Becomes the Goal
            category / CarePlan category.
        goal_description: Human-readable goal, e.g. "Secure emergency
            shelter placement within 7 days".
        resource_name: Name of the matched resource (e.g. "211 Helpline").
        resource_contact: Contact string ("Dial 211", "1-800-...").
        resource_url: Optional resource URL.
        z_code: Optional ICD-10 Z-code -- when present, attached to the
            Goal.addresses for terminology binding.
    """
    ctx = _get_fhir_context(tool_context, "write_care_plan")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info(
        "tool_write_care_plan patient_id=%s category=%s resource=%s",
        patient_id, category, resource_name,
    )

    now = datetime.now(timezone.utc).isoformat()
    subject = {"reference": f"Patient/{patient_id}"}

    # -- 1. Goal --------------------------------------------------------
    goal_body: dict = {
        "resourceType": "Goal",
        "lifecycleStatus": "proposed",
        "description": {"text": goal_description},
        "subject": subject,
        "category": [
            {
                "text": category,
                "coding": [
                    {
                        "system": (
                            "http://terminology.hl7.org/CodeSystem/"
                            "goal-category"
                        ),
                        "code": category,
                    }
                ],
            }
        ],
        "note": [
            {
                "text": (
                    f"AI-identified SDOH goal by MamaGuard. "
                    f"Category: {category}. "
                    f"Matched resource: {resource_name} ({resource_contact}). "
                    f"Requires care team confirmation before action."
                ),
            }
        ],
    }
    if z_code:
        goal_body["addresses"] = [
            {
                "display": f"ICD-10 {z_code}",
                "identifier": {
                    "system": "http://hl7.org/fhir/sid/icd-10-cm",
                    "value": z_code,
                },
            }
        ]

    try:
        created_goal = _fhir_post(fhir_url, fhir_token, "Goal", goal_body)
    except httpx.HTTPStatusError as e:
        logger.warning(
            "goal_write_failed patient_id=%s http_status=%d",
            patient_id, e.response.status_code,
        )
        return {
            "status": "error",
            "action": "write_failed",
            "resource_type": "Goal",
            "http_status": e.response.status_code,
            "error_message": (
                f"FHIR server rejected Goal write (HTTP {e.response.status_code}). "
                "Expected on read-only FHIR servers (SMART R4 sandbox). "
                "Write-back works on HAPI R4 or other CRUD-enabled servers."
            ),
        }
    except Exception as e:
        return {
            "status": "error",
            "action": "write_failed",
            "resource_type": "Goal",
            "error_message": f"Could not reach FHIR server: {e}",
        }

    goal_id = created_goal.get("id", "unknown")
    logger.info("goal_created id=%s patient_id=%s", goal_id, patient_id)

    # -- 2. CarePlan referencing the Goal -------------------------------
    activity_detail_text_parts = [
        f"Contact {resource_name} at {resource_contact}",
    ]
    if resource_url:
        activity_detail_text_parts.append(f"Web: {resource_url}")
    activity_detail_text = ". ".join(activity_detail_text_parts) + "."

    care_plan_body: dict = {
        "resourceType": "CarePlan",
        "status": "active",
        "intent": "plan",
        "title": f"SDOH {category} referral",
        "description": goal_description,
        "subject": subject,
        "period": {"start": now},
        "created": now,
        "category": [
            {
                "text": f"SDOH-{category}",
                "coding": [
                    {
                        "system": (
                            "http://hl7.org/fhir/us/core/CodeSystem/"
                            "us-core-tags"
                        ),
                        "code": "sdoh",
                    }
                ],
            }
        ],
        "goal": [{"reference": f"Goal/{goal_id}"}],
        "activity": [
            {
                "detail": {
                    "status": "not-started",
                    "description": activity_detail_text,
                    "performer": [{"display": resource_name}],
                }
            }
        ],
        "note": [
            {
                "text": (
                    f"AI-generated SDOH CarePlan by MamaGuard. "
                    f"Linked Goal: {goal_id}. "
                    f"Resource: {resource_name}. "
                    f"Requires care team review and action."
                ),
            }
        ],
    }

    try:
        created_plan = _fhir_post(fhir_url, fhir_token, "CarePlan", care_plan_body)
    except httpx.HTTPStatusError as e:
        logger.warning(
            "care_plan_write_failed patient_id=%s http_status=%d goal_id=%s",
            patient_id, e.response.status_code, goal_id,
        )
        return {
            "status": "partial",
            "action": "care_plan_write_failed",
            "resource_type": "CarePlan",
            "http_status": e.response.status_code,
            "goal_id": goal_id,
            "goal_created": True,
            "error_message": (
                f"Goal created (id={goal_id}) but CarePlan POST failed "
                f"with HTTP {e.response.status_code}. "
                "Expected on read-only FHIR servers."
            ),
        }
    except Exception as e:
        return {
            "status": "partial",
            "action": "care_plan_write_failed",
            "resource_type": "CarePlan",
            "goal_id": goal_id,
            "goal_created": True,
            "error_message": f"Could not reach FHIR server for CarePlan POST: {e}",
        }

    plan_id = created_plan.get("id", "unknown")
    logger.info(
        "care_plan_created id=%s goal_id=%s patient_id=%s",
        plan_id, goal_id, patient_id,
    )

    return {
        "status": "success",
        "action": "created",
        "resource_type": "CarePlan",
        "care_plan_id": plan_id,
        "goal_id": goal_id,
        "patient_id": patient_id,
        "category": category,
        "resource_name": resource_name,
        "resource_contact": resource_contact,
    }
