"""
Rosa Martinez — postpartum patient >6 months out.

Clinical edge case (e): tests that the agent correctly deprioritizes
pregnancy-specific risks for a patient whose pregnancy ended >6 months ago.
Should focus on general wellness rather than obstetric risk escalation.

Clinical profile:
  - 34yo female, Spanish-speaking
  - Resolved pregnancy (onset 2024-10-01, abatement 2025-06-15) — ~10 months postpartum
  - BP normal (120-124/78-82)
  - HbA1c normal (5.4)
  - One resolved mild gestational HTN (now resolved)
  - No active conditions
  - Active Medicaid coverage
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    coverage,
    hba1c_observation,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-rosa-012"

_resources = [
    patient(PATIENT_ID, "Rosa", "Martinez", "1991-12-03",
            gender="female", language="Spanish"),

    # Resolved pregnancy — delivered 2025-06-15 (~10 months ago)
    condition("bench-r-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="resolved", onset="2024-10-01", abatement="2025-06-15"),

    # Resolved gestational hypertension — resolved with pregnancy
    condition("bench-r-ghtn1", PATIENT_ID, "48194001",
              "Gestational hypertension",
              clinical_status="resolved", onset="2025-03-01", abatement="2025-06-15"),

    # Current BP normal (postpartum)
    bp_observation("bench-r-bp1", PATIENT_ID, "2026-01-10", 120, 78),
    bp_observation("bench-r-bp2", PATIENT_ID, "2026-02-10", 122, 80),
    bp_observation("bench-r-bp3", PATIENT_ID, "2026-03-10", 124, 82),

    # Normal HbA1c
    hba1c_observation("bench-r-a1c1", PATIENT_ID, "2026-01-10", 5.4),

    # Active Medicaid
    coverage("bench-r-cov1", PATIENT_ID, "Medicaid",
             status="active", start="2025-01-01", end="2026-12-31"),
]

BUNDLE = transaction_bundle(_resources)
