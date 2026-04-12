"""
MamaGuard MCP Server

Exposes all 14 FHIR tools from mamaguard/shared/tools/ via the MCP protocol.
Shares tool implementations with the ADK agents — no duplication.

SHARP context: each tool accepts fhir_url, fhir_token, and patient_id as
explicit parameters so any MCP client (Cursor, Claude Desktop, custom)
can pass EHR session credentials without extra middleware.

Run:
    python -m mamaguard.mcp_server.server          # stdio (default)
    MCP_TRANSPORT=sse python -m mamaguard.mcp_server.server   # SSE

Environment variables (all optional):
    MCP_HOST        Bind host for SSE transport (default: 0.0.0.0)
    MCP_PORT        Bind port for SSE transport (default: 8080)
    MCP_TRANSPORT   "stdio" (default) or "sse"
"""

from __future__ import annotations

import json
import os
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from .context import FhirContext

# FhirContext duck-types ToolContext (implements .state dict) for MCP use.
# mypy can't verify structural compatibility, so tool calls use type: ignore.

# -- Shared tool imports (single source of truth) ----------------------------
from mamaguard.shared.tools.fhir_base import (
    get_patient_summary as _get_patient_summary,
    get_active_medications as _get_active_medications,
)
from mamaguard.shared.tools.maternal import (
    get_bp_trend as _get_bp_trend,
    get_glucose_trend as _get_glucose_trend,
    get_pregnancy_history as _get_pregnancy_history,
    get_maternal_risk_profile as _get_maternal_risk_profile,
)
from mamaguard.shared.tools.pediatric import (
    get_immunization_gaps as _get_immunization_gaps,
    get_developmental_screening_status as _get_developmental_screening_status,
    get_care_gaps as _get_care_gaps,
)
from mamaguard.shared.tools.sdoh import (
    get_sdoh_screening as _get_sdoh_screening,
    find_sdoh_resources as _find_sdoh_resources,
)
from mamaguard.shared.tools.writeback import (
    write_risk_assessment as _write_risk_assessment,
    create_communication_request as _create_communication_request,
    write_care_plan as _write_care_plan,
)

# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="mamaguard",
    instructions=(
        "MamaGuard FHIR tools for maternal and pediatric health assessment. "
        "Pass EHR session credentials (fhir_url, fhir_token, patient_id) with "
        "every call. These are the SHARP extension fields: fhirUrl → fhir_url, "
        "fhirToken → fhir_token, patientId → patient_id."
    ),
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ctx(fhir_url: str, fhir_token: str, patient_id: str) -> FhirContext:
    return FhirContext(fhir_url=fhir_url, fhir_token=fhir_token, patient_id=patient_id)


def _json(result: dict) -> str:
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Tool 1: get_patient_summary
# ---------------------------------------------------------------------------

