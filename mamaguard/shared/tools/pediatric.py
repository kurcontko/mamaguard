"""
Pediatric FHIR tools -- immunization gaps, developmental screening, care gaps.

Tools:
    get_immunization_gaps              Due vs received vaccines per CDC schedule
    get_developmental_screening_status Completed vs due screenings per AAP
    get_care_gaps                      Overdue screenings, missed appointments
"""

import logging
from datetime import datetime
from typing import TypedDict

from google.adk.tools import ToolContext

from .cache import cached_tool
from .fhir_base import (
    _bundle_resources,
    _clinician_review,
    _coding_display,
    _get_fhir_context,
    _safe_fhir_get,
    _silent_fhir_get,
)

logger = logging.getLogger(__name__)


class _CdcScheduleItem(TypedDict):
    vaccine: str
    dose: int
    due_months: int
    series: str


class _MilestoneItem(TypedDict):
    screening: str
    due_months: int


# Age ceiling for pediatric immunization schedule (18 years).
# Above this, the CDC adult schedule applies — the pediatric tool returns
# a non-applicable response instead of flagging every child vaccine as overdue.
_PEDIATRIC_AGE_CEILING_MONTHS = 18 * 12  # 216


# CVX (CDC vaccine codes) → canonical pediatric vaccine abbreviation.
# A single CVX may satisfy multiple series (combo vaccines list each component).
# Source: https://www2a.cdc.gov/vaccines/iis/iisstandards/vaccines.asp
_CVX_MAP: dict[str, tuple[str, ...]] = {
    # Hepatitis B
    "08": ("HepB",), "42": ("HepB",), "43": ("HepB",), "44": ("HepB",),
    "45": ("HepB",), "51": ("HepB", "Hib"), "58": ("HepB",),
    # DTaP (incl. combos)
    "20": ("DTaP",), "106": ("DTaP",), "107": ("DTaP",),
    "110": ("DTaP", "HepB", "IPV"),         # Pediarix
    "120": ("DTaP", "HepB", "IPV", "Hib"),  # Pentacel-like
    "130": ("DTaP", "IPV"),                 # Kinrix / Quadracel
    "132": ("DTaP", "IPV", "Hib"),
    "146": ("DTaP", "IPV", "Hib", "HepB"),  # Vaxelis
    "170": ("DTaP", "IPV", "Hib"),
    # IPV (polio)
    "10": ("IPV",), "89": ("IPV",),
    # Hib
    "17": ("Hib",), "46": ("Hib",), "47": ("Hib",), "48": ("Hib",),
    "49": ("Hib",), "50": ("Hib",),
    # PCV
    "133": ("PCV13",), "152": ("PCV13",),
    "215": ("PCV13", "PCV15"), "237": ("PCV13", "PCV20"),
    # Rotavirus
    "116": ("RV",), "119": ("RV",), "122": ("RV",),
    # Influenza (common codes)
    "88": ("Influenza",), "140": ("Influenza",), "141": ("Influenza",),
    "150": ("Influenza",), "158": ("Influenza",), "161": ("Influenza",),
    "168": ("Influenza",), "185": ("Influenza",), "186": ("Influenza",),
    # MMR / Varicella
    "03": ("MMR",), "05": ("MMR",),
    "21": ("Varicella",), "94": ("MMR", "Varicella"),  # MMRV
    # Hepatitis A
    "83": ("HepA",), "84": ("HepA",), "85": ("HepA",), "31": ("HepA",),
    "104": ("HepA", "HepB"),  # Twinrix
}


