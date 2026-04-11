"""
Maternal FHIR fixtures — synthetic data for benchmark scenarios.

Scenarios:
  1. maria_high_risk   — Stage 2 HTN, diabetes, recurrent pregnancy loss
  2. sarah_low_risk    — Normal BP, normal glucose, one healthy pregnancy
  3. elena_preeclampsia — Acute preeclampsia with rapid BP deterioration
"""


# -- Helpers ------------------------------------------------------------------

def _bp_observation(obs_id: str, date: str, systolic: float, diastolic: float) -> dict:
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "code": {
                "coding": [{"system": "http://loinc.org", "code": "55284-4", "display": "Blood pressure panel"}],
                "text": "Blood pressure panel",
            },
            "effectiveDateTime": date,
            "component": [
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic"}]},
                    "valueQuantity": {"value": systolic, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic"}]},
                    "valueQuantity": {"value": diastolic, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                },
            ],
        }
    }


def _hba1c_observation(obs_id: str, date: str, value: float) -> dict:
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "code": {
                "coding": [{"system": "http://loinc.org", "code": "4548-4", "display": "Hemoglobin A1c"}],
                "text": "HbA1c",
            },
            "effectiveDateTime": date,
            "valueQuantity": {"value": value, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"},
        }
    }


def _glucose_observation(obs_id: str, date: str, value: float) -> dict:
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "code": {
                "coding": [{"system": "http://loinc.org", "code": "2339-0", "display": "Glucose [Mass/volume] in Blood"}],
                "text": "Glucose",
            },
            "effectiveDateTime": date,
            "valueQuantity": {"value": value, "unit": "mg/dL", "system": "http://unitsofmeasure.org", "code": "mg/dL"},
        }
    }


def _pregnancy_condition(cond_id: str, snomed: str, text: str, status: str, onset: str, abatement: str | None = None) -> dict:
    res = {
        "resourceType": "Condition",
        "id": cond_id,
        "code": {
            "coding": [{"system": "http://snomed.info/sct", "code": snomed, "display": text}],
            "text": text,
        },
        "clinicalStatus": {"coding": [{"code": status}]},
        "onsetDateTime": onset,
    }
    if abatement:
        res["abatementDateTime"] = abatement
    return {"resource": res}


def _medication_request(med_id: str, name: str, dosage: str, authored: str) -> dict:
    return {
        "resource": {
            "resourceType": "MedicationRequest",
            "id": med_id,
            "status": "active",
            "medicationCodeableConcept": {"text": name},
            "dosageInstruction": [{"text": dosage}],
            "authoredOn": authored,
        }
    }


def _patient(patient_id: str, given: str, family: str, birth_date: str,
             gender: str = "female", language: str | None = None) -> dict:
    patient = {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [{"use": "official", "given": [given], "family": family}],
        "birthDate": birth_date,
        "gender": gender,
    }
    if language:
        patient["communication"] = [
            {"language": {"text": language, "coding": [{"display": language}]}}
        ]
    return patient


# =============================================================================
# Scenario 1: Maria — High-risk maternal patient
# =============================================================================

MARIA_PATIENT_ID = "maria-bench-001"

MARIA_PATIENT = _patient(
    MARIA_PATIENT_ID, "Maria", "Santos", "1988-03-15",
    language="French",
)

MARIA_BP_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _bp_observation("bp-m1", "2025-01-10", 142, 88),
        _bp_observation("bp-m2", "2025-03-20", 148, 94),
        _bp_observation("bp-m3", "2025-06-15", 155, 98),
        _bp_observation("bp-m4", "2025-09-01", 162, 104),
        _bp_observation("bp-m5", "2025-11-20", 170, 110),
        _bp_observation("bp-m6", "2026-01-16", 168, 108),
    ],
}

MARIA_HBA1C_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _hba1c_observation("hba1c-m1", "2025-03-15", 6.8),
        _hba1c_observation("hba1c-m2", "2025-09-15", 7.4),
        _hba1c_observation("hba1c-m3", "2026-01-10", 7.9),
    ],
}

MARIA_GLUCOSE_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _glucose_observation("glu-m1", "2025-06-10", 145),
        _glucose_observation("glu-m2", "2025-12-10", 162),
    ],
}

MARIA_PREGNANCY_BUNDLES = {
    "72892002": {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            _pregnancy_condition("preg-m1", "72892002", "Normal pregnancy", "resolved", "2015-03-01", "2015-12-01"),
        ],
    },
    "35999006": {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            _pregnancy_condition("preg-m2", "35999006", "Blighted ovum", "resolved", "2012-06-01"),
            _pregnancy_condition("preg-m3", "35999006", "Blighted ovum", "resolved", "2014-01-01"),
        ],
    },
    "19169002": {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            _pregnancy_condition("preg-m4", "19169002", "Miscarriage", "resolved", "2013-04-01"),
            _pregnancy_condition("preg-m5", "19169002", "Miscarriage", "resolved", "2016-08-01"),
        ],
    },
    "156073000": {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            _pregnancy_condition("preg-m6", "156073000", "Fetal complication", "resolved", "2017-11-01"),
        ],
    },
}

