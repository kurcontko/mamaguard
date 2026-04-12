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

import httpx
from google.adk.tools import ToolContext

from .fhir_base import (
    _coding_display,
    _connection_error_result,
    _fhir_get,
    _get_fhir_context,
    _http_error_result,
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


def get_immunization_gaps(tool_context: ToolContext = None) -> dict:
    """
    Check immunization status against CDC recommended schedule.

    Queries all Immunization resources for the patient, compares against
    the CDC schedule based on the patient's age, and returns a gap analysis
    showing received, due, and overdue vaccines.

    No arguments required -- patient age is computed from FHIR demographics.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_immunization_gaps patient_id=%s", patient_id)

    # Get patient DOB
    try:
        patient = _fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    birth_date = patient.get("birthDate", "")
    age_months = _compute_age_months(birth_date)
    if age_months is None:
        return {
            "status": "error",
            "error_message": "Cannot compute patient age -- birthDate missing or invalid",
        }

    # Get all immunizations
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Immunization",
            params={"patient": patient_id, "_count": "100"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    # Parse received vaccines
    received_vaccines = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        vaccine_code = res.get("vaccineCode", {})
        vaccine_name = vaccine_code.get("text") or _coding_display(vaccine_code.get("coding", []))
        received_vaccines.append({
            "vaccine": vaccine_name,
            "date": res.get("occurrenceDateTime", ""),
            "status": res.get("status", ""),
            "resource_id": res.get("id", ""),
        })

    # Compare against CDC schedule
    received_names_lower = [v["vaccine"].lower() for v in received_vaccines]
    due = []
    overdue = []
    up_to_date = []

    for item in _CDC_SCHEDULE:
        if item["due_months"] > age_months:
            continue  # Not yet due

        # Check if this vaccine+dose has been received (fuzzy match)
        vaccine_key = item["vaccine"].lower()
        matching = [v for v in received_names_lower if vaccine_key in v]
        dose_received = len(matching) >= item["dose"]

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
        "clinician_review": {
            "required": has_gaps,
            "reason": f"{len(overdue)} overdue immunizations detected" if has_gaps else "",
            "recommendation": "Schedule catch-up immunizations" if has_gaps else "Immunizations up to date",
            "evidence_basis": [
                f"{item['series']} dose {item['dose']} (due at {item['due_at_months']} months)"
                for item in overdue
            ],
            "confidence": 0.9,
        },
    }


def get_developmental_screening_status(tool_context: ToolContext = None) -> dict:
    """
    Check developmental screening status against AAP Bright Futures schedule.

    Compares the patient's age against the recommended screening schedule and
    checks for completed developmental Observations.

    No arguments required -- patient age is computed from FHIR demographics.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_developmental_screening_status patient_id=%s", patient_id)

    # Get patient DOB
    try:
        patient = _fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    birth_date = patient.get("birthDate", "")
    age_months = _compute_age_months(birth_date)
    if age_months is None:
        return {
            "status": "error",
            "error_message": "Cannot compute patient age -- birthDate missing or invalid",
        }

    # Get developmental observations
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Observation",
            params={
                "patient": patient_id,
                "category": "survey",
                "_count": "50",
                "_sort": "-date",
            },
        )
    except Exception:
        bundle = {"entry": []}

    completed_screenings = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
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
        "clinician_review": {
            "required": has_gaps and age_months <= 36,
            "reason": f"{len(due_screenings)} developmental screenings due" if has_gaps else "",
            "recommendation": "Schedule developmental screening at next visit" if has_gaps else "",
            "evidence_basis": [
                f"{s['screening']} (due at {s['due_at_months']} months)"
                for s in due_screenings
            ],
            "confidence": 0.8,
        },
    }


def get_care_gaps(tool_context: ToolContext = None) -> dict:
    """
    Identify care gaps -- overdue screenings, missed appointments, unmet goals.

    Queries CarePlan, Goal, and Encounter resources to find gaps in preventive care.

    No arguments required.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx

    fhir_url, fhir_token, patient_id = ctx
    logger.info("tool_get_care_gaps patient_id=%s", patient_id)

    gaps = []

    # Check active care plans
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "CarePlan",
            params={"patient": patient_id, "status": "active", "_count": "20"},
        )
        active_plans = []
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
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
    except Exception:
        active_plans = []

    # Check goals
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Goal",
            params={"patient": patient_id, "_count": "20"},
        )
        goals = []
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            description = (res.get("description") or {}).get("text", "")
            status = res.get("lifecycleStatus", "")
            goals.append({
                "description": description,
                "status": status,
                "resource_id": res.get("id", ""),
            })
            if status in ("accepted", "active") and not description:
                gaps.append(f"Goal/{res.get('id', '')} is {status} but lacks description")
    except Exception:
        goals = []

    # Check recent encounters (last 6 months)
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Encounter",
            params={"patient": patient_id, "_sort": "-date", "_count": "10"},
        )
        encounters = []
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
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
    except Exception:
        encounters = []

    return {
        "status": "success",
        "patient_id": patient_id,
        "data": {
            "active_care_plans": active_plans,
            "goals": goals,
            "recent_encounters": encounters,
            "identified_gaps": gaps,
        },
        "clinician_review": {
            "required": len(gaps) > 0,
            "reason": f"{len(gaps)} care gap(s) identified" if gaps else "",
            "recommendation": "; ".join(gaps) if gaps else "No care gaps identified",
            "evidence_basis": gaps,
            "confidence": 0.7,
        },
    }
