"""
Unit tests for ``mamaguard.shared.app_factory.create_a2a_app`` and the live
``mamaguard.app.a2a_app`` agent-card endpoint.

The app_factory is the single function that wires up the A2A ASGI application
(agent card, security scheme, FHIR extension, middleware). These tests validate
the contract Prompt Opinion and ``scripts/deploy.sh`` depend on:

1. Agent card structure — name, version, skills, FHIR extension, security.
2. Auth enforcement — middleware is attached and enforcing on the real app.
3. Agent card public bypass — ``/.well-known/agent-card.json`` requires no key.

The tests call the real ``a2a_app`` through ASGI directly and verify the
lifespan route registration separately.
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
import warnings
from dataclasses import dataclass
from typing import Any

# Ensure required env vars are set before any mamaguard import triggers
# dotenv loading or middleware initialization.
os.environ.setdefault("VALID_API_KEYS", "test-factory-key")
os.environ.setdefault("GOOGLE_API_KEY", "fake-key-for-test")

# Suppress ADK experimental warnings that clutter test output.
warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")

from unittest.mock import patch

from mamaguard.shared import middleware as mw


def _get_app():
    """Import the real a2a_app lazily so env vars are set first."""
    from mamaguard.app import a2a_app
    return a2a_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FHIR_EXTENSION_URI = "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"


class _AppTestCase(unittest.TestCase):
    """Base class that exercises the real A2A app through ASGI directly."""

    app = None
    client: _ASGIClient

    @classmethod
    def setUpClass(cls):
        cls.app = _get_app()
        cls.client = _ASGIClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        pass


@dataclass
class _ASGIResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class _ASGIClient:
    """Small synchronous ASGI test client.

    Starlette's TestClient currently hangs in this sandbox at anyio's thread
    portal boundary. These tests do not need a network client; calling the ASGI
    app directly still exercises routing and middleware.
    """

    def __init__(self, app):
        self._app = app

    def get(self, path: str, headers: dict[str, str] | None = None) -> _ASGIResponse:
        return asyncio.run(_asgi_request(self._app, "GET", path, headers=headers))

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _ASGIResponse:
        return asyncio.run(
            _asgi_request(self._app, "POST", path, json_body=json, headers=headers)
        )


async def _asgi_request(
    app,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> _ASGIResponse:
    body = b""
    raw_headers: list[tuple[bytes, bytes]] = []
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        raw_headers.append((b"content-type", b"application/json"))

    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))

    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    messages: list[dict[str, Any]] = []

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
        "state": {},
    }

    await app(scope, receive, send)

    status_code = 500
    response_headers: dict[str, str] = {}
    chunks: list[bytes] = []
    for message in messages:
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    return _ASGIResponse(
        status_code=status_code,
        headers=response_headers,
        content=b"".join(chunks),
    )


def _bootstrap_a2a_routes(app) -> None:
    async def _run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(_run_lifespan())


# ===================================================================
# Agent Card Structure
# ===================================================================

class TestAgentCardEndpoint(_AppTestCase):
    """``/.well-known/agent-card.json`` returns 200 with valid card shape."""

    def test_status_200(self):
        resp = self.client.get("/.well-known/agent-card.json")
        self.assertEqual(resp.status_code, 200)

    def test_content_type_json(self):
        resp = self.client.get("/.well-known/agent-card.json")
        self.assertIn("application/json", resp.headers.get("content-type", ""))

    def test_card_name(self):
        card = self.client.get("/.well-known/agent-card.json").json()
        self.assertEqual(card["name"], "MamaGuard Care Coordinator")

    def test_card_version(self):
        from mamaguard import MAMAGUARD_VERSION
        card = self.client.get("/.well-known/agent-card.json").json()
        self.assertEqual(card["version"], MAMAGUARD_VERSION)

    def test_card_description_mentions_fhir_tools(self):
        card = self.client.get("/.well-known/agent-card.json").json()
        self.assertIn("15 FHIR tools", card["description"])

    def test_card_description_mentions_liaison_pattern(self):
        card = self.client.get("/.well-known/agent-card.json").json()
        self.assertIn("Liaison", card["description"])

    def test_card_has_supported_interfaces(self):
        """A2A v1: transports live in supportedInterfaces[]; the legacy top-level
        `url` field has been removed."""
        card = self.client.get("/.well-known/agent-card.json").json()
        ifaces = card.get("supportedInterfaces")
        self.assertIsInstance(ifaces, list)
        self.assertGreater(len(ifaces), 0, "supportedInterfaces must contain at least one entry")
        primary = ifaces[0]
        self.assertTrue(primary.get("url"), "primary supportedInterface must have a url")
        self.assertEqual(primary.get("protocolVersion"), "1.0")
        self.assertEqual(primary.get("protocolBinding"), "JSONRPC")

    def test_card_drops_v0_3_legacy_fields(self):
        """A2A v1 spec removes `url`, `preferredTransport`, `additionalInterfaces`,
        and `capabilities.stateTransitionHistory`. PO's .NET v1 parser rejects
        cards that still ship them alongside `supportedInterfaces`."""
        card = self.client.get("/.well-known/agent-card.json").json()
        self.assertNotIn("url", card)
        self.assertNotIn("preferredTransport", card)
        self.assertNotIn("additionalInterfaces", card)
        self.assertNotIn("stateTransitionHistory", card.get("capabilities", {}))


class TestAgentCardSkills(_AppTestCase):
    """Agent card advertises exactly 4 skills matching the 3 sub-agents + 1 composite."""

    def _get_skills(self):
        card = self.client.get("/.well-known/agent-card.json").json()
        return card.get("skills", [])

    def test_skills_count(self):
        self.assertEqual(len(self._get_skills()), 4)

    def test_skill_ids(self):
        ids = {s["id"] for s in self._get_skills()}
        expected = {
            "maternal-risk-assessment",
            "pediatric-care-transition",
            "sdoh-screening-outreach",
            "comprehensive-care-plan",
        }
        self.assertEqual(ids, expected)

    def test_every_skill_has_name(self):
        for skill in self._get_skills():
            self.assertTrue(skill.get("name"), f"Skill {skill['id']} missing name")

    def test_every_skill_has_description(self):
        for skill in self._get_skills():
            self.assertTrue(
                skill.get("description"),
                f"Skill {skill['id']} missing description",
            )

    def test_every_skill_has_tags(self):
        for skill in self._get_skills():
            self.assertIsInstance(skill.get("tags"), list, f"Skill {skill['id']} tags not a list")
            self.assertGreater(len(skill["tags"]), 0, f"Skill {skill['id']} has no tags")

    def test_maternal_skill_mentions_7_tools(self):
        skills = {s["id"]: s for s in self._get_skills()}
        self.assertIn("7 FHIR tools", skills["maternal-risk-assessment"]["description"])

    def test_pediatric_skill_mentions_5_tools(self):
        skills = {s["id"]: s for s in self._get_skills()}
        self.assertIn("5 FHIR tools", skills["pediatric-care-transition"]["description"])

    def test_sdoh_skill_mentions_6_tools(self):
        skills = {s["id"]: s for s in self._get_skills()}
        self.assertIn("6 FHIR tools", skills["sdoh-screening-outreach"]["description"])

    def test_comprehensive_skill_mentions_5t(self):
        skills = {s["id"]: s for s in self._get_skills()}
        self.assertIn("5T", skills["comprehensive-care-plan"]["description"])


class TestAgentCardSecurity(_AppTestCase):
    """Agent card declares API key security scheme for Prompt Opinion."""

    def _get_card(self):
        return self.client.get("/.well-known/agent-card.json").json()

    def test_security_schemes_present(self):
        card = self._get_card()
        self.assertIn("securitySchemes", card)

    def test_apikey_scheme_declared(self):
        card = self._get_card()
        self.assertIn("apiKey", card["securitySchemes"])

    def test_apikey_scheme_type(self):
        scheme = self._get_card()["securitySchemes"]["apiKey"]
        self.assertEqual(scheme["type"], "apiKey")

    def test_apikey_scheme_header(self):
        scheme = self._get_card()["securitySchemes"]["apiKey"]
        self.assertEqual(scheme["in"], "header")
        self.assertEqual(scheme["name"], "X-API-Key")

    def test_security_requirement_list(self):
        card = self._get_card()
        self.assertIsInstance(card.get("security"), list)
        self.assertIn({"apiKey": []}, card["security"])


class TestAgentCardCapabilities(_AppTestCase):
    """Agent card capabilities: streaming, FHIR extension, protocol version."""

    def _get_card(self):
        return self.client.get("/.well-known/agent-card.json").json()

    def test_streaming_disabled(self):
        # Working agent precedent on the PO marketplace (e.g. Homeward) declares
        # streaming=False so PO's BYO consultation tool uses non-streaming
        # SendMessage instead of SSE. Forum threads confirm SSE handling is
        # brittle in PO's parser. See po_debug_session_2026-05-11.md.
        caps = self._get_card()["capabilities"]
        self.assertFalse(caps.get("streaming"))

    def test_fhir_extension_present(self):
        exts = self._get_card()["capabilities"].get("extensions", [])
        uris = [e["uri"] for e in exts]
        self.assertIn(FHIR_EXTENSION_URI, uris)

    def test_fhir_extension_required(self):
        exts = self._get_card()["capabilities"]["extensions"]
        fhir_ext = next(e for e in exts if e["uri"] == FHIR_EXTENSION_URI)
        self.assertTrue(fhir_ext["required"])

    def test_fhir_extension_has_description(self):
        exts = self._get_card()["capabilities"]["extensions"]
        fhir_ext = next(e for e in exts if e["uri"] == FHIR_EXTENSION_URI)
        self.assertTrue(fhir_ext.get("description"))

    def test_fhir_extension_declares_smart_scopes(self):
        """PO uses extension.params.scopes to drive the SMART consent dialog."""
        exts = self._get_card()["capabilities"]["extensions"]
        fhir_ext = next(e for e in exts if e["uri"] == FHIR_EXTENSION_URI)
        scopes = fhir_ext.get("params", {}).get("scopes", [])
        names = {s["name"] for s in scopes}
        self.assertIn("patient/Patient.rs", names)
        # Reads the agent actually performs
        for read_scope in (
            "patient/Observation.rs",
            "patient/Condition.rs",
            "patient/MedicationRequest.rs",
            "patient/Immunization.rs",
            "patient/Coverage.rs",
            "patient/RelatedPerson.rs",
            "patient/RiskAssessment.rs",
            "patient/CommunicationRequest.rs",
            "patient/CarePlan.rs",
            "patient/Goal.rs",
            "patient/ServiceRequest.rs",
        ):
            self.assertIn(read_scope, names, f"missing read scope {read_scope}")
        # Writes performed by commit_pending_write
        for write_scope in (
            "patient/RiskAssessment.cu",
            "patient/CommunicationRequest.cu",
            "patient/CarePlan.cu",
            "patient/Goal.cu",
        ):
            self.assertIn(write_scope, names, f"missing write scope {write_scope}")
        patient_scope = next(s for s in scopes if s["name"] == "patient/Patient.rs")
        self.assertTrue(patient_scope.get("required"), "Patient.rs must be required")

    def test_protocol_version(self):
        card = self._get_card()
        self.assertEqual(card.get("protocolVersion"), "1.0")

    def test_input_output_modes(self):
        card = self._get_card()
        self.assertIn("text/plain", card.get("defaultInputModes", []))
        self.assertIn("text/plain", card.get("defaultOutputModes", []))


# ===================================================================
# Auth Enforcement on the Real App
# ===================================================================

class TestAuthOnRealApp(_AppTestCase):
    """Auth middleware is wired into the real A2A app (not just the echo test app)."""

    def test_agent_card_no_key_returns_200(self):
        """Public bypass: agent card requires no API key."""
        resp = self.client.get("/.well-known/agent-card.json")
        self.assertEqual(resp.status_code, 200)

    def test_agent_card_with_bad_key_still_200(self):
        """Public bypass is unconditional for discovery."""
        resp = self.client.get(
            "/.well-known/agent-card.json",
            headers={"X-API-Key": "totally-wrong-key"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_post_without_key_returns_401(self):
        with patch.object(mw, "VALID_API_KEYS", {"test-factory-key"}):
            resp = self.client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "message/send",
                    "id": "auth-test-1",
                    "params": {
                        "message": {
                            "messageId": "auth-test-msg-1",
                            "role": "user",
                            "parts": [{"text": "hello"}],
                        }
                    },
                },
            )
        self.assertEqual(resp.status_code, 401)

    def test_post_with_bad_key_returns_403(self):
        with patch.object(mw, "VALID_API_KEYS", {"test-factory-key"}):
            resp = self.client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "message/send",
                    "id": "auth-test-2",
                    "params": {
                        "message": {
                            "messageId": "auth-test-msg-2",
                            "role": "user",
                            "parts": [{"text": "hello"}],
                        }
                    },
                },
                headers={"X-API-Key": "wrong-key"},
            )
        self.assertEqual(resp.status_code, 403)

    def test_post_with_valid_key_passes_auth(self):
        """Valid key passes middleware; response may be 200 or 500 (no real LLM backend)."""
        with patch.object(mw, "VALID_API_KEYS", {"test-factory-key"}):
            resp = self.client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "message/send",
                    "id": "auth-test-3",
                    "params": {
                        "message": {
                            "messageId": "auth-test-msg-3",
                            "role": "user",
                            "parts": [{"text": "hello"}],
                        }
                    },
                },
                headers={"X-API-Key": "test-factory-key"},
            )
        # Auth passed — response is 200 (or 500 if no GOOGLE_API_KEY configured).
        # 401 and 403 would mean auth failed.
        self.assertNotIn(resp.status_code, (401, 403))


# ===================================================================
# Deprecated Agent Card Path
# ===================================================================

class TestDeprecatedAgentCardPath(_AppTestCase):
    """ADK also registers ``/.well-known/agent.json`` as a deprecated alias."""

    def test_deprecated_path_also_accessible(self):
        resp = self.client.get("/.well-known/agent.json")
        # This path is NOT in the middleware public bypass list, so it will
        # require an API key. Accept 200 (if middleware updated) or 401 (current).
        self.assertIn(resp.status_code, (200, 401))

    def test_lifespan_registers_a2a_routes(self):
        _bootstrap_a2a_routes(self.app)
        paths = [getattr(route, "path", None) for route in self.app.router.routes]
        self.assertIn("/", paths)
        self.assertIn("/.well-known/agent.json", paths)


# ===================================================================
# create_a2a_app factory kwargs
# ===================================================================

class TestCreateA2aAppFactory(unittest.TestCase):
    """Test ``create_a2a_app`` factory with custom kwargs."""

    def _create_app(self, **kwargs):
        from mamaguard.orchestrator.agent import root_agent
        from mamaguard.shared.app_factory import create_a2a_app
        defaults = dict(
            agent=root_agent,
            name="Test Agent",
            description="Test description",
            url="http://localhost:9999",
            port=9999,
        )
        defaults.update(kwargs)
        return create_a2a_app(**defaults)

    def test_returns_starlette_app(self):
        from starlette.applications import Starlette
        app = self._create_app()
        self.assertIsInstance(app, Starlette)

    def test_no_fhir_extension(self):
        """When fhir_extension_uri is None, no extensions in card."""
        app = self._create_app(fhir_extension_uri=None)
        card = _ASGIClient(app).get("/.well-known/agent-card.json").json()
        exts = card.get("capabilities", {}).get("extensions", [])
        self.assertEqual(len(exts), 0)

    def test_custom_fhir_extension_uri(self):
        app = self._create_app(fhir_extension_uri="https://custom.example.com/fhir")
        card = _ASGIClient(app).get("/.well-known/agent-card.json").json()
        exts = card["capabilities"]["extensions"]
        self.assertEqual(len(exts), 1)
        self.assertEqual(exts[0]["uri"], "https://custom.example.com/fhir")

    def test_no_api_key_requirement(self):
        """When require_api_key=False, no security scheme in card."""
        app = self._create_app(require_api_key=False)
        card = _ASGIClient(app).get("/.well-known/agent-card.json").json()
        self.assertIsNone(card.get("securitySchemes"))
        self.assertIsNone(card.get("security"))

    def test_custom_skills(self):
        from a2a.types import AgentSkill
        custom_skills = [
            AgentSkill(
                id="custom-skill",
                name="Custom Skill",
                description="A custom skill for testing",
                tags=["test"],
            ),
        ]
        app = self._create_app(skills=custom_skills)
        card = _ASGIClient(app).get("/.well-known/agent-card.json").json()
        self.assertEqual(len(card["skills"]), 1)
        self.assertEqual(card["skills"][0]["id"], "custom-skill")

    def test_custom_name_and_description(self):
        app = self._create_app(name="Custom Agent", description="Custom desc")
        card = _ASGIClient(app).get("/.well-known/agent-card.json").json()
        self.assertEqual(card["name"], "Custom Agent")
        self.assertEqual(card["description"], "Custom desc")

    def test_custom_version(self):
        app = self._create_app(version="2.0.0")
        card = _ASGIClient(app).get("/.well-known/agent-card.json").json()
        self.assertEqual(card["version"], "2.0.0")


if __name__ == "__main__":
    unittest.main()
