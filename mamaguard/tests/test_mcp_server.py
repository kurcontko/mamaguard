"""
Tests for the MamaGuard MCP server.

Covers:
1. FhirContext adapter (context.py)
2. MCP tool registration (all 14 tools visible)
3. Tool invocation — happy path with mocked FHIR responses
4. Error propagation — missing credentials surfaced cleanly
5. SHARP context constructor (from_sharp)
6. MCP protocol handshake (initialize → server info + capabilities)
7. MCP protocol tool listing (list_tools via protocol layer)
8. MCP protocol tool invocation (call_tool via protocol layer)
9. FHIR/SHARP context propagation through MCP protocol
"""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

import anyio
from anyio import create_memory_object_stream
from mcp.shared.message import SessionMessage
from mcp.client.session import ClientSession
from mcp.types import Implementation


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


# ---------------------------------------------------------------------------
# MCP protocol integration tests
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine in a new event loop."""
    return asyncio.run(coro)


async def _create_mcp_client_session():
    """
    Create an in-memory MCP client↔server pair.

    Returns (task_group, client, cancel_fn) — the caller must `await
    client.initialize()` inside the client async context manager and
    cancel the task group when done.
    """
    from mamaguard.mcp_server.server import mcp as mcp_server

    client_to_server_send, client_to_server_recv = (
        create_memory_object_stream[SessionMessage | Exception](100)
    )
    server_to_client_send, server_to_client_recv = (
        create_memory_object_stream[SessionMessage | Exception](100)
    )

    low_server = mcp_server._mcp_server
    init_opts = low_server.create_initialization_options()

    return (
        low_server,
        init_opts,
        client_to_server_recv,
        server_to_client_send,
        ClientSession(
            read_stream=server_to_client_recv,
            write_stream=client_to_server_send,
            client_info=Implementation(name="mamaguard-test-client", version="0.1"),
        ),
    )


class TestMcpProtocolHandshake(unittest.TestCase):
    """MCP protocol handshake: initialize → server info + capabilities."""

    def test_initialize_returns_server_info(self):
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    result = await client.initialize()
                    self.assertEqual(result.serverInfo.name, "mamaguard")
                    self.assertIsNotNone(result.serverInfo.version)
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_initialize_returns_instructions(self):
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    result = await client.initialize()
                    self.assertIn("SHARP", result.instructions)
                    self.assertIn("fhir_url", result.instructions)
                    self.assertIn("fhir_token", result.instructions)
                    self.assertIn("patient_id", result.instructions)
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_initialize_advertises_tool_capability(self):
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    result = await client.initialize()
                    self.assertIsNotNone(result.capabilities.tools)
                    tg.cancel_scope.cancel()

        _run_async(_test())


class TestMcpProtocolListTools(unittest.TestCase):
    """MCP protocol tool listing via the protocol layer."""

    def test_list_tools_returns_all_14(self):
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    tools_result = await client.list_tools()
                    names = {t.name for t in tools_result.tools}
                    self.assertEqual(names, EXPECTED_TOOLS)
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_every_tool_has_sharp_params(self):
        """Every MCP tool must accept fhir_url, fhir_token, patient_id."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    tools_result = await client.list_tools()
                    for tool in tools_result.tools:
                        props = tool.inputSchema.get("properties", {})
                        for sharp_param in ("fhir_url", "fhir_token", "patient_id"):
                            self.assertIn(
                                sharp_param,
                                props,
                                f"Tool {tool.name} missing SHARP param {sharp_param}",
                            )
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_every_tool_has_description(self):
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    tools_result = await client.list_tools()
                    for tool in tools_result.tools:
                        self.assertTrue(
                            tool.description and len(tool.description) > 10,
                            f"Tool {tool.name} has insufficient description",
                        )
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_sharp_params_are_required(self):
        """fhir_url, fhir_token, patient_id must be required on every tool."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    tools_result = await client.list_tools()
                    for tool in tools_result.tools:
                        required = tool.inputSchema.get("required", [])
                        for sharp_param in ("fhir_url", "fhir_token", "patient_id"):
                            self.assertIn(
                                sharp_param,
                                required,
                                f"Tool {tool.name}: {sharp_param} should be required",
                            )
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_read_tools_have_no_extra_required_beyond_sharp(self):
        """Read-only tools (patient summary, BP trend, etc.) should only
        require the three SHARP params (plus optional defaults)."""
        read_tools = {
            "get_patient_summary", "get_active_medications",
            "get_pregnancy_history", "get_maternal_risk_profile",
            "get_sdoh_screening",
        }
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    tools_result = await client.list_tools()
                    for tool in tools_result.tools:
                        if tool.name in read_tools:
                            required = set(tool.inputSchema.get("required", []))
                            self.assertEqual(
                                required,
                                {"fhir_url", "fhir_token", "patient_id"},
                                f"Tool {tool.name} has unexpected required params: "
                                f"{required - {'fhir_url', 'fhir_token', 'patient_id'}}",
                            )
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_write_tools_require_domain_params(self):
        """Write tools must require domain-specific params beyond SHARP."""
        write_tool_extra_required = {
            "write_risk_assessment": {"risk_type", "probability", "basis", "mitigation"},
            "create_communication_request": {"medium", "content"},
            "write_care_plan": {
                "category", "goal_description", "resource_name", "resource_contact",
            },
        }
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    tools_result = await client.list_tools()
                    tool_map = {t.name: t for t in tools_result.tools}
                    for tool_name, expected_extra in write_tool_extra_required.items():
                        tool = tool_map[tool_name]
                        required = set(tool.inputSchema.get("required", []))
                        sharp = {"fhir_url", "fhir_token", "patient_id"}
                        extra = required - sharp
                        self.assertTrue(
                            expected_extra.issubset(extra),
                            f"Tool {tool_name} missing required domain params: "
                            f"{expected_extra - extra}",
                        )
                    tg.cancel_scope.cancel()

        _run_async(_test())


class TestMcpProtocolCallTool(unittest.TestCase):
    """MCP protocol tool invocation via call_tool."""

    def test_call_tool_returns_json_text_content(self):
        """call_tool response contains a TextContent with valid JSON."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_get:
                        mock_get.side_effect = [
                            {
                                "resourceType": "Patient", "id": "p1",
                                "name": [{"family": "Garcia"}],
                                "birthDate": "1990-03-15", "gender": "female",
                            },
                            {"resourceType": "Bundle", "entry": []},
                            {"resourceType": "Bundle", "entry": []},
                            {"resourceType": "Bundle", "entry": []},
                        ]
                        result = await client.call_tool("get_patient_summary", {
                            "fhir_url": "https://r4.smarthealthit.org",
                            "fhir_token": "tok",
                            "patient_id": "p1",
                        })
                    self.assertGreater(len(result.content), 0)
                    self.assertEqual(result.content[0].type, "text")
                    data = json.loads(result.content[0].text)
                    self.assertEqual(data["status"], "success")
                    self.assertEqual(data["patient_id"], "p1")
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_call_tool_missing_credentials_returns_error(self):
        """Empty SHARP credentials → error propagated via protocol."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    result = await client.call_tool("get_patient_summary", {
                        "fhir_url": "",
                        "fhir_token": "",
                        "patient_id": "",
                    })
                    data = json.loads(result.content[0].text)
                    self.assertEqual(data["status"], "error")
                    self.assertIn("missing", data["error_message"])
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_call_tool_bp_trend_with_months_back(self):
        """Optional months_back param flows through protocol."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    with patch("mamaguard.shared.tools.maternal._fhir_get") as mock_get:
                        mock_get.return_value = {"resourceType": "Bundle", "entry": []}
                        result = await client.call_tool("get_bp_trend", {
                            "fhir_url": "https://fhir.example.org",
                            "fhir_token": "tok",
                            "patient_id": "p1",
                            "months_back": 6,
                        })
                    data = json.loads(result.content[0].text)
                    self.assertEqual(data["status"], "success")
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_call_tool_write_risk_assessment_via_protocol(self):
        """Write tool invocation through the full protocol layer."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    with patch("mamaguard.shared.tools.writeback._fhir_post") as mock_post:
                        mock_post.return_value = {
                            "id": "ra-proto-001",
                            "resourceType": "RiskAssessment",
                        }
                        result = await client.call_tool("write_risk_assessment", {
                            "fhir_url": "https://hapi.fhir.org/baseR4",
                            "fhir_token": "write-tok",
                            "patient_id": "p1",
                            "risk_type": "postpartum-hypertensive-crisis",
                            "probability": 0.72,
                            "basis": "BP 148/92",
                            "mitigation": "Schedule follow-up",
                        })
                    data = json.loads(result.content[0].text)
                    self.assertEqual(data["status"], "success")
                    self.assertEqual(data["resource_id"], "ra-proto-001")
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_call_tool_find_sdoh_resources_via_protocol(self):
        """SDOH resource lookup tool invoked through protocol."""
        async def _test():
            import os
            os.environ.pop("MAMAGUARD_SDOH_API_URL", None)
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    result = await client.call_tool("find_sdoh_resources", {
                        "fhir_url": "https://fhir.example.org",
                        "fhir_token": "tok",
                        "patient_id": "p1",
                        "category_or_code": "Z59.0",
                        "zip_code": "02139",
                    })
                    data = json.loads(result.content[0].text)
                    self.assertEqual(data["status"], "success")
                    self.assertEqual(data["category"], "housing")
                    self.assertGreaterEqual(data["resource_count"], 1)
                    tg.cancel_scope.cancel()

        _run_async(_test())


class TestMcpFhirContextPropagation(unittest.TestCase):
    """Verify SHARP credentials propagate through the MCP protocol layer
    into the shared tool implementations."""

    def test_fhir_url_and_token_reach_fhir_get(self):
        """SHARP params → FhirContext → _fhir_get called with correct URL/token."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_get:
                        mock_get.side_effect = [
                            {
                                "resourceType": "Patient", "id": "maria-42",
                                "name": [{"family": "Garcia"}],
                                "birthDate": "1990-03-15", "gender": "female",
                            },
                            {"resourceType": "Bundle", "entry": []},
                            {"resourceType": "Bundle", "entry": []},
                            {"resourceType": "Bundle", "entry": []},
                        ]
                        await client.call_tool("get_patient_summary", {
                            "fhir_url": "https://custom-ehr.hospital.org/fhir/R4",
                            "fhir_token": "ehr-session-bearer-xyz",
                            "patient_id": "maria-42",
                        })

                    # Verify first call to _fhir_get received our SHARP creds
                    first_call_args = mock_get.call_args_list[0]
                    called_url = first_call_args[0][0]
                    called_token = first_call_args[0][1]
                    self.assertIn(
                        "custom-ehr.hospital.org",
                        called_url,
                        "FHIR URL not propagated through MCP protocol",
                    )
                    self.assertEqual(
                        called_token,
                        "ehr-session-bearer-xyz",
                        "FHIR token not propagated through MCP protocol",
                    )
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_patient_id_reaches_fhir_get(self):
        """patient_id flows through MCP → FhirContext → FHIR resource path."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_get:
                        mock_get.side_effect = [
                            {
                                "resourceType": "Patient", "id": "synthea-maria-881f",
                                "name": [{"family": "Santos"}],
                                "birthDate": "1991-06-20", "gender": "female",
                            },
                            {"resourceType": "Bundle", "entry": []},
                            {"resourceType": "Bundle", "entry": []},
                            {"resourceType": "Bundle", "entry": []},
                        ]
                        await client.call_tool("get_patient_summary", {
                            "fhir_url": "https://r4.smarthealthit.org",
                            "fhir_token": "tok",
                            "patient_id": "synthea-maria-881f",
                        })

                    # _fhir_get(fhir_url, token, resource_path, ...) —
                    # patient_id appears in the resource path (arg[2]) and/or
                    # query params, not the base URL (arg[0]).
                    all_args_str = " ".join(
                        str(c) for c in mock_get.call_args_list
                    )
                    self.assertIn(
                        "synthea-maria-881f",
                        all_args_str,
                        "patient_id not propagated through MCP protocol to FHIR calls",
                    )
                    # First call fetches Patient/{id}
                    first_call_resource_path = mock_get.call_args_list[0][0][2]
                    self.assertEqual(
                        first_call_resource_path,
                        "Patient/synthea-maria-881f",
                    )
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_trailing_slash_stripped_through_protocol(self):
        """Trailing slash on fhir_url is stripped before reaching _fhir_get."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_get:
                        mock_get.side_effect = [
                            {
                                "resourceType": "Patient", "id": "p1",
                                "name": [{"family": "Test"}],
                                "birthDate": "1990-01-01", "gender": "female",
                            },
                            {"resourceType": "Bundle", "entry": []},
                            {"resourceType": "Bundle", "entry": []},
                            {"resourceType": "Bundle", "entry": []},
                        ]
                        await client.call_tool("get_patient_summary", {
                            "fhir_url": "https://r4.smarthealthit.org/",
                            "fhir_token": "tok",
                            "patient_id": "p1",
                        })

                    first_call_url = mock_get.call_args_list[0][0][0]
                    self.assertFalse(
                        first_call_url.startswith("https://r4.smarthealthit.org//"),
                        f"Double slash in URL — trailing slash not stripped: {first_call_url}",
                    )
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_context_propagation_through_write_tool(self):
        """SHARP creds propagate through MCP → write tool → _fhir_post."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    with patch("mamaguard.shared.tools.writeback._fhir_post") as mock_post:
                        mock_post.return_value = {
                            "id": "ra-001",
                            "resourceType": "RiskAssessment",
                        }
                        await client.call_tool("write_risk_assessment", {
                            "fhir_url": "https://write-ehr.hospital.org/fhir",
                            "fhir_token": "write-bearer-abc",
                            "patient_id": "write-patient-99",
                            "risk_type": "test-risk",
                            "probability": 0.5,
                            "basis": "test",
                            "mitigation": "test",
                        })

                    call_args = mock_post.call_args
                    called_url = call_args[0][0]  # fhir_url
                    called_token = call_args[0][1]  # token
                    self.assertIn("write-ehr.hospital.org", called_url)
                    self.assertEqual(called_token, "write-bearer-abc")
                    tg.cancel_scope.cancel()

        _run_async(_test())

    def test_context_propagation_through_sdoh_tool(self):
        """SHARP creds propagate to SDOH read tool through MCP."""
        async def _test():
            low_server, init_opts, c2s_recv, s2c_send, client = (
                await _create_mcp_client_session()
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)
                async with client:
                    await client.initialize()
                    with patch("mamaguard.shared.tools.sdoh._fhir_get") as mock_get:
                        mock_get.return_value = {"resourceType": "Bundle", "entry": []}
                        await client.call_tool("get_sdoh_screening", {
                            "fhir_url": "https://sdoh-ehr.org/fhir",
                            "fhir_token": "sdoh-bearer-tok",
                            "patient_id": "sdoh-patient-7",
                        })

                    # SDOH screening makes multiple FHIR calls (Patient, Condition, Coverage, etc.)
                    self.assertGreater(mock_get.call_count, 0)
                    first_call_url = mock_get.call_args_list[0][0][0]
                    first_call_token = mock_get.call_args_list[0][0][1]
                    self.assertIn("sdoh-ehr.org", first_call_url)
                    self.assertEqual(first_call_token, "sdoh-bearer-tok")
                    tg.cancel_scope.cancel()

        _run_async(_test())


# ---------------------------------------------------------------------------
# sse_app export (Docker/uvicorn deployment path)
# ---------------------------------------------------------------------------

class TestSseAppExport(unittest.TestCase):
    """Verify that the module-level sse_app is a valid Starlette ASGI app."""

    def test_sse_app_is_starlette_instance(self):
        from mamaguard.mcp_server.server import sse_app
        from starlette.applications import Starlette
        self.assertIsInstance(sse_app, Starlette)

    def test_sse_app_is_callable(self):
        from mamaguard.mcp_server.server import sse_app
        self.assertTrue(callable(sse_app))

    def test_sse_app_has_routes(self):
        from mamaguard.mcp_server.server import sse_app
        self.assertGreater(len(sse_app.routes), 0)


if __name__ == "__main__":
    unittest.main()
