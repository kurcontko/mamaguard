#!/usr/bin/env bash
# ============================================================================
# MamaGuard submission Tier-2b benchmark run (Nemotron + DeepSeek judge).
# ============================================================================
#
# This is the "locked codebase" run that produces the headline number for
# the Devpost submission. Expect 8-10 hours of wall time.
#
# Run this at T-7 days before deadline (around 2026-05-04) so you have a
# 7-day buffer for re-runs / video cut / submission paperwork.
#
# Prerequisites:
#   1. Nemotron serving on DGX port 30000 (see ~/repos/nemotron.md on DGX
#      for the docker run command; our shared vllm_node container typically
#      serves Gemma on :8000, so Nemotron needs a second container OR a
#      swap that takes Gemma offline for the duration of the run).
#   2. HAPI FHIR up on localhost:8090 with the bench bundles loaded.
#   3. .env populated with JUDGE_API_KEY (OpenRouter / DeepSeek).
#
# Usage:
#   ./scripts/run_submission_benchmark.sh                   # full Tier-2b
#   ./scripts/run_submission_benchmark.sh --smoke           # 3-case smoke
#   ./scripts/run_submission_benchmark.sh --no-judge        # skip LLM judge
# ============================================================================
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPO_ROOT"

SMOKE=0
JUDGE_FLAG="--judge"
EXTRA_FLAGS=()
for arg in "$@"; do
  case "$arg" in
    --smoke) SMOKE=1 ;;
    --no-judge) JUDGE_FLAG="" ;;
    --no-fhir-setup) EXTRA_FLAGS+=("--no-fhir-setup") ;;
    *) echo "unknown flag: $arg"; exit 2 ;;
  esac
done

# -- Source env --------------------------------------------------------------
if [[ -f .env ]]; then
  set -a; source .env; set +a
else
  echo "ERROR: .env not found at $REPO_ROOT/.env"
  exit 1
fi

# -- Override model backend for submission run -------------------------------
export BENCH_API_BASE="${BENCH_API_BASE:-http://10.10.10.2:30000/v1}"
export BENCH_MODEL="${BENCH_MODEL:-nemotron}"
export BENCH_API_KEY="${BENCH_API_KEY:-EMPTY}"
export BENCH_MAX_TOKENS="${BENCH_MAX_TOKENS:-16384}"
export BENCH_TEMPERATURE="${BENCH_TEMPERATURE:-0.4}"
export BENCH_TIMEOUT="${BENCH_TIMEOUT:-300}"

echo "=========================================="
echo "MamaGuard Tier-2b submission run"
echo "=========================================="
echo "Agent backend : $BENCH_API_BASE  (model=$BENCH_MODEL)"
echo "Judge         : ${JUDGE_API_BASE:-(disabled)}  (model=${JUDGE_MODEL:-n/a})"
echo "Temperature   : $BENCH_TEMPERATURE"
echo "Max tokens    : $BENCH_MAX_TOKENS"
echo "Timeout       : $BENCH_TIMEOUT s per turn"
echo "Mode          : $([[ $SMOKE -eq 1 ]] && echo 'SMOKE (3 cases)' || echo 'FULL')"
echo "=========================================="

# -- Preflight: agent backend must be reachable ------------------------------
echo "[preflight] probing agent endpoint..."
if ! curl -sf --max-time 5 "${BENCH_API_BASE}/models" -o /dev/null; then
  echo "ERROR: agent endpoint ${BENCH_API_BASE}/models not reachable."
  echo "       On DGX (qrc@10.10.10.2), see ~/repos/nemotron.md to start Nemotron."
  exit 1
fi
echo "[preflight] agent OK"

# -- Preflight: HAPI -----------------------------------------------------------
echo "[preflight] probing FHIR server..."
FHIR_URL="${HAPI_FHIR_URL:-http://localhost:8090/fhir}"
if ! curl -sf --max-time 5 "$FHIR_URL/metadata" -o /dev/null; then
  echo "ERROR: FHIR server $FHIR_URL unreachable. Start HAPI container first."
  exit 1
fi
echo "[preflight] HAPI OK at $FHIR_URL"

# -- Preflight: Tier-1 must still be 100% before burning 8+ hours on Tier-2b --
echo "[preflight] running Tier-1 gate..."
if ! uv run python -m benchmarks.runner 2>&1 | tee /tmp/submission_tier1.log | grep -q "OVERALL SCORE: 100.0%"; then
  echo "ERROR: Tier-1 regression detected -- do not proceed to Tier-2b."
  echo "       see /tmp/submission_tier1.log"
  exit 1
fi
echo "[preflight] Tier-1 100%"

# -- Output destination -------------------------------------------------------
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT_DIR="benchmarks/fixtures/submission_runs"
mkdir -p "$OUT_DIR"
OUT_JSON="$OUT_DIR/tier2b_${BENCH_MODEL}_${TIMESTAMP}.json"
LOG_FILE="$OUT_DIR/tier2b_${BENCH_MODEL}_${TIMESTAMP}.log"

echo "[run] writing JSON to $OUT_JSON"
echo "[run] writing log  to $LOG_FILE"

# -- Actual run ---------------------------------------------------------------
BENCH_FLAGS=(--e2e --backend vllm "${EXTRA_FLAGS[@]}")
if [[ $JUDGE_FLAG ]]; then
  BENCH_FLAGS+=("$JUDGE_FLAG")
fi
if [[ $SMOKE -eq 1 ]]; then
  # Smoke run: restrict to a single e2e category to keep runtime low.
  BENCH_FLAGS+=(--e2e-categories routing)
fi

START=$(date +%s)
uv run python -m benchmarks.runner "${BENCH_FLAGS[@]}" 2>&1 | tee "$LOG_FILE"
END=$(date +%s)
ELAPSED=$((END - START))

# Try to extract the final JSON summary if `--json` was used; otherwise the
# log file is the durable artefact.
if grep -q "^{" "$LOG_FILE"; then
  grep "^{" "$LOG_FILE" | tail -1 > "$OUT_JSON" || true
fi

echo "=========================================="
echo "Submission run complete in $((ELAPSED / 60)) min $((ELAPSED % 60)) s"
echo "JSON: $OUT_JSON (may be empty -- log is the durable artefact)"
echo "LOG : $LOG_FILE"
echo "=========================================="
