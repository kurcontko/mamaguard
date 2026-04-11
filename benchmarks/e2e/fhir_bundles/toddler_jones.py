"""
Ava Jones — 18-month-old toddler, mostly up to date.

Clinical profile:
  - Born 2024-10-09, ~18 months old
  - Up to date on most CDC-schedule vaccines
  - Missing M-CHAT autism screening (due at 18 months)
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    immunization,
    patient,
    survey_observation,
    transaction_bundle,
)

PATIENT_ID = "bench-toddler-jones-002"

_imms = [
    ("imm1", "HepB", "2024-10-09"),
    ("imm2", "HepB", "2024-11-09"),
    ("imm3", "DTaP", "2024-12-09"),
    ("imm4", "IPV", "2024-12-09"),
    ("imm5", "Hib", "2024-12-09"),
    ("imm6", "PCV13", "2024-12-09"),
    ("imm7", "RV", "2024-12-09"),
    ("imm8", "DTaP", "2025-02-09"),
    ("imm9", "IPV", "2025-02-09"),
    ("imm10", "Hib", "2025-02-09"),
    ("imm11", "PCV13", "2025-02-09"),
    ("imm12", "RV", "2025-02-09"),
    ("imm13", "HepB", "2025-04-09"),
    ("imm14", "DTaP", "2025-04-09"),
    ("imm15", "PCV13", "2025-04-09"),
    ("imm16", "Influenza", "2025-04-09"),
    ("imm17", "MMR", "2025-10-09"),
    ("imm18", "Varicella", "2025-10-09"),
    ("imm19", "HepA", "2025-10-09"),
    ("imm20", "PCV13", "2025-10-09"),
]

_screens = [
    ("scr1", "Newborn metabolic screen", "2024-10-10"),
    ("scr2", "Hearing screen", "2024-10-10"),
    ("scr3", "Developmental surveillance", "2024-11-09"),
    ("scr4", "Developmental surveillance", "2024-12-09"),
    ("scr5", "Developmental surveillance", "2025-02-09"),
    ("scr6", "Developmental surveillance", "2025-04-09"),
    ("scr7", "Developmental screening (ASQ/PEDS)", "2025-07-09"),
    ("scr8", "Developmental surveillance", "2025-10-09"),
    # M-CHAT autism screen at 18mo NOT recorded
]

_resources = [
    patient(PATIENT_ID, "Ava", "Jones", "2024-10-09", gender="female"),
] + [
    immunization(f"bench-tj-{sid}", PATIENT_ID, vaccine, date)
    for sid, vaccine, date in _imms
] + [
    survey_observation(f"bench-tj-{sid}", PATIENT_ID, date, name)
    for sid, name, date in _screens
]

BUNDLE = transaction_bundle(_resources)
