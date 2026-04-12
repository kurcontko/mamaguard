"""
Shared tools catalogue -- re-exports all 14 tool functions.

Base FHIR tools (fhir_base.py)
    get_patient_summary       Patient demographics + conditions + meds + recent vitals
    get_active_medications    Active MedicationRequest resources

Maternal tools (maternal.py)
    get_bp_trend              Blood pressure readings with trend and alerts
    get_glucose_trend         Glucose + HbA1c readings with trend
    get_pregnancy_history     All pregnancies with outcomes and complications
    get_maternal_risk_profile Compound risk profile (BP + glucose + pregnancy)

Pediatric tools (pediatric.py)
    get_immunization_gaps              Due vs received vaccines per CDC schedule
    get_developmental_screening_status Completed vs due screenings per AAP
    get_care_gaps                      Overdue items from CarePlan/Goal/Encounter

SDOH tools (sdoh.py)
    get_sdoh_screening        SDOH conditions, coverage, language barriers
    find_sdoh_resources       Z-code/category + ZIP → concrete callable resources

Write-back tools (writeback.py)
    write_risk_assessment        POST RiskAssessment to FHIR
    create_communication_request POST CommunicationRequest to FHIR
    write_care_plan              POST Goal + CarePlan tied to an SDOH resource
"""

from .fhir_base import (
    get_active_medications,
    get_patient_summary,
)

from .maternal import (
    get_bp_trend,
    get_glucose_trend,
    get_maternal_risk_profile,
    get_pregnancy_history,
)

from .pediatric import (
    get_care_gaps,
    get_developmental_screening_status,
    get_immunization_gaps,
)

from .sdoh import (
    find_sdoh_resources,
    get_sdoh_screening,
)

from .writeback import (
    create_communication_request,
    write_care_plan,
    write_risk_assessment,
)

__all__ = [
    "get_patient_summary",
    "get_active_medications",
    "get_bp_trend",
    "get_glucose_trend",
    "get_maternal_risk_profile",
    "get_pregnancy_history",
    "get_immunization_gaps",
    "get_developmental_screening_status",
    "get_care_gaps",
    "get_sdoh_screening",
    "find_sdoh_resources",
    "write_risk_assessment",
    "create_communication_request",
    "write_care_plan",
]
