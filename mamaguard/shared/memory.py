"""
FHIR-native longitudinal memory (architecture v3 shift #3).

Agent memory is stored as FHIR DocumentReference resources attached to the
patient. Each run:

1. `inject_memory_block` (before_model_callback) fetches the most recent
   N memory notes and prepends them to the orchestrator's system prompt
   as a `<patient-memory>` block.
2. `persist_memory_note` (after_model_callback) writes a new
   DocumentReference summarising the current turn — but only on the
   terminal LLM response (no pending tool calls), and only if the
   synthesised output actually contains a 5T Template section.

Why FHIR: PHI stays inside the FHIR server's compliance boundary, memory
survives ephemeral container restarts, and any other agent on the
marketplace can read it via a standard query. Zero new infra.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


FHIR_MEMORY_SYSTEM = "http://mamaguard.ai/codes"
FHIR_MEMORY_CODE = "agent-memory-note"
FHIR_MEMORY_CATEGORY = "clinical-reasoning-history"
DEFAULT_MEMORY_COUNT = 5
_FHIR_TIMEOUT = 10
# Use display-only author. A referenced Device must exist on the server
# (HAPI enforces referential integrity and rejects writes otherwise); a
# display-only Reference is legal FHIR R4 and portable across SMART sandboxes.
_MEMORY_AUTHOR_DISPLAY = "MamaGuard v3"


@dataclass(frozen=True)
class MemoryNote:
    """A single agent-memory-note extracted from a DocumentReference."""

    date: str
    memory_type: str
    content: str
    resource_id: str = ""

    def to_markdown(self) -> str:
        header = f"### {self.date} — {self.memory_type}"
        return f"{header}\n{self.content.strip()}"


# -- Fetch --------------------------------------------------------------------

def fetch_agent_memory(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    count: int = DEFAULT_MEMORY_COUNT,
) -> list[MemoryNote]:
    """
    Fetch the N most recent agent-memory-note DocumentReferences for a patient.

    Returns an empty list on any FHIR error (absent memory is an expected
    state — a first-ever run has none — and must not block the turn).
    """
    if not (fhir_url and fhir_token and patient_id):
        return []

    params = {
        "subject": f"Patient/{patient_id}",
        "category": FHIR_MEMORY_CATEGORY,
        "_sort": "-date",
        "_count": str(count),
    }
    try:
        response = httpx.get(
            f"{fhir_url.rstrip('/')}/DocumentReference",
            params=params,
            headers={
                "Authorization": f"Bearer {fhir_token}",
                "Accept": "application/fhir+json",
            },
            timeout=_FHIR_TIMEOUT,
        )
        response.raise_for_status()
        bundle = response.json()
    except Exception as exc:
        logger.info(
            "memory_fetch_failed patient_id=%s error=%s",
            patient_id, exc,
        )
        return []

    notes: list[MemoryNote] = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource") or {}
        if not _is_mamaguard_memory(resource):
            continue
        note = _extract_note(resource)
        if note is not None:
            notes.append(note)

    logger.info(
        "memory_fetch_ok patient_id=%s count=%d",
        patient_id, len(notes),
    )
    return notes


def _is_mamaguard_memory(resource: dict) -> bool:
    """Guard against DocumentReferences from other authors / systems."""
    if resource.get("resourceType") != "DocumentReference":
        return False
    for type_coding in (resource.get("type") or {}).get("coding", []):
        if (type_coding.get("system") == FHIR_MEMORY_SYSTEM
                and type_coding.get("code") == FHIR_MEMORY_CODE):
            return True
    return False


def _extract_note(resource: dict) -> MemoryNote | None:
    date = resource.get("date") or ""
    memory_type = _extract_memory_subtype(resource) or FHIR_MEMORY_CATEGORY
    for attachment_wrapper in resource.get("content") or []:
        attachment = attachment_wrapper.get("attachment") or {}
        data_b64 = attachment.get("data")
        if not data_b64:
            continue
        try:
            content = base64.b64decode(data_b64).decode("utf-8", errors="replace")
        except Exception:
            continue
        return MemoryNote(
            date=date,
            memory_type=memory_type,
            content=content,
            resource_id=resource.get("id", ""),
        )
    return None


def _extract_memory_subtype(resource: dict) -> str:
    """
    Return the memory subtype (e.g. 'trajectory', 'feedback').

    The subtype is carried as the second coding on `type.coding` (the first
    is always the agent-memory-note marker). Older notes written before this
    change stored the subtype in `category.coding[0]`; we fall back to that
    so historical memory still renders correctly.
    """
    for type_coding in (resource.get("type") or {}).get("coding", []):
        code = type_coding.get("code")
        if code and code != FHIR_MEMORY_CODE:
            return code
    for category in resource.get("category") or []:
        for coding in category.get("coding") or []:
            code = coding.get("code")
            if code and code != FHIR_MEMORY_CATEGORY:
                return code
    return ""


# -- Write --------------------------------------------------------------------

def write_agent_memory(
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    content_markdown: str,
    memory_type: str = "trajectory",
) -> dict:
    """
    POST a new agent-memory-note DocumentReference.

    Returns a status dict similar to the writeback tools. FHIR write failures
    are logged but non-fatal — the clinical response has already been given
    to the user by this point.
    """
    if not content_markdown.strip():
        return {"status": "skipped", "reason": "empty_content"}

    # type.coding carries two labels on the same CodeableConcept:
    #   1. agent-memory-note -- identifies the document as MamaGuard memory
    #      (used by _is_mamaguard_memory to filter the search result).
    #   2. the memory subtype (trajectory / feedback / trajectory-elevated)
    #      -- carries the per-note classification without fracturing the
    #      category axis we need for FHIR search.
    # category is always the stable "clinical-reasoning-history" so the
    # search `category=clinical-reasoning-history` always returns every
    # memory note regardless of subtype.
    type_codings = [{
        "system": FHIR_MEMORY_SYSTEM,
        "code": FHIR_MEMORY_CODE,
        "display": "MamaGuard agent memory note",
    }]
    if memory_type and memory_type != FHIR_MEMORY_CODE:
        type_codings.append({
            "system": FHIR_MEMORY_SYSTEM,
            "code": memory_type,
        })

    resource = {
        "resourceType": "DocumentReference",
        "status": "current",
        "subject": {"reference": f"Patient/{patient_id}"},
        "type": {"coding": type_codings},
        "category": [{
            "coding": [{
                "system": FHIR_MEMORY_SYSTEM,
                "code": FHIR_MEMORY_CATEGORY,
                "display": "Clinical reasoning history",
            }],
        }],
        "author": [{"display": _MEMORY_AUTHOR_DISPLAY}],
        "date": datetime.now(timezone.utc).isoformat(),
        "content": [{
            "attachment": {
                "contentType": "text/markdown",
                "data": base64.b64encode(
                    content_markdown.encode("utf-8")
                ).decode("ascii"),
            },
        }],
    }

    try:
        response = httpx.post(
            f"{fhir_url.rstrip('/')}/DocumentReference",
            json=resource,
            headers={
                "Authorization": f"Bearer {fhir_token}",
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            },
            timeout=_FHIR_TIMEOUT,
        )
        response.raise_for_status()
        created = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "memory_write_failed patient_id=%s http_status=%d",
            patient_id, exc.response.status_code,
        )
        return {
            "status": "error",
            "http_status": exc.response.status_code,
            "error_message": (
                f"FHIR rejected memory write (HTTP {exc.response.status_code}). "
                "Read-only servers silently drop memory; HAPI R4 persists it."
            ),
        }
    except Exception as exc:
        logger.warning(
            "memory_write_exception patient_id=%s error=%s",
            patient_id, exc,
        )
        return {"status": "error", "error_message": str(exc)}

    resource_id = created.get("id", "unknown")
    logger.info(
        "memory_write_ok patient_id=%s resource_id=%s type=%s",
        patient_id, resource_id, memory_type,
    )
    return {
        "status": "success",
        "resource_id": resource_id,
        "memory_type": memory_type,
    }


# -- Prompt injection ---------------------------------------------------------

def format_memory_block(notes: list[MemoryNote]) -> str:
    """Render notes as a `<patient-memory>` block for system instructions."""
    if not notes:
        return ""
    body = "\n\n".join(note.to_markdown() for note in notes)
    return (
        "<patient-memory>\n"
        "Prior MamaGuard assessments for this patient (newest first). "
        "Use these to spot trajectories (e.g. rising BP, repeated missed visits) "
        "and to avoid re-proposing interventions a clinician has already declined.\n\n"
        f"{body}\n"
        "</patient-memory>"
    )


def inject_memory_block(callback_context, llm_request) -> None:
    """
    ADK before_model_callback.

    Reads FHIR context (populated earlier in the callback chain by
    extract_fhir_context), fetches recent memory notes, and appends a
    `<patient-memory>` block to the system instruction.
    """
    state = callback_context.state
    fhir_url = state.get("fhir_url", "")
    fhir_token = state.get("fhir_token", "")
    patient_id = state.get("patient_id", "")

    if not (fhir_url and fhir_token and patient_id):
        return None

    # Fetch once per invocation: before_model_callback fires on every LLM hop
    # but the memory is stable within a turn.
    if state.get("_memory_injected_for") == patient_id:
        return None

    notes = fetch_agent_memory(fhir_url, fhir_token, patient_id)
    state["_memory_injected_for"] = patient_id
    state["_memory_note_count"] = len(notes)

    if not notes:
        return None

    block = format_memory_block(notes)
    _append_to_system_instruction(llm_request, block)
    logger.info(
        "memory_injected patient_id=%s notes=%d bytes=%d",
        patient_id, len(notes), len(block),
    )
    return None


def _append_to_system_instruction(llm_request: Any, block: str) -> None:
    """
    Append `block` to llm_request.config.system_instruction.

    ADK wraps system instructions in a Content; we tolerate either a plain
    string or a structured object and fall back to a best-effort append.
    """
    config = getattr(llm_request, "config", None)
    if config is None:
        return
    existing = getattr(config, "system_instruction", None)
    if existing is None:
        config.system_instruction = block
        return
    if isinstance(existing, str):
        config.system_instruction = f"{existing}\n\n{block}"
        return
    # Structured Content: append a text part if we can.
    parts = getattr(existing, "parts", None)
    if isinstance(parts, list):
        try:
            from google.genai import types
            parts.append(types.Part.from_text(text=block))
            return
        except Exception:
            pass
    # Last resort: stringify.
    config.system_instruction = f"{existing}\n\n{block}"


# -- Persistence after the turn ----------------------------------------------

def persist_memory_note(callback_context, llm_response) -> None:
    """
    ADK after_model_callback.

    On the terminal LLM response (no pending tool calls), derive a concise
    memory note from the synthesised 5T output and POST it to FHIR.

    Non-terminal responses (those carrying function calls) are skipped
    so we only persist the final synthesis, not intermediate reasoning.
    """
    if _has_pending_tool_calls(llm_response):
        return None

    state = callback_context.state
    fhir_url = state.get("fhir_url", "")
    fhir_token = state.get("fhir_token", "")
    patient_id = state.get("patient_id", "")
    if not (fhir_url and fhir_token and patient_id):
        return None

    if state.get("_memory_persisted"):
        return None

    text = _response_text(llm_response)
    note = _derive_memory_note(text)
    if not note:
        return None

    state["_memory_persisted"] = True
    result = write_agent_memory(
        fhir_url, fhir_token, patient_id,
        content_markdown=note,
        memory_type=_classify_memory(note),
    )
    state["_memory_write_status"] = result.get("status")
    return None


def _has_pending_tool_calls(llm_response: Any) -> bool:
    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return False
    for part in parts:
        if getattr(part, "function_call", None):
            return True
    return False


def _response_text(llm_response: Any) -> str:
    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return ""
    chunks: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text and not getattr(part, "thought", False):
            chunks.append(text)
    return "\n".join(chunks)


# Keep the memory note compact — this is what every future turn reads back.
_MAX_NOTE_CHARS = 2000
_TEMPLATE_MARKER = "**Template**"
_TALK_MARKER = "**Talk**"
_TABLE_MARKER = "**Table**"


def _derive_memory_note(response_text: str) -> str:
    """
    Keep the Talk + Template sections of the 5T output. These carry the
    clinical verdict; Table/Task/Transaction are either duplicated data
    or ephemeral write-back IDs not worth re-reading on the next visit.
    """
    if not response_text or _TEMPLATE_MARKER not in response_text:
        return ""

    talk_start = response_text.find(_TALK_MARKER)
    template_start = response_text.find(_TEMPLATE_MARKER)
    table_start = response_text.find(_TABLE_MARKER)

    start = talk_start if talk_start != -1 else template_start
    end = table_start if table_start != -1 else len(response_text)
    excerpt = response_text[start:end].strip()
    if len(excerpt) > _MAX_NOTE_CHARS:
        excerpt = excerpt[:_MAX_NOTE_CHARS].rstrip() + "\n…[truncated]"
    return excerpt


def _classify_memory(note: str) -> str:
    """Coarse type tag so future fetchers can differentiate note styles."""
    lowered = note.lower()
    if "urgent" in lowered or "high" in lowered:
        return "trajectory-elevated"
    return "trajectory"
