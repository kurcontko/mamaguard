# MamaGuard Demo Script (< 3 minutes)

## Pre-demo checklist
- [ ] Cloud Run agent healthy (`curl <AGENT_URL>/.well-known/agent-card.json` returns 200)
- [ ] BYO Agent published on PO Marketplace
- [ ] Maria patient ID ready: bench-maria-001 (linked child: bench-baby-santos-001)
- [ ] All inputs pre-copied (no typing during recording)
- [ ] Verify 5T output rendering (Talk/Template/Table/Task/Transaction sections visible)

---

## Scene 1: Introduction (0:00 – 0:15) ~15s

**Voiceover:** "MamaGuard is an AI care coordination agent for maternal and pediatric health. It analyzes FHIR patient records using three specialist agents, 16 shared FHIR tools, and approval-gated write planning — maternal risk, pediatric transitions, and social determinants — with seamless mother-to-child handoff and the clinician always in control. Every response follows the 5T framework: Talk, Template, Table, Task, Transaction. It ships as both an A2A agent and an MCP server."

**Visual:** Architecture diagram (dual A2A + MCP paths, 3 agents, 16 FHIR tools, Liaison pattern, 5T output)

## Scene 2: Launch from Marketplace (0:15 – 0:30) ~15s

**Action:** Open PO Marketplace → find "MamaGuard" → Launch

**Voiceover:** "MamaGuard is available on the Prompt Opinion Marketplace as a BYO Agent. Clinicians launch it directly from the launchpad."

**Action:** Select patient Maria (bench-maria-001)

## Scene 3: Maternal Risk Assessment (0:30 – 1:15) ~45s

**Input:** `Assess maternal risk for this patient`

**Wait for response (~5–8s).** Expected 5T output:

> **Talk** — Maria presents with URGENT maternal risk: Stage 2 hypertension (most recent BP 162/104) with escalating trend, and HbA1c 7.2% in the diabetes range. She is 8 weeks postpartum. Immediate clinician review is recommended.
>
> **Template** — Risk Level: URGENT
> Key findings:
> - BP 162/104 on 2026-03-20 (Observation/bp-m5) — Stage 2 HTN
> - BP 158/98 on 2026-03-10 (Observation/bp-m4) — escalating trend
> - HbA1c 7.2% on 2026-03-18 (Observation/hba1c-m1) — diabetes range
> - Pregnancy: resolved 2026-02-01, postpartum ≤12mo
> ⚠ CLINICIAN REVIEW REQUIRED: Stage 2 HTN with escalating postpartum BP trend. Medication management requires clinician review.
>
> **Table**
> | Metric | Value | Date | Source |
> |--------|-------|------|--------|
> | BP | 162/104 | 2026-03-20 | Observation/bp-m5 |
> | BP | 158/98 | 2026-03-10 | Observation/bp-m4 |
> | HbA1c | 7.2% | 2026-03-18 | Observation/hba1c-m1 |
>
> **Task**
> 1. URGENT — Clinician review of BP trend and postpartum HTN | Clinician | Within 24h
> 2. HIGH — Repeat HbA1c in 3 months | Lab / Clinician | 3 months
> 3. MODERATE — Postpartum follow-up visit | OB team | 2 weeks
>
> **Transaction** — RiskAssessment/ra-001 created (maternal_risk_agent). Requires clinician approval.
>
> AI-generated analysis. Not for clinical use.

**Key points to highlight:**
- Structured 5T format with FHIR resource citations (Observation IDs, dates)
- Safety filter: no specific drug names — says "Medication management requires clinician review"
- ⚠ CLINICIAN REVIEW REQUIRED block (Liaison pattern)
- RiskAssessment FHIR resource written back to patient record

**Voiceover:** "The maternal agent queries the FHIR server for BP trends, glucose, pregnancy history, and medications using a compound risk profile tool. It identifies Stage 2 hypertension and diabetes-range HbA1c — flagging clinician review. Notice the structured 5T output: every finding cites a FHIR resource ID, and the agent never prescribes — it writes a RiskAssessment and defers treatment to the clinician."

