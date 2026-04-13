"""
FHIR context hook -- ADK before_model_callback.

Extracts FHIR credentials from A2A message metadata and stores them in
session state so tools can use them without credentials appearing in prompts.
"""

import json
import logging
import os
from urllib.parse import urlparse

from .logging_utils import safe_pretty_json, serialize_for_log, token_fingerprint
from .smart_tickets import (
    SMART_TICKETS_ENABLED,
    TicketError,
    decode_permission_ticket,
)

logger = logging.getLogger(__name__)

LOG_HOOK_RAW_OBJECTS = os.getenv("LOG_HOOK_RAW_OBJECTS", "false").lower() == "true"

FHIR_CONTEXT_KEY = "fhir-context"


def _first_non_empty(*values):
    for v in values:
        if v not in (None, ""):
            return v
    return None


def _safe_correlation_ids(callback_context, llm_request) -> dict:
    return {
        "task_id": _first_non_empty(
            getattr(llm_request, "task_id", None),
            getattr(callback_context, "task_id", None),
        ),
        "context_id": _first_non_empty(
            getattr(llm_request, "context_id", None),
            getattr(callback_context, "context_id", None),
        ),
        "message_id": _first_non_empty(
            getattr(llm_request, "message_id", None),
            getattr(callback_context, "message_id", None),
        ),
    }


