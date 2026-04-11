"""
Elena Petrova — rapidly deteriorating BP in active pregnancy.

Clinical profile:
  - 30yo female, Russian-speaking
  - Active pregnancy (onset 2025-09-01)
  - BP climbing rapidly: 124/82 -> 184/118 over 9 weeks
  - No prior HTN history
  - Classic preeclampsia presentation
"""

from benchmarks.e2e.fhir_bundles._helpers import (
    bp_observation,
    condition,
    hba1c_observation,
    patient,
    transaction_bundle,
)

PATIENT_ID = "bench-elena-003"

_resources = [
    patient(PATIENT_ID, "Elena", "Petrova", "1995-11-03",
            gender="female", language="Russian"),

    # Active pregnancy
    condition("bench-e-preg", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2025-09-01"),

    # Rapidly worsening BP
    bp_observation("bench-e-bp1", PATIENT_ID, "2026-01-05", 124, 82),
    bp_observation("bench-e-bp2", PATIENT_ID, "2026-02-01", 138, 88),
    bp_observation("bench-e-bp3", PATIENT_ID, "2026-02-15", 156, 102),
    bp_observation("bench-e-bp4", PATIENT_ID, "2026-03-01", 172, 114),
    bp_observation("bench-e-bp5", PATIENT_ID, "2026-03-10", 184, 118),

    # Normal A1c — distinguish from Maria
    hba1c_observation("bench-e-a1c1", PATIENT_ID, "2026-01-10", 5.0),
]

BUNDLE = transaction_bundle(_resources)
