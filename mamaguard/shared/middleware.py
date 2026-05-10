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
import re
import secrets
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .fhir_hook import FHIR_CONTEXT_KEY, extract_fhir_from_payload
from .logging_utils import redact_headers, redact_payload, safe_pretty_json, token_fingerprint

logger = logging.getLogger(__name__)

LOG_FULL_PAYLOAD = os.getenv("LOG_FULL_PAYLOAD", "false").lower() == "true"

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


# JSON-RPC method aliases: A2A v1 (.NET-style PascalCase) -> v0.3 (slash-style).
# Prompt Opinion's marketplace dispatches with v1 method names, but our
# a2a-python SDK is still on v0.3 — without aliasing, the SDK returns
# JSON-RPC error -32601 ("Method not found") for everything PO sends.
# Spec ref: https://a2a-protocol.org/latest/specification/ §11 (RPC bindings).
JSON_RPC_METHOD_ALIASES = {
    "SendMessage": "message/send",
    "SendStreamingMessage": "message/stream",
    "GetTask": "tasks/get",
    "CancelTask": "tasks/cancel",
    "SetTaskPushNotificationConfig": "tasks/pushNotificationConfig/set",
    "GetTaskPushNotificationConfig": "tasks/pushNotificationConfig/get",
    "ListTaskPushNotificationConfig": "tasks/pushNotificationConfig/list",
    "DeleteTaskPushNotificationConfig": "tasks/pushNotificationConfig/delete",
    "ResubscribeToTask": "tasks/resubscribe",
    "GetAuthenticatedExtendedCard": "agent/authenticatedExtendedCard",
}

_SCOPE_A2A_OUTBOUND_ENUM_STYLE = "mamaguard.a2a_outbound_enum_style"
_A2A_V1_ENUM_STYLE = "v1"

# A2A v1 sends gRPC/proto-style enum values (`ROLE_USER`, `ROLE_AGENT`,
# `KIND_TEXT`, etc.); the v0.3 a2a-python SDK validates against the bare
# lowercase form. Walk the parsed payload and normalize known enum keys
# before the SDK's pydantic model rejects them.
_ENUM_VALUE_NORMALIZERS = {
    "role": {
        "ROLE_USER": "user",
        "ROLE_AGENT": "agent",
    },
    "kind": {
        "KIND_TEXT": "text",
        "KIND_FILE": "file",
        "KIND_DATA": "data",
        "KIND_MESSAGE": "message",
        "KIND_TASK": "task",
        "KIND_STATUS_UPDATE": "status-update",
        "KIND_ARTIFACT_UPDATE": "artifact-update",
    },
    # Accept BOTH ``STATE_*`` (older form) and ``TASK_STATE_*`` (canonical
    # A2A v1 proto names) on inbound. Order matters: dict-comprehension below
    # builds ``_ENUM_VALUE_DENORMALIZERS`` from this mapping with later entries
    # winning; ``TASK_STATE_*`` is placed SECOND so outbound emissions use the
    # canonical proto names per the working PO agent precedent on Devpost.
    "state": {
        "STATE_SUBMITTED": "submitted",
        "STATE_WORKING": "working",
        "STATE_INPUT_REQUIRED": "input-required",
        "STATE_COMPLETED": "completed",
        "STATE_CANCELED": "canceled",
        "STATE_FAILED": "failed",
        "STATE_REJECTED": "rejected",
        "STATE_AUTH_REQUIRED": "auth-required",
        "STATE_UNKNOWN": "unknown",
        "TASK_STATE_SUBMITTED": "submitted",
        "TASK_STATE_WORKING": "working",
        "TASK_STATE_INPUT_REQUIRED": "input-required",
        "TASK_STATE_COMPLETED": "completed",
        "TASK_STATE_CANCELED": "canceled",
        "TASK_STATE_FAILED": "failed",
        "TASK_STATE_REJECTED": "rejected",
        "TASK_STATE_AUTH_REQUIRED": "auth-required",
        "TASK_STATE_UNKNOWN": "unknown",
    },
}


