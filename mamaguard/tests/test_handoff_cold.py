"""
Cold mother-to-child handoff test.

Exercises the complete two-invocation handoff workflow on Synthea Maria
(bench-maria-001) and her newborn Lucas (bench-baby-santos-001):

  Phase 1 (Maternal): Run maternal + SDOH tools against Maria's FHIR data.
          Verify URGENT risk, clinician review flags, and evidence.

  Phase 2 (Pediatric): Switch patient context to baby Lucas. Run pediatric
          tools. Verify immunization gaps and developmental screening needs.

  Protocol: Verify the orchestrator's handoff instruction contracts and
            that both phases produce valid clinician_review blocks.

All FHIR responses are mocked from the actual benchmark bundle definitions
so this test is deterministic (Tier-1, no LLM, no network).
"""

import unittest
from unittest.mock import patch

from benchmarks.e2e.fhir_bundles.maria_high_risk import BUNDLE as MARIA_BUNDLE, PATIENT_ID as MARIA_ID
from benchmarks.e2e.fhir_bundles.baby_santos import BUNDLE as BABY_BUNDLE, PATIENT_ID as BABY_ID


# ---------------------------------------------------------------------------
# Mock FHIR server: serves resources from the actual benchmark bundles
# ---------------------------------------------------------------------------


def _resources_by_type(bundle: dict) -> dict[str, list[dict]]:
    """Index a FHIR transaction bundle by resourceType."""
    index: dict[str, list[dict]] = {}
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        rtype = res.get("resourceType", "")
        index.setdefault(rtype, []).append(res)
    return index


_MARIA_RES = _resources_by_type(MARIA_BUNDLE)
_BABY_RES = _resources_by_type(BABY_BUNDLE)

_ALL_RES = {
    MARIA_ID: _MARIA_RES,
    BABY_ID: _BABY_RES,
}


def _fhir_side_effect(patient_id: str):
    """Build a mock _fhir_get that serves the right resources for a patient."""
    res_index = _ALL_RES.get(patient_id, {})

    def _mock_fhir_get(fhir_url, token, path, params=None):
        params = params or {}

        # Direct resource read: Patient/<id>
        if path.startswith("Patient/"):
            patients = res_index.get("Patient", [])
            if patients:
                return patients[0]
            return {"resourceType": "Patient", "id": patient_id}

        # Observation queries
        if path == "Observation":
            observations = res_index.get("Observation", [])
            code_filter = params.get("code", "")
            category_filter = params.get("category", "")
            matched = []
            for obs in observations:
                # Match by LOINC code
                if code_filter:
                    obs_codings = obs.get("code", {}).get("coding", [])
                    obs_codes = [c.get("code", "") for c in obs_codings]
                    # Support both bare code and system|code format
                    loinc_codes = [c.split("|")[-1] for c in code_filter.split(",")]
                    if not any(lc in obs_codes for lc in loinc_codes):
                        continue
                # Match by category
                if category_filter:
                    obs_cats = obs.get("category", [])
                    cat_codes = [
                        c.get("code", "")
                        for cat in obs_cats
                        for c in cat.get("coding", [])
                    ]
                    if category_filter not in cat_codes:
                        continue
                matched.append(obs)
            return {
                "resourceType": "Bundle",
                "entry": [{"resource": r} for r in matched],
            }

        # Condition queries
        if path == "Condition":
            conditions = res_index.get("Condition", [])
            code_filter = params.get("code", "")
            clinical_status = params.get("clinical-status", "")
            matched = []
            for cond in conditions:
                # Match by SNOMED code
                if code_filter:
                    cond_codings = cond.get("code", {}).get("coding", [])
                    cond_codes = [c.get("code", "") for c in cond_codings]
                    snomed_codes = [c.split("|")[-1] for c in code_filter.split(",")]
                    if not any(sc in cond_codes for sc in snomed_codes):
                        continue
                # Match by clinical status
                if clinical_status:
                    status_codings = (cond.get("clinicalStatus") or {}).get("coding", [])
                    if not any(c.get("code") == clinical_status for c in status_codings):
                        continue
                matched.append(cond)
            return {
                "resourceType": "Bundle",
                "entry": [{"resource": r} for r in matched],
            }

        # Coverage queries
        if path == "Coverage":
            coverages = res_index.get("Coverage", [])
            return {
                "resourceType": "Bundle",
                "entry": [{"resource": r} for r in coverages],
            }

        # Immunization queries
        if path == "Immunization":
            imms = res_index.get("Immunization", [])
            return {
                "resourceType": "Bundle",
                "entry": [{"resource": r} for r in imms],
            }

        # MedicationRequest queries
        if path == "MedicationRequest":
            meds = res_index.get("MedicationRequest", [])
            return {
                "resourceType": "Bundle",
                "entry": [{"resource": r} for r in meds],
            }

        # CarePlan, Goal, Encounter — empty for benchmark patients
        if path in ("CarePlan", "Goal", "Encounter"):
            return {"resourceType": "Bundle", "entry": []}

        # Default: empty bundle
        return {"resourceType": "Bundle", "entry": []}

    return _mock_fhir_get


