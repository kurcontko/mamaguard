# Task: Fix CI Tier-2 HAPI bundle loading bug

**Claimed:** 2026-04-12
**Branch:** feat/fix-ci-hapi-bundle-loading
**Worktree:** /workspace/worktrees/fix-ci-hapi-bundle-loading

## Files to touch
- .github/workflows/ci.yml (fix bundle loading step)

## Scope
The CI "Load FHIR bundles into HAPI" step globs for *.json files but all FHIR
bundles are Python modules. Zero data is loaded, making Tier-2 e2e tests run
against an empty HAPI server. Fix the loading step to use the Python bundle
module (`benchmarks.e2e.fhir_bundles.ALL_PATIENTS`).
