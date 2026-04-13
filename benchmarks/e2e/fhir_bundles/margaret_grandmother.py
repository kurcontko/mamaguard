"""
Margaret Washington — 68-year-old grandmother as primary caregiver.

Diverse patient (a): tests that the pediatric agent handles a non-child
gracefully. Margaret is bringing in her 3-year-old grandchild for care;
she is not herself a pediatric patient. When queried about pediatric
wellness for Margaret herself, the agent should recognize this is an
adult and respond appropriately (not error, not treat as a child).

Clinical profile:
  - 68yo female, English-speaking
  - Primary caregiver for 3yo grandchild
  - Chronic conditions: controlled Type 2 DM, osteoarthritis
  - BP slightly elevated but stable (134-138/84-88)
  - HbA1c 6.9 (diabetes range but stable)
  - On metformin + lisinopril
  - Active Medicare coverage
  - No pregnancy history relevant to current care
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

PATIENT_ID = "bench-margaret-013"

_resources = [
    patient(PATIENT_ID, "Margaret", "Washington", "1958-02-14",
            gender="female", language="English"),

    # Chronic conditions — controlled
    condition("bench-mw-dm2", PATIENT_ID, "44054006",
              "Type 2 diabetes mellitus",
              clinical_status="active", onset="2015-03-01"),
    condition("bench-mw-oa", PATIENT_ID, "396275006", "Osteoarthritis",
              clinical_status="active", onset="2019-08-01"),

    # BP — slightly elevated but stable
    bp_observation("bench-mw-bp1", PATIENT_ID, "2026-01-15", 134, 84),
    bp_observation("bench-mw-bp2", PATIENT_ID, "2026-02-15", 136, 86),
    bp_observation("bench-mw-bp3", PATIENT_ID, "2026-03-15", 138, 88),

    # HbA1c — diabetes range but stable
    hba1c_observation("bench-mw-a1c1", PATIENT_ID, "2025-09-15", 7.0),
    hba1c_observation("bench-mw-a1c2", PATIENT_ID, "2026-01-15", 6.9),

    # Medications
    medication_request("bench-mw-med1", PATIENT_ID, "Metformin 1000mg",
                       "Take 1 tablet twice daily with meals", "2020-01-15"),
    medication_request("bench-mw-med2", PATIENT_ID, "Lisinopril 10mg",
                       "Take 1 tablet daily", "2021-06-01"),

    # Active Medicare
    coverage("bench-mw-cov1", PATIENT_ID, "Medicare Part A+B",
             status="active", start="2023-02-01"),
]

BUNDLE = transaction_bundle(_resources)
