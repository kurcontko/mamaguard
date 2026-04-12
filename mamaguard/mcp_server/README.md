# MamaGuard MCP Server

Standalone MCP server exposing 15 FHIR tools for maternal-pediatric care coordination. Shares tool implementations with the ADK agents (single source of truth -- no duplication).

## Quick Start

```bash
# Install dependencies
pip install -r mamaguard/requirements.txt

# Run with stdio transport (default -- for Claude Desktop, Cursor, etc.)
python -m mamaguard.mcp_server.server

# Run with SSE transport (for remote/web clients)
MCP_TRANSPORT=sse MCP_PORT=8080 python -m mamaguard.mcp_server.server
```

## Architecture

```
MCP Client (Claude Desktop / Cursor / PO BYO Agent / custom)
    │
    │  MCP protocol (stdio or SSE)
    ▼
mamaguard/mcp_server/server.py     ← FastMCP server, 15 tool registrations
    │
    │  Direct Python imports (no HTTP, no duplication)
    ▼
mamaguard/shared/tools/*           ← Shared tool implementations
    │
    │  httpx + Bearer token
    ▼
FHIR R4 Server (SMART / HAPI)
```

The MCP server wraps the same tool functions used by the ADK agents. Each tool accepts `fhir_url`, `fhir_token`, and `patient_id` as explicit parameters (SHARP extension pattern), so any MCP client can pass EHR session credentials without middleware.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | Transport protocol: `stdio` or `sse` |
| `MCP_HOST` | `0.0.0.0` | Bind host for SSE transport |
| `MCP_PORT` | `8080` | Bind port for SSE transport |
| `MAMAGUARD_SDOH_API_URL` | *(empty)* | External SDOH directory URL for `find_sdoh_resources` |
| `MAMAGUARD_SDOH_API_KEY` | *(empty)* | API key for external SDOH directory |
| `MAMAGUARD_SMART_TICKETS` | `false` | Enable SMART Permission Ticket enforcement |
| `MAMAGUARD_SMART_TICKETS_SECRET` | *(empty)* | HS256 signing key for dev/test tickets |
| `MAMAGUARD_SMART_TICKETS_AUDIENCE` | *(empty)* | Expected JWT `aud` claim value |

## Tools

Every tool requires three SHARP context parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `fhir_url` | `str` | Base URL of the FHIR R4 server |
| `fhir_token` | `str` | Bearer token for FHIR server authentication |
| `patient_id` | `str` | FHIR Patient resource ID |

### Base Tools

| Tool | Additional Params | Description |
|------|------------------|-------------|
| `get_patient_summary` | -- | Demographics, conditions, medications, recent vitals |
| `get_active_medications` | -- | Active medications with dosage instructions |
| `find_linked_newborn` | `mother_patient_id: str` | Find child Patients linked via RelatedPerson |

### Maternal Tools

| Tool | Additional Params | Description |
|------|------------------|-------------|
| `get_bp_trend` | `months_back: int = 24` | BP readings, trend direction, >140/90 alert |
| `get_glucose_trend` | `months_back: int = 24` | Glucose + HbA1c readings, trend analysis |
| `get_pregnancy_history` | -- | Gravida/para summary, outcomes, complications |
| `get_maternal_risk_profile` | -- | Compound risk profile: conditions + obs + meds |

### Pediatric Tools

| Tool | Additional Params | Description |
|------|------------------|-------------|
| `get_immunization_gaps` | -- | Due vs received vaccines per ACIP schedule |
| `get_developmental_screening_status` | -- | ASQ/M-CHAT/PEDS screening status |
| `get_care_gaps` | -- | Overdue screenings, missed appointments, unmet goals |

### SDOH Tools

| Tool | Additional Params | Description |
|------|------------------|-------------|
| `get_sdoh_screening` | -- | Z-code conditions, coverage gaps, language barriers |
| `find_sdoh_resources` | `category_or_code: str`, `zip_code: str` | Concrete resources for an SDOH need + location |

### Write-back Tools

| Tool | Additional Params | Description |
|------|------------------|-------------|
| `write_risk_assessment` | `risk_type`, `probability`, `basis`, `mitigation` | POST RiskAssessment to FHIR server |
| `create_communication_request` | `medium`, `content`, `priority="routine"` | POST CommunicationRequest for outreach |
| `write_care_plan` | `category`, `goal_description`, `resource_name`, `resource_contact`, `resource_url=""`, `z_code=""` | POST linked Goal + CarePlan for SDOH referral |

### Response Format

Read tools return JSON with a `clinician_review` object (Liaison Agent pattern):

```json
{
  "data": { "readings": [...], "trend": "increasing", "alert": true },
  "clinician_review": {
    "required": true,
    "reason": "BP trend shows postpartum spike to 170/98",
    "recommendation": "Consider adding labetalol",
    "evidence_basis": ["Observation/xyz (BP 170/98 on 2019-10-16)"],
    "confidence": 0.85
  }
}
```

Write tools return the created resource ID or a structured error.

## SHARP Extension Context

The MCP server implements the SHARP extension pattern for FHIR context propagation. Instead of relying on middleware or session state (as the ADK agents do), each tool accepts credentials as explicit parameters.

The `FhirContext` adapter (`context.py`) also supports constructing context from a SHARP dict:

```python
from mamaguard.mcp_server.context import FhirContext

# From SHARP extension metadata
ctx = FhirContext.from_sharp({
    "fhirUrl": "https://r4.smarthealthit.org",
    "fhirToken": "eyJ...",
    "patientId": "881f534f-d041-425d-a542-cbf669f43e18"
})
```

## Docker

The MCP server module exports an `sse_app` (Starlette ASGI app) so the
same Dockerfile used for the A2A agent also serves the MCP server via
uvicorn — just override `AGENT_MODULE` and `PORT`:

```bash
# Build
docker build -t mamaguard-mcp -f mamaguard/Dockerfile mamaguard/

# Run with SSE transport (uvicorn serves the ASGI app)
docker run -p 8080:8080 \
  -e AGENT_MODULE=mamaguard.mcp_server.server:sse_app \
  -e PORT=8080 \
  mamaguard-mcp
```

## Tests

```bash
# MCP server tests only (40 tests)
python -m pytest mamaguard/tests/test_mcp_server.py -v

# Full suite
python -m pytest mamaguard/tests/ -v
```

Tests cover: tool registration (all 15), tool invocation with mocked FHIR, FHIR context propagation, SHARP deserialization, and error handling.
