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

from .middleware import (
    A2aV1OutboundMiddleware,
    ApiKeyMiddleware,
    FhirHeaderMiddleware,
    JsonRpcMethodAliasMiddleware,
)


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
    # SMART scopes the agent advertises to Prompt Opinion. Only Patient.rs is
    # required — every other scope is optional so PO can register and consult
    # the agent even if the workspace user declines a subset (the FHIR tools
    # already degrade gracefully on 403). Write scopes (.cu) cover the resources
    # `commit_pending_write` POSTs after clinician approval.
    # Spec ref: https://docs.promptopinion.ai/fhir-context/a2a-fhir-context#extension-scopes
    fhir_smart_scopes = [
        {"name": "patient/Patient.rs", "required": True},
        {"name": "patient/Observation.rs"},
        {"name": "patient/Condition.rs"},
        {"name": "patient/MedicationRequest.rs"},
        {"name": "patient/Encounter.rs"},
        {"name": "patient/Immunization.rs"},
        {"name": "patient/Coverage.rs"},
        {"name": "patient/RelatedPerson.rs"},
        {"name": "patient/RiskAssessment.cu"},
        {"name": "patient/CommunicationRequest.cu"},
        {"name": "patient/CarePlan.cu"},
        {"name": "patient/Goal.cu"},
    ]

    extensions = []
    if fhir_extension_uri:
        extensions = [
            AgentExtension(
                uri=fhir_extension_uri,
                description="FHIR R4 context -- allows the agent to query the patient's FHIR server.",
                required=True,
                params={"scopes": fhir_smart_scopes},
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
            # Working-precedent agents on PO marketplace (e.g. Homeward) set
            # streaming=False so PO's BYO consultation uses non-streaming
            # SendMessage instead of SendStreamingMessage. SSE handling in PO's
            # parser appears unreliable per the Devpost forum
            # (see po_debug_session_2026-05-11.md).
            streaming=False,
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

    # Override the agent-card route with one that emits A2A v1 schema. The
    # a2a-python SDK still emits the v0.3.0 shape (preferredTransport +
    # additionalInterfaces, capabilities.stateTransitionHistory, top-level
    # `url`) — but Prompt Opinion's marketplace parses with the .NET v1 SDK,
    # which requires the consolidated `supportedInterfaces[]` (each entry:
    # url, protocolBinding, protocolVersion) and rejects the deprecated
    # fields. We translate v0.3 -> v1 here so PO can register MamaGuard
    # without waiting for upstream a2a-python to catch up.
    # Spec ref: https://a2a-protocol.org/latest/specification/ §4.4.6 + §8.5.
    # Migration ref: https://docs.promptopinion.ai/a2a-v1-migration
    A2A_V1_PROTOCOL_VERSION = "1.0"
    card_payload = agent_card.model_dump(by_alias=True, exclude_none=True, mode="json")
    card_payload["protocolVersion"] = A2A_V1_PROTOCOL_VERSION
    primary_url = card_payload["url"]
    primary_iface = {
        "url": primary_url,
        "protocolBinding": card_payload.get("preferredTransport", "JSONRPC"),
        "protocolVersion": A2A_V1_PROTOCOL_VERSION,
    }
    extra_ifaces = []
    for entry in card_payload.get("additionalInterfaces", []):
        extra_ifaces.append({
            "url": entry.get("url", primary_url),
            "protocolBinding": entry.get("transport", "JSONRPC"),
            "protocolVersion": A2A_V1_PROTOCOL_VERSION,
        })
    card_payload["supportedInterfaces"] = [primary_iface, *extra_ifaces]

    # Strip fields removed in A2A v1. Keeping them alongside `supportedInterfaces`
    # makes the .NET v1 parser reject the card.
    for legacy_field in ("url", "preferredTransport", "additionalInterfaces"):
        card_payload.pop(legacy_field, None)
    card_payload.get("capabilities", {}).pop("stateTransitionHistory", None)

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

    # FHIR header bridge runs regardless of auth — PO forwards FHIR context as
    # HTTP headers and the existing fhir_hook only reads JSON-RPC metadata.
    # Mounted AFTER JsonRpcMethodAliasMiddleware below so the alias runs first
    # (Starlette executes middleware LIFO). The order is:
    #   1. JsonRpcMethodAliasMiddleware  (SendStreamingMessage → message/stream)
    #   2. FhirHeaderMiddleware          (x-fhir-* headers → params.metadata)
    #   3. ApiKeyMiddleware (if enabled) (X-API-Key check + payload logging)
    app.add_middleware(FhirHeaderMiddleware)

    # Method-aliasing runs regardless of auth: PO's v1 verbs need rewriting
    # before the SDK dispatches. Add LAST so it runs FIRST (Starlette is LIFO).
    app.add_middleware(JsonRpcMethodAliasMiddleware)

    # A2A v1 outbound formatting: must run OUTERMOST so it sees the final
    # response after the SDK has produced it. Added last → runs first for
    # inbound (passthrough), wraps the response on outbound when the request
    # arrived using PO's v1 wire format.
    app.add_middleware(A2aV1OutboundMiddleware)

    return app
