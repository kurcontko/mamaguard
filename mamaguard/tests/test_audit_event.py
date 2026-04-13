"""Unit tests for FHIR AuditEvent generation."""

import json
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx


class MockToolContext:
    def __init__(self, fhir_url="https://fhir.example.org", fhir_token="tok", patient_id="p1"):
        self.state = {"fhir_url": fhir_url, "fhir_token": fhir_token, "patient_id": patient_id}


class TestBuildAuditEvent(unittest.TestCase):
    def test_read_action(self):
        from mamaguard.shared.audit_event import build_audit_event

        event = build_audit_event(
            patient_id="p1",
            tool_name="get_patient_summary",
            action="R",
            outcome="0",
        )
        self.assertEqual(event["resourceType"], "AuditEvent")
        self.assertEqual(event["action"], "R")
        self.assertEqual(event["outcome"], "0")
        self.assertEqual(event["type"]["code"], "110110")
        self.assertEqual(event["subtype"][0]["code"], "read")
        self.assertEqual(event["entity"][0]["what"]["reference"], "Patient/p1")
        self.assertIn("get_patient_summary", event["entity"][0]["description"])
        self.assertIn("get_patient_summary", event["agent"][0]["who"]["display"])
        self.assertEqual(event["agent"][0]["name"], "MamaGuard")
        self.assertFalse(event["agent"][0]["requestor"])
        self.assertEqual(event["source"]["type"][0]["code"], "4")
        self.assertEqual(event["purposeOfEvent"][0]["coding"][0]["code"], "TREAT")

    def test_create_action(self):
        from mamaguard.shared.audit_event import build_audit_event

        event = build_audit_event(
            patient_id="p2",
            tool_name="write_risk_assessment",
            action="C",
            outcome="0",
        )
        self.assertEqual(event["action"], "C")
        self.assertEqual(event["subtype"][0]["code"], "create")
        self.assertEqual(event["entity"][0]["what"]["reference"], "Patient/p2")

    def test_error_outcome(self):
        from mamaguard.shared.audit_event import build_audit_event

        event = build_audit_event(
            patient_id="p1",
            tool_name="get_bp_trend",
            action="R",
            outcome="8",
        )
        self.assertEqual(event["outcome"], "8")

    def test_recorded_is_iso_utc(self):
        from mamaguard.shared.audit_event import build_audit_event

        event = build_audit_event("p1", "test_tool", "R", "0")
        recorded = event["recorded"]
        # Should parse as a valid ISO datetime
        dt = datetime.fromisoformat(recorded)
        self.assertIsNotNone(dt.tzinfo)


class TestPostAuditEvent(unittest.TestCase):
    @patch("mamaguard.shared.audit_event.httpx.post")
    def test_successful_post(self, mock_post):
        from mamaguard.shared.audit_event import post_audit_event, build_audit_event

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "ae-123"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        event = build_audit_event("p1", "get_patient_summary", "R", "0")
        result = post_audit_event("https://fhir.example.org", "tok", event)
        self.assertTrue(result)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "https://fhir.example.org/AuditEvent")
        self.assertEqual(call_args.kwargs["json"]["resourceType"], "AuditEvent")
        self.assertEqual(call_args.kwargs["headers"]["Authorization"], "Bearer tok")
        self.assertEqual(call_args.kwargs["timeout"], 3)

    @patch("mamaguard.shared.audit_event.httpx.post")
    def test_http_error_swallowed(self, mock_post):
        from mamaguard.shared.audit_event import post_audit_event, build_audit_event

        mock_post.side_effect = httpx.HTTPStatusError(
            "405",
            request=MagicMock(),
            response=MagicMock(status_code=405),
        )

        event = build_audit_event("p1", "get_patient_summary", "R", "0")
        result = post_audit_event("https://fhir.example.org", "tok", event)
        self.assertFalse(result)

    @patch("mamaguard.shared.audit_event.httpx.post")
    def test_connection_error_swallowed(self, mock_post):
        from mamaguard.shared.audit_event import post_audit_event, build_audit_event

        mock_post.side_effect = httpx.ConnectError("unreachable")

        event = build_audit_event("p1", "get_patient_summary", "R", "0")
        result = post_audit_event("https://fhir.example.org", "tok", event)
        self.assertFalse(result)

    @patch("mamaguard.shared.audit_event.httpx.post")
    def test_timeout_swallowed(self, mock_post):
        from mamaguard.shared.audit_event import post_audit_event, build_audit_event

        mock_post.side_effect = httpx.ReadTimeout("timeout")

        event = build_audit_event("p1", "get_patient_summary", "R", "0")
        result = post_audit_event("https://fhir.example.org", "tok", event)
        self.assertFalse(result)


class TestEmitAuditEvent(unittest.TestCase):
    @patch("mamaguard.shared.audit_event.post_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_enabled_calls_post(self, mock_post):
        from mamaguard.shared.audit_event import emit_audit_event

        mock_post.return_value = True

        emit_audit_event("https://fhir.example.org", "tok", "p1", "get_bp_trend", "R", "0")
        mock_post.assert_called_once()
        event = mock_post.call_args.args[2]
        self.assertEqual(event["resourceType"], "AuditEvent")
        self.assertEqual(event["entity"][0]["what"]["reference"], "Patient/p1")

    @patch("mamaguard.shared.audit_event.post_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": ""})
    def test_disabled_skips_post(self, mock_post):
        from mamaguard.shared.audit_event import emit_audit_event

        emit_audit_event("https://fhir.example.org", "tok", "p1", "get_bp_trend", "R", "0")
        mock_post.assert_not_called()

    @patch("mamaguard.shared.audit_event.post_audit_event")
    @patch.dict(os.environ, {}, clear=False)
    def test_unset_env_skips_post(self, mock_post):
        from mamaguard.shared.audit_event import emit_audit_event

        # Remove the key if present
        os.environ.pop("MAMAGUARD_AUDIT_EVENTS", None)
        emit_audit_event("https://fhir.example.org", "tok", "p1", "get_bp_trend", "R", "0")
        mock_post.assert_not_called()


