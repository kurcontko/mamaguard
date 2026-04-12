"""
Baseline comparison table (Phase 3 — AI Factor judging evidence).

Extends the single-case reasoning-trace benchmark with a multi-case side-by-
side comparison: for each of three clinical scenarios (mild / moderate /
severe) we run the naive rule-engine baseline and the MamaGuard liaison
synthesis against the same mocked FHIR bundles, then quantify the lift the
synthesis layer contributes.

Purpose
-------
Gives the hackathon judges a single artefact that shows, across a range of
complexity, what a non-AI rule engine would have produced versus what the
MamaGuard synthesis actually produces. It is the concrete evidence for the
"AI Factor" judging axis called out in TASK.md Phase 3.

Outputs
-------
- `benchmarks/fixtures/baseline_comparison_table.json` — full per-case data
  (baseline flags, synthesis risk level, cross-factor insights, advantage
  diff, per-case deltas) for downstream tooling.
- `benchmarks/fixtures/baseline_comparison_table.md` — human-readable
  markdown table for inclusion in submission materials / README.

Both are committed. The `baseline_comparison_fixture_current` Tier-1 case
pins the fixtures against live synthesis output so drift in the synthesis
layer, rule engine, or mocked FHIR fixtures is surfaced on every benchmark
run. Regenerate via:

    python3 -m benchmarks.clinical_reasoning.bench_baseline_comparison \
        --regenerate-fixture
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from benchmarks.base import BenchmarkResult, BenchmarkSuite, MockToolContext, Verdict

suite = BenchmarkSuite(
    name="baseline_comparison",
    description="Rule-engine baseline vs. MamaGuard synthesis across mild/moderate/severe cases",
)


# -- Case definition -----------------------------------------------------------


@dataclass
class CaseFixture:
    """Raw mocked FHIR bundles + metadata for one comparison case."""

    case_id: str
    display_name: str
    tier: str  # low, moderate, severe
    narrative: str
    patient_id: str
    bp_bundle: dict = field(default_factory=dict)
    hba1c_bundle: dict = field(default_factory=dict)
    glucose_bundle: dict = field(default_factory=dict)
    pregnancy_bundle: dict = field(default_factory=dict)
    loss_bundle: dict = field(default_factory=dict)
    all_conditions_bundle: dict = field(default_factory=dict)
    patient_resource: dict = field(default_factory=dict)
    coverage_bundle: dict = field(default_factory=dict)


def _empty_bundle() -> dict:
    return {"resourceType": "Bundle", "type": "searchset", "entry": []}


def _bp_entry(dt: str, sys_mmhg: int, dia_mmhg: int, obs_id: str) -> dict:
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "effectiveDateTime": dt,
            "component": [
                {
                    "code": {"coding": [{"code": "8480-6"}]},
                    "valueQuantity": {"value": sys_mmhg, "unit": "mmHg"},
                },
                {
                    "code": {"coding": [{"code": "8462-4"}]},
                    "valueQuantity": {"value": dia_mmhg, "unit": "mmHg"},
                },
            ],
        }
    }


def _hba1c_entry(dt: str, value: float, obs_id: str) -> dict:
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "effectiveDateTime": dt,
            "valueQuantity": {"value": value, "unit": "%"},
        }
    }


def _glucose_entry(dt: str, value: int, obs_id: str) -> dict:
    return {
        "resource": {
            "resourceType": "Observation",
            "id": obs_id,
            "effectiveDateTime": dt,
            "valueQuantity": {"value": value, "unit": "mg/dL"},
        }
    }


def _housing_condition(cond_id: str = "cond-housing") -> dict:
    return {
        "resource": {
            "resourceType": "Condition",
            "id": cond_id,
            "code": {
                "coding": [
                    {"code": "105531004", "display": "Housing problem (finding)"}
                ],
                "text": "Housing problem",
            },
            "clinicalStatus": {"coding": [{"code": "active"}]},
            "onsetDateTime": "2025-11-01",
        }
    }


def _normal_pregnancy_condition(cond_id: str = "cond-preg") -> dict:
    return {
        "resource": {
            "resourceType": "Condition",
            "id": cond_id,
            "code": {
                "coding": [{"code": "72892002", "display": "Normal pregnancy"}],
                "text": "Normal pregnancy",
            },
            "clinicalStatus": {"coding": [{"code": "resolved"}]},
            "onsetDateTime": "2025-05-10",
            "abatementDateTime": "2026-02-14",
        }
    }


def _patient_resource(patient_id: str, language: str | None) -> dict:
    res: dict[str, Any] = {"resourceType": "Patient", "id": patient_id}
    if language:
        # Language code: english -> en, spanish -> es. Good enough for the
        # bench; the real tool uses BCP-47 codes or display text.
        code = {"english": "en", "spanish": "es"}.get(language.lower(), language[:2])
        res["communication"] = [
            {
                "language": {
                    "coding": [
                        {
                            "system": "urn:ietf:bcp:47",
                            "code": code,
                            "display": language.title(),
                        }
                    ],
                    "text": language.title(),
                },
                "preferred": True,
            }
        ]
    return res


def _medicaid_coverage_bundle(patient_id: str) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "Coverage",
                    "id": f"cov-{patient_id}",
                    "status": "active",
                    "type": {"text": "Medicaid"},
                }
            }
        ],
    }


# -- Concrete cases ------------------------------------------------------------


def _case_low() -> CaseFixture:
    """Routine postpartum visit — essentially a negative control."""
    pid = "bench-low-ana"
    return CaseFixture(
        case_id="low_routine_postpartum",
        display_name="Routine postpartum — low complexity",
        tier="low",
        narrative=(
            "Postpartum follow-up, BP 128/82 and 124/78, HbA1c 5.4%, English "
            "speaker, active Medicaid coverage, no SDOH Z-codes. A correctly "
            "calibrated system should keep this case at ROUTINE and NOT flag "
            "clinician review."
        ),
        patient_id=pid,
        bp_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                _bp_entry("2026-03-22", 128, 82, "bp-low-1"),
                _bp_entry("2026-03-05", 124, 78, "bp-low-2"),
            ],
        },
        hba1c_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_hba1c_entry("2026-03-20", 5.4, "hba1c-low-1")],
        },
        glucose_bundle=_empty_bundle(),
        pregnancy_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_normal_pregnancy_condition("preg-low")],
        },
        loss_bundle=_empty_bundle(),
        all_conditions_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_normal_pregnancy_condition("preg-low")],
        },
        patient_resource=_patient_resource(pid, "english"),
        coverage_bundle=_medicaid_coverage_bundle(pid),
    )


def _case_moderate() -> CaseFixture:
    """Elevated BP + borderline diabetes + language barrier; coverage intact."""
    pid = "bench-mod-lucia"
    return CaseFixture(
        case_id="moderate_gdm_language",
        display_name="Moderate — elevated BP + borderline A1c + language",
        tier="moderate",
        narrative=(
            "Two-week postpartum: BP 146/92 and 142/88 (Stage 1), HbA1c 6.8% "
            "(diabetes range), Spanish-preferred, active Medicaid, no housing/"
            "food Z-codes. The rule engine should surface three flat flags "
            "(HIGH_BP, DIABETES, LANGUAGE_BARRIER); the liaison synthesis "
            "should lift this to HIGH risk with a BP-diabetes extended-"
            "postpartum-followup interaction and a Spanish education priority."
        ),
        patient_id=pid,
        bp_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                _bp_entry("2026-03-25", 146, 92, "bp-mod-1"),
                _bp_entry("2026-03-12", 142, 88, "bp-mod-2"),
            ],
        },
        hba1c_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_hba1c_entry("2026-03-22", 6.8, "hba1c-mod-1")],
        },
        glucose_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_glucose_entry("2026-03-22", 132, "glu-mod-1")],
        },
        pregnancy_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_normal_pregnancy_condition("preg-mod")],
        },
        loss_bundle=_empty_bundle(),
        all_conditions_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_normal_pregnancy_condition("preg-mod")],
        },
        patient_resource=_patient_resource(pid, "spanish"),
        coverage_bundle=_medicaid_coverage_bundle(pid),
    )


def _case_severe() -> CaseFixture:
    """Severe compound: Stage-2 HTN + diabetes-range A1c + housing + Spanish + no coverage."""
    pid = "bench-sev-marta"
    return CaseFixture(
        case_id="severe_compound_postpartum",
        display_name="Severe compound — HTN + A1c + housing + language + coverage gap",
        tier="severe",
        narrative=(
            "Three-week postpartum: BP 164/106 and 160/100 (Stage 2), HbA1c "
            "7.4% (diabetes range), active housing-problem Z-code (SNOMED "
            "105531004), Spanish-preferred, no active Coverage resource "
            "(Medicaid gap). The liaison synthesis should produce URGENT "
            "risk with 4+ cross-factor interactions — the rule engine can "
            "only emit 5 flat, isolated flags."
        ),
        patient_id=pid,
        bp_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                _bp_entry("2026-03-30", 164, 106, "bp-sev-1"),
                _bp_entry("2026-03-20", 160, 100, "bp-sev-2"),
            ],
        },
        hba1c_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_hba1c_entry("2026-03-28", 7.4, "hba1c-sev-1")],
        },
        glucose_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_glucose_entry("2026-03-28", 152, "glu-sev-1")],
        },
        pregnancy_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [_normal_pregnancy_condition("preg-sev")],
        },
        loss_bundle=_empty_bundle(),
        all_conditions_bundle={
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                _housing_condition("cond-housing-sev"),
                _normal_pregnancy_condition("preg-sev"),
            ],
        },
        patient_resource=_patient_resource(pid, "spanish"),
        coverage_bundle=_empty_bundle(),
    )


CASES: list[CaseFixture] = [_case_low(), _case_moderate(), _case_severe()]


# -- Mock side-effect factories ------------------------------------------------


def _maternal_side_effect_for(case: CaseFixture) -> Callable:
    """Route mocked `_fhir_get` calls made from `mamaguard.shared.tools.maternal`."""

    def _side_effect(fhir_url, token, path, params=None):
        params = params or {}
        code = params.get("code", "")
        if path == "Observation":
            if "55284-4" in code:
                return case.bp_bundle
            if "4548-4" in code:
                return case.hba1c_bundle
            if "2339-0" in code:
                return case.glucose_bundle
            return _empty_bundle()
        if path == "Condition":
            if "72892002" in code:
                return case.pregnancy_bundle
            return case.loss_bundle
        return _empty_bundle()

    return _side_effect


def _sdoh_side_effect_for(case: CaseFixture) -> Callable:
    """Route mocked `_fhir_get` calls made from `mamaguard.shared.tools.sdoh`."""

    def _side_effect(fhir_url, token, path, params=None):
        if path.startswith("Patient/"):
            return case.patient_resource
        if path == "Condition":
            return case.all_conditions_bundle
        if path == "Coverage":
            return case.coverage_bundle
        return _empty_bundle()

    return _side_effect


# -- Rule-engine baseline (parametric version of the reasoning_trace one) ------


def rule_engine_baseline(case: CaseFixture) -> dict:
    """
    Deliberately naive non-AI baseline. Walks the same raw bundles the
    synthesis path will see and emits a flat list of isolated flags with no
    risk level, evidence, clinician-review reasoning, or cross-factor
    structure. Same shape and philosophy as the function of the same name
    in `bench_reasoning_trace.py`, parametrised over a `CaseFixture`.
    """
    flags: list[str] = []

    max_sys, max_dia = 0, 0
    for entry in case.bp_bundle.get("entry", []):
        for comp in entry["resource"].get("component", []):
            loinc = (comp.get("code", {}).get("coding") or [{}])[0].get("code")
            v = comp.get("valueQuantity", {}).get("value", 0)
            if loinc == "8480-6":
                max_sys = max(max_sys, v)
            elif loinc == "8462-4":
                max_dia = max(max_dia, v)
    if max_sys > 140 or max_dia > 90:
        flags.append("HIGH_BP")

    for entry in case.hba1c_bundle.get("entry", []):
        if entry["resource"].get("valueQuantity", {}).get("value", 0) > 6.5:
            flags.append("DIABETES")
            break

    for entry in case.all_conditions_bundle.get("entry", []):
        text = (entry["resource"].get("code", {}).get("text") or "").lower()
        if "housing" in text:
            flags.append("HOUSING_ISSUE")
            break

    for comm in case.patient_resource.get("communication", []):
        lang = (comm.get("language", {}).get("text") or "").lower()
        if lang and lang != "english":
            flags.append("LANGUAGE_BARRIER")
            break

    if not case.coverage_bundle.get("entry"):
        flags.append("NO_COVERAGE")

    return {
        "engine": "rule_based_baseline",
        "flags": flags,
        # Intentionally absent: risk_level, risk_factors, clinician_review,
        # evidence_basis, confidence, recommendations, interactions.
    }


# -- MamaGuard synthesis driver ------------------------------------------------


def mamaguard_synthesis(case: CaseFixture) -> dict:
    """Run the real MamaGuard clinical + SDOH tools against the case fixture."""
    from mamaguard.shared.tools import maternal as maternal_mod
    from mamaguard.shared.tools import sdoh as sdoh_mod
    from mamaguard.shared.tools.maternal import get_maternal_risk_profile
    from mamaguard.shared.tools.sdoh import get_sdoh_screening

    ctx = MockToolContext(patient_id=case.patient_id)

    with patch.object(maternal_mod, "_fhir_get", side_effect=_maternal_side_effect_for(case)), \
         patch.object(sdoh_mod, "_fhir_get", side_effect=_sdoh_side_effect_for(case)):
        maternal_profile = get_maternal_risk_profile(tool_context=ctx)
        sdoh_profile = get_sdoh_screening(tool_context=ctx)

    cross_factor_insights = _compose_cross_factor_insights(maternal_profile, sdoh_profile)

    return {
        "engine": "mamaguard_synthesis",
        "patient_id": case.patient_id,
        "maternal_profile": maternal_profile,
        "sdoh_profile": sdoh_profile,
        "cross_factor_insights": cross_factor_insights,
    }


def _compose_cross_factor_insights(maternal: dict, sdoh: dict) -> dict:
    """
    Cross-domain insights: exactly the liaison-layer synthesis the rule
    engine cannot produce. Mirrors `_compose_cross_factor_insights` in
    bench_reasoning_trace so the comparison stays apples-to-apples.
    """
    m_data = maternal.get("data", {}) if maternal.get("status") == "success" else {}
    s_data = sdoh.get("data", {}) if sdoh.get("status") == "success" else {}

    insights: list[str] = []
    priorities: list[str] = []

    risk_level = m_data.get("risk_level", "ROUTINE")
    risk_factors = m_data.get("risk_factors", [])
    has_severe_bp = any("Stage 2" in f or ">160" in f for f in risk_factors)
    has_any_bp = any("BP" in f or "hypertension" in f.lower() for f in risk_factors)
    has_diabetes = any("Diabetes" in f or ">6.5" in f or "HbA1c" in f for f in risk_factors)

    has_housing = any(
        "housing" in (c.get("condition") or "").lower()
        for c in s_data.get("sdoh_conditions", [])
    )
    has_language_barrier = bool(s_data.get("language")) and s_data[
        "language"
    ].lower() not in ("english", "en")
    has_coverage_gap = len(s_data.get("coverage", [])) == 0

    if has_severe_bp and has_coverage_gap:
        insights.append(
            "Severe hypertension co-occurs with a coverage gap: antihypertensive "
            "access is at risk. Treat as an urgent continuity-of-care issue, "
            "not just a medication adjustment."
        )
        priorities.append("urgent_coverage_bridge")

    if (has_severe_bp or has_any_bp) and has_language_barrier:
        insights.append(
            "Postpartum BP teaching must be delivered in the patient's "
            "preferred language; English-only discharge instructions are a "
            "known driver of postpartum readmission."
        )
        priorities.append("spanish_bp_education")

    if has_diabetes and has_housing:
        insights.append(
            "Diabetes management is incompatible with unstable housing "
            "(refrigeration for insulin, consistent meal timing). SDOH team "
            "should be looped in before any glycemic medication change."
        )
        priorities.append("housing_before_glycemic_plan")

    if (has_severe_bp or has_any_bp) and has_diabetes:
        insights.append(
            "Overlap of postpartum hypertension and diabetes-range HbA1c "
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


# -- Advantage diff ------------------------------------------------------------


def _synthesis_advantage(baseline: dict, synthesis: dict) -> dict:
    """Structured per-case AI Factor lift diff."""
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
        "baseline_flags": list(baseline.get("flags", [])),
        "synthesis_risk_level": maternal.get("data", {}).get("risk_level"),
        "synthesis_risk_factor_count": len(
            maternal.get("data", {}).get("risk_factors", [])
        ),
        "synthesis_evidence_ref_count": len(evidence_refs),
        "synthesis_has_clinician_reason": bool(m_review.get("reason"))
        or bool(s_review.get("reason")),
        "synthesis_has_recommendation": bool(m_review.get("recommendation"))
        or bool(s_review.get("recommendation")),
        "synthesis_has_confidence": "confidence" in m_review,
        "synthesis_has_language_context": bool(sdoh.get("data", {}).get("language")),
        "synthesis_has_coverage_context": "coverage" in sdoh.get("data", {}),
        "synthesis_cross_factor_insight_count": len(
            cross.get("clinical_sdoh_interactions", [])
        ),
        "synthesis_cross_factor_priorities": cross.get("recommended_priorities", []),
    }
    affordance_keys = [
        "synthesis_risk_level",
        "synthesis_has_clinician_reason",
        "synthesis_has_recommendation",
        "synthesis_has_confidence",
        "synthesis_has_language_context",
        "synthesis_has_coverage_context",
    ]
    advantages["affordances_added_by_synthesis"] = sum(
        1 for k in affordance_keys if advantages.get(k)
    )
    advantages["evidence_multiplier"] = len(evidence_refs) / max(
        1, advantages["baseline_flag_count"]
    )
    return advantages


# -- Table build + render ------------------------------------------------------


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
JSON_FIXTURE_PATH = FIXTURE_DIR / "baseline_comparison_table.json"
MD_FIXTURE_PATH = FIXTURE_DIR / "baseline_comparison_table.md"


def _build_case_record(case: CaseFixture) -> dict:
    baseline = rule_engine_baseline(case)
    synthesis = mamaguard_synthesis(case)
    advantage = _synthesis_advantage(baseline, synthesis)
    return {
        "case_id": case.case_id,
        "display_name": case.display_name,
        "tier": case.tier,
        "narrative": case.narrative,
        "rule_engine_baseline": baseline,
        "mamaguard_synthesis": {
            # Trim synthesis payload: we only need the liaison-facing slice,
            # not the full raw FHIR dump (which bench_reasoning_trace already
            # captures for the compound case).
            "maternal_risk_level": synthesis["maternal_profile"]
            .get("data", {})
            .get("risk_level"),
            "maternal_risk_factors": synthesis["maternal_profile"]
            .get("data", {})
            .get("risk_factors", []),
            "maternal_clinician_review": synthesis["maternal_profile"].get(
                "clinician_review", {}
            ),
            "sdoh_language": synthesis["sdoh_profile"].get("data", {}).get("language"),
            "sdoh_has_coverage": bool(
                synthesis["sdoh_profile"].get("data", {}).get("coverage")
            ),
            "sdoh_conditions": synthesis["sdoh_profile"]
            .get("data", {})
            .get("sdoh_conditions", []),
            "sdoh_clinician_review": synthesis["sdoh_profile"].get(
                "clinician_review", {}
            ),
            "cross_factor_insights": synthesis["cross_factor_insights"],
        },
        "synthesis_advantage": advantage,
    }


def _build_full_table() -> dict:
    records = [_build_case_record(c) for c in CASES]
    totals = {
        "cases": len(records),
        "total_baseline_flags": sum(
            r["synthesis_advantage"]["baseline_flag_count"] for r in records
        ),
        "total_synthesis_evidence_refs": sum(
            r["synthesis_advantage"]["synthesis_evidence_ref_count"] for r in records
        ),
        "total_cross_factor_insights": sum(
            r["synthesis_advantage"]["synthesis_cross_factor_insight_count"]
            for r in records
        ),
        "cases_at_urgent_or_high": sum(
            1
            for r in records
            if r["synthesis_advantage"]["synthesis_risk_level"] in ("URGENT", "HIGH")
        ),
    }
    return {
        "artefact": "baseline_comparison_table",
        "purpose": (
            "Side-by-side rule-engine vs. MamaGuard synthesis across mild / "
            "moderate / severe clinical cases. Evidence for the 'AI Factor' "
            "judging axis — shows the concrete affordances (compound risk "
            "level, evidence citation, cross-factor insight) that a non-AI "
            "rule engine cannot produce from the same FHIR inputs."
        ),
        "cases": records,
        "totals": totals,
    }


def _render_markdown(table: dict) -> str:
    """Render the comparison table as a committable markdown artefact."""
    lines: list[str] = []
    lines.append("# Baseline Comparison Table — Rule Engine vs. MamaGuard Synthesis")
    lines.append("")
    lines.append(
        "Auto-generated by `benchmarks/clinical_reasoning/bench_baseline_comparison.py`. "
        "Do not hand-edit — regenerate via "
        "`python3 -m benchmarks.clinical_reasoning.bench_baseline_comparison --regenerate-fixture`."
    )
    lines.append("")
    lines.append(table["purpose"])
    lines.append("")

    lines.append(
        "| Case | Tier | Rule-engine flags | Synthesis risk | Evidence refs | "
        "Cross-factor insights | Affordances added |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for rec in table["cases"]:
        adv = rec["synthesis_advantage"]
        flags_str = ", ".join(adv["baseline_flags"]) or "—"
        lines.append(
            "| {name} | {tier} | {flag_count} ({flags}) | {risk} | {ev} | {cf} | {aff}/6 |".format(
                name=rec["display_name"],
                tier=rec["tier"],
                flag_count=adv["baseline_flag_count"],
                flags=flags_str,
                risk=adv["synthesis_risk_level"] or "—",
                ev=adv["synthesis_evidence_ref_count"],
                cf=adv["synthesis_cross_factor_insight_count"],
                aff=adv["affordances_added_by_synthesis"],
            )
        )
    lines.append("")

    lines.append("## Totals")
    lines.append("")
    totals = table["totals"]
    lines.append(f"- Cases evaluated: **{totals['cases']}**")
    lines.append(
        f"- Rule-engine flags emitted across all cases: **{totals['total_baseline_flags']}**"
    )
    lines.append(
        f"- Synthesis FHIR evidence refs cited across all cases: **{totals['total_synthesis_evidence_refs']}**"
    )
    lines.append(
        f"- Cross-factor clinical×SDOH insights produced by synthesis: **{totals['total_cross_factor_insights']}**"
    )
    lines.append(
        f"- Cases elevated to URGENT/HIGH by synthesis: **{totals['cases_at_urgent_or_high']}**"
    )
    lines.append("")

    lines.append("## Per-case detail")
    for rec in table["cases"]:
        lines.append("")
        lines.append(f"### {rec['display_name']} (`{rec['case_id']}` — {rec['tier']})")
        lines.append("")
        lines.append(rec["narrative"])
        lines.append("")
        adv = rec["synthesis_advantage"]
        lines.append(
            f"- **Rule-engine baseline:** {adv['baseline_flag_count']} flat flag(s) — "
            f"{', '.join(adv['baseline_flags']) if adv['baseline_flags'] else '(none)'}"
        )
        lines.append(
            f"- **Synthesis risk level:** {adv['synthesis_risk_level'] or '(n/a)'}"
        )
        lines.append(
            f"- **Synthesis evidence refs:** {adv['synthesis_evidence_ref_count']}"
        )
        insights = rec["mamaguard_synthesis"]["cross_factor_insights"][
            "clinical_sdoh_interactions"
        ]
        if insights:
            lines.append("- **Cross-factor insights:**")
            for ins in insights:
                lines.append(f"  - {ins}")
        else:
            lines.append("- **Cross-factor insights:** (none — synthesis correctly stayed quiet)")
        priorities = rec["mamaguard_synthesis"]["cross_factor_insights"][
            "recommended_priorities"
        ]
        if priorities:
            lines.append(f"- **Recommended priorities:** {', '.join(priorities)}")
    lines.append("")
    return "\n".join(lines)


def _load_json_fixture() -> dict | None:
    if not JSON_FIXTURE_PATH.exists():
        return None
    try:
        return json.loads(JSON_FIXTURE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _regenerate_fixtures() -> None:
    table = _build_full_table()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    JSON_FIXTURE_PATH.write_text(json.dumps(table, indent=2, default=str) + "\n")
    MD_FIXTURE_PATH.write_text(_render_markdown(table) + "\n")
    print(f"Wrote JSON fixture: {JSON_FIXTURE_PATH}")
    print(f"Wrote markdown fixture: {MD_FIXTURE_PATH}")


# -- Benchmark cases -----------------------------------------------------------


@suite.case(
    "low_case_stays_routine",
    "Rule engine emits no flags; synthesis correctly stays at ROUTINE with no clinician review",
    "baseline_comparison",
)
def bench_low_case_stays_routine():
    case = _case_low()
    baseline = rule_engine_baseline(case)
    synthesis = mamaguard_synthesis(case)
    maternal = synthesis["maternal_profile"]
    sdoh = synthesis["sdoh_profile"]
    m_data = maternal["data"]
    s_data = sdoh["data"]
    cross = synthesis["cross_factor_insights"]

    checks = {
        "baseline_emits_no_flags": baseline["flags"] == [],
        "synthesis_risk_routine": m_data["risk_level"] == "ROUTINE",
        "synthesis_no_risk_factors": len(m_data["risk_factors"]) == 0,
        "maternal_clinician_review_not_required": maternal["clinician_review"][
            "required"
        ]
        is False,
        "sdoh_clinician_review_not_required": sdoh["clinician_review"]["required"]
        is False,
        "has_coverage": len(s_data.get("coverage", [])) > 0,
        "english_language": (s_data.get("language") or "").lower() in ("english", "en"),
        "no_cross_factor_noise": len(cross["clinical_sdoh_interactions"]) == 0,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="low_case_stays_routine",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case(
    "moderate_case_lifts_to_high",
    "Synthesis elevates moderate case above the rule-engine flat flags with cross-factor insight",
    "baseline_comparison",
)
def bench_moderate_case_lifts_to_high():
    case = _case_moderate()
    baseline = rule_engine_baseline(case)
    synthesis = mamaguard_synthesis(case)
    maternal = synthesis["maternal_profile"]
    sdoh = synthesis["sdoh_profile"]
    m_data = maternal["data"]
    s_data = sdoh["data"]
    cross = synthesis["cross_factor_insights"]

    checks = {
        "baseline_has_bp_flag": "HIGH_BP" in baseline["flags"],
        "baseline_has_diabetes_flag": "DIABETES" in baseline["flags"],
        "baseline_has_language_flag": "LANGUAGE_BARRIER" in baseline["flags"],
        "baseline_has_no_coverage_flag": "NO_COVERAGE" not in baseline["flags"],
        "synthesis_risk_elevated": m_data["risk_level"] in ("HIGH", "URGENT"),
        "synthesis_multi_factor": len(m_data["risk_factors"]) >= 2,
        "maternal_clinician_review_required": maternal["clinician_review"]["required"]
        is True,
        "spanish_detected": (s_data.get("language") or "").lower() == "spanish",
        "coverage_present": len(s_data.get("coverage", [])) > 0,
        "cross_factor_produced": len(cross["clinical_sdoh_interactions"]) >= 1,
        "extended_followup_priority": "extended_postpartum_followup"
        in cross["recommended_priorities"],
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="moderate_case_lifts_to_high",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case(
    "severe_case_produces_urgent_compound",
    "Severe compound case: URGENT risk + 3+ cross-factor insights + 3+ AI-Factor affordances",
    "baseline_comparison",
)
def bench_severe_case_produces_urgent_compound():
    case = _case_severe()
    baseline = rule_engine_baseline(case)
    synthesis = mamaguard_synthesis(case)
    advantage = _synthesis_advantage(baseline, synthesis)
    maternal = synthesis["maternal_profile"]
    sdoh = synthesis["sdoh_profile"]
    cross = synthesis["cross_factor_insights"]

    checks = {
        "baseline_has_five_flags": set(baseline["flags"])
        == {"HIGH_BP", "DIABETES", "HOUSING_ISSUE", "LANGUAGE_BARRIER", "NO_COVERAGE"},
        "synthesis_risk_urgent": maternal["data"]["risk_level"] == "URGENT",
        "synthesis_has_evidence_refs": advantage["synthesis_evidence_ref_count"] >= 3,
        "cross_factor_count_3_plus": len(cross["clinical_sdoh_interactions"]) >= 3,
        "affordances_added_6": advantage["affordances_added_by_synthesis"] == 6,
        "sdoh_clinician_review_required": sdoh["clinician_review"]["required"] is True,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="severe_case_produces_urgent_compound",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details={
            **checks,
            "evidence_refs": advantage["synthesis_evidence_ref_count"],
            "cross_factor_count": len(cross["clinical_sdoh_interactions"]),
        },
    )


@suite.case(
    "lift_monotonic_across_tiers",
    "Synthesis produces strictly more (or equal) affordances as case tier escalates low→moderate→severe",
    "baseline_comparison",
)
def bench_lift_monotonic_across_tiers():
    records = [_build_case_record(c) for c in CASES]
    tiers = [r["tier"] for r in records]
    risk_levels = [r["synthesis_advantage"]["synthesis_risk_level"] for r in records]
    cross_counts = [
        r["synthesis_advantage"]["synthesis_cross_factor_insight_count"] for r in records
    ]

    risk_order = {None: 0, "ROUTINE": 1, "MODERATE": 2, "HIGH": 3, "URGENT": 4}
    risk_monotonic = all(
        risk_order.get(risk_levels[i], 0) <= risk_order.get(risk_levels[i + 1], 0)
        for i in range(len(risk_levels) - 1)
    )
    cross_monotonic = all(
        cross_counts[i] <= cross_counts[i + 1] for i in range(len(cross_counts) - 1)
    )

    checks = {
        "three_cases_ordered_low_moderate_severe": tiers == ["low", "moderate", "severe"],
        "risk_level_monotonic": risk_monotonic,
        "cross_factor_count_monotonic": cross_monotonic,
        "low_case_has_no_insights": cross_counts[0] == 0,
        "severe_case_has_most_insights": cross_counts[-1] == max(cross_counts),
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="lift_monotonic_across_tiers",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details={
            **checks,
            "risk_levels": risk_levels,
            "cross_factor_counts": cross_counts,
        },
    )


@suite.case(
    "baseline_comparison_fixture_current",
    "Committed baseline-comparison JSON + markdown fixtures match live synthesis output",
    "baseline_comparison",
)
def bench_baseline_comparison_fixture_current():
    live = _build_full_table()
    json_fixture = _load_json_fixture()
    md_current = MD_FIXTURE_PATH.read_text() if MD_FIXTURE_PATH.exists() else ""
    md_live = _render_markdown(live) + "\n"

    def _case_signature(rec: dict) -> dict:
        adv = rec["synthesis_advantage"]
        return {
            "case_id": rec["case_id"],
            "tier": rec["tier"],
            "baseline_flags": adv["baseline_flags"],
            "synthesis_risk_level": adv["synthesis_risk_level"],
            "synthesis_evidence_ref_count": adv["synthesis_evidence_ref_count"],
            "synthesis_cross_factor_insight_count": adv[
                "synthesis_cross_factor_insight_count"
            ],
            "affordances_added_by_synthesis": adv["affordances_added_by_synthesis"],
        }

    live_sigs = [_case_signature(r) for r in live["cases"]]
    fixture_sigs = (
        [_case_signature(r) for r in json_fixture["cases"]] if json_fixture else []
    )

    checks = {
        "json_fixture_exists": json_fixture is not None,
        "md_fixture_exists": MD_FIXTURE_PATH.exists(),
        "case_count_matches": bool(json_fixture)
        and len(json_fixture.get("cases", [])) == len(live["cases"]),
        "case_signatures_match": live_sigs == fixture_sigs,
        "md_matches_live_render": md_current == md_live,
        "totals_match": bool(json_fixture)
        and json_fixture.get("totals") == live["totals"],
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="baseline_comparison_fixture_current",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details={
            **checks,
            "json_fixture_path": str(JSON_FIXTURE_PATH),
            "md_fixture_path": str(MD_FIXTURE_PATH),
            "hint": (
                "If this fails, the synthesis layer, rule engine, mocked FHIR "
                "fixtures, or markdown renderer changed — regenerate with "
                "`python3 -m benchmarks.clinical_reasoning.bench_baseline_comparison "
                "--regenerate-fixture`."
            ),
        },
    )


# -- CLI: regenerate the fixtures ---------------------------------------------


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Baseline comparison table benchmark (Phase 3)"
    )
    parser.add_argument(
        "--regenerate-fixture",
        action="store_true",
        help="Rewrite the committed JSON + markdown fixtures from live synthesis output",
    )
    args = parser.parse_args()
    if args.regenerate_fixture:
        _regenerate_fixtures()
    else:
        print(
            "Run via `python3 -m benchmarks.runner --suite baseline_comparison` "
            "to execute the benchmark cases."
        )
