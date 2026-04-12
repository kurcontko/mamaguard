"""Dedicated unit tests for mamaguard/shared/tools/fhir_base.py.

Covers private helpers (_get_fhir_context, _fhir_get, _http_error_result,
_connection_error_result, _coding_display) and public tools (get_patient_summary,
get_active_medications) including error paths, edge cases, and graceful
degradation when downstream FHIR queries fail.
"""

import unittest
from unittest.mock import MagicMock, patch

import httpx


# ---------------------------------------------------------------------------
# Shared mock
# ---------------------------------------------------------------------------

class MockToolContext:
    """Minimal mock for google.adk.tools.ToolContext."""

    def __init__(self, fhir_url="", fhir_token="", patient_id="", **extra):
        self.state = {
            "fhir_url": fhir_url,
            "fhir_token": fhir_token,
            "patient_id": patient_id,
            **extra,
        }


def _valid_ctx(**overrides):
    defaults = dict(
        fhir_url="https://fhir.example.org",
        fhir_token="test-token",
        patient_id="patient-42",
    )
    defaults.update(overrides)
    return MockToolContext(**defaults)


def _make_http_error(status_code: int, body: str = "error body") -> httpx.HTTPStatusError:
    resp = httpx.Response(status_code, text=body, request=httpx.Request("GET", "http://x"))
    return httpx.HTTPStatusError(f"{status_code}", request=resp.request, response=resp)


# ===========================================================================
# _get_fhir_context
# ===========================================================================