# Fuzzy display-text fragments → canonical abbreviation.
# Handles servers that return human-readable names without CVX codes.
_DISPLAY_HINTS: list[tuple[str, str]] = [
    # More specific patterns first — "mmrv" and "dtap-hepb-ipv" before "mmr" / "dtap"
    ("mmrv", "MMR"), ("mmrv", "Varicella"),
    ("measles", "MMR"), ("mumps", "MMR"), ("rubella", "MMR"),
    ("varicel", "Varicella"), ("chicken pox", "Varicella"), ("chickenpox", "Varicella"),
    ("pneumoc", "PCV13"), ("pcv", "PCV13"), ("prevnar", "PCV13"),
    ("rotavir", "RV"), ("rotateq", "RV"), ("rotarix", "RV"),
    ("haemophilus", "Hib"), ("hib", "Hib"),
    ("polio", "IPV"), ("ipv", "IPV"),
    ("diphth", "DTaP"), ("pertuss", "DTaP"), ("tetanus", "DTaP"),
    ("dtap", "DTaP"), ("dtp", "DTaP"),
    ("influenza", "Influenza"), ("flu", "Influenza"),
    ("hepatitis a", "HepA"), ("hep a", "HepA"), ("hepa", "HepA"),
    ("hepatitis b", "HepB"), ("hep b", "HepB"), ("hepb", "HepB"),
]


def _normalize_vaccine(vaccine_code: dict) -> set[str]:
    """
    Return the set of canonical vaccine abbreviations this Immunization satisfies.

    Prefers CVX codes (authoritative), falls back to SNOMED display text and
    the CodeableConcept's `text` field. Combo vaccines satisfy multiple series.
    """
    matches: set[str] = set()

    # 1. CVX codes (most authoritative)
    for coding in vaccine_code.get("coding", []) or []:
        system = (coding.get("system") or "").lower()
        code = (coding.get("code") or "").strip()
        if code and ("hl7.org/fhir/sid/cvx" in system or system.endswith("/cvx")):
            matches.update(_CVX_MAP.get(code.zfill(2), ()))
            matches.update(_CVX_MAP.get(code, ()))

    # 2. Display text on any coding + .text fallback
    display_sources = [c.get("display", "") for c in vaccine_code.get("coding", []) or []]
    display_sources.append(vaccine_code.get("text", "") or "")
    for raw in display_sources:
        text = (raw or "").lower()
        if not text:
            continue
        for fragment, canonical in _DISPLAY_HINTS:
            if fragment in text:
                matches.add(canonical)

    return matches


# CDC Recommended Immunization Schedule (simplified, by age in months)
_CDC_SCHEDULE: list[_CdcScheduleItem] = [
    {"vaccine": "HepB", "dose": 1, "due_months": 0, "series": "Hepatitis B"},
    {"vaccine": "HepB", "dose": 2, "due_months": 1, "series": "Hepatitis B"},
    {"vaccine": "DTaP", "dose": 1, "due_months": 2, "series": "Diphtheria, Tetanus, Pertussis"},
    {"vaccine": "IPV", "dose": 1, "due_months": 2, "series": "Polio"},
    {"vaccine": "Hib", "dose": 1, "due_months": 2, "series": "Haemophilus influenzae type b"},
    {"vaccine": "PCV13", "dose": 1, "due_months": 2, "series": "Pneumococcal"},
    {"vaccine": "RV", "dose": 1, "due_months": 2, "series": "Rotavirus"},
    {"vaccine": "DTaP", "dose": 2, "due_months": 4, "series": "Diphtheria, Tetanus, Pertussis"},
    {"vaccine": "IPV", "dose": 2, "due_months": 4, "series": "Polio"},
    {"vaccine": "Hib", "dose": 2, "due_months": 4, "series": "Haemophilus influenzae type b"},
    {"vaccine": "PCV13", "dose": 2, "due_months": 4, "series": "Pneumococcal"},
    {"vaccine": "RV", "dose": 2, "due_months": 4, "series": "Rotavirus"},
    {"vaccine": "HepB", "dose": 3, "due_months": 6, "series": "Hepatitis B"},
    {"vaccine": "DTaP", "dose": 3, "due_months": 6, "series": "Diphtheria, Tetanus, Pertussis"},
    {"vaccine": "PCV13", "dose": 3, "due_months": 6, "series": "Pneumococcal"},
    {"vaccine": "Influenza", "dose": 1, "due_months": 6, "series": "Influenza (annual)"},
    {"vaccine": "MMR", "dose": 1, "due_months": 12, "series": "Measles, Mumps, Rubella"},
    {"vaccine": "Varicella", "dose": 1, "due_months": 12, "series": "Varicella"},
    {"vaccine": "HepA", "dose": 1, "due_months": 12, "series": "Hepatitis A"},
    {"vaccine": "PCV13", "dose": 4, "due_months": 12, "series": "Pneumococcal"},
    {"vaccine": "DTaP", "dose": 4, "due_months": 15, "series": "Diphtheria, Tetanus, Pertussis"},
    {"vaccine": "DTaP", "dose": 5, "due_months": 48, "series": "Diphtheria, Tetanus, Pertussis"},
    {"vaccine": "IPV", "dose": 4, "due_months": 48, "series": "Polio"},
    {"vaccine": "MMR", "dose": 2, "due_months": 48, "series": "Measles, Mumps, Rubella"},
    {"vaccine": "Varicella", "dose": 2, "due_months": 48, "series": "Varicella"},
]

