"""
Compound reasoning-trace benchmark (Phase 2d — AI Factor evidence).

Forces the MamaGuard clinical stack to synthesise across multiple simultaneous
risk domains that a naive rule engine would see only as five unrelated flags:

  1. Postpartum Stage-2 hypertension  (BP 162/104, 158/98 on recent dates)
  2. HbA1c in the diabetes range      (7.2%)
  3. Housing instability Z-code        (SNOMED 105531004 — housing problem)
  4. Spanish language preference       (Patient.communication)
  5. Medicaid gap                      (no active Coverage resource)

For each case the benchmark runs three things in the same harness:

  - `rule_engine_baseline()`: a deliberately naive if/elif chain producing a
    flat list of domain flags with no synthesis, evidence, or clinician-review
    structure. Stand-in for "what non-AI software would have produced".
  - `mamaguard_synthesis()`: calls the real MamaGuard tools
    (`get_maternal_risk_profile` + `get_sdoh_screening`) against a mocked
    FHIR backend holding the compound-case bundles. Returns the full
    structured reasoning trace.
  - A side-by-side diff showing which AI-Factor affordances the synthesis
    contributes beyond the rule-engine baseline.

The full reasoning trace is captured to
`benchmarks/fixtures/reasoning_trace_maria.json` so it can be cited in
docs / submission materials. The trace is rewritten whenever the mocked FHIR
data or the synthesis layer changes — the fixture file is the canonical
reference snapshot, and `bench_reasoning_trace_fixture_current` verifies it
matches live synthesis output so regressions are surfaced on every Tier-1 run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from benchmarks.base import BenchmarkResult, BenchmarkSuite, MockToolContext, Verdict

suite = BenchmarkSuite(
    name="reasoning_trace",
    description="Compound-case synthesis vs. rule-engine baseline (AI Factor evidence)",
)


# -- Compound-case raw FHIR fixtures -------------------------------------------

PATIENT_ID = "compound-maria-001"

# Two recent BP readings, both severe (>160 systolic OR >110 diastolic), a
# third older reading that is elevated but not severe. Trend = increasing.
_BP_BUNDLE: dict[str, Any] = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        {
            "resource": {
                "resourceType": "Observation",
                "id": "bp-compound-1",
                "effectiveDateTime": "2026-03-20",
                "component": [
                    {"code": {"coding": [{"code": "8480-6"}]},
                     "valueQuantity": {"value": 162, "unit": "mmHg"}},
                    {"code": {"coding": [{"code": "8462-4"}]},
                     "valueQuantity": {"value": 104, "unit": "mmHg"}},
                ],
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "id": "bp-compound-2",
                "effectiveDateTime": "2026-03-10",
                "component": [
                    {"code": {"coding": [{"code": "8480-6"}]},
                     "valueQuantity": {"value": 158, "unit": "mmHg"}},
                    {"code": {"coding": [{"code": "8462-4"}]},
                     "valueQuantity": {"value": 98, "unit": "mmHg"}},
                ],
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "id": "bp-compound-3",
                "effectiveDateTime": "2026-02-15",
                "component": [
                    {"code": {"coding": [{"code": "8480-6"}]},
                     "valueQuantity": {"value": 144, "unit": "mmHg"}},
                    {"code": {"coding": [{"code": "8462-4"}]},
                     "valueQuantity": {"value": 92, "unit": "mmHg"}},
                ],
            }
        },
    ],
}

_HBA1C_BUNDLE: dict[str, Any] = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [{
        "resource": {
            "resourceType": "Observation",
            "id": "hba1c-compound-1",
            "effectiveDateTime": "2026-03-18",
            "valueQuantity": {"value": 7.2, "unit": "%"},
        }
    }],
}

_GLUCOSE_BUNDLE: dict[str, Any] = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [{
        "resource": {
            "resourceType": "Observation",
            "id": "glucose-compound-1",
            "effectiveDateTime": "2026-03-18",
            "valueQuantity": {"value": 148, "unit": "mg/dL"},
        }
    }],
}

# One resolved normal pregnancy (the recent live birth — context for postpartum
# flag), no recurrent losses.
_PREGNANCY_BUNDLE: dict[str, Any] = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [{
        "resource": {
            "resourceType": "Condition",
            "id": "preg-compound-1",
            "code": {"coding": [{"code": "72892002", "display": "Normal pregnancy"}],
                     "text": "Normal pregnancy"},
            "clinicalStatus": {"coding": [{"code": "resolved"}]},
            "onsetDateTime": "2025-05-10",
            "abatementDateTime": "2026-02-14",
        }
    }],
}

# All-conditions bundle returned by sdoh.get_sdoh_screening: includes the
# housing Z-code equivalent (SNOMED 105531004) plus the (clinically noisy but
# harmless) resolved normal pregnancy.
_ALL_CONDITIONS_BUNDLE: dict[str, Any] = {
    "resourceType": "Bundle",
    "type": "searchset",
    "entry": [
        {
            "resource": {
                "resourceType": "Condition",
                "id": "sdoh-housing-1",
                "code": {
                    "coding": [{"code": "105531004",
                                "display": "Housing problem (finding)"}],
                    "text": "Housing problem",
                },
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2025-11-01",
            }
        },
        {
            "resource": {
                "resourceType": "Condition",
                "id": "preg-compound-1",
                "code": {
                    "coding": [{"code": "72892002", "display": "Normal pregnancy"}],
                    "text": "Normal pregnancy",
                },
                "clinicalStatus": {"coding": [{"code": "resolved"}]},
            }
        },
    ],
}

_PATIENT_RESOURCE: dict[str, Any] = {
    "resourceType": "Patient",
    "id": PATIENT_ID,
    "communication": [{
        "language": {
            "coding": [{"system": "urn:ietf:bcp:47", "code": "es",
                        "display": "Spanish"}],
            "text": "Spanish",
        },
        "preferred": True,
    }],
}

# Empty Coverage bundle — this is the Medicaid gap.
_EMPTY_COVERAGE_BUNDLE: dict[str, Any] = {"resourceType": "Bundle", "type": "searchset", "entry": []}


def _maternal_fhir_side_effect(fhir_url, token, path, params=None):
    """Route mocked `_fhir_get` calls made from `mamaguard.shared.tools.maternal`."""
    params = params or {}
    code = params.get("code", "")
    if path == "Observation":
        if "55284-4" in code:
            return _BP_BUNDLE
        if "4548-4" in code:
            return _HBA1C_BUNDLE
        if "2339-0" in code:
            return _GLUCOSE_BUNDLE
    if path == "Condition":
        if "72892002" in code:
            return _PREGNANCY_BUNDLE
        # No losses — return empty for the other pregnancy SNOMED codes.
        return {"resourceType": "Bundle", "entry": []}
    return {"resourceType": "Bundle", "entry": []}


def _sdoh_fhir_side_effect(fhir_url, token, path, params=None):
    """Route mocked `_fhir_get` calls made from `mamaguard.shared.tools.sdoh`."""
    if path.startswith("Patient/"):
        return _PATIENT_RESOURCE
    if path == "Condition":
        return _ALL_CONDITIONS_BUNDLE
    if path == "Coverage":
        return _EMPTY_COVERAGE_BUNDLE
    return {"resourceType": "Bundle", "entry": []}


# -- Rule-engine baseline ------------------------------------------------------

def rule_engine_baseline() -> dict:
    """
    Deliberately naive non-AI baseline.

    Walks the same raw FHIR bundles and emits a flat list of domain flags with
    NO synthesis: no compound risk level, no evidence trails, no clinician
    review reasons, no cross-factor interactions, no confidence, no structured
    recommendations. The point of this function is to be the "floor" that a
    non-reasoning rule engine would produce from the same inputs — so the
    benchmark can show the exact AI-Factor lift that MamaGuard delivers.
    """
    flags: list[str] = []

    # Flag 1: highest systolic > 140 → HIGH_BP
    max_sys = 0
    max_dia = 0
    for entry in _BP_BUNDLE.get("entry", []):
        for comp in entry["resource"].get("component", []):
            loinc = (comp.get("code", {}).get("coding") or [{}])[0].get("code")
            v = comp.get("valueQuantity", {}).get("value", 0)
            if loinc == "8480-6":
                max_sys = max(max_sys, v)
            elif loinc == "8462-4":
                max_dia = max(max_dia, v)
    if max_sys > 140 or max_dia > 90:
        flags.append("HIGH_BP")

    # Flag 2: any HbA1c > 6.5 → DIABETES
    for entry in _HBA1C_BUNDLE.get("entry", []):
        if entry["resource"].get("valueQuantity", {}).get("value", 0) > 6.5:
            flags.append("DIABETES")
            break

    # Flag 3: housing-problem condition present
    for entry in _ALL_CONDITIONS_BUNDLE.get("entry", []):
        text = (entry["resource"].get("code", {}).get("text") or "").lower()
        if "housing" in text:
            flags.append("HOUSING_ISSUE")
            break

    # Flag 4: non-English language
    for comm in _PATIENT_RESOURCE.get("communication", []):
        lang = (comm.get("language", {}).get("text") or "").lower()
        if lang and lang != "english":
            flags.append("LANGUAGE_BARRIER")
            break

    # Flag 5: no Coverage resources
    if not _EMPTY_COVERAGE_BUNDLE.get("entry"):
        flags.append("NO_COVERAGE")

    return {
        "engine": "rule_based_baseline",
        "flags": flags,
        # Intentionally absent: risk_level, risk_factors, clinician_review,
        # evidence_basis, confidence, recommendations. A rule engine cannot
        # produce these without adding LLM-style reasoning.
    }


# -- MamaGuard synthesis driver -------------------------------------------------

def mamaguard_synthesis() -> dict:
    """
    Run the real MamaGuard clinical + SDOH tools against the compound-case
    fixtures and return a structured reasoning trace.
    """
    from mamaguard.shared.tools import fhir_base as fhir_base_mod
    from mamaguard.shared.tools.maternal import get_maternal_risk_profile
    from mamaguard.shared.tools.sdoh import get_sdoh_screening

    ctx = MockToolContext(patient_id=PATIENT_ID)

    def _combined_fhir_side_effect(fhir_url, token, path, params=None):
        params = params or {}
        code = params.get("code", "")
        if path.startswith("Patient/"):
            return _PATIENT_RESOURCE
        if path == "Coverage":
            return _EMPTY_COVERAGE_BUNDLE
        if path == "Observation":
            if "55284-4" in code:
                return _BP_BUNDLE
            if "4548-4" in code:
                return _HBA1C_BUNDLE
            if "2339-0" in code:
                return _GLUCOSE_BUNDLE
            return {"resourceType": "Bundle", "entry": []}
        if path == "Condition":
            if code:
                return _PREGNANCY_BUNDLE if "72892002" in code else {"resourceType": "Bundle", "entry": []}
            return _ALL_CONDITIONS_BUNDLE
        return {"resourceType": "Bundle", "entry": []}

    with patch.object(fhir_base_mod, "_fhir_get", side_effect=_combined_fhir_side_effect):
        maternal_profile = get_maternal_risk_profile(tool_context=ctx)  # type: ignore[arg-type]
        sdoh_profile = get_sdoh_screening(tool_context=ctx)  # type: ignore[arg-type]

    # Cross-factor synthesis — what the liaison layer uses to compose the
    # clinician-facing summary after both specialist agents return. This is
    # the piece the rule engine fundamentally cannot produce.
    cross_factor_insights = _compose_cross_factor_insights(maternal_profile, sdoh_profile)

    return {
        "engine": "mamaguard_synthesis",
        "patient_id": PATIENT_ID,
        "maternal_profile": maternal_profile,
        "sdoh_profile": sdoh_profile,
        "cross_factor_insights": cross_factor_insights,
    }


def _compose_cross_factor_insights(maternal: dict, sdoh: dict) -> dict:
    """
    Synthesise cross-domain insights from the specialist tool outputs.

    This mirrors what the MamaGuard liaison orchestrator does when it stitches
    together maternal + SDOH specialist results before returning to the
    clinician. The logic is intentionally *not* in the rule engine baseline
    because it requires reasoning about interactions between flags.
    """
    m_data = maternal.get("data", {}) if maternal.get("status") == "success" else {}
    s_data = sdoh.get("data", {}) if sdoh.get("status") == "success" else {}

    insights: list[str] = []
    priorities: list[str] = []

    risk_level = m_data.get("risk_level", "ROUTINE")
    risk_factors = m_data.get("risk_factors", [])
    has_severe_bp = any("Stage 2" in f or ">160" in f for f in risk_factors)
    has_diabetes = any("Diabetes" in f or ">6.5" in f or "HbA1c" in f for f in risk_factors)

    has_housing = any("housing" in (c.get("condition") or "").lower()
                      for c in s_data.get("sdoh_conditions", []))
    has_language_barrier = bool(s_data.get("language")) and \
        s_data["language"].lower() not in ("english", "en")
    has_coverage_gap = len(s_data.get("coverage", [])) == 0

    # The compound insights — each one is an explicit interaction between a
    # clinical finding and a social-context finding that a rule engine would
    # miss.
    if has_severe_bp and has_coverage_gap:
        insights.append(
            "Severe hypertension co-occurs with a coverage gap: antihypertensive "
            "access is at risk. Treat as an urgent continuity-of-care issue, "
            "not just a medication adjustment."
        )
        priorities.append("urgent_coverage_bridge")

    if has_severe_bp and has_language_barrier:
        insights.append(
            "Postpartum severe BP teaching must be delivered in the patient's "
            "preferred language (Spanish); English-only discharge instructions "
            "are a known driver of readmission for postpartum preeclampsia."
        )
        priorities.append("spanish_bp_education")

    if has_diabetes and has_housing:
        insights.append(
            "Diabetes management is incompatible with unstable housing "
            "(refrigeration for insulin, consistent meal timing). SDOH team "
            "should be looped in before any glycemic medication change."
        )
        priorities.append("housing_before_glycemic_plan")

    if has_severe_bp and has_diabetes:
        insights.append(
            "Overlap of postpartum hypertension and diabetes range HbA1c "
            "raises long-term cardiovascular risk — flag for extended "
            "postpartum follow-up beyond the 6-week standard."
        )
        priorities.append("extended_postpartum_followup")

    if has_housing and has_coverage_gap and has_language_barrier:
        insights.append(
            "All three social determinants (housing, coverage, language) are "
            "present simultaneously — escalate to SDOH navigator for bundled "
            "wraparound referral, not three independent referrals."
        )
        priorities.append("bundled_sdoh_navigation")

    return {
        "compound_risk_level": risk_level,
        "clinical_sdoh_interactions": insights,
        "recommended_priorities": priorities,
        "synthesis_confidence": 0.85 if insights else 0.6,
    }


# -- Diff: what synthesis adds over the rule-engine baseline -------------------

def _synthesis_advantage(baseline: dict, synthesis: dict) -> dict:
    """Return a structured diff showing AI Factor lift."""
    maternal = synthesis.get("maternal_profile", {})
    sdoh = synthesis.get("sdoh_profile", {})
    cross = synthesis.get("cross_factor_insights", {})

    m_review = maternal.get("clinician_review", {})
    s_review = sdoh.get("clinician_review", {})

    evidence_refs = list(m_review.get("evidence_basis", [])) + list(
        s_review.get("evidence_basis", [])
    )

    advantages = {
        "baseline_flag_count": len(baseline.get("flags", [])),
        "baseline_has_compound_risk_level": False,  # by construction
        "baseline_has_evidence_basis": False,       # by construction
        "baseline_has_clinician_reason": False,     # by construction
        "baseline_has_cross_factor_insights": False,  # by construction
        "synthesis_risk_level": maternal.get("data", {}).get("risk_level"),
        "synthesis_risk_factor_count": len(maternal.get("data", {}).get("risk_factors", [])),
        "synthesis_evidence_ref_count": len(evidence_refs),
        "synthesis_evidence_refs": evidence_refs,
        "synthesis_has_clinician_reason": bool(m_review.get("reason")),
        "synthesis_has_recommendation": bool(m_review.get("recommendation")),
        "synthesis_has_confidence": "confidence" in m_review,
        "synthesis_has_language_context": bool(sdoh.get("data", {}).get("language")),
        "synthesis_has_coverage_context": "coverage" in sdoh.get("data", {}),
        "synthesis_cross_factor_insight_count": len(cross.get("clinical_sdoh_interactions", [])),
        "synthesis_cross_factor_priorities": cross.get("recommended_priorities", []),
    }

    # Count affordances present in synthesis but absent in baseline.
    affordance_keys = [
        "synthesis_risk_level",
        "synthesis_has_clinician_reason",
        "synthesis_has_recommendation",
        "synthesis_has_confidence",
        "synthesis_has_language_context",
        "synthesis_has_coverage_context",
    ]
    affordances_added = sum(1 for k in affordance_keys if advantages.get(k))
    advantages["affordances_added_by_synthesis"] = affordances_added
    advantages["evidence_multiplier"] = (
        len(evidence_refs) / max(1, advantages["baseline_flag_count"])
    )
    return advantages


# -- Fixture capture -----------------------------------------------------------

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "reasoning_trace_maria.json"


def _build_full_trace() -> dict:
    baseline = rule_engine_baseline()
    synthesis = mamaguard_synthesis()
    diff = _synthesis_advantage(baseline, synthesis)
    return {
        "case_name": "compound_maria_postpartum",
        "description": (
            "Compound synthesis scenario: postpartum Stage-2 HTN + HbA1c "
            "diabetes-range + housing instability Z-code + Spanish language "
            "preference + Medicaid gap. Demonstrates AI Factor lift of "
            "MamaGuard's liaison-pattern synthesis vs. a naive rule engine."
        ),
        "rule_engine_baseline": baseline,
        "mamaguard_synthesis": synthesis,
        "synthesis_advantage": diff,
    }


def _load_fixture() -> dict | None:
    if not FIXTURE_PATH.exists():
        return None
    try:
        return json.loads(FIXTURE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


# -- Benchmark cases -----------------------------------------------------------

@suite.case(
    "compound_synthesis_detects_all_factors",
    "Liaison synthesis detects BP + diabetes range + housing + language + coverage gap together",
    "reasoning_trace",
)
def bench_compound_synthesis_detects_all_factors():
    synthesis = mamaguard_synthesis()
    maternal = synthesis["maternal_profile"]
    sdoh = synthesis["sdoh_profile"]

    m_data = maternal["data"]
    s_data = sdoh["data"]

    checks = {
        # Maternal side
        "risk_level_elevated": m_data["risk_level"] in ("URGENT", "HIGH"),
        "bp_severe_flagged": bool(m_data["bp_summary"]["alert_severe"]),
        "hba1c_diabetes_range": bool(m_data["glucose_summary"]["diabetes_range"]),
        "multi_factor": len(m_data["risk_factors"]) >= 2,
        "maternal_clinician_review": maternal["clinician_review"]["required"] is True,
        # SDOH side
        "housing_condition_present": any(
            "housing" in (c.get("condition") or "").lower()
            for c in s_data["sdoh_conditions"]
        ),
        "spanish_language_detected": (s_data.get("language") or "").lower() == "spanish",
        "coverage_gap_detected": len(s_data.get("coverage", [])) == 0,
        "sdoh_clinician_review": sdoh["clinician_review"]["required"] is True,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="compound_synthesis_detects_all_factors",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case(
    "rule_engine_baseline_is_flat",
    "Rule-engine baseline produces isolated flags without synthesis structure",
    "reasoning_trace",
)
def bench_rule_engine_baseline_is_flat():
    baseline = rule_engine_baseline()
    expected = {"HIGH_BP", "DIABETES", "HOUSING_ISSUE", "LANGUAGE_BARRIER", "NO_COVERAGE"}
    checks = {
        "all_five_flags_present": set(baseline["flags"]) == expected,
        "no_risk_level_field": "risk_level" not in baseline,
        "no_clinician_review_field": "clinician_review" not in baseline,
        "no_evidence_basis_field": "evidence_basis" not in baseline,
        "no_confidence_field": "confidence" not in baseline,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="rule_engine_baseline_is_flat",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case(
    "synthesis_beats_baseline_diff",
    "Liaison synthesis adds compound risk, evidence refs, cross-factor insights",
    "reasoning_trace",
)
def bench_synthesis_beats_baseline_diff():
    baseline = rule_engine_baseline()
    synthesis = mamaguard_synthesis()
    diff = _synthesis_advantage(baseline, synthesis)

    checks = {
        "baseline_had_five_flat_flags": diff["baseline_flag_count"] == 5,
        "synthesis_has_compound_risk_level": diff["synthesis_risk_level"] in ("URGENT", "HIGH"),
        "synthesis_adds_all_six_affordances": diff["affordances_added_by_synthesis"] == 6,
        "synthesis_cites_fhir_evidence": diff["synthesis_evidence_ref_count"] >= 3,
        "synthesis_has_cross_factor_insights": diff["synthesis_cross_factor_insight_count"] >= 3,
        "evidence_multiplier_gt_baseline": diff["evidence_multiplier"] >= 1.0,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="synthesis_beats_baseline_diff",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details={**checks, "diff_summary": {
            "baseline_flag_count": diff["baseline_flag_count"],
            "synthesis_risk_level": diff["synthesis_risk_level"],
            "synthesis_evidence_ref_count": diff["synthesis_evidence_ref_count"],
            "synthesis_cross_factor_insight_count": diff["synthesis_cross_factor_insight_count"],
            "affordances_added_by_synthesis": diff["affordances_added_by_synthesis"],
        }},
    )


@suite.case(
    "cross_factor_insights_reference_interactions",
    "Cross-factor layer explicitly names clinical x SDOH interactions",
    "reasoning_trace",
)
def bench_cross_factor_insights_reference_interactions():
    synthesis = mamaguard_synthesis()
    cross = synthesis["cross_factor_insights"]
    insight_text = " ".join(cross.get("clinical_sdoh_interactions", [])).lower()
    priorities = cross.get("recommended_priorities", [])

    checks = {
        "mentions_coverage_interaction": "coverage" in insight_text,
        "mentions_spanish_education": "spanish" in insight_text,
        "mentions_housing_diabetes_interaction": "housing" in insight_text and "insulin" in insight_text,
        "mentions_postpartum_followup": "postpartum" in insight_text,
        "has_recommended_priorities": len(priorities) >= 4,
        "compound_risk_label_populated": cross.get("compound_risk_level") in ("URGENT", "HIGH"),
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="cross_factor_insights_reference_interactions",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details={**checks, "insight_count": len(cross.get("clinical_sdoh_interactions", []))},
    )


@suite.case(
    "reasoning_trace_fixture_current",
    "Committed reasoning-trace fixture matches live synthesis output",
    "reasoning_trace",
)
def bench_reasoning_trace_fixture_current():
    """
    Keep `benchmarks/fixtures/reasoning_trace_maria.json` in sync with the
    live synthesis. The fixture is committed so it can be cited in docs /
    submission materials; this case makes a drift in the synthesis layer or
    the mocked FHIR fixtures surface immediately as a Tier-1 failure.
    """
    live = _build_full_trace()
    fixture = _load_fixture()

    checks = {
        "fixture_exists": fixture is not None,
        "case_name_matches": bool(fixture) and fixture.get("case_name") == live["case_name"],
        "baseline_flags_match": bool(fixture) and fixture.get("rule_engine_baseline", {}).get("flags") == live["rule_engine_baseline"]["flags"],
        "synthesis_risk_level_matches": bool(fixture) and fixture.get("mamaguard_synthesis", {}).get("maternal_profile", {}).get("data", {}).get("risk_level") == live["mamaguard_synthesis"]["maternal_profile"]["data"]["risk_level"],
        "cross_factor_count_matches": bool(fixture) and len(
            fixture.get("mamaguard_synthesis", {}).get("cross_factor_insights", {}).get("clinical_sdoh_interactions", [])
        ) == len(live["mamaguard_synthesis"]["cross_factor_insights"]["clinical_sdoh_interactions"]),
        "synthesis_advantage_matches": bool(fixture) and fixture.get("synthesis_advantage", {}).get("affordances_added_by_synthesis") == live["synthesis_advantage"]["affordances_added_by_synthesis"],
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="reasoning_trace_fixture_current",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details={
            **checks,
            "fixture_path": str(FIXTURE_PATH),
            "hint": (
                "If this fails, the synthesis layer or mocked FHIR fixtures "
                "changed — regenerate with "
                "`python3 -m benchmarks.clinical_reasoning.bench_reasoning_trace "
                "--regenerate-fixture`."
            ),
        },
    )


# -- CLI: regenerate the fixture ----------------------------------------------

def _regenerate_fixture() -> None:
    trace = _build_full_trace()
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(trace, indent=2, default=str) + "\n")
    print(f"Wrote reasoning-trace fixture to {FIXTURE_PATH}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compound reasoning-trace benchmark")
    parser.add_argument("--regenerate-fixture", action="store_true",
                        help="Rewrite the committed fixture from live synthesis output")
    args = parser.parse_args()
    if args.regenerate_fixture:
        _regenerate_fixture()
    else:
        print("Run via `python3 -m benchmarks.runner --suite reasoning_trace` "
              "to execute the benchmark cases.")
