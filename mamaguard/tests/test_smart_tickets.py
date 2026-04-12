"""
Tests for SMART Permission Tickets — Phase 2b.

Covers:
  - JWT decoding: valid, expired, malformed, missing claims, audience mismatch
  - Scope checking: exact match, wildcard, permission superset, insufficient
  - Tool scope mapping: every tool has a mapping, coverage audit
  - enforce_smart_ticket: enabled/disabled flag, missing ticket, patient mismatch,
    expired in-session, scope denied, authorized
  - fhir_hook integration: ticket extracted from FHIR context and stored in state
  - _get_fhir_context integration: scope enforcement blocks tool when enabled
"""

import time
import unittest
from unittest.mock import patch

import jwt

from mamaguard.shared.smart_tickets import (
    TOOL_SCOPES,
    PermissionTicket,
    TicketError,
    _scope_satisfies,
    check_tool_scope,
    decode_permission_ticket,
    enforce_smart_ticket,
)
from mamaguard.shared.fhir_hook import _extract_smart_ticket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET = "test-secret-key-for-unit-tests"
_PATIENT = "881f534f-d041-425d-a542-cbf669f43e18"


def _make_ticket_jwt(
    sub: str = _PATIENT,
    scope: str = "patient/Observation.rs patient/Condition.rs",
    exp: int | None = None,
    iss: str = "https://auth.example.com",
    aud: str = "",
    secret: str = _SECRET,
    algorithm: str = "HS256",
    **extra,
) -> str:
    """Helper to create a signed JWT for testing."""
    claims = {
        "sub": sub,
        "scope": scope,
        "exp": exp or int(time.time()) + 3600,
        "iss": iss,
        **extra,
    }
    if aud:
        claims["aud"] = aud
    return jwt.encode(claims, secret, algorithm=algorithm)


# ===========================================================================
# 1. JWT Decoding
# ===========================================================================


class TestDecodePermissionTicket(unittest.TestCase):
    """decode_permission_ticket — JWT validation."""

    def test_valid_ticket(self):
        token = _make_ticket_jwt()
        ticket = decode_permission_ticket(token, signing_key=_SECRET)
        self.assertIsInstance(ticket, PermissionTicket)
        self.assertEqual(ticket.sub, _PATIENT)
        self.assertIn("patient/Observation.rs", ticket.scopes)
        self.assertIn("patient/Condition.rs", ticket.scopes)
        self.assertEqual(len(ticket.scopes), 2)
        self.assertGreater(ticket.exp, int(time.time()))
        self.assertEqual(ticket.iss, "https://auth.example.com")

    def test_expired_ticket(self):
        token = _make_ticket_jwt(exp=int(time.time()) - 60)
        with self.assertRaises(TicketError) as cm:
            decode_permission_ticket(token, signing_key=_SECRET)
        self.assertIn("expired", str(cm.exception).lower())

    def test_malformed_jwt(self):
        with self.assertRaises(TicketError) as cm:
            decode_permission_ticket("not.a.jwt", signing_key=_SECRET)
        self.assertIn("decode failed", str(cm.exception).lower())

    def test_wrong_signing_key(self):
        token = _make_ticket_jwt(secret="correct-key")
        with self.assertRaises(TicketError):
            decode_permission_ticket(token, signing_key="wrong-key")

    def test_missing_sub_claim(self):
        raw = jwt.encode(
            {"scope": "patient/Observation.rs", "exp": int(time.time()) + 3600},
            _SECRET, algorithm="HS256",
        )
        with self.assertRaises(TicketError) as cm:
            decode_permission_ticket(raw, signing_key=_SECRET)
        self.assertIn("missing required claim", str(cm.exception).lower())

    def test_missing_scope_claim(self):
        raw = jwt.encode(
            {"sub": _PATIENT, "exp": int(time.time()) + 3600},
            _SECRET, algorithm="HS256",
        )
        with self.assertRaises(TicketError) as cm:
            decode_permission_ticket(raw, signing_key=_SECRET)
        self.assertIn("missing required claim", str(cm.exception).lower())

    def test_missing_exp_claim(self):
        # Manually craft a JWT without exp by using PyJWS directly
        import json as _json, base64
        header = base64.urlsafe_b64encode(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            _json.dumps({"sub": _PATIENT, "scope": "patient/Observation.rs"}).encode()
        ).rstrip(b"=")
        import hmac, hashlib
        sig_input = header + b"." + payload
        sig = base64.urlsafe_b64encode(
            hmac.new(_SECRET.encode(), sig_input, hashlib.sha256).digest()
        ).rstrip(b"=")
        raw = (sig_input + b"." + sig).decode()
        with self.assertRaises(TicketError) as cm:
            decode_permission_ticket(raw, signing_key=_SECRET)
        err = str(cm.exception).lower()
        self.assertTrue("expired" in err or "missing" in err or "invalid" in err)

    def test_audience_match(self):
        token = _make_ticket_jwt(aud="https://mamaguard.example.com")
        ticket = decode_permission_ticket(
            token, signing_key=_SECRET, audience="https://mamaguard.example.com",
        )
        self.assertEqual(ticket.sub, _PATIENT)

    def test_audience_mismatch(self):
        token = _make_ticket_jwt(aud="https://other.example.com")
        with self.assertRaises(TicketError) as cm:
            decode_permission_ticket(
                token, signing_key=_SECRET, audience="https://mamaguard.example.com",
            )
        self.assertIn("audience", str(cm.exception).lower())

    def test_no_signing_key_raises(self):
        token = _make_ticket_jwt()
        with self.assertRaises(TicketError) as cm:
            decode_permission_ticket(token, signing_key="")
        self.assertIn("no signing key", str(cm.exception).lower())

    def test_scopes_parsed_from_space_delimited(self):
        token = _make_ticket_jwt(scope="patient/Patient.rs patient/Observation.rs patient/Condition.rs")
        ticket = decode_permission_ticket(token, signing_key=_SECRET)
        self.assertEqual(ticket.scopes, frozenset([
            "patient/Patient.rs",
            "patient/Observation.rs",
            "patient/Condition.rs",
        ]))

    def test_empty_scope_string(self):
        token = _make_ticket_jwt(scope="")
        ticket = decode_permission_ticket(token, signing_key=_SECRET)
        self.assertEqual(ticket.scopes, frozenset())

    def test_raw_claims_preserved(self):
        token = _make_ticket_jwt(custom_field="test_value")
        ticket = decode_permission_ticket(token, signing_key=_SECRET)
        self.assertEqual(ticket.raw_claims.get("custom_field"), "test_value")


