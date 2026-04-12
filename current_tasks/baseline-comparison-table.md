# Task: Baseline comparison table (Phase 3 — AI Factor judging evidence)

- **Started:** 2026-04-12
- **Branch:** `feat/baseline-comparison-table`
- **Worktree:** `/workspace/baseline-comparison-table-worktree`

## Scope

Extend the single-case reasoning-trace benchmark (Phase 2d) into a multi-case
baseline comparison. For each case, run the rule-engine baseline and the
MamaGuard synthesis against the same mocked FHIR fixtures and emit a
side-by-side comparison table capturing:

- flag/factor count (baseline vs. synthesis)
- risk level produced
- evidence refs cited
- cross-factor insights surfaced
- AI-Factor affordance count

Generate a committed markdown artifact (`benchmarks/fixtures/baseline_comparison_table.md`)
plus a committed JSON fixture (`benchmarks/fixtures/baseline_comparison_table.json`)
so the comparison can be cited verbatim in judging materials. Pin the fixture
against live synthesis via a Tier-1 benchmark case (same drift-surfacing pattern
as `reasoning_trace_fixture_current`).

## Files to touch

- `benchmarks/clinical_reasoning/bench_baseline_comparison.py` — new (mild/moderate/severe cases + table generator)
- `benchmarks/fixtures/baseline_comparison_table.json` — new
- `benchmarks/fixtures/baseline_comparison_table.md` — new
- `benchmarks/runner.py` — classifier already has `clinical_reasoning` category, verify new suite rolls in (edit only if needed)
- `PROGRESS.md` — append Completed bullet
