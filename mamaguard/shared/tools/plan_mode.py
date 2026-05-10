"""
Plan/commit split for FHIR writebacks (Phase 3 of architecture v3).

Every destructive write splits into two phases:

  1. plan_<name>(...)  -> returns {plan_id, bundle, preview, requires_approval}
                          builds the FHIR body, stores it in session state,
                          does NOT POST.
  2. commit_pending_write(plan_id, approved=True)
                          retrieves the plan, POSTs only if approved.

Policy: HIGH/URGENT risk levels require explicit approval. ROUTINE/MODERATE
are auto-committable inline (the agent may pass approved=True immediately
in the same turn), but the bundle still flows through plan -> commit so
the audit trail shows a proposed-then-committed write rather than a
one-shot mutation.

This turns the Liaison pattern from "the agent says it consulted a
clinician" into "the FHIR bundle was shown, reviewed, and approved".
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from google.adk.tools import ToolContext

from .fhir_base import _get_fhir_context
from .writeback import (
    _post_resource,
    _validate_care_plan,
    _validate_communication_request,
    _validate_risk_assessment,
)

logger = logging.getLogger(__name__)

_PENDING_WRITES_KEY = "pending_fhir_writes"
_APPROVAL_REQUIRED_LEVELS = {"HIGH", "URGENT"}


# ---------------------------------------------------------------------------
# Plan store -- process-level so plans survive across sessions and PO chat
# threads. This is what makes Scene 5 (clinician approval) work even when the
# clinician opens a brand-new conversation to issue the approval: the
# orchestrator's ``commit_pending_write`` can find the plan by id regardless
# of which session staged it.
#
# Tradeoffs:
#   - Plans don't survive a container restart (in-memory only). Production
#     deployments should persist plans as FHIR resources with status=draft
#     instead, scoped to the originating workspace.
#   - Plan ids are timestamp + random, so collisions across users are vanishingly
#     unlikely; but a malicious actor with a guessed plan_id could commit
#     someone else's plan. Acceptable for single-tenant demo; real deployments
#     need per-workspace scoping in the store key.
# ---------------------------------------------------------------------------

_PROCESS_PLAN_STORE: dict[str, dict] = {}


def _store(tool_context: ToolContext | None) -> dict[str, dict]:
    return _PROCESS_PLAN_STORE


def _new_plan_id(store: dict, resource_type: str) -> str:
    return f"plan-{resource_type.lower()}-{len(store) + 1}-{int(time.time() * 1000)}"


def _requires_approval(risk_level: str, priority: str | None = None) -> bool:
    lvl = (risk_level or "").strip().upper()
    if lvl in _APPROVAL_REQUIRED_LEVELS:
        return True
    pri = (priority or "").strip().lower()
    return pri in {"urgent", "asap", "stat"}


def _build_preview(resource_type: str, body: dict, summary: str) -> str:
    """Human-readable preview that gets shown to the clinician."""
    lines = [
        f"Proposed FHIR write: {resource_type}",
        f"Subject: {body.get('subject', {}).get('reference', 'unknown')}",
        f"Summary: {summary}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# plan_* tools
# ---------------------------------------------------------------------------


def plan_risk_assessment(
    risk_type: str,
    probability: float,
    basis: str,
    mitigation: str,
    risk_level: str = "HIGH",
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Plan a RiskAssessment write. Does NOT POST to FHIR.

    Returns a plan_id that must be passed to `commit_pending_write` to
    actually create the resource. HIGH/URGENT risk levels set
    requires_approval=True; the clinician must confirm before commit.

    Args:
        risk_type: Type of risk (e.g., "postpartum-hypertensive-crisis")
        probability: Probability (0.0 to 1.0)
        basis: Evidence basis (free text)
        mitigation: Recommended mitigation (free text)
        risk_level: "URGENT" | "HIGH" | "MODERATE" | "ROUTINE" (default HIGH)
    """
    validation_err = _validate_risk_assessment(risk_type, probability, basis, mitigation)
    if validation_err is not None:
        return validation_err

    ctx = _get_fhir_context(tool_context, "plan_risk_assessment")
    if isinstance(ctx, dict):
        return ctx
    _, _, patient_id = ctx

    body = {
        "resourceType": "RiskAssessment",
        "status": "final",
        "subject": {"reference": f"Patient/{patient_id}"},
        "occurrenceDateTime": datetime.now(timezone.utc).isoformat(),
        "prediction": [
            {
                "outcome": {"text": risk_type},
                "probabilityDecimal": round(probability, 2),
            }
        ],
        "basis": [{"display": basis}],
        "mitigation": mitigation,
        "note": [
            {
                "text": (
                    f"AI-generated risk assessment by MamaGuard. "
                    f"Risk level: {risk_level}. Basis: {basis}. Mitigation: {mitigation}."
                )
            }
        ],
    }

    store = _store(tool_context)
    plan_id = _new_plan_id(store, "RiskAssessment")
    needs_approval = _requires_approval(risk_level)
    summary = f"{risk_type} (p={probability:.2f}, level={risk_level})"

    store[plan_id] = {
        "plan_id": plan_id,
        "resource_type": "RiskAssessment",
        "body": body,
        "patient_id": patient_id,
        "risk_level": risk_level,
        "requires_approval": needs_approval,
        "status": "pending",
        "summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        "tool_plan_risk_assessment plan_id=%s patient_id=%s requires_approval=%s",
        plan_id, patient_id, needs_approval,
    )
    return {
        "status": "planned",
        "action": "plan",
        "plan_id": plan_id,
        "resource_type": "RiskAssessment",
        "requires_approval": needs_approval,
        "preview": _build_preview("RiskAssessment", body, summary),
        "bundle": body,
        "risk_level": risk_level,
    }


