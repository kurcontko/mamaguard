"""
Priya Sharma — gestational diabetes with borderline hypertension.

Clinical profile:
  - 31yo female, Hindi-speaking
  - Active pregnancy (onset 2025-11-01)
  - Gestational diabetes: HbA1c 5.4 → 5.8 → 6.8 (worsening during pregnancy)
  - BP trending upward: 124/80 → 142/92 (Stage 1, elevated)
  - On Glyburide (GDM) + Prenatal vitamins
  - Employer-sponsored PPO insurance
  - No SDOH conditions
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    coverage,
    glucose_observation,
    hba1c_observation,
    medication_request,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-priya-006"

_resources = [
    patient(PATIENT_ID, "Priya", "Sharma", "1994-08-20",
            gender="female", language="Hindi"),

    # Active pregnancy
    condition("bench-p-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2025-11-01"),

    # GDM diagnosed during pregnancy
    condition("bench-p-gdm", PATIENT_ID, "11687002",
              "Gestational diabetes mellitus",
              clinical_status="active", onset="2026-01-15"),

    # BP trend — borderline Stage 1, trending upward
    bp_observation("bench-p-bp1", PATIENT_ID, "2025-12-01", 124, 80),
    bp_observation("bench-p-bp2", PATIENT_ID, "2026-01-15", 130, 84),
    bp_observation("bench-p-bp3", PATIENT_ID, "2026-02-15", 136, 88),
    bp_observation("bench-p-bp4", PATIENT_ID, "2026-03-15", 142, 92),

    # HbA1c — worsening during pregnancy (GDM pattern)
    hba1c_observation("bench-p-a1c1", PATIENT_ID, "2025-12-01", 5.4),
    hba1c_observation("bench-p-a1c2", PATIENT_ID, "2026-01-20", 5.8),
    hba1c_observation("bench-p-a1c3", PATIENT_ID, "2026-03-10", 6.8),

    # Glucose fingersticks
    glucose_observation("bench-p-glu1", PATIENT_ID, "2026-01-10", 128),
    glucose_observation("bench-p-glu2", PATIENT_ID, "2026-03-10", 142),

    # Medications
    medication_request("bench-p-med1", PATIENT_ID, "Glyburide 5mg",
                       "Take 1 tablet twice daily", "2026-01-20"),
    medication_request("bench-p-med2", PATIENT_ID, "Prenatal vitamins",
                       "Take 1 tablet daily", "2025-11-15"),

    # Insurance
    coverage("bench-p-cov1", PATIENT_ID, "Employer-sponsored PPO",
             status="active", start="2025-01-01"),
]

BUNDLE = transaction_bundle(_resources)
