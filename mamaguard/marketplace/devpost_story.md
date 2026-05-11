# MamaGuard — Devpost Story

## Inspiration

The US has the worst maternal mortality rate in the developed world, and ~80% of those deaths are preventable. Postpartum is the most dangerous window — and the one where care continuity falls apart fastest. The signal is almost never one lab or one missed visit; it's the **combination** of an elevated BP, a borderline HbA1c, a lapsed Medicaid coverage, a language barrier, and a clinician decision made two weeks ago that nobody re-read. Rules engines flag each piece in isolation. Clinicians don't have 20 minutes per chart to fuse them. I built MamaGuard for the gap between those two facts.

## What it does

MamaGuard is a **FHIR-native maternal-child care agent** that gives clinicians continuity, synthesis, and approval-gated action in one workflow:

- **Recalls prior clinician decisions** from FHIR `DocumentReference` so a fresh session knows that metformin was already declined for GI intolerance — and doesn't suggest it again.
- **Synthesizes compound risk** across BP trend, HbA1c, pregnancy history, housing, language, and Coverage gaps into a single urgent maternal narrative.
- **Writes back a pending Goal + CarePlan + CommunicationRequest** — and waits for the clinician to approve in Prompt Opinion before anything is committed.
- **Hands off mother → newborn** by following the linked patient resource into pediatric follow-up without a manual chart switch.

The demo runs against Maria, a postpartum patient with Stage 2 hypertension, diabetes-range HbA1c, coverage instability, and Spanish-language preference.

## How I built it

- **Agent runtime:** Google ADK, deployed to **Azure Container Apps** (`ca-mamaguard` + `ca-hapi-fhir` HAPI R4) for the live demo.
- **MCP server:** exposes FHIR read + write-back tools so any agent — not just MamaGuard — can use the continuity layer.
- **A2A v1** wire format aligned with Prompt Opinion's `SendA2AMessage`, so MamaGuard is invokable as a BYO agent from PO chat.
- **Plan-mode approval gate:** the agent emits a structured pending bundle; PO renders it; clinician approval flips the writes to active state.
- **Model backends:** production runs **Gemini 2.5 Flash**; benchmarks swap in **Nemotron-3-Super-120B** on a DGX Spark over a 10GbE direct link, with **DeepSeek v3.2 as LLM-as-judge**.
- **SHARP extension spec** carries the patient ID and FHIR token through the MCP and A2A boundaries.

## Challenges I ran into

- **A2A wire-format drift.** The PO BYO chat speaks A2A v1, not v0.3 — I had to drop deprecated agent-card fields and re-declare SMART scopes before invocations stopped silently failing.
- **Plan-mode in a chat surface.** Getting a pending CarePlan bundle to render *and* round-trip approval through PO's BYO chat took several iterations of the orchestrator prompt.
- **Memory window vs. demo entropy.** Every agent run writes a `DocumentReference`, which pushes Dr. Kim's prior memory note out of the fetch window — so I built a pre-record cleanup ritual.
- **Cloud Run → Azure pivot.** My scripts and docs assumed Cloud Run; live deployment landed on Azure Container Apps, with HAPI on in-memory H2 that requires a non-empty `fhirToken`.
- **Reasoning-mode models eat their own content.** Nemotron with `--reasoning-parser nemotron_v3` returns `message.content = null` when reasoning fires; I hardened the bench client to fall through to `message.reasoning`.
- **Saying no to scope.** Two weeks out I pivoted from benchmark-maximalism to patient-action storytelling. Cutting good work hurt.

## Accomplishments that I'm proud of

- **93.1% Tier-2b end-to-end pass rate** (45/47) on the April 17, 2026 submission run — against a live HAPI FHIR server, not mocks.
- **+30% average lift over a naive LLM** on the AI-factor benchmark, judged by DeepSeek v3.2 across clinical accuracy, risk, safety, completeness, and output quality.
- **100% clinician-review flagging** on URGENT/HIGH cases in safety verification — nothing dangerous gets auto-committed.
- A **clinician-approved write-back loop** that actually works end-to-end in Prompt Opinion's chat surface, not a screenshot.
- A **dual-track submission**: a usable MCP server other agents can pick up, plus a fully configured A2A agent on the PO marketplace.

## What I learned

- **`DocumentReference` is underrated as agent memory.** Continuity that lives inside the FHIR boundary survives session resets, model swaps, and clinician handoffs in a way that vector stores don't.
- **The judging unlock is the approval gate, not the model.** Every clinician I showed this to relaxed the moment they saw that *nothing writes until they say so*. That single architectural choice answered most of the safety, feasibility, and liability questions before they were asked.
- **Compound reasoning is where rules stop and GenAI starts.** Five flat flags is a worklist. One synthesized "Stage 2 postpartum HTN + diabetes-range HbA1c + Medicaid gap + Spanish-only support — call her today" is a clinical decision.
- **Narrative beats more tools.** I had a stretch goal to add three more FHIR tools the week before submission and chose to write the clinician story instead. It was the right call.

## What's next for MamaGuard

- **Pilot with a community health clinic** focused on perinatal Medicaid populations — the cohort where compound maternal + SDOH risk hits hardest.
- **SMART-on-FHIR launch into Epic and Cerner sandboxes**, replacing HAPI with a real EHR session and SHARP-bridged credentials.
- **Outreach delivery**, not just outreach planning: Twilio + secure-messaging adapters behind the CommunicationRequest, still approval-gated.
- **SFT a smaller model** — Gemma-4-26B-A4B on DGX Spark, trained on Nemotron-generated gold responses and judged by DeepSeek — to bring inference cost down to clinic-budget territory.
- **Extend the pattern beyond maternal-child**: pediatric chronic disease, geriatric polypharmacy, and oncology survivorship all have the same compound-continuity shape.
- **Open-source the MCP server** so any agent author can plug into the same approval-gated FHIR continuity layer I used.