def plan_communication_request(
    medium: str,
    content: str,
    priority: str = "routine",
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Plan a CommunicationRequest write. Does NOT POST to FHIR.

    Args:
        medium: Communication medium (phone / email / sms / mail)
        content: Message content or purpose
        priority: "routine" | "urgent" | "asap" | "stat"
    """
    validation_err = _validate_communication_request(medium, content, priority)
    if validation_err is not None:
        return validation_err

    ctx = _get_fhir_context(tool_context, "plan_communication_request")
    if isinstance(ctx, dict):
        return ctx
    _, _, patient_id = ctx

    body = {
        "resourceType": "CommunicationRequest",
        "status": "active",
        "priority": priority,
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": datetime.now(timezone.utc).isoformat(),
        "medium": [{"text": medium}],
        "payload": [{"contentString": content}],
        "note": [
            {
                "text": (
                    f"AI-generated outreach request by MamaGuard. "
                    f"Medium: {medium}. Priority: {priority}."
                )
            }
        ],
    }

    store = _store(tool_context)
    plan_id = _new_plan_id(store, "CommunicationRequest")
    needs_approval = _requires_approval("", priority=priority)
    summary = f"{medium} / {priority}: {content[:60]}"

    store[plan_id] = {
        "plan_id": plan_id,
        "resource_type": "CommunicationRequest",
        "body": body,
        "patient_id": patient_id,
        "priority": priority,
        "requires_approval": needs_approval,
        "status": "pending",
        "summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        "tool_plan_communication_request plan_id=%s patient_id=%s priority=%s",
        plan_id, patient_id, priority,
    )
    return {
        "status": "planned",
        "action": "plan",
        "plan_id": plan_id,
        "resource_type": "CommunicationRequest",
        "requires_approval": needs_approval,
        "preview": _build_preview("CommunicationRequest", body, summary),
        "bundle": body,
        "priority": priority,
    }


def plan_care_plan(
    category: str,
    goal_description: str,
    resource_name: str,
    resource_contact: str,
    resource_url: str = "",
    z_code: str = "",
    risk_level: str = "MODERATE",
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Plan a linked Goal + CarePlan write. Does NOT POST to FHIR.

    Returns a plan_id referencing a Goal + CarePlan pair. commit_pending_write
    POSTs both resources in order (Goal first, then CarePlan referencing it).
    """
    validation_err = _validate_care_plan(category, goal_description, resource_name, resource_contact)
    if validation_err is not None:
        return validation_err

    ctx = _get_fhir_context(tool_context, "plan_care_plan")
    if isinstance(ctx, dict):
        return ctx
    _, _, patient_id = ctx

    now = datetime.now(timezone.utc).isoformat()
    subject = {"reference": f"Patient/{patient_id}"}

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
                            "http://terminology.hl7.org/CodeSystem/goal-category"
                        ),
                        "code": category,
                    }
                ],
            }
        ],
        "note": [
            {
                "text": (
                    f"AI-identified SDOH goal by MamaGuard. Category: {category}. "
                    f"Matched resource: {resource_name} ({resource_contact})."
                )
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

    activity_parts = [f"Contact {resource_name} at {resource_contact}"]
    if resource_url:
        activity_parts.append(f"Web: {resource_url}")
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
                            "http://hl7.org/fhir/us/core/CodeSystem/us-core-tags"
                        ),
                        "code": "sdoh",
                    }
                ],
            }
        ],
        # Placeholder goal reference — rewritten on commit to Goal/<real_id>.
        "goal": [{"reference": "Goal/__PLAN_PLACEHOLDER__"}],
        "activity": [
            {
                "detail": {
                    "status": "not-started",
                    "description": ". ".join(activity_parts) + ".",
                    "performer": [{"display": resource_name}],
                }
            }
        ],
        "note": [
            {
                "text": (
                    f"AI-generated SDOH CarePlan by MamaGuard. "
                    f"Resource: {resource_name}. Requires care team review."
                )
            }
        ],
    }

    store = _store(tool_context)
    plan_id = _new_plan_id(store, "CarePlanBundle")
    needs_approval = _requires_approval(risk_level)
    summary = f"SDOH {category} -> {resource_name}"

    store[plan_id] = {
        "plan_id": plan_id,
        "resource_type": "CarePlanBundle",  # compound plan (Goal + CarePlan)
        "goal_body": goal_body,
        "care_plan_body": care_plan_body,
        "patient_id": patient_id,
        "category": category,
        "resource_name": resource_name,
        "risk_level": risk_level,
        "requires_approval": needs_approval,
        "status": "pending",
        "summary": summary,
        "created_at": now,
    }
    logger.info(
        "tool_plan_care_plan plan_id=%s patient_id=%s category=%s",
        plan_id, patient_id, category,
    )
    return {
        "status": "planned",
        "action": "plan",
        "plan_id": plan_id,
        "resource_type": "CarePlanBundle",
        "requires_approval": needs_approval,
        "preview": _build_preview("Goal + CarePlan", goal_body, summary),
        "goal_bundle": goal_body,
        "care_plan_bundle": care_plan_body,
        "category": category,
    }


