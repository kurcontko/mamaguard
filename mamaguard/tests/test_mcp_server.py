"""
Tests for the MamaGuard MCP server.

Covers:
1. FhirContext adapter (context.py)
2. MCP tool registration (all 14 tools visible)
3. Tool invocation — happy path with mocked FHIR responses
4. Error propagation — missing credentials surfaced cleanly
5. SHARP context constructor (from_sharp)
"""

import json
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# FhirContext tests
# ---------------------------------------------------------------------------

class TestFhirContext(unittest.TestCase):
    def test_basic_construction(self):
        from mamaguard.mcp_server.context import FhirContext
        ctx = FhirContext(
            fhir_url="https://r4.smarthealthit.org",
            fhir_token="tok123",
            patient_id="p1",
        )
        self.assertEqual(ctx.state["fhir_url"], "https://r4.smarthealthit.org")
        self.assertEqual(ctx.state["fhir_token"], "tok123")
        self.assertEqual(ctx.state["patient_id"], "p1")

    def test_trailing_slash_stripped(self):
        from mamaguard.mcp_server.context import FhirContext
        ctx = FhirContext(
            fhir_url="https://r4.smarthealthit.org/",
            fhir_token="tok",
            patient_id="p1",
        )
        self.assertEqual(ctx.state["fhir_url"], "https://r4.smarthealthit.org")

    def test_from_sharp(self):
        from mamaguard.mcp_server.context import FhirContext
        sharp = {
            "fhirUrl": "https://hapi.fhir.org/baseR4",
            "fhirToken": "sharp-tok",
            "patientId": "sharppat",
        }
        ctx = FhirContext.from_sharp(sharp)
        self.assertEqual(ctx.state["fhir_url"], "https://hapi.fhir.org/baseR4")
        self.assertEqual(ctx.state["fhir_token"], "sharp-tok")
        self.assertEqual(ctx.state["patient_id"], "sharppat")

    def test_from_sharp_missing_keys(self):
        from mamaguard.mcp_server.context import FhirContext
        ctx = FhirContext.from_sharp({})
        # Empty strings — tools will return error dict, not crash
        self.assertEqual(ctx.state["fhir_url"], "")
        self.assertEqual(ctx.state["fhir_token"], "")
        self.assertEqual(ctx.state["patient_id"], "")


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "get_patient_summary",
    "get_active_medications",
    "get_bp_trend",
    "get_glucose_trend",
    "get_pregnancy_history",
    "get_maternal_risk_profile",
    "get_immunization_gaps",
    "get_developmental_screening_status",
    "get_care_gaps",
    "get_sdoh_screening",
    "find_sdoh_resources",
    "write_risk_assessment",
    "create_communication_request",
    "write_care_plan",
}


class TestMcpToolRegistration(unittest.TestCase):
    def _registered_names(self):
        from mamaguard.mcp_server.server import mcp
        # FastMCP stores tools in _tool_manager
        tool_manager = mcp._tool_manager
        return {name for name in tool_manager._tools}

    def test_all_14_tools_registered(self):
        registered = self._registered_names()
        missing = EXPECTED_TOOLS - registered
        self.assertEqual(missing, set(), f"Missing tools: {missing}")

    def test_no_extra_tools(self):
        registered = self._registered_names()
        extra = registered - EXPECTED_TOOLS
        self.assertEqual(extra, set(), f"Unexpected extra tools: {extra}")


# ---------------------------------------------------------------------------
# Tool invocation — happy path
# ---------------------------------------------------------------------------

def _make_patient_bundle():
    return {
        "resourceType": "Patient",
        "id": "p1",
        "name": [{"use": "official", "family": "Garcia", "given": ["Maria"]}],
        "birthDate": "1990-03-15",
        "gender": "female",
    }


def _make_empty_bundle():
    return {"resourceType": "Bundle", "entry": []}


class TestGetPatientSummaryTool(unittest.TestCase):
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_returns_json_string(self, mock_get):
        mock_get.side_effect = [
            _make_patient_bundle(),
            _make_empty_bundle(),  # conditions
            _make_empty_bundle(),  # medications
            _make_empty_bundle(),  # vitals
        ]
        from mamaguard.mcp_server.server import get_patient_summary
        result = get_patient_summary(
            fhir_url="https://fhir.example.org",
            fhir_token="tok",
            patient_id="p1",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["patient_id"], "p1")
        self.assertIn("name", data)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_missing_credentials_propagated(self, mock_get):
        from mamaguard.mcp_server.server import get_patient_summary
        result = get_patient_summary(
            fhir_url="",
            fhir_token="",
            patient_id="",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "error")
        self.assertIn("missing", data["error_message"])
        mock_get.assert_not_called()


class TestGetActiveMedicationsTool(unittest.TestCase):
    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_returns_medication_list(self, mock_get):
        mock_get.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "MedicationRequest",
                        "status": "active",
                        "medicationCodeableConcept": {"text": "Labetalol 200mg"},
                        "dosageInstruction": [{"text": "twice daily"}],
                        "authoredOn": "2025-01-10",
                    }
                }
            ],
        }
        from mamaguard.mcp_server.server import get_active_medications
        result = get_active_medications(
            fhir_url="https://fhir.example.org",
            fhir_token="tok",
            patient_id="p1",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["medications"][0]["medication"], "Labetalol 200mg")


