# Expand test_pediatric.py and test_sdoh.py coverage

**Claimed:** 2026-04-12
**Branch:** feat/pediatric-sdoh-test-expansion
**Worktree:** /workspace/pediatric-sdoh-test-expansion-worktree

## Scope

Close the Code-hygiene item "Fill in `test_pediatric.py` and `test_sdoh.py` (currently placeholders)" from TASK.md. Both files have basic happy-path coverage; fill in error paths, edge cases, and under-tested branches.

### Files to touch

- `mamaguard/tests/test_pediatric.py` — add edge/error-path tests
- `mamaguard/tests/test_sdoh.py` — add edge/error-path tests for `get_sdoh_screening`

### Coverage targets

**pediatric.py:**
- `_compute_age_months`: None / empty / malformed / valid
- `get_immunization_gaps`: up-to-date (no gaps), missing/invalid birthDate, HTTPStatusError on patient fetch, ConnectError on immunization fetch, missing context
- `get_developmental_screening_status`: age > 36 months (review not required), missing birthDate, observation-fetch exception → empty bundle path, all-completed case
- `get_care_gaps`: goal-without-description gap detected, CarePlan fetch exception, missing context

**sdoh.py `get_sdoh_screening`:**
- Housing Z-code condition flagged as SDOH
- Patient fetch HTTPStatusError
- Coverage fetch ConnectError
- Missing FHIR context → error shape

## Non-goals

- No source changes — tests only
- No new tools
- Skip `find_sdoh_resources` and `write_care_plan` (already well-covered)
