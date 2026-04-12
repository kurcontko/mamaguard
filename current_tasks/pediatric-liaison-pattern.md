---
task: Add Liaison Pattern safety language to pediatric agent instruction
timestamp: 2026-04-12
branch: feat/pediatric-liaison-pattern
worktree: /workspace/pediatric-liaison-worktree
files:
  - mamaguard/pediatric_agent/agent.py
---

The pediatric agent instruction is missing the Liaison Pattern (no-autonomy) safety language
that the maternal and SDOH agents have. The `safety_liaison_pattern_enforced` benchmark
scores 83.3% (5/6) because `pediatric_no_autonomy` is false. Fix: add Liaison Pattern
section to PEDIATRIC_INSTRUCTION.
