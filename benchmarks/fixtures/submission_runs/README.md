# Submission benchmark runs

Durable Tier-2b results on the v3 architecture branch.

## Run log

| Date (UTC) | Branch / Commit | Backend | Overall | Pass/Total | Notes |
|---|---|---|---|---|---|
| 2026-04-15 | main (v1, post-task-57) | Nemotron-120B | 88.3% | n/a | 8h20m, reference baseline for v1 |
| 2026-04-16 | architecture-v3 / `aa434f4` | Gemma-26B-A4B | 90.0% | 44/47 | Phase 2+4 committed |
| 2026-04-17 | feat/hackathon-top3-push (full) | Gemma-26B-A4B | 88.6% | 40/47 | Task #2 wiring regressed 5 cases; reverted |
| **2026-04-17** | **feat/hackathon-top3-push / `73a7986`** | **Gemma-26B-A4B** | **93.1%** | **45/47** | **New high after Task #8 revert** |

## 93.1% run details

- Commit: `73a7986` (Task #8 revert landed).
- Log: `tier2b_gemma_v3top3_revert_20260417T103657Z.log`
- Case summary: `tier2b_gemma_top3_93.1pct_summary.txt`
- Judge: DeepSeek v3.2 via OpenRouter
- 2 remaining failures (both persistent from baseline, marginal improvement):
  - `e2e_child_smith_catchup` 54% — 5-yo catch-up, missing MMR/Varicella keywords in agent output despite tool correctly flagging them.
  - `e2e_handoff_pediatric_phase` 57% — newborn case, missing DTaP/PCV13 keywords.
- 1 recovered pass from baseline:
  - `e2e_diverse_grandmother_peds` 67% FAIL → 75% PASS (adult short-circuit in Task #1).

Both remaining failures are pure output-shaping (the tool returns correct
structured data; the agent text doesn't surface the specific series names).
A deeper fix would require forcing the agent to enumerate `overdue[*].vaccine`
verbatim in the Table. Out of scope for this run but noted for a follow-up.
