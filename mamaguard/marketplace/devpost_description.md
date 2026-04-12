# MamaGuard: Maternal-Pediatric Care Coordinator

## What it does

MamaGuard is a multi-agent AI care coordination system that analyzes FHIR patient records to support maternal and pediatric health. It coordinates three specialist agents through a single A2A interface:

- **Maternal Risk Monitor** — Analyzes BP trends, glucose control, pregnancy history, and postpartum complications. Flags hypertensive crisis (>160/110 mmHg), uncontrolled diabetes (HbA1c >6.5%), and recurrent pregnancy loss.

- **Pediatric Transition Agent** — Tracks immunization schedules against CDC recommendations, monitors developmental milestones per AAP Bright Futures, and identifies care gaps.

- **SDOH & Outreach Agent** — Screens for insurance coverage gaps, language barriers, food insecurity, and housing instability. Looks up concrete community resources (findhelp.org / 211 directory with curated national fallback), writes FHIR Goal + CarePlan pairs so the care team has trackable interventions, and generates CommunicationRequest resources for outreach.

## How it works

MamaGuard ships two interoperable artifacts — an **A2A agent** (BYO Agent on Prompt Opinion) and a **standalone MCP server** — both backed by the same 15 FHIR tools on Google Cloud Run.

**A2A Agent path (primary):**
1. Clinician launches MamaGuard from the PO launchpad and selects a patient
2. PO sends FHIR context (server URL, bearer token, patient ID) via A2A metadata
3. The orchestrator routes to specialist sub-agents based on the query
4. Each agent queries the FHIR server using 15 specialized tools
5. All output follows the **5T framework** (Talk, Template, Table, Task, Transaction) for structured clinical reporting
6. Results include structured risk assessments with the **Liaison Agent pattern** — AI recommends, clinician decides
7. When clinician review is needed, the agent pauses (INPUT_REQUIRED state)
8. Write-back tools create RiskAssessment, CommunicationRequest, Goal, and CarePlan resources on the FHIR server
9. Every tool invocation emits a **FHIR AuditEvent** for HIPAA compliance trail (feature-flagged)

**Mother-to-child handoff:**
The orchestrator calls `find_linked_newborn` to discover children linked to a maternal patient via FHIR RelatedPerson resources. This enables seamless single-session maternal-to-pediatric transitions — the agent automatically finds the linked child, carries maternal risk factors (GDM, preeclampsia, preterm delivery) into the pediatric context, and routes to the pediatric agent without requiring the clinician to manually switch patients.

**MCP Server path (dual submission):**
Any MCP-compatible client (Claude Desktop, Cursor, other PO agents) can connect to MamaGuard's MCP server and invoke the same 15 FHIR tools directly. SHARP context is accepted via MCP client metadata, maintaining the same credential isolation model.

## Why it matters — Impact Hypothesis

| Metric | Current Baseline | Target with MamaGuard |
|--------|-----------------|----------------------|
| Postpartum follow-up completion | 60% attend (40% never return) | 85%+ via proactive gap detection |
| Postpartum hypertensive crisis detection | Median 5 days to detect | Same-day flagging via automated BP trend analysis |
| Childhood immunization adherence | 70.4% full series on time | 90%+ via automated gap detection |
| Clinician chart-review time | 15-20 min manual review | <2 min AI-synthesized risk summary |
| SDOH screening completion | <25% of eligible patients | 80%+ via automated Z-code + Coverage analysis |

**Cost impact:** Preventable maternal morbidity costs $32.3B/year in the US. Each avoided severe maternal morbidity event saves ~$115K in acute care costs.

## Where GenAI goes beyond rules

MamaGuard's AI factor is **compound clinical reasoning across heterogeneous data**:

1. **Cross-resource synthesis** — A rule engine flags BP >140/90. MamaGuard looks at 6 pregnancies with 5 losses, uncontrolled HTN across 8 years, concurrent diabetes, and one postpartum visit — then explains *why this combination* is dangerous.

2. **Contextual medication safety** — HCTZ is acceptable for HTN, but in a postpartum patient with diabetes who may be breastfeeding, the recommendation shifts to labetalol. This requires patient-specific clinical context.

3. **SDOH-clinical integration** — Connecting a Medicaid gap + French language preference + food insecurity + postpartum BP crisis into a unified outreach plan with culturally appropriate referrals. The agent finds concrete community resources (211, WIC, SNAP, housing programs) and writes trackable FHIR CarePlan + Goal pairs.

