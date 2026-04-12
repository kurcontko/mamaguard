"""
SMART Permission Tickets — reference implementation.

Based on Josh Mandel's "SMART Permission Tickets" CI build draft (March 6, 2026).
Feature-flagged via MAMAGUARD_SMART_TICKETS environment variable.

A permission ticket is a signed JWT containing:
  - sub: patient ID (must match session patient_id)
  - scope: space-delimited SMART v2 scopes (e.g. "patient/Observation.rs patient/Condition.rs")
  - exp: expiration timestamp
  - iss: issuer URL
  - aud: audience (agent URL, optional validation)

Each MamaGuard tool declares the SMART scopes it requires. When tickets are
enabled, the tool layer checks that the ticket grants every required scope
before executing the FHIR call.
"""

import logging
import os
import time
from dataclasses import dataclass, field

import jwt

logger = logging.getLogger(__name__)

# Feature flag — off by default; set to "true" to enable ticket enforcement.
SMART_TICKETS_ENABLED = os.getenv("MAMAGUARD_SMART_TICKETS", "").lower() == "true"

# Signing key for HS256 verification (dev/test).  Production should use RS256
# with a JWKS endpoint; this reference implementation covers the HS256 path
# and documents the RS256 extension point.
SMART_TICKETS_SECRET = os.getenv("MAMAGUARD_SMART_TICKETS_SECRET", "")

# Optional audience claim to validate against.
SMART_TICKETS_AUDIENCE = os.getenv("MAMAGUARD_SMART_TICKETS_AUDIENCE", "")

# Algorithms accepted for ticket verification.
_ACCEPTED_ALGORITHMS = ["HS256", "RS256"]


# ---------------------------------------------------------------------------
# PermissionTicket — decoded, validated ticket
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PermissionTicket:
    """A validated SMART Permission Ticket."""

    sub: str                     # Patient ID
    scopes: frozenset[str]       # Granted SMART scopes
    exp: int                     # Expiration (Unix timestamp)
    iss: str = ""                # Issuer URL
    aud: str = ""                # Audience
    raw_claims: dict = field(default_factory=dict, repr=False)


# ---------------------------------------------------------------------------
# Tool → required SMART scopes mapping
# ---------------------------------------------------------------------------
# SMART v2 scope syntax: <context>/<resource>.<permissions>
#   context  = "patient" (all MamaGuard tools are patient-context)
#   resource = FHIR resource type
#   permissions: r = read, s = search, c = create, u = update, d = delete
#
# A tool's required scopes list means the ticket must grant ALL of them.

TOOL_SCOPES: dict[str, list[str]] = {
    # -- Read tools ----------------------------------------------------------
    "get_patient_summary": [
        "patient/Patient.rs",
        "patient/Condition.rs",
        "patient/MedicationRequest.rs",
        "patient/Observation.rs",
    ],
    "get_active_medications": [
        "patient/MedicationRequest.rs",
    ],
    "get_bp_trend": [
        "patient/Observation.rs",
    ],
    "get_glucose_trend": [
        "patient/Observation.rs",
    ],
    "get_pregnancy_history": [
        "patient/Condition.rs",
    ],
    "get_maternal_risk_profile": [
        "patient/Observation.rs",
        "patient/Condition.rs",
        "patient/MedicationRequest.rs",
    ],
    "get_immunization_gaps": [
        "patient/Patient.rs",
        "patient/Immunization.rs",
    ],
    "get_developmental_screening_status": [
        "patient/Patient.rs",
        "patient/Observation.rs",
    ],
    "get_care_gaps": [
        "patient/CarePlan.rs",
        "patient/Goal.rs",
        "patient/Condition.rs",
    ],
    "get_sdoh_screening": [
        "patient/Patient.rs",
        "patient/Condition.rs",
        "patient/Coverage.rs",
    ],
    # find_sdoh_resources has no FHIR access (external API only)
    "find_sdoh_resources": [],
    # -- Write tools ---------------------------------------------------------
    "write_risk_assessment": [
        "patient/RiskAssessment.c",
    ],
    "create_communication_request": [
        "patient/CommunicationRequest.c",
    ],
    "write_care_plan": [
        "patient/Goal.c",
        "patient/CarePlan.c",
    ],
}


# ---------------------------------------------------------------------------
# Ticket decoding & validation
# ---------------------------------------------------------------------------

class TicketError(Exception):
    """Raised when a permission ticket is invalid."""