class TestGetFhirContextNone(unittest.TestCase):
    """tool_context=None must return an error dict."""

    def test_none_context(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        result = _get_fhir_context(None)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")
        self.assertIn("no tool context", result["error_message"])


class TestGetFhirContextTrailingSlash(unittest.TestCase):
    """fhir_url trailing slash should be stripped."""

    def test_trailing_slash_stripped(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = MockToolContext(
            fhir_url="https://fhir.example.org/",
            fhir_token="tok",
            patient_id="p1",
        )
        result = _get_fhir_context(ctx)
        self.assertIsInstance(result, tuple)
        self.assertEqual(result[0], "https://fhir.example.org")

    def test_multiple_trailing_slashes_stripped(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = MockToolContext(
            fhir_url="https://fhir.example.org///",
            fhir_token="tok",
            patient_id="p1",
        )
        result = _get_fhir_context(ctx)
        self.assertIsInstance(result, tuple)
        self.assertFalse(result[0].endswith("/"))


class TestGetFhirContextMissingFields(unittest.TestCase):
    """All missing-field combinations report correctly."""

    def test_missing_all(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        result = _get_fhir_context(MockToolContext())
        self.assertEqual(result["status"], "error")
        for field in ("fhir_url", "fhir_token", "patient_id"):
            self.assertIn(field, result["error_message"])

    def test_missing_fhir_url_only(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = MockToolContext(fhir_token="tok", patient_id="p1")
        result = _get_fhir_context(ctx)
        self.assertIn("fhir_url", result["error_message"])
        self.assertNotIn("fhir_token", result["error_message"])

    def test_missing_patient_id_only(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = MockToolContext(fhir_url="https://x", fhir_token="tok")
        result = _get_fhir_context(ctx)
        self.assertIn("patient_id", result["error_message"])
        self.assertNotIn("fhir_url", result["error_message"])


class TestGetFhirContextSmartTicket(unittest.TestCase):
    """SMART ticket enforcement when tool_name is provided."""

    @patch("mamaguard.shared.tools.fhir_base.enforce_smart_ticket", return_value=None)
    def test_smart_ticket_passes(self, mock_enforce):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = _valid_ctx()
        result = _get_fhir_context(ctx, tool_name="get_patient_summary")
        self.assertIsInstance(result, tuple)
        mock_enforce.assert_called_once_with(ctx.state, "get_patient_summary")

    @patch("mamaguard.shared.tools.fhir_base.enforce_smart_ticket")
    def test_smart_ticket_blocks(self, mock_enforce):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        err = {"status": "error", "error_message": "scope insufficient"}
        mock_enforce.return_value = err
        ctx = _valid_ctx()
        result = _get_fhir_context(ctx, tool_name="get_bp_trend")
        self.assertEqual(result, err)

    @patch("mamaguard.shared.tools.fhir_base.enforce_smart_ticket")
    def test_no_tool_name_skips_enforcement(self, mock_enforce):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        ctx = _valid_ctx()
        result = _get_fhir_context(ctx)
        self.assertIsInstance(result, tuple)
        mock_enforce.assert_not_called()


# ===========================================================================
# _fhir_get
# ===========================================================================

class TestFhirGet(unittest.TestCase):
    """Low-level HTTP GET wrapper."""

    @patch("mamaguard.shared.tools.fhir_base.httpx.get")
    def test_sends_auth_and_accept_headers(self, mock_get):
        from mamaguard.shared.tools.fhir_base import _fhir_get

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"resourceType": "Patient"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = _fhir_get("https://fhir.example.org", "my-token", "Patient/42")
        self.assertEqual(result, {"resourceType": "Patient"})

        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.args[0], "https://fhir.example.org/Patient/42")
        headers = call_kwargs.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer my-token")
        self.assertEqual(headers["Accept"], "application/fhir+json")

    @patch("mamaguard.shared.tools.fhir_base.httpx.get")
    def test_passes_params(self, mock_get):
        from mamaguard.shared.tools.fhir_base import _fhir_get

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        _fhir_get("https://fhir.example.org", "tok", "Condition", params={"patient": "p1"})
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["params"], {"patient": "p1"})

    @patch("mamaguard.shared.tools.fhir_base.httpx.get")
    def test_uses_timeout(self, mock_get):
        from mamaguard.shared.tools.fhir_base import _fhir_get, _FHIR_TIMEOUT

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        _fhir_get("https://fhir.example.org", "tok", "Patient/1")
        self.assertEqual(mock_get.call_args.kwargs["timeout"], _FHIR_TIMEOUT)

    @patch("mamaguard.shared.tools.fhir_base.httpx.get")
    def test_raises_on_http_error(self, mock_get):
        from mamaguard.shared.tools.fhir_base import _fhir_get

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = _make_http_error(403)
        mock_get.return_value = mock_resp

        with self.assertRaises(httpx.HTTPStatusError):
            _fhir_get("https://fhir.example.org", "tok", "Patient/1")


# ===========================================================================
# _http_error_result / _connection_error_result
# ===========================================================================

class TestHttpErrorResult(unittest.TestCase):

    def test_shape(self):
        from mamaguard.shared.tools.fhir_base import _http_error_result

        exc = _make_http_error(404, "Not Found")
        result = _http_error_result(exc)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 404)
        self.assertIn("404", result["error_message"])

    def test_truncates_long_body(self):
        from mamaguard.shared.tools.fhir_base import _http_error_result

        exc = _make_http_error(500, "x" * 500)
        result = _http_error_result(exc)
        # The error_message includes at most 200 chars of body
        self.assertLessEqual(len(result["error_message"]), 300)

    def test_various_status_codes(self):
        from mamaguard.shared.tools.fhir_base import _http_error_result

        for code in (400, 401, 403, 404, 500, 502, 503):
            exc = _make_http_error(code)
            result = _http_error_result(exc)
            self.assertEqual(result["http_status"], code)
            self.assertIn(str(code), result["error_message"])


class TestConnectionErrorResult(unittest.TestCase):

    def test_shape(self):
        from mamaguard.shared.tools.fhir_base import _connection_error_result

        exc = httpx.ConnectError("Connection refused")
        result = _connection_error_result(exc)
        self.assertEqual(result["status"], "error")
        self.assertIn("Connection refused", result["error_message"])
        self.assertNotIn("http_status", result)

    def test_read_timeout(self):
        from mamaguard.shared.tools.fhir_base import _connection_error_result

        exc = httpx.ReadTimeout("Read timed out")
        result = _connection_error_result(exc)
        self.assertIn("Read timed out", result["error_message"])

    def test_generic_exception(self):
        from mamaguard.shared.tools.fhir_base import _connection_error_result

        result = _connection_error_result(RuntimeError("unexpected"))
        self.assertEqual(result["status"], "error")
        self.assertIn("unexpected", result["error_message"])


# ===========================================================================
# _coding_display
# ===========================================================================

class TestCodingDisplay(unittest.TestCase):

    def test_returns_first_display(self):
        from mamaguard.shared.tools.fhir_base import _coding_display

        codings = [
            {"system": "http://loinc.org", "code": "1234"},
            {"system": "http://snomed.info", "code": "5678", "display": "Hypertension"},
        ]
        self.assertEqual(_coding_display(codings), "Hypertension")

    def test_first_coding_with_display_wins(self):
        from mamaguard.shared.tools.fhir_base import _coding_display

        codings = [
            {"display": "Alpha"},
            {"display": "Beta"},
        ]
        self.assertEqual(_coding_display(codings), "Alpha")

    def test_empty_list(self):
        from mamaguard.shared.tools.fhir_base import _coding_display

        self.assertEqual(_coding_display([]), "Unknown")

    def test_no_display_fields(self):
        from mamaguard.shared.tools.fhir_base import _coding_display

        codings = [{"code": "1234"}, {"code": "5678"}]
        self.assertEqual(_coding_display(codings), "Unknown")

    def test_empty_string_display_skipped(self):
        from mamaguard.shared.tools.fhir_base import _coding_display

        codings = [{"display": ""}, {"display": "Real Name"}]
        self.assertEqual(_coding_display(codings), "Real Name")

    def test_none_display_skipped(self):
        from mamaguard.shared.tools.fhir_base import _coding_display

        codings = [{"display": None}, {"display": "Actual"}]
        self.assertEqual(_coding_display(codings), "Actual")


# ===========================================================================
# get_patient_summary — error paths
# ===========================================================================

class TestGetPatientSummaryErrors(unittest.TestCase):
    """Error paths in get_patient_summary."""

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_http_error(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        mock_fhir_get.side_effect = _make_http_error(403, "Forbidden")
        result = get_patient_summary(_valid_ctx())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 403)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_connect_error(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        mock_fhir_get.side_effect = httpx.ConnectError("Connection refused")
        result = get_patient_summary(_valid_ctx())
        self.assertEqual(result["status"], "error")
        self.assertIn("Connection refused", result["error_message"])
        self.assertNotIn("http_status", result)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_read_timeout(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        mock_fhir_get.side_effect = httpx.ReadTimeout("Read timed out")
        result = get_patient_summary(_valid_ctx())
        self.assertEqual(result["status"], "error")
        self.assertIn("Read timed out", result["error_message"])

    def test_none_tool_context(self):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        result = get_patient_summary(None)
        self.assertEqual(result["status"], "error")
        self.assertIn("no tool context", result["error_message"])


class TestGetPatientSummaryGracefulDegradation(unittest.TestCase):
    """When sub-queries (conditions, meds, vitals) fail, patient summary
    should still return success with empty lists rather than failing entirely."""

    PATIENT = {
        "resourceType": "Patient",
        "id": "p1",
        "name": [{"use": "official", "given": ["Test"], "family": "User"}],
        "birthDate": "2000-01-01",
        "gender": "male",
    }

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_condition_failure_degraded_gracefully(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return self.PATIENT
            if path == "Condition":
                raise httpx.ConnectError("down")
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir_get.side_effect = side_effect
        result = get_patient_summary(_valid_ctx())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["active_conditions"], [])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_medication_failure_degraded_gracefully(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return self.PATIENT
            if path == "MedicationRequest":
                raise httpx.ReadTimeout("timeout")
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir_get.side_effect = side_effect
        result = get_patient_summary(_valid_ctx())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["active_medications"], [])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_vitals_failure_degraded_gracefully(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        def side_effect(fhir_url, token, path, params=None):
            if path.startswith("Patient/"):
                return self.PATIENT
            if path == "Observation":
                raise RuntimeError("unexpected error")
            return {"resourceType": "Bundle", "entry": []}

        mock_fhir_get.side_effect = side_effect
        result = get_patient_summary(_valid_ctx())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["recent_vitals"], [])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_all_subqueries_fail_still_success(self, mock_fhir_get):
        """If Patient works but all three sub-queries fail, still returns success."""
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        call_count = [0]

        def side_effect(fhir_url, token, path, params=None):
            call_count[0] += 1
            if path.startswith("Patient/"):
                return self.PATIENT
            raise httpx.ConnectError("all down")

        mock_fhir_get.side_effect = side_effect
        result = get_patient_summary(_valid_ctx())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["active_conditions"], [])
        self.assertEqual(result["active_medications"], [])
        self.assertEqual(result["recent_vitals"], [])
        # Patient + Condition + MedicationRequest + Observation = 4 calls
        self.assertEqual(call_count[0], 4)


# ===========================================================================
# get_patient_summary — edge cases
# ===========================================================================

class TestGetPatientSummaryEdgeCases(unittest.TestCase):
    """Edge cases in patient data parsing."""

    def _run_with_patient(self, patient_data):
        """Helper: run get_patient_summary with custom Patient resource, empty sub-queries."""
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_fhir_get:
            def side_effect(fhir_url, token, path, params=None):
                if path.startswith("Patient/"):
                    return patient_data
                return {"resourceType": "Bundle", "entry": []}

            mock_fhir_get.side_effect = side_effect
            return get_patient_summary(_valid_ctx())

    def test_no_name_array(self):
        result = self._run_with_patient({"resourceType": "Patient", "id": "p1"})
        self.assertEqual(result["status"], "success")
        # Empty name list → falls back to empty dict → "Unknown" or empty
        # The code does: names[0] if names else {} → official.get("given", []) etc.
        self.assertIn("name", result)

    def test_non_official_name_fallback(self):
        """When no name has use=official, falls back to first name."""
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "usual", "given": ["Nickname"], "family": "Smith"}],
        })
        self.assertEqual(result["name"], "Nickname Smith")

    def test_name_with_only_family(self):
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "official", "family": "Solo"}],
        })
        self.assertEqual(result["name"], "Solo")

    def test_name_with_multiple_given(self):
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "official", "given": ["Maria", "Elena"], "family": "Santos"}],
        })
        self.assertEqual(result["name"], "Maria Elena Santos")

    def test_no_address(self):
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "official", "given": ["X"], "family": "Y"}],
        })
        self.assertEqual(result["status"], "success")
        self.assertNotIn("address", result)

    def test_no_telecom(self):
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "official", "given": ["X"], "family": "Y"}],
        })
        self.assertEqual(result["contacts"], [])

    def test_no_communication(self):
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "official", "given": ["X"], "family": "Y"}],
        })
        self.assertIsNone(result["language"])

    def test_language_from_coding_display(self):
        """Language falls back to coding display when text is absent."""
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "official", "given": ["X"], "family": "Y"}],
            "communication": [{"language": {"coding": [{"display": "Spanish"}]}}],
        })
        self.assertEqual(result["language"], "Spanish")

    def test_language_text_preferred_over_coding(self):
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "official", "given": ["X"], "family": "Y"}],
            "communication": [{"language": {"text": "French", "coding": [{"display": "fra"}]}}],
        })
        self.assertEqual(result["language"], "French")

    def test_no_marital_status(self):
        result = self._run_with_patient({
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"use": "official", "given": ["X"], "family": "Y"}],
        })
        self.assertIsNone(result["marital_status"])

    def test_condition_with_coding_only(self):
        """Condition with coding but no text uses _coding_display fallback."""
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_fhir_get:
            def side_effect(fhir_url, token, path, params=None):
                if path.startswith("Patient/"):
                    return {
                        "resourceType": "Patient", "id": "p1",
                        "name": [{"use": "official", "given": ["X"], "family": "Y"}],
                    }
                if path == "Condition":
                    return {
                        "resourceType": "Bundle",
                        "entry": [{
                            "resource": {
                                "code": {"coding": [{"display": "Essential HTN"}]},
                                "onsetPeriod": {"start": "2020-01-01"},
                            }
                        }],
                    }
                return {"resourceType": "Bundle", "entry": []}

            mock_fhir_get.side_effect = side_effect
            result = get_patient_summary(_valid_ctx())

        self.assertEqual(result["active_conditions"][0]["condition"], "Essential HTN")
        self.assertEqual(result["active_conditions"][0]["onset"], "2020-01-01")

    def test_condition_with_onset_period(self):
        """Condition uses onsetPeriod.start when onsetDateTime is absent."""
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_fhir_get:
            def side_effect(fhir_url, token, path, params=None):
                if path.startswith("Patient/"):
                    return {
                        "resourceType": "Patient", "id": "p1",
                        "name": [{"use": "official", "given": ["X"], "family": "Y"}],
                    }
                if path == "Condition":
                    return {
                        "resourceType": "Bundle",
                        "entry": [{
                            "resource": {
                                "code": {"text": "GDM"},
                                "onsetPeriod": {"start": "2025-06-01"},
                            }
                        }],
                    }
                return {"resourceType": "Bundle", "entry": []}

            mock_fhir_get.side_effect = side_effect
            result = get_patient_summary(_valid_ctx())

        self.assertEqual(result["active_conditions"][0]["onset"], "2025-06-01")


