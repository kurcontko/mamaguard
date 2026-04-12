"""
Security middleware -- API key authentication and A2A extension activation.

Every request is blocked unless it carries a valid X-API-Key header.
The only public endpoint is /.well-known/agent-card.json.

When the client sends ``X-A2A-Extensions`` requesting FHIR context activation,
the middleware echoes the extension URI in the response header so Prompt Opinion
knows the agent supports it.  The ADK's ``A2aAgentExecutor`` only auto-activates
its own internal extension; custom extensions declared in the agent card must be
activated explicitly.
"""

import json
import logging
import os
import secrets
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .fhir_hook import extract_fhir_from_payload
from .logging_utils import redact_headers, redact_payload, safe_pretty_json, token_fingerprint

logger = logging.getLogger(__name__)

LOG_FULL_PAYLOAD = os.getenv("LOG_FULL_PAYLOAD", "true").lower() == "true"

# A2A extension negotiation header (per A2A protocol spec).
A2A_EXTENSIONS_HEADER = "X-A2A-Extensions"

# FHIR extension URI — must match the agent card declaration in app.py.
FHIR_EXTENSION_URI = (
    f"{os.getenv('PO_PLATFORM_BASE_URL', 'https://app.promptopinion.ai')}"
    "/schemas/a2a/v1/fhir-context"
)

# Load API keys from environment. Fallback to defaults for local dev only.
_env_keys = os.getenv("MAMAGUARD_API_KEYS", os.getenv("MAMAGUARD_API_KEY", ""))
VALID_API_KEYS: set = {k.strip() for k in _env_keys.split(",") if k.strip()} or {"dev-key-local"}

if VALID_API_KEYS == {"dev-key-local"}:
    logger.warning(
        "SECURITY_DEV_KEY_ACTIVE No MAMAGUARD_API_KEY(S) configured — "
        "using default dev-key-local. Set MAMAGUARD_API_KEY before deploying."
    )


def _activate_extension(response, uri: str) -> None:  # type: ignore[type-arg]
    """Add *uri* to the ``X-A2A-Extensions`` response header.

    Merges with any extensions the A2A SDK already activated (e.g. the ADK's
    own ``a2a-extension``), avoiding duplicates.
    """
    existing = {
        e.strip()
        for e in response.headers.get(A2A_EXTENSIONS_HEADER, "").split(",")
        if e.strip()
    }
    existing.add(uri)
    response.headers[A2A_EXTENSIONS_HEADER] = ", ".join(sorted(existing))


def _is_valid_key(candidate: str) -> bool:
    """Timing-safe API key validation.

    Uses ``secrets.compare_digest`` so response time does not leak
    information about valid keys.  Always iterates all keys to avoid
    leaking the set size.
    """
    result = False
    for valid_key in VALID_API_KEYS:
        if secrets.compare_digest(candidate, valid_key):
            result = True
    return result


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces X-API-Key authentication.
    Also bridges FHIR metadata from params.message.metadata up to
    params.metadata so the ADK callback path can find it.
    """

    async def dispatch(self, request: Request, call_next):
        body_bytes = await request.body()
        body_text = body_bytes.decode("utf-8", errors="replace")

        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            pass

        if LOG_FULL_PAYLOAD:
            redacted_body = safe_pretty_json(redact_payload(parsed)) if parsed else body_text
            logger.info(
                "incoming_http_request path=%s method=%s headers=%s\npayload=\n%s",
                request.url.path, request.method,
                safe_pretty_json(redact_headers(dict(request.headers))),
                redacted_body,
            )

        # Bridge FHIR metadata from message.metadata -> params.metadata
        fhir_key, fhir_data = extract_fhir_from_payload(parsed)

        if isinstance(parsed, dict):
            params = parsed.get("params")
            if isinstance(params, dict):
                if fhir_key and fhir_data and not params.get("metadata"):
                    params["metadata"] = {fhir_key: fhir_data}
                    body_bytes = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
                    request._body = body_bytes  # type: ignore[attr-defined]

                    logger.info(
                        "FHIR_METADATA_BRIDGED source=message.metadata target=params.metadata key=%s",
                        fhir_key,
                    )

        if fhir_data:
            logger.info("FHIR_URL_FOUND value=%s", fhir_data.get("fhirUrl", "[EMPTY]"))
            logger.info("FHIR_TOKEN_FOUND fingerprint=%s", token_fingerprint(fhir_data.get("fhirToken", "")))
            logger.info("FHIR_PATIENT_FOUND value=%s", fhir_data.get("patientId", "[EMPTY]"))
        else:
            logger.info("FHIR_NOT_FOUND_IN_PAYLOAD keys_checked=params.metadata,message.metadata")

        # Parse requested A2A extensions from the incoming header.
        _requested_exts = {
            e.strip()
            for e in request.headers.get(A2A_EXTENSIONS_HEADER, "").split(",")
            if e.strip()
        }

        # Agent-card endpoint is intentionally public.
        if request.url.path == "/.well-known/agent-card.json":
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            logger.warning(
                "security_rejected_missing_api_key path=%s method=%s",
                request.url.path, request.method,
            )
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "detail": "X-API-Key header is required"},
            )

        if not _is_valid_key(api_key):
            logger.warning(
                "security_rejected_invalid_api_key path=%s method=%s key_prefix=%s",
                request.url.path, request.method, api_key[:6],
            )
            return JSONResponse(
                status_code=403,
                content={"error": "Forbidden", "detail": "Invalid API key"},
            )

        logger.info(
            "security_authorized path=%s method=%s key_prefix=%s",
            request.url.path, request.method, api_key[:6],
        )

        response = await call_next(request)

        # Activate FHIR extension in the response if the client requested it.
        # The ADK only auto-activates its own internal extension; our FHIR
        # extension declared in the agent card must be activated explicitly
        # so Prompt Opinion (or any A2A client) sees it echoed back.
        if FHIR_EXTENSION_URI in _requested_exts:
            _activate_extension(response, FHIR_EXTENSION_URI)

        return response