## Scene 4: SDOH Screening + Actionable Resources (1:15 – 1:50) ~35s

**Input:** `Screen for social determinants, find resources, and create a care plan`

**Wait for response (~6–10s).** Expected 5T output:

> **Talk** — Maria has active SDOH risk factors: no active insurance coverage and French-language preference requiring interpreter services. She is postpartum on chronic medications — the insurance gap is URGENT due to risk of medication discontinuation.
>
> **Template** — Risk Level: URGENT
> Active SDOH conditions:
> - No active Coverage resource found — URGENT (patient on chronic medications)
> - Primary language: French, interpreter needed (Patient/bench-maria-001)
> ⚠ CLINICIAN REVIEW REQUIRED: Insurance gap with chronic medication risk.
>
> **Table**
> | Domain | Severity | FHIR Source |
> |--------|----------|-------------|
> | Insurance | URGENT | No active Coverage |
> | Language | MODERATE | Patient/bench-maria-001 (French) |
>
> | Resource | Type | Contact |
> |----------|------|---------|
> | Medicaid Enrollment Office | Insurance | 555-0102 |
> | WIC Program | Nutrition | 211 hotline |
> | Interpreter Services | Language | 555-0199 |
>
> **Task**
> 1. URGENT — Medicaid re-enrollment; coverage continuity for chronic meds | Benefits navigator | Within 48h
> 2. MODERATE — Arrange French interpreter for upcoming appointments | Scheduling | Next visit
>
> **Transaction** — Goal/goal-001 + CarePlan/cp-001 created (sdoh_outreach_agent). CommunicationRequest/comm-002 created (Medicaid outreach). Requires clinician approval.
>
> AI-generated analysis. Not for clinical use.

**Key points to highlight:**
- Community resources table with actionable contacts
- FHIR Goal + CarePlan written — trackable SDOH referral, not just a text recommendation
- CommunicationRequest for outreach follow-up
- Cross-domain risk elevation: insurance gap + chronic medications = URGENT

**Voiceover:** "The SDOH agent screens FHIR data, detects Maria has no insurance and speaks French, then looks up concrete resources — Medicaid enrollment, WIC, interpreter services — and writes a trackable FHIR CarePlan linked to a Goal so the care team can follow through. This is the actionable SDOH loop: screen, find resources, persist the intervention as FHIR write-backs."

## Scene 5: Mother-to-Child Handoff (1:50 – 2:15) ~25s

**Input:** `Find linked children and check their immunization status`

**Wait for response (~5–8s).** Expected 5T output:

> **Talk** — Baby Santos (6 weeks old) has HIGH pediatric risk: only the birth-dose HepB has been administered; the 2-month vaccine series is now due. Maternal history includes diabetes — neonatal glucose monitoring applies. Linked via FHIR RelatedPerson from Maria (bench-maria-001).
>
> **Template** — Risk Level: HIGH
> Key findings:
> - 1 of 6 expected immunizations received (HepB birth dose)
> - 2-month vaccines due: DTaP, IPV, Hib, PCV13, RV
> - ASQ-3 developmental screening due at 2 months
> - Maternal DM2 noted — monitor for neonatal hypoglycemia
> ⚠ CLINICIAN REVIEW REQUIRED: Overdue immunizations; catch-up schedule needed.
>
> **Table**
> | Vaccine | Dose | Status | Date |
> |---------|------|--------|------|
> | HepB | 1 | Completed | 2026-02-09 |
> | DTaP | 1 | Due | 2-month visit |
> | IPV | 1 | Due | 2-month visit |
> | Hib | 1 | Due | 2-month visit |
> | PCV13 | 1 | Due | 2-month visit |
> | RV | 1 | Due | 2-month visit |
>
> **Task**
> 1. HIGH — Schedule catch-up vaccination visit | Pediatrician | Within 2 weeks
> 2. MODERATE — Complete ASQ-3 developmental screening | Pediatrician | 2-month visit
> 3. MODERATE — Anticipatory guidance: safe sleep, feeding | Care team | Next visit
>
> **Transaction** — CommunicationRequest/comm-001 created (pediatric_transition_agent, catch-up vaccine outreach). Requires clinician approval.
>
> AI-generated analysis. Not for clinical use.

