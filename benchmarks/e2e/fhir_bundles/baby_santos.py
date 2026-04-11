"""
Lucas Santos — 2-month-old newborn.

Clinical profile:
  - Born 2026-02-09, roughly 2 months old at bench time (2026-04-11)
  - Only HepB #1 at birth — due for full 2-month visit vaccines
  - Newborn metabolic + hearing screens completed
  - Mother is Maria Santos (high-risk: HTN + DM2)
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    immunization,
    patient,
    survey_observation,
    transaction_bundle,
)

PATIENT_ID = "bench-baby-santos-001"

_resources = [
    patient(PATIENT_ID, "Lucas", "Santos", "2026-02-09", gender="male"),

    # Immunizations — only birth dose given
    immunization("bench-bs-imm1", PATIENT_ID, "HepB", "2026-02-09"),

    # Newborn screens completed
    survey_observation("bench-bs-scr1", PATIENT_ID, "2026-02-10", "Newborn metabolic screen"),
    survey_observation("bench-bs-scr2", PATIENT_ID, "2026-02-10", "Hearing screen"),
]

BUNDLE = transaction_bundle(_resources)
