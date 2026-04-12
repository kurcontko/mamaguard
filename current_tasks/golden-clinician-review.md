# Task: Golden-file tests for liaison `clinician_review` output shape

**Claimed:** 2026-04-12T01:13:48Z
**Branch:** `feat/golden-clinician-review`
**Worktree:** `/workspace/golden-clinician-review-worktree`
**Source task:** TASK.md Phase 3 — "Golden-file tests for liaison `clinician_review` output shape on every tool (prevent contract drift)."

## Scope

Pin each liaison-returning FHIR tool's `clinician_review` dict against a committed JSON fixture so wording/evidence drift is caught in CI. This is distinct from the existing shape-only assertions in `test_agents_in_process.py` — those check *types and keys*, goldens pin *values*.

## Files to touch

- `mamaguard/tests/test_clinician_review_golden.py` (new test module)
- `mamaguard/tests/fixtures/clinician_review/*.json` (new fixture directory — one file per tool/case)

## Tools covered (9 read tools)

- maternal: `get_bp_trend`, `get_glucose_trend`, `get_pregnancy_history`, `get_maternal_risk_profile`
- pediatric: `get_immunization_gaps`, `get_developmental_screening_status`, `get_care_gaps`
- sdoh: `get_sdoh_screening`, `find_sdoh_resources`

Writeback tools do not emit `clinician_review` (verified via grep) and are out of scope.

## Approach

1. Per tool, define one deterministic mocked FHIR fixture that produces a stable `clinician_review` block.
2. Invoke the tool with mocked `_fhir_get` (or `_fetch_external_resources` for `find_sdoh_resources`).
3. Compare `result["clinician_review"]` to the committed golden JSON using `assertEqual`.
4. Refresh workflow via `UPDATE_GOLDENS=1 python -m unittest mamaguard.tests.test_clinician_review_golden` (writes goldens to disk); documented at top of the test module.

## Definition of done

- New test module + fixture JSON files committed.
- All 9 read tools pinned; each golden has `required`, `reason`, `evidence_basis`.
- `python -m unittest` green (all 100+ existing tests still pass).
- Tier-1 benchmark score unchanged.
- PROGRESS.md updated.
