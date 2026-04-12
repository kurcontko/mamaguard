"""
Unit tests for ``mamaguard.shared.logging_utils``.

`logging_utils` is tiny but load-bearing: every agent module, middleware, and
hook goes through ``configure_logging`` at startup and through ``redact_headers``
/ ``token_fingerprint`` on every request. Until now it had zero direct tests —
only a glancing docstring mention in ``test_agents_in_process.py``. These tests
pin its externally-observable behaviour so a future refactor can't silently
change the log wire format (ANSI colours, redaction marker shape, fingerprint
shape).

Scope:
  - ``_AnsiColorFormatter.format`` — colour codes per level + unknown level
    fallback + ``record.levelname`` restored even when the parent formatter
    raises.
  - ``configure_logging`` — idempotent attach, level + propagation config.
  - ``safe_pretty_json`` — happy path, ``default=str`` fallback, total-fail
    fallback to ``str()`` via the exception path.
  - ``serialize_for_log`` — None, primitives, containers, Pydantic-like
    ``model_dump(mode="json")``, ``TypeError`` fallback, exception fallback,
    generic-object ``str`` fallback.
  - ``redact_headers`` — case-insensitive sensitive-key redaction, non-dict
    passthrough, len annotation.
  - ``token_fingerprint`` — empty string, non-empty shape + determinism.

``_enable_windows_ansi`` is Windows-only and unsafe to exercise under Linux;
it's intentionally out of scope.
"""

from __future__ import annotations

import hashlib
import logging
import unittest

from mamaguard.shared import logging_utils as lu
from mamaguard.shared.logging_utils import (
    _AnsiColorFormatter,
    configure_logging,
    redact_headers,
    redact_payload,
    safe_pretty_json,
    serialize_for_log,
    token_fingerprint,
)


