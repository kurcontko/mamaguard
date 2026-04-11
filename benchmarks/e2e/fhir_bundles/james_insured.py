"""
James Wilson — fully insured, English-speaking, no SDOH concerns.

Clinical profile:
  - 40yo male, English-speaking
  - Employer-sponsored PPO
  - Only seasonal allergies
  - No SDOH conditions
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    condition,
    coverage,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-james-004"

_resources = [
    patient(PATIENT_ID, "James", "Wilson", "1985-08-20",
            gender="male", language="English"),

    condition("bench-j-allergy", PATIENT_ID, "21719001",
              "Allergic rhinitis due to pollen", clinical_status="active"),

    coverage("bench-j-cov1", PATIENT_ID, "Employer-sponsored PPO",
             status="active", start="2025-01-01"),
]

BUNDLE = transaction_bundle(_resources)
