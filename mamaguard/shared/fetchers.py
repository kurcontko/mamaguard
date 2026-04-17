"""
Async domain fetchers for the v2 architecture.

Each fetcher wraps the existing sync FHIR tools with asyncio.to_thread so
that all domain queries run in parallel via asyncio.gather. No FHIR logic
is rewritten -- we only compose the existing tool layer.

Used by mamaguard.shared.prefetch.prefetch_clinical_context
(before_agent_callback).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from mamaguard.shared.tools import (
    find_linked_newborn,
    find_sdoh_resources,
    get_active_medications,
    get_care_gaps,
    get_developmental_screening_status,
    get_immunization_gaps,
    get_maternal_risk_profile,
    get_patient_summary,
    get_sdoh_screening,
)

logger = logging.getLogger(__name__)


# -- Lightweight state adapter -----------------------------------------------

class _StateCtx:
    """
    Minimal ToolContext replacement used by the fetchers.

    Existing tools read credentials from ``tool_context.state``; they do not
    require the full ADK ToolContext, only a ``.state`` attribute.  When we
    call a tool from a fetcher we construct one of these with the FHIR
    credentials scoped to the current (possibly child) patient.
    """

    __slots__ = ("state",)

    def __init__(self, fhir_url: str, fhir_token: str, patient_id: str):
        self.state: dict[str, Any] = {
            "fhir_url": fhir_url,
            "fhir_token": fhir_token,
            "patient_id": patient_id,
        }


# -- Structured return types -------------------------------------------------

@dataclass
class MaternalData:
    patient_summary: dict = field(default_factory=dict)
    risk_profile: dict = field(default_factory=dict)
    medications: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    status: str = "ok"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PediatricData:
    linked_child: dict | None = None
    immunizations: dict = field(default_factory=dict)
    development: dict = field(default_factory=dict)
    care_gaps: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    status: str = "ok"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SdohData:
    screening: dict = field(default_factory=dict)
    care_gaps: dict = field(default_factory=dict)
    resources: list = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "ok"

    def to_dict(self) -> dict:
        return asdict(self)


# -- Internal helpers --------------------------------------------------------

def _is_error(result: Any) -> bool:
    return isinstance(result, dict) and result.get("status") == "error"


def _err_message(result: Any) -> str:
    if isinstance(result, dict):
        return result.get("error_message") or str(result)
    return str(result)


async def _call_tool(tool, ctx: _StateCtx) -> Any:
    """Run a sync tool in a thread so asyncio.gather actually parallelises."""
    return await asyncio.to_thread(tool, ctx)


# -- Maternal fetcher --------------------------------------------------------

async def fetch_maternal_data(
    fhir_url: str, fhir_token: str, patient_id: str
) -> MaternalData:
    """Parallel maternal-domain fetch: patient summary + risk profile + meds."""
    ctx = _StateCtx(fhir_url, fhir_token, patient_id)

    summary, risk, meds = await asyncio.gather(
        _call_tool(get_patient_summary, ctx),
        _call_tool(get_maternal_risk_profile, ctx),
        _call_tool(get_active_medications, ctx),
        return_exceptions=True,
    )

    data = MaternalData()

    if isinstance(summary, Exception):
        data.errors.append(f"patient_summary: {summary}")
    elif _is_error(summary):
        data.errors.append(f"patient_summary: {_err_message(summary)}")
    else:
        data.patient_summary = summary

    if isinstance(risk, Exception):
        data.errors.append(f"risk_profile: {risk}")
    elif _is_error(risk):
        data.errors.append(f"risk_profile: {_err_message(risk)}")
    else:
        data.risk_profile = risk

    if isinstance(meds, Exception):
        data.errors.append(f"medications: {meds}")
    elif _is_error(meds):
        data.errors.append(f"medications: {_err_message(meds)}")
    else:
        data.medications = meds

    if data.errors and not (data.patient_summary or data.risk_profile):
        data.status = "error"
    elif data.errors:
        data.status = "partial"

    logger.info(
        "fetch_maternal_data patient=%s status=%s errors=%d",
        patient_id, data.status, len(data.errors),
    )
    return data


# -- Pediatric fetcher -------------------------------------------------------

async def fetch_pediatric_data(
    fhir_url: str, fhir_token: str, patient_id: str
) -> PediatricData:
    """
    Pediatric fetch.

    Step 1: look up linked newborn via RelatedPerson (on mother's patient_id).
    Step 2: if found, switch to the child's patient context and parallel-fetch
            immunizations, developmental screening, and care gaps.
    Step 3: if no linked child, return status=no_linked_child -- the agent
            will note this and the synthesizer will skip the pediatric domain.
    """
    mother_ctx = _StateCtx(fhir_url, fhir_token, patient_id)

    # find_linked_newborn signature: (mother_patient_id, tool_context)
    newborn_result = await asyncio.to_thread(
        find_linked_newborn,
        mother_patient_id=patient_id,
        tool_context=mother_ctx,
    )

    if isinstance(newborn_result, Exception):
        return PediatricData(
            errors=[f"linked_newborn: {newborn_result}"],
            status="error",
        )
    if _is_error(newborn_result):
        return PediatricData(
            errors=[f"linked_newborn: {_err_message(newborn_result)}"],
            status="error",
        )

    children = newborn_result.get("linked_newborns") or []
    if not children:
        logger.info(
            "fetch_pediatric_data patient=%s status=no_linked_child",
            patient_id,
        )
        return PediatricData(
            linked_child=None,
            status="no_linked_child",
        )

    # Use the first linked child for the pediatric assessment.  Multi-child
    # cases are handled by the orchestrator / clinician selection.
    child = children[0]
    child_id = child.get("child_patient_id")
    if not child_id:
        return PediatricData(
            linked_child=child,
            errors=["linked_newborn: missing child_patient_id"],
            status="error",
        )

    child_ctx = _StateCtx(fhir_url, fhir_token, child_id)

    imm, dev, gaps = await asyncio.gather(
        _call_tool(get_immunization_gaps, child_ctx),
        _call_tool(get_developmental_screening_status, child_ctx),
        _call_tool(get_care_gaps, child_ctx),
        return_exceptions=True,
    )

    data = PediatricData(linked_child=child)

    if isinstance(imm, Exception):
        data.errors.append(f"immunizations: {imm}")
    elif _is_error(imm):
        data.errors.append(f"immunizations: {_err_message(imm)}")
    else:
        data.immunizations = imm

    if isinstance(dev, Exception):
        data.errors.append(f"development: {dev}")
    elif _is_error(dev):
        data.errors.append(f"development: {_err_message(dev)}")
    else:
        data.development = dev

    if isinstance(gaps, Exception):
        data.errors.append(f"care_gaps: {gaps}")
    elif _is_error(gaps):
        data.errors.append(f"care_gaps: {_err_message(gaps)}")
    else:
        data.care_gaps = gaps

    if data.errors and not (data.immunizations or data.development):
        data.status = "error"
    elif data.errors:
        data.status = "partial"

    logger.info(
        "fetch_pediatric_data mother=%s child=%s status=%s errors=%d",
        patient_id, child_id, data.status, len(data.errors),
    )
    return data


# -- SDOH fetcher ------------------------------------------------------------

async def fetch_sdoh_data(
    fhir_url: str, fhir_token: str, patient_id: str
) -> SdohData:
    """
    SDOH fetch.

    Step 1: parallel-fetch screening (Z-codes + coverage + language) and
            care gaps.
    Step 2: look up concrete community resources for identified risk
            categories (single lookup per category, deduplicated).
    """
    ctx = _StateCtx(fhir_url, fhir_token, patient_id)

    screening, gaps = await asyncio.gather(
        _call_tool(get_sdoh_screening, ctx),
        _call_tool(get_care_gaps, ctx),
        return_exceptions=True,
    )

    data = SdohData()

    if isinstance(screening, Exception):
        data.errors.append(f"screening: {screening}")
    elif _is_error(screening):
        data.errors.append(f"screening: {_err_message(screening)}")
    else:
        data.screening = screening

    if isinstance(gaps, Exception):
        data.errors.append(f"care_gaps: {gaps}")
    elif _is_error(gaps):
        data.errors.append(f"care_gaps: {_err_message(gaps)}")
    else:
        data.care_gaps = gaps

    # Derive resource lookup categories from screening findings.  The
    # screening tool doesn't emit a categories list, so we infer from its
    # three signal lists (sdoh_conditions, coverage, language).
    categories = _infer_sdoh_categories(data.screening)
    zip_code = ""  # populated below from patient_summary if we fetch it

    if categories:
        lookups = [
            asyncio.to_thread(
                find_sdoh_resources,
                category_or_code=cat,
                zip_code=zip_code,
                tool_context=ctx,
            )
            for cat in categories
        ]
        results = await asyncio.gather(*lookups, return_exceptions=True)
        for cat, res in zip(categories, results):
            if isinstance(res, Exception):
                data.errors.append(f"resources[{cat}]: {res}")
                continue
            if _is_error(res):
                data.errors.append(f"resources[{cat}]: {_err_message(res)}")
                continue
            data.resources.append({"category": cat, "result": res})

    if data.errors and not data.screening:
        data.status = "error"
    elif data.errors:
        data.status = "partial"

    logger.info(
        "fetch_sdoh_data patient=%s status=%s categories=%d errors=%d",
        patient_id, data.status, len(data.resources), len(data.errors),
    )
    return data


async def _call_tool_with_args(tool, ctx: _StateCtx, **kwargs) -> Any:
    """Run a sync tool that takes keyword args alongside the tool context."""
    return await asyncio.to_thread(tool, tool_context=ctx, **kwargs)


# -- SDOH category inference -------------------------------------------------

# Keywords in sdoh_conditions.condition / risk_factors that map to a
# resource-directory category.  Keep the list conservative; the synthesis
# LLM can always ask for a more specific lookup via the tool layer.
_SDOH_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "housing": ("homeless", "housing", "unsheltered", "eviction", "shelter"),
    "food": ("food", "nutrition", "hunger", "snap", "wic"),
    "transportation": ("transport", "ride", "bus"),
    "economic": ("unemploy", "poverty", "income", "financial"),
    "education": ("education", "literacy", "school"),
    "safety": ("abuse", "neglect", "violence", "refugee", "immigration"),
}


def _infer_sdoh_categories(screening: dict) -> list[str]:
    """
    Derive resource-lookup categories from screening output.

    Rules:
      - No coverage resources          -> "insurance"
      - Non-English language detected  -> "language"
      - Condition text / risk factor keyword hit -> matching category
    Categories are deduplicated and capped at 5 to avoid resource-lookup spam.
    """
    if not isinstance(screening, dict):
        return []
    data = screening.get("data") or {}
    categories: list[str] = []

    if not data.get("coverage"):
        categories.append("insurance")

    language = (data.get("language") or "").lower()
    if language and language not in ("english", "en"):
        categories.append("language")

    haystacks: list[str] = []
    for cond in data.get("sdoh_conditions") or []:
        haystacks.append(str(cond.get("condition") or "").lower())
    for rf in data.get("risk_factors") or []:
        haystacks.append(str(rf).lower())

    for cat, keywords in _SDOH_CATEGORY_KEYWORDS.items():
        if any(any(kw in h for kw in keywords) for h in haystacks):
            categories.append(cat)

    # Deduplicate preserving order
    seen: set[str] = set()
    unique = [c for c in categories if not (c in seen or seen.add(c))]
    return unique[:5]
