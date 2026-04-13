"""
Structured JSON output formatter for MamaGuard 5T responses.

When ``output_format=json`` is passed in request metadata, transforms the
orchestrator's markdown 5T response into a machine-readable JSON object:

.. code-block:: json

    {
      "risk_level": "URGENT",
      "talk": "...",
      "findings": [...],
      "tasks": [...],
      "fhir_writes": [...],
      "disclaimer": "..."
    }

This enables programmatic consumption by other A2A agents and downstream
systems without markdown parsing.
"""

from __future__ import annotations

import json
import re
from typing import Any

from google.adk.models.llm_response import LlmResponse

# ---------------------------------------------------------------------------
# 5T Section extraction
# ---------------------------------------------------------------------------

# Match bold or heading-style section markers: **Talk**, ## Talk, etc.
_SECTION_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:\*\*|#{1,3}\s*)(Talk|Template|Table|Task|Transaction)"
    r"(?:\*\*)?[\s\-—:]*",
    re.IGNORECASE,
)

_RISK_LEVEL_PATTERN = re.compile(
    r"(?:Combined\s+)?Risk\s+Level[:\s]*(\b(?:URGENT|HIGH|MODERATE|ROUTINE)\b)",
    re.IGNORECASE,
)

# Task line: "1. URGENT — description | responsible | timeframe"
_TASK_LINE_PATTERN = re.compile(
    r"^\s*\d+\.\s*"
    r"(URGENT|HIGH|MODERATE|ROUTINE)\s*[\-—–]+\s*"
    r"(.+?)$",
    re.IGNORECASE | re.MULTILINE,
)

# FHIR resource references: ResourceType/id
_FHIR_WRITE_PATTERN = re.compile(
    r"\b(RiskAssessment|CarePlan|Goal|CommunicationRequest|AuditEvent)"
    r"/([A-Za-z0-9_\-]+)"
)

# Findings: lines with FHIR Observation/Condition refs and values
_FINDING_LINE_PATTERN = re.compile(
    r"(?:^|\n)\s*[-•*]?\s*(.+?"
    r"(?:Observation|Condition|Coverage|MedicationStatement|Immunization)"
    r"/[A-Za-z0-9_\-]+[^)\n]*)",
    re.IGNORECASE,
)

_DISCLAIMER_PATTERN = re.compile(
    r"(AI-generated\s+analysis[^\n]*(?:Not for clinical use)[^\n]*)",
    re.IGNORECASE,
)

# Confidence patterns:
# "Overall confidence: 0.75 (MODERATE)" or "Overall: 0.88 (HIGH)"
_OVERALL_CONFIDENCE_PATTERN = re.compile(
    r"Overall\s+(?:confidence:?\s*)?(\d+\.\d+)\s*\((\w+)\)",
    re.IGNORECASE,
)

# Per-domain: "Maternal 0.88" or "BP trend 0.9" or "SDOH screening 0.8"
_ITEM_CONFIDENCE_PATTERN = re.compile(
    r"(?:^|[,;.])\s*([A-Za-z][A-Za-z /]+?)\s+(\d+\.\d+)",
)

# Lower confidence flagged items: "Lower confidence: care gaps (0.7) — reason"
_LOW_CONFIDENCE_PATTERN = re.compile(
    r"[Ll]ower\s+confidence[:\s]+(.+?)(?:\n|$)",
)


