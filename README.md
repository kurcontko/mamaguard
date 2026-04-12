# MamaGuard: AI-Powered Maternal-Pediatric Care Coordination

> **80% of pregnancy-related deaths are preventable. 40% of new mothers never return for postpartum care.**
> MamaGuard closes the coordination gap with three specialist AI agents, 14 FHIR tools, and the clinician always in control.

Built for the [Agents Assemble](https://agents-assemble.devpost.com/) hackathon. Dual-track submission: **A2A Agent** + **MCP Server** (Superpower), published on the [Prompt Opinion Marketplace](https://promptopinion.ai).

---

## What It Does

MamaGuard is a multi-agent AI care coordination system that analyzes FHIR patient records to support maternal and pediatric health. Three specialist agents coordinate through a single A2A interface:

| Agent | Role | Key Tools |
|-------|------|-----------|
| **Maternal Risk Monitor** | BP trends, glucose control, pregnancy history, postpartum complications | `get_bp_trend`, `get_glucose_trend`, `get_pregnancy_history`, `get_maternal_risk_profile`, `write_risk_assessment` |
| **Pediatric Transition** | Immunization gaps (CDC schedule), developmental milestones (AAP Bright Futures), care gaps | `get_immunization_gaps`, `get_developmental_screening_status`, `get_care_gaps` |
| **SDOH & Outreach** | Insurance coverage gaps, language barriers, food/housing insecurity, community resource lookup, actionable referrals | `get_sdoh_screening`, `find_sdoh_resources`, `write_care_plan`, `create_communication_request` |

Every tool response includes a **Liaison Agent pattern** `clinician_review` object -- AI recommends, clinician decides. When review is required, the agent pauses (`INPUT_REQUIRED` state) until the clinician acts.

---

## Architecture

```
                     Prompt Opinion Platform
                    +--------------------------+
                    |  BYO Agent (configured    |
                    |  in PO with system        |
                    |  prompt + FHIR context)   |
                    +------+----------+--------+
          A2A JSON-RPC |          | MCP (SSE/stdio)
          + FHIR metadata|          | + SHARP params
                         v          v
+--------------------------------+  +--------------------------+
|  MamaGuard A2A Agent           |  |  MamaGuard MCP Server    |
|  (Cloud Run -- Agent track)    |  |  (Superpower track)      |
|  +---------------------------+ |  |  FastMCP, 14 tools       |
|  |  Orchestrator (Gemini)    | |  |  stdio + SSE transport   |
|  |  +-- Maternal Agent       | |  +-----------+--------------+
|  |  +-- Pediatric Agent      | |              |
|  |  +-- SDOH Agent           | |              |
|  +------------+--------------+ |              |
|               |                |              |
|  Shared FHIR Tool Layer        |              |
|  (14 tools, single source     <--- shared code |
|   of truth -- no duplication)  |              |
|  +----------------------------+|              |
|               |                |              |
|  Middleware + FHIR Hook        |              |
+---------------+----------------+              |
                | HTTPS + Bearer Token          |
                +---------------+---------------+
                                v
                       FHIR R4 Server
                     (SMART / HAPI)
```

**Data flow:** Clinician launches MamaGuard from Prompt Opinion > selects patient > PO sends FHIR context (server URL, bearer token, patient ID) via A2A metadata > orchestrator routes to specialist agents > agents query FHIR server using shared tool layer > results include structured risk assessments with evidence citations > clinician reviews and decides.

---

## Impact Hypothesis

| Metric | Current Baseline | Target with MamaGuard |
|--------|:----------------:|:---------------------:|
| Postpartum follow-up completion | 60% attend | 85%+ via proactive gap detection |
| Postpartum hypertensive crisis detection | Median 5 days | Same-day automated BP trend flagging |
| Childhood immunization adherence | 70.4% on time | 90%+ via automated gap detection |
| Clinician chart-review time | 15-20 min manual | <2 min AI-synthesized risk summary |
| SDOH screening completion | <25% of eligible | 80%+ via automated Z-code analysis |

**Cost impact:** Preventable maternal morbidity costs $32.3B/year in the US. Each avoided severe maternal morbidity event saves ~$115K in acute care costs.

---

## Where GenAI Goes Beyond Rules (AI Factor)

1. **Cross-resource synthesis** -- A rule engine flags BP >140/90. MamaGuard looks at 6 pregnancies with 5 losses, uncontrolled HTN across 8 years, concurrent diabetes, and a single postpartum visit -- then explains *why this combination* is dangerous.

2. **Contextual medication safety** -- HCTZ is acceptable for HTN, but in a postpartum patient with diabetes who may be breastfeeding, the recommendation shifts to labetalol. This requires patient-specific clinical context.

3. **SDOH-clinical integration** -- Connecting a Medicaid gap + French language + food insecurity + postpartum BP crisis into a unified outreach plan with culturally appropriate referrals.

4. **Natural language care plans** -- Converting structured FHIR data into prioritized, evidence-cited care summaries using the 5T framework (Talk, Template, Table, Task, Transaction).

See `benchmarks/clinical_reasoning/` for quantified AI Factor evidence: rule-engine baseline vs. MamaGuard synthesis across low/moderate/severe cases.

---

## Quick Start

### Prerequisites

- Python 3.11+
- [Google AI Studio API key](https://aistudio.google.com/) (free)

### Local Development

```bash
# Clone and install
git clone <repo-url> && cd mamaguard
pip install -r mamaguard/requirements.txt

# Configure
cp mamaguard/.env.example mamaguard/.env
# Edit .env: set GOOGLE_API_KEY and MAMAGUARD_API_KEY

# Run the A2A agent
cd mamaguard && python app.py
# Agent card: http://localhost:8001/.well-known/agent-card.json

# Or run the MCP server (stdio -- for Claude Desktop, Cursor)
python -m mamaguard.mcp_server.server

# Or run with SSE transport (for remote clients)
MCP_TRANSPORT=sse MCP_PORT=8080 python -m mamaguard.mcp_server.server
```

### Docker

```bash
docker build -t mamaguard -f mamaguard/Dockerfile mamaguard/
docker run -p 8001:8001 \
  -e GOOGLE_API_KEY=your-key \
  -e MAMAGUARD_API_KEY=your-agent-key \
  mamaguard
```

### Deploy to Cloud Run

```bash
# Full pipeline: pre-deploy checks + deploy + verify
./scripts/deploy.sh

# Or dry run
./scripts/deploy.sh --dry-run
```

---

## Testing

```bash
# Unit tests (671 tests)
python3 -m pytest mamaguard/tests/ -v

# Tier-1 deterministic benchmarks (47 cases)
python3 -m benchmarks.runner

# Pre-deploy check (unit tests + benchmarks, exit 1 if score < 95%)
./scripts/pre_deploy_check.sh

# With HAPI FHIR smoke tests
./scripts/pre_deploy_check.sh --hapi
```

**Test coverage:**
- 671 unit tests across 17 test modules
- 47/47 Tier-1 benchmark cases at 100.0%
- Agent routing, tool invocation, error paths, FHIR base utilities, FHIR writeback, SMART tickets, middleware, golden-file contract tests, LLM-as-judge care plan checkers, FHIR hook, logging utilities, mother-child handoff, MCP protocol integration, SDOH resource classification, A2A app factory and agent card endpoint, benchmark harness infrastructure

---

## Demo Patient: Maria

**Patient/881f534f-d041-425d-a542-cbf669f43e18** -- a 50-year-old Black, French-speaking woman with:

- 6 pregnancies (5 losses), emergency delivery
- Uncontrolled HTN (BP consistently >140/90, spike to 170/98 postpartum)
- DM2 with HbA1c trending upward
- Only ONE postnatal visit, no insurance on record

MamaGuard identifies: **URGENT** risk (Stage 2 HTN + recurrent pregnancy loss + no coverage), generates a prioritized care plan with FHIR evidence citations, flags clinician review, and creates outreach resources including community referrals.

---

## Project Structure

```
mamaguard/
+-- orchestrator/agent.py        # Routes to sub-agents via AgentTool
+-- maternal_agent/agent.py      # Maternal Risk Monitor
+-- pediatric_agent/agent.py     # Pediatric Transition Agent
+-- sdoh_agent/agent.py          # SDOH & Outreach Agent
+-- mcp_server/                  # Standalone MCP server (Superpower track)
|   +-- server.py                # FastMCP, 14 tools, stdio + SSE
|   +-- context.py               # FhirContext adapter (SHARP -> state)
+-- shared/
|   +-- tools/                   # 14 FHIR tools (single source of truth)
|   |   +-- fhir_base.py         # Patient summary, active medications
|   |   +-- maternal.py          # BP trend, glucose, pregnancy history
|   |   +-- pediatric.py         # Immunizations, developmental screening
|   |   +-- sdoh.py              # SDOH screening, resource lookup
|   |   +-- writeback.py         # RiskAssessment, CommunicationRequest, CarePlan
|   +-- app_factory.py           # A2A app + AgentCard creation
|   +-- middleware.py             # API key auth + FHIR metadata bridging
|   +-- fhir_hook.py             # before_model_callback -- credential extraction
|   +-- smart_tickets.py         # SMART Permission Tickets (Mandel spec)
|   +-- sdoh_resources.py        # Offline SDOH resource map
+-- marketplace/                 # Marketplace submission configs (both tracks)
+-- tests/                       # 671 unit tests
+-- app.py                       # A2A entry point
+-- Dockerfile                   # Cloud Run deployment
+-- requirements.txt
benchmarks/
+-- runner.py                    # Tier-1/2/3 benchmark harness
+-- clinical_reasoning/          # AI Factor evidence (rule engine vs. synthesis)
+-- llm_eval/                    # LLM-as-judge care plan checkers
+-- e2e/                         # End-to-end cases + FHIR bundles (11 patients)
+-- medagent/                    # MedAgentBench (42 cases)
scripts/
+-- deploy.sh                    # Cloud Run deploy pipeline
+-- pre_deploy_check.sh          # Pre-deploy verification
```

---

## Key Technologies

| Component | Choice | Why |
|-----------|--------|-----|
| Agent framework | Google ADK + A2A SDK | Reference implementation for A2A protocol |
| LLM | Gemini 2.5 Flash | Free tier, Google AI Studio |
| MCP server | FastMCP | Superpower track, dual submission |
| Healthcare data | FHIR R4 | Industry standard; SMART + HAPI servers |
| FHIR context | SHARP extension | EHR session credentials in A2A/MCP metadata |
| Permission model | SMART Permission Tickets | Josh Mandel's March 2026 spec |
| Deployment | Google Cloud Run | Single container, HTTPS, auto-scaling |
| SDOH resources | findhelp.org / 211 gateway | External directory with curated offline fallback |

---

## Security

- **Liaison Agent pattern** -- AI recommends, clinician decides. No autonomous clinical action.
- **Credentials never in prompt** -- FHIR tokens extracted via `before_model_callback`, stored in session state, never visible to the LLM.
- **API key authentication** -- X-API-Key header enforcement on all endpoints except agent card discovery.
- **SMART Permission Tickets** -- Scope-limited tool authorization (feature-flagged). Each of 14 tools mapped to required SMART v2 scopes.
- **Minimum Necessary** -- Each tool queries only the FHIR resources it needs.
- **Synthetic data only** -- SMART R4 Synthea records. No real PHI.

---

## Built With

Python 3.11 | Google ADK | A2A SDK | Gemini 2.5 Flash | FHIR R4 | FastMCP | SMART/HAPI | Google Cloud Run | Docker | httpx | uvicorn | PyJWT

---

## Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) -- Full architecture, agent definitions, security model, implementation plan
- [`mamaguard/marketplace/`](mamaguard/marketplace/) -- Marketplace setup guides, system prompts, demo script
- [`mamaguard/mcp_server/README.md`](mamaguard/mcp_server/README.md) -- MCP server docs, tool reference, Docker

---

## License

Hackathon submission -- see hackathon rules for usage terms.
