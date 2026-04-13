"""
Tests for SHARP context validation in mamaguard.shared.fhir_hook.

Covers validate_sharp_context() and its integration into extract_fhir_context().
"""

import json
import unittest
from types import SimpleNamespace

from mamaguard.shared.fhir_hook import (
    extract_fhir_context,
    validate_sharp_context,
)


# ---------------------------------------------------------------------------
# Helpers / fakes (same pattern as test_fhir_hook.py)
# ---------------------------------------------------------------------------


class FakeCallbackContext:
    def __init__(self, metadata=None, a2a_metadata=None):
        self.state: dict = {}
        self.metadata = metadata
        if a2a_metadata is not None:
            self.run_config = SimpleNamespace(
                custom_metadata={"a2a_metadata": a2a_metadata}
            )
        else:
            self.run_config = None
        self.task_id = "task-1"
        self.context_id = "ctx-1"
        self.message_id = "msg-1"


def _fake_llm_request():
    return SimpleNamespace(task_id="task-1", context_id="ctx-1", message_id="msg-1")


# ===========================================================================
# 1. validate_sharp_context — unit tests
# ===========================================================================


class TestValidateSharpContext(unittest.TestCase):
    """Direct tests for validate_sharp_context()."""

    # -- Valid URLs ----------------------------------------------------------

    def test_valid_https_url(self):
        errors = validate_sharp_context(
            "https://fhir.example.org", "patient-1", "token-abc"
        )
        self.assertEqual(errors, [])

    def test_valid_https_url_with_path(self):
        errors = validate_sharp_context(
            "https://fhir.example.org/fhir/R4", "p1", "tok"
        )
        self.assertEqual(errors, [])

    def test_valid_http_localhost(self):
        errors = validate_sharp_context(
            "http://localhost:8080/fhir", "p1", "tok"
        )
        self.assertEqual(errors, [])

    def test_valid_http_localhost_no_port(self):
        errors = validate_sharp_context(
            "http://localhost/fhir", "p1", "tok"
        )
        self.assertEqual(errors, [])

    def test_valid_http_127_0_0_1(self):
        errors = validate_sharp_context(
            "http://127.0.0.1:8080/fhir", "p1", "tok"
        )
        self.assertEqual(errors, [])

    # -- Invalid URLs -------------------------------------------------------

    def test_http_non_localhost_rejected(self):
        errors = validate_sharp_context(
            "http://fhir.example.org", "p1", "tok"
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("fhir_url", errors[0])
        self.assertIn("https://", errors[0])

    def test_ftp_url_rejected(self):
        errors = validate_sharp_context("ftp://fhir.example.org", "p1", "tok")
        self.assertEqual(len(errors), 1)
        self.assertIn("fhir_url", errors[0])

    def test_bare_hostname_rejected(self):
        errors = validate_sharp_context("fhir.example.org", "p1", "tok")
        self.assertEqual(len(errors), 1)
        self.assertIn("fhir_url", errors[0])

    def test_empty_url_rejected(self):
        errors = validate_sharp_context("", "p1", "tok")
        self.assertEqual(len(errors), 1)
        self.assertIn("fhir_url", errors[0])
        self.assertIn("non-empty", errors[0])

    def test_whitespace_only_url_rejected(self):
        errors = validate_sharp_context("   ", "p1", "tok")
        self.assertEqual(len(errors), 1)
        self.assertIn("fhir_url", errors[0])

    # -- Empty patient_id ---------------------------------------------------

    def test_empty_patient_id_rejected(self):
        errors = validate_sharp_context("https://fhir.example.org", "", "tok")
        self.assertEqual(len(errors), 1)
        self.assertIn("patient_id", errors[0])

    def test_whitespace_patient_id_rejected(self):
        errors = validate_sharp_context("https://fhir.example.org", "  ", "tok")
        self.assertEqual(len(errors), 1)
        self.assertIn("patient_id", errors[0])

    def test_non_string_patient_id_rejected(self):
        errors = validate_sharp_context("https://fhir.example.org", 123, "tok")  # type: ignore[arg-type]
        self.assertEqual(len(errors), 1)
        self.assertIn("patient_id", errors[0])

    # -- Empty fhir_token ---------------------------------------------------

    def test_empty_token_rejected(self):
        errors = validate_sharp_context("https://fhir.example.org", "p1", "")
        self.assertEqual(len(errors), 1)
        self.assertIn("fhir_token", errors[0])

    def test_whitespace_token_rejected(self):
        errors = validate_sharp_context("https://fhir.example.org", "p1", "  ")
        self.assertEqual(len(errors), 1)
        self.assertIn("fhir_token", errors[0])

    def test_non_string_token_rejected(self):
        errors = validate_sharp_context("https://fhir.example.org", "p1", 42)  # type: ignore[arg-type]
        self.assertEqual(len(errors), 1)
        self.assertIn("fhir_token", errors[0])

    # -- Multiple errors ----------------------------------------------------

    def test_all_fields_invalid(self):
        errors = validate_sharp_context("", "", "")
        self.assertEqual(len(errors), 3)

    def test_bad_url_and_empty_patient(self):
        errors = validate_sharp_context("http://external.com", "", "tok")
        self.assertEqual(len(errors), 2)

    def test_none_values_rejected(self):
        errors = validate_sharp_context(None, None, None)  # type: ignore[arg-type]
        self.assertEqual(len(errors), 3)


# ===========================================================================
# 2. Integration: extract_fhir_context stores validation errors in state
# ===========================================================================


class TestExtractFhirContextValidation(unittest.TestCase):
    """Verify that extract_fhir_context calls validation and stores errors."""

    def test_valid_context_no_errors_in_state(self):
        cb = FakeCallbackContext(metadata={
            "fhir-context": {
                "fhirUrl": "https://fhir.example.org",
                "fhirToken": "tok-abc",
                "patientId": "patient-1",
            },
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_context_errors", cb.state)
        self.assertEqual(cb.state["fhir_url"], "https://fhir.example.org")
        self.assertEqual(cb.state["patient_id"], "patient-1")

    def test_http_localhost_no_errors(self):
        cb = FakeCallbackContext(metadata={
            "fhir-context": {
                "fhirUrl": "http://localhost:8080/fhir",
                "fhirToken": "tok",
                "patientId": "p1",
            },
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_context_errors", cb.state)

    def test_invalid_url_stores_errors(self):
        cb = FakeCallbackContext(metadata={
            "fhir-context": {
                "fhirUrl": "http://external.com/fhir",
                "fhirToken": "tok",
                "patientId": "p1",
            },
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertIn("fhir_context_errors", cb.state)
        self.assertEqual(len(cb.state["fhir_context_errors"]), 1)
        self.assertIn("fhir_url", cb.state["fhir_context_errors"][0])
        # Values still stored for downstream inspection
        self.assertEqual(cb.state["fhir_url"], "http://external.com/fhir")

    def test_empty_patient_id_stores_error(self):
        cb = FakeCallbackContext(metadata={
            "fhir-context": {
                "fhirUrl": "https://fhir.example.org",
                "fhirToken": "tok",
                "patientId": "",
            },
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertIn("fhir_context_errors", cb.state)
        self.assertTrue(any("patient_id" in e for e in cb.state["fhir_context_errors"]))

    def test_empty_token_stores_error(self):
        cb = FakeCallbackContext(metadata={
            "fhir-context": {
                "fhirUrl": "https://fhir.example.org",
                "fhirToken": "",
                "patientId": "p1",
            },
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertIn("fhir_context_errors", cb.state)
        self.assertTrue(any("fhir_token" in e for e in cb.state["fhir_context_errors"]))

    def test_missing_all_fields_stores_three_errors(self):
        """FHIR context dict with only a dummy key — all 3 fields default to ''."""
        cb = FakeCallbackContext(metadata={
            "fhir-context": {"dummy": "value"},
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertIn("fhir_context_errors", cb.state)
        self.assertEqual(len(cb.state["fhir_context_errors"]), 3)

    def test_no_fhir_context_key_no_errors(self):
        """When there's no fhir-context key at all, no validation runs."""
        cb = FakeCallbackContext(metadata={"unrelated": "value"})
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_context_errors", cb.state)

    def test_none_fhir_url_in_context(self):
        """fhirUrl is None in the context dict — gets coerced to '' by validation."""
        cb = FakeCallbackContext(metadata={
            "fhir-context": {
                "fhirUrl": None,
                "fhirToken": "tok",
                "patientId": "p1",
            },
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertIn("fhir_context_errors", cb.state)
        self.assertTrue(any("fhir_url" in e for e in cb.state["fhir_context_errors"]))


# ===========================================================================
# 3. Integration: _get_fhir_context surfaces validation errors
# ===========================================================================


class TestGetFhirContextValidationErrors(unittest.TestCase):
    """Verify that _get_fhir_context returns error when state has
    fhir_context_errors."""

    def test_validation_errors_returned(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        tc = SimpleNamespace(state={
            "fhir_url": "http://bad.com/fhir",
            "fhir_token": "tok",
            "patient_id": "p1",
            "fhir_context_errors": ["fhir_url must start with https://"],
        })
        result = _get_fhir_context(tc, "test_tool")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "error")
        self.assertIn("SHARP validation", result["error_message"])

    def test_no_validation_errors_returns_tuple(self):
        from mamaguard.shared.tools.fhir_base import _get_fhir_context

        tc = SimpleNamespace(state={
            "fhir_url": "https://fhir.example.org",
            "fhir_token": "tok",
            "patient_id": "p1",
        })
        result = _get_fhir_context(tc, "test_tool")
        self.assertIsInstance(result, tuple)
        self.assertEqual(result[0], "https://fhir.example.org")


if __name__ == "__main__":
    unittest.main()