# ---------------------------------------------------------------------------
# commit_pending_write -- single commit tool for all plan types
# ---------------------------------------------------------------------------


def commit_pending_write(
    plan_id: str,
    approved: bool = True,
    approver: str = "clinician",
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Commit (POST) or deny a previously planned FHIR write.

    Args:
        plan_id: plan_id returned from a plan_* tool
        approved: True to POST, False to record a denial
        approver: Display name of the approver (for audit trail)
    """
    store = _store(tool_context)
    plan = store.get(plan_id)
    if plan is None:
        return {
            "status": "error",
            "action": "commit_failed",
            "error_message": f"No pending plan with id {plan_id}",
        }
    if plan["status"] != "pending":
        return {
            "status": "error",
            "action": "commit_failed",
            "plan_id": plan_id,
            "error_message": f"Plan {plan_id} already {plan['status']}",
        }

    if not approved:
        plan["status"] = "denied"
        plan["approver"] = approver
        logger.info("tool_commit_denied plan_id=%s approver=%s", plan_id, approver)
        return {
            "status": "denied",
            "action": "commit",
            "plan_id": plan_id,
            "resource_type": plan["resource_type"],
            "approver": approver,
        }

    ctx = _get_fhir_context(tool_context, "commit_pending_write")
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    if plan["resource_type"] == "CarePlanBundle":
        return _commit_care_plan_bundle(plan, fhir_url, fhir_token, patient_id, approver, store)

    result, err = _post_resource(
        fhir_url, fhir_token, plan["resource_type"], plan["body"], patient_id,
    )
    if err:
        plan["status"] = "failed"
        plan["error"] = err.get("error_message")
        return {**err, "plan_id": plan_id}

    plan["status"] = "committed"
    plan["approver"] = approver
    plan["resource_id"] = result["resource_id"]
    logger.info(
        "tool_commit_pending_write plan_id=%s resource=%s id=%s approver=%s",
        plan_id, plan["resource_type"], result["resource_id"], approver,
    )
    return {
        **result,
        "plan_id": plan_id,
        "approver": approver,
        "committed_from_plan": True,
    }


def _commit_care_plan_bundle(
    plan: dict,
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    approver: str,
    store: dict,
) -> dict:
    goal_result, err = _post_resource(
        fhir_url, fhir_token, "Goal", plan["goal_body"], patient_id,
    )
    if err:
        plan["status"] = "failed"
        plan["error"] = err.get("error_message")
        return {**err, "plan_id": plan["plan_id"]}

    goal_id = goal_result["resource_id"]
    care_plan_body: dict[str, Any] = plan["care_plan_body"]
    care_plan_body["goal"] = [{"reference": f"Goal/{goal_id}"}]

    plan_result, err = _post_resource(
        fhir_url, fhir_token, "CarePlan", care_plan_body, patient_id,
    )
    if err:
        plan["status"] = "partial"
        plan["goal_id"] = goal_id
        err.update(
            status="partial",
            action="care_plan_write_failed",
            goal_id=goal_id,
            goal_created=True,
            plan_id=plan["plan_id"],
            approver=approver,
        )
        return err

    plan["status"] = "committed"
    plan["approver"] = approver
    plan["goal_id"] = goal_id
    plan["care_plan_id"] = plan_result["resource_id"]
    logger.info(
        "tool_commit_care_plan plan_id=%s goal=%s care_plan=%s approver=%s",
        plan["plan_id"], goal_id, plan_result["resource_id"], approver,
    )
    return {
        **plan_result,
        "care_plan_id": plan_result["resource_id"],
        "goal_id": goal_id,
        "plan_id": plan["plan_id"],
        "approver": approver,
        "committed_from_plan": True,
        "category": plan["category"],
        "resource_name": plan["resource_name"],
    }


def list_pending_writes(tool_context: ToolContext | None = None) -> dict:
    """
    List all pending plans in the current session.

    Returns a snapshot the agent / clinician can inspect before approving.
    """
    store = _store(tool_context)
    pending = [
        {
            "plan_id": p["plan_id"],
            "resource_type": p["resource_type"],
            "status": p["status"],
            "requires_approval": p["requires_approval"],
            "summary": p.get("summary", ""),
            "created_at": p.get("created_at", ""),
        }
        for p in store.values()
    ]
    return {
        "status": "success",
        "count": len(pending),
        "pending": [p for p in pending if p["status"] == "pending"],
        "history": [p for p in pending if p["status"] != "pending"],
    }