class TestGetPatientSummaryVitalsEdgeCases(unittest.TestCase):
    """Edge cases in vitals parsing within get_patient_summary."""

    PATIENT = {
        "resourceType": "Patient", "id": "p1",
        "name": [{"use": "official", "given": ["X"], "family": "Y"}],
    }

    def _run_with_vitals(self, vitals_entries):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_fhir_get:
            def side_effect(fhir_url, token, path, params=None):
                if path.startswith("Patient/"):
                    return self.PATIENT
                if path == "Observation":
                    return {"resourceType": "Bundle", "entry": vitals_entries}
                return {"resourceType": "Bundle", "entry": []}

            mock_fhir_get.side_effect = side_effect
            return get_patient_summary(_valid_ctx())

    def test_vital_with_value_quantity(self):
        result = self._run_with_vitals([{
            "resource": {
                "code": {"text": "Heart Rate"},
                "effectiveDateTime": "2024-01-01",
                "valueQuantity": {"value": 72, "unit": "bpm"},
            }
        }])
        vital = result["recent_vitals"][0]
        self.assertEqual(vital["observation"], "Heart Rate")
        self.assertEqual(vital["value"], 72)
        self.assertEqual(vital["unit"], "bpm")
        self.assertIsNone(vital["components"])

    def test_vital_with_value_codeable_concept(self):
        result = self._run_with_vitals([{
            "resource": {
                "code": {"text": "Tobacco Use"},
                "effectiveDateTime": "2024-01-01",
                "valueCodeableConcept": {"text": "Never smoker"},
            }
        }])
        vital = result["recent_vitals"][0]
        self.assertEqual(vital["value"], "Never smoker")
        self.assertIsNone(vital["unit"])

    def test_vital_with_value_codeable_concept_coding_fallback(self):
        result = self._run_with_vitals([{
            "resource": {
                "code": {"text": "Tobacco Use"},
                "effectiveDateTime": "2024-01-01",
                "valueCodeableConcept": {"coding": [{"display": "Former smoker"}]},
            }
        }])
        vital = result["recent_vitals"][0]
        self.assertEqual(vital["value"], "Former smoker")

    def test_vital_with_no_value(self):
        """Vital with neither valueQuantity nor valueCodeableConcept."""
        result = self._run_with_vitals([{
            "resource": {
                "code": {"text": "Panel"},
                "effectiveDateTime": "2024-01-01",
                "component": [
                    {
                        "code": {"text": "Systolic"},
                        "valueQuantity": {"value": 120, "unit": "mmHg"},
                    },
                ],
            }
        }])
        vital = result["recent_vitals"][0]
        self.assertIsNone(vital["value"])
        self.assertIsNone(vital["unit"])
        self.assertIsNotNone(vital["components"])
        self.assertEqual(len(vital["components"]), 1)

    def test_vital_code_from_coding(self):
        """Vital code uses _coding_display when text is absent."""
        result = self._run_with_vitals([{
            "resource": {
                "code": {"coding": [{"display": "Body Weight"}]},
                "effectiveDateTime": "2024-01-01",
                "valueQuantity": {"value": 68, "unit": "kg"},
            }
        }])
        self.assertEqual(result["recent_vitals"][0]["observation"], "Body Weight")

    def test_vital_quantity_code_fallback(self):
        """valueQuantity.code used when unit is absent."""
        result = self._run_with_vitals([{
            "resource": {
                "code": {"text": "Temp"},
                "effectiveDateTime": "2024-01-01",
                "valueQuantity": {"value": 37.0, "code": "Cel"},
            }
        }])
        self.assertEqual(result["recent_vitals"][0]["unit"], "Cel")

    def test_component_code_from_coding(self):
        """Component code uses _coding_display when text is absent."""
        result = self._run_with_vitals([{
            "resource": {
                "code": {"text": "BP"},
                "effectiveDateTime": "2024-01-01",
                "component": [
                    {
                        "code": {"coding": [{"display": "Systolic BP"}]},
                        "valueQuantity": {"value": 130, "unit": "mmHg"},
                    },
                ],
            }
        }])
        comp = result["recent_vitals"][0]["components"][0]
        self.assertEqual(comp["name"], "Systolic BP")

    def test_empty_vitals_bundle(self):
        result = self._run_with_vitals([])
        self.assertEqual(result["recent_vitals"], [])


