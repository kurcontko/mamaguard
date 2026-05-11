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
    aisha_sdoh_only,
    baby_santos,
    baby_williams,
    carol_well_controlled,
    chen_conflicting_bp,
    child_smith,
    destiny_young_maternal,
    elena_preeclampsia,
    fatima_complex,
    grace_no_conditions,
    james_insured,
    jaylen_teen_pregnancy,
    lisa_expired_insurance,
    margaret_grandmother,
    maria_high_risk,
    priya_gdm,
    rosa_postpartum,
    sarah_low_risk,
    toddler_jones,
)


def get_bundle_refs(patient_id: str) -> set[str]:
    """Return the set of all FHIR resource references in a patient's bundle.

    Each reference is ``ResourceType/id`` (e.g. ``Observation/bench-m-bp1``).
    Returns an empty set for unknown patient IDs.
    """
    info = ALL_PATIENTS.get(patient_id)
    if info is None:
        return set()
    bundle = info["bundle"]
    refs: set[str] = set()
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        rtype = res.get("resourceType")
        rid = res.get("id")
        if rtype and rid:
            refs.add(f"{rtype}/{rid}")
    return refs


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
    priya_gdm.PATIENT_ID: {
        "bundle": priya_gdm.BUNDLE,
        "label": "Priya Sharma",
        "scenario": "gestational diabetes + Stage 1 HTN, Hindi-speaking, insured",
    },
    destiny_young_maternal.PATIENT_ID: {
        "bundle": destiny_young_maternal.BUNDLE,
        "label": "Destiny Williams",
        "scenario": "19yo first pregnancy, SDOH (stress + social isolation), Medicaid",
    },
    baby_williams.PATIENT_ID: {
        "bundle": baby_williams.BUNDLE,
        "label": "Mia Williams (7 months)",
        "scenario": "7-month-old who missed 4-month visit, overdue immunizations",
    },
    grace_no_conditions.PATIENT_ID: {
        "bundle": grace_no_conditions.BUNDLE,
        "label": "Grace Park",
        "scenario": "healthy pregnancy, zero conditions — should be ROUTINE, not error",
    },
    aisha_sdoh_only.PATIENT_ID: {
        "bundle": aisha_sdoh_only.BUNDLE,
        "label": "Aisha Johnson",
        "scenario": "SDOH-only issues (unemployment, food insecurity, housing), no medical risk",
    },
    chen_conflicting_bp.PATIENT_ID: {
        "bundle": chen_conflicting_bp.BUNDLE,
        "label": "Lin Chen",
        "scenario": "active HTN condition but recent BP readings all normal — conflicting data",
    },
    lisa_expired_insurance.PATIENT_ID: {
        "bundle": lisa_expired_insurance.BUNDLE,
        "label": "Lisa Brown",
        "scenario": "expired insurance (coverage.period.end in past), otherwise low-risk",
    },
    rosa_postpartum.PATIENT_ID: {
        "bundle": rosa_postpartum.BUNDLE,
        "label": "Rosa Martinez",
        "scenario": "postpartum >6 months, resolved gestational HTN — deprioritize pregnancy risks",
    },
    margaret_grandmother.PATIENT_ID: {
        "bundle": margaret_grandmother.BUNDLE,
        "label": "Margaret Washington",
        "scenario": "68yo grandmother as primary caregiver — pediatric agent should handle non-child gracefully",
    },
    jaylen_teen_pregnancy.PATIENT_ID: {
        "bundle": jaylen_teen_pregnancy.BUNDLE,
        "label": "Jaylen Carter",
        "scenario": "16yo teen pregnancy, uninsured, social isolation + educational disruption",
    },
    carol_well_controlled.PATIENT_ID: {
        "bundle": carol_well_controlled.BUNDLE,
        "label": "Carol Nguyen",
        "scenario": "well-controlled DM2 + HTN + hypothyroidism during pregnancy — should be ROUTINE",
    },
}
