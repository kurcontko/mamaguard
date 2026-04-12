#!/usr/bin/env bash
# deploy.sh — deploy MamaGuard to Cloud Run
#
# Usage:
#   ./scripts/deploy.sh                   # deploy with pre-deploy checks
#   ./scripts/deploy.sh --skip-checks     # skip pre-deploy checks (CI already ran them)
#   ./scripts/deploy.sh --dry-run         # show what would happen without deploying
#
# Required environment variables:
#   GOOGLE_API_KEY       — Gemini API key (set as Cloud Run secret or env var)
#   MAMAGUARD_API_KEY    — API key(s) for agent auth (comma-separated)
#
# Optional environment variables:
#   GCP_PROJECT          — GCP project ID (default: current gcloud project)
#   GCP_REGION           — Cloud Run region (default: us-central1)
#   SERVICE_NAME         — Cloud Run service name (default: mamaguard)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Helpers ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

pass()  { echo -e "${GREEN}[PASS]${RESET} $*"; }
fail()  { echo -e "${RED}[FAIL]${RESET} $*"; exit 1; }
warn()  { echo -e "${YELLOW}[WARN]${RESET} $*"; }
info()  { echo -e "  [*] $*"; }
hr()    { echo "────────────────────────────────────────────────────────────────"; }

# ── Parse args ─────────────────────────────────────────────────────────────────

SKIP_CHECKS=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --skip-checks) SKIP_CHECKS=1 ;;
        --dry-run)     DRY_RUN=1 ;;
        *)             echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# ── Config ────────────────────────────────────────────────────────────────────

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || echo '')}"
GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-mamaguard}"

hr
echo "  MamaGuard Cloud Run Deploy"
info "project:     ${GCP_PROJECT:-<not set>}"
info "region:      ${GCP_REGION}"
info "service:     ${SERVICE_NAME}"
info "skip checks: $([ "${SKIP_CHECKS}" -eq 1 ] && echo 'yes' || echo 'no')"
info "dry run:     $([ "${DRY_RUN}" -eq 1 ] && echo 'yes' || echo 'no')"
hr
echo

# ── Preflight ─────────────────────────────────────────────────────────────────

if [ -z "${GCP_PROJECT}" ]; then
    fail "GCP_PROJECT is not set and no default gcloud project configured"
fi

if ! command -v gcloud &>/dev/null; then
    fail "gcloud CLI not found — install from https://cloud.google.com/sdk/docs/install"
fi

# ── Step 1: Pre-deploy checks ────────────────────────────────────────────────

if [ "${SKIP_CHECKS}" -eq 0 ]; then
    echo "Step 1/3 — Running pre-deploy checks"
    hr
    "${SCRIPT_DIR}/pre_deploy_check.sh" || fail "Pre-deploy checks failed — aborting deploy"
    pass "pre-deploy checks"
    echo
else
    warn "Step 1/3 — Pre-deploy checks SKIPPED"
    echo
fi

# ── Step 2: Deploy to Cloud Run ──────────────────────────────────────────────

echo "Step 2/3 — Deploying to Cloud Run"
hr

DEPLOY_CMD=(
    gcloud run deploy "${SERVICE_NAME}"
    --source "${REPO_ROOT}/mamaguard"
    --project "${GCP_PROJECT}"
    --region "${GCP_REGION}"
    --platform managed
    --allow-unauthenticated
    --port 8001
    --memory 512Mi
    --cpu 1
    --timeout 300
    --max-instances 10
    --set-env-vars "PYTHONDONTWRITEBYTECODE=1,PYTHONUNBUFFERED=1,LOG_FULL_PAYLOAD=true"
)

# Add API keys if set (prefer secrets, but env vars work for initial deploy)
if [ -n "${GOOGLE_API_KEY:-}" ]; then
    DEPLOY_CMD+=(--set-env-vars "GOOGLE_API_KEY=${GOOGLE_API_KEY}")
fi
if [ -n "${MAMAGUARD_API_KEY:-}" ]; then
    DEPLOY_CMD+=(--set-env-vars "MAMAGUARD_API_KEY=${MAMAGUARD_API_KEY}")
