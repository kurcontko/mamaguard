#!/usr/bin/env bash
# demo_pre_record_cleanup.sh — Run before each demo recording session.
#
# Deletes all agent-generated memory DocumentReferences for Maria from the
# Azure HAPI sandbox, leaving only the seeded Dr. Kim metformin note
# (DocumentReference/1208). This keeps the Scene 4 memory-recall demo
# working — the agent fetches only the 5 most-recent notes, and Dr. Kim's
# note is the oldest, so it falls out of the window if test runs accumulate.
#
# Usage:  ./scripts/demo_pre_record_cleanup.sh
#
# Optional override:  HAPI_URL=<your-hapi> ./scripts/demo_pre_record_cleanup.sh

set -euo pipefail

HAPI_URL="${HAPI_URL:-https://ca-hapi-fhir.gentleisland-cc083285.eastus.azurecontainerapps.io/fhir}"
KEEP_ID="${KEEP_ID:-1208}"
PATIENT_ID="${PATIENT_ID:-bench-maria-001}"

echo "Cleaning up agent-generated memory notes for Patient/${PATIENT_ID}"
echo "  HAPI: ${HAPI_URL}"
echo "  Keeping: DocumentReference/${KEEP_ID} (seeded Dr. Kim note)"
echo ""

DELETED=0
while read -r ID; do
    [ -z "${ID}" ] && continue
    CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "${HAPI_URL}/DocumentReference/${ID}")
    echo "  DELETE DocumentReference/${ID}: HTTP ${CODE}"
    DELETED=$((DELETED + 1))
done < <(curl -fsS "${HAPI_URL}/DocumentReference?subject=Patient/${PATIENT_ID}&_count=50" \
    | python3 -c "
import sys, json, os
keep = os.environ.get('KEEP_ID', '1208')
b = json.load(sys.stdin)
for e in b.get('entry', []):
    rid = e['resource'].get('id')
    if rid and rid != keep:
        print(rid)
" KEEP_ID="${KEEP_ID}")

echo ""
echo "Deleted ${DELETED} agent-generated note(s)."
echo ""
echo "=== Verify Dr. Kim note still present ==="
RESP=$(curl -fsS "${HAPI_URL}/DocumentReference/${KEEP_ID}" 2>&1)
if echo "${RESP}" | python3 -c "import sys,json; r=json.load(sys.stdin); sys.exit(0 if r.get('id') == '${KEEP_ID}' else 1)" 2>/dev/null; then
    echo "  OK: DocumentReference/${KEEP_ID} present"
else
    echo "  MISSING — re-seed with:"
    echo "    HAPI_FHIR_URL=${HAPI_URL} uv run python scripts/demo_memory_recall.py --seed-only"
    exit 1
fi
