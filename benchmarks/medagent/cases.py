"""
42 MedAgentBench-style cases over MamaGuard's FHIR tools.

Format follows the public MedAgentBench task definition:
  - instruction:   natural-language user query
  - patient_id:    FHIR Patient.id under test
  - task_type:     "query" (read-only) | "action" (write-back)
  - gold_tools:    the minimal tool set a correct answer must invoke
  - gold_answer:   expected key facts (substrings in the final text)
  - gold_not:      substrings that MUST NOT appear (safety)

Cases cover the clinical domains MamaGuard targets:
  - Maternal vitals and labs
  - Obstetric history
  - Medication review
  - Pediatric immunizations
  - Pediatric developmental screening
  - SDOH (coverage, language, Z-codes)
  - Compound risk reasoning
  - Write-back actions (RiskAssessment, CommunicationRequest, CarePlan)
  - Actionable SDOH (find_sdoh_resources, write_care_plan)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MedAgentCase:
    id: str
    instruction: str
    patient_id: str
    task_type: str  # "query" or "action"
    gold_tools: set[str] = field(default_factory=set)
    gold_answer: list[str] = field(default_factory=list)
    gold_not: list[str] = field(default_factory=list)
    domain: str = ""  # maternal | pediatric | sdoh | compound


CASES: list[MedAgentCase] = [
    # -------------------------------------------------------------------
    # Query tasks — Maternal vitals & labs
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q01",
        instruction="What is the most recent blood pressure reading for this patient?",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_bp_trend", "get_patient_summary"},
        gold_answer=["168", "108"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q02",
        instruction="Summarize the systolic blood pressure trend over the last 12 months.",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_bp_trend"},
        gold_answer=["142", "170"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q03",
        instruction="Does this patient have Stage 2 hypertension on any recent reading?",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_bp_trend"},
        gold_answer=["Stage 2", "yes"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q04",
        instruction="What was this patient's latest HbA1c value and does it indicate diabetes?",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_glucose_trend"},
        gold_answer=["7.9", "diabet"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q05",
        instruction="Is this patient's HbA1c in the normal range?",
        patient_id="bench-sarah-002",
        task_type="query",
        gold_tools={"get_glucose_trend"},
        gold_answer=["5.1", "normal"],
        gold_not=["diabet"],
        domain="maternal",
    ),

    # -------------------------------------------------------------------
    # Query tasks — Obstetric history
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q06",
        instruction="How many total pregnancies does this patient have on record and what were the outcomes?",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_pregnancy_history"},
        gold_answer=["6", "live birth", "loss"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q07",
        instruction="Does this patient meet criteria for recurrent pregnancy loss (2+ losses)?",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_pregnancy_history"},
        gold_answer=["recurrent", "yes"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q08",
        instruction="Has this patient had any pregnancy losses?",
        patient_id="bench-sarah-002",
        task_type="query",
        gold_tools={"get_pregnancy_history"},
        gold_answer=["no"],
        gold_not=["recurrent"],
        domain="maternal",
    ),

    # -------------------------------------------------------------------
    # Query tasks — Medications
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q09",
        instruction="List all active medications for this patient.",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_active_medications", "get_patient_summary"},
        gold_answer=["Hydrochlorothiazide", "Metformin"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q10",
        instruction="Is this patient on any antihypertensive medication?",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_active_medications", "get_patient_summary"},
        gold_answer=["Hydrochlorothiazide", "yes"],
        domain="maternal",
    ),

    # -------------------------------------------------------------------
    # Query tasks — Pediatric immunizations
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q11",
        instruction="What immunizations is this 2-month-old due for at today's visit?",
        patient_id="bench-baby-santos-001",
        task_type="query",
        gold_tools={"get_immunization_gaps"},
        gold_answer=["DTaP", "IPV", "PCV13"],
        domain="pediatric",
    ),
    MedAgentCase(
        id="ma_q12",
        instruction="Is this child up to date on HepB?",
        patient_id="bench-baby-santos-001",
        task_type="query",
        gold_tools={"get_immunization_gaps"},
        gold_answer=["HepB"],
        domain="pediatric",
    ),
    MedAgentCase(
        id="ma_q13",
        instruction="How many immunizations does this 5-year-old have overdue?",
        patient_id="bench-child-smith-003",
        task_type="query",
        gold_tools={"get_immunization_gaps"},
        gold_answer=["overdue", "MMR"],
        domain="pediatric",
    ),
    MedAgentCase(
        id="ma_q14",
        instruction="What developmental screening is this 18-month-old missing?",
        patient_id="bench-toddler-jones-002",
        task_type="query",
        gold_tools={"get_developmental_screening_status"},
        gold_answer=["autism", "M-CHAT"],
        domain="pediatric",
    ),

    # -------------------------------------------------------------------
    # Query tasks — SDOH
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q15",
        instruction="What is this patient's primary language, and do they need an interpreter?",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_sdoh_screening", "get_patient_summary"},
        gold_answer=["French", "interpreter"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_q16",
        instruction="Does this patient have active insurance coverage?",
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_sdoh_screening"},
        gold_answer=["no", "uninsured"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_q17",
        instruction="Does this patient have any SDOH conditions documented?",
        patient_id="bench-fatima-005",
        task_type="query",
        gold_tools={"get_sdoh_screening"},
        gold_answer=["unemployed", "food"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_q18",
        instruction="Is this patient insured through Medicaid?",
        patient_id="bench-fatima-005",
        task_type="query",
        gold_tools={"get_sdoh_screening"},
        gold_answer=["Medicaid"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_q19",
        instruction="Screen this patient for SDOH risk factors.",
        patient_id="bench-james-004",
        task_type="query",
        gold_tools={"get_sdoh_screening"},
        gold_answer=["English"],
        gold_not=["uninsured", "interpreter"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_q23",
        instruction=(
            "This patient has a documented housing problem. "
            "Find local community resources that can help with housing assistance."
        ),
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"find_sdoh_resources"},
        gold_answer=["housing", "211"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_q24",
        instruction=(
            "This patient is experiencing food insecurity. "
            "What community food assistance programs are available?"
        ),
        patient_id="bench-fatima-005",
        task_type="query",
        gold_tools={"find_sdoh_resources"},
        gold_answer=["food", "SNAP"],
        domain="sdoh",
    ),

    # -------------------------------------------------------------------
    # Compound reasoning — require multiple tools
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q20",
        instruction=(
            "Perform a comprehensive maternal risk assessment for this patient — "
            "consider BP, glucose, pregnancy history, and current medications."
        ),
        patient_id="bench-maria-001",
        task_type="query",
        gold_tools={"get_maternal_risk_profile"},
        gold_answer=["URGENT", "hypertension", "diabetes"],
        gold_not=["I prescribe"],
        domain="compound",
    ),
    MedAgentCase(
        id="ma_q21",
        instruction=(
            "This pregnant patient reports headaches and visual changes. "
            "Review her BP trend and assess preeclampsia risk."
        ),
        patient_id="bench-elena-003",
        task_type="query",
        gold_tools={"get_bp_trend"},
        gold_answer=["Stage 2", "184"],
        gold_not=["ROUTINE"],
        domain="compound",
    ),
    MedAgentCase(
        id="ma_q22",
        instruction=(
            "This 2-month-old's mother has Type 2 diabetes and Stage 2 hypertension. "
            "What additional screening or monitoring does the infant need beyond "
            "routine immunizations?"
        ),
        patient_id="bench-baby-santos-001",
        task_type="query",
        gold_tools={"get_immunization_gaps"},
        gold_answer=["glucose", "hypoglycemia"],  # should mention maternal DM2 context
        domain="compound",
    ),

    # -------------------------------------------------------------------
    # Action tasks — write-back to FHIR
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_a01",
        instruction=(
            "After reviewing this patient's data, create a FHIR RiskAssessment "
            "documenting the hypertensive crisis risk. Include evidence basis "
            "and recommended mitigation."
        ),
        patient_id="bench-maria-001",
        task_type="action",
        gold_tools={"write_risk_assessment"},
        gold_answer=["RiskAssessment", "hypertensi"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_a02",
        instruction=(
            "Create a CommunicationRequest to schedule a French-language "
            "postpartum follow-up call for this patient."
        ),
        patient_id="bench-maria-001",
        task_type="action",
        gold_tools={"create_communication_request"},
        gold_answer=["CommunicationRequest", "French"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_a03",
        instruction=(
            "Create a CommunicationRequest to contact this family about the "
            "overdue childhood immunizations."
        ),
        patient_id="bench-child-smith-003",
        task_type="action",
        gold_tools={"create_communication_request"},
        gold_answer=["CommunicationRequest", "immuniz"],
        domain="pediatric",
    ),
    MedAgentCase(
        id="ma_a04",
        instruction=(
            "This patient has food insecurity. Find relevant community resources "
            "and create a FHIR CarePlan linking to a food assistance program."
        ),
        patient_id="bench-fatima-005",
        task_type="action",
        gold_tools={"find_sdoh_resources", "write_care_plan"},
        gold_answer=["CarePlan", "Goal", "food"],
        gold_not=["I prescribe"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_a05",
        instruction=(
            "Screen this patient for SDOH issues, find resources for any "
            "identified needs, and document a care plan for her housing problem."
        ),
        patient_id="bench-maria-001",
        task_type="action",
        gold_tools={"get_sdoh_screening", "find_sdoh_resources", "write_care_plan"},
        gold_answer=["CarePlan", "housing"],
        gold_not=["I prescribe"],
        domain="compound",
    ),

    # -------------------------------------------------------------------
    # Query tasks — Priya Sharma (GDM + Stage 1 HTN)
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q25",
        instruction="What is this patient's latest HbA1c and is gestational diabetes controlled?",
        patient_id="bench-priya-006",
        task_type="query",
        gold_tools={"get_glucose_trend"},
        gold_answer=["6.8", "diabet"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q26",
        instruction="Review this patient's blood pressure trend. Any hypertension concerns?",
        patient_id="bench-priya-006",
        task_type="query",
        gold_tools={"get_bp_trend"},
        gold_answer=["142", "elevated"],
        gold_not=["Stage 2"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q27",
        instruction="List all active medications for this patient with gestational diabetes.",
        patient_id="bench-priya-006",
        task_type="query",
        gold_tools={"get_active_medications", "get_patient_summary"},
        gold_answer=["Glyburide", "Prenatal"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q28",
        instruction=(
            "Perform a comprehensive maternal risk assessment for this patient. "
            "She has gestational diabetes and borderline hypertension."
        ),
        patient_id="bench-priya-006",
        task_type="query",
        gold_tools={"get_maternal_risk_profile"},
        gold_answer=["HIGH", "Elevated BP"],
        gold_not=["URGENT", "I prescribe"],
        domain="compound",
    ),

    # -------------------------------------------------------------------
    # Query tasks — Destiny Williams (19yo, SDOH)
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q29",
        instruction="Screen this 19-year-old pregnant patient for social determinants of health.",
        patient_id="bench-destiny-007",
        task_type="query",
        gold_tools={"get_sdoh_screening"},
        gold_answer=["Stress", "Medicaid"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_q30",
        instruction="Does this patient have any prior pregnancies or pregnancy losses on record?",
        patient_id="bench-destiny-007",
        task_type="query",
        gold_tools={"get_pregnancy_history"},
        gold_answer=["1"],
        gold_not=["recurrent", "loss"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_q31",
        instruction=(
            "This patient is experiencing stress and social isolation. "
            "What community support resources are available?"
        ),
        patient_id="bench-destiny-007",
        task_type="query",
        gold_tools={"find_sdoh_resources"},
        gold_answer=["211"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_q32",
        instruction=(
            "Assess this 19-year-old's maternal risk profile. "
            "Is her pregnancy medically high risk?"
        ),
        patient_id="bench-destiny-007",
        task_type="query",
        gold_tools={"get_maternal_risk_profile"},
        gold_answer=["ROUTINE"],
        gold_not=["URGENT", "HIGH", "Stage 2"],
        domain="compound",
    ),

    # -------------------------------------------------------------------
    # Query tasks — Baby Williams (7mo, missed 4-month visit)
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_q33",
        instruction=(
            "This 7-month-old missed her 4-month well-child visit. "
            "What immunizations is she overdue for?"
        ),
        patient_id="bench-baby-williams-004",
        task_type="query",
        gold_tools={"get_immunization_gaps"},
        gold_answer=["DTaP", "overdue"],
        domain="pediatric",
    ),
    MedAgentCase(
        id="ma_q34",
        instruction="Check developmental screening status for this 7-month-old infant.",
        patient_id="bench-baby-williams-004",
        task_type="query",
        gold_tools={"get_developmental_screening_status"},
        gold_answer=["surveillance"],
        domain="pediatric",
    ),

    # -------------------------------------------------------------------
    # Action tasks — new patients
    # -------------------------------------------------------------------
    MedAgentCase(
        id="ma_a06",
        instruction=(
            "Create a FHIR RiskAssessment for this patient documenting "
            "the gestational diabetes and elevated blood pressure risk. "
            "Include evidence basis."
        ),
        patient_id="bench-priya-006",
        task_type="action",
        gold_tools={"write_risk_assessment"},
        gold_answer=["RiskAssessment", "diabet"],
        gold_not=["I prescribe"],
        domain="maternal",
    ),
    MedAgentCase(
        id="ma_a07",
        instruction=(
            "This young patient has stress and social isolation. "
            "Find support resources and create a FHIR CarePlan to "
            "connect her with community services."
        ),
        patient_id="bench-destiny-007",
        task_type="action",
        gold_tools={"find_sdoh_resources", "write_care_plan"},
        gold_answer=["CarePlan", "Goal"],
        gold_not=["I prescribe"],
        domain="sdoh",
    ),
    MedAgentCase(
        id="ma_a08",
        instruction=(
            "Create a CommunicationRequest to schedule a catch-up "
            "immunization visit for this 7-month-old who missed her "
            "4-month vaccines."
        ),
        patient_id="bench-baby-williams-004",
        task_type="action",
        gold_tools={"create_communication_request"},
        gold_answer=["CommunicationRequest", "immuniz"],
        domain="pediatric",
    ),
]
