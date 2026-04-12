# MamaGuard — Architecture, Plan & Project Structure

**Maternal-Pediatric Care Coordination Agent**
Hackathon: Agents Assemble | Deadline: May 11, 2026 | Track: A2A Agent

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
   - 2.1 [High-Level Architecture](#21-high-level-architecture)
   - 2.2 [Agent Topology](#22-agent-topology)
   - 2.3 [Data Flow](#23-data-flow)
   - 2.4 [FHIR Tool Layer](#24-fhir-tool-layer-adk-tools-not-a-standalone-mcp-server)
   - 2.5 [A2A Agent Definitions](#25-a2a-agent-definitions)
   - 2.6 [Security Architecture](#26-security-architecture)
   - 2.7 [Prompt Opinion Integration](#27-prompt-opinion-integration)
   - 2.8 [Standalone MCP Server (Phase 2a)](#28-standalone-mcp-server-phase-2a)
3. [Project Structure](#3-project-structure)
4. [Tech Stack](#4-tech-stack)
5. [FHIR Data Strategy](#5-fhir-data-strategy)
6. [Implementation Plan](#6-implementation-plan)
7. [Demo Strategy](#7-demo-strategy)
8. [Submission Checklist](#8-submission-checklist)
9. [Risk Register](#9-risk-register)

---

## 1. System Overview

### What It Is

MamaGuard is a multi-agent AI care coordination system for maternal and pediatric health. It analyzes FHIR patient records to:

- **Monitor maternal risk** — BP trends, glucose control, pregnancy complications, postpartum risk
- **Manage pediatric transitions** — newborn screening, immunization gaps, developmental milestones
- **Screen for SDOH** — insurance coverage gaps, food insecurity, language barriers, community resources
- **Coordinate care** — synthesize findings into prioritized action plans, pause for clinician review

### Why It Wins

| Judge | Direct Hit |
|-------|-----------|
| Stephon Proctor (CHOP) | Pediatric care, extends CHIPPER's MCP approach |
| Alice Zheng (Foreground Capital) | Women's health VC, maternal health is her #1 thesis |
| Josh Mandel (Microsoft) | MCP + FHIR + Liaison Agent pattern — his own innovations |
| Joshua Hickey (Mayo) | "Patient360" across maternal-pediatric journey |
| Piyush Mathur (Cleveland Clinic) | Patient safety, maternal ICU (preeclampsia/HELLP) |
| Parth Tripathi (Google) | Multi-agent A2A showcase |

### Potential Impact Hypothesis (Measurable Claims)

The judging rubric asks for a "clear hypothesis for improving outcomes, costs, or time." MamaGuard's impact hypothesis, with measurable metrics:

| Metric | Baseline (literature) | Target with MamaGuard | Source |
|--------|----------------------|----------------------|--------|
| **Postpartum follow-up completion rate** | 60% of mothers attend postpartum visit (40% never return) | 85%+ via proactive outreach + gap detection + CommunicationRequest tracking | ACOG Committee Opinion #736 |
| **Postpartum hypertensive crisis detection** | Median 5 days to detect postpartum BP emergency | Same-day flagging via automated BP trend analysis on FHIR Observations | Baylor 2023 maternal morbidity study |
| **Childhood immunization schedule adherence** | 70.4% of children receive full series on time (CDC NIS 2024) | 90%+ via automated gap detection + care coordinator task generation | CDC National Immunization Survey |
| **Clinician chart-review time for maternal risk** | 15-20 min manual review of multi-resource patient record | <2 min to review AI-synthesized risk summary with evidence citations | Mayo Clinic workflow analysis |
| **SDOH screening completion rate** | <25% of eligible patients screened for SDOH (NCQA 2025) | 80%+ via automated Z-code + Coverage analysis requiring no clinician time for initial screen | CMS SDOH screening mandate 2026 |
| **Preventable maternal mortality** | 80% of pregnancy-related deaths are preventable (CDC 2024) | Reduction via earlier detection of hypertensive crisis, coverage gaps, and care fragmentation | CDC MMRC Report |

**Cost impact:** Preventable maternal morbidity costs $32.3B/year in the US (Mathematica 2024). Each avoided severe maternal morbidity event saves ~$115K in acute care costs. MamaGuard targets the coordination gap that accounts for the majority of preventable cases.

**Evaluation frame for demo:** Show Maria's case as a concrete before/after. Without MamaGuard: BP spike undetected for weeks, no SDOH screening, insurance lapses, newborn misses early vaccines. With MamaGuard: same-day flag, outreach initiated, Medicaid extension identified, immunization schedule tracked.

### Where GenAI Goes Beyond Rule-Based CDS (AI Factor)

The judging rubric asks: "Does it use GenAI for something rule-based software cannot do?" MamaGuard's AI Factor is **compound clinical reasoning across heterogeneous data**, not threshold checking. Specifically:

1. **Cross-resource narrative synthesis.** A rule engine can flag BP >140/90. It cannot look at 6 pregnancies with 5 losses, an obstetric emergency, uncontrolled HTN across 8 years of readings, concurrent diabetes with neuropathy, and a single postpartum visit — then synthesize a risk narrative that explains *why this combination* is dangerous and what the prioritized intervention sequence should be. The LLM reasons over the *interaction* of conditions, not each condition in isolation.

2. **Contextual medication safety.** Hydrochlorothiazide is generally acceptable for HTN, but in a postpartum patient with diabetes who is potentially breastfeeding and has a BP spike to 170/98, the recommendation shifts to labetalol — a judgment that depends on patient-specific clinical context (pregnancy status, comorbidities, breastfeeding status, prior med history). Rule-based systems encode drug-drug interactions; they do not reason about patient-context-dependent prescribing appropriateness.

3. **SDOH-clinical risk integration.** Connecting a Medicaid coverage gap (Coverage resource) + French language preference (Patient resource) + food insecurity risk (Condition Z-code) + postpartum hypertensive crisis (Observation trend) into a unified outreach plan with culturally appropriate, language-matched referrals requires reasoning across clinical and social domains simultaneously. No rule engine spans this.

4. **Natural language care plan generation.** Converting structured FHIR data into prioritized, clinician-readable care coordination summaries with evidence citations, confidence levels, and specific next-step recommendations — formatted for different audiences (OB, pediatrician, social worker, care coordinator) — is a generative task.

5. **Temporal pattern recognition.** Identifying that Maria's BP has been Stage 2 across 6 readings over 8 years *despite* medication, combined with worsening postpartum, suggests medication non-response — a pattern that requires reasoning over longitudinal trends rather than point-in-time threshold checks.

**What the tools do vs. what the LLM does:** The FHIR tools are data retrieval functions (structured queries, threshold flags). The LLM's job is *reasoning over the retrieved data*: synthesizing multi-resource findings, generating contextual recommendations, prioritizing interventions, and producing human-readable care plans. The tools are the eyes; the LLM is the brain.

### Adoption Matrix

Every feature falls into one of three tiers. Only "Adopt Now" items block submission.

#### Adopt Now (must ship for Stage 1 + judging)

| Feature | Rationale |
|---------|-----------|
| A2A agent (orchestrator + 3 sub-agents) | Core submission; Track B requirement |
| BYO Agent on PO Marketplace | The actual submission artifact judges launch |
| FHIR tool layer (ADK in-process) | Data access for all agent reasoning |
| SHARP-pattern FHIR context handling | Required by PO for FHIR-aware agents |
| Liaison Agent pattern (INPUT_REQUIRED) | Key differentiator for Mandel; Non-Device CDS |
| FHIR write-back (RiskAssessment, CommunicationRequest) | Bidirectional FHIR differentiator |
| Two-invocation mother/child handoff | Honest, patient-scoped, feasible workflow |
| Structured audit logging (per tool call) | Compliance design intent without failure surface |
| Public YouTube demo video | Rules requirement |
| X-API-Key agent auth | Minimum viable agent security |

#### Stretch (implement if time allows, behind flags)

| Feature | Rationale | Gate |
|---------|-----------|------|
| ~~SMART Permission Tickets validation~~ | **Implemented.** See [SMART Permission Tickets Spec Compliance](#smart-permission-tickets-spec-compliance) below. Feature-flagged via `MAMAGUARD_SMART_TICKETS=true`. | Done |
| FHIR AuditEvent write-back | Defensible compliance claim, but adds failure surface. Best-effort emission behind flag, HAPI-only (SMART may reject). | Phase 4, HAPI target only |
| Automatic mother-child linkage via RelatedPerson | Optional demo enhancement only. RelatedPerson is person-to-patient, not patient-to-patient linkage. Do not center architecture on posting linkage resources to shared sandbox. | Phase 3, only if writable HAPI env is set up |

#### Defer (not built for this submission)

| Feature | Rationale |
|---------|-----------|
| ~~Standalone MCP Server (Superpower track)~~ | **Implemented.** See [Section 2.8](#28-standalone-mcp-server-phase-2a) below. FastMCP server exposing all 14 FHIR tools, SHARP context, stdio + SSE transports, 40 tests. Marketplace config in `marketplace/mcp_config.json`. | Done |
| ~~External SDOH APIs (211.org, findhelp.org)~~ | **Implemented.** `find_sdoh_resources` hits external directory with 5s timeout; curated offline fallback (211, WIC, SNAP, HUD, etc.) so agent is always actionable. | Done |
| Multi-model consensus (ClinicalMem-style) | Cost, complexity, not needed for judging criteria |
| Wearable data integration | No FHIR source available in sandbox |
| CDS Hooks implementation | Interesting pattern but adds protocol surface without judging payoff |

### Core Design Principles

1. **Liaison Agent Pattern** — AI analyzes and recommends; clinician decides. Never autonomous clinical action.
2. **Bidirectional FHIR** — Reads patient data AND writes RiskAssessment + CommunicationRequest back.
3. **Credentials never in prompt** — FHIR tokens extracted via `before_model_callback`, stored in session state.
4. **Minimum Necessary** — Each agent/tool queries only the FHIR resources it needs.
5. **Real data, synthetic patients** — SMART R4 sandbox with Synthea-generated records.

---

## 2. Architecture

### 2.1 High-Level Architecture

```
                         Prompt Opinion Platform
                        ┌─────────────────────────┐
                        │  BYO Agent (configured   │
                        │  in PO with system       │
                        │  prompt + FHIR context)  │
                        └──────┬──────────┬───────┘
              A2A JSON-RPC │          │ MCP (SSE/stdio)
              + FHIR metadata│          │ + SHARP params
                             ▼          ▼
┌────────────────────────────────┐  ┌──────────────────────────┐
│  MamaGuard A2A Agent           │  │  MamaGuard MCP Server    │
│  (Cloud Run — Agent track)     │  │  (Superpower track)      │
│  ┌──────────────────────────┐  │  │  FastMCP, 14 tools       │
│  │  Orchestrator            │  │  │  stdio + SSE transport   │
│  │  ├── Maternal Agent      │  │  │                          │
│  │  ├── Pediatric Agent     │  │  └────────────┬─────────────┘
│  │  └── SDOH Agent          │  │               │
│  └──────────┬───────────────┘  │               │
│             │                  │               │
│  Shared FHIR Tool Layer        │               │
│  ┌──────────────────────────┐  │               │
│  │  14 tools: base, maternal,│  │  (same tools, │
│  │  peds, SDOH, writeback   │◄─┼───shared code)│
│  └──────────┬───────────────┘  │               │
│             │                  │               │
│  Middleware + FHIR Hook        │               │
└─────────────┼──────────────────┘               │
              │ HTTPS + Bearer Token             │
              └──────────────┬───────────────────┘
                             ▼
                    FHIR R4 Server (SMART / HAPI)
```

### 2.2 Agent Topology

**Architecture choice: Single external agent with in-process sub-agents**

```
mamaguard_orchestrator (exposed via A2A)
  ├── AgentTool → maternal_risk_agent     (in-process, no HTTP)
  ├── AgentTool → pediatric_transition_agent (in-process, no HTTP)
  └── AgentTool → sdoh_outreach_agent     (in-process, no HTTP)
```

**Why this topology:**
- In-process sub-agents share session state (FHIR credentials propagate via `before_model_callback`)
- Single container, single URL, single deployment
- `AgentTool` routing is a proven pattern from `po-adk-python`

**Marketplace artifacts: Dual submission (Agent + Superpower tracks).**
The **BYO Agent** (Agent track) is the primary submission — it consults the external A2A agent on Cloud Run for all clinical queries. The **MCP server** (Superpower track) is the second artifact — it exposes the same 14 FHIR tools via MCP, attachable to any BYO Agent or usable from Claude Desktop/Cursor. Both are published to the Prompt Opinion Marketplace. From the judge's perspective, they open the Marketplace, find "MamaGuard", launch it, select a patient, and interact — all within PO. The external agent and MCP server are infrastructure; the BYO Agents are the submission surface.

### 2.3 Data Flow

```
1. Clinician opens PO BYO Agent → selects patient → asks about Maria
2. PO sends A2A JSON-RPC to MamaGuard with FHIR context in metadata:
   {
     "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context": {
       "fhirUrl": "https://app.promptopinion.ai/api/workspaces/{id}/fhir",
       "fhirToken": "eyJ...",
       "patientId": "881f534f-d041-425d-a542-cbf669f43e18"
     }
   }
3. middleware.py: validates X-API-Key, bridges metadata to ADK-expected location
4. fhir_hook.py: before_model_callback extracts FHIR creds → session state
5. Orchestrator routes to sub-agents via AgentTool (shared session state)
6. Sub-agent tools read from tool_context.state["fhir_url"], ["fhir_token"], ["patient_id"]
7. Tools call FHIR server with httpx + Bearer token
8. Results include clinician_review object when human judgment needed
9. If clinician_review.required == true → A2A task state → INPUT_REQUIRED
10. Clinician reviews, provides input → agent continues
```

### 2.4 FHIR Tool Layer

The tools below are **Google ADK tool functions** called in-process by sub-agents. The same tool implementations are also exposed via the standalone MCP server (see [Section 2.8](#28-standalone-mcp-server-phase-2a)) — single source of truth, no duplication.

14 tools organized by domain:

#### Base Tools (reused from po-adk-python)

| Tool | Parameters | Returns | FHIR Queries |
|------|-----------|---------|-------------|
| `get_patient_summary` | `patient_id` | Demographics, active conditions, meds, recent vitals | Patient, Condition, MedicationRequest, Observation (latest) |
| `get_active_medications` | `patient_id` | Active meds with dosages, interaction flags | MedicationRequest (status=active) |

#### Maternal Tools (NEW)

| Tool | Parameters | Returns | FHIR Queries |
|------|-----------|---------|-------------|
| `get_maternal_risk_profile` | `patient_id` | Conditions, BP trend, meds, pregnancy history, risk score | Condition (pregnancy SNOMEDs), Observation (BP/glucose/HbA1c), MedicationRequest, Encounter |
| `get_bp_trend` | `patient_id`, `months_back=24` | BP readings with dates, trend direction, alert if >140/90 | Observation (LOINC 55284-4, sorted by date) |
| `get_glucose_trend` | `patient_id`, `months_back=24` | Glucose + HbA1c readings, trend direction | Observation (LOINC 2339-0, 4548-4) |
| `get_pregnancy_history` | `patient_id` | All pregnancies with outcomes, complications, dates | Condition (SNOMED 72892002, 35999006, 19169002, 156073000) |

#### Pediatric Tools (NEW)

| Tool | Parameters | Returns | FHIR Queries |
|------|-----------|---------|-------------|
| `get_immunization_gaps` | `patient_id`, `age_months` | Due vs received vaccines, gap list per CDC schedule | Immunization (all), Patient (DOB) |
| `get_developmental_screening_status` | `patient_id` | Completed vs due screenings per AAP Bright Futures | Observation (developmental LOINCs), Patient (DOB) |
| `get_care_gaps` | `patient_id` | Overdue screenings, missed appointments, unmet goals | CarePlan, Goal, Encounter, Observation |

#### SDOH Tools (NEW)

| Tool | Parameters | Returns | FHIR Queries |
|------|-----------|---------|-------------|
| `get_sdoh_screening` | `patient_id` | SDOH conditions (Z-codes), questionnaire responses, risk factors | Condition (SNOMED Z55-Z65), QuestionnaireResponse, Coverage |
| `find_sdoh_resources` | `category_or_code`, `zip_code` | Concrete community resources for SDOH need + location | External directory / offline fallback |

#### Write-back Tools (NEW)

| Tool | Parameters | Returns | FHIR Queries |
|------|-----------|---------|-------------|
| `write_risk_assessment` | `patient_id`, `risk_type`, `probability`, `basis`, `mitigation` | Created RiskAssessment resource ID | POST RiskAssessment |
| `create_communication_request` | `patient_id`, `medium`, `content`, `priority` | Created CommunicationRequest resource ID | POST CommunicationRequest |
| `write_care_plan` | `patient_id`, `category`, `goal_description`, `resource_name`, `resource_contact`, `resource_url`, `z_code` | Linked Goal + CarePlan resource IDs | POST Goal + POST CarePlan |

#### Liaison Agent Pattern

Every tool response includes:
```json
{
  "data": { "..." },
  "clinician_review": {
    "required": true|false,
    "reason": "BP trend shows postpartum spike to 170/98",
    "recommendation": "Consider adding labetalol",
    "evidence_basis": ["Observation/xyz (BP 170/98 on 2019-10-16)", "ACOG Bulletin #222"],
    "confidence": 0.85
  }
}
```

When `required: true` → orchestrator transitions A2A task to `INPUT_REQUIRED`.

### 2.5 A2A Agent Definitions

#### Agent Card (served at `/.well-known/agent-card.json`)

```json
{
  "name": "MamaGuard Care Coordinator",
  "description": "Maternal-pediatric care coordination agent. Monitors high-risk pregnancies, manages mother-to-child care transitions, screens for SDOH, coordinates outreach. Pauses for clinician review on critical decisions.",
  "url": "https://mamaguard-xxxxx.run.app",
  "version": "1.0.0",
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "stateTransitionHistory": true,
    "extensions": [{
      "uri": "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context",
      "description": "FHIR R4 context for secure patient data access",
      "required": true
    }]
  },
  "skills": [
    {"id": "maternal-risk-assessment", "name": "Maternal Risk Assessment",
     "description": "Analyzes maternal risk factors: BP trends, glucose, pregnancy history, postpartum complications. Pauses for clinician review.",
     "tags": ["maternal", "risk", "pregnancy", "fhir"]},
    {"id": "pediatric-care-transition", "name": "Pediatric Care Transition",
     "description": "Manages newborn screening, immunization schedule, developmental milestones per CDC/AAP guidelines.",
     "tags": ["pediatric", "immunization", "screening", "newborn"]},
    {"id": "sdoh-screening-outreach", "name": "SDOH Screening & Outreach",
     "description": "Screens for SDOH risks, insurance gaps, connects to community resources, generates outreach requests.",
     "tags": ["sdoh", "social-determinants", "outreach"]},
    {"id": "comprehensive-care-plan", "name": "Comprehensive Care Plan",
     "description": "Synthesizes maternal, pediatric, and SDOH findings into prioritized care coordination plan.",
     "tags": ["care-plan", "coordination", "summary"]}
  ],
  "securitySchemes": {
    "apiKey": {"type": "apiKey", "name": "X-API-Key", "in": "header"}
  },
  "security": [{"apiKey": []}]
}
```

#### Sub-Agent Specifications

| Agent | Name | Model | Tools | Key Behavior |
|-------|------|-------|-------|-------------|
| **Orchestrator** | `mamaguard_orchestrator` | gemini-2.5-flash | `AgentTool(maternal)`, `AgentTool(pediatric)`, `AgentTool(sdoh)` | Routes sequentially: maternal → pediatric → SDOH → synthesize. Outputs via 5T framework (Talk/Template/Table/Task/Transaction). Adds Liaison notice. |
| **Maternal Risk Monitor** | `maternal_risk_agent` | gemini-2.5-flash | `get_maternal_risk_profile`, `get_bp_trend`, `get_glucose_trend`, `get_pregnancy_history`, `get_active_medications`, `write_risk_assessment` | Calls profile → trends → history → meds. Produces risk-stratified assessment. Marks medication changes as `clinician_review.required`. Cites FHIR resource IDs. |
| **Pediatric Transition** | `pediatric_transition_agent` | gemini-2.5-flash | `get_patient_summary`, `get_immunization_gaps`, `get_developmental_screening_status`, `get_care_gaps`, `create_communication_request` | Maps CDC immunization schedule against received vaccines. Checks AAP Bright Futures milestones. Generates tasks with due dates. |
| **SDOH + Outreach** | `sdoh_outreach_agent` | gemini-2.5-flash | `get_sdoh_screening`, `find_sdoh_resources`, `get_patient_summary`, `create_communication_request`, `write_care_plan`, `get_care_gaps` | Identifies Z-code conditions, insurance gaps, language barriers. Looks up actionable community resources (findhelp.org / 211 gateway with offline fallback). Creates linked Goal + CarePlan for SDOH referrals. Creates CommunicationRequest resources. |

All sub-agents use `before_model_callback=extract_fhir_context` for credential extraction.

#### Mother-to-Child Handoff Mechanism

**Problem:** The BYO Agent is patient-scoped (one patient at a time). The SMART FHIR sandbox does not link mother and child Patient resources. The "pediatric care transition" skill needs to reason about the child's record when the agent was launched in the mother's context.

**Solution: Two-invocation workflow with explicit patient switch.**

The orchestrator does NOT attempt to access a child's record from the mother's session. Instead:

1. **Maternal session (Patient = Maria):** The Maternal Risk Monitor and SDOH Agent run against Maria's record. The orchestrator's output includes a structured handoff section:
   ```
   ## Pediatric Transition — Action Required
   To complete the care coordination, switch patient context to Maria's newborn
   and invoke the "Pediatric Care Transition" skill. The following maternal risk
   factors should inform the pediatric assessment:
   - Maternal DM2 → screen newborn for neonatal hypoglycemia
   - Obstetric emergency delivery → monitor for birth trauma sequelae
   - No insurance on record → verify newborn Medicaid enrollment
   ```

2. **Pediatric session (Patient = newborn):** The clinician (or BYO Agent prompt) switches patient context to the child. The Pediatric Transition Agent runs against the child's Immunization, Observation, and Condition resources. It references the maternal handoff notes from the prior session.

**Why this is honest and feasible:**
- It respects the patient-scoped security model (no cross-patient data leakage)
- It matches real clinical workflow — OB hands off to pediatrician with a summary
- It avoids fabricating a mother-child FHIR link that doesn't exist in the data
- The demo shows both sessions sequentially: "First, let's look at Maria... Now, switching to her newborn..."

**Demo approach:** Pre-select a Synthea pediatric patient (newborn age range) as the "child." The narrative connects them; the FHIR data doesn't need to. The demo voiceover says "Maria's newborn" while the system correctly operates on a separate patient record. This is transparent to judges — real EHRs would have `RelatedPerson` links, which we'd use in production.

**Stretch: Automatic linkage (do NOT make this the baseline).** RelatedPerson is a person-to-patient resource, not a general patient-to-patient linkage primitive. Posting synthetic linkage resources to a shared demo sandbox is fragile and may confuse judges. If a writable FHIR environment we control (e.g., our own HAPI instance) is available, automatic linkage can be an optional demo enhancement — but the two-invocation workflow remains the architectural baseline.

### 2.6 Security Architecture

| Layer | Implementation | Rationale |
|-------|---------------|-----------|
| **Transport** | HTTPS (Cloud Run enforces TLS) | A2A spec requirement |
| **Agent Auth** | X-API-Key header | Matches po-adk-python pattern |
| **FHIR Auth** | Bearer token from A2A FHIR context metadata | Token never enters LLM prompt |
| **Data** | Synthetic only (SMART R4 Synthea data) | Hackathon rule: real PHI = disqualification |
| **Audit** | Structured logging per tool call (tool name, patient ID, timestamp, action, outcome). Core scope. | HIPAA compliance design intent via application logs |
| **Audit (stretch)** | FHIR AuditEvent POST behind feature flag, HAPI-only target. Not in critical path. | Best-effort compliance demo; do not add to SMART sandbox |
| **Human-in-loop** | Liaison Agent pattern → `INPUT_REQUIRED` state | Non-Device CDS (FDA); Mandel's pattern |
| **Scoping** | Narrow per-tool FHIR queries | Minimum Necessary Rule (HIPAA) |
| **Credentials** | `before_model_callback` → session state | Credentials never visible to LLM |
| **Input validation** | Sanitize all inter-agent inputs | Prompt injection defense |

#### Key Security Patterns (from reference implementations)

| Pattern | Source |
|---------|--------|
| Credentials never in prompt | po-adk-python `fhir_hook.py` |
| AgentTool for in-process routing (shared session) | po-adk-python orchestrator |
| Patient ID from JWT `patient` claim | po-community-mcp `fhir-utilities.ts` |
| Output size limits | health-record-mcp (2MB grep, 500KB query) |
| Per-request server creation (header isolation) | po-community-mcp `index.ts` |
| FHIR context metadata URI match | `https://app.promptopinion.ai/schemas/a2a/v1/fhir-context` |
| SMART Permission Tickets | `mamaguard/shared/smart_tickets.py` — scope-limited tool authorization |

#### SMART Permission Tickets Spec Compliance

Reference implementation of Josh Mandel's "SMART Permission Tickets" CI build draft (March 6, 2026). Feature-flagged via `MAMAGUARD_SMART_TICKETS=true` — disabled by default so existing flows are unaffected.

**Spec elements implemented:**

| Element | Status | Implementation |
|---------|--------|---------------|
| JWT-encoded ticket | Done | `decode_permission_ticket()` validates HS256/RS256 JWTs via PyJWT |
| Required claims: `sub`, `scope`, `exp` | Done | Enforced at decode time; missing claims raise `TicketError` |
| `sub` = patient ID | Done | Validated against `session.patient_id` at enforcement time |
| `scope` = SMART v2 scopes | Done | Space-delimited string parsed to set; `patient/<Resource>.<perms>` format |
| `exp` = expiration | Done | Checked at decode (JWT library) AND at enforcement (belt-and-suspenders for stale sessions) |
| `aud` = audience | Done | Optional; validated when `MAMAGUARD_SMART_TICKETS_AUDIENCE` is set |
| Scope enforcement per tool | Done | `TOOL_SCOPES` maps each of the 14 tools to required SMART scopes |
| Wildcard resource (`patient/*.rs`) | Done | `_scope_satisfies()` handles `*` resource and permission superset matching |
| Permission superset (`cruds` satisfies `rs`) | Done | Set-based permission letter matching |

**Data flow:**

1. Caller includes `permissionTicket` JWT in FHIR context metadata alongside `fhirUrl`, `fhirToken`, `patientId`.
2. `fhir_hook.extract_fhir_context()` decodes the ticket and stores it in `callback_context.state["smart_ticket"]`.
3. Each tool calls `_get_fhir_context(tool_context, tool_name)` which invokes `enforce_smart_ticket()`.
4. Enforcement checks: ticket present → patient match → not expired → scopes sufficient.
5. On any failure, tool returns a structured error dict; the FHIR call is never made.

**Tool → scope mapping (SMART v2 syntax):**

| Tool | Required Scopes |
|------|----------------|
| `get_patient_summary` | `patient/Patient.rs patient/Condition.rs patient/MedicationRequest.rs patient/Observation.rs` |
| `get_active_medications` | `patient/MedicationRequest.rs` |
| `get_bp_trend` | `patient/Observation.rs` |
| `get_glucose_trend` | `patient/Observation.rs` |
| `get_pregnancy_history` | `patient/Condition.rs` |
| `get_maternal_risk_profile` | `patient/Observation.rs patient/Condition.rs patient/MedicationRequest.rs` |
| `get_immunization_gaps` | `patient/Patient.rs patient/Immunization.rs` |
| `get_developmental_screening_status` | `patient/Patient.rs patient/Observation.rs` |
| `get_care_gaps` | `patient/CarePlan.rs patient/Goal.rs patient/Condition.rs` |
| `get_sdoh_screening` | `patient/Patient.rs patient/Condition.rs patient/Coverage.rs` |
| `find_sdoh_resources` | *(none — external API only)* |
| `write_risk_assessment` | `patient/RiskAssessment.c` |
| `create_communication_request` | `patient/CommunicationRequest.c` |
| `write_care_plan` | `patient/Goal.c patient/CarePlan.c` |

**Configuration:**

| Env Variable | Purpose | Default |
|-------------|---------|---------|
| `MAMAGUARD_SMART_TICKETS` | Enable ticket enforcement (`true`/`false`) | `false` |
| `MAMAGUARD_SMART_TICKETS_SECRET` | HS256 signing key for dev/test | *(empty)* |
| `MAMAGUARD_SMART_TICKETS_AUDIENCE` | Expected `aud` claim value | *(empty — skip audience check)* |

**Production path:** Replace HS256 with RS256 using a JWKS endpoint from the SMART authorization server. The `_ACCEPTED_ALGORITHMS` list already includes RS256; pass the public key to `decode_permission_ticket(signing_key=...)`.

**Test coverage:** 53 tests in `mamaguard/tests/test_smart_tickets.py` covering JWT decode (valid/expired/malformed/missing claims/audience), scope checking (exact/wildcard/superset/insufficient), tool scope mapping audit, enforcement pipeline, fhir_hook integration, and 3 end-to-end scenarios.

### 2.7 Prompt Opinion Integration

#### What Gets Published to Marketplace

**The BYO Agent is the marketplace-published artifact** — it is what judges discover, launch from the launchpad, and interact with directly. The external A2A agent on Cloud Run is backend infrastructure that the BYO Agent consults.

#### Registration Flow

1. Deploy external A2A agent to Cloud Run → get public HTTPS URL
2. PO → Agents → External Agents → Add Connection
3. Enter: `https://mamaguard-xxxxx.run.app/.well-known/agent-card.json`
4. PO fetches card, displays name/skills/security/FHIR extension
5. Acknowledge: "PO will send authenticated token as part of FHIR context"
6. **Create the BYO Agent** — this is the marketplace-facing submission:
   - Name: "MamaGuard: Maternal-Pediatric Care Coordinator"
   - Configure to consult the external MamaGuard A2A agent
   - Publish to Marketplace
7. Verify: BYO Agent appears on launchpad, is directly invokable by any user

#### BYO Agent Configuration (the Marketplace submission)

- **Scope:** Patient (agent works with patient-specific data)
- **Model:** Gemini 2.5 Flash (free via Google AI Studio)
- **System prompt:** Instructs the BYO Agent to consult MamaGuard for all maternal-pediatric queries; formats responses using the 5T framework
- **Consultation:** Configured to consult the external MamaGuard A2A agent
- **FHIR context:** Enabled (PO sends FHIR headers through to external agent)
- **Response format:** Structured via 5T framework (Talk/Template/Table/Task/Transaction)
- **Marketplace visibility:** Published and discoverable on launchpad

#### Platform Constraints

- External agents accessed ONLY via "Consult" from BYO agent — not from launchpad
- Current A2A version: v0.3 (metadata in `message.metadata`)
- BYO agents can attach MCP servers directly
- Guardrails: pre-prompt validation agents available

### 2.8 Standalone MCP Server (Phase 2a)

The MCP server is MamaGuard's **second submission artifact** — covering the Superpower track alongside the A2A Agent track. It exposes all 14 FHIR tools via the Model Context Protocol using [FastMCP](https://github.com/jlowin/fastmcp).

#### Key Design

- **Single source of truth:** `mamaguard/mcp_server/server.py` imports tool functions directly from `mamaguard/shared/tools/*` — zero copy-paste.
- **SHARP via explicit parameters:** Instead of relying on middleware/session state, each tool accepts `fhir_url`, `fhir_token`, `patient_id` as the first three parameters.
- **Dual transport:** stdio (for Claude Desktop, Cursor) and SSE (for remote/web clients).
- **FhirContext adapter:** `mamaguard/mcp_server/context.py` wraps explicit params into the `.state` dict expected by shared tool implementations.

#### Running

```bash
# stdio (Claude Desktop, Cursor, etc.)
python -m mamaguard.mcp_server.server

# SSE (remote clients, PO BYO Agent attachment)
MCP_TRANSPORT=sse MCP_PORT=8080 python -m mamaguard.mcp_server.server
```

#### Tool Coverage

All 14 tools from the ADK agents are registered: 2 base + 4 maternal + 3 pediatric + 2 SDOH + 3 write-back. Each tool returns JSON-serialized results including the `clinician_review` Liaison Agent object.

#### Marketplace Publishing

Two paths for the Prompt Opinion Marketplace:

1. **Attach to BYO Agent:** PO BYO Agents can attach MCP servers directly. Deploy the MCP server with SSE transport and add the SSE endpoint URL in the BYO Agent config.
2. **Standalone artifact:** Create a dedicated BYO Agent wrapper that uses the attached MCP tools for all FHIR queries.

Configuration files: `marketplace/mcp_config.json` (server metadata), `marketplace/mcp_setup.md` (step-by-step setup).

#### Client Configuration Examples

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "mamaguard": {
      "command": "python",
      "args": ["-m", "mamaguard.mcp_server.server"],
      "cwd": "/path/to/repo/mamaguard"
    }
  }
}
```

**Cursor:**
```json
{
  "mamaguard": {
    "command": "python",
    "args": ["-m", "mamaguard.mcp_server.server"],
    "cwd": "/path/to/repo/mamaguard"
  }
}
```

#### Test Coverage

16 test classes in `mamaguard/tests/test_mcp_server.py`: tool registration (all 14 registered, no extras), tool invocation with mocked FHIR, FhirContext construction + SHARP deserialization, and error propagation.

---

## 3. Project Structure

```
mamaguard/
├── orchestrator/
│   └── agent.py                 # Orchestrator: routes to sub-agents via AgentTool
├── maternal_agent/
│   └── agent.py                 # Maternal Risk Monitor agent definition
├── pediatric_agent/
│   └── agent.py                 # Pediatric Transition Agent definition
├── sdoh_agent/
│   └── agent.py                 # SDOH + Outreach Agent definition
├── mcp_server/                    # Standalone MCP server (Superpower track — Phase 2a)
│   ├── __init__.py               # Package stub
│   ├── server.py                 # FastMCP server: 14 tools, stdio + SSE transports
│   ├── context.py                # FhirContext adapter (SHARP params → .state dict)
│   └── README.md                  # MCP server docs: quick start, tool reference, Docker
├── shared/
│   ├── app_factory.py           # [REUSE] create_a2a_app() — AgentCard + ASGI app
│   ├── middleware.py             # [REUSE] X-API-Key enforcement + FHIR metadata bridging
│   ├── fhir_hook.py             # [REUSE] before_model_callback — FHIR cred extraction
│   ├── smart_tickets.py         # SMART Permission Tickets (Phase 2b)
│   ├── sdoh_resources.py        # Offline SDOH resource map (Phase 2c)
│   ├── logging_utils.py         # [REUSE] ANSI-colour logger
│   └── tools/
│       ├── __init__.py           # Re-exports all tools
│       ├── fhir_base.py          # get_patient_summary, get_active_medications
│       ├── maternal.py           # get_maternal_risk_profile, get_bp_trend,
│       │                         #   get_glucose_trend, get_pregnancy_history
│       ├── pediatric.py          # get_immunization_gaps,
│       │                         #   get_developmental_screening_status, get_care_gaps
│       ├── sdoh.py               # get_sdoh_screening, find_sdoh_resources
│       └── writeback.py          # write_risk_assessment, create_communication_request,
│                                 #   write_care_plan
├── marketplace/                   # Source-controlled marketplace configs (both tracks)
│   ├── byo_system_prompt.md      # BYO Agent system prompt (copy-paste into PO)
│   ├── byo_consultation_prompt.md # Consultation prompt for A2A handoff
│   ├── byo_config.json           # BYO Agent settings: scope, model, FHIR toggle
│   ├── mcp_config.json           # MCP server metadata: tools, SHARP fields, env vars
│   ├── mcp_setup.md              # Step-by-step MCP server marketplace setup
│   ├── README.md                  # Step-by-step BYO Agent marketplace setup
│   ├── demo_script.md            # Pre-demo checklist + 7-scene video breakdown
│   └── devpost_description.md    # Devpost submission copy
├── app.py                        # A2A entry point (agent card, skills, FHIR extension)
├── Dockerfile                    # Single image, AGENT_MODULE env selects agent
├── docker-compose.yml            # Multi-agent local dev
├── Procfile                      # honcho start — all agents locally
├── requirements.txt              # Dependencies (pinned)
├── .env.example                  # GOOGLE_API_KEY, MAMAGUARD_API_KEY
└── tests/
    ├── test_fhir_tools.py        # Unit tests for FHIR base tool functions
    ├── test_maternal.py           # Maternal tool tests with mock FHIR data
    ├── test_pediatric.py          # Pediatric tool tests
    ├── test_sdoh.py               # SDOH screening tool tests
    ├── test_writeback.py          # RiskAssessment + CommunicationRequest write tests
    ├── test_integration.sh        # curl-based end-to-end A2A integration tests
    └── test_marketplace.sh        # Verify agent card, BYO consult flow, skill invocation
```

### BYO Agent Config Bundle (`marketplace/`)

The BYO Agent configured inside Prompt Opinion is the actual submission artifact — what judges discover and launch. Because PO's BYO Agent configuration is done through the web UI (not deployable code), we source-control the configuration as copyable files:

**`marketplace/byo_system_prompt.md`** — The system prompt pasted into the BYO Agent config. Instructs the agent to:
- Greet the clinician and identify the patient in context
- Consult the external MamaGuard A2A agent for all maternal-pediatric queries
- Format responses using the 5T framework
- Display Liaison Agent notices when clinician review is needed
- Include disclaimers on AI-generated content

**`marketplace/byo_consultation_prompt.md`** — The consultation prompt that triggers the A2A handoff to the external MamaGuard agent.

**`marketplace/byo_config.json`** — Structured record of all BYO Agent settings:
```json
{
  "name": "MamaGuard: Maternal-Pediatric Care Coordinator",
  "scope": "patient",
  "model": "gemini-2.5-flash",
  "fhir_context_enabled": true,
  "external_agent_url": "https://mamaguard-xxxxx.run.app",
  "guardrails": [],
  "response_format": "5T"
}
```

**`marketplace/README.md`** — Reproduction steps: how to create the BYO Agent in PO from these files.

This ensures any team member can reproduce the exact marketplace listing, and the submission surface is version-controlled alongside the backend.

### File Responsibilities

#### Entry Point: `app.py`
- Imports orchestrator agent
- Calls `create_a2a_app()` with AgentCard (name, skills, security, FHIR extension)
- Serves on port 8001
- Serves `/.well-known/agent-card.json` (always public, no auth)

#### Orchestrator: `orchestrator/agent.py`
```python
from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from maternal_agent.agent import maternal_risk_agent
from pediatric_agent.agent import pediatric_transition_agent
from sdoh_agent.agent import sdoh_outreach_agent
from shared.fhir_hook import extract_fhir_context

root_agent = Agent(
    name="mamaguard_orchestrator",
    model="gemini-2.5-flash",
    instruction="...",  # Route: maternal → pediatric → SDOH → synthesize
    tools=[
        AgentTool(agent=maternal_risk_agent),
        AgentTool(agent=pediatric_transition_agent),
        AgentTool(agent=sdoh_outreach_agent),
    ],
    before_model_callback=extract_fhir_context,
)
```

#### Sub-Agent Pattern: `maternal_agent/agent.py`
```python
from google.adk.agents import Agent
from shared.fhir_hook import extract_fhir_context
from shared.tools import (
    get_maternal_risk_profile, get_bp_trend,
    get_glucose_trend, get_pregnancy_history,
    get_active_medications, write_risk_assessment,
)

maternal_risk_agent = Agent(
    name="maternal_risk_agent",
    model="gemini-2.5-flash",
    description="Maternal health risk assessment specialist",
    instruction="...",
    tools=[get_maternal_risk_profile, get_bp_trend, ...],
    before_model_callback=extract_fhir_context,
)
```

#### Tool Pattern: `shared/tools/maternal.py`
```python
import httpx
from google.adk.agents import ToolContext

async def get_bp_trend(patient_id: str, months_back: int = 24,
                       tool_context: ToolContext = None) -> dict:
    """Get blood pressure trend for maternal monitoring."""
    fhir_url = tool_context.state["fhir_url"]
    fhir_token = tool_context.state["fhir_token"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{fhir_url}/Observation",
            params={"patient": patient_id, "code": "http://loinc.org|55284-4",
                    "_sort": "-date", "_count": "20", "_format": "json"},
            headers={"Authorization": f"Bearer {fhir_token}"},
        )
        bundle = resp.json()
        # Parse observations, compute trend, build response
        readings = [...]
        return {
            "data": {"readings": readings, "trend": "...", "alert": True},
            "clinician_review": {
                "required": any(r["systolic"] > 140 for r in readings),
                "reason": "...", "recommendation": "...",
                "evidence_basis": [...], "confidence": 0.85,
            },
        }
```

---

## 4. Tech Stack

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Language** | Python | 3.11+ | po-adk-python reference; Tier 1 MCP SDK; fastest prototyping |
| **A2A Framework** | Google ADK | >= 1.25.0 | Reference implementation stack; AgentTool for sub-agents |
| **A2A SDK** | a2a-sdk | >= 0.3.0 | Required for A2A protocol compliance |
| **LLM** | Gemini 2.5 Flash | (Google AI Studio, free) | Free tier sufficient; Google judge; po-adk-python default |
| **HTTP Client** | httpx | >= 0.28.0 | Async, used in reference; FHIR REST calls |
| **Web Server** | uvicorn | >= 0.41.0 | ASGI, reference pattern |
| **Config** | python-dotenv | >= 1.0.0 | Env var management |
| **FHIR Server** | SMART R4 | r4.smarthealthit.org | 260 pregnancies, 7,455 immunizations, 1,611 CommunicationRequests |
| **FHIR Backup** | HAPI R4 | hapi.fhir.org/baseR4 | Full CRUD (for write-back testing); no auth |
| **Deployment** | Google Cloud Run | — | Free tier; `gcloud run deploy --source .`; proven pattern |
| **Container** | Docker | — | Single image, `AGENT_MODULE` env selects agent |
| **Local Dev** | honcho (Procfile) | — | Runs all agents simultaneously |

### `requirements.txt`

```
google-adk>=1.25.0
a2a-sdk[http-server]>=0.3.0
httpx>=0.28.0
python-dotenv>=1.0.0
uvicorn>=0.41.0
mcp[server]>=1.0.0
PyJWT>=2.8.0
```

---

## 5. FHIR Data Strategy

### Primary Server: SMART R4 (`r4.smarthealthit.org`)

| Resource | Count | Usage |
|----------|-------|-------|
| Observation | 104,825 | BP trends, glucose, HbA1c, developmental screenings |
| ExplanationOfBenefit | 26,926 | Cost analysis (future enhancement) |
| Immunization | 7,455 | Pediatric immunization gap detection |
| CarePlan | 1,812 | Active care plans, antenatal plans |
| CommunicationRequest | 1,611 | Outreach tracking |
| Goal | 1,192 | Health milestones (HbA1c, BP targets) |
| Patient | 639 | Demographics (richer per-patient data) |
| Condition | — | Diagnoses (pregnancy, comorbidities, SDOH Z-codes) |
| Coverage | 227 | Insurance status (Medicaid gaps) |

### Demo Patient: "Maria" (Patient/881f534f-d041-425d-a542-cbf669f43e18)

- **Age:** 50, Black, French-speaking
- **Chronic:** DM2, HTN (never controlled, always >140/90), metabolic syndrome, diabetic neuropathy, anemia
- **Obstetric:** 6 pregnancies — 5 losses (blighted ovum, fetal complications), 1 live birth via emergency delivery
- **Postpartum:** BP spiked to 170/98. Only ONE postnatal visit. No insurance on record.
- **Medications:** Hydrochlorothiazide 25mg (since 2003), Metformin ER 500mg (since 2006)
- **22 conditions, 148 observations, 42 encounters, 9 immunizations**

### Critical FHIR Gotcha

**Synthea uses SNOMED codes, NOT ICD-10.** Query with:
```
code=http://snomed.info/sct|72892002  (normal pregnancy)
code=http://snomed.info/sct|398254007 (preeclampsia)
```
NOT `code=O24` or `code=O14`. Most teams will get this wrong.

### Key LOINC Codes

| Measurement | LOINC | Usage |
|------------|-------|-------|
| Blood pressure panel | 55284-4 | Maternal BP monitoring |
| Glucose | 2339-0 | Gestational diabetes monitoring |
| HbA1c | 4548-4 | Long-term glucose control |

### Efficient Query Pattern

Use `_revinclude` for compound patient queries:
```
GET /Patient?_id={id}&_revinclude=Condition:patient&_revinclude=MedicationRequest:patient&_revinclude=Observation:patient
```
Returns patient + ALL linked resources in one call.

---

## 6. Implementation Plan

**34 days available: April 7 → May 11, 2026**

### Phase 1: Foundation (Days 1-3)

| Task | Details | Status |
|------|---------|--------|
| Fork po-adk-python | Clone, strip example agents, set up project structure | [x] |
| Set up shared/ layer | Reuse app_factory, middleware, fhir_hook, logging_utils | [x] |
| Implement fhir_base.py | Reuse/adapt get_patient_summary, get_active_medications | [x] |
| Deploy skeleton to Cloud Run | Dockerfile, Procfile, `scripts/deploy.sh` ready; awaiting `gcloud run deploy` | [~] |
| Register in Prompt Opinion | Add Connection with agent card URL, verify discovery | [ ] |
| Create BYO Agent in PO | Write system prompt (`marketplace/byo_system_prompt.md`), configure consultation, publish to Marketplace | [~] |
| Write marketplace config bundle | `byo_config.json`, `byo_consultation_prompt.md`, `marketplace/README.md` — commit to repo | [x] |
| Verify BYO Agent launchable | Confirm judges can find and launch from PO launchpad | [ ] |
| Test FHIR context flow | End-to-end: PO BYO Agent → consult → external agent → FHIR server → response | [ ] |
| Probe Synthea mother-child links | Informational only — two-invocation handoff tested cold with 16 deterministic tests | [x] |

### Phase 2: Maternal Agent (Days 4-7)

| Task | Details | Status |
|------|---------|--------|
| Build `get_maternal_risk_profile` | Compound query: conditions + obs + meds + encounters | [x] |
| Build `get_bp_trend` | LOINC 55284-4, date-sorted, alert threshold | [x] |
| Build `get_glucose_trend` | LOINC 2339-0 + 4548-4, trend computation | [x] |
| Build `get_pregnancy_history` | SNOMED pregnancy codes, outcome classification | [x] |
| Implement Liaison pattern | `clinician_review` response structure in all tools | [x] |
| Build `write_risk_assessment` | POST RiskAssessment to FHIR server | [x] |
| Write maternal_risk_agent | Instruction, tool wiring, test with Maria's data | [x] |
| Test maternal flow end-to-end | 84 maternal tool tests + 16 handoff cold tests + 10 Tier-1 benchmarks | [x] |

### Phase 3: Pediatric + SDOH Agents (Days 8-12)

| Task | Details | Status |
|------|---------|--------|
| Build `get_immunization_gaps` | CDC schedule logic vs Immunization resources | [x] |
| Build `get_developmental_screening_status` | AAP Bright Futures milestone checks | [x] |
| Build `get_care_gaps` | Cross-reference CarePlan + Goal + Encounter + Observation | [x] |
| Build `get_sdoh_screening` | Z-code conditions, QuestionnaireResponse, Coverage | [x] |
| Build `create_communication_request` | POST CommunicationRequest (outreach tracking) | [x] |
| Write pediatric_transition_agent | Instruction, tool wiring | [x] |
| Write sdoh_outreach_agent | Instruction, tool wiring, + `find_sdoh_resources` + `write_care_plan` | [x] |
| Implement orchestrator routing | AgentTool wiring, sequential delegation, synthesis | [x] |
| Test full 3-agent flow | 28 in-process agent tests + 8 orchestration benchmarks + 54/54 Tier-1 | [x] |

### Phase 4: Integration + Polish (Days 13-17)

| Task | Details | Status |
|------|---------|--------|
| End-to-end testing in PO | Full flow with Maria in Prompt Opinion UI | [ ] |
| Write integration tests | 770 unit tests, 54/54 Tier-1 benchmarks at 100.0%, mypy clean | [x] |
| Handle edge cases | Missing data, FHIR errors, timeout handling — error-path tests for all tools | [x] |
| Optimize agent instructions | Liaison pattern enforced on all 3 sub-agents, 5T alignment | [x] |
| Deploy final to Cloud Run | Dockerfile + Procfile + `scripts/deploy.sh` ready; awaiting deploy | [~] |
| Write Devpost description | `marketplace/devpost_description.md` committed | [x] |

### Phase 5: Demo + Submission (Days 18-20)

| Task | Details | Status |
|------|---------|--------|
| Script demo video | `marketplace/demo_script.md` committed | [x] |
| Record demo (OBS Studio) | 1080p, multiple takes, pre-copy all inputs | [ ] |
| Upload to YouTube | **Public** (required by rules), "Not for Kids" | [ ] |
| Finalize Devpost submission | Title, description, video, marketplace URL, team | [ ] |
| Final PO marketplace check | Verify functional, all skills visible | [ ] |
| Submit before deadline | May 11, 2026 @ 11:00 PM EDT | [ ] |

### Buffer: 14 days for unexpected issues

### Scope-Consistent Fallback (if time-constrained)

**Critical rule: the agent card, demo, and marketplace listing must match actual functionality.** If the build slips, do NOT ship a 4-skill agent card with 2 stubs. Instead:

**Option A (preferred): Ship all 3 agents with reduced depth.**
- All 4 skills functional but with simpler tool implementations (e.g., `get_immunization_gaps` returns a basic schedule comparison rather than full CDC logic)
- Agent card and demo remain consistent with actual behavior
- Demo shows all 3 agents working, each producing real output

**Option B (last resort): Shrink the agent card to maternal-only.**
- Agent card declares 2 skills: `maternal-risk-assessment` and `comprehensive-care-plan`
- Remove pediatric and SDOH skills from agent card entirely
- Demo script shortened to show only maternal flow
- Devpost description mentions pediatric + SDOH as future roadmap, not current capability
- BYO Agent system prompt updated to match reduced scope

---

## 7. Demo Strategy

### 3-Minute Video Arc

| Time | Section | Screen | Voiceover |
|------|---------|--------|-----------|
| 0:00-0:05 | Hook | "80% of pregnancy-related deaths are preventable." — CDC | (silence) |
| 0:05-0:10 | Hook | "40% of new mothers never return for postpartum care." | (silence) |
| 0:10-0:15 | Hook | "Black mothers die at 3x the rate. Most after discharge." | "These aren't just statistics." |
| 0:15-0:25 | Patient | Maria's summary card (designed, not raw JSON) | Introduce Maria — 5 losses, emergency delivery, no insurance |
| 0:25-0:45 | Problem | Split-screen: fragmented care vs gaps | Postpartum BP spike, missed vaccines, insurance expiring |
| 0:45-1:05 | Solution | Architecture diagram (3 agents + FHIR tools + A2A) | MamaGuard overview, Liaison Agent principle |
| 1:05-1:15 | Demo | PO UI — selecting MamaGuard, patient loaded | "Let's see it in action" |
| 1:15-1:35 | Maternal | Agent output — risk score, BP trend, clinician review flag | BP never controlled, Liaison pause for OB review |
| 1:35-1:55 | Pediatric | Immunization schedule, developmental timeline | CDC schedule, tasks with due dates |
| 1:55-2:15 | SDOH | Insurance gap, community resources, CommunicationRequest | Medicaid expiration, WIC/SNAP referrals |
| 2:15-2:30 | Summary | Consolidated care plan (URGENT/HIGH/MODERATE/ROUTINE) | Unified priorities, all auditable |
| 2:30-2:50 | Impact | Statistics with MamaGuard logo | 700+ deaths/year, 80% preventable, coordination gap |
| 2:50-3:00 | Close | Team, tech stack, GitHub | "Every mother deserves coordinated care." |

### Technical Depth Moments (flash on screen)

| Timestamp | Content | Duration | Judge Target |
|-----------|---------|----------|-------------|
| 0:50 | Architecture diagram | 5s | Parth Tripathi (A2A) |
| 1:20 | FHIR JSON snippet (BP with LOINC) | 3s | Josh Mandel (FHIR) |
| 1:40 | `clinician_review.required: true` | 3s | Mandel (Liaison pattern) |
| 2:10 | CommunicationRequest write-back | 3s | Bidirectional FHIR |
| 2:25 | Agent Card JSON with FHIR extension | 3s | A2A compliance |

---

## 8. Submission Checklist

### Stage 1: Technical Qualification (PASS/FAIL)

- [ ] **BYO Agent published to Prompt Opinion Marketplace** — directly launchable by judges
- [ ] External A2A agent deployed with valid agent card at `/.well-known/agent-card.json`
- [ ] BYO Agent configured to consult external agent, end-to-end flow verified
- [ ] Discoverable and directly invokable from PO launchpad (not requiring manual "Add Connection")
- [ ] Synthetic data only (SMART R4 sandbox)

### Devpost Submission

- [ ] **Title:** "MamaGuard: AI-Powered Maternal-Pediatric Care Coordination"
- [ ] **Description:** Features, architecture, impact hypothesis, tech stack
- [ ] **Demo video:** YouTube link, **public** (rules require publicly visible), < 3 minutes
- [ ] **Marketplace URL:** Link to MamaGuard on Prompt Opinion
- [ ] **Built with:** Python, Google ADK, A2A, FHIR R4, Gemini 2.5 Flash, Prompt Opinion
- [ ] **Team members:** All registered on Devpost + hackathon + PO

### Technical Deliverables

- [ ] Agent deployed to public HTTPS URL (Cloud Run)
- [x] Agent card served correctly (verified via `test_app_factory.py` — 41 tests)
- [x] A2A FHIR context handling working (SHARP header patterns via ADK tools — 66 fhir_hook tests)
- [x] 14 FHIR tools functional (ADK in-process + MCP server — 770 unit tests)
- [x] 4 A2A skills working (orchestrator + 3 sub-agents — 28 in-process agent tests)
- [x] Liaison Agent pattern demonstrated (INPUT_REQUIRED — all 3 sub-agents enforce)
- [x] FHIR write-back (RiskAssessment + CommunicationRequest + Goal/CarePlan — error-path tests)
- [x] X-API-Key authentication (24 middleware tests, timing-safe comparison)
- [x] Error handling for missing FHIR context (all tools return structured error)
- [~] MCP server published (Superpower track — code + marketplace config ready, awaiting PO publish)
- [x] SMART Permission Tickets (feature-flagged — 53 tests)

### Demo Video

- [ ] Under 3 minutes
- [ ] Shows MamaGuard working in Prompt Opinion (launched from Marketplace)
- [ ] Scripted voiceover
- [ ] 1080p minimum
- [ ] YouTube upload — **Public** (rules require publicly visible; unlisted may fail qualification)
- [ ] Addresses AI Factor (compound reasoning, not just thresholds) + Impact (measurable metrics) + Feasibility

---

## 9. Risk Register

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Synthea doesn't link mother-child records | HIGH | Med | Two-invocation workflow: maternal session → handoff summary → pediatric session with separate patient. Demo shows both sequentially. If RelatedPerson links found during impl, use them instead. See Section 2.5 "Mother-to-Child Handoff Mechanism." |
| SMART FHIR server down during demo | LOW | Critical | Pre-record video. Never live demo. HAPI as backup. |
| Prompt Opinion undocumented limitations | Med | High | Register agent in PO within first 3 days. Join PO Discord. |
| Another team submits maternal health project | LOW | Med | Zero visible competitors as of April 7. Differentiators hard to copy. |
| Gemini hallucinates clinical recommendations | Med | High | Validate against FHIR data. Liaison Agent catches errors. Disclaimers. |
| Demo breaks during recording | Med | Med | Multiple takes. Pre-copy inputs. Backup simpler query. |
| Cloud Run cold start too slow | Med | Low | `--min-instances 1`. Pre-warm before recording. |
| FHIR write-back fails on SMART sandbox | Med | Med | Fallback to HAPI (full CRUD). Or mock write for demo. |
| Time runs out | Med | High | **Option A:** Ship all 3 agents with simpler tools. **Option B:** Shrink agent card to maternal-only (remove unbuilt skills entirely). Never ship stubs that don't match the agent card. |

---

## Appendix A: FHIR Query Templates

```bash
BASE="https://r4.smarthealthit.org"
PID="881f534f-d041-425d-a542-cbf669f43e18"

# Patient demographics
curl "$BASE/Patient/$PID?_format=json"

# All conditions
curl "$BASE/Condition?patient=$PID&_count=100&_format=json"

# Pregnancy conditions (SNOMED!)
curl "$BASE/Condition?patient=$PID&code=http://snomed.info/sct|72892002&_format=json"

# Blood pressure trend
curl "$BASE/Observation?patient=$PID&code=http://loinc.org|55284-4&_sort=-date&_format=json"

# HbA1c trend
curl "$BASE/Observation?patient=$PID&code=http://loinc.org|4548-4&_sort=-date&_format=json"

# Active medications
curl "$BASE/MedicationRequest?patient=$PID&status=active&_format=json"

# Immunizations
curl "$BASE/Immunization?patient=$PID&_count=50&_format=json"

# Compound query (all linked resources in one call)
curl "$BASE/Patient?_id=$PID&_revinclude=Condition:patient&_revinclude=MedicationRequest:patient&_revinclude=Observation:patient&_format=json"
```

## Appendix B: Key FHIR Resource IDs (Maria)

```
Patient:           881f534f-d041-425d-a542-cbf669f43e18
Diabetes:          abc9ea4f-6eb2-44b6-8f02-e16cb056b5ca
Hypertension:      07c4fa62-b6c4-44c0-9443-6f6e59dc47cb
Diabetic Neuro:    70758a4d-cacc-4206-9621-571dd6de6528
Pregnancy (last):  9f80e77a-1580-480f-a4e5-48ec05ca4354
Miscarriage:       c38df46a-5d39-4920-9664-38c9044454c4
Metformin:         f6255a19-d66f-41df-a70f-42a68ae2b36f
HCTZ:              91a9e5d7-4e57-4879-9340-611acb049f8f
Diabetes CarePlan: a1137ae0-3235-435b-9940-9616f913caa0
Antenatal CarePlan:d0461449-a0e3-4ee4-b212-98ee63c0f050
OB Emergency Enc:  ac1b3f76-e5a2-42cd-8901-918172c7b74a
HbA1c Goal:        b90493f4-7ea8-4aaa-903a-e27edee13557
BP Goal:           dc5d7f64-ff98-400e-8651-7d265503d049
```

## Appendix C: Competitive Positioning

### Unique Differentiators

1. **6-for-6 judge alignment** — maternal (Zheng) + pediatric (Proctor) + FHIR (Mandel) + ops (Hickey) + safety (Mathur) + A2A (Tripathi)
2. **Liaison Agent pattern** — Mandel's own innovation, implemented in code
3. **Bidirectional FHIR** — writes RiskAssessment + CommunicationRequest back (most only read)
4. **Mother-child linked care** — unique clinical workflow no competitor has
5. **Real FHIR data** — SMART R4 Synthea records, not mock data
6. **SDOH + Gravity Project** — CMS 2026 mandate alignment
7. **Emotionally compelling demo patient** — Maria's story (5 losses, emergency delivery, no insurance)

### Confirmed Crowded (AVOID)

- Prior Authorization (3+ projects)
- Medication Reconciliation (MedRecon exists)
- Generic CDS (2+ projects)

### Confirmed Open (WE OWN)

- Maternal health: ZERO competitors
- Pediatric workflows: ZERO competitors
- SDOH screening: ZERO competitors
- Care coordination: ZERO competitors
