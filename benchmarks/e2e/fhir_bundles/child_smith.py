"""
Ethan Smith — 5-year-old, lost to follow-up.

Clinical profile:
  - Born 2021-04-09, ~5 years old
  - Only 4 immunizations on record (2-month shots)
  - Massive catch-up immunization backlog
  - No developmental screenings since hearing screen
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    immunization,
    patient,
    survey_observation,
    transaction_bundle,
)

PATIENT_ID = "bench-child-smith-003"

_resources = [
    patient(PATIENT_ID, "Ethan", "Smith", "2021-04-09", gender="male"),

    # Only 2-month vaccines given
    immunization("bench-cs-imm1", PATIENT_ID, "HepB", "2021-04-09"),
    immunization("bench-cs-imm2", PATIENT_ID, "HepB", "2021-05-09"),
    immunization("bench-cs-imm3", PATIENT_ID, "DTaP", "2021-06-09"),
    immunization("bench-cs-imm4", PATIENT_ID, "IPV", "2021-06-09"),

    # Only newborn screens
    survey_observation("bench-cs-scr1", PATIENT_ID, "2021-04-10", "Newborn metabolic screen"),
    survey_observation("bench-cs-scr2", PATIENT_ID, "2021-04-10", "Hearing screen"),
]

BUNDLE = transaction_bundle(_resources)
