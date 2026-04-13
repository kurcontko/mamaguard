"""
Response quality self-check — lightweight post-generation validation.

Checks orchestrator responses for structural completeness:
  (a) All 5T sections present (Talk, Template, Table, Task, Transaction)
  (b) Clinician review mentioned when risk is HIGH/URGENT
  (c) Response under 1500 tokens (approx)

Logs warnings on failure but never blocks the response.
Wired as a step in the orchestrator's ``after_model_callback`` chain.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from google.adk.models.llm_response import LlmResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 5T section detection
# ---------------------------------------------------------------------------

# Matches **Talk**, ## Talk, ### Talk — etc.
_SECTION_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:\*\*|#{1,3}\s*)(Talk|Template|Table|Task|Transaction)"
    r"(?:\*\*)?[\s\-—:]",
    re.IGNORECASE,
)

_ALL_5T = {"talk", "template", "table", "task", "transaction"}

# Risk levels that warrant clinician review
_HIGH_RISK_PATTERN = re.compile(
    r"\b(?:URGENT|HIGH)\b",
)

_CLINICIAN_REVIEW_PATTERN = re.compile(
    r"clinician\s+review",
    re.IGNORECASE,
)

# Rough token estimate: 1 token ≈ 4 characters
_TOKEN_LIMIT = 1500
_CHAR_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_5t_sections(text: str) -> list[str]:
    """Return names of missing 5T sections (empty list = all present)."""
    found = {m.group(1).lower() for m in _SECTION_PATTERN.finditer(text)}
    missing = sorted(_ALL_5T - found)
    return missing


def check_clinician_review(text: str) -> bool:
    """Return True if clinician review is mentioned OR risk is not HIGH/URGENT.

    Returns False (= warning) only when the response contains HIGH/URGENT
    risk but does NOT mention clinician review.
    """
    has_high_risk = _HIGH_RISK_PATTERN.search(text) is not None
    if not has_high_risk:
        return True  # No high risk — no requirement to mention clinician review
    has_review = _CLINICIAN_REVIEW_PATTERN.search(text) is not None
    return has_review


def check_token_length(text: str) -> tuple[bool, int]:
    """Return (under_limit, estimated_tokens).

    Uses a rough heuristic of 1 token ≈ 4 characters.
    """
    estimated = len(text) // _CHAR_PER_TOKEN
    return estimated <= _TOKEN_LIMIT, estimated


# ---------------------------------------------------------------------------
# Combined check
# ---------------------------------------------------------------------------


def run_quality_checks(text: str) -> list[str]:
    """Run all quality checks on response text.

    Returns a list of warning strings (empty = all checks passed).
    """
    if not text or not text.strip():
        return ["Response is empty"]

    warnings: list[str] = []

    # (a) 5T completeness
    missing = check_5t_sections(text)
    if missing:
        warnings.append(
            f"Missing 5T sections: {', '.join(missing)}"
        )

    # (b) Clinician review when HIGH/URGENT
    if not check_clinician_review(text):
        warnings.append(
            "Response has HIGH/URGENT risk but does not mention clinician review"
        )

    # (c) Token length
    under_limit, estimated = check_token_length(text)
    if not under_limit:
        warnings.append(
            f"Response exceeds soft token limit: ~{estimated} tokens (limit {_TOKEN_LIMIT})"
        )

    return warnings


# ---------------------------------------------------------------------------
# ADK after_model_callback
# ---------------------------------------------------------------------------


def quality_check_callback(
    callback_context: Any,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Post-model quality self-check.

    Scans text parts of the LLM response for structural quality issues.
    Logs warnings but never modifies or blocks the response.
    """
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

    warnings = run_quality_checks(full_text)
    if warnings:
        logger.warning(
            "Quality check warnings (%d): %s",
            len(warnings),
            "; ".join(warnings),
        )

    return None