def _coerce_fhir_data(value):
    """Accept either a dict or a JSON string; return a dict or None."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def validate_sharp_context(fhir_url: str, patient_id: str, fhir_token: str) -> list[str]:
    """
    Validate SHARP/FHIR context fields.

    Returns a list of error strings (empty if all fields are valid).
    Rules:
      - fhir_url must start with https:// or http://localhost
      - patient_id must be a non-empty string
      - fhir_token must be a non-empty string
    """
    errors: list[str] = []

    if not isinstance(patient_id, str) or not patient_id.strip():
        errors.append("patient_id must be a non-empty string")

    if not isinstance(fhir_token, str) or not fhir_token.strip():
        errors.append("fhir_token must be a non-empty string")

    if not isinstance(fhir_url, str) or not fhir_url.strip():
        errors.append("fhir_url must be a non-empty string")
    else:
        parsed = urlparse(fhir_url.strip())
        is_https = parsed.scheme == "https"
        is_localhost = parsed.scheme == "http" and (
            parsed.hostname in ("localhost", "127.0.0.1")
        )
        if not (is_https or is_localhost):
            errors.append(
                "fhir_url must start with https:// or http://localhost "
                f"(got {fhir_url!r})"
            )

    return errors


def _extract_metadata_sources(callback_context, llm_request) -> list:
    """Return candidate metadata dicts in priority order."""
    callback_metadata = getattr(callback_context, "metadata", None)

    run_config = getattr(callback_context, "run_config", None)
    custom_metadata = getattr(run_config, "custom_metadata", None) if run_config else None
    a2a_metadata = custom_metadata.get("a2a_metadata") if isinstance(custom_metadata, dict) else None

    llm_payload = serialize_for_log(llm_request)
    contents = llm_payload.get("contents", []) if isinstance(llm_payload, dict) else []
    content_metadata = None
    if contents and isinstance(contents, list):
        last = contents[-1]
        if isinstance(last, dict):
            content_metadata = last.get("metadata")

    return [
        ("callback_context.metadata", callback_metadata),
        ("callback_context.run_config.custom_metadata.a2a_metadata", a2a_metadata),
        ("llm_request.contents[-1].metadata", content_metadata),
    ]


def _extract_smart_ticket(fhir_data: dict, state: dict, correlation: dict) -> None:
    """
    If SMART Permission Tickets are enabled and the FHIR context contains a
    ``permissionTicket`` JWT, decode it and store the validated
    ``PermissionTicket`` in ``state["smart_ticket"]``.

    On decode failure the error is logged but the request is **not** blocked —
    the tool-level enforcement in ``smart_tickets.enforce_smart_ticket`` will
    return a structured error when the tool is actually invoked.
    """
    if not SMART_TICKETS_ENABLED:
        return

    raw_ticket = fhir_data.get("permissionTicket", "")
    if not raw_ticket:
        logger.info(
            "smart_ticket_not_present task_id=%s",
            correlation.get("task_id"),
        )
        return

    try:
        ticket = decode_permission_ticket(raw_ticket)
        state["smart_ticket"] = ticket
        logger.info(
            "smart_ticket_decoded task_id=%s sub=%s scopes=%s exp=%d",
            correlation.get("task_id"),
            ticket.sub,
            " ".join(sorted(ticket.scopes)),
            ticket.exp,
        )
    except TicketError as exc:
        logger.warning(
            "smart_ticket_decode_failed task_id=%s error=%s",
            correlation.get("task_id"),
            exc,
        )


def extract_fhir_from_payload(payload: dict):
    """
    Extract FHIR context from a raw JSON-RPC payload dict.
    Returns (key, fhir_data_dict) or (None, None).
    """
    if not isinstance(payload, dict):
        return None, None

    params = payload.get("params")
    if not isinstance(params, dict):
        return None, None

    for metadata in (params.get("metadata"), (params.get("message") or {}).get("metadata")):
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if FHIR_CONTEXT_KEY in str(key):
                    return key, _coerce_fhir_data(value)

    return None, None


def extract_fhir_context(callback_context, llm_request):
    """
    ADK before_model_callback.
    Reads FHIR credentials from A2A message metadata and writes them into
    callback_context.state so that tools can call the FHIR server.
    Returns None (does not modify the LLM request).
    """
    correlation = _safe_correlation_ids(callback_context, llm_request)
    metadata_sources = _extract_metadata_sources(callback_context, llm_request)

    selected_source = "none"
    metadata = {}
    for source_name, candidate in metadata_sources:
        if isinstance(candidate, dict) and candidate:
            metadata = candidate
            selected_source = source_name
            break

    metadata_keys = list(metadata.keys())

    if LOG_HOOK_RAW_OBJECTS:
        logger.info("hook_raw_llm_request=\n%s", safe_pretty_json(serialize_for_log(llm_request)))
        logger.info(
            "hook_raw_callback_context=\n%s",
            safe_pretty_json({
                "task_id": getattr(callback_context, "task_id", None),
                "context_id": getattr(callback_context, "context_id", None),
                "message_id": getattr(callback_context, "message_id", None),
                "metadata": serialize_for_log(getattr(callback_context, "metadata", None)),
                "state": serialize_for_log(getattr(callback_context, "state", None)),
            }),
        )

    logger.info(
        "hook_called_enter task_id=%s context_id=%s message_id=%s metadata_source=%s metadata_keys=%s",
        correlation["task_id"], correlation["context_id"], correlation["message_id"],
        selected_source, metadata_keys,
    )

    if not metadata:
        logger.info(
            "hook_called_no_metadata task_id=%s context_id=%s message_id=%s",
            correlation["task_id"], correlation["context_id"], correlation["message_id"],
        )
        return None

    if not isinstance(metadata, dict):
        logger.warning(
            "hook_called_metadata_invalid_shape task_id=%s context_id=%s message_id=%s metadata_type=%s",
            correlation["task_id"], correlation["context_id"], correlation["message_id"],
            type(metadata).__name__,
        )
        return None

    fhir_data = None
    for key, value in metadata.items():
        if FHIR_CONTEXT_KEY in str(key):
            fhir_data = _coerce_fhir_data(value)
            if fhir_data is None:
                logger.warning(
                    "hook_called_fhir_malformed task_id=%s context_id=%s message_id=%s "
                    "metadata_key=%s value_type=%s",
                    correlation["task_id"], correlation["context_id"], correlation["message_id"],
                    key, type(value).__name__,
                )
            break

    if fhir_data:
        fhir_url = fhir_data.get("fhirUrl", "")
        fhir_token = fhir_data.get("fhirToken", "")
        patient_id = fhir_data.get("patientId", "")

        # -- SHARP context validation --------------------------------------
        validation_errors = validate_sharp_context(
            fhir_url or "", patient_id or "", fhir_token or "",
        )
        if validation_errors:
            callback_context.state["fhir_context_errors"] = validation_errors
            for err in validation_errors:
                logger.warning(
                    "sharp_context_invalid task_id=%s error=%s",
                    correlation["task_id"], err,
                )

        callback_context.state["fhir_url"] = fhir_url
        callback_context.state["fhir_token"] = fhir_token
        callback_context.state["patient_id"] = patient_id

        logger.info("FHIR_URL_FOUND value=%s", callback_context.state["fhir_url"] or "[EMPTY]")
        logger.info("FHIR_TOKEN_FOUND fingerprint=%s", token_fingerprint(callback_context.state["fhir_token"]))
        logger.info("FHIR_PATIENT_FOUND value=%s", callback_context.state["patient_id"] or "[EMPTY]")

        # -- SMART Permission Ticket extraction (feature-flagged) ----------
        _extract_smart_ticket(fhir_data, callback_context.state, correlation)

        logger.info(
            "hook_called_fhir_found task_id=%s context_id=%s message_id=%s "
            "patient_id=%s fhir_url_set=%s fhir_token=%s",
            correlation["task_id"], correlation["context_id"], correlation["message_id"],
            callback_context.state["patient_id"],
            bool(callback_context.state["fhir_url"]),
            token_fingerprint(callback_context.state["fhir_token"]),
        )
    else:
        logger.info(
            "hook_called_fhir_not_found task_id=%s context_id=%s message_id=%s metadata_keys=%s",
            correlation["task_id"], correlation["context_id"], correlation["message_id"],
            metadata_keys,
        )

    # -- output_format extraction (for JSON output mode) --------------------
    output_format = metadata.get("output_format", "")
    if output_format:
        callback_context.state["output_format"] = output_format
        logger.info("output_format=%s", output_format)

    logger.info(
        "hook_called_exit task_id=%s context_id=%s message_id=%s patient_id=%s",
        correlation["task_id"], correlation["context_id"], correlation["message_id"],
        callback_context.state.get("patient_id", ""),
    )

    return None
