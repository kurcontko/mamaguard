"""
Jaylen Carter — 16-year-old with teen pregnancy.

Diverse patient (b): high-risk maternal due to age (16yo), plus SDOH
concerns: uninsured, school disruption, social isolation. Tests that
the agent correctly identifies adolescent pregnancy as elevated risk
and flags multiple SDOH domains without over-medicalizing.

Clinical profile:
  - 16yo female, English-speaking
  - First pregnancy (active, onset 2026-01-20, ~12 weeks)
  - BP normal (112-118/70-74)
  - HbA1c normal (5.1)
  - No chronic medical conditions
  - SDOH: social isolation, educational disruption
  - No insurance coverage (uninsured)
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    hba1c_observation,
    medication_request,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-jaylen-014"

_resources = [
    patient(PATIENT_ID, "Jaylen", "Carter", "2009-11-03",
            gender="female", language="English"),

    # First pregnancy — active
    condition("bench-jc-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2026-01-20"),

    # SDOH conditions
    condition("bench-jc-sdoh1", PATIENT_ID, None, "Social isolation",
              clinical_status="active", onset="2026-02-01"),
    condition("bench-jc-sdoh2", PATIENT_ID, None, "Educational disruption",
              clinical_status="active", onset="2026-02-01"),

    # Normal BP
    bp_observation("bench-jc-bp1", PATIENT_ID, "2026-02-10", 112, 70),
    bp_observation("bench-jc-bp2", PATIENT_ID, "2026-03-10", 116, 72),
    bp_observation("bench-jc-bp3", PATIENT_ID, "2026-04-05", 118, 74),

    # Normal HbA1c
    hba1c_observation("bench-jc-a1c1", PATIENT_ID, "2026-02-10", 5.1),

    # Prenatal vitamins only
    medication_request("bench-jc-med1", PATIENT_ID, "Prenatal vitamins",
                       "Take 1 tablet daily", "2026-02-01"),

    # No Coverage resource — uninsured
]

BUNDLE = transaction_bundle(_resources)
