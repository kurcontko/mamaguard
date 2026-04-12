#!/usr/bin/env bash
# pre_deploy_check.sh — gate deploy on green benchmarks
#
# Usage:
#   ./scripts/pre_deploy_check.sh            # Tier-1 only (fast, no Docker)
#   ./scripts/pre_deploy_check.sh --hapi     # Tier-1 + Tier-2 HAPI smoke
#
# Exit codes:
#   0 — all checks green
#   1 — one or more checks failed
#
# Environment variables:
#   HAPI_FHIR_URL      — override HAPI endpoint (default: http://localhost:8090/fhir)
#   NO_FHIR_SETUP      — set to "1" to skip HAPI container lifecycle (assume already running)
#   SKIP_UNIT_TESTS    — set to "1" to skip pytest unit test suite
#   SKIP_MYPY          — set to "1" to skip mypy type check
#   MIN_OVERALL_SCORE  — minimum acceptable overall benchmark score 0–1 (default: 0.95)
#   PYTHON             — Python interpreter to use (default: python3)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# ── Helpers ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

pass()  { echo -e "${GREEN}[PASS]${RESET} $*"; }
fail()  { echo -e "${RED}[FAIL]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET} $*"; }
info()  { echo -e "  [*] $*"; }
hr()    { echo "────────────────────────────────────────────────────────────────"; }

FAILURES=0

# ── Parse args ─────────────────────────────────────────────────────────────────

RUN_HAPI=0
for arg in "$@"; do
    case "$arg" in
        --hapi) RUN_HAPI=1 ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

MIN_OVERALL_SCORE="${MIN_OVERALL_SCORE:-0.95}"
PYTHON="${PYTHON:-python3}"

hr
echo "  MamaGuard Pre-Deploy Check"
info "repo:              ${REPO_ROOT}"
info "python:            $(${PYTHON} --version 2>&1)"
info "min overall score: ${MIN_OVERALL_SCORE}"
info "hapi smoke:        $([ "${RUN_HAPI}" -eq 1 ] && echo 'yes' || echo 'no (pass --hapi to enable)')"
hr
echo

# ── Step 1: Unit tests ─────────────────────────────────────────────────────────

if [ "${SKIP_UNIT_TESTS:-0}" != "1" ]; then
    echo "Step 1/4 — Unit tests (pytest mamaguard/tests/)"
    hr

    UNIT_LOG=$(mktemp)
    ${PYTHON} -m pytest mamaguard/tests/ -q --tb=short 2>&1 | tee "${UNIT_LOG}"
    UNIT_EXIT=${PIPESTATUS[0]}

    if [ "${UNIT_EXIT}" -eq 0 ]; then
        pass "unit-tests"
    else
        fail "unit-tests (exit ${UNIT_EXIT}) — full output above"
        FAILURES=$((FAILURES + 1))
    fi
    echo
else
    warn "Step 1/4 — Unit tests SKIPPED (SKIP_UNIT_TESTS=1)"
    echo
fi

# ── Step 2: mypy type check ──────────────────────────────────────────────────

if [ "${SKIP_MYPY:-0}" != "1" ]; then
    echo "Step 2/4 — mypy type check (mamaguard/ benchmarks/)"
    hr

    MYPY_LOG=$(mktemp)
    ${PYTHON} -m mypy mamaguard/ benchmarks/ 2>&1 | tee "${MYPY_LOG}"
    MYPY_EXIT=${PIPESTATUS[0]}

    if [ "${MYPY_EXIT}" -eq 0 ]; then
        pass "mypy"
    else
        fail "mypy (exit ${MYPY_EXIT}) — full output above"
        FAILURES=$((FAILURES + 1))
    fi
    echo
else
    warn "Step 2/4 — mypy type check SKIPPED (SKIP_MYPY=1)"
    echo
fi

# ── Step 3: Tier-1 deterministic benchmarks ───────────────────────────────────

echo "Step 3/4 — Tier-1 deterministic benchmarks"
hr

BENCH_JSON=$(mktemp)
BENCH_LOG=$(mktemp)

# Capture stdout (JSON) and stderr (logging) separately
${PYTHON} -m benchmarks.runner --json > "${BENCH_JSON}" 2>"${BENCH_LOG}"
BENCH_EXIT=$?

if [ "${BENCH_EXIT}" -ne 0 ]; then
    fail "benchmarks.runner exited ${BENCH_EXIT}"
    cat "${BENCH_LOG}"
    FAILURES=$((FAILURES + 1))
else
    # Parse JSON and check overall score
    OVERALL=$(${PYTHON} -c "
import json, sys
try:
    data = json.load(open('${BENCH_JSON}'))
    score = data['scores']['overall_score']
    print(f'{score:.3f}')
    sys.exit(0 if score >= float('${MIN_OVERALL_SCORE}') else 1)
except Exception as e:
    print(f'parse-error: {e}')
    sys.exit(1)
" 2>&1)
    SCORE_EXIT=$?

    if [ "${SCORE_EXIT}" -eq 0 ]; then
        pass "tier-1-benchmarks (overall score: ${OVERALL})"
    else
        fail "tier-1-benchmarks: score ${OVERALL} below minimum ${MIN_OVERALL_SCORE}"
        FAILURES=$((FAILURES + 1))
    fi

    # Print suite summary
    ${PYTHON} - <<EOF 2>/dev/null || true
import json
data = json.load(open("${BENCH_JSON}"))
for suite, s in data["scores"]["suites"].items():
    icon = "+" if s["pass_rate"] >= float("${MIN_OVERALL_SCORE}") else "X"
    print(f"  [{icon}] {suite:35s} {s['passed']}/{s['total']} passed  score: {s['avg_score']:.1%}")
print()
print(f"  Overall: {data['scores']['overall_score']:.1%}")
EOF
fi
echo

# ── Step 4: Tier-2 HAPI smoke (optional) ──────────────────────────────────────

if [ "${RUN_HAPI}" -eq 1 ]; then
    echo "Step 4/4 — Tier-2 HAPI smoke (end-to-end)"
    hr

    # Default: let the runner manage HAPI lifecycle; override with NO_FHIR_SETUP=1
    HAPI_FLAGS="--e2e"
    if [ "${NO_FHIR_SETUP:-0}" = "1" ]; then
        HAPI_FLAGS="--e2e --no-fhir-setup"
    fi

    HAPI_JSON=$(mktemp)
    HAPI_LOG=$(mktemp)

    ${PYTHON} -m benchmarks.runner ${HAPI_FLAGS} --json > "${HAPI_JSON}" 2>"${HAPI_LOG}"
    HAPI_EXIT=$?

    if [ "${HAPI_EXIT}" -eq 0 ]; then
        E2E_SCORE=$(${PYTHON} -c "
import json
data = json.load(open('${HAPI_JSON}'))
cats = data['scores']['categories']
print(f'{cats.get(\"e2e\", 0):.3f}')
" 2>/dev/null || echo "0")
        pass "tier-2-hapi-smoke (e2e score: ${E2E_SCORE})"
    else
        fail "tier-2-hapi-smoke (exit ${HAPI_EXIT})"
        tail -30 "${HAPI_LOG}"
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "Step 4/4 — Tier-2 HAPI smoke  (skipped — pass --hapi to enable)"
fi
echo

# ── Summary ───────────────────────────────────────────────────────────────────

hr
if [ ${FAILURES} -eq 0 ]; then
    pass "All checks passed — safe to deploy"
    echo
    exit 0
else
    fail "${FAILURES} check(s) failed — do NOT deploy"
    echo
    exit 1
fi
