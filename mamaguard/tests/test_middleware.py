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
from mamaguard.shared.middleware import ApiKeyMiddleware, _is_valid_key


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


if __name__ == "__main__":
    unittest.main()
