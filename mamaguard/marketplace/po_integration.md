# MamaGuard -- Prompt Opinion FHIR Integration Reference

How FHIR context flows from Prompt Opinion (PO) to MamaGuard, field by field.
Use this when publishing to the PO Marketplace or debugging context issues.

## FHIR Context Flow (End to End)

```
PO Workspace (patient selected)
  |
  |-- X-A2A-Extensions: .../fhir-context   (extension negotiation)
  |-- X-API-Key: <key>                      (authentication)
  |
  v
JSON-RPC request body:
  params.metadata["fhir-context"] = {
    "fhirUrl":    "https://fhir.example.org/r4",
    "fhirToken":  "eyJhbGciOiJ...",
    "patientId":  "Patient/12345"
  }
  |
  v
ApiKeyMiddleware (middleware.py)
  - Validates X-API-Key
  - Bridges message.metadata -> params.metadata if needed
  - Echoes FHIR extension in response header
  |
  v
extract_fhir_context() (fhir_hook.py) -- ADK before_model_callback
  - Reads metadata from 3 locations (priority order)
  - Writes to session state:
      state["fhir_url"]    = "https://fhir.example.org/r4"
      state["fhir_token"]  = "eyJhbGciOiJ..."
      state["patient_id"]  = "Patient/12345"
  |
  v
FHIR tools (_get_fhir_context in fhir_base.py)
  - Read credentials from state
  - Make authenticated FHIR R4 requests
```

## Metadata Field Names

PO sends FHIR context under a single metadata key. MamaGuard accepts two forms:

| Key Format | Example |
|------------|---------|
| Short form | `"fhir-context"` |
| Full SHARP URI | `"https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"` |

Detection is by substring match (`"fhir-context" in key`), so both work.

### Value Object

```json
{
  "fhirUrl":    "https://fhir.example.org/r4",
  "fhirToken":  "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "patientId":  "bench-maria-001"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `fhirUrl` | string | FHIR R4 base URL. Trailing slash is stripped automatically. |
| `fhirToken` | string | Bearer token for FHIR auth. Never logged in full (fingerprint only). |
| `patientId` | string | Patient resource ID (not the full `Patient/` reference). |

The value can be a JSON object or a JSON-encoded string -- both are accepted via `_coerce_fhir_data()`.

### Optional Fields

| Field | Type | When Present |
|-------|------|-------------|
| `permissionTicket` | string (JWT) | When SMART Permission Tickets are enabled (`MAMAGUARD_SMART_TICKETS=true`). Contains SMART v2 scopes restricting which tools can run. |
| `output_format` | string | Sibling key in metadata (not inside fhir-context). Set to `"json"` for structured JSON output instead of 5T markdown. |

## Extension URI

MamaGuard declares a required FHIR extension in its agent card:

```
https://app.promptopinion.ai/schemas/a2a/v1/fhir-context
```

This URI is configurable via the `PO_PLATFORM_BASE_URL` env var (default: `https://app.promptopinion.ai`). The extension is `required=True`, meaning PO must provide FHIR context for the agent to function.

### Extension Negotiation

1. PO sends `X-A2A-Extensions: https://app.promptopinion.ai/schemas/a2a/v1/fhir-context` in the request header.
2. MamaGuard's middleware echoes it back in the response header to confirm activation.
3. This is necessary because the ADK only auto-activates its own internal extensions -- custom extensions must be explicitly activated by the middleware.

## Token Format

PO provides a FHIR bearer token scoped to the selected patient's EHR session. MamaGuard uses it as-is in `Authorization: Bearer <token>` headers on all FHIR requests. It does not validate, decode, or inspect the token -- that's the FHIR server's job.

For HAPI FHIR test servers (like `https://r4.smarthealthit.org`), any non-empty string works as a token.

## Metadata Location Priority

The fhir_hook checks three metadata locations in priority order. PO typically uses location 1.

| Priority | Location | Path in JSON-RPC |
|----------|----------|------------------|
| 1 (highest) | `params.metadata` | `{"params": {"metadata": {"fhir-context": {...}}}}` |
| 2 | `run_config.custom_metadata.a2a_metadata` | Set by middleware bridging |
| 3 (lowest) | `llm_request.contents[-1].metadata` | Last content block metadata |

### Metadata Bridging

If PO sends FHIR context in `params.message.metadata` instead of `params.metadata`, the `ApiKeyMiddleware` automatically bridges it up:

```
params.message.metadata["fhir-context"]  -->  params.metadata["fhir-context"]
```

This handles PO platform variations without requiring changes on PO's side.

## Authentication

All endpoints except `/.well-known/agent-card.json` require an API key.

| Header | Value |
|--------|-------|
| `X-API-Key` | Key configured in `MAMAGUARD_API_KEY` or `MAMAGUARD_API_KEYS` (comma-separated for multiple) |

Keys are validated with `secrets.compare_digest()` (timing-safe). If no key is configured, a dev-only default (`dev-key-local`) is used with a warning.

## Environment Variables

Required for PO integration:

| Variable | Example | Purpose |
|----------|---------|---------|
| `MAMAGUARD_API_KEY` | `po-prod-xxxx` | API key PO uses to authenticate |
| `MAMAGUARD_URL` | `https://mamaguard-xxxxx.run.app` | Public URL for agent card |
| `PO_PLATFORM_BASE_URL` | `https://app.promptopinion.ai` | PO base URL (default, rarely changed) |

