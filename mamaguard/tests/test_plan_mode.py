"""Unit tests for plan/commit split (Phase 3)."""

import unittest
from unittest.mock import MagicMock, patch

from mamaguard.shared.tools import plan_mode


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="p-1"):
        self.state = {
            "fhir_url": fhir_url,
            "fhir_token": fhir_token,
            "patient_id": patient_id,
        }


def _reset_plan_store() -> None:
    """Clear the process-level plan store between tests so cross-test state
    doesn't leak (the store now lives at module scope so commit_pending_write
    can find plans across sessions/PO chat threads)."""
    plan_mode._PROCESS_PLAN_STORE.clear()


def _post_ok(fhir_url, token, resource_type, body):
    return {"id": f"{resource_type.lower()}-123", "resourceType": resource_type}


class TestPlanRiskAssessment(unittest.TestCase):
    def setUp(self):
        _reset_plan_store()

    def test_plan_stores_bundle_and_requires_approval_for_urgent(self):
        from mamaguard.shared.tools.plan_mode import plan_risk_assessment

        ctx = MockToolContext()
        result = plan_risk_assessment(
            risk_type="postpartum-hypertensive-crisis",
            probability=0.8,
            basis="BP 162/104 on 2026-04-01",
            mitigation="Urgent clinician review",
            risk_level="URGENT",
            tool_context=ctx,
        )
        self.assertEqual(result["status"], "planned")
        self.assertTrue(result["requires_approval"])
        self.assertEqual(result["resource_type"], "RiskAssessment")
        self.assertIn("plan_id", result)
        self.assertIn("bundle", result)
        self.assertEqual(result["bundle"]["resourceType"], "RiskAssessment")
        # Plan should be stored in session state for later commit
        self.assertIn(result["plan_id"], plan_mode._PROCESS_PLAN_STORE)

    def test_plan_routine_does_not_require_approval(self):
        from mamaguard.shared.tools.plan_mode import plan_risk_assessment

        result = plan_risk_assessment(
            risk_type="routine-followup",
            probability=0.1,
            basis="baseline",
            mitigation="standard",
            risk_level="ROUTINE",
            tool_context=MockToolContext(),
        )
        self.assertFalse(result["requires_approval"])

    def test_plan_validates_probability(self):
        from mamaguard.shared.tools.plan_mode import plan_risk_assessment

        result = plan_risk_assessment(
            risk_type="crisis", probability=1.5, basis="b", mitigation="m",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")


class TestCommitPendingWrite(unittest.TestCase):
    def setUp(self):
        _reset_plan_store()

    @patch("mamaguard.shared.tools.plan_mode._post_resource")
    def test_commit_approved_posts_resource(self, mock_post):
        from mamaguard.shared.tools.plan_mode import commit_pending_write, plan_risk_assessment

        mock_post.return_value = (
            {"status": "success", "action": "created", "resource_type": "RiskAssessment",
             "resource_id": "ra-42", "patient_id": "p-1"},
            None,
        )
        ctx = MockToolContext()
        plan = plan_risk_assessment(
            risk_type="x", probability=0.7, basis="b", mitigation="m",
            risk_level="HIGH", tool_context=ctx,
        )
        result = commit_pending_write(plan["plan_id"], approved=True, approver="Dr. Kim", tool_context=ctx)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resource_id"], "ra-42")
        self.assertEqual(result["approver"], "Dr. Kim")
        self.assertTrue(result["committed_from_plan"])
        mock_post.assert_called_once()
        # Plan status updated in store
        self.assertEqual(plan_mode._PROCESS_PLAN_STORE[plan["plan_id"]]["status"], "committed")

    @patch("mamaguard.shared.tools.plan_mode._post_resource")
    def test_commit_denied_does_not_post(self, mock_post):
        from mamaguard.shared.tools.plan_mode import commit_pending_write, plan_risk_assessment

        ctx = MockToolContext()
        plan = plan_risk_assessment(
            risk_type="x", probability=0.9, basis="b", mitigation="m",
            risk_level="URGENT", tool_context=ctx,
        )
        result = commit_pending_write(plan["plan_id"], approved=False, tool_context=ctx)
        self.assertEqual(result["status"], "denied")
        mock_post.assert_not_called()
        self.assertEqual(plan_mode._PROCESS_PLAN_STORE[plan["plan_id"]]["status"], "denied")

    def test_commit_unknown_plan_id(self):
        from mamaguard.shared.tools.plan_mode import commit_pending_write

        result = commit_pending_write("does-not-exist", tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")
        self.assertIn("No pending plan", result["error_message"])

    @patch("mamaguard.shared.tools.plan_mode._post_resource")
    def test_cannot_recommit_committed_plan(self, mock_post):
        from mamaguard.shared.tools.plan_mode import commit_pending_write, plan_risk_assessment

        mock_post.return_value = (
            {"status": "success", "action": "created", "resource_type": "RiskAssessment",
             "resource_id": "ra-1", "patient_id": "p-1"},
            None,
        )
        ctx = MockToolContext()
        plan = plan_risk_assessment(
            risk_type="x", probability=0.8, basis="b", mitigation="m",
            risk_level="HIGH", tool_context=ctx,
        )
        commit_pending_write(plan["plan_id"], approved=True, tool_context=ctx)
        second = commit_pending_write(plan["plan_id"], approved=True, tool_context=ctx)
        self.assertEqual(second["status"], "error")
        self.assertIn("already committed", second["error_message"])


class TestPlanCarePlan(unittest.TestCase):
    def setUp(self):
        _reset_plan_store()

    @patch("mamaguard.shared.tools.plan_mode._post_resource")
    def test_care_plan_bundle_posts_goal_then_care_plan_with_real_ref(self, mock_post):
        from mamaguard.shared.tools.plan_mode import commit_pending_write, plan_care_plan

        posts = []
        def side_effect(fhir_url, token, resource_type, body, patient_id):
            posts.append((resource_type, body))
            rid = "goal-1" if resource_type == "Goal" else "cp-1"
            return (
                {"status": "success", "action": "created", "resource_type": resource_type,
                 "resource_id": rid, "patient_id": patient_id},
                None,
            )
        mock_post.side_effect = side_effect

        ctx = MockToolContext()
        plan = plan_care_plan(
            category="housing",
            goal_description="Secure emergency shelter within 7 days",
            resource_name="211 Helpline",
            resource_contact="Dial 211",
            z_code="Z59.00",
            risk_level="HIGH",
            tool_context=ctx,
        )
        self.assertTrue(plan["requires_approval"])
        # CarePlan bundle carries a placeholder until commit rewrites it
        self.assertEqual(plan["care_plan_bundle"]["goal"][0]["reference"],
                         "Goal/__PLAN_PLACEHOLDER__")

        result = commit_pending_write(plan["plan_id"], approved=True, approver="navigator",
                                      tool_context=ctx)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["goal_id"], "goal-1")
        self.assertEqual(result["care_plan_id"], "cp-1")
        # CarePlan POST should reference the real Goal id, not the placeholder
        cp_body = next(body for rtype, body in posts if rtype == "CarePlan")
        self.assertEqual(cp_body["goal"][0]["reference"], "Goal/goal-1")


class TestListPendingWrites(unittest.TestCase):
    def setUp(self):
        _reset_plan_store()

    def test_lists_pending_and_committed_separately(self):
        from mamaguard.shared.tools.plan_mode import (
            commit_pending_write, list_pending_writes, plan_risk_assessment,
        )

        ctx = MockToolContext()
        p1 = plan_risk_assessment(
            risk_type="a", probability=0.8, basis="b", mitigation="m",
            risk_level="HIGH", tool_context=ctx,
        )
        plan_risk_assessment(
            risk_type="b", probability=0.3, basis="b", mitigation="m",
            risk_level="ROUTINE", tool_context=ctx,
        )
        # Deny p1 so it lands in history, not pending
        commit_pending_write(p1["plan_id"], approved=False, tool_context=ctx)

        result = list_pending_writes(tool_context=ctx)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["pending"]), 1)
        self.assertEqual(len(result["history"]), 1)
        self.assertEqual(result["history"][0]["status"], "denied")


if __name__ == "__main__":
    unittest.main()
