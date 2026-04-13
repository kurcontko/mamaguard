"""
Lin Chen — patient with conflicting data: active HTN condition but recent normal BP.

Clinical edge case (c): tests that the agent flags the discrepancy between
an active hypertension diagnosis and consistently normal recent BP readings.
The agent should note that BP is currently well-controlled or question
whether the HTN condition should be re-evaluated, rather than blindly
reporting HIGH risk from the condition alone.

Clinical profile:
  - 35yo female, Mandarin-speaking
  - Active pregnancy (onset 2025-10-01)
  - Active condition: Essential hypertension (diagnosed 2022)
  - Recent BP all normal (118-124/76-82) — well-controlled
  - HbA1c normal (5.3)
  - On Labetalol (anti-hypertensive) — explains the controlled BP
  - Active insurance
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

PATIENT_ID = "bench-chen-010"

_resources = [
    patient(PATIENT_ID, "Lin", "Chen", "1990-06-18",
            gender="female", language="Mandarin"),

    # Active pregnancy
    condition("bench-c-preg1", PATIENT_ID, "72892002", "Normal pregnancy",
              clinical_status="active", onset="2025-10-01"),

    # Active HTN condition (diagnosed years ago)
    condition("bench-c-htn1", PATIENT_ID, "59621000", "Essential hypertension",
              clinical_status="active", onset="2022-03-15"),

    # Recent BP all NORMAL despite active HTN diagnosis
    bp_observation("bench-c-bp1", PATIENT_ID, "2026-01-10", 118, 76),
    bp_observation("bench-c-bp2", PATIENT_ID, "2026-02-10", 122, 80),
    bp_observation("bench-c-bp3", PATIENT_ID, "2026-03-10", 120, 78),
    bp_observation("bench-c-bp4", PATIENT_ID, "2026-04-05", 124, 82),

    # Normal HbA1c
    hba1c_observation("bench-c-a1c1", PATIENT_ID, "2026-01-10", 5.3),

    # Anti-hypertensive medication — explains controlled BP
    medication_request("bench-c-med1", PATIENT_ID, "Labetalol 200mg",
                       "Take 1 tablet twice daily", "2022-04-01"),
    medication_request("bench-c-med2", PATIENT_ID, "Prenatal vitamins",
                       "Take 1 tablet daily", "2025-10-15"),

    # Active insurance
    coverage("bench-c-cov1", PATIENT_ID, "Employer-sponsored HMO",
             status="active", start="2025-01-01"),
]

BUNDLE = transaction_bundle(_resources)