def _extract_sections(text: str) -> dict[str, str]:
    """Split a 5T markdown response into section name → content."""
    matches = list(_SECTION_PATTERN.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def _extract_risk_level(template_text: str) -> str:
    """Extract risk level from the Template section."""
    m = _RISK_LEVEL_PATTERN.search(template_text)
    return m.group(1).upper() if m else "UNKNOWN"


def _extract_findings(template_text: str) -> list[str]:
    """Extract finding lines from the Template section."""
    findings: list[str] = []
    for m in _FINDING_LINE_PATTERN.finditer(template_text):
        line = m.group(1).strip().rstrip(".,;")
        if line and len(line) > 10:
            findings.append(line)
    # Deduplicate preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for f in findings:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


def _extract_tasks(task_text: str) -> list[dict[str, str]]:
    """Extract structured task items from the Task section."""
    tasks: list[dict[str, str]] = []
    for m in _TASK_LINE_PATTERN.finditer(task_text):
        priority = m.group(1).upper()
        rest = m.group(2).strip()
        # Split on pipe for "description | responsible | timeframe"
        parts = [p.strip() for p in rest.split("|")]
        task: dict[str, str] = {"priority": priority, "description": parts[0]}
        if len(parts) >= 2:
            task["responsible"] = parts[1]
        if len(parts) >= 3:
            task["timeframe"] = parts[2]
        tasks.append(task)
    return tasks


def _extract_fhir_writes(transaction_text: str) -> list[dict[str, str]]:
    """Extract FHIR write-back references from the Transaction section."""
    writes: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _FHIR_WRITE_PATTERN.finditer(transaction_text):
        resource_type = m.group(1)
        resource_id = m.group(2)
        ref = f"{resource_type}/{resource_id}"
        if ref not in seen:
            seen.add(ref)
            writes.append({
                "resource_type": resource_type,
                "resource_id": resource_id,
                "reference": ref,
            })
    return writes


def _extract_confidence(template_text: str) -> dict[str, Any] | None:
    """Extract confidence scoring from the Template section.

    Returns a dict with overall score/label and any flagged low-confidence
    items, or None if no confidence info found.
    """
    m = _OVERALL_CONFIDENCE_PATTERN.search(template_text)
    if not m:
        return None

    result: dict[str, Any] = {
        "overall": float(m.group(1)),
        "label": m.group(2).upper(),
    }

    # Extract per-item confidence scores from the same block
    # Find the confidence line(s) — everything between "Overall confidence" and the next section
    conf_start = template_text.find("onfidence")
    if conf_start >= 0:
        # Find start of line containing "onfidence"
        line_start = template_text.rfind("\n", 0, conf_start)
        line_start = line_start + 1 if line_start >= 0 else 0
        # Find the next section marker or clinician review
        rest = template_text[line_start:]
        # Grab all text until next ⚠ or section marker
        end_markers = [rest.find("⚠"), rest.find("\n**"), rest.find("\n#")]
        end_markers = [e for e in end_markers if e > 0]
        conf_block = rest[:min(end_markers)] if end_markers else rest
        items: dict[str, float] = {}
        for im in _ITEM_CONFIDENCE_PATTERN.finditer(conf_block):
            name = im.group(1).strip()
            score = float(im.group(2))
            # Skip "Overall" itself and very short matches
            if name.lower() != "overall" and len(name) > 1:
                items[name] = score
        if items:
            result["items"] = items

    # Extract lower-confidence flags
    low_m = _LOW_CONFIDENCE_PATTERN.search(template_text)
    if low_m:
        result["low_confidence_flags"] = low_m.group(1).strip()

    return result


def _extract_disclaimer(text: str) -> str:
    """Extract the AI disclaimer from the full response."""
    m = _DISCLAIMER_PATTERN.search(text)
    return m.group(1).strip() if m else ""


def markdown_to_json(text: str) -> dict[str, Any]:
    """Convert a 5T markdown response to structured JSON.

    Returns a dict with:
        - risk_level: str (URGENT/HIGH/MODERATE/ROUTINE/UNKNOWN)
        - talk: str (narrative summary)
        - findings: list[str] (evidence-backed clinical findings)
        - tasks: list[dict] (prioritized action items)
        - fhir_writes: list[dict] (FHIR write-back references)
        - disclaimer: str
    """
    sections = _extract_sections(text)

    risk_level = "UNKNOWN"
    findings: list[str] = []
    confidence: dict[str, Any] | None = None
    if "template" in sections:
        risk_level = _extract_risk_level(sections["template"])
        findings = _extract_findings(sections["template"])
        confidence = _extract_confidence(sections["template"])

    tasks: list[dict[str, str]] = []
    if "task" in sections:
        tasks = _extract_tasks(sections["task"])

    fhir_writes: list[dict[str, str]] = []
    if "transaction" in sections:
        fhir_writes = _extract_fhir_writes(sections["transaction"])

    result: dict[str, Any] = {
        "risk_level": risk_level,
        "talk": sections.get("talk", ""),
        "findings": findings,
        "tasks": tasks,
        "fhir_writes": fhir_writes,
        "disclaimer": _extract_disclaimer(text),
    }
    if confidence:
        result["confidence"] = confidence
    return result


# ---------------------------------------------------------------------------
# Metadata extraction helper
# ---------------------------------------------------------------------------


def get_output_format(callback_context: Any) -> str:
    """Read ``output_format`` from request metadata, defaulting to markdown.

    Checks (in priority order):
      1. callback_context.state["output_format"] (set by fhir_hook or test)
      2. callback_context.metadata.get("output_format")
    """
    state = getattr(callback_context, "state", None) or {}
    fmt = state.get("output_format", "")
    if fmt:
        return fmt.lower()

    metadata = getattr(callback_context, "metadata", None) or {}
    fmt = metadata.get("output_format", "")
    if fmt:
        return fmt.lower()

    return "markdown"


# ---------------------------------------------------------------------------
# ADK after_model_callback
# ---------------------------------------------------------------------------


def json_output_callback(
    callback_context: Any,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Convert 5T markdown response to JSON when output_format=json.

    Reads ``output_format`` from metadata/state. If not ``json``, does
    nothing (returns None). Otherwise, parses the 5T markdown and replaces
    the text part(s) with a single JSON string.
    """
    if get_output_format(callback_context) != "json":
        return None

    content = llm_response.content
    if content is None or content.parts is None:
        return None

    # Collect all text from parts
    full_text = ""
    for part in content.parts:
        if part.text:
            full_text += part.text + "\n"

    if not full_text.strip():
        return None

    structured = markdown_to_json(full_text)

    # Include agent timing data if available in state
    state = getattr(callback_context, "state", None) or {}
    timings = state.get("_agent_timings")
    if timings:
        total = sum(t.get("elapsed_s", 0.0) for t in timings)
        structured["timing"] = {
            "agents": {
                t["agent"]: t["elapsed_s"] for t in timings
            },
            "total_s": round(total, 1),
        }

    json_str = json.dumps(structured, indent=2, ensure_ascii=False)

    # Replace all text parts with a single JSON part
    content.parts[0].text = json_str
    # Clear extra text parts (keep non-text parts like function calls)
    content.parts[:] = [
        p for i, p in enumerate(content.parts)
        if i == 0 or p.text is None
    ]

    return None
