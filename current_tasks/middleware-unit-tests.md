# Claim: ApiKeyMiddleware unit tests

- **Agent:** opus-4.6
- **Started:** 2026-04-12
- **Branch:** feat/middleware-tests
- **Worktree:** /workspace/middleware-tests-worktree
- **Scope:** `mamaguard/tests/test_middleware.py` (new) — unit tests for `mamaguard/shared/middleware.py` `ApiKeyMiddleware`:
  - public `/.well-known/agent-card.json` bypass
  - 401 on missing X-API-Key
  - 403 on invalid X-API-Key
  - 200 on valid X-API-Key
  - FHIR metadata bridged from `params.message.metadata` → `params.metadata` when empty
  - existing `params.metadata` not overwritten
  - non-JSON / empty / missing-params body handled without crash
- **Files touched:** only the new test file. No source changes expected.
- **Why:** Middleware is the only path between Prompt Opinion traffic and the ADK agent; FHIR bridging is covered transitively via in-process tests but the HTTP middleware layer itself has zero direct coverage.
