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

from a2a.types import AgentSkill

from mamaguard.shared.app_factory import create_a2a_app
from mamaguard.orchestrator.agent import root_agent

a2a_app = create_a2a_app(
    agent=root_agent,
    name="MamaGuard Care Coordinator",
    description=(
        "Maternal-pediatric care coordination agent with 15 FHIR tools. "
        "Monitors high-risk pregnancies, manages mother-to-child care transitions, "
        "screens for SDOH with actionable community resource referrals, and writes "
        "back RiskAssessment, CommunicationRequest, Goal, and CarePlan resources. "
        "Pauses for clinician review on critical decisions (Liaison Agent pattern). "
        "Requires FHIR context (server URL, bearer token, patient ID)."
    ),
    url=os.getenv("MAMAGUARD_URL", os.getenv("BASE_URL", "http://localhost:8001")),
    port=8001,
    fhir_extension_uri=f"{os.getenv('PO_PLATFORM_BASE_URL', 'https://app.promptopinion.ai')}/schemas/a2a/v1/fhir-context",
    skills=[
        AgentSkill(
            id="maternal-risk-assessment",
            name="Maternal Risk Assessment",
            description=(
                "Analyzes maternal risk factors using 7 FHIR tools: BP trends, "
                "glucose/HbA1c control, pregnancy history, medication review, and "
                "compound risk profile. Flags Stage 2 HTN, uncontrolled diabetes, "
                "and recurrent pregnancy loss. Writes RiskAssessment to FHIR. "
                "Example: 'Assess maternal risk for this patient' or "
                "'What are this patient's BP trends?'"
            ),
            tags=["maternal", "risk", "pregnancy", "fhir"],
        ),
        AgentSkill(
            id="pediatric-care-transition",
            name="Pediatric Care Transition",
            description=(
                "Manages pediatric care using 5 FHIR tools: immunization gap "
                "analysis against CDC schedule, developmental screening per AAP "
                "Bright Futures, and preventive care gap detection. Creates "
                "CommunicationRequest for follow-up. Considers maternal risk "
                "factors for newborns. "
                "Example: 'Check immunization status and developmental milestones'"
            ),
            tags=["pediatric", "immunization", "screening", "newborn"],
        ),
        AgentSkill(
            id="sdoh-screening-outreach",
            name="SDOH Screening & Outreach",
            description=(
                "Screens for social determinants using 6 FHIR tools: insurance "
                "coverage gaps, language barriers, Z-code conditions (housing, food, "
                "economic). Looks up concrete community resources (211, WIC, SNAP, "
                "Medicaid). Writes FHIR Goal + CarePlan for trackable referrals and "
                "CommunicationRequest for outreach. "
                "Example: 'Screen for social determinants and find resources'"
            ),
            tags=["sdoh", "social-determinants", "outreach", "care-plan"],
        ),
        AgentSkill(
            id="comprehensive-care-plan",
            name="Comprehensive Care Plan",
            description=(
                "Runs all three specialists sequentially — maternal risk, pediatric "
                "transition, SDOH screening — then synthesizes findings into a "
                "prioritized 5T care coordination plan (Talk, Template, Table, Task, "
                "Transaction). Best for full patient assessments. "
                "Example: 'Run a comprehensive assessment for this patient'"
            ),
            tags=["care-plan", "coordination", "summary"],
        ),
    ],
)