# ===========================================================================
# 2. Scope Checking
# ===========================================================================


class TestScopeSatisfies(unittest.TestCase):
    """_scope_satisfies — single scope matching."""

    def test_exact_match(self):
        self.assertTrue(_scope_satisfies(
            frozenset(["patient/Observation.rs"]), "patient/Observation.rs",
        ))

    def test_no_match(self):
        self.assertFalse(_scope_satisfies(
            frozenset(["patient/Condition.rs"]), "patient/Observation.rs",
        ))

    def test_wildcard_resource(self):
        self.assertTrue(_scope_satisfies(
            frozenset(["patient/*.rs"]), "patient/Observation.rs",
        ))

    def test_wildcard_wrong_context(self):
        self.assertFalse(_scope_satisfies(
            frozenset(["user/*.rs"]), "patient/Observation.rs",
        ))

    def test_permission_superset_grants(self):
        # "cruds" contains "r" and "s", so should satisfy "rs"
        self.assertTrue(_scope_satisfies(
            frozenset(["patient/Observation.cruds"]), "patient/Observation.rs",
        ))

    def test_permission_superset_for_create(self):
        self.assertTrue(_scope_satisfies(
            frozenset(["patient/RiskAssessment.cruds"]), "patient/RiskAssessment.c",
        ))

    def test_permission_subset_denied(self):
        # "r" alone does not satisfy "rs" (missing "s")
        self.assertFalse(_scope_satisfies(
            frozenset(["patient/Observation.r"]), "patient/Observation.rs",
        ))

    def test_read_does_not_grant_create(self):
        self.assertFalse(_scope_satisfies(
            frozenset(["patient/RiskAssessment.rs"]), "patient/RiskAssessment.c",
        ))

    def test_malformed_required_scope(self):
        self.assertFalse(_scope_satisfies(frozenset(["patient/Observation.rs"]), "malformed"))

    def test_malformed_granted_scope(self):
        self.assertFalse(_scope_satisfies(frozenset(["malformed"]), "patient/Observation.rs"))


