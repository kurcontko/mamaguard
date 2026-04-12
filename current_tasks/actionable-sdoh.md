# Phase 2c — Actionable SDOH

**Claimed:** 2026-04-12
**Branch:** feat/actionable-sdoh
**Worktree:** /workspace/actionable-sdoh-worktree

## Scope (files I will touch)

- `mamaguard/shared/tools/sdoh.py` — add `find_sdoh_resources(category, zip_code)` with pluggable external lookup + curated offline fallback
- `mamaguard/shared/sdoh_resources.py` — new curated offline resource map (housing, food, transport, medicaid, interpreter, perinatal)
- `mamaguard/shared/tools/writeback.py` — add `write_care_plan(category, goal_description, resource_name, resource_contact, z_code?)` creating FHIR Goal + CarePlan
- `mamaguard/shared/tools/__init__.py` — re-export new tools
- `mamaguard/sdoh_agent/agent.py` — register new tools on the SDOH agent
- `mamaguard/mcp_server/server.py` — expose `find_sdoh_resources` + `write_care_plan` as MCP tools
- `mamaguard/tests/test_sdoh.py` — Z59.0 + ZIP → non-empty list; external API down → fallback
- `mamaguard/tests/test_writeback.py` — write_care_plan happy path + rejection

## Definition of done

- Z59.0 (housing) + ZIP → non-empty resource list → CarePlan POST assertion (tests green)
- Graceful degradation when external API is down (fall back to offline curated list)
- `python -m unittest discover mamaguard/tests` all green
- Tier-1 benchmarks still pass `scripts/pre_deploy_check.sh`
- PROGRESS.md updated, merged to main
