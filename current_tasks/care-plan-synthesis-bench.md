# Task: Wire care plan synthesis checkers into Tier-1 benchmark suite

**Claimed:** 2026-04-12
**Branch:** feat/care-plan-synthesis-bench
**Worktree:** /workspace/worktrees/care-plan-synthesis-bench

## Files to touch
- benchmarks/clinical_reasoning/bench_care_plan_synthesis.py (NEW)
- benchmarks/runner.py (add import + register suite)

## Scope
Create Tier-1 deterministic benchmark suite exercising judge.py's care plan synthesis
checkers (faithfulness, completeness, safety_flags, combined score) against realistic
responses derived from the Maria compound case fixture. Wire into runner.py.
