# Logging utils unit tests

- **Started:** 2026-04-12
- **Branch:** feat/logging-utils-tests
- **Worktree:** /workspace/logging-utils-tests-worktree
- **Task:** Code hygiene — `mamaguard/shared/logging_utils.py` currently has **0 direct tests** (only a glancing docstring mention in `test_agents_in_process.py`). Fill this gap with a focused unit-test file so the utility surface is pinned before wider refactors.

## Scope

Tests only. No source changes to `logging_utils.py`.

### Files to add

- `mamaguard/tests/test_logging_utils.py` — new file

### Functions under test

- `_AnsiColorFormatter.format` — DEBUG/INFO/WARNING/ERROR/CRITICAL colour codes, unknown level fallback, `record.levelname` restored even on exception
- `configure_logging` — first call attaches one handler and sets level/propagate; second call is a no-op (idempotent)
- `safe_pretty_json` — JSON-serialisable value, non-serialisable fallback (uses `default=str`), totally-unserialisable fallback to `str()` via exception path
- `serialize_for_log` — None passthrough, primitive passthrough, dict/list passthrough, Pydantic-like `model_dump(mode="json")` path, `model_dump` without kwargs fallback (`TypeError`), `model_dump` exception fallback to `str()`, arbitrary object fallback to `str()`
- `redact_headers` — sensitive keys redacted (case-insensitive: `X-Api-Key`, `Authorization`, `Cookie`, `Set-Cookie`), non-sensitive preserved, non-dict input passthrough, len annotation in redaction marker
- `token_fingerprint` — empty → `"empty"`, non-empty → `"len=<n> sha256=<12 hex>"` stable for same input

## Out of scope

- `_enable_windows_ansi` — Windows-only, unsafe to exercise under Linux; skip.
