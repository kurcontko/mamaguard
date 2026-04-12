# MamaGuard Demo Script (< 3 minutes)

## Pre-demo checklist
- [ ] Cloud Run agent healthy (curl agent card returns 200)
- [ ] BYO Agent published on PO Marketplace
- [ ] Maria patient ID ready: 881f534f-d041-425d-a542-cbf669f43e18
- [ ] All inputs pre-copied (no typing during recording)

---

## Scene 1: Introduction (0:00 - 0:15)

**Voiceover:** "MamaGuard is an AI care coordination agent for maternal and pediatric health. It analyzes FHIR patient records using three specialist agents and fifteen tools — maternal risk, pediatric transitions, and social determinants — with seamless mother-to-child handoff and the clinician always in control. It ships as both an A2A agent and an MCP server."

**Visual:** Architecture diagram (dual A2A + MCP paths, 3 agents, 15 FHIR tools, Liaison pattern)

## Scene 2: Launch from Marketplace (0:15 - 0:30)

**Action:** Open PO Marketplace → find "MamaGuard" → Launch

**Voiceover:** "MamaGuard is available on the Prompt Opinion Marketplace as a BYO Agent. Clinicians launch it directly from the launchpad."

**Action:** Select patient Maria (881f534f)

## Scene 3: Maternal Risk Assessment (0:30 - 1:15)

**Input:** "Assess maternal risk for this patient"

**Wait for response.** Expected output shows:
- URGENT risk level
- BP trend: consistently >140/90, spike to 170/98 postpartum
- HbA1c trend: diabetes range
- 6 pregnancies, 5 losses
- CLINICIAN REVIEW REQUIRED for BP management

**Voiceover:** "The maternal agent queries the FHIR server for BP trends, glucose, pregnancy history, and medications. It identifies Stage 2 hypertension and recurrent pregnancy loss — flagging clinician review before any treatment recommendations."

**Flash:** Briefly show the FHIR JSON in the response (resource IDs, dates, values)

## Scene 4: SDOH Screening + Actionable Resources (1:15 - 1:50)

**Input:** "Screen for social determinants, find resources, and create a care plan"

**Wait for response.** Expected output shows:
- No insurance coverage found
- Primary language: French (language barrier)
- Concrete community resources found: Medicaid enrollment, 211 hotline, WIC, interpreter services
- FHIR Goal + CarePlan written (trackable SDOH referral)
- CommunicationRequest resource created for outreach

**Voiceover:** "The SDOH agent screens FHIR data, detects Maria has no insurance and speaks French, then looks up concrete resources — Medicaid enrollment, WIC, interpreter services — and writes a trackable FHIR CarePlan linked to a Goal so the care team can follow through. This is the actionable SDOH loop: screen, find resources, persist the intervention."

## Scene 5: Mother-to-Child Handoff (1:50 - 2:15)

**Input:** "Find linked children and check their immunization status"

**Wait for response.** Expected output shows:
- Orchestrator calls `find_linked_newborn` → discovers Lucas (linked via RelatedPerson)
- Maternal risk factors carried into pediatric context (DM2 → neonatal hypoglycemia screening)
- Immunization gap analysis against CDC schedule (birth through adolescent vaccines)
- Developmental screening status per AAP Bright Futures

**Voiceover:** "The orchestrator automatically discovers Maria's linked newborn, Lucas, via FHIR RelatedPerson resources — no manual patient switch needed. It carries maternal risk factors into the pediatric context and routes to the pediatric agent for immunization and developmental assessment."

## Scene 6: Technical Depth (2:15 - 2:45)

**Flash through quickly:**
1. Agent card JSON at `/.well-known/agent-card.json` (4 skills, FHIR extension, SMART tickets)
2. `clinician_review` object in tool response (Liaison pattern — every tool)
3. FHIR resources written: RiskAssessment, CommunicationRequest, Goal + CarePlan
4. MCP server exposing same 15 tools (dual submission: A2A + MCP)
5. API key security + FHIR token never in LLM prompt

**Voiceover:** "Under the hood: A2A protocol with FHIR context and SMART Permission Tickets, Liaison Agent pattern for human-in-the-loop, bidirectional FHIR write-back with four resource types, and a standalone MCP server exposing the same tools for any MCP-compatible client."

## Scene 7: Closing (2:45 - 3:00)

**Voiceover:** "MamaGuard targets the coordination gap responsible for 80% of preventable maternal deaths. Three specialist agents, fifteen FHIR tools, seamless mother-to-child handoff, dual A2A and MCP submission — with the clinician always in control."

**Visual:** Impact metrics table from Devpost description

---

## Pre-copied inputs
```
Assess maternal risk for this patient
Screen for social determinants, find resources, and create a care plan
Find linked children and check their immunization status
```