class TestGetBpTrendTool(unittest.TestCase):
    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_returns_readings_and_trend(self, mock_get):
        mock_get.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "effectiveDateTime": "2025-10-01",
                        "component": [
                            {
                                "code": {"coding": [{"code": "8480-6"}]},
                                "valueQuantity": {"value": 135, "unit": "mmHg"},
                            },
                            {
                                "code": {"coding": [{"code": "8462-4"}]},
                                "valueQuantity": {"value": 85, "unit": "mmHg"},
                            },
                        ],
                    }
                }
            ],
        }
        from mamaguard.mcp_server.server import get_bp_trend
        result = get_bp_trend(
            fhir_url="https://fhir.example.org",
            fhir_token="tok",
            patient_id="p1",
            months_back=12,
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "success")
        # readings are nested under data.readings in the maternal tool response
        readings = data.get("readings") or data.get("data", {}).get("readings", [])
        self.assertIsInstance(readings, list)

    @patch("mamaguard.shared.tools.maternal._fhir_get")
    def test_default_months_back(self, mock_get):
        mock_get.return_value = {"resourceType": "Bundle", "entry": []}
        from mamaguard.mcp_server.server import get_bp_trend
        result = get_bp_trend(
            fhir_url="https://fhir.example.org",
            fhir_token="tok",
            patient_id="p1",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "success")


class TestWriteRiskAssessmentTool(unittest.TestCase):
    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_creates_risk_assessment(self, mock_post):
        mock_post.return_value = {"id": "ra-001", "resourceType": "RiskAssessment"}
        from mamaguard.mcp_server.server import write_risk_assessment
        result = write_risk_assessment(
            fhir_url="https://hapi.fhir.org/baseR4",
            fhir_token="tok",
            patient_id="p1",
            risk_type="postpartum-hypertensive-crisis",
            probability=0.72,
            basis="BP 148/92 at 2 weeks postpartum, prior pre-eclampsia",
            mitigation="Schedule immediate follow-up, consider antihypertensives",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["resource_id"], "ra-001")
        self.assertAlmostEqual(data["probability"], 0.72)

    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_propagates_http_error(self, mock_post):
        import httpx
        response = MagicMock()
        response.status_code = 403
        response.text = "Forbidden"
        mock_post.side_effect = httpx.HTTPStatusError(
            "403 Forbidden", request=MagicMock(), response=response
        )
        from mamaguard.mcp_server.server import write_risk_assessment
        result = write_risk_assessment(
            fhir_url="https://r4.smarthealthit.org",
            fhir_token="tok",
            patient_id="p1",
            risk_type="test",
            probability=0.5,
            basis="test",
            mitigation="test",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["http_status"], 403)


class TestCreateCommunicationRequestTool(unittest.TestCase):
    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_creates_comm_request(self, mock_post):
        mock_post.return_value = {"id": "cr-001", "resourceType": "CommunicationRequest"}
        from mamaguard.mcp_server.server import create_communication_request
        result = create_communication_request(
            fhir_url="https://hapi.fhir.org/baseR4",
            fhir_token="tok",
            patient_id="p1",
            medium="phone",
            content="Schedule 6-week postpartum follow-up",
            priority="routine",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["medium"], "phone")
        self.assertEqual(data["resource_id"], "cr-001")


class TestSdohScreeningTool(unittest.TestCase):
    @patch("mamaguard.shared.tools.sdoh._fhir_get")
    def test_returns_screening_result(self, mock_get):
        mock_get.return_value = {"resourceType": "Bundle", "entry": []}
        from mamaguard.mcp_server.server import get_sdoh_screening
        result = get_sdoh_screening(
            fhir_url="https://fhir.example.org",
            fhir_token="tok",
            patient_id="p1",
        )
        data = json.loads(result)
        # should not crash; status depends on implementation
        self.assertIn("status", data)


class TestCareGapsTool(unittest.TestCase):
    @patch("mamaguard.shared.tools.pediatric._fhir_get")
    def test_returns_care_gaps(self, mock_get):
        mock_get.return_value = {"resourceType": "Bundle", "entry": []}
        from mamaguard.mcp_server.server import get_care_gaps
        result = get_care_gaps(
            fhir_url="https://fhir.example.org",
            fhir_token="tok",
            patient_id="child-01",
        )
        data = json.loads(result)
        self.assertIn("status", data)


class TestFindSdohResourcesTool(unittest.TestCase):
    def test_z590_housing_offline(self):
        from mamaguard.mcp_server.server import find_sdoh_resources
        import os as _os
        _os.environ.pop("MAMAGUARD_SDOH_API_URL", None)
        result = find_sdoh_resources(
            fhir_url="https://fhir.example.org",
            fhir_token="tok",
            patient_id="p1",
            category_or_code="Z59.0",
            zip_code="02139",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["category"], "housing")
        self.assertGreaterEqual(data["resource_count"], 1)


class TestWriteCarePlanTool(unittest.TestCase):
    @patch("mamaguard.shared.tools.writeback._fhir_post")
    def test_creates_goal_and_care_plan(self, mock_post):
        def side_effect(fhir_url, token, resource_type, body):
            if resource_type == "Goal":
                return {"resourceType": "Goal", "id": "goal-42"}
            return {"resourceType": "CarePlan", "id": "cp-42"}
        mock_post.side_effect = side_effect

        from mamaguard.mcp_server.server import write_care_plan
        result = write_care_plan(
            fhir_url="https://hapi.fhir.org/baseR4",
            fhir_token="tok",
            patient_id="p1",
            category="housing",
            goal_description="Secure emergency shelter within 7 days",
            resource_name="211 Helpline",
            resource_contact="Dial 211",
            resource_url="https://www.211.org",
            z_code="Z59.0",
        )
        data = json.loads(result)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["care_plan_id"], "cp-42")
        self.assertEqual(data["goal_id"], "goal-42")


if __name__ == "__main__":
    unittest.main()
