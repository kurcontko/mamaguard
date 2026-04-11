"""
SDOH FHIR fixtures — social determinants of health scenarios.

Scenarios:
  1. maria_sdoh      — French-speaking, uninsured gap, stress condition
  2. james_insured   — English-speaking, fully insured, no SDOH conditions
  3. fatima_complex  — Arabic-speaking, unemployed, food insecurity, Medicaid
"""


def _patient(patient_id: str, given: str, family: str, birth_date: str,
             language: str | None = None) -> dict:
    patient = {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [{"use": "official", "given": [given], "family": family}],
        "birthDate": birth_date,
        "gender": "female",
    }
    if language:
        patient["communication"] = [
            {"language": {"text": language, "coding": [{"display": language}]}}
        ]
    return patient


def _condition(cond_id: str, code: str, text: str, status: str = "active") -> dict:
    return {
        "resource": {
            "resourceType": "Condition",
            "id": cond_id,
            "code": {
                "text": text,
                "coding": [{"system": "http://snomed.info/sct", "code": code, "display": text}],
            },
            "clinicalStatus": {"coding": [{"code": status}]},
        }
    }


def _coverage(cov_id: str, cov_type: str, status: str,
              start: str, end: str | None = None) -> dict:
    period = {"start": start}
    if end:
        period["end"] = end
    return {
        "resource": {
            "resourceType": "Coverage",
            "id": cov_id,
            "status": status,
            "type": {"text": cov_type},
            "period": period,
        }
    }


# =============================================================================
# Scenario 1: Maria — Language barrier + coverage gap + SDOH conditions
# =============================================================================

MARIA_SDOH_PATIENT_ID = "maria-sdoh-001"
MARIA_SDOH_PATIENT = _patient(MARIA_SDOH_PATIENT_ID, "Maria", "Santos", "1988-03-15", language="French")

MARIA_SDOH_CONDITIONS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _condition("sdoh-m1", "73595000", "Stress"),
        _condition("sdoh-m2", "105531004", "Housing problem"),
        {"resource": {
            "resourceType": "Condition", "id": "cond-m-htn",
            "code": {"text": "Essential hypertension", "coding": [{"display": "Essential hypertension"}]},
            "clinicalStatus": {"coding": [{"code": "active"}]},
        }},
    ],
}

MARIA_SDOH_COVERAGE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [],  # No coverage — uninsured
}


# =============================================================================
# Scenario 2: James — Fully insured, no SDOH risk factors
# =============================================================================

JAMES_SDOH_PATIENT_ID = "james-sdoh-002"
JAMES_SDOH_PATIENT = _patient(JAMES_SDOH_PATIENT_ID, "James", "Wilson", "1985-08-20", language="English")

JAMES_SDOH_CONDITIONS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        {"resource": {
            "resourceType": "Condition", "id": "cond-j1",
            "code": {"text": "Seasonal allergies", "coding": [{"display": "Seasonal allergies"}]},
            "clinicalStatus": {"coding": [{"code": "active"}]},
        }},
    ],
}

JAMES_SDOH_COVERAGE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _coverage("cov-j1", "Employer-sponsored PPO", "active", "2025-01-01"),
    ],
}


# =============================================================================
# Scenario 3: Fatima — Complex SDOH (language + unemployment + food insecurity)
# =============================================================================

FATIMA_SDOH_PATIENT_ID = "fatima-sdoh-003"
FATIMA_SDOH_PATIENT = _patient(FATIMA_SDOH_PATIENT_ID, "Fatima", "Al-Hassan", "1990-01-12", language="Arabic")

FATIMA_SDOH_CONDITIONS = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _condition("sdoh-f1", "160904001", "Unemployed"),
        _condition("sdoh-f2", "73595000", "Stress"),
        {"resource": {
            "resourceType": "Condition", "id": "sdoh-f3",
            "code": {
                "text": "Food insecurity",
                "coding": [{"display": "Food insecurity"}],
            },
            "clinicalStatus": {"coding": [{"code": "active"}]},
        }},
    ],
}

FATIMA_SDOH_COVERAGE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _coverage("cov-f1", "Medicaid", "active", "2025-06-01", "2026-05-31"),
    ],
}
