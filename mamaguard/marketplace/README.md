# MamaGuard -- Prompt Opinion Marketplace Setup

## Prerequisites

1. MamaGuard agent deployed to Cloud Run with public HTTPS URL
2. Prompt Opinion account (free at https://promptopinion.ai)
3. Google AI Studio API key (free)

## Step-by-Step Setup

### 1. Register External Agent

1. In PO, go to **Agents > External Agents > Add Connection**
2. Enter agent card URL: `https://YOUR-CLOUD-RUN-URL/.well-known/agent-card.json`
3. PO will discover the agent card with 4 skills and FHIR extension
4. Enter the API key configured in your deployment
5. Acknowledge: "PO will send an authenticated token as part of the FHIR context"

### 2. Create BYO Agent

1. Go to **Agents > Create Agent**
2. Name: `MamaGuard: Maternal-Pediatric Care Coordinator`
3. Scope: **Patient**
4. Model: **Gemini 2.5 Flash** (configure Google AI Studio key)
5. System prompt: copy from `byo_system_prompt.md`
6. Enable FHIR context
7. Add consultation to the registered MamaGuard external agent
8. Consultation prompt: copy from `byo_consultation_prompt.md`

### 3. Publish to Marketplace

1. Click **Publish to Marketplace**
2. Verify: agent appears on launchpad and is directly invokable

### 4. Test

1. Launch MamaGuard from launchpad
2. Select patient Maria (Patient/bench-maria-001)
3. Ask: "Assess maternal risk for this patient"
4. Verify: BYO consults external agent > FHIR data flows > structured response returns
