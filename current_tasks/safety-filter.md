# Task: Post-processing safety validation layer

**Claimed**: 2026-04-12
**Branch**: feat/safety-filter
**Worktree**: /workspace/repo-safety-filter

## Files to touch
- `mamaguard/shared/safety_filter.py` (NEW) — after_model_callback with prescribing language detection/redaction
- `mamaguard/orchestrator/agent.py` — wire after_model_callback
- `mamaguard/maternal_agent/agent.py` — wire after_model_callback
- `mamaguard/pediatric_agent/agent.py` — wire after_model_callback
- `mamaguard/sdoh_agent/agent.py` — wire after_model_callback
- `mamaguard/tests/test_safety_filter.py` (NEW) — unit tests
- `mamaguard/tests/test_agents_in_process.py` — verify callback wired

## Rationale
Safety report S-2 (HIGH severity): prescribing language in agent responses despite liaison pattern instructions.
Prompt hardening alone is partially effective (elena_preeclampsia: 0/3 pass rate).
Safety report conclusion recommends "post-processing validation layer to catch prescribing language."