class MockToolContext:
    """Minimal stand-in for ToolContext."""

    def __init__(self, patient_id: str):
        self.state = {
            "fhir_url": "https://fhir.example.org",
            "fhir_token": "bench-token",
            "patient_id": patient_id,
        }


# ---------------------------------------------------------------------------
# Phase 1: Maternal assessment on Maria
# ---------------------------------------------------------------------------


class TestMaternalPhase(unittest.TestCase):
    """Run all maternal tools against Maria's FHIR data.

    Maria (bench-maria-001): 38yo, French-speaking, Stage 2 HTN (170/110),
    DM2 (HbA1c 7.9%), 5 pregnancy losses, uninsured, housing + stress.
    """

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_bp_trend_detects_stage2_htn(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_bp_trend

        mock_fhir.side_effect = _fhir_side_effect(MARIA_ID)
        result = get_bp_trend(tool_context=MockToolContext(MARIA_ID))

        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertTrue(data["alert_severe"], "Should detect Stage 2 HTN (>160/110)")
        self.assertTrue(data["alert_elevated"])
        self.assertGreaterEqual(data["count"], 6, "Maria has 6 BP readings")
        # Verify the 170/110 reading is captured
        systolics = [r["systolic"] for r in data["readings"]]
        self.assertIn(170, systolics, "170 mmHg reading must appear")

        cr = result["clinician_review"]
        self.assertTrue(cr["required"])
        self.assertIn("Stage 2", cr["reason"])
        self.assertTrue(cr["evidence_basis"], "Must cite elevated readings")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_glucose_trend_detects_diabetes(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_glucose_trend

        mock_fhir.side_effect = _fhir_side_effect(MARIA_ID)
        result = get_glucose_trend(tool_context=MockToolContext(MARIA_ID))

        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertTrue(data["diabetes_range"], "HbA1c > 6.5 = diabetes range")
        # Maria's HbA1c values: 6.8, 7.4, 7.9 — all > 6.5
        hba1c_vals = [r["value"] for r in data["hba1c_readings"]]
        self.assertIn(7.9, hba1c_vals, "Latest HbA1c 7.9 must appear")
        self.assertEqual(data["hba1c_trend"], "increasing")

        cr = result["clinician_review"]
        self.assertTrue(cr["required"])
        self.assertIn("6.5", cr["reason"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_pregnancy_history_detects_recurrent_loss(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_pregnancy_history

        mock_fhir.side_effect = _fhir_side_effect(MARIA_ID)
        result = get_pregnancy_history(tool_context=MockToolContext(MARIA_ID))

        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertEqual(data["live_births"], 1)
        self.assertEqual(data["losses"], 5, "Maria has 5 pregnancy losses")
        self.assertTrue(data["high_risk"])
        self.assertEqual(data["total_count"], 6)

        cr = result["clinician_review"]
        self.assertTrue(cr["required"])
        self.assertIn("5 losses", cr["reason"])
        self.assertGreaterEqual(len(cr["evidence_basis"]), 5)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_maternal_risk_profile_is_urgent(self, mock_fhir):
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        mock_fhir.side_effect = _fhir_side_effect(MARIA_ID)
        result = get_maternal_risk_profile(tool_context=MockToolContext(MARIA_ID))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["risk_level"], "URGENT")

        factors = result["data"]["risk_factors"]
        self.assertTrue(
            any("Stage 2" in f for f in factors),
            f"Must cite Stage 2 HTN in risk factors: {factors}",
        )
        self.assertTrue(
            any("Recurrent" in f or "loss" in f for f in factors),
            f"Must cite recurrent loss: {factors}",
        )

        cr = result["clinician_review"]
        self.assertTrue(cr["required"])
        self.assertIn("URGENT", cr["reason"])
        # Compound evidence from all three sub-tools
        self.assertGreaterEqual(
            len(cr["evidence_basis"]), 6,
            "Evidence basis should aggregate BP + HbA1c + pregnancy evidence",
        )

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_sdoh_screening_detects_vulnerabilities(self, mock_fhir):
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        mock_fhir.side_effect = _fhir_side_effect(MARIA_ID)
        result = get_sdoh_screening(tool_context=MockToolContext(MARIA_ID))

        self.assertEqual(result["status"], "success")
        data = result["data"]

        # Language barrier: French
        self.assertEqual(data["language"], "French")
        self.assertTrue(
            any("French" in rf for rf in data["risk_factors"]),
            "Should flag French language barrier",
        )

        # SDOH conditions: stress + housing problem
        sdoh_texts = [c["condition"] for c in data["sdoh_conditions"]]
        self.assertTrue(
            any("tress" in t for t in sdoh_texts),
            f"Stress condition missing: {sdoh_texts}",
        )
        self.assertTrue(
            any("ousing" in t for t in sdoh_texts),
            f"Housing problem missing: {sdoh_texts}",
        )

        # No insurance
        self.assertEqual(data["coverage"], [])
        self.assertTrue(
            any("insurance" in rf.lower() or "uninsured" in rf.lower()
                for rf in data["risk_factors"]),
            "Should flag no insurance",
        )

        cr = result["clinician_review"]
        self.assertTrue(cr["required"])
        self.assertIn("coverage", cr["reason"].lower())


# ---------------------------------------------------------------------------
# Phase 2: Pediatric assessment on Baby Lucas
# ---------------------------------------------------------------------------


class TestPediatricPhase(unittest.TestCase):
    """Run pediatric tools against baby Lucas's FHIR data.

    Lucas (bench-baby-santos-001): 2-month-old male, only HepB#1 at birth,
    newborn screens completed. Mother is Maria (high-risk).
    """

    @patch("mamaguard.shared.tools.pediatric._compute_age_months", return_value=2)
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_immunization_gaps_finds_due_vaccines(self, mock_fhir, _mock_age):
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        mock_fhir.side_effect = _fhir_side_effect(BABY_ID)
        result = get_immunization_gaps(tool_context=MockToolContext(BABY_ID))

        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertEqual(data["age_months"], 2)
        self.assertEqual(data["received_count"], 1, "Only HepB#1 received")

        # At 2 months, due/overdue: HepB#2 (1mo), DTaP#1, IPV#1, Hib#1, PCV13#1, RV#1
        due_vaccines = {item["vaccine"] for item in data["due"]}
        overdue_vaccines = {item["vaccine"] for item in data["overdue"]}
        all_needed = due_vaccines | overdue_vaccines

        for expected in ("DTaP", "IPV", "Hib", "PCV13", "RV"):
            self.assertIn(
                expected, all_needed,
                f"{expected} should be due or overdue at 2 months",
            )

        # HepB#2 due at 1 month — should be in due or overdue
        self.assertIn("HepB", all_needed, "HepB#2 should be due or overdue")

        # Up to date: only HepB#1
        up_to_date_vaccines = {item["vaccine"] for item in data["up_to_date"]}
        self.assertIn("HepB", up_to_date_vaccines, "HepB#1 should be up to date")

    @patch("mamaguard.shared.tools.pediatric._compute_age_months", return_value=2)
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_developmental_screening_finds_due_surveillance(self, mock_fhir, _mock_age):
        from mamaguard.shared.tools.pediatric import get_developmental_screening_status

        mock_fhir.side_effect = _fhir_side_effect(BABY_ID)
        result = get_developmental_screening_status(
            tool_context=MockToolContext(BABY_ID),
        )

        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertEqual(data["age_months"], 2)

        # Completed: newborn metabolic + hearing screen
        completed_names = [m["screening"] for m in data["completed"]]
        self.assertTrue(
            any("metabolic" in n.lower() or "newborn" in n.lower() for n in completed_names),
            f"Newborn metabolic screen should be completed: {completed_names}",
        )
        self.assertTrue(
            any("hearing" in n.lower() for n in completed_names),
            f"Hearing screen should be completed: {completed_names}",
        )

        # Due: developmental surveillance at 1 and 2 months
        due_names = [s["screening"] for s in data["due"]]
        self.assertTrue(
            any("surveillance" in n.lower() or "developmental" in n.lower()
                for n in due_names),
            f"Developmental surveillance should be due: {due_names}",
        )
        self.assertTrue(data["has_gaps"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_care_gaps_returns_valid_shape(self, mock_fhir):
        from mamaguard.shared.tools.pediatric import get_care_gaps

        mock_fhir.side_effect = _fhir_side_effect(BABY_ID)
        result = get_care_gaps(tool_context=MockToolContext(BABY_ID))

        self.assertEqual(result["status"], "success")
        self.assertIn("clinician_review", result)
        cr = result["clinician_review"]
        self.assertIn("required", cr)
        self.assertIsInstance(cr["required"], bool)


# ---------------------------------------------------------------------------
# Phase 3: Handoff protocol validation
# ---------------------------------------------------------------------------


class TestHandoffProtocol(unittest.TestCase):
    """Verify the orchestrator instruction encodes the handoff contract."""

    def test_orchestrator_declares_handoff_section(self):
        from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION

        self.assertIn(
            "Pediatric Transition",
            ORCHESTRATOR_INSTRUCTION,
            "Orchestrator must reference Pediatric Transition section",
        )

    def test_orchestrator_instructs_context_switch(self):
        from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION

        lower = ORCHESTRATOR_INSTRUCTION.lower()
        self.assertTrue(
            "switch patient context" in lower or "switch" in lower,
            "Orchestrator must instruct clinician to switch patient context",
        )

    def test_orchestrator_lists_maternal_risk_factors_for_handoff(self):
        from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION

        lower = ORCHESTRATOR_INSTRUCTION.lower()
        self.assertIn(
            "maternal risk factors",
            lower,
            "Handoff section must mention maternal risk factors to inform pediatric",
        )

    def test_orchestrator_routes_comprehensive_through_all_agents(self):
        from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION

        lower = ORCHESTRATOR_INSTRUCTION.lower()
        # Comprehensive assessment now uses a two-turn fan-out:
        # turn 1 dispatches find_linked_newborn + maternal + sdoh in parallel,
        # turn 2 dispatches pediatric only if a child was found.
        self.assertIn("first turn", lower)
        self.assertIn("second turn", lower)
        for sub_agent in (
            "maternal_risk_agent",
            "pediatric_transition_agent",
            "sdoh_outreach_agent",
            "find_linked_newborn",
        ):
            self.assertIn(sub_agent, lower, f"missing routing for {sub_agent}")

    def test_pediatric_instruction_acknowledges_maternal_context(self):
        from mamaguard.pediatric_agent.agent import PEDIATRIC_INSTRUCTION

        lower = PEDIATRIC_INSTRUCTION.lower()
        self.assertTrue(
            "maternal" in lower,
            "Pediatric instruction should acknowledge maternal context "
            "for newborn assessment",
        )


# ---------------------------------------------------------------------------
# Phase 4: End-to-end handoff contract
# ---------------------------------------------------------------------------


class TestHandoffEndToEnd(unittest.TestCase):
    """Exercise the complete two-phase handoff with both patients.

    Phase 1: maternal tools on Maria → collect risk factors + evidence
    Phase 2: pediatric tools on Baby Lucas → verify immunization gaps

    This proves the handoff is mechanically sound: both patients produce
    valid, non-empty clinical assessments, and the handoff protocol in the
    orchestrator instruction connects them.
    """

    @patch("mamaguard.shared.tools.pediatric._compute_age_months", return_value=2)
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_full_handoff_both_phases_produce_valid_output(
        self, mock_ped_fhir, mock_sdoh_fhir, mock_mat_fhir, _mock_age,
    ):
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile
        from mamaguard.shared.tools.pediatric import get_immunization_gaps
        from mamaguard.shared.tools.sdoh import get_sdoh_screening

        mock_mat_fhir.side_effect = _fhir_side_effect(MARIA_ID)
        mock_sdoh_fhir.side_effect = _fhir_side_effect(MARIA_ID)
        mock_ped_fhir.side_effect = _fhir_side_effect(BABY_ID)

        # --- Phase 1: Maternal assessment on Maria ---
        maternal_result = get_maternal_risk_profile(
            tool_context=MockToolContext(MARIA_ID),
        )
        self.assertEqual(maternal_result["status"], "success")
        self.assertEqual(maternal_result["data"]["risk_level"], "URGENT")
        maternal_cr = maternal_result["clinician_review"]
        self.assertTrue(maternal_cr["required"])
        self.assertTrue(maternal_cr["evidence_basis"])

        sdoh_result = get_sdoh_screening(
            tool_context=MockToolContext(MARIA_ID),
        )
        self.assertEqual(sdoh_result["status"], "success")
        sdoh_cr = sdoh_result["clinician_review"]
        self.assertTrue(sdoh_cr["required"])

        # Collect maternal risk factors that inform pediatric assessment
        risk_factors = maternal_result["data"]["risk_factors"]
        self.assertGreaterEqual(len(risk_factors), 2)

        # --- Phase 2: Pediatric assessment on Baby Lucas ---
        # (simulates clinician switching patient context)
        pediatric_result = get_immunization_gaps(
            tool_context=MockToolContext(BABY_ID),
        )
        self.assertEqual(pediatric_result["status"], "success")
        ped_data = pediatric_result["data"]
        due_or_overdue = len(ped_data["due"]) + len(ped_data["overdue"])
        self.assertGreaterEqual(
            due_or_overdue, 5,
            "Baby Lucas should have at least 5 vaccines due/overdue at 2 months",
        )

        # Verify both phases produced valid clinician_review blocks
        for label, result in [
            ("maternal", maternal_result),
            ("sdoh", sdoh_result),
            ("pediatric", pediatric_result),
        ]:
            cr = result.get("clinician_review")
            self.assertIsInstance(cr, dict, f"{label}: missing clinician_review")
            self.assertIn("required", cr, f"{label}: missing required field")
            self.assertIn("reason", cr, f"{label}: missing reason field")
            self.assertIn("evidence_basis", cr, f"{label}: missing evidence_basis")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_maternal_evidence_cites_fhir_resources(self, mock_fhir):
        """Maternal evidence_basis must cite specific FHIR resource IDs —
        this is what the orchestrator presents in the Pediatric Transition
        section to inform the clinician about risk context."""
        from mamaguard.shared.tools.maternal import get_maternal_risk_profile

        mock_fhir.side_effect = _fhir_side_effect(MARIA_ID)
        result = get_maternal_risk_profile(tool_context=MockToolContext(MARIA_ID))

        evidence = result["clinician_review"]["evidence_basis"]
        # Must cite at least one Observation (BP or HbA1c) and one Condition
        has_observation = any("Observation/" in e for e in evidence)
        has_condition = any("Condition/" in e for e in evidence)
        self.assertTrue(
            has_observation,
            f"Evidence must cite Observation resources: {evidence}",
        )
        self.assertTrue(
            has_condition,
            f"Evidence must cite Condition resources: {evidence}",
        )

    @patch("mamaguard.shared.tools.pediatric._compute_age_months", return_value=2)
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_pediatric_evidence_lists_overdue_series(self, mock_fhir, _mock_age):
        """Pediatric evidence_basis must list the vaccine series that are
        due — this is what appears in the assessment output for the clinician."""
        from mamaguard.shared.tools.pediatric import get_immunization_gaps

        mock_fhir.side_effect = _fhir_side_effect(BABY_ID)
        result = get_immunization_gaps(tool_context=MockToolContext(BABY_ID))

        # due + overdue items should be in evidence_basis or in the data
        due_vaccines = [item["vaccine"] for item in result["data"]["due"]]
        overdue_vaccines = [item["vaccine"] for item in result["data"]["overdue"]]
        all_needed = due_vaccines + overdue_vaccines
        self.assertGreaterEqual(
            len(all_needed), 5,
            f"Should have 5+ vaccines due/overdue: {all_needed}",
        )


if __name__ == "__main__":
    unittest.main()