# ─────────────────────────────────────────────────────────────────────────────
# _AnsiColorFormatter.format
# ─────────────────────────────────────────────────────────────────────────────
class TestAnsiColorFormatter(unittest.TestCase):
    def _make_record(self, level: int, msg: str = "hello") -> logging.LogRecord:
        return logging.LogRecord(
            name="mamaguard.test",
            level=level,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_known_levels_wrap_levelname_in_ansi_codes(self):
        fmt = _AnsiColorFormatter("%(levelname)s %(message)s")
        cases = {
            logging.DEBUG: "\x1b[36m",
            logging.INFO: "\x1b[32m",
            logging.WARNING: "\x1b[33m",
            logging.ERROR: "\x1b[31m",
            logging.CRITICAL: "\x1b[35m",
        }
        for level, code in cases.items():
            record = self._make_record(level, msg="hi")
            out = fmt.format(record)
            self.assertIn(code, out, f"missing colour code for {logging.getLevelName(level)}")
            self.assertIn("\x1b[0m", out, "missing RESET code")
            self.assertIn("hi", out)

    def test_known_level_restores_original_levelname(self):
        fmt = _AnsiColorFormatter("%(levelname)s %(message)s")
        record = self._make_record(logging.WARNING)
        self.assertEqual(record.levelname, "WARNING")
        fmt.format(record)
        # After format returns, the record must be re-usable by other handlers
        # that render plain text.
        self.assertEqual(record.levelname, "WARNING")

    def test_unknown_level_emits_no_colour_codes(self):
        fmt = _AnsiColorFormatter("%(levelname)s %(message)s")
        # Custom numeric level with no colour mapping — should pass through
        # untouched (no leading \x1b escape).
        record = self._make_record(42, msg="unknown")
        record.levelname = "TRACE"
        out = fmt.format(record)
        self.assertNotIn("\x1b[", out)
        self.assertIn("TRACE", out)
        self.assertIn("unknown", out)
        # And levelname must still be restored.
        self.assertEqual(record.levelname, "TRACE")

    def test_levelname_restored_even_when_super_format_raises(self):
        """The try/finally contract: if the parent Formatter blows up, the
        record's levelname must still come back clean so a chained handler
        doesn't render ``\x1b[31mERROR\x1b[0m`` as plain text."""
        # Format string references an attribute that doesn't exist on the record,
        # which makes logging.Formatter.format raise KeyError during %-formatting.
        fmt = _AnsiColorFormatter("%(levelname)s %(nope)s")
        record = self._make_record(logging.ERROR)
        original = record.levelname
        with self.assertRaises(Exception):
            fmt.format(record)
        self.assertEqual(record.levelname, original)


# ─────────────────────────────────────────────────────────────────────────────
# configure_logging
# ─────────────────────────────────────────────────────────────────────────────
class TestConfigureLogging(unittest.TestCase):
    def setUp(self):
        # Each test gets its own throwaway logger name so we don't leak
        # handlers across tests or pollute the real "mamaguard" logger.
        self.pkg = f"mamaguard_test_{self.id()}"
        logger = logging.getLogger(self.pkg)
        # Clean slate — removing any handlers from prior runs in the same
        # process.
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger.propagate = True
        logger.setLevel(logging.NOTSET)

    def tearDown(self):
        logger = logging.getLogger(self.pkg)
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger.propagate = True

    def test_first_call_attaches_one_handler_and_sets_level(self):
        configure_logging(self.pkg)
        logger = logging.getLogger(self.pkg)
        self.assertEqual(len(logger.handlers), 1)
        self.assertEqual(logger.level, logging.INFO)
        self.assertFalse(logger.propagate)
        handler = logger.handlers[0]
        self.assertIsInstance(handler, logging.StreamHandler)
        self.assertIsInstance(handler.formatter, _AnsiColorFormatter)

    def test_repeat_call_is_noop(self):
        configure_logging(self.pkg)
        configure_logging(self.pkg)
        configure_logging(self.pkg)
        logger = logging.getLogger(self.pkg)
        self.assertEqual(
            len(logger.handlers),
            1,
            "configure_logging must short-circuit when handlers are already attached",
        )


# ─────────────────────────────────────────────────────────────────────────────
# safe_pretty_json
# ─────────────────────────────────────────────────────────────────────────────
class TestSafePrettyJson(unittest.TestCase):
    def test_serialisable_value_roundtrips_as_indented_json(self):
        out = safe_pretty_json({"b": 2, "a": 1})
        # sort_keys=True is part of the observable contract — downstream log
        # diffs rely on deterministic ordering.
        self.assertIn('"a": 1', out)
        self.assertIn('"b": 2', out)
        self.assertLess(out.index('"a"'), out.index('"b"'))
        self.assertIn("\n", out)  # indent=2

    def test_nonserialisable_object_falls_back_via_default_str(self):
        class Opaque:
            def __str__(self) -> str:
                return "<Opaque-42>"

        out = safe_pretty_json({"thing": Opaque()})
        # default=str triggers inside json.dumps, so this is still valid JSON
        # containing the __str__ value rather than raising.
        self.assertIn("<Opaque-42>", out)
        self.assertIn('"thing"', out)

    def test_total_failure_falls_back_to_str_of_value(self):
        class Exploding:
            def __repr__(self) -> str:  # pragma: no cover - called only via str
                return "Exploding()"

            def __str__(self) -> str:
                return "Exploding()"

            def __iter__(self):
                # json.dumps probes common magic methods; the actual failure
                # path is harder to reach cleanly, so we use a value that json
                # can't serialise AND provides a usable ``str`` fallback.
                raise TypeError("no iter")

        # A set of unserialisable objects: json.dumps with default=str will
        # still succeed because default=str is applied. To reach the bare
        # ``except`` branch we feed json.dumps something that raises from
        # inside ``default`` itself: a ``default`` callable isn't user-supplied
        # here, so we instead pass a value whose ``str()`` also raises during
        # the default attempt. Simplest reliable way: patch json.dumps to
        # raise.
        import json as _json

        real_dumps = _json.dumps

        def boom(*args, **kwargs):
            raise ValueError("forced")

        _json.dumps = boom  # type: ignore[assignment]
        try:
            out = safe_pretty_json({"k": "v"})
        finally:
            _json.dumps = real_dumps  # type: ignore[assignment]
        self.assertEqual(out, str({"k": "v"}))


# ─────────────────────────────────────────────────────────────────────────────
# serialize_for_log
# ─────────────────────────────────────────────────────────────────────────────
class TestSerializeForLog(unittest.TestCase):
    def test_none_passthrough(self):
        self.assertIsNone(serialize_for_log(None))

    def test_primitive_passthrough(self):
        self.assertEqual(serialize_for_log("abc"), "abc")
        self.assertEqual(serialize_for_log(3), 3)
        self.assertEqual(serialize_for_log(3.14), 3.14)
        self.assertIs(serialize_for_log(True), True)

    def test_container_passthrough(self):
        self.assertEqual(serialize_for_log([1, 2]), [1, 2])
        self.assertEqual(serialize_for_log({"a": 1}), {"a": 1})
        self.assertEqual(serialize_for_log((1, 2)), (1, 2))

    def test_pydantic_like_model_dump_json_mode(self):
        class FakeModel:
            calls: list[dict] = []

            def model_dump(self, mode=None, **kwargs):
                FakeModel.calls.append({"mode": mode, **kwargs})
                return {"fake": True, "mode": mode}

        FakeModel.calls = []
        out = serialize_for_log(FakeModel())
        self.assertEqual(out, {"fake": True, "mode": "json"})
        self.assertEqual(FakeModel.calls, [{"mode": "json"}])

    def test_pydantic_like_model_dump_typeerror_falls_back_to_bare_call(self):
        """If ``model_dump`` rejects ``mode=`` (e.g. an older or custom
        implementation), ``serialize_for_log`` must retry without kwargs."""

        class LegacyModel:
            def __init__(self):
                self.n_calls = 0
                self.last_kwargs = None

            def model_dump(self, *args, **kwargs):
                self.n_calls += 1
                if kwargs:
                    raise TypeError("legacy model_dump takes no kwargs")
                self.last_kwargs = kwargs
                return {"legacy": True}

        m = LegacyModel()
        out = serialize_for_log(m)
        self.assertEqual(out, {"legacy": True})
        self.assertEqual(m.n_calls, 2)  # first with kwargs, second bare
        self.assertEqual(m.last_kwargs, {})

    def test_pydantic_like_model_dump_generic_exception_falls_back_to_str(self):
        class BrokenModel:
            def model_dump(self, *args, **kwargs):
                raise RuntimeError("broken")

            def __str__(self) -> str:
                return "<Broken>"

        self.assertEqual(serialize_for_log(BrokenModel()), "<Broken>")

    def test_generic_object_falls_back_to_str(self):
        class Plain:
            def __str__(self) -> str:
                return "<Plain>"

        self.assertEqual(serialize_for_log(Plain()), "<Plain>")

    def test_non_callable_model_dump_attribute_is_ignored(self):
        class Weird:
            model_dump = "not-a-method"

            def __str__(self) -> str:
                return "<Weird>"

        # ``callable(model_dump)`` is False → falls through to str().
        self.assertEqual(serialize_for_log(Weird()), "<Weird>")


# ─────────────────────────────────────────────────────────────────────────────
# redact_headers
# ─────────────────────────────────────────────────────────────────────────────
class TestRedactHeaders(unittest.TestCase):
    def test_sensitive_keys_are_redacted_case_insensitively(self):
        headers = {
            "X-API-Key": "super-secret-123",
            "authorization": "Bearer abcdef",
            "Cookie": "session=xyz",
            "Set-Cookie": "other=1",
            "Content-Type": "application/json",
            "X-Request-Id": "req-1",
        }
        out = redact_headers(headers)
        for key in ("X-API-Key", "authorization", "Cookie", "Set-Cookie"):
            marker = out[key]
            self.assertTrue(
                isinstance(marker, str) and marker.startswith("[REDACTED len="),
                f"{key} was not redacted: {marker!r}",
            )
            # Length of the original value must be surfaced for debugging.
            expected_len = len(headers[key])
            self.assertIn(f"len={expected_len}", marker)
        # Non-sensitive headers are passed through unchanged.
        self.assertEqual(out["Content-Type"], "application/json")
        self.assertEqual(out["X-Request-Id"], "req-1")

    def test_redaction_returns_a_copy_not_the_same_dict(self):
        headers = {"X-API-Key": "abc"}
        out = redact_headers(headers)
        self.assertIsNot(out, headers)
        # Caller's dict must still contain the raw value.
        self.assertEqual(headers["X-API-Key"], "abc")

    def test_non_dict_input_passes_through(self):
        # Important: the middleware sometimes hands us a list-of-tuples from
        # raw ASGI scope — we must not crash.
        raw = [("x-api-key", "abc")]
        self.assertEqual(redact_headers(raw), raw)  # type: ignore[arg-type]
        self.assertIsNone(redact_headers(None))  # type: ignore[arg-type]

    def test_empty_dict_returns_empty_dict(self):
        self.assertEqual(redact_headers({}), {})


# ─────────────────────────────────────────────────────────────────────────────
# token_fingerprint
# ─────────────────────────────────────────────────────────────────────────────
class TestTokenFingerprint(unittest.TestCase):
    def test_empty_string_returns_sentinel(self):
        self.assertEqual(token_fingerprint(""), "empty")

    def test_none_returns_sentinel(self):
        # The signature is typed ``str`` but the guard is truthy, so None
        # — which real code occasionally passes via getattr(..., token, None)
        # — must also map to the sentinel rather than crashing.
        self.assertEqual(token_fingerprint(None), "empty")  # type: ignore[arg-type]

    def test_nonempty_token_uses_len_and_sha256_prefix(self):
        token = "abcdef1234567890"
        out = token_fingerprint(token)
        expected_digest = hashlib.sha256(token.encode()).hexdigest()[:12]
        self.assertEqual(out, f"len={len(token)} sha256={expected_digest}")

    def test_fingerprint_is_deterministic_for_same_input(self):
        self.assertEqual(
            token_fingerprint("repeatable-token"),
            token_fingerprint("repeatable-token"),
        )

    def test_different_tokens_have_different_fingerprints(self):
        a = token_fingerprint("token-one")
        b = token_fingerprint("token-two")
        self.assertNotEqual(a, b)

    def test_fingerprint_does_not_leak_raw_token(self):
        secret = "highly-sensitive-bearer-token-please-do-not-leak"
        out = token_fingerprint(secret)
        self.assertNotIn(secret, out)


# ─────────────────────────────────────────────────────────────────────────────
# redact_payload
# ─────────────────────────────────────────────────────────────────────────────
class TestRedactPayload(unittest.TestCase):
    def test_fhirToken_is_redacted(self):
        payload = {"params": {"metadata": {"fhirToken": "eyJ0eXAiOiJKV1Q"}}}
        out = redact_payload(payload)
        self.assertIn("[REDACTED ", out["params"]["metadata"]["fhirToken"])
        self.assertNotIn("eyJ0eXAiOiJKV1Q", str(out))

    def test_permissionTicket_is_redacted(self):
        payload = {"permissionTicket": "eyJhbGciOi.payload.sig"}
        out = redact_payload(payload)
        self.assertIn("[REDACTED ", out["permissionTicket"])
        self.assertNotIn("eyJhbGciOi", str(out))

    def test_case_insensitive_key_matching(self):
        payload = {"FHIRTOKEN": "secret", "PermissionTicket": "jwt"}
        out = redact_payload(payload)
        self.assertIn("[REDACTED ", out["FHIRTOKEN"])
        self.assertIn("[REDACTED ", out["PermissionTicket"])

    def test_non_sensitive_keys_pass_through(self):
        payload = {"fhirUrl": "https://fhir.example.com", "patientId": "Patient/123"}
        out = redact_payload(payload)
        self.assertEqual(out["fhirUrl"], "https://fhir.example.com")
        self.assertEqual(out["patientId"], "Patient/123")

    def test_deeply_nested_token_redacted(self):
        payload = {
            "params": {
                "message": {
                    "metadata": {
                        "fhir-context": {
                            "fhirUrl": "https://fhir.example.com",
                            "fhirToken": "bearer-token-secret-123",
                            "patientId": "Patient/1",
                            "permissionTicket": "jwt-ticket-abc",
                        }
                    }
                }
            }
        }
        out = redact_payload(payload)
        ctx = out["params"]["message"]["metadata"]["fhir-context"]
        self.assertEqual(ctx["fhirUrl"], "https://fhir.example.com")
        self.assertEqual(ctx["patientId"], "Patient/1")
        self.assertIn("[REDACTED ", ctx["fhirToken"])
        self.assertIn("[REDACTED ", ctx["permissionTicket"])
        self.assertNotIn("bearer-token-secret-123", str(out))
        self.assertNotIn("jwt-ticket-abc", str(out))

    def test_empty_token_value(self):
        payload = {"fhirToken": ""}
        out = redact_payload(payload)
        self.assertEqual(out["fhirToken"], "[REDACTED empty]")

    def test_none_token_value(self):
        payload = {"fhirToken": None}
        out = redact_payload(payload)
        self.assertEqual(out["fhirToken"], "[REDACTED empty]")

    def test_list_values_recursed(self):
        payload = [{"fhirToken": "secret"}, {"safe": "value"}]
        out = redact_payload(payload)
        self.assertIn("[REDACTED ", out[0]["fhirToken"])
        self.assertEqual(out[1]["safe"], "value")

    def test_non_dict_non_list_passthrough(self):
        self.assertEqual(redact_payload("string"), "string")
        self.assertEqual(redact_payload(42), 42)
        self.assertIsNone(redact_payload(None))

    def test_original_payload_not_mutated(self):
        original_token = "my-secret-token"
        payload = {"fhirToken": original_token}
        redact_payload(payload)
        self.assertEqual(payload["fhirToken"], original_token)

    def test_redacted_token_includes_fingerprint(self):
        token = "bearer-abc-123"
        payload = {"fhirToken": token}
        out = redact_payload(payload)
        fp = token_fingerprint(token)
        self.assertIn(fp, out["fhirToken"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