@mcp.tool()
def get_patient_summary(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
) -> str:
    """
    Fetch a comprehensive patient summary from the FHIR server.

    Returns demographics, active conditions, active medications, and recent
    vital signs. Use this as the first tool in any clinical workflow.

    Args:
        fhir_url: Base URL of the FHIR R4 server (e.g. https://r4.smarthealthit.org)
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
    """
    return _json(_get_patient_summary(_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 2: get_active_medications
# ---------------------------------------------------------------------------

@mcp.tool()
def get_active_medications(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
) -> str:
    """
    Retrieve the patient's current active medication list.

    Returns medication names, dosage instructions, and prescribing dates.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
    """
    return _json(_get_active_medications(_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 3: get_bp_trend
# ---------------------------------------------------------------------------

@mcp.tool()
def get_bp_trend(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    months_back: int = 24,
) -> str:
    """
    Get blood pressure trend for maternal monitoring.

    Queries LOINC 55284-4 (Blood pressure panel). Returns readings, trend
    direction (increasing/stable/decreasing), and an alert flag if any
    reading exceeds 140/90 mmHg (postpartum hypertension threshold).

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
        months_back: How many months of history to retrieve (default 24)
    """
    return _json(_get_bp_trend(months_back=months_back, tool_context=_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 4: get_glucose_trend
# ---------------------------------------------------------------------------

@mcp.tool()
def get_glucose_trend(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    months_back: int = 24,
) -> str:
    """
    Get glucose and HbA1c trend for gestational diabetes monitoring.

    Returns fasting glucose and HbA1c readings with trend analysis. Flags
    HbA1c ≥ 6.5% (diabetes threshold) and fasting glucose ≥ 126 mg/dL.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
        months_back: How many months of history to retrieve (default 24)
    """
    return _json(_get_glucose_trend(months_back=months_back, tool_context=_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 5: get_pregnancy_history
# ---------------------------------------------------------------------------

@mcp.tool()
def get_pregnancy_history(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
) -> str:
    """
    Retrieve complete pregnancy history including outcomes and complications.

    Queries Condition resources for pregnancy-related SNOMED codes. Returns
    gravida/para summary, prior complications (pre-eclampsia, GDM, preterm
    delivery), and current pregnancy status.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
    """
    return _json(_get_pregnancy_history(tool_context=_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 6: get_maternal_risk_profile
# ---------------------------------------------------------------------------

@mcp.tool()
def get_maternal_risk_profile(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
) -> str:
    """
    Generate a compound maternal risk profile for clinical decision support.

    Combines active conditions, recent observations, and medications into a
    structured risk summary. Highlights postpartum hypertension, GDM, SDOH
    barriers, and medication non-adherence signals.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
    """
    return _json(_get_maternal_risk_profile(tool_context=_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 7: get_immunization_gaps
# ---------------------------------------------------------------------------

@mcp.tool()
def get_immunization_gaps(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
) -> str:
    """
    Identify immunization gaps relative to the ACIP schedule.

    Compares Immunization resources against age-appropriate ACIP schedule
    milestones. Returns missing vaccines, overdue vaccines, and next
    recommended dates.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
    """
    return _json(_get_immunization_gaps(tool_context=_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 8: get_developmental_screening_status
# ---------------------------------------------------------------------------

@mcp.tool()
def get_developmental_screening_status(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
) -> str:
    """
    Check developmental screening status for pediatric patients.

    Queries Observation resources for ASQ, M-CHAT, and PEDS screening results.
    Returns completed screenings, pending age-appropriate screenings, and any
    flagged developmental concerns.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
    """
    return _json(_get_developmental_screening_status(tool_context=_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 9: get_care_gaps
# ---------------------------------------------------------------------------

@mcp.tool()
def get_care_gaps(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
) -> str:
    """
    Identify open care gaps for preventive and chronic care management.

    Returns HEDIS-aligned care gaps: overdue well-child visits, missing labs,
    chronic disease follow-ups, and preventive screenings. Includes priority
    rating for each gap.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
    """
    return _json(_get_care_gaps(tool_context=_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 10: get_sdoh_screening
# ---------------------------------------------------------------------------

@mcp.tool()
def get_sdoh_screening(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
) -> str:
    """
    Retrieve Social Determinants of Health (SDOH) screening results.

    Queries Observation resources for PRAPARE, Hunger Vital Sign, and AHC
    HRSN screening instruments. Returns Z-codes for identified barriers
    (housing, food, transportation, social isolation).

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token for FHIR server authentication
        patient_id: FHIR Patient resource ID
    """
    return _json(_get_sdoh_screening(tool_context=_ctx(fhir_url, fhir_token, patient_id)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool 11: write_risk_assessment
# ---------------------------------------------------------------------------

@mcp.tool()
def write_risk_assessment(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    risk_type: str,
    probability: float,
    basis: str,
    mitigation: str,
) -> str:
    """
    Write a RiskAssessment resource to the FHIR server.

    Creates a structured RiskAssessment documenting a clinical risk identified
    by AI analysis. Requires a CRUD-enabled FHIR server (HAPI R4 or similar);
    read-only servers (SMART R4 sandbox) will return an error.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token with write permissions
        patient_id: FHIR Patient resource ID
        risk_type: Type of risk (e.g. "postpartum-hypertensive-crisis",
                   "medication-non-response", "recurrent-pregnancy-loss")
        probability: Estimated probability 0.0–1.0
        basis: Evidence basis for the assessment (free text)
        mitigation: Recommended mitigation steps (free text)
    """
    return _json(_write_risk_assessment(
        risk_type=risk_type,
        probability=probability,
        basis=basis,
        mitigation=mitigation,
        tool_context=_ctx(fhir_url, fhir_token, patient_id),  # type: ignore[arg-type]
    ))


# ---------------------------------------------------------------------------
# Tool 12: create_communication_request
# ---------------------------------------------------------------------------

@mcp.tool()
def create_communication_request(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    medium: str,
    content: str,
    priority: str = "routine",
) -> str:
    """
    Create a CommunicationRequest on the FHIR server.

    Generates a care-team outreach request — scheduling a follow-up call,
    sending educational materials, requesting an interpreter, etc.
    Requires a CRUD-enabled FHIR server.

    Args:
        fhir_url: Base URL of the FHIR R4 server
        fhir_token: Bearer token with write permissions
        patient_id: FHIR Patient resource ID
        medium: Communication medium ("phone", "email", "sms", "mail")
        content: Message content or purpose (free text)
        priority: Priority level ("routine", "urgent", "asap", "stat")
    """
    return _json(_create_communication_request(
        medium=medium,
        content=content,
        priority=priority,
        tool_context=_ctx(fhir_url, fhir_token, patient_id),  # type: ignore[arg-type]
    ))


# ---------------------------------------------------------------------------
# Tool 13: find_sdoh_resources (Phase 2c actionable SDOH)
# ---------------------------------------------------------------------------

@mcp.tool()
def find_sdoh_resources(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    category_or_code: str,
    zip_code: str,
) -> str:
    """
    Look up concrete, callable SDOH resources for a Z-code + ZIP.

    Tries an external directory (findhelp.org / 211 gateway) when
    MAMAGUARD_SDOH_API_URL is set on the server, and falls back to a
    curated offline list of national hotlines + federal programs so the
    SDOH agent is always actionable — even when the external directory
    is unreachable.

    Args:
        fhir_url: Base URL of the FHIR R4 server (not used by this tool
            today, but kept on the signature for SHARP consistency).
        fhir_token: Bearer token (unused, SHARP consistency).
        patient_id: FHIR Patient resource ID (unused, SHARP consistency).
        category_or_code: ICD-10 Z-code ("Z59.0"), SNOMED code, or a
            plain-English category ("housing", "food").
        zip_code: Patient ZIP.
    """
    return _json(_find_sdoh_resources(
        category_or_code=category_or_code,
        zip_code=zip_code,
        tool_context=_ctx(fhir_url, fhir_token, patient_id),  # type: ignore[arg-type]
    ))


# ---------------------------------------------------------------------------
# Tool 14: write_care_plan (Phase 2c actionable SDOH)
# ---------------------------------------------------------------------------

@mcp.tool()
def write_care_plan(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    category: str,
    goal_description: str,
    resource_name: str,
    resource_contact: str,
    resource_url: str = "",
    z_code: str = "",
) -> str:
    """
    Create a linked FHIR Goal + CarePlan documenting an SDOH referral.

    The Goal encodes what we want to achieve for the patient; the
    CarePlan references the Goal and carries the concrete resource
    details in an activity detail so a navigator can pick it up and
    call the referenced organization. Returns a `partial` status if the
    Goal writes but the CarePlan write is rejected — the Goal is still
    trackable in the patient record.

    Args:
        fhir_url: Base URL of the FHIR R4 server.
        fhir_token: Bearer token with write permissions.
        patient_id: FHIR Patient resource ID.
        category: Resolved SDOH category ("housing", "food", ...).
        goal_description: Human-readable goal.
        resource_name: Name of the matched resource.
        resource_contact: Contact string ("Dial 211", "1-800-...").
        resource_url: Optional resource URL.
        z_code: Optional ICD-10 Z-code for Goal.addresses.
    """
    return _json(_write_care_plan(
        category=category,
        goal_description=goal_description,
        resource_name=resource_name,
        resource_contact=resource_contact,
        resource_url=resource_url,
        z_code=z_code,
        tool_context=_ctx(fhir_url, fhir_token, patient_id),  # type: ignore[arg-type]
    ))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8080"))
        mcp.run(transport="sse", host=host, port=port)  # type: ignore[call-arg]
    else:
        mcp.run(transport="stdio")
