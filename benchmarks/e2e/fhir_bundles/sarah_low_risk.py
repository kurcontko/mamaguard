"""
Sarah Johnson — low-risk maternal patient.

Clinical profile:
  - 33yo female, English-speaking
  - Normotensive (BP stable around 118/76)
  - Euglycemic (HbA1c 5.1-5.2)
  - One prior healthy pregnancy (2023)
  - Employer-sponsored insurance
  - No chronic conditions
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    coverage,
    hba1c_observation,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-sarah-002"

_resources = [
    patient(PATIENT_ID, "Sarah", "Johnson", "1992-07-22",
            gender="female", language="English"),

    # One resolved healthy pregnancy
    condition("bench-s-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="resolved", onset="2023-01-15", abatement="2023-09-20"),

    # Normal BP
    bp_observation("bench-s-bp1", PATIENT_ID, "2025-06-15", 118, 76),
    bp_observation("bench-s-bp2", PATIENT_ID, "2025-09-10", 120, 78),
    bp_observation("bench-s-bp3", PATIENT_ID, "2025-12-05", 116, 74),
    bp_observation("bench-s-bp4", PATIENT_ID, "2026-02-15", 122, 80),

    # Normal HbA1c
    hba1c_observation("bench-s-a1c1", PATIENT_ID, "2025-06-15", 5.2),
    hba1c_observation("bench-s-a1c2", PATIENT_ID, "2025-12-15", 5.1),

    # Insurance
    coverage("bench-s-cov1", PATIENT_ID, "Employer-sponsored PPO",
             status="active", start="2025-01-01"),
]

BUNDLE = transaction_bundle(_resources)
