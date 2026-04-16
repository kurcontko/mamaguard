"""
Agent orchestration benchmarks — MedAgentBench inspired.

Tests correct agent routing, tool selection, and multi-agent workflow
by validating the orchestrator's routing rules and agent configurations.
"""

from benchmarks.base import BenchmarkResult, BenchmarkSuite, Verdict

suite = BenchmarkSuite(
    name="orchestration",
    description="Agent orchestration — routing, tool assignment, agent config",
)


# -- Agent Configuration Validation -------------------------------------------

@suite.case("agent_config_orchestrator", "Orchestrator has all 3 sub-agents wired", "orchestration")
def bench_orchestrator_config():
    from mamaguard.orchestrator.agent import root_agent

    tool_names = [t.agent.name if hasattr(t, 'agent') else str(t) for t in root_agent.tools]
    checks = {
        "has_maternal": "maternal_risk_agent" in tool_names,
        "has_pediatric": "pediatric_transition_agent" in tool_names,
        "has_sdoh": "sdoh_outreach_agent" in tool_names,
        "has_fhir_hook": root_agent.before_model_callback is not None,
        "model_set": root_agent.model is not None and root_agent.model != "",
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="agent_config_orchestrator",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details={**checks, "tool_names": tool_names},
    )


@suite.case("agent_config_maternal_tools", "Maternal agent has correct tool set", "orchestration")
def bench_maternal_tools():
    from mamaguard.maternal_agent.agent import maternal_risk_agent

    tool_names = [t.__name__ if callable(t) else str(t) for t in maternal_risk_agent.tools]
    required_tools = [
        "get_maternal_risk_profile",
        "get_bp_trend",
        "get_glucose_trend",
        "get_pregnancy_history",
        "get_patient_summary",
        "write_risk_assessment",
    ]
    checks = {}
    for tool in required_tools:
        checks[f"has_{tool}"] = tool in tool_names
    checks["has_fhir_hook"] = maternal_risk_agent.before_model_callback is not None

    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="agent_config_maternal_tools",
        verdict=Verdict.PASS if score >= 0.85 else Verdict.FAIL,
        score=score,
        details={**checks, "actual_tools": tool_names},
    )


@suite.case("agent_config_pediatric_tools", "Pediatric agent has correct tool set", "orchestration")
def bench_pediatric_tools():
    from mamaguard.pediatric_agent.agent import pediatric_transition_agent

    tool_names = [t.__name__ if callable(t) else str(t) for t in pediatric_transition_agent.tools]
    required_tools = [
        "get_immunization_gaps",
        "get_developmental_screening_status",
        "get_care_gaps",
        "get_patient_summary",
    ]
    checks = {}
    for tool in required_tools:
        checks[f"has_{tool}"] = tool in tool_names
    checks["has_fhir_hook"] = pediatric_transition_agent.before_model_callback is not None

    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="agent_config_pediatric_tools",
        verdict=Verdict.PASS if score >= 0.85 else Verdict.FAIL,
        score=score,
        details={**checks, "actual_tools": tool_names},
    )


@suite.case("agent_config_sdoh_tools", "SDOH agent has correct tool set", "orchestration")
def bench_sdoh_tools():
    from mamaguard.sdoh_agent.agent import sdoh_outreach_agent

    tool_names = [t.__name__ if callable(t) else str(t) for t in sdoh_outreach_agent.tools]
    required_tools = [
        "get_sdoh_screening",
        "get_patient_summary",
        "create_communication_request",
    ]
    checks = {}
    for tool in required_tools:
        checks[f"has_{tool}"] = tool in tool_names
    checks["has_fhir_hook"] = sdoh_outreach_agent.before_model_callback is not None

    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="agent_config_sdoh_tools",
        verdict=Verdict.PASS if score >= 0.85 else Verdict.FAIL,
        score=score,
        details={**checks, "actual_tools": tool_names},
    )


# -- Routing Rule Validation ---------------------------------------------------

@suite.case("routing_rules_in_instruction", "Orchestrator instruction contains routing rules", "orchestration")
def bench_routing_rules():
    from mamaguard.orchestrator.agent import ORCHESTRATOR_INSTRUCTION

    instruction = ORCHESTRATOR_INSTRUCTION.lower()
    checks = {
        "maternal_routing": "maternal" in instruction and "maternal_risk_agent" in instruction,
        "pediatric_routing": "pediatric" in instruction and "pediatric_transition_agent" in instruction,
        "sdoh_routing": "sdoh" in instruction and "sdoh_outreach_agent" in instruction,
        "comprehensive_routing": "comprehensive" in instruction or "all three" in instruction,
        "5t_framework": "5t" in instruction or ("talk" in instruction and "template" in instruction),
        "liaison_pattern": "liaison" in instruction or "clinician review" in instruction,
        "no_fabrication_rule": "never fabricate" in instruction or "do not fabricate" in instruction,
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="routing_rules_in_instruction",
        verdict=Verdict.PASS if score >= 0.85 else Verdict.FAIL,
        score=score,
        details=checks,
    )


# -- Safety Invariant Checks ---------------------------------------------------

