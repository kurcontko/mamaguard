"""
Post-processing safety filter — ADK ``after_model_callback``.

Scans LLM response text for prescribing language that violates the Liaison
Pattern (no autonomous treatment decisions) and redacts it with a safe
deferral phrase.  This is a runtime safety net: even if prompt instructions
fail to prevent prescribing language (observed in Tier-2a for severe
preeclampsia scenarios), this callback catches it before the response
reaches the clinician.

Feature-flagged via ``MAMAGUARD_SAFETY_FILTER`` env var (enabled by default).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from google.adk.models.llm_response import LlmResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENABLED_RAW = os.environ.get("MAMAGUARD_SAFETY_FILTER", "true")
SAFETY_FILTER_ENABLED: bool = _ENABLED_RAW.lower() in ("1", "true", "yes")

REDACTION_PHRASE = (
    "[Specific treatment decisions deferred to treating clinician"
    " — see risk assessment above]"
)

# ---------------------------------------------------------------------------
# Prescribing-language patterns
# ---------------------------------------------------------------------------

# Action verbs that signal autonomous prescribing when combined with a drug
# or dosage.  Designed to catch phrases like "initiate labetalol 200mg IV"
# while NOT matching "patient is currently on labetalol" (reporting existing
# medication from FHIR data).
_PRESCRIBING_VERB_PATTERNS: list[re.Pattern[str]] = [
    # Direct prescribing
    re.compile(
        r"\b(?:i |we )?"
        r"(?:prescribe|administer|initiate|start(?:ing)?|begin(?:ning)?|order(?:ing)?|give|commence)"
        r"\b[^.!?\n]{0,80}?"
        r"(?:\d+\s*(?:mg|mcg|µg|g|mL|units?|IU)\b|"
        r"(?:labetalol|hydralazine|magnesium\s*sulfate|nifedipine|methyldopa|"
        r"metformin|insulin|aspirin|heparin|oxytocin|misoprostol|"
        r"betamethasone|dexamethasone|terbutaline|indomethacin|"
        r"lovenox|enoxaparin|methergine|methylergonovine|"
        r"labetalol|atenolol|amlodipine|lisinopril|enalapril|"
        r"glyburide|metformin|iron|ferrous|folic\s*acid"
        r")\b)",
        re.IGNORECASE,
    ),
    # "start patient on <drug>"
    re.compile(
        r"\bstart\s+(?:the\s+)?(?:patient|her|him|them|mother|mom)\s+on\b",
        re.IGNORECASE,
    ),
    # "initiate treatment/therapy with"
    re.compile(
        r"\binitiate\s+(?:treatment|therapy|medication|antihypertensive|"
        r"magnesium|iv|intravenous)\b",
        re.IGNORECASE,
    ),
    # "begin <drug> therapy"
    re.compile(
        r"\bbegin\s+\w+\s+(?:therapy|treatment|infusion|drip)\b",
        re.IGNORECASE,
    ),
    # Explicit "I prescribe / I'm prescribing"
    re.compile(
        r"\bi(?:'m| am| will| hereby)?\s*prescrib(?:e|ing)\b",
        re.IGNORECASE,
    ),
    # Dosage recommendation: "200 mg IV" or "10 mg/day oral"
    re.compile(
        r"\b(?:give|administer|dose|bolus)\s+\d+\s*(?:mg|mcg|µg|g|mL|units?|IU)\b",
        re.IGNORECASE,
    ),
    # Bare "initiate" in clinical context (broad catch)
    re.compile(
        r"\binitiate\b(?!.*\bclinician\b)",
        re.IGNORECASE,
    ),
    # "begin treatment/therapy with" (broad catch)
    re.compile(
        r"\bbegin\s+(?:treatment|therapy)\s+with\b",
        re.IGNORECASE,
    ),
    # "start her/him/them on"
    re.compile(
        r"\bstart\s+(?:her|him|them|the patient)\s+on\b",
        re.IGNORECASE,
    ),
]

# Sentence-level patterns — if any match, the ENTIRE sentence is redacted.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _is_reporting_existing(sentence: str) -> bool:
    """Return True if the sentence is reporting an existing medication.

    Phrases like 'patient is currently on labetalol' or 'currently taking
    metformin' are NOT prescribing — they report FHIR data.
    """
    reporting = re.search(
        r"\b(?:currently|already|presently|previously)\s+"
        r"(?:on|taking|receiving|prescribed|using)\b",
        sentence,
        re.IGNORECASE,
    )
    return reporting is not None


def filter_prescribing_language(text: str) -> tuple[str, list[str]]:
    """Scan text for prescribing language and redact matching sentences.

    Returns:
        (filtered_text, list_of_redacted_fragments)
    """
    if not text:
        return text, []

    sentences = _SENTENCE_SPLIT.split(text)
    redacted: list[str] = []
    output: list[str] = []

    for sentence in sentences:
        if _is_reporting_existing(sentence):
            output.append(sentence)
            continue

        matched = False
        for pattern in _PRESCRIBING_VERB_PATTERNS:
            if pattern.search(sentence):
                matched = True
                break

        if matched:
            redacted.append(sentence.strip())
            output.append(REDACTION_PHRASE)
        else:
            output.append(sentence)

    return " ".join(output), redacted


# ---------------------------------------------------------------------------
# ADK after_model_callback
# ---------------------------------------------------------------------------


def safety_after_model_callback(
    callback_context: Any,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Post-model safety filter.

    Scans text parts of the LLM response for prescribing language and
    redacts offending sentences.  Returns ``None`` (keep original) when
    the filter is disabled or no prescribing language is found.
    """
    if not SAFETY_FILTER_ENABLED:
        return None

    content = llm_response.content
    if content is None or content.parts is None:
        return None

    any_redacted = False
    all_redacted: list[str] = []

    for part in content.parts:
        if part.text is None:
            continue
        filtered, redacted_items = filter_prescribing_language(part.text)
        if redacted_items:
            part.text = filtered
            all_redacted.extend(redacted_items)
            any_redacted = True

    if any_redacted:
        logger.warning(
            "Safety filter redacted %d prescribing fragment(s): %s",
            len(all_redacted),
            "; ".join(all_redacted[:3]),  # Log at most 3 fragments
        )

    # Return None to keep the (now-mutated) response — no need to replace.
    return None