MARIA_MEDICATIONS_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _medication_request("med-m1", "Hydrochlorothiazide 25mg", "Take 1 tablet daily", "2024-06-01"),
        _medication_request("med-m2", "Metformin 500mg", "Take 1 tablet twice daily with meals", "2024-09-01"),
        _medication_request("med-m3", "Prenatal vitamins", "Take 1 tablet daily", "2025-01-15"),
    ],
}

MARIA_CONDITIONS_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        {"resource": {
            "resourceType": "Condition", "id": "cond-m1",
            "code": {"text": "Essential hypertension", "coding": [{"display": "Essential hypertension"}]},
            "clinicalStatus": {"coding": [{"code": "active"}]},
            "onsetDateTime": "2018-05-01",
        }},
        {"resource": {
            "resourceType": "Condition", "id": "cond-m2",
            "code": {"text": "Type 2 diabetes mellitus", "coding": [{"display": "Type 2 diabetes mellitus"}]},
            "clinicalStatus": {"coding": [{"code": "active"}]},
            "onsetDateTime": "2020-02-01",
        }},
        {"resource": {
            "resourceType": "Condition", "id": "cond-m3",
            "code": {"text": "Diabetic peripheral neuropathy", "coding": [{"display": "Diabetic peripheral neuropathy"}]},
            "clinicalStatus": {"coding": [{"code": "active"}]},
            "onsetDateTime": "2023-07-01",
        }},
    ],
}

MARIA_VITALS_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _bp_observation("vital-m1", "2026-01-16", 168, 108),
    ],
}


# =============================================================================
# Scenario 2: Sarah — Low-risk maternal patient
# =============================================================================

SARAH_PATIENT_ID = "sarah-bench-002"

SARAH_PATIENT = _patient(
    SARAH_PATIENT_ID, "Sarah", "Johnson", "1992-07-22",
    language="English",
)

SARAH_BP_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _bp_observation("bp-s1", "2025-06-15", 118, 76),
        _bp_observation("bp-s2", "2025-09-10", 120, 78),
        _bp_observation("bp-s3", "2025-12-05", 116, 74),
        _bp_observation("bp-s4", "2026-02-15", 122, 80),
    ],
}

SARAH_HBA1C_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _hba1c_observation("hba1c-s1", "2025-06-15", 5.2),
        _hba1c_observation("hba1c-s2", "2025-12-15", 5.1),
    ],
}

SARAH_GLUCOSE_BUNDLE = {"resourceType": "Bundle", "type": "searchset", "entry": []}

SARAH_PREGNANCY_BUNDLES = {
    "72892002": {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            _pregnancy_condition("preg-s1", "72892002", "Normal pregnancy", "resolved", "2023-01-15", "2023-09-20"),
        ],
    },
    "35999006": {"resourceType": "Bundle", "type": "searchset", "entry": []},
    "19169002": {"resourceType": "Bundle", "type": "searchset", "entry": []},
    "156073000": {"resourceType": "Bundle", "type": "searchset", "entry": []},
}


# =============================================================================
# Scenario 3: Elena — Acute preeclampsia (rapid deterioration)
# =============================================================================

ELENA_PATIENT_ID = "elena-bench-003"

ELENA_PATIENT = _patient(
    ELENA_PATIENT_ID, "Elena", "Petrova", "1995-11-03",
    language="Russian",
)

ELENA_BP_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _bp_observation("bp-e1", "2026-01-05", 124, 82),
        _bp_observation("bp-e2", "2026-02-01", 138, 88),
        _bp_observation("bp-e3", "2026-02-15", 156, 102),
        _bp_observation("bp-e4", "2026-03-01", 172, 114),
        _bp_observation("bp-e5", "2026-03-10", 184, 118),
    ],
}

ELENA_HBA1C_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        _hba1c_observation("hba1c-e1", "2026-01-10", 5.0),
    ],
}

ELENA_GLUCOSE_BUNDLE = {"resourceType": "Bundle", "type": "searchset", "entry": []}

ELENA_PREGNANCY_BUNDLES = {
    "72892002": {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            _pregnancy_condition("preg-e1", "72892002", "Normal pregnancy", "active", "2025-09-01"),
        ],
    },
    "35999006": {"resourceType": "Bundle", "type": "searchset", "entry": []},
    "19169002": {"resourceType": "Bundle", "type": "searchset", "entry": []},
    "156073000": {"resourceType": "Bundle", "type": "searchset", "entry": []},
}
