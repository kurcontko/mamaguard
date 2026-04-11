"""
Maria Santos — high-risk maternal patient.

Clinical profile:
  - 38yo female, French-speaking
  - Stage 2 hypertension (worsening over 12 months, recent 170/110)
  - Type 2 diabetes (HbA1c rising 6.8 -> 7.9)
  - 6 pregnancies: 1 live birth + 5 losses
  - Uninsured
  - On hydrochlorothiazide (HTN) + metformin (DM2)
  - Active SDOH: stress, housing problem
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    glucose_observation,
    hba1c_observation,
    medication_request,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-maria-001"

_p = patient(
    PATIENT_ID, "Maria", "Santos", "1988-03-15",
    gender="female", language="French",
)

_resources = [
    _p,

    # Chronic conditions
    condition("bench-m-htn", PATIENT_ID, "59621000", "Essential hypertension",
              clinical_status="active", onset="2018-05-01"),
    condition("bench-m-dm2", PATIENT_ID, "44054006", "Type 2 diabetes mellitus",
              clinical_status="active", onset="2020-02-01"),
    condition("bench-m-neuro", PATIENT_ID, "230572002", "Diabetic peripheral neuropathy",
              clinical_status="active", onset="2023-07-01"),

    # Pregnancy history — 1 live birth + 5 losses
    condition("bench-m-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="resolved", onset="2015-03-01", abatement="2015-12-01"),
    condition("bench-m-preg2", PATIENT_ID, "35999006", "Blighted ovum",
              clinical_status="resolved", onset="2012-06-01"),
    condition("bench-m-preg3", PATIENT_ID, "35999006", "Blighted ovum",
              clinical_status="resolved", onset="2014-01-01"),
    condition("bench-m-preg4", PATIENT_ID, "19169002", "Miscarriage",
              clinical_status="resolved", onset="2013-04-01"),
    condition("bench-m-preg5", PATIENT_ID, "19169002", "Miscarriage",
              clinical_status="resolved", onset="2016-08-01"),
    condition("bench-m-preg6", PATIENT_ID, "156073000", "Fetal complication",
              clinical_status="resolved", onset="2017-11-01"),

    # SDOH conditions
    condition("bench-m-sdoh1", PATIENT_ID, "73595000", "Stress",
              clinical_status="active", onset="2024-01-01"),
    condition("bench-m-sdoh2", PATIENT_ID, "105531004", "Housing problem",
              clinical_status="active", onset="2024-06-01"),

    # Blood pressure trend — worsening
    bp_observation("bench-m-bp1", PATIENT_ID, "2025-01-10", 142, 88),
    bp_observation("bench-m-bp2", PATIENT_ID, "2025-03-20", 148, 94),
    bp_observation("bench-m-bp3", PATIENT_ID, "2025-06-15", 155, 98),
    bp_observation("bench-m-bp4", PATIENT_ID, "2025-09-01", 162, 104),
    bp_observation("bench-m-bp5", PATIENT_ID, "2025-11-20", 170, 110),
    bp_observation("bench-m-bp6", PATIENT_ID, "2026-01-16", 168, 108),

    # HbA1c trend — worsening
    hba1c_observation("bench-m-a1c1", PATIENT_ID, "2025-03-15", 6.8),
    hba1c_observation("bench-m-a1c2", PATIENT_ID, "2025-09-15", 7.4),
    hba1c_observation("bench-m-a1c3", PATIENT_ID, "2026-01-10", 7.9),

    # Glucose fingersticks
    glucose_observation("bench-m-glu1", PATIENT_ID, "2025-06-10", 145),
    glucose_observation("bench-m-glu2", PATIENT_ID, "2025-12-10", 162),

    # Medications
    medication_request("bench-m-med1", PATIENT_ID, "Hydrochlorothiazide 25mg",
                       "Take 1 tablet daily", "2024-06-01"),
    medication_request("bench-m-med2", PATIENT_ID, "Metformin 500mg",
                       "Take 1 tablet twice daily with meals", "2024-09-01"),
    medication_request("bench-m-med3", PATIENT_ID, "Prenatal vitamins",
                       "Take 1 tablet daily", "2025-01-15"),

    # No Coverage resource — uninsured
]

BUNDLE = transaction_bundle(_resources)