Optional:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAMAGUARD_API_KEYS` | (none) | Comma-separated keys (overrides `MAMAGUARD_API_KEY`) |
| `MAMAGUARD_SMART_TICKETS` | `false` | Enable SMART Permission Ticket enforcement |
| `MAMAGUARD_SMART_TICKETS_SECRET` | (none) | HS256 key for dev/test ticket signing |
| `MAMAGUARD_SMART_TICKETS_AUDIENCE` | (none) | Expected JWT `aud` claim |
| `LOG_HOOK_RAW_OBJECTS` | `false` | Log raw callback objects (debug only) |
| `LOG_FULL_PAYLOAD` | `false` | Log incoming HTTP payloads (tokens redacted). Dev only — leave off in production. |

## Troubleshooting

### Missing FHIR context

**Symptom:** Agent responds "FHIR context is not available" or tools return `{"status": "error", "error_message": "missing: fhir_url, fhir_token, patient_id"}`.

**Causes:**
1. **FHIR context not enabled in PO workspace.** Go to BYO Agent settings and verify "Enable FHIR context" is checked.
2. **Extension not activated.** Check that the agent card at `/.well-known/agent-card.json` returns the FHIR extension with `required: true`. PO must request it via `X-A2A-Extensions` header.
3. **Metadata key mismatch.** MamaGuard matches on substring `"fhir-context"`. If PO sends a different key name, it won't be detected. Check logs for `hook_called_no_metadata` or `hook_called_fhir_not_found`.

**Debug:** Set `LOG_HOOK_RAW_OBJECTS=true` and check Cloud Run logs for the full `hook_raw_callback_context` to see exactly what metadata arrived.

### Wrong patient ID format

**Symptom:** FHIR requests return 404 or unexpected patient data.

**Causes:**
1. **Full reference vs. bare ID.** MamaGuard expects a bare ID like `bench-maria-001`, not `Patient/bench-maria-001`. Tools construct the full URL as `{fhir_url}/Patient/{patient_id}`. If PO sends the full reference, FHIR requests will hit `/Patient/Patient/bench-maria-001`.
2. **ID mismatch between PO patient selector and FHIR server.** The patient ID PO sends must exist on the FHIR server connected to that workspace. Verify with: `curl -H "Authorization: Bearer <token>" <fhir_url>/Patient/<patient_id>`.

### Extension not activated

**Symptom:** PO doesn't send FHIR context even though the agent card declares it.

**Causes:**
1. **Agent card not re-fetched.** After updating the extension URI, PO may cache the old agent card. Re-register the external agent or force a refresh in PO settings.
2. **URI mismatch.** The extension URI in the agent card must exactly match what PO expects. Default: `https://app.promptopinion.ai/schemas/a2a/v1/fhir-context`. If `PO_PLATFORM_BASE_URL` is set to a different value, the URI will differ and PO won't recognize it.
3. **Middleware not echoing.** Check that the response includes `X-A2A-Extensions` with the FHIR URI. If the middleware isn't loaded (e.g. custom ASGI setup), the extension won't be activated.

### API key rejected (401/403)

**Symptom:** PO gets 401 Unauthorized or 403 Forbidden.

**Causes:**
1. **Key not set.** Ensure `MAMAGUARD_API_KEY` is set in the deployment environment (Cloud Run env vars).
2. **Key mismatch.** The key PO sends must exactly match. Check for trailing whitespace or encoding issues.
3. **Multiple keys.** Use `MAMAGUARD_API_KEYS` (comma-separated) if PO uses a different key than your dev key.

### FHIR server errors

**Symptom:** Tools return `{"status": "error", "error_message": "Could not reach FHIR server: ..."}`.

**Causes:**
1. **Token expired.** PO session tokens have limited lifetime. The agent prompts instruct to explain what data is unavailable and recommend manual check.
2. **Network unreachable.** If MamaGuard runs on Cloud Run and the FHIR server is behind a firewall, requests will fail. Ensure the FHIR server is reachable from the deployment network.
3. **Wrong FHIR URL.** Verify `fhirUrl` points to a valid FHIR R4 endpoint (should respond to `GET /metadata`).

### JSON output mode not working

**Symptom:** Response is markdown even though `output_format=json` was requested.

**Cause:** `output_format` must be a sibling key in `params.metadata`, not inside the `fhir-context` object:

```json
{
  "params": {
    "metadata": {
      "fhir-context": {"fhirUrl": "...", "fhirToken": "...", "patientId": "..."},
      "output_format": "json"
    }
  }
}
```

## Quick Verification Checklist

Before publishing to the PO Marketplace:

1. **Agent card accessible:** `curl https://YOUR-URL/.well-known/agent-card.json` returns valid JSON with 4 skills and FHIR extension.
2. **API key works:** `curl -H "X-API-Key: YOUR-KEY" https://YOUR-URL/` returns something other than 401/403.
3. **FHIR extension present:** Agent card JSON includes `extensions` array with `uri` containing `fhir-context` and `required: true`.
4. **Smoke test passes:** Run `make smoke` against the deployed agent (update endpoint in `scripts/smoke_test.py`).
5. **PO test query:** In PO, select a patient, ask "Assess maternal risk for this patient", verify structured 5T response with FHIR citations.
