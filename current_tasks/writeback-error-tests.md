# Error-path tests for FHIR writeback

**Claimed:** 2026-04-12
**Branch:** feat/writeback-error-tests
**Worktree:** /workspace/writeback-error-tests-worktree

## Scope (from TASK.md — Code hygiene)

Error-path tests for FHIR writeback (`test_writeback.py`): 4xx/5xx responses, network errors.

Existing tests cover only 403/405 status codes. Missing coverage:
- Other 4xx (400/422) and 5xx (500) HTTP rejections.
- The `except Exception` branch that catches `httpx.ConnectError` / `httpx.ReadTimeout` — currently zero coverage across all three write tools.
- `create_communication_request`: no missing-context test.

## Files touched

- `mamaguard/tests/test_writeback.py` — add error-path tests only. No source changes.

## DoD

- New tests exercise 4xx-other, 5xx, and network-error branches for each of `write_risk_assessment`, `create_communication_request`, `write_care_plan` (Goal + CarePlan branches).
- `create_communication_request` missing-context test added.
- `python -m unittest mamaguard.tests.test_writeback -v` green.
- Full unit-test suite still green (88+ → new count).
- Tier-1 benchmarks still pass (no source changed, so this is a sanity check).
