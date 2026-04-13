"""
Lisa Brown — patient with expired insurance coverage.

Clinical edge case (d): tests that the agent correctly identifies
coverage.period.end in the past as lapsed/expired insurance and flags it.
The patient is otherwise low-risk clinically.

Clinical profile:
  - 32yo female, English-speaking
  - Active pregnancy (onset 2025-12-01)
  - BP normal (116-120/74-78)
  - HbA1c normal (5.1)
  - No chronic conditions
  - Insurance EXPIRED: period.end = 2025-12-31 (lapsed ~3.5 months ago)
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    coverage,
    hba1c_observation,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-lisa-011"

_resources = [
    patient(PATIENT_ID, "Lisa", "Brown", "1993-04-12",
            gender="female", language="English"),

    # Active pregnancy
    condition("bench-l-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2025-12-01"),

    # Normal BP
    bp_observation("bench-l-bp1", PATIENT_ID, "2026-01-15", 116, 74),
    bp_observation("bench-l-bp2", PATIENT_ID, "2026-02-15", 118, 76),
    bp_observation("bench-l-bp3", PATIENT_ID, "2026-03-15", 120, 78),

    # Normal HbA1c
    hba1c_observation("bench-l-a1c1", PATIENT_ID, "2026-01-15", 5.1),

    # EXPIRED insurance — period.end in the past
    coverage("bench-l-cov1", PATIENT_ID, "Employer-sponsored PPO",
             status="active", start="2025-01-01", end="2025-12-31"),
]

BUNDLE = transaction_bundle(_resources)
