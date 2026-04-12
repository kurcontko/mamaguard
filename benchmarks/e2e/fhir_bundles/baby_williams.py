"""
Mia Williams — 7-month-old who missed 4-month well-child visit.

Clinical profile:
  - Born 2025-09-12, roughly 7 months old at bench time (2026-04-12)
  - Received birth + 2-month vaccines (HepB #1, HepB #2, DTaP #1, IPV #1,
    Hib #1, PCV13 #1, RV #1)
  - Missed entire 4-month visit — 4-month vaccines now overdue
  - Due for 6-month vaccines (HepB #3, DTaP #3, PCV13 #3, Influenza #1)
  - Newborn metabolic + hearing screens completed
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    immunization,
    patient,
    survey_observation,
    transaction_bundle,
)

PATIENT_ID = "bench-baby-williams-004"

_resources = [
    patient(PATIENT_ID, "Mia", "Williams", "2025-09-12", gender="female"),

    # Birth dose
    immunization("bench-bw-imm-hepb1", PATIENT_ID, "HepB", "2025-09-12"),

    # 1-month dose
    immunization("bench-bw-imm-hepb2", PATIENT_ID, "HepB", "2025-10-12"),

    # 2-month visit vaccines
    immunization("bench-bw-imm-dtap1", PATIENT_ID, "DTaP", "2025-11-12"),
    immunization("bench-bw-imm-ipv1", PATIENT_ID, "IPV", "2025-11-12"),
    immunization("bench-bw-imm-hib1", PATIENT_ID, "Hib", "2025-11-12"),
    immunization("bench-bw-imm-pcv1", PATIENT_ID, "PCV13", "2025-11-12"),
    immunization("bench-bw-imm-rv1", PATIENT_ID, "RV", "2025-11-12"),

    # 4-month visit MISSED — no vaccines given at 4 months

    # Newborn screens completed
    survey_observation("bench-bw-scr1", PATIENT_ID, "2025-09-13",
                       "Newborn metabolic screen"),
    survey_observation("bench-bw-scr2", PATIENT_ID, "2025-09-13",
                       "Hearing screen"),
]

BUNDLE = transaction_bundle(_resources)
