"""
Carol Nguyen — patient with well-controlled chronic conditions.

Diverse patient (c): has multiple chronic conditions (Type 2 DM, HTN,
hypothyroidism) but ALL are well-controlled with medication. BP normal,
HbA1c 5.8 (pre-diabetes range, well-managed), thyroid on levothyroxine.
Active pregnancy. Should get ROUTINE across the board — tests that
agents don't escalate risk for diagnoses that are clinically controlled.

Clinical profile:
  - 33yo female, Vietnamese-speaking
  - Active pregnancy (onset 2025-12-01, ~18 weeks)
  - Type 2 DM — well-controlled (HbA1c 5.8)
  - HTN — well-controlled (BP 118-124/76-80)
  - Hypothyroidism — on levothyroxine
  - On metformin, labetalol, levothyroxine, prenatal vitamins
  - Active employer-sponsored insurance
  - No SDOH concerns
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    coverage,
    hba1c_observation,
    medication_request,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-carol-015"

_resources = [
    patient(PATIENT_ID, "Carol", "Nguyen", "1993-04-22",
            gender="female", language="Vietnamese"),

    # Active pregnancy
    condition("bench-cn-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2025-12-01"),

    # Chronic conditions — all well-controlled
    condition("bench-cn-dm2", PATIENT_ID, "44054006",
              "Type 2 diabetes mellitus",
              clinical_status="active", onset="2020-06-01"),
    condition("bench-cn-htn", PATIENT_ID, "59621000",
              "Essential hypertension",
              clinical_status="active", onset="2021-01-15"),
    condition("bench-cn-thyroid", PATIENT_ID, "40930008",
              "Hypothyroidism",
              clinical_status="active", onset="2019-09-01"),

    # BP — well-controlled, normal range
    bp_observation("bench-cn-bp1", PATIENT_ID, "2026-01-10", 118, 76),
    bp_observation("bench-cn-bp2", PATIENT_ID, "2026-02-10", 120, 78),
    bp_observation("bench-cn-bp3", PATIENT_ID, "2026-03-10", 122, 78),
    bp_observation("bench-cn-bp4", PATIENT_ID, "2026-04-05", 124, 80),

    # HbA1c — well-controlled (pre-diabetes range)
    hba1c_observation("bench-cn-a1c1", PATIENT_ID, "2025-09-15", 5.9),
    hba1c_observation("bench-cn-a1c2", PATIENT_ID, "2026-01-10", 5.8),

    # Medications
    medication_request("bench-cn-med1", PATIENT_ID, "Metformin 500mg",
                       "Take 1 tablet twice daily with meals", "2020-07-01"),
    medication_request("bench-cn-med2", PATIENT_ID, "Labetalol 100mg",
                       "Take 1 tablet twice daily", "2021-02-01"),
    medication_request("bench-cn-med3", PATIENT_ID, "Levothyroxine 75mcg",
                       "Take 1 tablet daily on empty stomach", "2019-10-01"),
    medication_request("bench-cn-med4", PATIENT_ID, "Prenatal vitamins",
                       "Take 1 tablet daily", "2025-12-15"),

    # Active employer-sponsored insurance
    coverage("bench-cn-cov1", PATIENT_ID, "Employer-sponsored PPO",
             status="active", start="2025-01-01"),
]

BUNDLE = transaction_bundle(_resources)
