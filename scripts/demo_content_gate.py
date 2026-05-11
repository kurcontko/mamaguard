#!/usr/bin/env python3
"""Demo-content gate for the MamaGuard Maria money-shot sequence.

This is stricter than a protocol smoke test. It verifies that the actual
judge-facing response is clean enough to record:
  - Maria maternal risk is grounded in FHIR values.
  - SDOH access barriers are present.
  - Lucas pediatric handoff is present.
  - HepB birth dose is not misstated as missing.
  - Newborn metabolic/hearing screens are shown as completed.
  - The response has 5T structure, clinician review, FHIR citations, and no
    visible FHIR server failures.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

FHIR_EXTENSION_URI = "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"
DEFAULT_API_KEY_FILE = "/tmp/mamaguard_api_key"
DEFAULT_OUTPUT = "/tmp/mamaguard_demo_response.md"
FIVE_T_SECTIONS = ("Talk", "Template", "Table", "Task", "Transaction")

DEMO_PROMPT = (
    "Demo sequence. First call find_linked_newborn with mother_patient_id "
    "bench-maria-001. If it returns a child, call pediatric_transition_agent "
    "and tell it to use patient_id bench-baby-santos-001 for its pediatric "
    "tools. Also call maternal_risk_agent and sdoh_outreach_agent. Synthesize "
    "one 5T response showing Maria maternal risk -> SDOH access barriers -> "
    "Lucas pediatric immunization/development planning. Use pediatric tool "
    "results exactly: if HepB birth dose is already received, say received, "
    "not due. For pediatric tasks, say schedule/review/verify; do not use "
    "prescribe, administer, initiate, or start. Include completed metabolic/"
    "hearing screens if reported. Explicitly include developmental surveillance "
    "due/overdue if the pediatric tool reports it. Cite FHIR evidence."
)

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def load_api_key(explicit: str | None, key_file: str) -> str:
    if explicit:
        return explicit.strip()
    env_key = os.getenv("MAMAGUARD_API_KEY")
    if env_key:
        return env_key.strip()
    path = Path(key_file)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "No API key found. Pass --api-key, set MAMAGUARD_API_KEY, "
        f"or create {key_file}."
    )


def response_text(body: dict[str, Any]) -> str:
    result = body.get("result") or {}
    for artifact in result.get("artifacts") or []:
        for part in artifact.get("parts") or []:
            text = part.get("text")
            if text:
                return text
    status = result.get("status") or {}
    message = status.get("message") or {}
    for part in message.get("parts") or []:
        text = part.get("text")
        if text:
            return text
    return ""


def task_state(body: dict[str, Any]) -> str:
    result = body.get("result") or {}
    return ((result.get("status") or {}).get("state") or "").lower()


def check(name: str, condition: bool, detail: str = "") -> Check:
    return Check(name, condition, "" if condition else detail)


def print_check(item: Check) -> None:
    if item.passed:
        print(f"  {GREEN}PASS{RESET} {item.name}")
    else:
        print(f"  {RED}FAIL{RESET} {item.name}: {item.detail}")


def run_demo_call(
    url: str,
    api_key: str,
    fhir_url: str,
    fhir_token: str,
    patient_id: str,
    timeout: float,
) -> tuple[int, float, dict[str, Any], str]:
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": "demo-content-gate",
        "params": {
            "message": {
                "messageId": "msg-demo-content-gate",
                "role": "user",
                "parts": [{"text": DEMO_PROMPT}],
            },
            "metadata": {
                "fhir-context": {
                    "fhirUrl": fhir_url.rstrip("/"),
                    "fhirToken": fhir_token,
                    "patientId": patient_id,
                }
            },
        },
    }
    started = time.monotonic()
    resp = httpx.post(
        url.rstrip("/") + "/",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "X-A2A-Extensions": FHIR_EXTENSION_URI,
        },
        json=payload,
        timeout=timeout,
    )
    elapsed = time.monotonic() - started
    body = resp.json() if resp.content else {}
    return resp.status_code, elapsed, body, response_text(body)


def evaluate(http_status: int, elapsed: float, body: dict[str, Any], text: str) -> list[Check]:
    upper = text.upper()
    fhir_refs = re.findall(
        r"(?:Observation|Condition|Coverage|Patient|RelatedPerson|RiskAssessment|"
        r"CarePlan|CommunicationRequest|Immunization)/[A-Za-z0-9_.-]+",
        text,
    )
    fhir_server_errors = (
        "FHIR ERROR",
        "FHIR SERVER ERROR",
        "CONNECTION ERROR",
        "FAILED DUE TO SERVER",
        "AUTHENTICATION ERROR",
    )
    unsafe_verbs = ("PRESCRIBE ", "START HER ON", "ADMINISTER ", "INITIATE ")
    birth_hepb_missing_claims = (
        "HEPB BIRTH DOSE MISSING",
        "INCLUDING THE HEPB BIRTH DOSE",
        "HEPB (BIRTH) | **OVERDUE",
        "HEPB BIRTH DOSE) | **OVERDUE",
        "NO VACCINATIONS",
        "0/6 VACCINATIONS",
    )

    return [
        check("HTTP 200", http_status == 200, f"HTTP {http_status}"),
        check("A2A task completed", task_state(body) == "completed", str((body.get("result") or {}).get("status"))[:240]),
        check("JSON-RPC id echoed", body.get("id") == "demo-content-gate", str(body.get("id"))),
        check("response text present", bool(text.strip()), "empty response"),
        check("all 5T sections present", all(f"**{s}**" in text for s in FIVE_T_SECTIONS), text[:500]),
        check("Maria maternal risk present", "MARIA" in upper and "168/108" in upper and "7.9" in upper, text[:600]),
        check("SDOH access barriers present", "INSURANCE" in upper and ("HOUSING" in upper or "COVERAGE" in upper), text[:600]),
        check("Lucas handoff present", "LUCAS" in upper or "BENCH-BABY-SANTOS-001" in upper, text[:600]),
        check("pediatric vaccine planning present", any(x in upper for x in ("DTAP", "PCV", "IMMUNIZATION", "VACCINE SERIES")), text[:800]),
        check("development planning present", "DEVELOPMENT" in upper or "SURVEILLANCE" in upper, text[:800]),
        check("newborn screens completed", "METABOLIC" in upper and "HEARING" in upper and "COMPLETED" in upper, text[:1000]),
        check("HepB birth dose not misstated as missing", not any(x in upper for x in birth_hepb_missing_claims), text[:1200]),
        check("clinician review present", "CLINICIAN REVIEW" in upper, text[:800]),
        check("FHIR citations present", len(fhir_refs) >= 5, f"{len(fhir_refs)} refs"),
        check("no visible FHIR server failure", not any(x in upper for x in fhir_server_errors), text[:1000]),
        check("no prescribing/action verbs", not any(x in upper for x in unsafe_verbs), text[:1200]),
        check("response under demo latency budget", elapsed <= 45.0, f"{elapsed:.1f}s"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Maria demo content gate")
    parser.add_argument("--url", default="http://127.0.0.1:8001", help="MamaGuard A2A URL")
    parser.add_argument("--fhir-url", default="http://localhost:8090/fhir", help="FHIR base URL reachable by the agent")
    parser.add_argument("--fhir-token", default="demo-token", help="FHIR bearer token for HAPI/demo servers")
    parser.add_argument("--patient-id", default="bench-maria-001", help="Mother patient ID")
    parser.add_argument("--api-key", default=None, help="A2A API key; otherwise env/file fallback is used")
    parser.add_argument("--api-key-file", default=DEFAULT_API_KEY_FILE)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Where to write the response markdown")
    args = parser.parse_args()

    api_key = load_api_key(args.api_key, args.api_key_file)
    print(f"{BOLD}=== MamaGuard Demo Content Gate ==={RESET}")
    print(f"  Agent:   {args.url.rstrip('/')}")
    print(f"  FHIR:    {args.fhir_url.rstrip('/')}")
    print(f"  Patient: {args.patient_id}")
    print(f"  API key: present ({len(api_key)} chars, value hidden)")

    http_status, elapsed, body, text = run_demo_call(
        url=args.url,
        api_key=api_key,
        fhir_url=args.fhir_url,
        fhir_token=args.fhir_token,
        patient_id=args.patient_id,
        timeout=args.timeout,
    )
    Path(args.output).write_text(text, encoding="utf-8")
    print(f"  {DIM}call: HTTP {http_status}, {elapsed:.1f}s, {len(text)} chars{RESET}")
    print(f"  {DIM}response written to {args.output}{RESET}")

    checks = evaluate(http_status, elapsed, body, text)
    print()
    for item in checks:
        print_check(item)

    failed = [item for item in checks if not item.passed]
    print(f"\n{BOLD}Results{RESET}: {len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        print(f"{RED}DEMO CONTENT GATE FAILED{RESET}")
        sys.exit(1)
    print(f"{GREEN}DEMO CONTENT GATE PASSED{RESET}")


if __name__ == "__main__":
    main()