def _normalize_v1_enums(node):
    """Recursively rewrite v1 proto-style enum strings into v0.3 lowercase
    on a parsed-JSON dict/list. Mutates in place; returns whether anything
    changed (for logging)."""
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                mapper = _ENUM_VALUE_NORMALIZERS.get(key)
                if mapper and value in mapper:
                    node[key] = mapper[value]
                    changed = True
            else:
                if _normalize_v1_enums(value):
                    changed = True
    elif isinstance(node, list):
        for item in node:
            if _normalize_v1_enums(item):
                changed = True
    return changed


# Inverse of _ENUM_VALUE_NORMALIZERS — used to re-encode outbound responses so
# v1-strict clients (Prompt Opinion's .NET parser) recognize role/kind/state
# values. PO sends ``STATE_SUBMITTED`` etc.; SDK responds in v0.3 lowercase
# (``submitted``) which PO does NOT recognize as a terminal state →
# "external agent did not respond with a task". We translate on the way out.
_ENUM_VALUE_DENORMALIZERS = {
    field: {v0_3: v1 for v1, v0_3 in mapper.items()}
    for field, mapper in _ENUM_VALUE_NORMALIZERS.items()
}


def _denormalize_v1_enums(node) -> bool:
    """Recursively rewrite v0.3 lowercase enum strings into v1 proto names
    on a parsed-JSON dict/list. Mutates in place; returns whether anything
    changed."""
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                mapper = _ENUM_VALUE_DENORMALIZERS.get(key)
                if mapper and value in mapper:
                    node[key] = mapper[value]
                    changed = True
            else:
                if _denormalize_v1_enums(value):
                    changed = True
    elif isinstance(node, list):
        for item in node:
            if _denormalize_v1_enums(item):
                changed = True
    return changed


# PO forwards FHIR session context as HTTP headers, not JSON-RPC metadata.
# The names below are what PO's BYO consultation tool emits on outbound calls
# (visible in the workspace "FHIR Context Headers" panel). If PO renames or
# adds a header, the all_x_headers log line surfaces it for fast iteration.
PO_FHIR_URL_HEADER = "x-fhir-server-url"
PO_PATIENT_ID_HEADER = "x-patient-id"
PO_FHIR_TOKEN_HEADERS = (
    "x-fhir-access-token",  # PO's actual header name, JWT with po_fhir scope
    "x-fhir-token",
    "x-fhir-authorization",
    "authorization",
)

# Placeholder token used when PO sends URL+patient but no auth header. PO's
# FHIR proxy authorizes via the workspace ID baked into the URL path, so the
# bearer is informational only — but `validate_sharp_context` requires a
# non-empty string, so we inject a clearly-labeled placeholder.
PO_PROXY_TOKEN_PLACEHOLDER = "po-managed"

# Confirmed as of 2026-05-10: PO's BYO ``SendA2AMessage`` tool does NOT forward
# the ``x-fhir-*`` headers it displays in the workspace UI. The only FHIR
# context that reaches the external A2A endpoint is what PO's BYO orchestrator
# inlines in the message body — typically the line
# ``Patient id: 526f3089-77ce-47bd-ab6a-70a54bcfeddb`` (the workspace patient
# UUID). When this fallback is enabled, the middleware parses that UUID and
# pairs it with a self-hosted HAPI URL so sub-agents have FHIR context to
# query. The HAPI fixture must be pre-loaded with the same patient ID
# (see ``scripts/load_po_alias.py``).
FALLBACK_FHIR_URL_ENV = "MAMAGUARD_FALLBACK_FHIR_URL"
FALLBACK_FHIR_TOKEN = "internal"
# Last-resort patient ID when no UUID is in the message and no headers are
# present. Useful for single-patient demo deployments where PO's BYO is
# inconsistent about inlining the patient identifier. Leave unset in
# multi-patient production deployments.
FALLBACK_PATIENT_ID_ENV = "MAMAGUARD_FALLBACK_PATIENT_ID"

# Match "Patient id: <uuid>" / "patient_id=<uuid>" / "Patient/<uuid>" in the
# inline prompt. PO uses lowercase UUIDs; HAPI search is case-sensitive on
# resource IDs, so we preserve the original casing.
_INLINE_PATIENT_ID_RE = re.compile(
    r"\b(?:patient\s*(?:id|/)\s*[:=]?\s*)([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})\b",
    re.IGNORECASE,
)


