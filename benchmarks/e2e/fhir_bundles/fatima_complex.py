"""
Fatima Al-Hassan — complex SDOH profile.

Clinical profile:
  - 36yo female, Arabic-speaking
  - Unemployed, food insecurity, elevated stress
  - Medicaid coverage (active but limited-duration)
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    condition,
    coverage,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-fatima-005"

_resources = [
    patient(PATIENT_ID, "Fatima", "Al-Hassan", "1990-01-12",
            gender="female", language="Arabic"),

    # SDOH conditions
    condition("bench-f-sdoh1", PATIENT_ID, "160904001", "Unemployed",
              clinical_status="active"),
    condition("bench-f-sdoh2", PATIENT_ID, "73595000", "Stress",
              clinical_status="active"),
    condition("bench-f-sdoh3", PATIENT_ID, None, "Food insecurity",
              clinical_status="active"),

    # Medicaid
    coverage("bench-f-cov1", PATIENT_ID, "Medicaid",
             status="active", start="2025-06-01", end="2026-05-31"),
]

BUNDLE = transaction_bundle(_resources)
