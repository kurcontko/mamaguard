"""
MamaGuard -- A2A application entry point.

Start the server with:
    uvicorn mamaguard.app:a2a_app --host 0.0.0.0 --port 8001

The agent card is served publicly at:
    GET http://localhost:8001/.well-known/agent-card.json

All other endpoints require an X-API-Key header (see shared/middleware.py).
"""

import os

from dotenv import load_dotenv

load_dotenv()

from a2a.types import AgentProvider, AgentSkill

from mamaguard import MAMAGUARD_VERSION
from mamaguard.shared.app_factory import create_a2a_app
from mamaguard.orchestrator.agent import root_agent

a2a_app = create_a2a_app(
    agent=root_agent,
    name="MamaGuard Care Coordinator",
    version=MAMAGUARD_VERSION,
    description=(
        "Maternal-pediatric care coordination agent with 15 FHIR tools. "
        "Three specialist agents (Maternal Risk, Pediatric Transition, SDOH Outreach) "
        "coordinate through an Orchestrator that routes queries, synthesizes findings "
        "into 5T output (Talk, Template, Table, Task, Transaction), and writes back "
        "RiskAssessment, CarePlan, and CommunicationRequest resources. "
        "Architecture: User -> Prompt Opinion -> A2A/MCP -> Orchestrator -> "
        "{Maternal, Pediatric, SDOH} agents -> shared FHIR tool layer -> FHIR R4 Server. "
        "Pauses for clinician review on critical decisions (Liaison Agent pattern). "
        "Requires FHIR context (server URL, bearer token, patient ID)."
    ),
    url=os.getenv("MAMAGUARD_URL", os.getenv("BASE_URL", "http://localhost:8001")),
    port=8001,
    fhir_extension_uri=f"{os.getenv('PO_PLATFORM_BASE_URL', 'https://app.promptopinion.ai')}/schemas/a2a/v1/fhir-context",
    provider=AgentProvider(
        organization="MamaGuard",
        url=os.getenv("MAMAGUARD_REPO_URL", "https://github.com/qrc/medical-hackathon-v3"),
    ),
    documentation_url=os.getenv(
        "MAMAGUARD_DOCS_URL",
        "https://github.com/qrc/medical-hackathon-v3/blob/main/README.md",
    ),
    skills=[
        AgentSkill(
            id="maternal-risk-assessment",
            name="Maternal Risk Assessment",
            description=(
                "Specialist agent with 7 FHIR tools that evaluates maternal risk "
                "across BP trends, glucose/HbA1c, pregnancy history, active "
                "medications, and a compound risk profile. Detects Stage 2 HTN, "
                "uncontrolled diabetes, recurrent pregnancy loss, and postpartum "
                "complications. Returns structured 5T output (Talk, Template, "
                "Table, Task, Transaction) with FHIR-cited evidence and writes "
                "RiskAssessment back to the patient record. Operates as a Liaison "
                "Agent — flags critical findings for clinician review, never "
                "prescribes or recommends specific medications."
            ),
            tags=["maternal", "risk", "pregnancy", "fhir"],
            examples=[
                "Assess maternal risk for this patient",
                "What are the BP and HbA1c trends and what do they mean clinically?",
                "Check this patient's pregnancy history and flag any complications",
            ],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
        ),
        AgentSkill(
            id="pediatric-care-transition",
            name="Pediatric Care Transition",
            description=(
                "Specialist agent with 5 FHIR tools covering immunization gap "
                "analysis (CDC schedule), developmental screening (AAP Bright "
                "Futures), and preventive care gaps. Integrates maternal context "
                "for newborns — screens for GDM-related neonatal risks, SGA from "
                "preeclampsia, and adjusts milestones for prematurity. Returns "
                "structured 5T output (Talk, Template, Table, Task, Transaction) "
                "and creates CommunicationRequest for follow-up. Operates as a "
                "Liaison Agent — flags all clinical decisions for clinician review."
            ),
            tags=["pediatric", "immunization", "screening", "newborn"],
            examples=[
                "Find linked children and check their immunization status",
                "Check immunization status and developmental milestones",
                "Are there pediatric care gaps inherited from the mother's history?",
            ],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
        ),
        AgentSkill(
            id="sdoh-screening-outreach",
            name="SDOH Screening & Outreach",
            description=(
                "Specialist agent with 6 FHIR tools that screens for social "
                "determinants: insurance coverage gaps, language barriers, and "
                "ICD-10 Z-code conditions (housing, food, transport, economic). "
                "Matches patients to concrete community resources (211, WIC, SNAP, "
                "Medicaid) and writes FHIR Goal + CarePlan for trackable referrals "
                "plus CommunicationRequest for outreach. Returns structured 5T "
                "output (Talk, Template, Table, Task, Transaction) prioritized by "
                "domain severity. Operates as a Liaison Agent — coordinates "
                "referrals while keeping clinicians in the loop."
            ),
            tags=["sdoh", "social-determinants", "outreach", "care-plan"],
            examples=[
                "Screen for social determinants, find resources, and create a care plan",
                "Does this patient have insurance and language barriers?",
                "Match this patient to community resources and write a CarePlan",
            ],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
        ),
        AgentSkill(
            id="comprehensive-care-plan",
            name="Comprehensive Care Plan",
            description=(
                "Runs all three specialist agents in parallel — maternal risk "
                "(7 tools), pediatric transition (5 tools), SDOH screening "
                "(6 tools) — then synthesizes findings into a unified 5T care "
                "coordination plan (Talk, Template, Table, Task, Transaction). "
                "Applies cross-domain risk elevation rules: SDOH gaps with chronic "
                "medications escalate risk; maternal complications elevate pediatric "
                "monitoring. Highest risk from any domain wins. Operates as a "
                "Liaison Agent — all critical decisions flagged for clinician "
                "review. Best for full patient assessments."
            ),
            tags=["care-plan", "coordination", "summary"],
            examples=[
                "Run a comprehensive assessment for this patient",
                "Give me the full picture across maternal, pediatric, and SDOH",
                "What is the current plan for this patient and what should I know about her history?",
            ],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
        ),
    ],
)