def _extract_inline_patient_id(parsed_body: dict) -> str:
    """Walk the JSON-RPC body looking for a Patient UUID in any text part.

    Returns the first UUID matched in ``params.message.parts[].text`` (or in
    any ``text`` field a future PO version might use). Returns ``""`` on no
    match. Patient IDs are intentionally narrow-matched (UUID v4 shape) to
    avoid accidentally extracting unrelated identifiers like task IDs.
    """
    if not isinstance(parsed_body, dict):
        return ""

    params = parsed_body.get("params")
    if not isinstance(params, dict):
        return ""

    message = params.get("message")
    if not isinstance(message, dict):
        return ""

    parts = message.get("parts")
    if not isinstance(parts, list):
        return ""

    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if not isinstance(text, str):
            continue
        match = _INLINE_PATIENT_ID_RE.search(text)
        if match:
            return match.group(1)

    return ""


class FhirHeaderMiddleware(BaseHTTPMiddleware):
    """
    Bridge Prompt Opinion's FHIR context HTTP headers into the JSON-RPC body
    as ``params.metadata.fhir-context``, so the existing ADK ``fhir_hook``
    picks them up unmodified.

    PO does NOT include FHIR context in the JSON-RPC body. Its BYO
    ``SendA2AMessage`` tool API only exposes ``externalAgentId`` + ``message``;
    the workspace-level FHIR session (server URL + patient ID, occasionally a
    bearer) is forwarded as headers on the HTTP request. Without this bridge
    every sub-agent sees ``metadata_source=none`` and returns
    "FHIR context is not available" errors.

    Runs regardless of auth so it survives the ``MAMAGUARD_AUTH_DISABLED=true``
    deployment used for the marketplace demo (which skips ApiKeyMiddleware).
    """

    async def dispatch(self, request: Request, call_next):
        if request.method != "POST":
            return await call_next(request)

        fhir_url = request.headers.get(PO_FHIR_URL_HEADER, "").strip()
        patient_id = request.headers.get(PO_PATIENT_ID_HEADER, "").strip()
        fhir_token = ""
        for header_name in PO_FHIR_TOKEN_HEADERS:
            value = request.headers.get(header_name, "").strip()
            if value:
                fhir_token = value
                break

        # Always log the x-* headers PO actually sent. If our extractors miss a
        # new key, this surfaces it without another deploy.
        x_headers_seen = sorted(
            h for h in request.headers.keys() if h.lower().startswith("x-")
        )
        logger.info(
            "fhir_headers_observed url=%s patient_id=%s token=%s x_headers=%s",
            fhir_url or "[EMPTY]",
            patient_id or "[EMPTY]",
            token_fingerprint(fhir_token) if fhir_token else "[EMPTY]",
            x_headers_seen,
        )

        headers_supplied_context = bool(fhir_url or patient_id or fhir_token)
        fallback_url = os.getenv(FALLBACK_FHIR_URL_ENV, "").strip()
        fallback_eligible = bool(fallback_url) and not headers_supplied_context

        if not headers_supplied_context and not fallback_eligible:
            return await call_next(request)

        body_bytes = await request.body()
        if not body_bytes:
            return await call_next(request)

        try:
            parsed = json.loads(body_bytes.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return await call_next(request)

        if not isinstance(parsed, dict):
            return await call_next(request)

        params = parsed.get("params")
        if not isinstance(params, dict):
            return await call_next(request)

        injection_source = "header"
        if fallback_eligible:
            inline_patient_id = _extract_inline_patient_id(parsed)
            fallback_patient_id = os.getenv(FALLBACK_PATIENT_ID_ENV, "").strip()

            chosen_patient_id = inline_patient_id or fallback_patient_id
            if not chosen_patient_id:
                logger.info(
                    "fhir_fallback_skipped reason=no_inline_patient_id_or_env "
                    "fallback_url=%s",
                    fallback_url,
                )
                return await call_next(request)

            fhir_url = fallback_url
            patient_id = chosen_patient_id
            fhir_token = FALLBACK_FHIR_TOKEN
            injection_source = (
                "fallback-inline" if inline_patient_id else "fallback-env"
            )

        # PO's FHIR proxy authorizes by workspace-ID-in-URL — bearer is optional.
        # `validate_sharp_context` requires non-empty token, so use placeholder.
        effective_token = fhir_token or PO_PROXY_TOKEN_PLACEHOLDER

        metadata = params.setdefault("metadata", {})
        metadata[FHIR_CONTEXT_KEY] = {
            "fhirUrl": fhir_url,
            "patientId": patient_id,
            "fhirToken": effective_token,
        }

        body_bytes = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
        request._body = body_bytes  # type: ignore[attr-defined]

        if injection_source.startswith("fallback"):
            logger.info(
                "fhir_context_injected_from_fallback fhir_url=%s patient_id=%s "
                "source=%s",
                fhir_url,
                patient_id,
                injection_source,
            )
        else:
            logger.info(
                "fhir_context_injected_from_headers fhir_url=%s patient_id=%s "
                "token_source=%s",
                fhir_url,
                patient_id,
                "header" if fhir_token != PO_PROXY_TOKEN_PLACEHOLDER else "placeholder",
            )

        return await call_next(request)


class A2aV1OutboundMiddleware(BaseHTTPMiddleware):
    """
    Re-encode outbound A2A enum values from v0.3 lowercase to v1 proto names so
    PO's v1-strict BYO consultation tool recognizes the terminal task state.

    Background: PO posts ``SendStreamingMessage`` with v1 proto-style enums
    (``ROLE_USER``, ``STATE_SUBMITTED``, …). ``JsonRpcMethodAliasMiddleware``
    normalizes those to v0.3 lowercase on the inbound side so the a2a-python
    SDK accepts them. But the SDK then emits SSE events with v0.3 lowercase
    values too (``state: "completed"``); PO's strict-v1 parser doesn't
    recognize those as terminal — it reports
    "the external agent did not respond with a task" even though the agent
    finished and returned a complete 5T artifact.

    This middleware is intentionally version-aware. ``JsonRpcMethodAliasMiddleware``
    marks the request scope only when the inbound request used A2A v1 method
    names or proto-style enums. Lowercase v0.3 clients keep receiving lowercase
    v0.3 responses.

    Streaming responses are buffered line-by-line and ``data: {...}`` events
    are rewritten. Non-streaming JSON-RPC responses are buffered as one JSON
    body and rewritten the same way.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.scope.get(_SCOPE_A2A_OUTBOUND_ENUM_STYLE) != _A2A_V1_ENUM_STYLE:
            return response

        content_type = response.headers.get("content-type", "")
        original_iterator = response.body_iterator

        if "text/event-stream" in content_type.lower():
            response.body_iterator = _denormalized_sse_iterator(original_iterator)
            return response

        if _is_json_content_type(content_type):
            if "content-length" in response.headers:
                del response.headers["content-length"]
            response.body_iterator = _denormalized_json_iterator(original_iterator)
            return response

        return response


# Backwards-compatible alias for older imports/tests.
SseEnumDenormalizerMiddleware = A2aV1OutboundMiddleware


def _is_json_content_type(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


async def _denormalized_sse_iterator(original_iterator):
    buffer = b""
    async for chunk in original_iterator:
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            yield _maybe_denormalize_sse_line(line) + b"\n"
    if buffer:
        yield _maybe_denormalize_sse_line(buffer)


async def _denormalized_json_iterator(original_iterator):
    body = b""
    async for chunk in original_iterator:
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        body += chunk
    yield _maybe_denormalize_json_body(body)


def _maybe_denormalize_json_body(body: bytes) -> bytes:
    """If ``body`` is a JSON-RPC response, rewrite v0.3 enum values to A2A v1
    and wrap a Task result in ``{"task": ...}`` for PO's ``$.result.task``
    validator.

    Malformed JSON is returned untouched so error responses still reach the
    client exactly as generated.
    """
    if not body:
        return body
    try:
        parsed = json.loads(body.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body
    enums_changed = _denormalize_v1_enums(parsed)
    wrap_changed = _wrap_jsonrpc_task_result(parsed)
    if not enums_changed and not wrap_changed:
        return body
    return json.dumps(parsed, ensure_ascii=False).encode("utf-8")


def _wrap_jsonrpc_task_result(parsed) -> bool:
    """If ``parsed`` is a JSON-RPC response whose ``result`` is a Task object
    (``kind == "KIND_TASK"`` after denormalization), wrap it as
    ``result = {"task": <task>}`` so PO's BYO consultation tool's
    ``$.result.task`` validator finds the task.

    The A2A v1 SendMessage spec returns the Task directly under ``result``,
    but PO's BYO consultation tool expects a nested ``task`` key per the
    staff guidance in the Devpost forum thread on
    "did not respond with a task" errors.

    Returns ``True`` if a rewrite happened. Idempotent: if ``result`` is
    already ``{"task": ...}`` it returns ``False``.
    """
    if not isinstance(parsed, dict):
        return False
    result = parsed.get("result")
    if not isinstance(result, dict):
        return False
    # Already wrapped — nothing to do.
    if "task" in result and "kind" not in result:
        return False
    if result.get("kind") != "KIND_TASK":
        return False
    parsed["result"] = {"task": result}
    return True


def _maybe_denormalize_sse_line(line: bytes) -> bytes:
    """If ``line`` is a ``data:`` SSE event with a JSON payload, walk and
    rewrite v0.3 enum values into v1 proto names. Otherwise return as-is.

    Errors are swallowed — a malformed event must still reach the client
    unchanged rather than disappear silently.
    """
    if not line.startswith(b"data:"):
        return line
    payload = line[len(b"data:"):].lstrip()
    if not payload:
        return line
    try:
        parsed = json.loads(payload.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return line
    changed = _denormalize_v1_enums(parsed)
    if not changed:
        return line
    re_encoded = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
    return b"data: " + re_encoded


class JsonRpcMethodAliasMiddleware(BaseHTTPMiddleware):
    """
    Translate A2A v1 JSON-RPC method names to the v0.3 equivalents the
    a2a-python SDK still expects. Logs the original method name so we can
    catch new v1 verbs as the spec evolves.

    Mounts before ApiKeyMiddleware so auth still runs against the rewritten
    body. Only touches POST requests with a JSON body — everything else
    passes through unchanged.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method != "POST":
            return await call_next(request)

        body_bytes = await request.body()
        if not body_bytes:
            return await call_next(request)

        try:
            parsed = json.loads(body_bytes.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return await call_next(request)

        if isinstance(parsed, dict):
            original_method = parsed.get("method")
            method_changed = False
            if isinstance(original_method, str):
                aliased = JSON_RPC_METHOD_ALIASES.get(original_method)
                if aliased and aliased != original_method:
                    parsed["method"] = aliased
                    method_changed = True
                    logger.info(
                        "jsonrpc_method_aliased original=%s rewritten=%s path=%s",
                        original_method, aliased, request.url.path,
                    )
                else:
                    logger.info(
                        "jsonrpc_method_observed name=%s aliased=%s path=%s",
                        original_method,
                        bool(aliased),
                        request.url.path,
                    )

            enums_changed = _normalize_v1_enums(parsed)
            if enums_changed:
                logger.info("jsonrpc_v1_enums_normalized path=%s", request.url.path)

            if method_changed or enums_changed:
                request.scope[_SCOPE_A2A_OUTBOUND_ENUM_STYLE] = _A2A_V1_ENUM_STYLE

            if method_changed or enums_changed:
                body_bytes = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
                request._body = body_bytes  # type: ignore[attr-defined]

        return await call_next(request)


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
                    # Writing to request._body is how Starlette's _CachedRequest
                    # exposes the body to downstream: BaseHTTPMiddleware wraps the
                    # request so wrapped_receive replays from _body once the body
                    # has been consumed here via `await request.body()`. Swapping
                    # in a custom receive does NOT work — call_next uses the
                    # closure-bound wrapped_receive, not request.receive. Pinning
                    # starlette in requirements.txt guards against this contract
                    # shifting under us.
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
