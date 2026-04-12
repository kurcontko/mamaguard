"""
Unit tests for ``mamaguard.shared.middleware.ApiKeyMiddleware``.

This is the only HTTP layer between Prompt Opinion traffic and the ADK agent,
so it has two jobs we care about:

1. API-key enforcement (401 missing, 403 invalid, public agent-card bypass).
2. FHIR metadata bridging from ``params.message.metadata`` to
   ``params.metadata`` so the ADK before-model hook can find it.

The tests below exercise the middleware in isolation against a minimal
Starlette app + ``TestClient`` — no ADK imports, no network. Module-level
``VALID_API_KEYS`` is patched per test so nothing touches the environment.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mamaguard.shared import middleware as mw
from mamaguard.shared.middleware import (
    A2A_EXTENSIONS_HEADER,
    ApiKeyMiddleware,
    FHIR_EXTENSION_URI,
    _activate_extension,
    _is_valid_key,
)


FHIR_KEY = "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"


async def _echo(request: Request) -> JSONResponse | PlainTextResponse:
    """Return the JSON-parsed body so tests can assert bridging downstream."""
    body = await request.body()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return PlainTextResponse(body.decode("utf-8", errors="replace"))
    return JSONResponse({"received": payload})


async def _agent_card(request: Request) -> JSONResponse:
    return JSONResponse({"name": "mamaguard", "version": "test"})


def _build_app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/echo", _echo, methods=["POST"]),
            Route("/.well-known/agent-card.json", _agent_card, methods=["GET"]),
        ],
    )
    app.add_middleware(ApiKeyMiddleware)
    return app


def _client(valid_keys: set[str] | None = None) -> TestClient:
    """Patch VALID_API_KEYS for the life of the returned TestClient.

    We cannot use a decorator/context manager neatly for every test because
    each call site needs its own override, so tests either use ``with
    patch(...)`` explicitly or wrap this helper.
    """
    if valid_keys is None:
        valid_keys = {"good-key"}
    # Caller is expected to patch via context manager; helper just builds app.
    return TestClient(_build_app())


class TestAgentCardBypass(unittest.TestCase):
    """/.well-known/agent-card.json must be reachable without any key."""

    def test_no_api_key(self):
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.get("/.well-known/agent-card.json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "mamaguard")

    def test_invalid_api_key_still_allowed(self):
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.get(
                "/.well-known/agent-card.json",
                headers={"X-API-Key": "totally-wrong"},
            )
        # Public bypass is unconditional — agent-card path returns 200 even
        # when a bad key is supplied, because Prompt Opinion discovery must
        # always succeed.
        self.assertEqual(resp.status_code, 200)


class TestApiKeyEnforcement(unittest.TestCase):
    """Every other endpoint must require a valid key."""

    def test_missing_api_key_returns_401(self):
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post("/echo", json={"hello": "world"})
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertEqual(body["error"], "Unauthorized")
        self.assertIn("X-API-Key", body["detail"])

    def test_invalid_api_key_returns_403(self):
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post(
                "/echo",
                json={"hello": "world"},
                headers={"X-API-Key": "bad-key"},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "Forbidden")

    def test_valid_api_key_passes_through(self):
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post(
                "/echo",
                json={"hello": "world"},
                headers={"X-API-Key": "good-key"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["received"], {"hello": "world"})

    def test_multiple_valid_keys(self):
        with patch.object(mw, "VALID_API_KEYS", {"key-a", "key-b"}):
            client = _client()
            resp_a = client.post("/echo", json={"n": 1}, headers={"X-API-Key": "key-a"})
            resp_b = client.post("/echo", json={"n": 2}, headers={"X-API-Key": "key-b"})
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_b.status_code, 200)


class TestFhirMetadataBridging(unittest.TestCase):
    """
    The middleware copies FHIR context from ``params.message.metadata`` up to
    ``params.metadata`` so the ADK before-model hook (which reads the latter)
    can find it. These tests assert that the downstream handler actually
    receives the rewritten body.
    """

    FHIR_VALUE = {
        "fhirUrl": "https://fhir.example.org",
        "fhirToken": "eyJ-TEST",
        "patientId": "patient-42",
    }

    def _post(self, payload: dict) -> dict:
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post(
                "/echo",
                json=payload,
                headers={"X-API-Key": "good-key"},
            )
        self.assertEqual(resp.status_code, 200, msg=resp.text)
        return resp.json()["received"]

    def test_bridged_from_message_metadata(self):
        payload = {
            "params": {
                "message": {
                    "metadata": {FHIR_KEY: self.FHIR_VALUE},
                }
            }
        }
        received = self._post(payload)

        # params.metadata must now exist and carry the FHIR context.
        params = received["params"]
        self.assertIn("metadata", params)
        self.assertEqual(params["metadata"][FHIR_KEY], self.FHIR_VALUE)
        # Original message.metadata untouched (non-destructive bridge).
        self.assertEqual(
            params["message"]["metadata"][FHIR_KEY], self.FHIR_VALUE
        )

    def test_existing_params_metadata_not_overwritten(self):
        original = {"other-key": {"x": 1}}
        payload = {
            "params": {
                "metadata": dict(original),
                "message": {
                    "metadata": {FHIR_KEY: self.FHIR_VALUE},
                },
            }
        }
        received = self._post(payload)

        # params.metadata was already set — middleware must leave it alone.
        self.assertEqual(received["params"]["metadata"], original)
        self.assertNotIn(FHIR_KEY, received["params"]["metadata"])

    def test_params_metadata_set_directly_is_passthrough(self):
        """FHIR context already on params.metadata needs no bridging."""
        payload = {
            "params": {
                "metadata": {FHIR_KEY: self.FHIR_VALUE},
                "message": {},
            }
        }
        received = self._post(payload)
        self.assertEqual(
            received["params"]["metadata"][FHIR_KEY], self.FHIR_VALUE
        )

    def test_no_fhir_key_no_bridging(self):
        """Unrelated message.metadata keys must not be lifted."""
        payload = {
            "params": {
                "message": {"metadata": {"unrelated": {"foo": "bar"}}},
            }
        }
        received = self._post(payload)
        # params.metadata should remain absent.
        self.assertNotIn("metadata", received["params"])

    def test_payload_without_params_is_passthrough(self):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        received = self._post(payload)
        self.assertEqual(received, payload)

    def test_fhir_key_as_json_string_is_coerced_to_dict_on_bridge(self):
        """Prompt Opinion sometimes sends the FHIR value as a JSON string.

        ``extract_fhir_from_payload`` coerces it via ``_coerce_fhir_data``,
        so after bridging the downstream handler sees a dict under
        ``params.metadata`` — not the raw JSON string.
        """
        stringified = json.dumps(self.FHIR_VALUE)
        payload = {
            "params": {
                "message": {"metadata": {FHIR_KEY: stringified}},
            }
        }
        received = self._post(payload)
        self.assertEqual(
            received["params"]["metadata"][FHIR_KEY], self.FHIR_VALUE
        )
        # message.metadata still contains the original (string) form.
        self.assertEqual(
            received["params"]["message"]["metadata"][FHIR_KEY], stringified
        )


class TestTimingSafeKeyValidation(unittest.TestCase):
    """Verify the ``_is_valid_key`` helper uses timing-safe comparison."""

    def test_valid_key_accepted(self):
        with patch.object(mw, "VALID_API_KEYS", {"alpha-key"}):
            self.assertTrue(_is_valid_key("alpha-key"))

    def test_invalid_key_rejected(self):
        with patch.object(mw, "VALID_API_KEYS", {"alpha-key"}):
            self.assertFalse(_is_valid_key("wrong-key"))

    def test_multiple_keys_any_match(self):
        with patch.object(mw, "VALID_API_KEYS", {"key-1", "key-2", "key-3"}):
            self.assertTrue(_is_valid_key("key-2"))

    def test_multiple_keys_none_match(self):
        with patch.object(mw, "VALID_API_KEYS", {"key-1", "key-2"}):
            self.assertFalse(_is_valid_key("key-9"))

    def test_empty_candidate_rejected(self):
        with patch.object(mw, "VALID_API_KEYS", {"key-1"}):
            self.assertFalse(_is_valid_key(""))

    def test_prefix_not_sufficient(self):
        """A prefix of a valid key must not pass (compare_digest requires exact match)."""
        with patch.object(mw, "VALID_API_KEYS", {"long-secret-key-value"}):
            self.assertFalse(_is_valid_key("long-secret"))

    def test_suffix_not_sufficient(self):
        with patch.object(mw, "VALID_API_KEYS", {"long-secret-key-value"}):
            self.assertFalse(_is_valid_key("key-value"))

    def test_uses_secrets_compare_digest(self):
        """Confirm the function calls ``secrets.compare_digest``."""
        with patch.object(mw, "VALID_API_KEYS", {"test-key"}):
            with patch("mamaguard.shared.middleware.secrets.compare_digest", return_value=True) as mock_cd:
                result = _is_valid_key("test-key")
        self.assertTrue(result)
        mock_cd.assert_called_once_with("test-key", "test-key")

    def test_iterates_all_keys_even_after_match(self):
        """Must not short-circuit — iterate all keys to avoid leaking set size."""
        with patch.object(mw, "VALID_API_KEYS", {"a", "b", "c"}):
            with patch("mamaguard.shared.middleware.secrets.compare_digest", side_effect=[True, False, False]) as mock_cd:
                _is_valid_key("a")
        self.assertEqual(mock_cd.call_count, 3)


class TestBodyEdgeCases(unittest.TestCase):
    """Non-JSON and empty bodies must not crash the middleware."""

    def test_non_json_body_with_valid_key(self):
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post(
                "/echo",
                content=b"not-json-at-all",
                headers={"X-API-Key": "good-key", "Content-Type": "text/plain"},
            )
        # Endpoint returns PlainTextResponse for non-JSON; middleware must
        # have allowed the request through without exploding on parse error.
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.text, "not-json-at-all")

    def test_non_json_body_without_key_still_401(self):
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post(
                "/echo",
                content=b"garbage",
                headers={"Content-Type": "text/plain"},
            )
        self.assertEqual(resp.status_code, 401)

    def test_empty_body_with_valid_key(self):
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post(
                "/echo",
                content=b"",
                headers={"X-API-Key": "good-key"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["received"], {})


class TestA2AExtensionActivation(unittest.TestCase):
    """When PO sends ``X-A2A-Extensions`` requesting the FHIR extension, the
    middleware must echo it back in the response header so the client knows
    the extension is active (per A2A protocol spec)."""

    def _post(self, headers: dict[str, str] | None = None):  # type: ignore[override]
        all_headers = {"X-API-Key": "good-key"}
        if headers:
            all_headers.update(headers)
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            return client.post("/echo", json={"ping": 1}, headers=all_headers)

    def test_fhir_extension_echoed_when_requested(self):
        """Client sends FHIR extension URI → response echoes it back."""
        resp = self._post({A2A_EXTENSIONS_HEADER: FHIR_EXTENSION_URI})
        self.assertEqual(resp.status_code, 200)
        activated = resp.headers.get(A2A_EXTENSIONS_HEADER, "")
        self.assertIn(FHIR_EXTENSION_URI, activated)

    def test_no_extension_header_when_not_requested(self):
        """No X-A2A-Extensions in request → no extension header in response."""
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        # The header should not appear at all (or be empty).
        activated = resp.headers.get(A2A_EXTENSIONS_HEADER, "")
        self.assertNotIn(FHIR_EXTENSION_URI, activated)

    def test_unrelated_extension_not_activated(self):
        """An unknown extension URI should not be echoed."""
        resp = self._post({A2A_EXTENSIONS_HEADER: "https://example.com/ext/unknown"})
        self.assertEqual(resp.status_code, 200)
        activated = resp.headers.get(A2A_EXTENSIONS_HEADER, "")
        self.assertNotIn("https://example.com/ext/unknown", activated)

    def test_fhir_among_multiple_requested(self):
        """FHIR URI mixed with other extensions → only FHIR is activated."""
        header_val = f"https://example.com/ext/other, {FHIR_EXTENSION_URI}"
        resp = self._post({A2A_EXTENSIONS_HEADER: header_val})
        self.assertEqual(resp.status_code, 200)
        activated = resp.headers.get(A2A_EXTENSIONS_HEADER, "")
        self.assertIn(FHIR_EXTENSION_URI, activated)
        # The unknown extension should NOT be echoed.
        self.assertNotIn("https://example.com/ext/other", activated)

    def test_extension_not_set_on_401(self):
        """Auth failure → no extension activation (request never reached agent)."""
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post(
                "/echo",
                json={"ping": 1},
                headers={A2A_EXTENSIONS_HEADER: FHIR_EXTENSION_URI},
                # No X-API-Key → 401
            )
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn(A2A_EXTENSIONS_HEADER, resp.headers)

    def test_extension_not_set_on_403(self):
        """Invalid key → no extension activation."""
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.post(
                "/echo",
                json={"ping": 1},
                headers={
                    "X-API-Key": "bad-key",
                    A2A_EXTENSIONS_HEADER: FHIR_EXTENSION_URI,
                },
            )
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn(A2A_EXTENSIONS_HEADER, resp.headers)

    def test_extension_not_set_on_agent_card(self):
        """Agent-card bypass path does not activate extensions."""
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}):
            client = _client()
            resp = client.get(
                "/.well-known/agent-card.json",
                headers={A2A_EXTENSIONS_HEADER: FHIR_EXTENSION_URI},
            )
        self.assertEqual(resp.status_code, 200)
        activated = resp.headers.get(A2A_EXTENSIONS_HEADER, "")
        self.assertNotIn(FHIR_EXTENSION_URI, activated)


class TestActivateExtensionHelper(unittest.TestCase):
    """Unit tests for the ``_activate_extension`` helper function."""

    def _make_response(self, existing_header: str | None = None) -> JSONResponse:
        resp = JSONResponse({"ok": True})
        if existing_header is not None:
            resp.headers[A2A_EXTENSIONS_HEADER] = existing_header
        return resp

    def test_adds_uri_when_no_existing_header(self):
        resp = self._make_response()
        _activate_extension(resp, "https://example.com/ext/a")
        self.assertEqual(
            resp.headers[A2A_EXTENSIONS_HEADER],
            "https://example.com/ext/a",
        )

    def test_merges_with_existing_header(self):
        resp = self._make_response("https://example.com/ext/a")
        _activate_extension(resp, "https://example.com/ext/b")
        parts = {
            e.strip()
            for e in resp.headers[A2A_EXTENSIONS_HEADER].split(",")
        }
        self.assertEqual(
            parts,
            {"https://example.com/ext/a", "https://example.com/ext/b"},
        )

    def test_no_duplicate_when_already_present(self):
        resp = self._make_response("https://example.com/ext/a")
        _activate_extension(resp, "https://example.com/ext/a")
        # Should appear exactly once.
        self.assertEqual(
            resp.headers[A2A_EXTENSIONS_HEADER],
            "https://example.com/ext/a",
        )

    def test_sorted_output(self):
        resp = self._make_response("https://z.example.com/ext")
        _activate_extension(resp, "https://a.example.com/ext")
        self.assertEqual(
            resp.headers[A2A_EXTENSIONS_HEADER],
            "https://a.example.com/ext, https://z.example.com/ext",
        )


class TestPayloadTokenRedactionInLogs(unittest.TestCase):
    """When LOG_FULL_PAYLOAD is True, FHIR tokens in the logged payload
    must be redacted so they don't appear in plaintext in Cloud Run logs."""

    def test_fhir_token_not_in_log_output(self):
        """The raw fhirToken value must not appear in any log message."""
        secret_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.secret"
        payload = {
            "params": {
                "message": {
                    "metadata": {
                        FHIR_KEY: {
                            "fhirUrl": "https://fhir.example.com",
                            "fhirToken": secret_token,
                            "patientId": "Patient/1",
                        }
                    }
                }
            }
        }
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}), \
             patch.object(mw, "LOG_FULL_PAYLOAD", True), \
             patch("mamaguard.shared.middleware.logger") as mock_logger:
            client = _client()
            resp = client.post(
                "/echo", json=payload, headers={"X-API-Key": "good-key"},
            )
        self.assertEqual(resp.status_code, 200)
        # Check every info/debug/warning call — the raw token must never appear.
        for call in mock_logger.info.call_args_list:
            msg = call[0][0] % call[0][1:] if len(call[0]) > 1 else str(call[0][0])
            self.assertNotIn(
                secret_token, msg,
                f"Raw fhirToken leaked in log message: {msg[:200]}...",
            )

    def test_redacted_marker_present_in_log_output(self):
        """The logged payload should contain a [REDACTED ...] marker for the token."""
        payload = {
            "params": {
                "message": {
                    "metadata": {
                        FHIR_KEY: {
                            "fhirUrl": "https://fhir.example.com",
                            "fhirToken": "secret-bearer-token",
                            "patientId": "Patient/1",
                        }
                    }
                }
            }
        }
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}), \
             patch.object(mw, "LOG_FULL_PAYLOAD", True), \
             patch("mamaguard.shared.middleware.logger") as mock_logger:
            client = _client()
            client.post("/echo", json=payload, headers={"X-API-Key": "good-key"})
        # Find the incoming_http_request log call
        found_redacted = False
        for call in mock_logger.info.call_args_list:
            msg = call[0][0] % call[0][1:] if len(call[0]) > 1 else str(call[0][0])
            if "incoming_http_request" in msg and "[REDACTED " in msg:
                found_redacted = True
                break
        self.assertTrue(found_redacted, "Expected [REDACTED ...] marker in payload log")

    def test_non_sensitive_fields_still_logged(self):
        """fhirUrl and patientId must remain visible in the logged payload."""
        payload = {
            "params": {
                "message": {
                    "metadata": {
                        FHIR_KEY: {
                            "fhirUrl": "https://fhir.example.com",
                            "fhirToken": "secret-token",
                            "patientId": "Patient/42",
                        }
                    }
                }
            }
        }
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}), \
             patch.object(mw, "LOG_FULL_PAYLOAD", True), \
             patch("mamaguard.shared.middleware.logger") as mock_logger:
            client = _client()
            client.post("/echo", json=payload, headers={"X-API-Key": "good-key"})
        payload_log = ""
        for call in mock_logger.info.call_args_list:
            msg = call[0][0] % call[0][1:] if len(call[0]) > 1 else str(call[0][0])
            if "incoming_http_request" in msg:
                payload_log = msg
                break
        self.assertIn("https://fhir.example.com", payload_log)
        self.assertIn("Patient/42", payload_log)

    def test_permission_ticket_also_redacted(self):
        """permissionTicket should also be redacted alongside fhirToken."""
        payload = {
            "params": {
                "metadata": {
                    FHIR_KEY: {
                        "fhirToken": "bearer-secret",
                        "permissionTicket": "jwt-ticket-secret",
                    }
                }
            }
        }
        with patch.object(mw, "VALID_API_KEYS", {"good-key"}), \
             patch.object(mw, "LOG_FULL_PAYLOAD", True), \
             patch("mamaguard.shared.middleware.logger") as mock_logger:
            client = _client()
            client.post("/echo", json=payload, headers={"X-API-Key": "good-key"})
        for call in mock_logger.info.call_args_list:
            msg = call[0][0] % call[0][1:] if len(call[0]) > 1 else str(call[0][0])
            self.assertNotIn("bearer-secret", msg)
            self.assertNotIn("jwt-ticket-secret", msg)


if __name__ == "__main__":
    unittest.main()