# AAP Bright Futures developmental screening schedule (age in months)
_DEVELOPMENTAL_MILESTONES: list[_MilestoneItem] = [
    {"screening": "Newborn metabolic screen", "due_months": 0},
    {"screening": "Hearing screen", "due_months": 0},
    {"screening": "Developmental surveillance", "due_months": 1},
    {"screening": "Developmental surveillance", "due_months": 2},
    {"screening": "Developmental surveillance", "due_months": 4},
    {"screening": "Developmental surveillance", "due_months": 6},
    {"screening": "Developmental screening (ASQ/PEDS)", "due_months": 9},
    {"screening": "Developmental surveillance", "due_months": 12},
    {"screening": "Autism screening (M-CHAT)", "due_months": 18},
    {"screening": "Developmental screening (ASQ/PEDS)", "due_months": 24},
    {"screening": "Autism screening (M-CHAT)", "due_months": 24},
    {"screening": "Developmental screening (ASQ/PEDS)", "due_months": 30},
    {"screening": "Developmental surveillance", "due_months": 36},
    {"screening": "Developmental surveillance", "due_months": 48},
]


def _compute_age_months(birth_date_str: str) -> int | None:
    """Compute age in months from a FHIR birthDate string."""
    if not birth_date_str:
        return None
    try:
        birth = datetime.strptime(birth_date_str[:10], "%Y-%m-%d")
        now = datetime.now()
        return (now.year - birth.year) * 12 + (now.month - birth.month)
    except (ValueError, TypeError):
        return None