**Key points to highlight:**
- `find_linked_newborn` discovers child via FHIR RelatedPerson — no manual patient switch
- Maternal risk factors (DM2) carried into pediatric context
- CDC immunization gap analysis with per-vaccine status table
- Tool response caching: second agent reuses patient data fetched by first agent

**Voiceover:** "The orchestrator automatically discovers Maria's linked newborn via FHIR RelatedPerson resources — no manual patient switch needed. It carries maternal risk factors into the pediatric context and routes to the pediatric agent for immunization gap analysis and developmental screening. Notice the mother-to-child handoff is seamless — one conversation covers both patients."

## Scene 6: Technical Depth (2:15 – 2:45) ~30s

**Flash through quickly:**
1. Agent card JSON at `/.well-known/agent-card.json` — 4 skills with 5T descriptions, FHIR extension, SMART Permission Tickets
2. `clinician_review` object in every tool response — `{ required, reason, evidence_basis, confidence }` (Liaison pattern)
3. FHIR write-back with validation: RiskAssessment, CommunicationRequest, Goal + CarePlan — required fields checked, risk_level validated, patient_id verified before POST
4. Safety filter: prescribing language auto-redacted, replaced with clinician deferral
5. Response filter: formatting cleanup (no triple backticks, collapsed rules, duplicate headers stripped)
6. Session-level tool response caching: second sub-agent reuses FHIR data from first — fewer server round-trips
7. FHIR error recovery: partial data triggers "⚠ DATA UNAVAILABLE" markers with manual review tasks, not silent failures
8. MCP server exposing 19 tools: 16 shared FHIR tools plus 3 compound assessments (dual submission: A2A + MCP)

**Voiceover:** "Under the hood: A2A protocol with FHIR context and SMART Permission Tickets, Liaison Agent pattern for human-in-the-loop, bidirectional FHIR write-back with field validation, a safety filter that prevents autonomous prescribing, session-level tool caching across sub-agents, graceful FHIR error recovery, and a standalone MCP server exposing the same FHIR tool layer plus compound assessments for any MCP-compatible client."

## Scene 7: Closing (2:45 – 3:00) ~15s

**Voiceover:** "MamaGuard targets the coordination gap responsible for 80% of preventable maternal deaths. Three specialist agents, 16 FHIR tools, structured 5T output, seamless mother-to-child handoff, dual A2A and MCP submission — with the clinician always in control."

**Visual:** Impact metrics table from Devpost description

---

## Timing Summary

| Scene | Duration | Cumulative |
|-------|----------|------------|
| 1. Introduction | ~15s | 0:15 |
| 2. Marketplace launch | ~15s | 0:30 |
| 3. Maternal risk | ~45s | 1:15 |
| 4. SDOH screening | ~35s | 1:50 |
| 5. Pediatric handoff | ~25s | 2:15 |
| 6. Technical depth | ~30s | 2:45 |
| 7. Closing | ~15s | 3:00 |

**Buffer:** If agent response times vary, trim Scene 6 flash-throughs first (cut items 5–7). Scenes 3–5 are the core demo.

---

## Pre-copied inputs
```
Assess maternal risk for this patient
Screen for social determinants, find resources, and create a care plan
Find linked children and check their immunization status
```

---

# v3 ADDENDUM — the two differentiators (insert if trimming length)

Architecture v3 adds two capabilities no competitor submission has. If the
3-minute cut needs more air, pull these into the middle of the video in
place of Scene 6 (Technical Depth). They answer AI Factor and Feasibility
more directly than a technical flash-through does.

## Scene 3.5: Longitudinal memory recall (insert after Maternal, ~30s)

