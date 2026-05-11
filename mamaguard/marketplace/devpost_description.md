# MamaGuard: FHIR-Native Maternal-Child Care Continuity Agent

## What it does

MamaGuard helps clinicians manage maternal-child care when the real risk is not one lab, one visit, or one missing referral, but the combination of all of them over time.

Our demo centers on Maria, a postpartum patient in Prompt Opinion. In a fresh session, MamaGuard retrieves a prior clinician decision from FHIR `DocumentReference`, recalls that metformin was previously declined because of GI intolerance, reads today's maternal and SDOH context from the chart, synthesizes an urgent postpartum risk story, creates a pending outreach plan, and waits for clinician approval before any care-coordination write-back is committed.

The product claim is simple:

- **Continuity inside FHIR**: prior decisions, trajectory notes, and in-flight plans live in the same FHIR boundary as the rest of the chart.
- **Compound maternal + SDOH reasoning**: MamaGuard combines BP trend, HbA1c, pregnancy history, language, housing, and insurance context into one clinician-facing synthesis that rules do not produce well.
- **Clinician-approved action**: Goal, CarePlan, and CommunicationRequest stay pending until the clinician approves in Prompt Opinion.
- **Optional mother-to-child handoff**: if a linked newborn is present, MamaGuard can continue into pediatric follow-up without forcing a manual patient switch.

## Why it matters

Without MamaGuard, continuity depends on fragmented chart review: prior decisions are easy to miss, declined recommendations get repeated, outreach is tracked outside the chart, and urgent postpartum risk can be diluted across separate notes, labs, and social-history fields.

With MamaGuard, a fresh session can recover what already happened, explain why today's combined maternal + SDOH picture is urgent, and turn that into tracked, clinician-approved follow-up in the same workflow.

## Where GenAI matters

This is not just rules automation.

Rules can say:

- BP is elevated
- HbA1c is abnormal
- Coverage is missing
- Language support is needed

MamaGuard goes further:

- It remembers the prior clinician decision and avoids repeating a declined recommendation.
- It explains why Stage 2 postpartum hypertension plus diabetes-range HbA1c plus coverage instability plus language barriers should change the urgency and outreach plan.
- It turns structured FHIR data into a concise 5T clinical summary: Talk, Template, Table, Task, Transaction.
- It pauses for clinician review before action, then commits the approved plan back to FHIR.

That combination of continuity, synthesis, and approval-gated action is the AI factor.

## How the demo works

1. A clinician launches MamaGuard from the Prompt Opinion marketplace and opens Maria's chart.
2. In a **fresh session**, MamaGuard recalls a prior decision from FHIR memory and cites it directly in the response.
3. It synthesizes Maria's urgent postpartum maternal risk together with SDOH amplifiers.
4. It generates a **pending** Goal + CarePlan + CommunicationRequest bundle for outreach.
5. The clinician approves the plan, and MamaGuard commits the write-back to FHIR.
6. If time permits, MamaGuard discovers Maria's linked newborn and continues into pediatric follow-up.

## Proof

We keep the submission proof to three headline numbers:

- **93.1% Tier-2b end-to-end** on the April 17, 2026 submission run (**45/47 passed**).
- **+30%** average lift over a naive LLM on our AI-factor benchmark.
- **100% clinician-review flagging** on URGENT/HIGH cases in safety verification.

What these numbers mean:

- The end-to-end score shows the full system working with real HAPI FHIR, real tool calls, and an independent judge.
- The AI-factor comparison shows MamaGuard's advantage is not "has more tooling"; it is better compound reasoning, better safety behavior, and better structured actionability on the same patient data.
- The clinician-review result shows the most important safety behavior is reliable: urgent cases are escalated to a human.

## Technical credibility

MamaGuard is intentionally technical where it helps impact and feasibility:

- **Prompt Opinion launch** as a BYO Agent for the primary clinician experience.
- **A2A + MCP dual artifact** backed by the same FHIR tool layer.
- **FHIR-native memory** via `DocumentReference`, not a sidecar memory store.
- **Approval gate** for care-coordination write-back.
- **FHIR write-back** of RiskAssessment, Goal, CarePlan, and CommunicationRequest.
- **FHIR AuditEvent** support for traceability.

We do not rely on architecture complexity as the story. The story is that continuity, synthesis, and clinician-approved action all happen inside standards-based clinical infrastructure.

## Built With

- Python 3.11
- Google ADK
- A2A SDK
- MCP SDK
- FHIR R4
- Prompt Opinion
- Google Cloud Run
- Gemini 2.5 Flash
- DeepSeek v3.2 judge
