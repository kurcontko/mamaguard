"""
LLM eval: Agent routing accuracy.

Tests whether the model correctly identifies which sub-agent to invoke
given different clinical queries.
"""

from benchmarks.base import BenchmarkResult, BenchmarkSuite, Verdict
from benchmarks.llm_eval.client import LLMConfig, chat_completion
from benchmarks.llm_eval.judge import check_contains_any
from benchmarks.llm_eval.scenarios import ROUTING_SCENARIOS

suite = BenchmarkSuite(
    name="llm_routing",
    description="LLM agent routing accuracy — does the model pick the right sub-agent?",
)


def _eval_routing(scenario, config: LLMConfig) -> BenchmarkResult:
    messages = [
        {"role": "system", "content": scenario.system_prompt},
        {"role": "user", "content": scenario.user_message},
    ]

    resp = chat_completion(messages=messages, config=config)
    content = resp.content.lower()

    expected_agent = scenario.expected["agent"]

    if expected_agent == "all":
        # Should mention all three agents
        checks = {
            "mentions_maternal": check_contains_any(content, ["maternal_risk_agent", "maternal"]),
            "mentions_pediatric": check_contains_any(content, ["pediatric_transition_agent", "pediatric"]),
            "mentions_sdoh": check_contains_any(content, ["sdoh_outreach_agent", "sdoh", "social"]),
        }
        score = sum(checks.values()) / len(checks)
        verdict = Verdict.PASS if score >= 0.66 else Verdict.FAIL
    else:
        # Should mention the correct agent
        agent_keywords = {
            "maternal_risk_agent": ["maternal_risk_agent", "maternal"],
            "pediatric_transition_agent": ["pediatric_transition_agent", "pediatric"],
            "sdoh_outreach_agent": ["sdoh_outreach_agent", "sdoh"],
        }
        correct_kws = agent_keywords.get(expected_agent, [expected_agent])
        wrong_agents = [k for k in agent_keywords if k != expected_agent]
        wrong_kws = []
        for wa in wrong_agents:
            wrong_kws.extend(agent_keywords[wa])

        correct = check_contains_any(content, correct_kws)
        # Only penalize if ONLY the wrong agent is mentioned (not if both appear)
        wrong_only = check_contains_any(content, wrong_kws) and not correct

        checks = {
            "correct_agent": correct,
            "no_wrong_agent_only": not wrong_only,
        }
        score = 1.0 if correct else 0.0
        verdict = Verdict.PASS if correct else Verdict.FAIL

    return BenchmarkResult(
        name=scenario.id,
        verdict=verdict,
        score=score,
        elapsed_ms=resp.elapsed_ms,
        details={
            **checks,
            "response_preview": resp.content[:300],
            "prompt_tokens": resp.prompt_tokens,
            "completion_tokens": resp.completion_tokens,
        },
    )


def build_suite(config: LLMConfig) -> BenchmarkSuite:
    """Build routing eval suite with the given LLM config."""
    s = BenchmarkSuite(
        name="llm_routing",
        description="LLM agent routing accuracy",
    )
    for scenario in ROUTING_SCENARIOS:
        # Capture scenario in closure
        def make_fn(sc):
            return lambda: _eval_routing(sc, config)
        s.add(
            __import__("benchmarks.base", fromlist=["BenchmarkCase"]).BenchmarkCase(
                name=scenario.id,
                description=scenario.name,
                category="routing",
                fn=make_fn(scenario),
            )
        )
    return s
