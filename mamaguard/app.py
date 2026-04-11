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
        "Maternal-pediatric care coordination agent. Monitors high-risk pregnancies, "
        "manages mother-to-child care transitions, screens for SDOH, coordinates "
        "outreach. Pauses for clinician review on critical decisions."
    ),
    url=os.getenv("MAMAGUARD_URL", os.getenv("BASE_URL", "http://localhost:8001")),
    port=8001,
    fhir_extension_uri=f"{os.getenv('PO_PLATFORM_BASE_URL', 'https://app.promptopinion.ai')}/schemas/a2a/v1/fhir-context",
    skills=[
        AgentSkill(
            id="maternal-risk-assessment",
            name="Maternal Risk Assessment",
            description="Analyzes maternal risk factors: BP trends, glucose, pregnancy history, postpartum complications. Pauses for clinician review.",
            tags=["maternal", "risk", "pregnancy", "fhir"],
        ),
        AgentSkill(
            id="pediatric-care-transition",
            name="Pediatric Care Transition",
            description="Manages newborn screening, immunization schedule, developmental milestones per CDC/AAP guidelines.",
            tags=["pediatric", "immunization", "screening", "newborn"],
        ),
        AgentSkill(
            id="sdoh-screening-outreach",
            name="SDOH Screening & Outreach",
            description="Screens for SDOH risks, insurance gaps, connects to community resources, generates outreach requests.",
            tags=["sdoh", "social-determinants", "outreach"],
        ),
        AgentSkill(
            id="comprehensive-care-plan",
            name="Comprehensive Care Plan",
            description="Synthesizes maternal, pediatric, and SDOH findings into prioritized care coordination plan.",
            tags=["care-plan", "coordination", "summary"],
        ),
    ],
)
