#!/usr/bin/env python3
"""MamaGuard agent smoke test -- pre-demo validation.

Sends 3 queries to a running agent via the A2A endpoint and validates
that responses contain the expected 5T sections and clinician review blocks.

Usage:
    python scripts/smoke_test.py                          # defaults
    python scripts/smoke_test.py --url http://host:8001   # custom URL
    python scripts/smoke_test.py --api-key my-key         # custom API key
    python scripts/smoke_test.py --timeout 120            # per-request timeout

Exit 0 if all checks pass, exit 1 if any fail.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field

import httpx

# -- ANSI colors ---------------------------------------------------------------

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# -- Config --------------------------------------------------------------------

DEFAULT_URL = "http://localhost:8001"
DEFAULT_API_KEY = "dev-key-local"
DEFAULT_TIMEOUT = 90  # seconds per request
DEFAULT_FHIR_URL = "http://localhost:8090/fhir"
DEFAULT_PATIENT_ID = "bench-maria-001"

# 5T section headers the agent should produce
FIVE_T_SECTIONS = ["Talk", "Template", "Table", "Task", "Transaction"]

# Clinician review marker
CLINICIAN_REVIEW_MARKER = "CLINICIAN REVIEW"

# Smoke test queries
QUERIES = [
    {
        "name": "Maternal risk assessment",
        "message": "Assess the maternal risk for this patient",
        "expect_5t": True,
        "expect_clinician_review": True,
    },
    {
        "name": "SDOH screening",
        "message": "Screen this patient for social determinants of health",
        "expect_5t": True,
        "expect_clinician_review": True,
    },
    {
        "name": "Comprehensive assessment",
        "message": "Run a comprehensive assessment for this patient",
        "expect_5t": True,
        "expect_clinician_review": True,
    },
]


# -- Result tracking -----------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class QueryResult:
    name: str
    checks: list[CheckResult] = field(default_factory=list)
    response_text: str = ""
    elapsed_s: float = 0.0
    error: str | None = None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks) and self.error is None


# -- A2A client ----------------------------------------------------------------


def build_payload(message: str, fhir_url: str, patient_id: str, req_id: str) -> dict:
    """Build a JSON-RPC message/send payload with FHIR context."""
    return {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": req_id,
        "params": {
            "message": {
                "messageId": f"msg-{req_id}",
                "role": "user",
                "parts": [{"text": message}],
            },
            "metadata": {
                "fhir-context": {
                    "fhirUrl": fhir_url,
                    "patientId": patient_id,
                }
            },
        },
    }


def extract_response_text(body: dict) -> str:
    """Pull the agent's text response out of the JSON-RPC result."""
    # A2A response: result.artifacts[].parts[].text or result.status.message.parts[].text
    result = body.get("result", {})

    # Try artifacts first
    for artifact in result.get("artifacts", []):
        for part in artifact.get("parts", []):
            if "text" in part:
                return part["text"]

    # Fall back to status message
    status = result.get("status", {})
    msg = status.get("message", {})
    for part in msg.get("parts", []):
        if "text" in part:
            return part["text"]

    return ""


def send_query(
    url: str,
    api_key: str,
    message: str,
    fhir_url: str,
    patient_id: str,
    timeout: float,
    req_id: str,
) -> tuple[str, float]:
    """Send one A2A message/send and return (response_text, elapsed_seconds)."""
    payload = build_payload(message, fhir_url, patient_id, req_id)
    t0 = time.monotonic()
    resp = httpx.post(
        url + "/",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        timeout=timeout,
    )
    elapsed = time.monotonic() - t0

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"JSON-RPC error: {body['error']}")

    text = extract_response_text(body)
    if not text:
        raise RuntimeError(f"No text in response: {json.dumps(body)[:300]}")

    return text, elapsed


# -- Validation ----------------------------------------------------------------


def check_5t_sections(text: str) -> list[CheckResult]:
    """Check that all 5T section headers appear in the response."""
    results = []
    for section in FIVE_T_SECTIONS:
        # Match **Talk** or **Talk:** or **Talk** -- (flexible)
        found = f"**{section}**" in text
        results.append(
            CheckResult(
                name=f"5T section: {section}",
                passed=found,
                detail="" if found else f"Missing **{section}** section",
            )
        )
    return results


def check_clinician_review(text: str) -> CheckResult:
    """Check that the clinician review marker appears."""
    found = CLINICIAN_REVIEW_MARKER in text.upper()
    return CheckResult(
        name="Clinician review block",
        passed=found,
        detail="" if found else f"Missing '{CLINICIAN_REVIEW_MARKER}' marker",
    )