@suite.case("safety_all_agents_have_fhir_hook", "All agents use FHIR context hook", "orchestration")
def bench_safety_fhir_hooks():
    from mamaguard.orchestrator.agent import root_agent
    from mamaguard.maternal_agent.agent import maternal_risk_agent
    from mamaguard.pediatric_agent.agent import pediatric_transition_agent
    from mamaguard.sdoh_agent.agent import sdoh_outreach_agent
    from mamaguard.shared.fhir_hook import extract_fhir_context

    def _has_hook(cb):
        if cb is extract_fhir_context:
            return True
        if isinstance(cb, list) and extract_fhir_context in cb:
            return True
        return False

    checks = {
        "orchestrator_hook": _has_hook(root_agent.before_model_callback),
        "maternal_hook": _has_hook(maternal_risk_agent.before_model_callback),
        "pediatric_hook": _has_hook(pediatric_transition_agent.before_model_callback),
        "sdoh_hook": _has_hook(sdoh_outreach_agent.before_model_callback),
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="safety_all_agents_have_fhir_hook",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


@suite.case("safety_liaison_pattern_enforced", "All sub-agents enforce clinician review pattern", "orchestration")
def bench_safety_liaison():
    from mamaguard.maternal_agent.agent import MATERNAL_INSTRUCTION
    from mamaguard.pediatric_agent.agent import PEDIATRIC_INSTRUCTION
    from mamaguard.sdoh_agent.agent import SDOH_INSTRUCTION

    checks = {}
    for name, instruction in [
        ("maternal", MATERNAL_INSTRUCTION),
        ("pediatric", PEDIATRIC_INSTRUCTION),
        ("sdoh", SDOH_INSTRUCTION),
    ]:
        lower = instruction.lower()
        checks[f"{name}_clinician_review"] = "clinician review" in lower
        checks[f"{name}_no_autonomy"] = "never recommend treatment" in lower

    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="safety_liaison_pattern_enforced",
        verdict=Verdict.PASS if score >= 0.8 else Verdict.FAIL,
        score=score,
        details=checks,
    )


# -- Write-back Tool Validation ------------------------------------------------

@suite.case("writeback_only_maternal_has_risk_assessment", "Only maternal agent can write RiskAssessment", "orchestration")
def bench_writeback_risk_assessment():
    from mamaguard.maternal_agent.agent import maternal_risk_agent
    from mamaguard.pediatric_agent.agent import pediatric_transition_agent
    from mamaguard.sdoh_agent.agent import sdoh_outreach_agent

    def has_tool(agent, tool_name):
        return any(
            (t.__name__ if callable(t) else str(t)) == tool_name
            for t in agent.tools
        )

    checks = {
        "maternal_has_write_risk": has_tool(maternal_risk_agent, "write_risk_assessment"),
        "pediatric_no_write_risk": not has_tool(pediatric_transition_agent, "write_risk_assessment"),
        "sdoh_no_write_risk": not has_tool(sdoh_outreach_agent, "write_risk_assessment"),
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="writeback_only_maternal_has_risk_assessment",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )


# -- JSON Output Mode Validation ---------------------------------------------

@suite.case("json_output_mode_converts_5t", "JSON formatter produces valid structured output from 5T markdown", "orchestration")
def bench_json_output_mode():
    import json
    from mamaguard.shared.json_formatter import markdown_to_json

    sample = (
        "**Talk** — Maria presents with Stage 2 hypertension.\n\n"
        "**Template** — Combined Risk Level: URGENT\n"
        "BP 162/104 (Observation/bp-m5), HbA1c 7.2% (Observation/hba1c-m1).\n\n"
        "**Table**\n"
        "| Metric | Value | Date | Source |\n"
        "|--------|-------|------|--------|\n"
        "| BP | 162/104 | 2026-03-20 | Observation/bp-m5 |\n\n"
        "**Task**\n"
        "1. URGENT — Clinician review of BP trend | Clinician | Within 24h\n"
        "2. HIGH — Repeat HbA1c | Lab | 3 months\n\n"
        "**Transaction** — RiskAssessment/ra-001 (maternal_risk_agent). "
        "CarePlan/cp-001 (sdoh_outreach_agent).\n\n"
        "AI-generated analysis of synthetic data. Not for clinical use."
    )

    result = markdown_to_json(sample)

    checks = {
        "valid_json": True,
        "has_risk_level": result.get("risk_level") == "URGENT",
        "has_talk": bool(result.get("talk")),
        "has_findings": len(result.get("findings", [])) > 0,
        "has_tasks": len(result.get("tasks", [])) > 0,
        "tasks_have_priority": all("priority" in t for t in result.get("tasks", [])),
        "has_fhir_writes": len(result.get("fhir_writes", [])) > 0,
        "fhir_writes_have_structure": all(
            "resource_type" in w and "reference" in w
            for w in result.get("fhir_writes", [])
        ),
        "has_disclaimer": "Not for clinical use" in result.get("disclaimer", ""),
        "serializable": False,
    }

    try:
        json.loads(json.dumps(result))
        checks["serializable"] = True
    except (TypeError, ValueError):
        pass

    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="json_output_mode_converts_5t",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details={**checks, "result_keys": list(result.keys())},
    )


@suite.case("json_output_mode_callback_wired", "Orchestrator callback chain includes JSON formatter", "orchestration")
def bench_json_callback_wired():
    import inspect
    from mamaguard.orchestrator.agent import _orchestrator_after_model_callback

    source = inspect.getsource(_orchestrator_after_model_callback)
    checks = {
        "has_safety_filter": "safety_after_model_callback" in source,
        "has_response_format": "response_format_callback" in source,
        "has_json_output": "json_output_callback" in source,
        "json_after_format": source.index("json_output_callback") > source.index("response_format_callback"),
    }
    score = sum(checks.values()) / len(checks)
    return BenchmarkResult(
        name="json_output_mode_callback_wired",
        verdict=Verdict.PASS if score == 1.0 else Verdict.FAIL,
        score=score,
        details=checks,
    )