def decode_permission_ticket(
    token: str,
    signing_key: str = "",
    audience: str = "",
    algorithms: list[str] | None = None,
) -> PermissionTicket:
    """
    Decode and validate a SMART Permission Ticket JWT.

    Raises TicketError on any validation failure (malformed, expired,
    missing required claims, audience mismatch).
    """
    key = signing_key or SMART_TICKETS_SECRET
    if not key:
        raise TicketError("No signing key configured for ticket verification")

    algs = algorithms or _ACCEPTED_ALGORITHMS
    aud = audience or SMART_TICKETS_AUDIENCE or None

    decode_opts: dict = {
        "algorithms": algs,
        "options": {"require": ["sub", "scope", "exp"]},
    }
    if aud:
        decode_opts["audience"] = aud

    try:
        claims = jwt.decode(token, key, **decode_opts)
    except jwt.ExpiredSignatureError:
        raise TicketError("Permission ticket has expired")
    except jwt.InvalidAudienceError:
        raise TicketError("Permission ticket audience mismatch")
    except jwt.DecodeError as exc:
        raise TicketError(f"Permission ticket decode failed: {exc}")
    except jwt.MissingRequiredClaimError as exc:
        raise TicketError(f"Permission ticket missing required claim: {exc}")
    except jwt.InvalidTokenError as exc:
        raise TicketError(f"Permission ticket invalid: {exc}")

    scope_str = claims.get("scope", "")
    scopes = frozenset(s for s in scope_str.split() if s)

    return PermissionTicket(
        sub=claims["sub"],
        scopes=scopes,
        exp=claims["exp"],
        iss=claims.get("iss", ""),
        aud=claims.get("aud", ""),
        raw_claims=claims,
    )


# ---------------------------------------------------------------------------
# Scope checking
# ---------------------------------------------------------------------------

def _scope_satisfies(granted: frozenset[str], required: str) -> bool:
    """
    Check if a single required scope is satisfied by the granted set.

    Handles wildcard grants:
      - "patient/*.rs" grants all patient read+search
      - "patient/Observation.cruds" grants "patient/Observation.rs"

    The permission letters in the granted scope must be a superset of those
    in the required scope.
    """
    if required in granted:
        return True

    # Parse required: "patient/Observation.rs" → context="patient", resource="Observation", perms="rs"
    try:
        ctx_res, req_perms = required.rsplit(".", 1)
        req_ctx, req_resource = ctx_res.split("/", 1)
    except ValueError:
        return False

    for g in granted:
        try:
            g_ctx_res, g_perms = g.rsplit(".", 1)
            g_ctx, g_resource = g_ctx_res.split("/", 1)
        except ValueError:
            continue

        if g_ctx != req_ctx:
            continue

        # Wildcard resource match
        if g_resource != "*" and g_resource != req_resource:
            continue

        # Permission letter check: granted must contain all required letters
        if set(req_perms).issubset(set(g_perms)):
            return True

    return False


def check_tool_scope(ticket: PermissionTicket, tool_name: str) -> str | None:
    """
    Verify that the ticket's scopes cover the requirements for *tool_name*.

    Returns None on success, or an error message string if insufficient.
    """
    required = TOOL_SCOPES.get(tool_name)
    if required is None:
        return f"Unknown tool '{tool_name}' — no scope mapping defined"

    if not required:
        return None  # No FHIR scopes needed (e.g. find_sdoh_resources)

    missing = [s for s in required if not _scope_satisfies(ticket.scopes, s)]
    if missing:
        return (
            f"Permission ticket does not grant required scope(s) for {tool_name}: "
            f"{', '.join(missing)}"
        )

    return None


# ---------------------------------------------------------------------------
# Full enforcement helper (used by _get_fhir_context)
# ---------------------------------------------------------------------------

def enforce_smart_ticket(state: dict, tool_name: str) -> dict | None:
    """
    If SMART tickets are enabled, validate the stored ticket against *tool_name*.

    Returns None if enforcement passes (or is disabled).
    Returns an error dict suitable as a tool return value if enforcement fails.
    """
    if not SMART_TICKETS_ENABLED:
        return None

    ticket = state.get("smart_ticket")
    if ticket is None:
        logger.warning("smart_ticket_missing tool=%s", tool_name)
        return {
            "status": "error",
            "error_message": (
                "SMART Permission Ticket is required but not present in session context. "
                "Ensure the caller includes 'permissionTicket' in the FHIR context metadata."
            ),
        }

    if not isinstance(ticket, PermissionTicket):
        logger.warning("smart_ticket_invalid_type tool=%s type=%s", tool_name, type(ticket).__name__)
        return {
            "status": "error",
            "error_message": "SMART Permission Ticket in session state is malformed.",
        }

    # Patient ID match: ticket.sub must match session patient_id
    session_patient = state.get("patient_id", "")
    if session_patient and ticket.sub != session_patient:
        logger.warning(
            "smart_ticket_patient_mismatch tool=%s ticket_sub=%s session_patient=%s",
            tool_name, ticket.sub, session_patient,
        )
        return {
            "status": "error",
            "error_message": (
                f"Permission ticket subject '{ticket.sub}' does not match "
                f"session patient '{session_patient}'."
            ),
        }

    # Check expiration (belt-and-suspenders; JWT decode already checks, but
    # the ticket may have been decoded at session start and now be stale).
    if ticket.exp < int(time.time()):
        logger.warning("smart_ticket_expired tool=%s exp=%d", tool_name, ticket.exp)
        return {
            "status": "error",
            "error_message": "SMART Permission Ticket has expired. Request a new ticket.",
        }

    # Scope check
    scope_err = check_tool_scope(ticket, tool_name)
    if scope_err:
        logger.warning("smart_ticket_scope_denied tool=%s detail=%s", tool_name, scope_err)
        return {
            "status": "error",
            "error_message": scope_err,
        }

    logger.info("smart_ticket_authorized tool=%s scopes=%s", tool_name, " ".join(sorted(ticket.scopes)))
    return None
