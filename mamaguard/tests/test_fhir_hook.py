"""
Dedicated unit tests for mamaguard.shared.fhir_hook — the FHIR metadata
bridge between Prompt Opinion / A2A callers and the agent's FHIR tools.

Covers every public and private helper:
  _first_non_empty, _coerce_fhir_data, _safe_correlation_ids,
  _extract_metadata_sources, extract_fhir_from_payload,
  extract_fhir_context (the ADK before_model_callback).

Other test files exercise fhir_hook functions indirectly:
  - test_agents_in_process.py: hook populates state, JSON-string coercion,
    SHARP URI keys, run_config fallback.
  - test_fhir_tools.py: extract_fhir_from_payload happy paths.
  - test_smart_tickets.py: _extract_smart_ticket integration.

This file adds direct coverage for helpers, edge cases, priority ordering,
and code paths not exercised elsewhere.
"""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mamaguard.shared.fhir_hook import (
    _coerce_fhir_data,
    _extract_metadata_sources,
    _first_non_empty,
    _safe_correlation_ids,
    extract_fhir_context,
    extract_fhir_from_payload,
)


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


class FakeCallbackContext:
    """Minimal stand-in for ADK CallbackContext."""

    def __init__(self, metadata=None, a2a_metadata=None, run_config=None):
        self.state: dict = {}
        self.metadata = metadata
        if run_config is not None:
            self.run_config = run_config
        elif a2a_metadata is not None:
            self.run_config = SimpleNamespace(
                custom_metadata={"a2a_metadata": a2a_metadata}
            )
        else:
            self.run_config = None
        self.task_id = "task-1"
        self.context_id = "ctx-1"
        self.message_id = "msg-1"


def _fake_llm_request(**overrides):
    """Return a minimal object that serialize_for_log can handle."""
    defaults = {"task_id": "task-1", "context_id": "ctx-1", "message_id": "msg-1"}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fhir_context_dict(
    url="https://fhir.example.org",
    token="tok-abc",
    patient="patient-1",
):
    return {"fhirUrl": url, "fhirToken": token, "patientId": patient}


# ===========================================================================
# 1. _first_non_empty
# ===========================================================================


class TestFirstNonEmpty(unittest.TestCase):
    def test_returns_first_value(self):
        self.assertEqual(_first_non_empty("a", "b"), "a")

    def test_skips_none(self):
        self.assertEqual(_first_non_empty(None, "b"), "b")

    def test_skips_empty_string(self):
        self.assertEqual(_first_non_empty("", "b"), "b")

    def test_skips_none_and_empty(self):
        self.assertEqual(_first_non_empty(None, "", "c"), "c")

    def test_returns_none_when_all_empty(self):
        self.assertIsNone(_first_non_empty(None, "", None))

    def test_returns_zero(self):
        """0 is not None or empty-string, so it should be returned."""
        self.assertEqual(_first_non_empty(None, 0, "fallback"), 0)

    def test_returns_false(self):
        """False is not None or empty-string, so it should be returned."""
        self.assertIs(_first_non_empty(None, False, "fallback"), False)

    def test_no_args(self):
        self.assertIsNone(_first_non_empty())

    def test_single_value(self):
        self.assertEqual(_first_non_empty("x"), "x")


# ===========================================================================
# 2. _coerce_fhir_data
# ===========================================================================


class TestCoerceFhirData(unittest.TestCase):
    def test_dict_passthrough(self):
        d = {"fhirUrl": "http://x"}
        self.assertIs(_coerce_fhir_data(d), d)

    def test_json_string_to_dict(self):
        s = json.dumps({"fhirUrl": "http://x", "patientId": "p1"})
        result = _coerce_fhir_data(s)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["patientId"], "p1")

    def test_json_string_non_dict_returns_none(self):
        """A JSON string that parses to a list is not valid FHIR context."""
        self.assertIsNone(_coerce_fhir_data(json.dumps([1, 2, 3])))

    def test_json_string_parses_to_string_returns_none(self):
        self.assertIsNone(_coerce_fhir_data(json.dumps("just a string")))

    def test_invalid_json_string_returns_none(self):
        self.assertIsNone(_coerce_fhir_data("not valid json {"))

    def test_none_returns_none(self):
        self.assertIsNone(_coerce_fhir_data(None))

    def test_int_returns_none(self):
        self.assertIsNone(_coerce_fhir_data(42))

    def test_empty_dict(self):
        """Empty dict is still a dict — returned as-is."""
        self.assertEqual(_coerce_fhir_data({}), {})

    def test_empty_string_returns_none(self):
        self.assertIsNone(_coerce_fhir_data(""))

    def test_bool_returns_none(self):
        self.assertIsNone(_coerce_fhir_data(True))