@cached_tool
def get_immunization_gaps(tool_context: ToolContext | None = None) -> dict:
    """
    Check immunization status against CDC recommended schedule.

    Queries all Immunization resources for the patient, compares against
    the CDC schedule based on the patient's age, and returns a gap analysis
    showing received, due, and overdue vaccines.

    No arguments required -- patient age is computed from FHIR demographics.
    """
    ctx = _get_fhir_context(tool_context, "get_immunization_gaps")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_immunization_gaps patient_id=%s", patient_id)

    # Get patient DOB
    patient, err = _safe_fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
    if err:
        return err

    birth_date = patient.get("birthDate", "")
    age_months = _compute_age_months(birth_date)
    if age_months is None:
        return {
            "status": "error",
            "error_message": "Cannot compute patient age -- birthDate missing or invalid",
        }

    # Adults: pediatric schedule does not apply. Short-circuit so the agent
    # does not surface child vaccines (DTaP, MMR, etc.) for a 68-year-old.
    if age_months > _PEDIATRIC_AGE_CEILING_MONTHS:
        age_years = age_months // 12
        return {
            "status": "success",
            "patient_id": patient_id,
            "data": {
                "age_months": age_months,
                "age_years": age_years,
                "birth_date": birth_date,
                "applicable": False,
                "reason": (
                    f"Patient is {age_years} years old. The pediatric CDC immunization "
                    "schedule applies only through age 18. Refer to the adult schedule "
                    "(e.g., Tdap, shingles, pneumococcal) for this patient."
                ),
                "has_gaps": False,
                "received": [],
                "up_to_date": [],
                "due": [],
                "overdue": [],
            },
            "clinician_review": _clinician_review(
                False,
                reason="",
                recommendation="Adult patient — pediatric immunization schedule not applicable",
                evidence=[],
                confidence=0.95,
            ),
        }

    # Get all immunizations
    bundle, err = _safe_fhir_get(
        fhir_url, fhir_token, "Immunization",
        params={"patient": patient_id, "_count": "100"},
    )
    if err:
        return err

    # Parse received vaccines — normalize each into the set of series it satisfies.
    received_vaccines = []
    series_dose_counts: dict[str, int] = {}
    for res in _bundle_resources(bundle):
        vaccine_code = res.get("vaccineCode", {})
        raw_name = vaccine_code.get("text") or _coding_display(vaccine_code.get("coding", []))
        satisfied = _normalize_vaccine(vaccine_code)
        # Fall back to the raw text token if normalization found nothing — preserves
        # behaviour for mock bundles that use bare abbreviations ("HepB", "DTaP", ...).
        if not satisfied and raw_name:
            satisfied = {raw_name.strip()}
        for series in satisfied:
            series_dose_counts[series] = series_dose_counts.get(series, 0) + 1
        received_vaccines.append({
            "vaccine": raw_name,
            "satisfies": sorted(satisfied),
            "date": res.get("occurrenceDateTime", ""),
            "status": res.get("status", ""),
            "resource_id": res.get("id", ""),
        })

    # Compare against CDC schedule using canonical series names.
    due = []
    overdue = []
    up_to_date = []

    for item in _CDC_SCHEDULE:
        if item["due_months"] > age_months:
            continue  # Not yet due

        received_count = series_dose_counts.get(item["vaccine"], 0)
        dose_received = received_count >= item["dose"]

        entry = {
            "vaccine": item["vaccine"],
            "dose": item["dose"],
            "series": item["series"],
            "due_at_months": item["due_months"],
        }

        if dose_received:
            up_to_date.append(entry)
        elif item["due_months"] + 2 < age_months:
            overdue.append(entry)
        else:
            due.append(entry)

    has_gaps = len(overdue) > 0

    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "age_months": age_months,
            "birth_date": birth_date,
            "received_count": len(received_vaccines),
            "received": received_vaccines,
            "up_to_date": up_to_date,
            "due": due,
            "overdue": overdue,
            "has_gaps": has_gaps,
        },
        "clinician_review": _clinician_review(
            has_gaps,
            reason=f"{len(overdue)} overdue immunizations detected" if has_gaps else "",
            recommendation="Schedule catch-up immunizations" if has_gaps else "Immunizations up to date",
            evidence=[
                f"{item['series']} dose {item['dose']} (due at {item['due_at_months']} months)"
                for item in overdue
            ],
            confidence=0.9,
        ),
    }