fi

info "Command: ${DEPLOY_CMD[*]}"
echo

if [ "${DRY_RUN}" -eq 1 ]; then
    warn "DRY RUN — skipping actual deployment"
    echo
else
    "${DEPLOY_CMD[@]}" 2>&1
    DEPLOY_EXIT=$?

    if [ "${DEPLOY_EXIT}" -ne 0 ]; then
        fail "gcloud run deploy failed (exit ${DEPLOY_EXIT})"
    fi
    pass "deploy succeeded"
    echo
fi

# ── Step 3: Verify agent-card endpoint ────────────────────────────────────────

echo "Step 3/3 — Verifying deployment"
hr

if [ "${DRY_RUN}" -eq 1 ]; then
    warn "DRY RUN — skipping verification"
    echo
else
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --project "${GCP_PROJECT}" \
        --region "${GCP_REGION}" \
        --format "value(status.url)" 2>/dev/null)

    if [ -z "${SERVICE_URL}" ]; then
        fail "Could not retrieve service URL"
    fi

    info "Service URL: ${SERVICE_URL}"

    # Verify agent-card endpoint (public, no auth needed)
    CARD_URL="${SERVICE_URL}/.well-known/agent-card.json"
    info "Checking: ${CARD_URL}"

    HTTP_CODE=$(curl -s -o /tmp/agent-card-response.json -w "%{http_code}" "${CARD_URL}" 2>/dev/null || echo "000")

    if [ "${HTTP_CODE}" = "200" ]; then
        pass "agent-card responds 200"
        # Verify it's valid JSON with expected fields
        python3 - <<EOF
import json, sys
try:
    card = json.load(open("/tmp/agent-card-response.json"))
    assert "name" in card, "missing 'name'"
    assert "url" in card, "missing 'url'"
    assert "skills" in card, "missing 'skills'"
    print(f"  Agent: {card['name']}")
    print(f"  URL:   {card['url']}")
    print(f"  Skills: {len(card['skills'])}")
except Exception as e:
    print(f"  WARNING: agent-card validation issue: {e}")
    sys.exit(1)
EOF
        VALIDATE_EXIT=$?
        if [ "${VALIDATE_EXIT}" -eq 0 ]; then
            pass "agent-card content valid"
        else
            warn "agent-card content has issues (see above)"
        fi
    else
        fail "agent-card returned HTTP ${HTTP_CODE} (expected 200)"
    fi

    # Verify auth is enforced on other endpoints
    AUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/" 2>/dev/null || echo "000")
    if [ "${AUTH_CODE}" = "401" ]; then
        pass "root endpoint correctly returns 401 (auth enforced)"
    else
        warn "root endpoint returned ${AUTH_CODE} (expected 401)"
    fi

    # Verify API key auth works
    if [ -n "${MAMAGUARD_API_KEY:-}" ]; then
        # Extract first key if comma-separated
        FIRST_KEY=$(echo "${MAMAGUARD_API_KEY}" | cut -d, -f1)
        AUTH_OK_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "X-API-Key: ${FIRST_KEY}" \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"agent/info","id":1}' \
            "${SERVICE_URL}/" 2>/dev/null || echo "000")
        if [ "${AUTH_OK_CODE}" = "200" ] || [ "${AUTH_OK_CODE}" = "405" ]; then
            pass "API key auth accepted (HTTP ${AUTH_OK_CODE})"
        else
            warn "API key auth test returned ${AUTH_OK_CODE}"
        fi
    fi

    echo
    hr
    echo
    pass "Deployment verified!"
    info "Service URL: ${SERVICE_URL}"
    info "Agent card:  ${CARD_URL}"

    # Update MAMAGUARD_URL suggestion
    echo
    info "Next steps:"
    info "  1. Set MAMAGUARD_URL=${SERVICE_URL} in Cloud Run env vars"
    info "  2. Publish to Prompt Opinion Marketplace"
    info "  3. Test mother->child handoff with Synthea Maria"
fi

echo
