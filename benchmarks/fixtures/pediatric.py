"""
Pediatric FHIR fixtures — synthetic data for benchmark scenarios.

Scenarios:
  1. baby_santos    — Maria's newborn, needs catch-up immunizations
  2. toddler_jones  — 18-month-old, up to date, needs autism screen
  3. child_smith    — 5-year-old, multiple overdue vaccines + missed screenings
"""


def _patient(patient_id: str, given: str, family: str, birth_date: str, gender: str = "male") -> dict:
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [{"use": "official", "given": [given], "family": family}],
        "birthDate": birth_date,
        "gender": gender,
    }


def _immunization(imm_id: str, vaccine: str, date: str, status: str = "completed") -> dict:
    return {
        "resource": {
            "resourceType": "Immunization",
            "id": imm_id,
            "status": status,
            "vaccineCode": {"text": vaccine},
            "occurrenceDateTime": date,
        }
    }


def _survey_observation(obs_id: str, name: str, date: str) -> dict:
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "category": [{"coding": [{"code": "survey"}]}],
            "code": {"text": name},
            "effectiveDateTime": date,
        }
    }


# =============================================================================
# Scenario 1: Baby Santos — 2-month-old newborn, partial immunizations
# =============================================================================

BABY_SANTOS_ID = "baby-santos-001"

# Born 2026-02-09 → ~2 months old as of 2026-04-09
BABY_SANTOS_PATIENT = _patient(BABY_SANTOS_ID, "Lucas", "Santos", "2026-02-09", "male")

BABY_SANTOS_IMMUNIZATIONS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _immunization("imm-bs1", "HepB", "2026-02-09"),  # Birth dose only
    ],
}

BABY_SANTOS_SCREENINGS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _survey_observation("scr-bs1", "Newborn metabolic screen", "2026-02-10"),
        _survey_observation("scr-bs2", "Hearing screen", "2026-02-10"),
    ],
}

# Expected gaps at 2 months: HepB dose 2, DTaP 1, IPV 1, Hib 1, PCV13 1, RV 1
# Expected screening gaps: developmental surveillance at 1 and 2 months


# =============================================================================
# Scenario 2: Toddler Jones — 18-month-old, mostly up to date
# =============================================================================

TODDLER_JONES_ID = "toddler-jones-002"

# Born 2024-10-09 → ~18 months old
TODDLER_JONES_PATIENT = _patient(TODDLER_JONES_ID, "Ava", "Jones", "2024-10-09", "female")

TODDLER_JONES_IMMUNIZATIONS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _immunization("imm-tj1", "HepB", "2024-10-09"),
        _immunization("imm-tj2", "HepB", "2024-11-09"),
        _immunization("imm-tj3", "DTaP", "2024-12-09"),
        _immunization("imm-tj4", "IPV", "2024-12-09"),
        _immunization("imm-tj5", "Hib", "2024-12-09"),
        _immunization("imm-tj6", "PCV13", "2024-12-09"),
        _immunization("imm-tj7", "RV", "2024-12-09"),
        _immunization("imm-tj8", "DTaP", "2025-02-09"),
        _immunization("imm-tj9", "IPV", "2025-02-09"),
        _immunization("imm-tj10", "Hib", "2025-02-09"),
        _immunization("imm-tj11", "PCV13", "2025-02-09"),
        _immunization("imm-tj12", "RV", "2025-02-09"),
        _immunization("imm-tj13", "HepB", "2025-04-09"),
        _immunization("imm-tj14", "DTaP", "2025-04-09"),
        _immunization("imm-tj15", "PCV13", "2025-04-09"),
        _immunization("imm-tj16", "Influenza", "2025-04-09"),
        _immunization("imm-tj17", "MMR", "2025-10-09"),
        _immunization("imm-tj18", "Varicella", "2025-10-09"),
        _immunization("imm-tj19", "HepA", "2025-10-09"),
        _immunization("imm-tj20", "PCV13", "2025-10-09"),
    ],
}

TODDLER_JONES_SCREENINGS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _survey_observation("scr-tj1", "Newborn metabolic screen", "2024-10-10"),
        _survey_observation("scr-tj2", "Hearing screen", "2024-10-10"),
        _survey_observation("scr-tj3", "Developmental surveillance", "2024-11-09"),
        _survey_observation("scr-tj4", "Developmental surveillance", "2024-12-09"),
        _survey_observation("scr-tj5", "Developmental surveillance", "2025-02-09"),
        _survey_observation("scr-tj6", "Developmental surveillance", "2025-04-09"),
        _survey_observation("scr-tj7", "Developmental screening (ASQ/PEDS)", "2025-07-09"),
        _survey_observation("scr-tj8", "Developmental surveillance", "2025-10-09"),
        # Missing: Autism screening (M-CHAT) at 18 months
    ],
}


# =============================================================================
# Scenario 3: Child Smith — 5-year-old with significant gaps
# =============================================================================

CHILD_SMITH_ID = "child-smith-003"

# Born 2021-04-09 → 60 months old
CHILD_SMITH_PATIENT = _patient(CHILD_SMITH_ID, "Ethan", "Smith", "2021-04-09", "male")

CHILD_SMITH_IMMUNIZATIONS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _immunization("imm-cs1", "HepB", "2021-04-09"),
        _immunization("imm-cs2", "HepB", "2021-05-09"),
        _immunization("imm-cs3", "DTaP", "2021-06-09"),
        _immunization("imm-cs4", "IPV", "2021-06-09"),
        # Many missing after 2-month visit — family lost to follow-up
    ],
}

CHILD_SMITH_SCREENINGS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _survey_observation("scr-cs1", "Newborn metabolic screen", "2021-04-10"),
        _survey_observation("scr-cs2", "Hearing screen", "2021-04-10"),
        # All developmental screenings missed
    ],
}

# Expected: massive immunization gaps + all developmental screenings overdue
