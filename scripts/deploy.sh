#!/usr/bin/env bash
# deploy.sh — deploy MamaGuard to Cloud Run
# Usage:  ./scripts/deploy.sh [--skip-checks] [--dry-run]
# Env: GOOGLE_API_KEY, MAMAGUARD_API_KEY (required); GCP_PROJECT, GCP_REGION, SERVICE_NAME (optional)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SKIP_CHECKS=0; DRY_RUN=0
for arg in "$@"; do
    case "$arg" in --skip-checks) SKIP_CHECKS=1 ;; --dry-run) DRY_RUN=1 ;; *) echo "Unknown: $arg"; exit 1 ;; esac
done

GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || echo '')}"
GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-mamaguard}"
[ -z "${GCP_PROJECT}" ] && echo "FAIL: GCP_PROJECT not set" && exit 1
command -v gcloud &>/dev/null || { echo "FAIL: gcloud CLI not found"; exit 1; }
echo "Deploying ${SERVICE_NAME} to ${GCP_PROJECT}/${GCP_REGION} (dry_run=${DRY_RUN})"

# Pre-deploy checks
[ "${SKIP_CHECKS}" -eq 0 ] && { "${SCRIPT_DIR}/pre_deploy_check.sh" || { echo "FAIL: pre-deploy checks"; exit 1; }; }

# Build deploy command
DEPLOY_CMD=(gcloud run deploy "${SERVICE_NAME}" --source "${REPO_ROOT}/mamaguard"
    --project "${GCP_PROJECT}" --region "${GCP_REGION}" --platform managed
    --allow-unauthenticated --port 8001 --memory 512Mi --cpu 1 --timeout 300
    --max-instances 10 --set-env-vars "PYTHONDONTWRITEBYTECODE=1,PYTHONUNBUFFERED=1")
[ -n "${GOOGLE_API_KEY:-}" ] && DEPLOY_CMD+=(--set-env-vars "GOOGLE_API_KEY=${GOOGLE_API_KEY}")
[ -n "${MAMAGUARD_API_KEY:-}" ] && DEPLOY_CMD+=(--set-env-vars "MAMAGUARD_API_KEY=${MAMAGUARD_API_KEY}")

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "DRY RUN — would execute: ${DEPLOY_CMD[*]}"; exit 0
fi

"${DEPLOY_CMD[@]}" 2>&1 || { echo "FAIL: gcloud run deploy"; exit 1; }

# Verify agent-card endpoint
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --project "${GCP_PROJECT}" --region "${GCP_REGION}" --format "value(status.url)" 2>/dev/null)
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${SERVICE_URL}/.well-known/agent-card.json" 2>/dev/null || echo "000")
[ "${HTTP_CODE}" = "200" ] && echo "OK: ${SERVICE_URL} — agent-card responds 200" || echo "WARN: agent-card returned HTTP ${HTTP_CODE}"
