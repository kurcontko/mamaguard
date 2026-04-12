"""Unit tests for FHIR write-back tools."""

import unittest
from unittest.mock import patch, MagicMock

import httpx


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="p1"):
        self.state = {"fhir_url": fhir_url, "fhir_token": fhir_token, "patient_id": patient_id}


class TestRiskAssessmentValidation(unittest.TestCase):
    """Validation checks for write_risk_assessment (pre-POST)."""

    def test_empty_risk_type_rejected(self):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        result = write_risk_assessment(
            risk_type="", probability=0.5, basis="evidence", mitigation="action",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("risk_type is required", result["error_message"])

    def test_probability_below_zero_rejected(self):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        result = write_risk_assessment(
            risk_type="test-risk", probability=-0.1, basis="evidence", mitigation="action",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("probability must be between", result["error_message"])

    def test_probability_above_one_rejected(self):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        result = write_risk_assessment(
            risk_type="test-risk", probability=1.5, basis="evidence", mitigation="action",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("probability must be between", result["error_message"])

    def test_empty_basis_rejected(self):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        result = write_risk_assessment(
            risk_type="test-risk", probability=0.5, basis="", mitigation="action",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("basis is required", result["error_message"])

    def test_empty_mitigation_rejected(self):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        result = write_risk_assessment(
            risk_type="test-risk", probability=0.5, basis="evidence", mitigation="",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("mitigation is required", result["error_message"])

    def test_multiple_errors_reported(self):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        result = write_risk_assessment(
            risk_type="", probability=2.0, basis="", mitigation="",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("risk_type is required", result["error_message"])
        self.assertIn("probability must be between", result["error_message"])
        self.assertIn("basis is required", result["error_message"])
        self.assertIn("mitigation is required", result["error_message"])

    def test_boundary_probability_zero_accepted(self):
        """probability=0.0 is valid (no risk)."""
        from mamaguard.shared.tools.writeback import _validate_risk_assessment

        self.assertIsNone(_validate_risk_assessment("risk", 0.0, "basis", "mitigation"))

    def test_boundary_probability_one_accepted(self):
        """probability=1.0 is valid (certain risk)."""
        from mamaguard.shared.tools.writeback import _validate_risk_assessment

        self.assertIsNone(_validate_risk_assessment("risk", 1.0, "basis", "mitigation"))


class TestCommunicationRequestValidation(unittest.TestCase):
    """Validation checks for create_communication_request (pre-POST)."""

    def test_empty_medium_rejected(self):
        from mamaguard.shared.tools.writeback import create_communication_request

        result = create_communication_request(
            medium="", content="Follow-up needed", priority="routine",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("medium is required", result["error_message"])

    def test_empty_content_rejected(self):
        from mamaguard.shared.tools.writeback import create_communication_request

        result = create_communication_request(
            medium="phone", content="", priority="routine",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("content is required", result["error_message"])

    def test_invalid_priority_rejected(self):
        from mamaguard.shared.tools.writeback import create_communication_request

        result = create_communication_request(
            medium="phone", content="test", priority="high",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("priority must be one of", result["error_message"])

    def test_valid_priorities_accepted(self):
        from mamaguard.shared.tools.writeback import _validate_communication_request

        for p in ("routine", "urgent", "asap", "stat"):
            self.assertIsNone(
                _validate_communication_request("phone", "content", p),
                f"priority={p!r} should be accepted",
            )


class TestCarePlanValidation(unittest.TestCase):
    """Validation checks for write_care_plan (pre-POST)."""

    def test_empty_category_rejected(self):
        from mamaguard.shared.tools.writeback import write_care_plan

        result = write_care_plan(
            category="", goal_description="goal", resource_name="R", resource_contact="C",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("category is required", result["error_message"])

    def test_empty_goal_description_rejected(self):
        from mamaguard.shared.tools.writeback import write_care_plan

        result = write_care_plan(
            category="housing", goal_description="", resource_name="R", resource_contact="C",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("goal_description is required", result["error_message"])

    def test_empty_resource_name_rejected(self):
        from mamaguard.shared.tools.writeback import write_care_plan

        result = write_care_plan(
            category="housing", goal_description="goal", resource_name="", resource_contact="C",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("resource_name is required", result["error_message"])

    def test_empty_resource_contact_rejected(self):
        from mamaguard.shared.tools.writeback import write_care_plan

        result = write_care_plan(
            category="housing", goal_description="goal", resource_name="R", resource_contact="",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("resource_contact is required", result["error_message"])

    def test_multiple_missing_fields_reported(self):
        from mamaguard.shared.tools.writeback import write_care_plan

        result = write_care_plan(
            category="", goal_description="", resource_name="", resource_contact="",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "validation_failed")
        self.assertIn("category is required", result["error_message"])
        self.assertIn("goal_description is required", result["error_message"])
        self.assertIn("resource_name is required", result["error_message"])
        self.assertIn("resource_contact is required", result["error_message"])


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

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_write_rejected_400_bad_request(self, mock_post):
        """A 4xx that isn't 405 should still surface http_status cleanly."""
        from mamaguard.shared.tools.writeback import write_risk_assessment

        response = MagicMock()
        response.status_code = 400
        response.text = "Bad Request"
        mock_post.side_effect = httpx.HTTPStatusError("", request=MagicMock(), response=response)

        result = write_risk_assessment(
            risk_type="test", probability=0.5, basis="test", mitigation="test",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "write_failed")
        self.assertEqual(result["resource_type"], "RiskAssessment")
        self.assertEqual(result["http_status"], 400)
        self.assertIn("400", result["error_message"])

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_write_rejected_500_server_error(self, mock_post):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        response = MagicMock()
        response.status_code = 500
        response.text = "Internal Server Error"
        mock_post.side_effect = httpx.HTTPStatusError("", request=MagicMock(), response=response)

        result = write_risk_assessment(
            risk_type="test", probability=0.5, basis="test", mitigation="test",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 500)
        self.assertEqual(result["resource_type"], "RiskAssessment")

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_network_error_connect(self, mock_post):
        """`except Exception` branch -- network unreachable."""
        from mamaguard.shared.tools.writeback import write_risk_assessment

        mock_post.side_effect = httpx.ConnectError("connection refused")

        result = write_risk_assessment(
            risk_type="test", probability=0.5, basis="test", mitigation="test",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "write_failed")
        self.assertEqual(result["resource_type"], "RiskAssessment")
        self.assertNotIn("http_status", result)
        self.assertIn("Could not reach FHIR server", result["error_message"])
        self.assertIn("connection refused", result["error_message"])

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_network_error_timeout(self, mock_post):
        from mamaguard.shared.tools.writeback import write_risk_assessment

        mock_post.side_effect = httpx.ReadTimeout("read timed out")

        result = write_risk_assessment(
            risk_type="test", probability=0.5, basis="test", mitigation="test",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["resource_type"], "RiskAssessment")
        self.assertNotIn("http_status", result)
        self.assertIn("Could not reach FHIR server", result["error_message"])


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

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_write_rejected_422_unprocessable(self, mock_post):
        from mamaguard.shared.tools.writeback import create_communication_request

        response = MagicMock()
        response.status_code = 422
        response.text = "Unprocessable Entity"
        mock_post.side_effect = httpx.HTTPStatusError("", request=MagicMock(), response=response)

        result = create_communication_request(
            medium="phone", content="test", tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "write_failed")
        self.assertEqual(result["resource_type"], "CommunicationRequest")
        self.assertEqual(result["http_status"], 422)
        self.assertIn("422", result["error_message"])

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_write_rejected_500_server_error(self, mock_post):
        from mamaguard.shared.tools.writeback import create_communication_request

        response = MagicMock()
        response.status_code = 500
        response.text = "Internal Server Error"
        mock_post.side_effect = httpx.HTTPStatusError("", request=MagicMock(), response=response)

        result = create_communication_request(
            medium="sms", content="test", tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 500)
        self.assertEqual(result["resource_type"], "CommunicationRequest")

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_network_error(self, mock_post):
        """`except Exception` branch -- network unreachable."""
        from mamaguard.shared.tools.writeback import create_communication_request

        mock_post.side_effect = httpx.ConnectError("name or service not known")

        result = create_communication_request(
            medium="phone", content="test", tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "write_failed")
        self.assertEqual(result["resource_type"], "CommunicationRequest")
        self.assertNotIn("http_status", result)
        self.assertIn("Could not reach FHIR server", result["error_message"])
        self.assertIn("name or service not known", result["error_message"])

    def test_missing_context(self):
        from mamaguard.shared.tools.writeback import create_communication_request

        ctx = MockToolContext(fhir_url="", fhir_token="", patient_id="")
        result = create_communication_request(
            medium="phone", content="test", tool_context=ctx,
        )
        self.assertEqual(result["status"], "error")


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

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_goal_rejected_500_server_error(self, mock_post):
        """5xx on the Goal POST short-circuits before CarePlan is attempted."""
        from mamaguard.shared.tools.writeback import write_care_plan

        response = MagicMock()
        response.status_code = 500
        response.text = "Internal Server Error"
        mock_post.side_effect = httpx.HTTPStatusError("", request=MagicMock(), response=response)

        result = write_care_plan(
            category="housing",
            goal_description="test",
            resource_name="211",
            resource_contact="Dial 211",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "write_failed")
        self.assertEqual(result["resource_type"], "Goal")
        self.assertEqual(result["http_status"], 500)
        # Only Goal attempted — CarePlan never posted.
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_post.call_args_list[0].args[2], "Goal")

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_goal_network_error(self, mock_post):
        """Network error on Goal POST → generic Exception branch, no http_status."""
        from mamaguard.shared.tools.writeback import write_care_plan

        mock_post.side_effect = httpx.ConnectError("connection refused")

        result = write_care_plan(
            category="housing",
            goal_description="test",
            resource_name="211",
            resource_contact="Dial 211",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["action"], "write_failed")
        self.assertEqual(result["resource_type"], "Goal")
        self.assertNotIn("http_status", result)
        self.assertIn("Could not reach FHIR server", result["error_message"])
        self.assertIn("connection refused", result["error_message"])
        self.assertEqual(mock_post.call_count, 1)

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_care_plan_rejected_500_returns_partial(self, mock_post):
        """Goal succeeds, CarePlan hits 5xx → partial with goal_id preserved."""
        from mamaguard.shared.tools.writeback import write_care_plan

        def side_effect(fhir_url, token, resource_type, body):
            if resource_type == "Goal":
                return {"resourceType": "Goal", "id": "goal-9"}
            response = MagicMock()
            response.status_code = 500
            response.text = "Internal Server Error"
            raise httpx.HTTPStatusError("", request=MagicMock(), response=response)

        mock_post.side_effect = side_effect

        result = write_care_plan(
            category="transportation",
            goal_description="Schedule non-emergency medical transport",
            resource_name="Local NEMT",
            resource_contact="1-555-0100",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["action"], "care_plan_write_failed")
        self.assertEqual(result["resource_type"], "CarePlan")
        self.assertEqual(result["http_status"], 500)
        self.assertEqual(result["goal_id"], "goal-9")
        self.assertTrue(result["goal_created"])
        self.assertEqual(mock_post.call_count, 2)

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_care_plan_network_error_returns_partial(self, mock_post):
        """Goal succeeds, CarePlan hits network error → partial, no http_status."""
        from mamaguard.shared.tools.writeback import write_care_plan

        def side_effect(fhir_url, token, resource_type, body):
            if resource_type == "Goal":
                return {"resourceType": "Goal", "id": "goal-12"}
            raise httpx.ReadTimeout("read timed out")

        mock_post.side_effect = side_effect

        result = write_care_plan(
            category="food",
            goal_description="Enroll in SNAP",
            resource_name="SNAP",
            resource_contact="1-800-221-5689",
            tool_context=MockToolContext(),
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["action"], "care_plan_write_failed")
        self.assertEqual(result["resource_type"], "CarePlan")
        self.assertEqual(result["goal_id"], "goal-12")
        self.assertTrue(result["goal_created"])
        self.assertNotIn("http_status", result)
        self.assertIn("Could not reach FHIR server", result["error_message"])
        self.assertIn("read timed out", result["error_message"])
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
