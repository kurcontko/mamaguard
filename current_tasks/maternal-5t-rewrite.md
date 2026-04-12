# Task: Rewrite maternal agent to 5T format

- **Claimed:** 2026-04-12
- **Branch:** feat/maternal-5t
- **Worktree:** /workspace/maternal-5t
- **Files:**
  - mamaguard/maternal_agent/agent.py (MATERNAL_INSTRUCTION rewrite)

## Scope
- Replace ad-hoc 5-section output format with explicit 5T (Talk/Template/Table/Task/Transaction)
- Add tool usage guidance (start with get_maternal_risk_profile, call write_risk_assessment when HIGH/URGENT)
- Add pregnancy status detection logic
- Keep Liaison Pattern unchanged
- Must pass: make test && make tier1