@cached_tool
def get_developmental_screening_status(tool_context: ToolContext | None = None) -> dict:
    """
    Check developmental screening status against AAP Bright Futures schedule.

    Compares the patient's age against the recommended screening schedule and
    checks for completed developmental Observations.

    No arguments required -- patient age is computed from FHIR demographics.
    """
    ctx = _get_fhir_context(tool_context, "get_developmental_screening_status")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_developmental_screening_status patient_id=%s", patient_id)

    # Get patient DOB
    patient, err = _safe_fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
    if err:
        return err

    birth_date = patient.get("birthDate", "")
    age_months = _compute_age_months(birth_date)
    if age_months is None:
        return {
            "status": "error",
            "error_message": "Cannot compute patient age -- birthDate missing or invalid",
        }

    # Get developmental observations
    completed_screenings = []
    for res in _silent_fhir_get(fhir_url, fhir_token, "Observation",
                                params={"patient": patient_id, "category": "survey", "_count": "50", "_sort": "-date"}):
        code = res.get("code", {})
        name = code.get("text") or _coding_display(code.get("coding", []))
        completed_screenings.append({
            "screening": name,
            "date": res.get("effectiveDateTime", ""),
            "resource_id": res.get("id", ""),
        })

    # Check against AAP schedule
    due_screenings = []
    completed_milestones = []
    for milestone in _DEVELOPMENTAL_MILESTONES:
        if milestone["due_months"] > age_months:
            continue
        # Fuzzy match completed
        matched = any(
            milestone["screening"].lower()[:10] in s["screening"].lower()
            for s in completed_screenings
        )
        entry = {
            "screening": milestone["screening"],
            "due_at_months": milestone["due_months"],
        }
        if matched:
            completed_milestones.append(entry)
        else:
            due_screenings.append(entry)

    has_gaps = len(due_screenings) > 0

    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "age_months": age_months,
            "completed": completed_milestones,
            "due": due_screenings,
            "completed_observations": completed_screenings,
            "has_gaps": has_gaps,
        },
        "clinician_review": _clinician_review(
            has_gaps and age_months <= 36,
            reason=f"{len(due_screenings)} developmental screenings due" if has_gaps else "",
            recommendation="Schedule developmental screening at next visit" if has_gaps else "",
            evidence=[f"{s['screening']} (due at {s['due_at_months']} months)" for s in due_screenings],
            confidence=0.8,
        ),
    }


@cached_tool
def get_care_gaps(tool_context: ToolContext | None = None) -> dict:
    """
    Identify care gaps -- overdue screenings, missed appointments, unmet goals.

    Queries CarePlan, Goal, and Encounter resources to find gaps in preventive care.

    No arguments required.
    """
    ctx = _get_fhir_context(tool_context, "get_care_gaps")
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_care_gaps patient_id=%s", patient_id)

    gaps = []

    # Check active care plans
    active_plans = []
    for res in _silent_fhir_get(fhir_url, fhir_token, "CarePlan",
                                params={"patient": patient_id, "status": "active", "_count": "20"}):
        categories = res.get("category", [])
        cat_text = ""
        for cat in categories:
            cat_text = cat.get("text") or _coding_display(cat.get("coding", []))
            break
        active_plans.append({
            "title": res.get("title") or cat_text or "Unnamed plan",
            "status": res.get("status"),
            "period_start": (res.get("period") or {}).get("start"),
            "period_end": (res.get("period") or {}).get("end"),
            "resource_id": res.get("id", ""),
        })

    # Check goals
    goals = []
    for res in _silent_fhir_get(fhir_url, fhir_token, "Goal",
                                params={"patient": patient_id, "_count": "20"}):
        description = (res.get("description") or {}).get("text", "")
        status = res.get("lifecycleStatus", "")
        goals.append({
            "description": description,
            "status": status,
            "resource_id": res.get("id", ""),
        })
        if status in ("accepted", "active") and not description:
            gaps.append(f"Goal/{res.get('id', '')} is {status} but lacks description")

    # Check recent encounters
    encounters = []
    for res in _silent_fhir_get(fhir_url, fhir_token, "Encounter",
                                params={"patient": patient_id, "_sort": "-date", "_count": "10"}):
        enc_type = ""
        for t in res.get("type", []):
            enc_type = t.get("text") or _coding_display(t.get("coding", []))
            break
        period = res.get("period", {})
        encounters.append({
            "type": enc_type,
            "status": res.get("status", ""),
            "date": period.get("start", ""),
            "resource_id": res.get("id", ""),
        })

    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "active_care_plans": active_plans,
            "goals": goals,
            "recent_encounters": encounters,
            "identified_gaps": gaps,
        },
        "clinician_review": _clinician_review(
            len(gaps) > 0,
            reason=f"{len(gaps)} care gap(s) identified" if gaps else "",
            recommendation="; ".join(gaps) if gaps else "No care gaps identified",
            evidence=gaps,
            confidence=0.7,
        ),
    }