4. **Natural language care plans** — Converting structured FHIR data into prioritized, evidence-cited care summaries using the 5T framework (Talk, Template, Table, Task, Transaction).

5. **Compound clinical reasoning** — Demonstrated with side-by-side benchmarks: a rule engine produces 5 flat flags; MamaGuard synthesizes URGENT compound risk across BP + HbA1c + pregnancy loss + housing + Medicaid gap, citing 7 FHIR evidence refs and 5 cross-factor clinical-SDOH interactions the rule engine cannot produce.

## Technical Architecture

```
Prompt Opinion ──┬── BYO Agent → A2A JSON-RPC ─┐
                 └── MCP Client → MCP Server ──┤
                                               ▼
                                    MamaGuard (Cloud Run)
                                    ├── Orchestrator (gemini-2.5-flash)
                                    │   ├── find_linked_newborn (mother→child)
                                    │   ├── Maternal Risk Monitor (7 tools)
                                    │   ├── Pediatric Transition Agent (5 tools)
                                    │   └── SDOH & Outreach Agent (6 tools)
                                    └── Shared FHIR Tool Layer (15 tools)
                                        ├── FHIR R4 Server (SMART/HAPI)
                                        └── External SDOH directory (findhelp.org / 211)
```

**Key technologies:**
- Google ADK + A2A SDK (agent framework)
- MCP (Model Context Protocol — standalone tool server, dual submission path)
- FHIR R4 (healthcare data standard)
- SHARP extension (FHIR context in A2A metadata + MCP client metadata)
- SMART Permission Tickets (Josh Mandel March 2026 draft — JWT-based scope enforcement)
- Liaison Agent pattern (human-in-the-loop for clinical decisions)
- 5T structured output (Talk, Template, Table, Task, Transaction)
- Bidirectional FHIR (reads patient data AND writes RiskAssessment, CommunicationRequest, Goal, CarePlan)
- FHIR AuditEvent generation (HIPAA compliance trail, feature-flagged)

## Built With

- Python 3.11
- Google ADK (google-adk >= 1.25.0)
- A2A SDK (a2a-sdk >= 0.3.0)
- MCP SDK (mcp[server] >= 1.0.0)
- PyJWT (SMART Permission Tickets)
- Gemini 2.5 Flash
- FHIR R4 (SMART sandbox + HAPI)
- Google Cloud Run
- Prompt Opinion Platform
- Docker
- httpx
- uvicorn

## Safety and Evaluation

MamaGuard includes a 3-tier benchmark suite with 879 unit tests and 57 deterministic Tier-1 benchmarks (100% pass rate):

- **Liaison pattern** — Every FHIR-reading tool returns a `clinician_review` object. All URGENT findings pause the agent (INPUT_REQUIRED) for clinician approval. AI never prescribes treatments, names drugs, or provides dosages.
- **No fabrication** — Every numeric value in the output must originate from a tool result. Reference-only thresholds in the agent prompt are labeled as such and may not be cited as patient data.
- **FHIR AuditEvent** — When enabled, every tool invocation emits a FHIR R4 AuditEvent recording what data was accessed, by which agent, with what outcome (HIPAA compliance trail).
- **AI Factor benchmark** — Side-by-side comparison of a naive LLM (no tools, no agents) vs. MamaGuard on identical patient data scored by an independent judge. Result: **+30% average score lift**, with the largest gain in safety (+37%) from the liaison pattern.
- **Equity evaluation** — Benchmark cases include Fatima (Arabic, uninsured), Priya (Hindi, GDM), Maria (French, SDOH), and James (insured) to test for language-barrier handling and insurance disparity detection.

## Demo

The demo shows Maria (Patient/881f534f), a 50-year-old Black, French-speaking woman with:
- 6 pregnancies (5 losses), emergency delivery
- Uncontrolled HTN (BP consistently >140/90, spike to 170/98 postpartum)
- DM2 with HbA1c trending 6.8 → 7.4 → 7.9 (diabetes range, worsening)
- Only ONE postnatal visit, no insurance on record
- Linked newborn: Lucas (Patient/bench-baby-santos-001)

MamaGuard identifies: URGENT risk (Stage 2 HTN + recurrent pregnancy loss + no coverage), generates a prioritized care plan with 5T structured output, flags clinician review, creates outreach resources, and discovers the linked newborn for seamless pediatric handoff.
