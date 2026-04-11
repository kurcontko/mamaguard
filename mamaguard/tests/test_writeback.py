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


if __name__ == "__main__":
    unittest.main()
