"""
Grace Park — patient with NO conditions at all.

Clinical edge case (a): tests that the agent returns ROUTINE, not an error,
when a patient has no active conditions, no prior pregnancy loss, no
chronic illness — just a straightforward healthy pregnancy.

Clinical profile:
  - 30yo female, English-speaking
  - First pregnancy (active, onset 2026-01-10)
  - BP normal (116-120/74-78)
  - HbA1c normal (5.0)
  - No conditions whatsoever (no HTN, no diabetes, nothing)
  - Active employer-sponsored insurance
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    coverage,
    hba1c_observation,
    patient,
    transaction_bundle,
    condition,
)

PATIENT_ID = "bench-grace-008"

_resources = [
    patient(PATIENT_ID, "Grace", "Park", "1995-11-20",
            gender="female", language="English"),

    # First pregnancy — active, healthy
    condition("bench-g-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2026-01-10"),

    # Normal BP readings
    bp_observation("bench-g-bp1", PATIENT_ID, "2026-02-10", 116, 74),
    bp_observation("bench-g-bp2", PATIENT_ID, "2026-03-10", 118, 76),
    bp_observation("bench-g-bp3", PATIENT_ID, "2026-04-05", 120, 78),

    # Normal HbA1c
    hba1c_observation("bench-g-a1c1", PATIENT_ID, "2026-02-10", 5.0),

    # Active insurance
    coverage("bench-g-cov1", PATIENT_ID, "Employer-sponsored PPO",
             status="active", start="2025-01-01"),
]

BUNDLE = transaction_bundle(_resources)
