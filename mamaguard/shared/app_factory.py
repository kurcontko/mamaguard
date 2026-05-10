"""
A2A application factory -- shared by all agents.

Each agent's app.py calls create_a2a_app() with its own name, description,
URL, and optional FHIR extension URI.
"""

import os
from typing import Any

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentProvider,
    AgentSkill,
    APIKeySecurityScheme,
    In,
    SecurityScheme,
)
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from starlette.responses import JSONResponse
from starlette.routing import Route

from .middleware import ApiKeyMiddleware


def create_a2a_app(
    agent,
    name: str,
    description: str,
    url: str,
    port: int = 8001,
    version: str = "1.0.0",
    fhir_extension_uri: str | None = None,
    require_api_key: bool = True,
    skills: list[AgentSkill] | None = None,
    provider: AgentProvider | None = None,
    documentation_url: str | None = None,
    icon_url: str | None = None,
):
    """
    Build and return an A2A ASGI application for the given ADK agent.
    """
    extensions = []
    if fhir_extension_uri:
        extensions = [
            AgentExtension(
                uri=fhir_extension_uri,
                description="FHIR R4 context -- allows the agent to query the patient's FHIR server.",
                required=True,
            )
        ]

    if require_api_key:
        security_schemes = {
            "apiKey": SecurityScheme(
                root=APIKeySecurityScheme(
                    type="apiKey",
                    name="X-API-Key",
                    in_=In.header,
                    description="API key required to access this agent.",
                )
            )
        }
        security: list[dict[str, Any]] | None = [{"apiKey": []}]
    else:
        security_schemes = None
        security = None

    agent_card = AgentCard(
        name=name,
        description=description,
        url=url,
        version=version,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            state_transition_history=True,
            extensions=extensions,
        ),
        skills=skills or [],
        security_schemes=security_schemes,
        security=security,
        provider=provider,
        documentation_url=documentation_url,
        icon_url=icon_url,
    )

    app = to_a2a(agent, port=port, agent_card=agent_card)

    # Override the agent-card route with our own that emits A2A v1-spec
    # `supportedInterfaces`. The a2a-python SDK still emits the v0.3.0 shape
    # (preferredTransport + additionalInterfaces, no protocolBinding) — but
    # Prompt Opinion's marketplace parses with the .NET v1 SDK which requires
    # the consolidated `supportedInterfaces[]` with three required keys per
    # entry: url, protocolBinding, protocolVersion.
    # Spec ref: https://a2a-protocol.org/latest/specification/ §4.4.6 + §8.5.
    # PO template: https://github.com/prompt-opinion/po-adk-python (app_factory.py)
    A2A_V1_PROTOCOL_VERSION = "1.0"
    card_payload = agent_card.model_dump(by_alias=True, exclude_none=True, mode="json")
    primary_iface = {
        "url": card_payload["url"],
        "protocolBinding": card_payload.get("preferredTransport", "JSONRPC"),
        "protocolVersion": A2A_V1_PROTOCOL_VERSION,
    }
    extra_ifaces = []
    for entry in card_payload.get("additionalInterfaces", []):
        extra_ifaces.append({
            "url": entry.get("url", card_payload["url"]),
            "protocolBinding": entry.get("transport", "JSONRPC"),
            "protocolVersion": A2A_V1_PROTOCOL_VERSION,
        })
    card_payload["supportedInterfaces"] = [primary_iface, *extra_ifaces]

    async def _agent_card_with_supported_interfaces(_request):
        return JSONResponse(card_payload)

    app.router.routes.insert(
        0,
        Route(
            "/.well-known/agent-card.json",
            _agent_card_with_supported_interfaces,
            methods=["GET"],
        ),
    )

    auth_disabled = os.environ.get("MAMAGUARD_AUTH_DISABLED", "").lower() in (
        "1", "true", "yes",
    )
    if require_api_key and not auth_disabled:
        app.add_middleware(ApiKeyMiddleware)

    return app