**Pre-demo:** run once before recording (do NOT record this):
```bash
uv run python scripts/demo_memory_recall.py --seed-only
```
This writes a `DocumentReference` on HAPI for Maria — a prior-visit note
stating "Dr. Kim declined metformin 38 days ago due to GI intolerance".

**Action:** open a **fresh** A2A session against Maria. Ask:

> `What is the current plan for Maria and what should I know about her history?`

**Expected 5T output (the magic moment):**

> **Talk** — Carrying forward from Dr. Kim's note of 38 days ago: metformin
> has been explicitly declined due to GI intolerance. Today's findings
> (BP 162/104, HbA1c 7.2%) remain URGENT, but antidiabetic escalation
> should NOT be proposed — coordination with Dr. Kim is required. Housing
> referral to Helping Hands is in-flight from the prior visit.
>
> **Template** — Continuity notes:
> - Prior visit 2026-03-10: metformin declined (Dr. Kim) — do not re-recommend
> - Housing referral submitted 2026-03-12 to Helping Hands, awaiting response
> - Primary language: French, interpreter confirmed
> ...

**Voiceover:** "Every other hackathon submission — AuthPilot, Clinical Oracle,
all of them — is stateless. They treat each patient interaction as the first
one. MamaGuard doesn't. Dr. Kim's decision from last month is stored as a
FHIR DocumentReference on the same server as every other resource. New
session, same patient — the note comes back, the agent carries forward,
no repeat prescribing of a medication that was already declined."

**Key points:**
- Memory lives **inside FHIR** (category `clinical-reasoning-history`) — zero new
  infra, full HIPAA boundary inheritance
- Readable by **any other A2A agent** on the marketplace via standard query
- The `<patient-memory>` block is injected by a `before_model_callback` — not
  magic, just FHIR

## Scene 4.5: Plan / Commit approval gate (insert after SDOH, ~25s)

**Action:** after Scene 4's SDOH output shows "Transaction — PENDING APPROVAL:
plan_id=plan-careplanbundle-1-XXXX", send:

> `Approve plan plan-careplanbundle-1-XXXX`

**Expected 5T output:**

> **Talk** — Goal and CarePlan committed for Maria's Medicaid re-enrollment
> referral. Clinician approval recorded in audit trail.
>
> **Transaction** — Goal/goal-001 + CarePlan/cp-001 POSTed (approved by
> clinician). plan_id=plan-careplanbundle-1-XXXX → committed.

**Voiceover:** "For HIGH and URGENT findings, MamaGuard does not POST directly
to FHIR. It builds the bundle, shows the bundle, waits for the clinician to
approve the bundle, then posts. This is the Liaison pattern turned into
demonstrable behavior rather than a claim — the FHIR write happens only
after a human says yes."

**Key points:**
- `plan_*` tools build + store the FHIR body but do not POST
- `commit_pending_write(plan_id, approved=True|False)` is the only path that
  reaches the server
- Policy: ROUTINE / MODERATE auto-commit, HIGH / URGENT require explicit
  approval
- Every commit is logged with the approver name (audit-trail friendly)

---

# Shot list (for the human recording this)

Record in this order, cut to 3 minutes in post:

1. **Screen capture** of the Prompt Opinion marketplace page with MamaGuard
   visible (30s, will be trimmed).
2. **Screen capture** of full A2A session in PO: three queries (maternal,
   SDOH, pediatric handoff). Capture the 5T output rendering clearly.
3. **Memory scene**: run `--seed-only` off-camera, then record a fresh
   session showing the recall — the "38 days ago" line is the payoff.
4. **Approval scene**: SDOH query followed by "Approve plan ..." follow-up.
5. **Voiceover** recorded separately, overlaid in post.
6. **Architecture diagram** b-roll (use the ASCII diagram from README.md
   rendered cleanly; replace with a real diagram if time permits).

Keep Scenes 3.5 and 4.5 if total runtime permits — they are the AI Factor
and Feasibility hooks judges actually care about.