class TestCheckToolScope(unittest.TestCase):
    """check_tool_scope — tool-level scope validation."""

    def test_sufficient_scope(self):
        ticket = PermissionTicket(
            sub=_PATIENT, scopes=frozenset(["patient/Observation.rs"]),
            exp=int(time.time()) + 3600,
        )
        self.assertIsNone(check_tool_scope(ticket, "get_bp_trend"))

    def test_insufficient_scope(self):
        ticket = PermissionTicket(
            sub=_PATIENT, scopes=frozenset(["patient/Condition.rs"]),
            exp=int(time.time()) + 3600,
        )
        err = check_tool_scope(ticket, "get_bp_trend")
        self.assertIsNotNone(err)
        self.assertIn("patient/Observation.rs", err)

    def test_partial_scope_denied(self):
        # get_patient_summary needs 4 scopes; grant only 2
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/Patient.rs", "patient/Condition.rs"]),
            exp=int(time.time()) + 3600,
        )
        err = check_tool_scope(ticket, "get_patient_summary")
        self.assertIsNotNone(err)
        self.assertIn("patient/MedicationRequest.rs", err)

    def test_full_scope_for_patient_summary(self):
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset([
                "patient/Patient.rs", "patient/Condition.rs",
                "patient/MedicationRequest.rs", "patient/Observation.rs",
            ]),
            exp=int(time.time()) + 3600,
        )
        self.assertIsNone(check_tool_scope(ticket, "get_patient_summary"))

    def test_wildcard_covers_all_read_tools(self):
        ticket = PermissionTicket(
            sub=_PATIENT, scopes=frozenset(["patient/*.rs"]),
            exp=int(time.time()) + 3600,
        )
        for tool_name, required in TOOL_SCOPES.items():
            if all(".rs" in s for s in required):
                self.assertIsNone(
                    check_tool_scope(ticket, tool_name),
                    f"Wildcard should cover {tool_name}",
                )

    def test_write_tool_scope(self):
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/RiskAssessment.c"]),
            exp=int(time.time()) + 3600,
        )
        self.assertIsNone(check_tool_scope(ticket, "write_risk_assessment"))

    def test_write_tool_denied_with_read_only(self):
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/RiskAssessment.rs"]),
            exp=int(time.time()) + 3600,
        )
        err = check_tool_scope(ticket, "write_risk_assessment")
        self.assertIsNotNone(err)
        self.assertIn("patient/RiskAssessment.c", err)

    def test_care_plan_write_needs_both_goal_and_careplan(self):
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/Goal.c"]),  # missing CarePlan.c
            exp=int(time.time()) + 3600,
        )
        err = check_tool_scope(ticket, "write_care_plan")
        self.assertIsNotNone(err)
        self.assertIn("patient/CarePlan.c", err)

    def test_find_sdoh_resources_no_scope_needed(self):
        ticket = PermissionTicket(
            sub=_PATIENT, scopes=frozenset(),
            exp=int(time.time()) + 3600,
        )
        self.assertIsNone(check_tool_scope(ticket, "find_sdoh_resources"))

    def test_unknown_tool_returns_error(self):
        ticket = PermissionTicket(
            sub=_PATIENT, scopes=frozenset(["patient/*.cruds"]),
            exp=int(time.time()) + 3600,
        )
        err = check_tool_scope(ticket, "nonexistent_tool")
        self.assertIsNotNone(err)
        self.assertIn("Unknown tool", err)


# ===========================================================================
# 3. Tool Scope Mapping Audit
# ===========================================================================


class TestToolScopeMapping(unittest.TestCase):
    """Ensure every tool in the codebase has a scope mapping."""

    def test_all_tools_mapped(self):
        expected_tools = {
            "get_patient_summary", "get_active_medications",
            "get_bp_trend", "get_glucose_trend",
            "get_pregnancy_history", "get_maternal_risk_profile",
            "get_immunization_gaps", "get_developmental_screening_status",
            "get_care_gaps", "get_sdoh_screening", "find_sdoh_resources",
            "write_risk_assessment", "create_communication_request",
            "write_care_plan",
        }
        self.assertEqual(set(TOOL_SCOPES.keys()), expected_tools)

    def test_read_tools_use_rs_scopes(self):
        read_tools = [
            "get_patient_summary", "get_active_medications",
            "get_bp_trend", "get_glucose_trend",
            "get_pregnancy_history", "get_maternal_risk_profile",
            "get_immunization_gaps", "get_developmental_screening_status",
            "get_care_gaps", "get_sdoh_screening",
        ]
        for tool in read_tools:
            for scope in TOOL_SCOPES[tool]:
                self.assertTrue(
                    scope.endswith(".rs"),
                    f"{tool} scope {scope} should end with .rs",
                )

    def test_write_tools_use_c_scopes(self):
        write_tools = [
            "write_risk_assessment", "create_communication_request",
            "write_care_plan",
        ]
        for tool in write_tools:
            for scope in TOOL_SCOPES[tool]:
                self.assertTrue(
                    scope.endswith(".c"),
                    f"{tool} scope {scope} should end with .c",
                )