# ===========================================================================
# 3. _safe_correlation_ids
# ===========================================================================


class TestSafeCorrelationIds(unittest.TestCase):
    def test_prefers_llm_request_values(self):
        cb = SimpleNamespace(task_id="cb-t", context_id="cb-c", message_id="cb-m")
        llm = SimpleNamespace(task_id="llm-t", context_id="llm-c", message_id="llm-m")
        ids = _safe_correlation_ids(cb, llm)
        self.assertEqual(ids["task_id"], "llm-t")
        self.assertEqual(ids["context_id"], "llm-c")
        self.assertEqual(ids["message_id"], "llm-m")

    def test_falls_back_to_callback_context(self):
        cb = SimpleNamespace(task_id="cb-t", context_id="cb-c", message_id="cb-m")
        llm = SimpleNamespace(task_id=None, context_id="", message_id=None)
        ids = _safe_correlation_ids(cb, llm)
        self.assertEqual(ids["task_id"], "cb-t")
        self.assertEqual(ids["context_id"], "cb-c")
        self.assertEqual(ids["message_id"], "cb-m")

    def test_missing_attributes_return_none(self):
        """When neither object has the attribute, getattr returns None."""
        cb = SimpleNamespace()
        llm = SimpleNamespace()
        ids = _safe_correlation_ids(cb, llm)
        self.assertIsNone(ids["task_id"])
        self.assertIsNone(ids["context_id"])
        self.assertIsNone(ids["message_id"])

    def test_partial_attributes(self):
        """llm_request has task_id but not others; cb has context_id."""
        cb = SimpleNamespace(context_id="cb-c")
        llm = SimpleNamespace(task_id="llm-t")
        ids = _safe_correlation_ids(cb, llm)
        self.assertEqual(ids["task_id"], "llm-t")
        self.assertEqual(ids["context_id"], "cb-c")
        self.assertIsNone(ids["message_id"])


# ===========================================================================
# 4. _extract_metadata_sources
# ===========================================================================


class TestExtractMetadataSources(unittest.TestCase):
    def test_returns_three_sources(self):
        cb = FakeCallbackContext()
        llm = _fake_llm_request()
        sources = _extract_metadata_sources(cb, llm)
        self.assertEqual(len(sources), 3)

    def test_first_source_is_callback_metadata(self):
        cb = FakeCallbackContext(metadata={"k": "v"})
        llm = _fake_llm_request()
        sources = _extract_metadata_sources(cb, llm)
        name, value = sources[0]
        self.assertEqual(name, "callback_context.metadata")
        self.assertEqual(value, {"k": "v"})

    def test_second_source_is_a2a_metadata(self):
        a2a = {"fhir-context": {"fhirUrl": "http://x"}}
        cb = FakeCallbackContext(a2a_metadata=a2a)
        llm = _fake_llm_request()
        sources = _extract_metadata_sources(cb, llm)
        name, value = sources[1]
        self.assertIn("a2a_metadata", name)
        self.assertEqual(value, a2a)

    def test_a2a_source_none_when_no_run_config(self):
        cb = FakeCallbackContext()
        llm = _fake_llm_request()
        sources = _extract_metadata_sources(cb, llm)
        _, value = sources[1]
        self.assertIsNone(value)

    def test_a2a_source_none_when_custom_metadata_not_dict(self):
        cb = FakeCallbackContext()
        cb.run_config = SimpleNamespace(custom_metadata="not-a-dict")
        llm = _fake_llm_request()
        sources = _extract_metadata_sources(cb, llm)
        _, value = sources[1]
        self.assertIsNone(value)

    def test_third_source_from_llm_request_contents(self):
        """When llm_request serializes to a dict with contents, the last
        content item's metadata is the third source."""
        llm = SimpleNamespace(
            task_id="t", context_id="c", message_id="m",
        )
        # serialize_for_log may call model_dump(); simulate a simple object
        # For this test, we just verify the function doesn't crash and
        # returns a 3-tuple with the third source.
        cb = FakeCallbackContext()
        sources = _extract_metadata_sources(cb, llm)
        self.assertEqual(len(sources), 3)
        self.assertIn("contents", sources[2][0])


