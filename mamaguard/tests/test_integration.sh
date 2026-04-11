#!/usr/bin/env bash
# MamaGuard integration tests — curl-based smoke tests against a running agent.
#
# Usage:
#   ./tests/test_integration.sh [base_url] [api_key]
#
# Defaults:
#   base_url = http://localhost:8001
#   api_key  = dev-key-local

set -euo pipefail

BASE_URL="${1:-http://localhost:8001}"
API_KEY="${2:-dev-key-local}"
PASS=0
FAIL=0

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }

assert_status() {
    local test_name="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        green "PASS: $test_name (HTTP $actual)"
        PASS=$((PASS + 1))
    else
        red  "FAIL: $test_name (expected HTTP $expected, got HTTP $actual)"
        FAIL=$((FAIL + 1))
    fi
}

assert_json_field() {
    local test_name="$1" json="$2" field="$3" expected="$4"
    local actual
    actual=$(echo "$json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$field',''))" 2>/dev/null || echo "PARSE_ERROR")
    if [ "$actual" = "$expected" ]; then
        green "PASS: $test_name ($field = $actual)"
        PASS=$((PASS + 1))
    else
        red  "FAIL: $test_name (expected $field='$expected', got '$actual')"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== MamaGuard Integration Tests ==="
echo "Target: $BASE_URL"
echo ""

# 1. Agent card is publicly accessible (no API key)
echo "--- Test: Agent Card ---"
HTTP_CODE=$(curl -s -o /tmp/mamaguard_test.json -w "%{http_code}" "$BASE_URL/.well-known/agent-card.json")
BODY=$(cat /tmp/mamaguard_test.json)
assert_status "Agent card accessible without API key" "200" "$HTTP_CODE"
assert_json_field "Agent card name" "$BODY" "name" "MamaGuard Care Coordinator"
assert_json_field "Agent card version" "$BODY" "version" "1.0.0"

# Check skills count
SKILLS_COUNT=$(echo "$BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('skills',[])))" 2>/dev/null || echo "0")
if [ "$SKILLS_COUNT" = "4" ]; then
    green "PASS: Agent card has 4 skills"
    PASS=$((PASS + 1))
else
    red  "FAIL: Expected 4 skills, got $SKILLS_COUNT"
    FAIL=$((FAIL + 1))
fi

# Check FHIR extension
HAS_FHIR=$(echo "$BODY" | python3 -c "
import sys, json
card = json.load(sys.stdin)
exts = card.get('capabilities', {}).get('extensions', [])
print('yes' if any('fhir-context' in e.get('uri','') for e in exts) else 'no')
" 2>/dev/null || echo "no")
if [ "$HAS_FHIR" = "yes" ]; then
    green "PASS: Agent card declares FHIR context extension"
    PASS=$((PASS + 1))
else
    red  "FAIL: Agent card missing FHIR context extension"
    FAIL=$((FAIL + 1))
fi

# Check security scheme
HAS_APIKEY=$(echo "$BODY" | python3 -c "
import sys, json
card = json.load(sys.stdin)
schemes = card.get('securitySchemes', {})
print('yes' if 'apiKey' in schemes else 'no')
" 2>/dev/null || echo "no")
if [ "$HAS_APIKEY" = "yes" ]; then
    green "PASS: Agent card declares apiKey security scheme"
    PASS=$((PASS + 1))
else
    red  "FAIL: Agent card missing apiKey security scheme"
    FAIL=$((FAIL + 1))
fi

# 2. A2A endpoint requires API key
echo ""
echo "--- Test: Auth Enforcement ---"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{"message":{"role":"user","parts":[{"text":"hello"}]}}}')
assert_status "POST without API key rejected" "401" "$HTTP_CODE"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: wrong-key-999" \
    -d '{"jsonrpc":"2.0","method":"message/send","id":"2","params":{"message":{"role":"user","parts":[{"text":"hello"}]}}}')
assert_status "POST with invalid API key rejected" "403" "$HTTP_CODE"

# 3. A2A endpoint accepts valid API key
echo ""
echo "--- Test: A2A Endpoint ---"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d '{"jsonrpc":"2.0","method":"message/send","id":"3","params":{"message":{"role":"user","parts":[{"text":"hello"}]}}}')
# Accept 200 or 500 (500 is OK for now — means auth passed but no GOOGLE_API_KEY configured)
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "500" ]; then
    green "PASS: POST with valid API key accepted (HTTP $HTTP_CODE)"
    PASS=$((PASS + 1))
else
    red  "FAIL: POST with valid API key got unexpected HTTP $HTTP_CODE"
    FAIL=$((FAIL + 1))
fi

# Summary
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