class TestAuditedDecorator(unittest.TestCase):
    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_read_tool_emits_read_action(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_patient_summary(tool_context=None):
            return {"status": "success", "patient_id": "p1"}

        ctx = MockToolContext()
        result = get_patient_summary(tool_context=ctx)

        self.assertEqual(result["status"], "success")
        mock_emit.assert_called_once_with(
            "https://fhir.example.org", "tok", "p1",
            "get_patient_summary", "R", "0",
        )

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_write_tool_emits_create_action(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def write_risk_assessment(risk_type, tool_context=None):
            return {"status": "success", "resource_id": "ra-1"}

        ctx = MockToolContext()
        result = write_risk_assessment("test-risk", tool_context=ctx)

        self.assertEqual(result["status"], "success")
        mock_emit.assert_called_once_with(
            "https://fhir.example.org", "tok", "p1",
            "write_risk_assessment", "C", "0",
        )

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_create_tool_emits_create_action(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def create_communication_request(medium, tool_context=None):
            return {"status": "success", "resource_id": "cr-1"}

        ctx = MockToolContext()
        result = create_communication_request("phone", tool_context=ctx)

        mock_emit.assert_called_once_with(
            "https://fhir.example.org", "tok", "p1",
            "create_communication_request", "C", "0",
        )

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_error_result_emits_failure_outcome(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_bp_trend(tool_context=None):
            return {"status": "error", "error_message": "FHIR server returned 500"}

        ctx = MockToolContext()
        result = get_bp_trend(tool_context=ctx)

        self.assertEqual(result["status"], "error")
        mock_emit.assert_called_once_with(
            "https://fhir.example.org", "tok", "p1",
            "get_bp_trend", "R", "8",
        )

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_partial_result_emits_minor_failure(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def write_care_plan(tool_context=None):
            return {"status": "partial", "message": "Goal created, CarePlan rejected"}

        ctx = MockToolContext()
        result = write_care_plan(tool_context=ctx)

        mock_emit.assert_called_once_with(
            "https://fhir.example.org", "tok", "p1",
            "write_care_plan", "C", "4",
        )

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": ""})
    def test_disabled_flag_skips_emit(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_patient_summary(tool_context=None):
            return {"status": "success"}

        ctx = MockToolContext()
        get_patient_summary(tool_context=ctx)
        mock_emit.assert_not_called()

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_no_context_skips_emit(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_patient_summary(tool_context=None):
            return {"status": "success"}

        # No tool_context provided
        get_patient_summary()
        mock_emit.assert_not_called()

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_missing_fhir_context_skips_emit(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_patient_summary(tool_context=None):
            return {"status": "success"}

        # Context with missing fields
        ctx = MockToolContext(fhir_url="", fhir_token="", patient_id="")
        get_patient_summary(tool_context=ctx)
        mock_emit.assert_not_called()

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_positional_context_detected(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_patient_summary(tool_context=None):
            return {"status": "success"}

        ctx = MockToolContext()
        # Pass as positional arg
        get_patient_summary(ctx)
        mock_emit.assert_called_once()

    def test_preserves_function_name(self):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_patient_summary(tool_context=None):
            """My docstring."""
            return {}

        self.assertEqual(get_patient_summary.__name__, "get_patient_summary")
        self.assertEqual(get_patient_summary.__doc__, "My docstring.")

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "1"})
    def test_env_value_1_enables(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_patient_summary(tool_context=None):
            return {"status": "success"}

        get_patient_summary(tool_context=MockToolContext())
        mock_emit.assert_called_once()

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "YES"})
    def test_env_value_yes_enables(self, mock_emit):
        from mamaguard.shared.audit_event import audited

        @audited
        def get_patient_summary(tool_context=None):
            return {"status": "success"}

        get_patient_summary(tool_context=MockToolContext())
        mock_emit.assert_called_once()


class TestInitReexportsAreAudited(unittest.TestCase):
    """Verify that tools imported from the package are wrapped."""

    @patch("mamaguard.shared.audit_event.emit_audit_event")
    @patch("mamaguard.shared.tools.fhir_base.httpx.get")
    @patch.dict(os.environ, {"MAMAGUARD_AUDIT_EVENTS": "true"})
    def test_get_patient_summary_via_init_emits(self, mock_get, mock_emit):
        from mamaguard.shared.tools import get_patient_summary

        # Mock FHIR responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "resourceType": "Patient",
            "name": [{"use": "official", "given": ["Maria"], "family": "Lopez"}],
            "birthDate": "1992-07-15",
            "gender": "female",
            "entry": [],
        }
        mock_get.return_value = mock_response

        ctx = MockToolContext()
        result = get_patient_summary(ctx)

        self.assertEqual(result["status"], "success")
        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        self.assertEqual(call_args.args[2], "p1")  # patient_id
        self.assertEqual(call_args.args[3], "get_patient_summary")  # tool_name
        self.assertEqual(call_args.args[4], "R")  # action
        self.assertEqual(call_args.args[5], "0")  # outcome


if __name__ == "__main__":
    unittest.main()