class TestGetPatientSummaryMedicationEdgeCases(unittest.TestCase):
    """Edge cases in medication parsing within get_patient_summary."""

    PATIENT = {
        "resourceType": "Patient", "id": "p1",
        "name": [{"use": "official", "given": ["X"], "family": "Y"}],
    }

    def _run_with_meds(self, med_entries):
        from mamaguard.shared.tools.fhir_base import get_patient_summary

        with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_fhir_get:
            def side_effect(fhir_url, token, path, params=None):
                if path.startswith("Patient/"):
                    return self.PATIENT
                if path == "MedicationRequest":
                    return {"resourceType": "Bundle", "entry": med_entries}
                return {"resourceType": "Bundle", "entry": []}

            mock_fhir_get.side_effect = side_effect
            return get_patient_summary(_valid_ctx())

    def test_medication_reference_not_reached_without_concept(self):
        """When medicationCodeableConcept is absent, _coding_display([]) returns
        "Unknown" (truthy) which short-circuits the or-chain before reaching
        medicationReference.  This pins the current behavior."""
        result = self._run_with_meds([{
            "resource": {
                "medicationReference": {"display": "Metformin Oral"},
                "dosageInstruction": [{"text": "Once daily"}],
            }
        }])
        # medicationReference is unreachable because _coding_display([]) → "Unknown"
        self.assertEqual(result["active_medications"][0]["medication"], "Unknown")

    def test_medication_coding_fallback(self):
        """When medicationCodeableConcept has no text, uses coding display."""
        result = self._run_with_meds([{
            "resource": {
                "medicationCodeableConcept": {
                    "coding": [{"display": "Lisinopril 10 MG"}],
                },
                "dosageInstruction": [{"text": "Once daily"}],
            }
        }])
        self.assertEqual(result["active_medications"][0]["medication"], "Lisinopril 10 MG")

    def test_medication_no_dosage(self):
        result = self._run_with_meds([{
            "resource": {
                "medicationCodeableConcept": {"text": "Aspirin"},
            }
        }])
        self.assertEqual(result["active_medications"][0]["dosage"], "Not specified")

    def test_medication_empty_dosage_text(self):
        result = self._run_with_meds([{
            "resource": {
                "medicationCodeableConcept": {"text": "Aspirin"},
                "dosageInstruction": [{"text": "Take as needed"}],
            }
        }])
        self.assertEqual(result["active_medications"][0]["dosage"], "Take as needed")

    def test_empty_medication_bundle(self):
        result = self._run_with_meds([])
        self.assertEqual(result["active_medications"], [])


