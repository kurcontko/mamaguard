"""
Shared tools catalogue -- re-exports all 21 tool functions.

When ``MAMAGUARD_AUDIT_EVENTS=true``, every tool invocation emits a FHIR
AuditEvent recording which agent accessed what data (HIPAA compliance trail).

Base FHIR tools (fhir_base.py)
    get_patient_summary       Patient demographics + conditions + meds + recent vitals
    get_active_medications    Active MedicationRequest resources
    get_current_plan          Active CarePlan/Goal/Request/RiskAssessment resources
    find_linked_newborn       Find child Patient linked via RelatedPerson

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

Plan-mode tools (plan_mode.py)
    plan_risk_assessment         Stage RiskAssessment for clinician approval
    plan_communication_request   Stage CommunicationRequest for clinician approval
    plan_care_plan               Stage Goal + CarePlan for clinician approval
    commit_pending_write         Commit or deny a staged FHIR write
    list_pending_writes          List staged and completed plan-mode writes
"""

from ..audit_event import audited
from .fhir_base import (
    find_linked_newborn as _find_linked_newborn,
)
from .fhir_base import (
    get_active_medications as _get_active_medications,
)
from .fhir_base import (
    get_current_plan as _get_current_plan,
)
from .fhir_base import (
    get_patient_summary as _get_patient_summary,
)
from .maternal import (
    get_bp_trend as _get_bp_trend,
)
from .maternal import (
    get_glucose_trend as _get_glucose_trend,
)
from .maternal import (
    get_maternal_risk_profile as _get_maternal_risk_profile,
)
from .maternal import (
    get_pregnancy_history as _get_pregnancy_history,
)
from .pediatric import (
    get_care_gaps as _get_care_gaps,
)
from .pediatric import (
    get_developmental_screening_status as _get_developmental_screening_status,
)
from .pediatric import (
    get_immunization_gaps as _get_immunization_gaps,
)
from .plan_mode import (
    commit_pending_write as _commit_pending_write,
)
from .plan_mode import (
    list_pending_writes as _list_pending_writes,
)
from .plan_mode import (
    plan_care_plan as _plan_care_plan,
)
from .plan_mode import (
    plan_communication_request as _plan_communication_request,
)
from .plan_mode import (
    plan_risk_assessment as _plan_risk_assessment,
)
from .sdoh import (
    find_sdoh_resources as _find_sdoh_resources,
)
from .sdoh import (
    get_sdoh_screening as _get_sdoh_screening,
)
from .writeback import (
    create_communication_request as _create_communication_request,
)
from .writeback import (
    write_care_plan as _write_care_plan,
)
from .writeback import (
    write_risk_assessment as _write_risk_assessment,
)

# Wrap every tool with the AuditEvent decorator.  When the feature flag
# is off (default), the wrapper is a no-op passthrough.
get_patient_summary = audited(_get_patient_summary)
get_active_medications = audited(_get_active_medications)
get_current_plan = audited(_get_current_plan)
find_linked_newborn = audited(_find_linked_newborn)
get_bp_trend = audited(_get_bp_trend)
get_glucose_trend = audited(_get_glucose_trend)
get_maternal_risk_profile = audited(_get_maternal_risk_profile)
get_pregnancy_history = audited(_get_pregnancy_history)
get_immunization_gaps = audited(_get_immunization_gaps)
get_developmental_screening_status = audited(_get_developmental_screening_status)
get_care_gaps = audited(_get_care_gaps)
get_sdoh_screening = audited(_get_sdoh_screening)
find_sdoh_resources = audited(_find_sdoh_resources)
write_risk_assessment = audited(_write_risk_assessment)
create_communication_request = audited(_create_communication_request)
write_care_plan = audited(_write_care_plan)
plan_risk_assessment = audited(_plan_risk_assessment)
plan_communication_request = audited(_plan_communication_request)
plan_care_plan = audited(_plan_care_plan)
commit_pending_write = audited(_commit_pending_write)
list_pending_writes = audited(_list_pending_writes)

__all__ = [
    "get_patient_summary",
    "get_active_medications",
    "get_current_plan",
    "find_linked_newborn",
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
    "plan_risk_assessment",
    "plan_communication_request",
    "plan_care_plan",
    "commit_pending_write",
    "list_pending_writes",
]