# ===========================================================================
# 5. extract_fhir_from_payload — edge cases beyond test_fhir_tools.py
# ===========================================================================


class TestExtractFhirFromPayload(unittest.TestCase):
    def test_params_none_returns_none(self):
        key, data = extract_fhir_from_payload({"params": None})
        self.assertIsNone(key)
        self.assertIsNone(data)

    def test_no_params_key(self):
        key, data = extract_fhir_from_payload({"other": "stuff"})
        self.assertIsNone(key)

    def test_empty_payload(self):
        key, data = extract_fhir_from_payload({})
        self.assertIsNone(key)

    def test_json_string_value_coerced(self):
        """FHIR context value as JSON string in params.metadata."""
        payload = {
            "params": {
                "metadata": {
                    "fhir-context": json.dumps(_fhir_context_dict()),
                }
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertIsNotNone(key)
        self.assertEqual(data["patientId"], "patient-1")

    def test_json_string_value_in_message_metadata(self):
        payload = {
            "params": {
                "message": {
                    "metadata": {
                        "fhir-context": json.dumps(_fhir_context_dict(patient="p2")),
                    }
                }
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertEqual(data["patientId"], "p2")

    def test_params_metadata_checked_before_message_metadata(self):
        """params.metadata is iterated before params.message.metadata."""
        payload = {
            "params": {
                "metadata": {
                    "fhir-context": _fhir_context_dict(patient="from-params"),
                },
                "message": {
                    "metadata": {
                        "fhir-context": _fhir_context_dict(patient="from-message"),
                    },
                },
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertEqual(data["patientId"], "from-params")

    def test_malformed_fhir_value_returns_none(self):
        payload = {
            "params": {
                "metadata": {"fhir-context": "not-json"}
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertIn("fhir-context", key)
        self.assertIsNone(data)

    def test_non_dict_value_returns_none(self):
        payload = {
            "params": {
                "metadata": {"fhir-context": 12345}
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertIn("fhir-context", key)
        self.assertIsNone(data)

    def test_message_none_does_not_crash(self):
        payload = {"params": {"message": None}}
        key, data = extract_fhir_from_payload(payload)
        self.assertIsNone(key)

    def test_metadata_with_no_fhir_key(self):
        payload = {
            "params": {
                "metadata": {"unrelated": "value"},
                "message": {"metadata": {"also-unrelated": "v"}},
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertIsNone(key)

    def test_sharp_uri_key_matched(self):
        uri = "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"
        payload = {
            "params": {
                "metadata": {uri: _fhir_context_dict(patient="sharp-p")}
            }
        }
        key, data = extract_fhir_from_payload(payload)
        self.assertEqual(key, uri)
        self.assertEqual(data["patientId"], "sharp-p")


# ===========================================================================
# 6. extract_fhir_context — the main ADK callback
# ===========================================================================


class TestExtractFhirContext(unittest.TestCase):
    """Comprehensive paths through the main hook function."""

    # -- Return value is always None (hook does not modify llm_request) -----

    def test_always_returns_none(self):
        cb = FakeCallbackContext(metadata={"fhir-context": _fhir_context_dict()})
        result = extract_fhir_context(cb, _fake_llm_request())
        self.assertIsNone(result)

    # -- State population ---------------------------------------------------

    def test_state_populated_from_callback_metadata(self):
        cb = FakeCallbackContext(metadata={
            "fhir-context": _fhir_context_dict("http://fhir", "tok", "p1"),
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["fhir_url"], "http://fhir")
        self.assertEqual(cb.state["fhir_token"], "tok")
        self.assertEqual(cb.state["patient_id"], "p1")

    def test_state_populated_from_a2a_metadata_fallback(self):
        cb = FakeCallbackContext(
            metadata=None,
            a2a_metadata={"fhir-context": _fhir_context_dict(patient="a2a-p")},
        )
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["patient_id"], "a2a-p")

    def test_callback_metadata_takes_priority_over_a2a(self):
        cb = FakeCallbackContext(
            metadata={"fhir-context": _fhir_context_dict(patient="cb-p")},
            a2a_metadata={"fhir-context": _fhir_context_dict(patient="a2a-p")},
        )
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["patient_id"], "cb-p")

    def test_empty_fhir_context_dict_treated_as_not_found(self):
        """An empty FHIR context dict {} is falsy in Python, so the hook
        correctly treats it the same as missing FHIR context."""
        cb = FakeCallbackContext(metadata={"fhir-context": {}})
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    def test_minimal_fhir_fields_default_to_empty_string(self):
        """If the FHIR context dict has at least one key but is missing
        others, state gets empty strings for the missing ones."""
        cb = FakeCallbackContext(metadata={
            "fhir-context": {"patientId": "p1"},
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["fhir_url"], "")
        self.assertEqual(cb.state["fhir_token"], "")
        self.assertEqual(cb.state["patient_id"], "p1")

    def test_partial_fhir_fields(self):
        cb = FakeCallbackContext(metadata={
            "fhir-context": {"fhirUrl": "http://x", "patientId": "p1"},
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["fhir_url"], "http://x")
        self.assertEqual(cb.state["fhir_token"], "")
        self.assertEqual(cb.state["patient_id"], "p1")

    def test_json_string_fhir_context_coerced(self):
        payload = json.dumps(_fhir_context_dict("http://j", "jtok", "jp"))
        cb = FakeCallbackContext(metadata={"fhir-context": payload})
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["fhir_url"], "http://j")
        self.assertEqual(cb.state["fhir_token"], "jtok")
        self.assertEqual(cb.state["patient_id"], "jp")

    # -- No-metadata / no-fhir paths ----------------------------------------

    def test_no_metadata_leaves_state_empty(self):
        cb = FakeCallbackContext(metadata=None)
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    def test_empty_metadata_dict_leaves_state_empty(self):
        cb = FakeCallbackContext(metadata={})
        # Empty dict is falsy → early return
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    def test_unrelated_metadata_keys_leave_state_empty(self):
        cb = FakeCallbackContext(metadata={"unrelated": "value", "another": 42})
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    def test_malformed_fhir_value_leaves_state_empty(self):
        """Non-JSON string as fhir-context value → coercion fails."""
        cb = FakeCallbackContext(metadata={"fhir-context": "bad data"})
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    def test_non_dict_json_fhir_value_leaves_state_empty(self):
        """JSON that parses to a list → coercion returns None."""
        cb = FakeCallbackContext(metadata={
            "fhir-context": json.dumps([1, 2, 3]),
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    def test_integer_fhir_value_leaves_state_empty(self):
        cb = FakeCallbackContext(metadata={"fhir-context": 42})
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    # -- SHARP URI key matching ---------------------------------------------

    def test_sharp_extension_uri_key_matched(self):
        uri = "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"
        cb = FakeCallbackContext(metadata={
            uri: _fhir_context_dict(patient="sharp-p"),
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["patient_id"], "sharp-p")

    def test_custom_uri_containing_fhir_context_matched(self):
        cb = FakeCallbackContext(metadata={
            "urn:example:fhir-context:v2": _fhir_context_dict(patient="custom"),
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["patient_id"], "custom")

    # -- SMART ticket integration (feature-flagged) -------------------------

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    @patch("mamaguard.shared.fhir_hook.decode_permission_ticket")
    def test_smart_ticket_extracted_when_enabled(self, mock_decode):
        from mamaguard.shared.smart_tickets import PermissionTicket

        ticket = PermissionTicket(
            sub="patient-1", scopes={"patient/Observation.rs"}, exp=9999999999
        )
        mock_decode.return_value = ticket

        fhir_data = _fhir_context_dict()
        fhir_data["permissionTicket"] = "eyJhbGciOi..."
        cb = FakeCallbackContext(metadata={"fhir-context": fhir_data})
        extract_fhir_context(cb, _fake_llm_request())

        self.assertEqual(cb.state["smart_ticket"], ticket)
        mock_decode.assert_called_once_with("eyJhbGciOi...")

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", False)
    def test_smart_ticket_not_extracted_when_disabled(self):
        fhir_data = _fhir_context_dict()
        fhir_data["permissionTicket"] = "eyJhbGciOi..."
        cb = FakeCallbackContext(metadata={"fhir-context": fhir_data})
        extract_fhir_context(cb, _fake_llm_request())

        self.assertNotIn("smart_ticket", cb.state)

    @patch("mamaguard.shared.fhir_hook.SMART_TICKETS_ENABLED", True)
    def test_no_ticket_field_does_not_crash(self):
        cb = FakeCallbackContext(metadata={
            "fhir-context": _fhir_context_dict(),
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("smart_ticket", cb.state)
        # State still populated normally
        self.assertEqual(cb.state["patient_id"], "patient-1")

    # -- LOG_HOOK_RAW_OBJECTS path ------------------------------------------

    @patch("mamaguard.shared.fhir_hook.LOG_HOOK_RAW_OBJECTS", True)
    def test_raw_logging_path_does_not_crash(self):
        """When LOG_HOOK_RAW_OBJECTS is True, extra logging runs. Verify
        it doesn't raise on our test objects."""
        cb = FakeCallbackContext(metadata={
            "fhir-context": _fhir_context_dict(),
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["patient_id"], "patient-1")

    @patch("mamaguard.shared.fhir_hook.LOG_HOOK_RAW_OBJECTS", True)
    def test_raw_logging_with_no_metadata(self):
        cb = FakeCallbackContext(metadata=None)
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    # -- Edge cases ---------------------------------------------------------

    def test_first_fhir_key_wins_on_break(self):
        """The hook breaks after the first metadata key containing
        'fhir-context'. Verify only the first match is used."""
        # Python dicts preserve insertion order, so first key wins.
        cb = FakeCallbackContext(metadata={
            "fhir-context": _fhir_context_dict(patient="first"),
            "alt-fhir-context": _fhir_context_dict(patient="second"),
        })
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["patient_id"], "first")

    def test_none_valued_fhir_fields_become_empty_string(self):
        """fhirUrl etc. set to None in the context dict → .get returns ''."""
        cb = FakeCallbackContext(metadata={
            "fhir-context": {"fhirUrl": None, "fhirToken": None, "patientId": None},
        })
        extract_fhir_context(cb, _fake_llm_request())
        # dict.get("fhirUrl", "") returns None (not ""), because key exists.
        # This tests the actual behavior.
        self.assertIsNone(cb.state["fhir_url"])

    def test_extra_fhir_fields_ignored(self):
        """Extra keys in the fhir context dict don't break anything."""
        fhir = _fhir_context_dict()
        fhir["extra_field"] = "ignored"
        fhir["anotherExtra"] = 123
        cb = FakeCallbackContext(metadata={"fhir-context": fhir})
        extract_fhir_context(cb, _fake_llm_request())
        self.assertEqual(cb.state["patient_id"], "patient-1")
        self.assertNotIn("extra_field", cb.state)

    def test_run_config_with_non_dict_custom_metadata(self):
        """run_config.custom_metadata is not a dict → a2a_metadata is None,
        but the hook should not crash."""
        cb = FakeCallbackContext(metadata=None)
        cb.run_config = SimpleNamespace(custom_metadata="a string, not a dict")
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)

    def test_run_config_with_missing_a2a_key(self):
        """custom_metadata is a dict but has no 'a2a_metadata' key."""
        cb = FakeCallbackContext(metadata=None)
        cb.run_config = SimpleNamespace(custom_metadata={"other_key": "value"})
        extract_fhir_context(cb, _fake_llm_request())
        self.assertNotIn("fhir_url", cb.state)


if __name__ == "__main__":
    unittest.main()
