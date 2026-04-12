"""Unit tests for FHIR write-back tools."""

import unittest
from unittest.mock import patch, MagicMock

import httpx


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="p1"):
        self.state = {"fhir_url": fhir_url, "fhir_token": fhir_token, "patient_id": patient_id}


class TestWriteRiskAssessment(unittest.TestCase):
    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_successful_write(self, mock_post):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        mock_post.return_value = {"resourceType": "RiskAssessment", "id": "ra-123"}

        result = write_risk_assessment(
            risk_type="postpartum-hypertensive-crisis",
            probability=0.75,
            basis="BP 170/98 on 2019-10-16, history of 6 pregnancies with 5 losses",
            mitigation="Immediate BP review, consider labetalol",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resource_id"], "ra-123")
        self.assertEqual(result["resource_type"], "RiskAssessment")
        self.assertEqual(result["risk_type"], "postpartum-hypertensive-crisis")

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_write_rejected_by_server(self, mock_post):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        response = MagicMock()
        response.status_code = 405
        response.text = "Method Not Allowed"
        mock_post.side_effect = httpx.HTTPStatusError("", request=MagicMock(), response=response)

        result = write_risk_assessment(
            risk_type="test", probability=0.5, basis="test", mitigation="test",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 405)
        self.assertIn("read-only", result["error_message"])

    def test_missing_context(self):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        ctx = MockToolContext(fhir_url="", fhir_token="", patient_id="")
        result = write_risk_assessment(
            risk_type="test", probability=0.5, basis="test", mitigation="test",
            tool_context=ctx,
        )
        self.assertEqual(result["status"], "error")


class TestCreateCommunicationRequest(unittest.TestCase):
    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_successful_create(self, mock_post):
        from mamaguard.shared.tools.writeback import create_communication_request

        mock_post.return_value = {"resourceType": "CommunicationRequest", "id": "cr-456"}

        result = create_communication_request(
            medium="phone",
            content="Schedule postpartum follow-up visit within 7 days",
            priority="urgent",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resource_id"], "cr-456")
        self.assertEqual(result["medium"], "phone")
        self.assertEqual(result["priority"], "urgent")

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_write_rejected(self, mock_post):
        from mamaguard.shared.tools.writeback import create_communication_request

        response = MagicMock()
        response.status_code = 403
        response.text = "Forbidden"
        mock_post.side_effect = httpx.HTTPStatusError("", request=MagicMock(), response=response)

        result = create_communication_request(
            medium="email", content="test", tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 403)


class TestWriteCarePlan(unittest.TestCase):
    """SDOH write_care_plan -- linked Goal + CarePlan (Phase 2c)."""

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_successful_create_goal_then_care_plan(self, mock_post):
        from mamaguard.shared.tools.writeback import write_care_plan

        def side_effect(fhir_url, token, resource_type, body):
            if resource_type == "Goal":
                return {"resourceType": "Goal", "id": "goal-1"}
            if resource_type == "CarePlan":
                return {"resourceType": "CarePlan", "id": "cp-1"}
            raise AssertionError(f"unexpected post {resource_type}")

        mock_post.side_effect = side_effect

        result = write_care_plan(
            category="housing",
            goal_description="Secure emergency shelter placement within 7 days",
            resource_name="211 Helpline",
            resource_contact="Dial 211",
            resource_url="https://www.211.org",
            z_code="Z59.0",
            tool_context=MockToolContext(),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["care_plan_id"], "cp-1")
        self.assertEqual(result["goal_id"], "goal-1")
        self.assertEqual(result["category"], "housing")
        self.assertEqual(result["resource_name"], "211 Helpline")
        # Two POSTs: Goal then CarePlan
        self.assertEqual(mock_post.call_count, 2)
        posted_types = [call.args[2] for call in mock_post.call_args_list]
        self.assertEqual(posted_types, ["Goal", "CarePlan"])
        # CarePlan body must reference the created Goal
        care_plan_body = mock_post.call_args_list[1].args[3]
        self.assertIn("goal", care_plan_body)
        self.assertEqual(care_plan_body["goal"][0]["reference"], "Goal/goal-1")
        # Activity detail carries contact so a navigator can dial it
        activity_text = care_plan_body["activity"][0]["detail"]["description"]
        self.assertIn("Dial 211", activity_text)
        self.assertIn("211.org", activity_text)
        # Goal body carries the Z-code for terminology binding
        goal_body = mock_post.call_args_list[0].args[3]
        self.assertEqual(
            goal_body["addresses"][0]["identifier"]["value"], "Z59.0"
        )

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_goal_write_rejected_by_server(self, mock_post):
        from mamaguard.shared.tools.writeback import write_care_plan

        response = MagicMock()
        response.status_code = 405
        response.text = "Method Not Allowed"
        mock_post.side_effect = httpx.HTTPStatusError("", request=MagicMock(), response=response)

        result = write_care_plan(
            category="housing",
            goal_description="test",
            resource_name="211",
            resource_contact="Dial 211",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["resource_type"], "Goal")
        self.assertEqual(result["http_status"], 405)
        self.assertEqual(mock_post.call_count, 1)

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_goal_created_but_care_plan_rejected_returns_partial(self, mock_post):
        from mamaguard.shared.tools.writeback import write_care_plan

        def side_effect(fhir_url, token, resource_type, body):
            if resource_type == "Goal":
                return {"resourceType": "Goal", "id": "goal-7"}
            response = MagicMock()
            response.status_code = 403
            response.text = "Forbidden"
            raise httpx.HTTPStatusError("", request=MagicMock(), response=response)

        mock_post.side_effect = side_effect

        result = write_care_plan(
            category="food",
            goal_description="Enroll in WIC",
            resource_name="WIC",
            resource_contact="1-800-942-3678",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["goal_id"], "goal-7")
        self.assertTrue(result["goal_created"])
        self.assertEqual(result["http_status"], 403)
        self.assertEqual(result["resource_type"], "CarePlan")

    def test_missing_context(self):
        from mamaguard.shared.tools.writeback import write_care_plan

        ctx = MockToolContext(fhir_url="", fhir_token="", patient_id="")
        result = write_care_plan(
            category="housing",
            goal_description="test",
            resource_name="211",
            resource_contact="Dial 211",
            tool_context=ctx,
        )
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