# ===========================================================================
# 4. enforce_smart_ticket
# ===========================================================================


class TestEnforceSmartTicket(unittest.TestCase):
    """enforce_smart_ticket — full enforcement flow."""

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", False)
    def test_disabled_returns_none(self):
        # No enforcement when feature flag is off
        self.assertIsNone(enforce_smart_ticket({}, "get_bp_trend"))

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    def test_missing_ticket_returns_error(self):
        result = enforce_smart_ticket({}, "get_bp_trend")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "error")
        self.assertIn("required but not present", result["error_message"])

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    def test_invalid_ticket_type_returns_error(self):
        result = enforce_smart_ticket({"smart_ticket": "not-a-ticket"}, "get_bp_trend")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "error")
        self.assertIn("malformed", result["error_message"])

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    def test_patient_mismatch_returns_error(self):
        ticket = PermissionTicket(
            sub="other-patient-id",
            scopes=frozenset(["patient/Observation.rs"]),
            exp=int(time.time()) + 3600,
        )
        state = {"smart_ticket": ticket, "patient_id": _PATIENT}
        result = enforce_smart_ticket(state, "get_bp_trend")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "error")
        self.assertIn("does not match", result["error_message"])

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    def test_expired_in_session_returns_error(self):
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/Observation.rs"]),
            exp=int(time.time()) - 60,  # already expired
        )
        state = {"smart_ticket": ticket, "patient_id": _PATIENT}
        result = enforce_smart_ticket(state, "get_bp_trend")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "error")
        self.assertIn("expired", result["error_message"].lower())

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    def test_insufficient_scope_returns_error(self):
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/Condition.rs"]),  # not Observation
            exp=int(time.time()) + 3600,
        )
        state = {"smart_ticket": ticket, "patient_id": _PATIENT}
        result = enforce_smart_ticket(state, "get_bp_trend")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "error")
        self.assertIn("patient/Observation.rs", result["error_message"])

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    def test_authorized_returns_none(self):
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/Observation.rs"]),
            exp=int(time.time()) + 3600,
        )
        state = {"smart_ticket": ticket, "patient_id": _PATIENT}
        self.assertIsNone(enforce_smart_ticket(state, "get_bp_trend"))

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    def test_authorized_with_wildcard(self):
        ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/*.cruds"]),
            exp=int(time.time()) + 3600,
        )
        state = {"smart_ticket": ticket, "patient_id": _PATIENT}
        # Should authorize any tool
        for tool_name in TOOL_SCOPES:
            self.assertIsNone(
                enforce_smart_ticket(state, tool_name),
                f"Wildcard cruds should authorize {tool_name}",
            )

    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    def test_no_patient_id_in_state_skips_patient_check(self):
        # If patient_id not yet set in state, patient match is skipped
        ticket = PermissionTicket(
            sub="some-other-patient",
            scopes=frozenset(["patient/Observation.rs"]),
            exp=int(time.time()) + 3600,
        )
        state = {"smart_ticket": ticket}  # no patient_id key
        self.assertIsNone(enforce_smart_ticket(state, "get_bp_trend"))


# ===========================================================================
# 5. fhir_hook integration — _extract_smart_ticket
# ===========================================================================


class TestExtractSmartTicket(unittest.TestCase):
    """_extract_smart_ticket — ticket extraction from FHIR context."""

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.fhir_hook.decode_permission_ticket")
    def test_ticket_extracted_and_stored(self, mock_decode):
        mock_ticket = PermissionTicket(
            sub=_PATIENT,
            scopes=frozenset(["patient/Observation.rs"]),
            exp=int(time.time()) + 3600,
        )
        mock_decode.return_value = mock_ticket

        state = {}
        fhir_data = {
            "fhirUrl": "https://fhir.example.com",
            "fhirToken": "tok",
            "patientId": _PATIENT,
            "permissionTicket": "some.jwt.token",
        }
        _extract_smart_ticket(fhir_data, state, {"task_id": "t1"})

        mock_decode.assert_called_once_with("some.jwt.token")
        self.assertIs(state["smart_ticket"], mock_ticket)

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.fhir_hook.decode_permission_ticket")
    def test_decode_failure_logs_but_does_not_block(self, mock_decode):
        mock_decode.side_effect = TicketError("bad token")

        state = {}
        fhir_data = {"permissionTicket": "bad.jwt"}
        _extract_smart_ticket(fhir_data, state, {"task_id": "t2"})

        self.assertNotIn("smart_ticket", state)

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    def test_no_ticket_field_is_noop(self):
        state = {}
        fhir_data = {"fhirUrl": "https://fhir.example.com"}
        _extract_smart_ticket(fhir_data, state, {"task_id": "t3"})
        self.assertNotIn("smart_ticket", state)

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", False)
    def test_disabled_flag_is_noop(self):
        state = {}
        fhir_data = {"permissionTicket": "some.jwt.token"}
        _extract_smart_ticket(fhir_data, state, {"task_id": "t4"})
        self.assertNotIn("smart_ticket", state)

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    def test_empty_ticket_string_is_noop(self):
        state = {}
        fhir_data = {"permissionTicket": ""}
        _extract_smart_ticket(fhir_data, state, {"task_id": "t5"})
        self.assertNotIn("smart_ticket", state)


# ===========================================================================
# 6. End-to-end: ticket JWT → fhir_hook → enforce → tool
# ===========================================================================


class TestEndToEnd(unittest.TestCase):
    """Full pipeline: create JWT, extract via hook, enforce at tool level."""

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_SECRET", _SECRET)
    @patch("mamaguard.shared.fhir_hook.decode_permission_ticket", wraps=decode_permission_ticket)
    def test_valid_ticket_authorizes_tool(self, mock_decode):
        token = _make_ticket_jwt(
            scope="patient/Observation.rs patient/Condition.rs patient/MedicationRequest.rs",
        )
        state = {"patient_id": _PATIENT}
        fhir_data = {"permissionTicket": token}

        _extract_smart_ticket(fhir_data, state, {"task_id": "e2e-1"})
        self.assertIn("smart_ticket", state)

        result = enforce_smart_ticket(state, "get_bp_trend")
        self.assertIsNone(result)

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_SECRET", _SECRET)
    @patch("mamaguard.shared.fhir_hook.decode_permission_ticket", wraps=decode_permission_ticket)
    def test_insufficient_scope_blocks_tool(self, mock_decode):
        token = _make_ticket_jwt(scope="patient/Condition.rs")  # not Observation
        state = {"patient_id": _PATIENT}
        fhir_data = {"permissionTicket": token}

        _extract_smart_ticket(fhir_data, state, {"task_id": "e2e-2"})
        self.assertIn("smart_ticket", state)

        result = enforce_smart_ticket(state, "get_bp_trend")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "error")
        self.assertIn("patient/Observation.rs", result["error_message"])

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.smart_tickets.SMART_TICKETS_SECRET", _SECRET)
    @patch("mamaguard.shared.fhir_hook.decode_permission_ticket", wraps=decode_permission_ticket)
    def test_expired_ticket_blocked_at_enforcement(self, mock_decode):
        token = _make_ticket_jwt(exp=int(time.time()) + 2)
        state = {"patient_id": _PATIENT}
        fhir_data = {"permissionTicket": token}

        _extract_smart_ticket(fhir_data, state, {"task_id": "e2e-3"})
        self.assertIn("smart_ticket", state)

        # Simulate time passing: manually set exp to past
        stale_ticket = PermissionTicket(
            sub=state["smart_ticket"].sub,
            scopes=state["smart_ticket"].scopes,
            exp=int(time.time()) - 10,
            iss=state["smart_ticket"].iss,
        )
        state["smart_ticket"] = stale_ticket

        result = enforce_smart_ticket(state, "get_bp_trend")
        self.assertIsNotNone(result)
        self.assertIn("expired", result["error_message"].lower())


if __name__ == "__main__":
    unittest.main()
