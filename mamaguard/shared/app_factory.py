"""
A2A application factory -- shared by all agents.

Each agent's app.py calls create_a2a_app() with its own name, description,
URL, and optional FHIR extension URI.
"""

from typing import Any

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentSkill,
    APIKeySecurityScheme,
    In,
    SecurityScheme,
)
from google.adk.a2a.utils.agent_to_a2a import to_a2a

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
    )

    app = to_a2a(agent, port=port, agent_card=agent_card)

    if require_api_key:
        app.add_middleware(ApiKeyMiddleware)

    return app