def validate_response(text: str, expect_5t: bool, expect_clinician_review: bool) -> list[CheckResult]:
    """Run all validation checks on a response."""
    checks: list[CheckResult] = []

    # Non-empty response
    checks.append(
        CheckResult(
            name="Non-empty response",
            passed=len(text.strip()) > 0,
            detail="" if text.strip() else "Response was empty",
        )
    )

    if expect_5t:
        checks.extend(check_5t_sections(text))

    if expect_clinician_review:
        checks.append(check_clinician_review(text))

    return checks


# -- Main ----------------------------------------------------------------------


def run_smoke_tests(
    url: str,
    api_key: str,
    fhir_url: str,
    patient_id: str,
    timeout: float,
    verbose: bool = False,
) -> list[QueryResult]:
    """Run all smoke test queries and return results."""
    results: list[QueryResult] = []

    for i, query in enumerate(QUERIES, 1):
        qr = QueryResult(name=query["name"])
        print(f"\n{BOLD}[{i}/{len(QUERIES)}] {query['name']}{RESET}")
        print(f"  {DIM}Query: {query['message']}{RESET}")

        try:
            text, elapsed = send_query(
                url=url,
                api_key=api_key,
                message=query["message"],
                fhir_url=fhir_url,
                patient_id=patient_id,
                timeout=timeout,
                req_id=str(i),
            )
            qr.response_text = text
            qr.elapsed_s = elapsed
            print(f"  {DIM}Response: {elapsed:.1f}s, {len(text)} chars{RESET}")

            if verbose:
                # Print first 500 chars of the response
                preview = text[:500] + ("..." if len(text) > 500 else "")
                print(f"  {DIM}---{RESET}")
                for line in preview.split("\n"):
                    print(f"  {DIM}{line}{RESET}")
                print(f"  {DIM}---{RESET}")

            qr.checks = validate_response(
                text,
                expect_5t=query["expect_5t"],
                expect_clinician_review=query["expect_clinician_review"],
            )

        except Exception as e:
            qr.error = str(e)
            qr.checks = [CheckResult(name="Request succeeded", passed=False, detail=str(e))]
            print(f"  {RED}ERROR: {e}{RESET}")

        # Print check results
        for check in qr.checks:
            if check.passed:
                print(f"  {GREEN}PASS{RESET} {check.name}")
            else:
                print(f"  {RED}FAIL{RESET} {check.name}: {check.detail}")

        results.append(qr)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="MamaGuard agent smoke test")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Agent URL (default: {DEFAULT_URL})")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--fhir-url", default=DEFAULT_FHIR_URL, help=f"FHIR server URL (default: {DEFAULT_FHIR_URL})")
    parser.add_argument("--patient-id", default=DEFAULT_PATIENT_ID, help=f"Patient ID (default: {DEFAULT_PATIENT_ID})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print response previews")
    args = parser.parse_args()

    from mamaguard import MAMAGUARD_VERSION

    print(f"{BOLD}=== MamaGuard Smoke Test ==={RESET}")
    print(f"  Version: {MAMAGUARD_VERSION}")
    print(f"  Agent:   {args.url}")
    print(f"  FHIR:    {args.fhir_url}")
    print(f"  Patient: {args.patient_id}")
    print(f"  Timeout: {args.timeout}s")

    results = run_smoke_tests(
        url=args.url,
        api_key=args.api_key,
        fhir_url=args.fhir_url,
        patient_id=args.patient_id,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    # Summary
    total_checks = sum(len(r.checks) for r in results)
    passed_checks = sum(sum(1 for c in r.checks if c.passed) for r in results)
    failed_queries = [r for r in results if not r.passed]

    print(f"\n{BOLD}=== Results ==={RESET}")
    for r in results:
        status = f"{GREEN}PASS{RESET}" if r.passed else f"{RED}FAIL{RESET}"
        timing = f" ({r.elapsed_s:.1f}s)" if r.elapsed_s > 0 else ""
        print(f"  {status} {r.name}{timing}")

    print(f"\n  Checks: {passed_checks}/{total_checks} passed")
    print(f"  Queries: {len(results) - len(failed_queries)}/{len(results)} passed")

    if failed_queries:
        print(f"\n  {RED}SMOKE TEST FAILED{RESET}")
        sys.exit(1)
    else:
        print(f"\n  {GREEN}SMOKE TEST PASSED{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
