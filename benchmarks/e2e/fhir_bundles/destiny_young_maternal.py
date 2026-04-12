"""
Destiny Williams — 19-year-old first-time pregnant, SDOH concerns.

Clinical profile:
  - 19yo female, English-speaking
  - First pregnancy (active, onset 2025-12-15)
  - BP normal (116-120/72-78)
  - HbA1c normal (5.0)
  - No chronic medical conditions
  - SDOH: stress, social isolation
  - Medicaid coverage
  - On Prenatal vitamins + Sertraline (anxiety/depression)
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

PATIENT_ID = "bench-destiny-007"

_resources = [
    patient(PATIENT_ID, "Destiny", "Williams", "2006-09-14",
            gender="female", language="English"),

    # First pregnancy — active
    condition("bench-d-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2025-12-15"),

    # SDOH conditions
    condition("bench-d-sdoh1", PATIENT_ID, "73595000", "Stress",
              clinical_status="active", onset="2025-10-01"),
    condition("bench-d-sdoh2", PATIENT_ID, None, "Social isolation",
              clinical_status="active", onset="2025-11-01"),

    # Normal BP
    bp_observation("bench-d-bp1", PATIENT_ID, "2026-01-10", 116, 74),
    bp_observation("bench-d-bp2", PATIENT_ID, "2026-02-15", 118, 76),
    bp_observation("bench-d-bp3", PATIENT_ID, "2026-03-10", 120, 78),

    # Normal HbA1c
    hba1c_observation("bench-d-a1c1", PATIENT_ID, "2026-01-10", 5.0),

    # Medications
    medication_request("bench-d-med1", PATIENT_ID, "Prenatal vitamins",
                       "Take 1 tablet daily", "2025-12-20"),
    medication_request("bench-d-med2", PATIENT_ID, "Sertraline 50mg",
                       "Take 1 tablet daily", "2025-10-15"),

    # Medicaid
    coverage("bench-d-cov1", PATIENT_ID, "Medicaid",
             status="active", start="2025-09-01"),
]

BUNDLE = transaction_bundle(_resources)
