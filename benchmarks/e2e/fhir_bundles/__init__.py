"""
Real FHIR R4 transaction bundles for benchmark patients.

Each module exports:
  PATIENT_ID   — stable FHIR id for the patient
  BUNDLE       — a FHIR transaction Bundle (dict) that can be POSTed to a
                 FHIR server root to create all resources atomically.

Usage:
    import httpx
    from benchmarks.e2e.fhir_bundles.maria_high_risk import BUNDLE, PATIENT_ID
    httpx.post("http://localhost:8090/fhir", json=BUNDLE)
"""

from benchmarks.e2e.fhir_bundles import (
    baby_santos,
    child_smith,
    elena_preeclampsia,
    fatima_complex,
    james_insured,
    maria_high_risk,
    sarah_low_risk,
    toddler_jones,
)

ALL_PATIENTS: dict[str, dict] = {
    # patient_id -> {"bundle": <Bundle>, "label": <human name>, "scenario": <str>}
    maria_high_risk.PATIENT_ID: {
        "bundle": maria_high_risk.BUNDLE,
        "label": "Maria Santos",
        "scenario": "high-risk maternal: Stage 2 HTN, T2DM, recurrent pregnancy loss",
    },
    sarah_low_risk.PATIENT_ID: {
        "bundle": sarah_low_risk.BUNDLE,
        "label": "Sarah Johnson",
        "scenario": "low-risk maternal: normotensive, euglycemic, uncomplicated",
    },
    elena_preeclampsia.PATIENT_ID: {
        "bundle": elena_preeclampsia.BUNDLE,
        "label": "Elena Petrova",
        "scenario": "rapidly worsening BP during pregnancy — preeclampsia risk",
    },
    baby_santos.PATIENT_ID: {
        "bundle": baby_santos.BUNDLE,
        "label": "Lucas Santos (newborn)",
        "scenario": "2-month-old, partial immunizations, mother with DM2",
    },
    toddler_jones.PATIENT_ID: {
        "bundle": toddler_jones.BUNDLE,
        "label": "Ava Jones (18 months)",
        "scenario": "toddler up to date but missing M-CHAT autism screen",
    },
    child_smith.PATIENT_ID: {
        "bundle": child_smith.BUNDLE,
        "label": "Ethan Smith (5 years)",
        "scenario": "5-year-old lost to follow-up, massive immunization gaps",
    },
    james_insured.PATIENT_ID: {
        "bundle": james_insured.BUNDLE,
        "label": "James Wilson",
        "scenario": "fully insured, English-speaking, no SDOH concerns",
    },
    fatima_complex.PATIENT_ID: {
        "bundle": fatima_complex.BUNDLE,
        "label": "Fatima Al-Hassan",
        "scenario": "Arabic-speaking, unemployed, food insecurity, Medicaid",
    },
}