# ===========================================================================
# get_active_medications — error paths
# ===========================================================================

class TestGetActiveMedicationsErrors(unittest.TestCase):

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_http_error(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.side_effect = _make_http_error(500, "Internal Server Error")
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 500)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_connect_error(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.side_effect = httpx.ConnectError("refused")
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["status"], "error")
        self.assertIn("refused", result["error_message"])
        self.assertNotIn("http_status", result)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_read_timeout(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.side_effect = httpx.ReadTimeout("timed out")
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["status"], "error")

    def test_none_context(self):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        result = get_active_medications(None)
        self.assertEqual(result["status"], "error")

    def test_missing_credentials(self):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        result = get_active_medications(MockToolContext())
        self.assertEqual(result["status"], "error")


class TestGetActiveMedicationsEdgeCases(unittest.TestCase):

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_empty_bundle(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {"resourceType": "Bundle", "entry": []}
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["medications"], [])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_bundle_without_entry_key(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {"resourceType": "Bundle"}
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["count"], 0)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_medication_reference_not_reached_without_concept(self, mock_fhir_get):
        """medicationReference is unreachable when medicationCodeableConcept is
        absent because _coding_display([]) returns "Unknown" (truthy), short-
        circuiting the or-chain.  This pins the current behavior."""
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{
                "resource": {
                    "medicationReference": {"display": "Insulin Glargine"},
                    "status": "active",
                    "authoredOn": "2023-06-15",
                    "requester": {"display": "Dr. Jones"},
                }
            }],
        }
        result = get_active_medications(_valid_ctx())
        # medicationReference never reached — _coding_display([]) → "Unknown"
        self.assertEqual(result["medications"][0]["medication"], "Unknown")
        self.assertEqual(result["medications"][0]["status"], "active")
        self.assertEqual(result["medications"][0]["authored_on"], "2023-06-15")
        self.assertEqual(result["medications"][0]["requester"], "Dr. Jones")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_medication_coding_fallback(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{
                "resource": {
                    "medicationCodeableConcept": {
                        "coding": [{"display": "Amlodipine 5mg"}],
                    },
                    "status": "active",
                }
            }],
        }
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["medications"][0]["medication"], "Amlodipine 5mg")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_medication_unknown_fallback(self, mock_fhir_get):
        """When both medicationCodeableConcept and medicationReference are absent."""
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{"resource": {"status": "active"}}],
        }
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["medications"][0]["medication"], "Unknown")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_missing_dosage(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{
                "resource": {
                    "medicationCodeableConcept": {"text": "Aspirin"},
                    "status": "active",
                }
            }],
        }
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["medications"][0]["dosage"], "Not specified")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_missing_requester(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{
                "resource": {
                    "medicationCodeableConcept": {"text": "Med"},
                    "status": "active",
                }
            }],
        }
        result = get_active_medications(_valid_ctx())
        self.assertIsNone(result["medications"][0]["requester"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_missing_authored_on(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{
                "resource": {
                    "medicationCodeableConcept": {"text": "Med"},
                    "status": "active",
                }
            }],
        }
        result = get_active_medications(_valid_ctx())
        self.assertIsNone(result["medications"][0]["authored_on"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_patient_id_in_result(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {"resourceType": "Bundle", "entry": []}
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["patient_id"], "patient-42")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_dosage_no_text_fallback(self, mock_fhir_get):
        """dosageInstruction exists but entry has no 'text' key."""
        from mamaguard.shared.tools.fhir_base import get_active_medications

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{
                "resource": {
                    "medicationCodeableConcept": {"text": "Med"},
                    "status": "active",
                    "dosageInstruction": [{"route": {"text": "oral"}}],
                }
            }],
        }
        result = get_active_medications(_valid_ctx())
        self.assertEqual(result["medications"][0]["dosage"], "No dosage text")


# ===========================================================================
# find_linked_newborn
# ===========================================================================

class TestFindLinkedNewborn(unittest.TestCase):
    """Tests for find_linked_newborn tool."""

    CHILD_RELATED_PERSON = {
        "resourceType": "RelatedPerson",
        "id": "rp-maria-lucas-001",
        "patient": {"reference": "Patient/bench-maria-001"},
        "relationship": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                "code": "CHILD",
                "display": "child",
            }],
        }],
        "name": [{"family": "Santos", "given": ["Lucas"]}],
        "birthDate": "2026-02-09",
        "gender": "male",
        "identifier": [{
            "system": "urn:mamaguard:linked-patient-id",
            "value": "bench-baby-santos-001",
        }],
    }

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_finds_linked_child(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{"resource": self.CHILD_RELATED_PERSON}],
        }
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["mother_patient_id"], "bench-maria-001")
        self.assertEqual(result["count"], 1)
        child = result["linked_newborns"][0]
        self.assertEqual(child["child_patient_id"], "bench-baby-santos-001")
        self.assertEqual(child["name"], "Lucas Santos")
        self.assertEqual(child["birth_date"], "2026-02-09")
        self.assertEqual(child["gender"], "male")
        self.assertEqual(child["related_person_id"], "rp-maria-lucas-001")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_empty_bundle_no_children(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        mock_fhir_get.return_value = {"resourceType": "Bundle", "entry": []}
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["linked_newborns"], [])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_filters_non_child_relationships(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        spouse_rp = {
            "resourceType": "RelatedPerson",
            "id": "rp-spouse",
            "relationship": [{
                "coding": [{"code": "SPS", "display": "spouse"}],
            }],
            "name": [{"family": "Santos", "given": ["Carlos"]}],
        }
        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": spouse_rp},
                {"resource": self.CHILD_RELATED_PERSON},
            ],
        }
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["linked_newborns"][0]["name"], "Lucas Santos")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_recognizes_son_relationship_code(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        son_rp = {
            "resourceType": "RelatedPerson",
            "id": "rp-son",
            "relationship": [{"coding": [{"code": "SON"}]}],
            "name": [{"family": "Santos", "given": ["Lucas"]}],
            "identifier": [{
                "system": "urn:mamaguard:linked-patient-id",
                "value": "bench-baby-santos-001",
            }],
        }
        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{"resource": son_rp}],
        }
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["count"], 1)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_recognizes_dau_relationship_code(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        dau_rp = {
            "resourceType": "RelatedPerson",
            "id": "rp-dau",
            "relationship": [{"coding": [{"code": "DAU"}]}],
            "name": [{"family": "Smith", "given": ["Emma"]}],
            "identifier": [{
                "system": "urn:mamaguard:linked-patient-id",
                "value": "baby-emma-001",
            }],
        }
        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{"resource": dau_rp}],
        }
        result = find_linked_newborn("mother-001", tool_context=_valid_ctx())
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["linked_newborns"][0]["name"], "Emma Smith")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_missing_identifier_returns_none_patient_id(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        rp_no_id = {
            "resourceType": "RelatedPerson",
            "id": "rp-no-link",
            "relationship": [{"coding": [{"code": "CHILD"}]}],
            "name": [{"family": "Santos", "given": ["Lucas"]}],
        }
        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{"resource": rp_no_id}],
        }
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["count"], 1)
        self.assertIsNone(result["linked_newborns"][0]["child_patient_id"])

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_missing_name_returns_unknown(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        rp_no_name = {
            "resourceType": "RelatedPerson",
            "id": "rp-anon",
            "relationship": [{"coding": [{"code": "CHILD"}]}],
            "identifier": [{
                "system": "urn:mamaguard:linked-patient-id",
                "value": "baby-001",
            }],
        }
        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [{"resource": rp_no_name}],
        }
        result = find_linked_newborn("mother-001", tool_context=_valid_ctx())
        self.assertEqual(result["linked_newborns"][0]["name"], "Unknown")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_http_error(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        mock_fhir_get.side_effect = _make_http_error(500, "Server Error")
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 500)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_connect_error(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        mock_fhir_get.side_effect = httpx.ConnectError("connection refused")
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["status"], "error")
        self.assertIn("connection refused", result["error_message"])

    def test_missing_context(self):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        result = find_linked_newborn("bench-maria-001", tool_context=None)
        self.assertEqual(result["status"], "error")

    def test_missing_credentials(self):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        result = find_linked_newborn("bench-maria-001", tool_context=MockToolContext())
        self.assertEqual(result["status"], "error")

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_bundle_without_entry_key(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        mock_fhir_get.return_value = {"resourceType": "Bundle"}
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 0)

    @patch("mamaguard.shared.tools.fhir_base._fhir_get")
    def test_multiple_children(self, mock_fhir_get):
        from mamaguard.shared.tools.fhir_base import find_linked_newborn

        child2 = {
            "resourceType": "RelatedPerson",
            "id": "rp-child2",
            "relationship": [{"coding": [{"code": "CHILD"}]}],
            "name": [{"family": "Santos", "given": ["Sofia"]}],
            "birthDate": "2024-05-01",
            "gender": "female",
            "identifier": [{
                "system": "urn:mamaguard:linked-patient-id",
                "value": "bench-sofia-001",
            }],
        }
        mock_fhir_get.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": self.CHILD_RELATED_PERSON},
                {"resource": child2},
            ],
        }
        result = find_linked_newborn("bench-maria-001", tool_context=_valid_ctx())
        self.assertEqual(result["count"], 2)
        names = {c["name"] for c in result["linked_newborns"]}
        self.assertEqual(names, {"Lucas Santos", "Sofia Santos"})


if __name__ == "__main__":
    unittest.main()
