"""
Aisha Johnson — patient with ONLY SDOH issues, no medical risk.

Clinical edge case (b): tests that SDOH-only issues produce MODERATE risk
(from SDOH domain), not URGENT. The agent should not escalate risk when
there are no clinical/medical concerns.

Clinical profile:
  - 28yo female, English-speaking
  - Active pregnancy (onset 2025-11-01)
  - BP normal (118-122/76-80)
  - HbA1c normal (4.9)
  - Zero medical conditions — no HTN, no diabetes, no complications
  - SDOH: unemployed, food insecurity, housing problem
  - Medicaid coverage
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    coverage,
    hba1c_observation,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-aisha-009"

_resources = [
    patient(PATIENT_ID, "Aisha", "Johnson", "1997-08-05",
            gender="female", language="English"),

    # Active pregnancy — uncomplicated
    condition("bench-a-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2025-11-01"),

    # SDOH conditions only (no medical conditions)
    condition("bench-a-sdoh1", PATIENT_ID, "160904001", "Unemployed",
              clinical_status="active", onset="2025-06-01"),
    condition("bench-a-sdoh2", PATIENT_ID, None, "Food insecurity",
              clinical_status="active", onset="2025-07-01"),
    condition("bench-a-sdoh3", PATIENT_ID, "105531004", "Housing problem",
              clinical_status="active", onset="2025-08-01"),

    # Normal BP
    bp_observation("bench-a-bp1", PATIENT_ID, "2026-01-15", 118, 76),
    bp_observation("bench-a-bp2", PATIENT_ID, "2026-02-15", 120, 78),
    bp_observation("bench-a-bp3", PATIENT_ID, "2026-03-15", 122, 80),

    # Normal HbA1c
    hba1c_observation("bench-a-a1c1", PATIENT_ID, "2026-01-15", 4.9),

    # Medicaid
    coverage("bench-a-cov1", PATIENT_ID, "Medicaid",
             status="active", start="2025-05-01", end="2026-04-30"),
]

BUNDLE = transaction_bundle(_resources)
