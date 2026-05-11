#!/usr/bin/env python3
"""Hard pre-submission checks for a live MamaGuard A2A endpoint.

This script intentionally covers more than the happy path:
  - public agent-card invariants
  - API-key rejection behavior
  - malformed A2A payload rejection
  - FHIR extension negotiation header echo
  - authenticated clinical completion with 5T / safety markers

It does not print API keys.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

FHIR_EXTENSION_URI = "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"
DEFAULT_URL = os.getenv(
    "MAMAGUARD_URL",
    "http://localhost:8001",
)
DEFAULT_API_KEY_FILE = "/tmp/mamaguard_api_key"
FIVE_T_SECTIONS = ("Talk", "Template", "Table", "Task", "Transaction")

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


def endpoint(base_url: str, path: str = "/") -> str:
    return base_url.rstrip("/") + path


def pass_if(name: str, condition: bool, detail: str = "") -> Check:
    return Check(name=name, passed=condition, detail="" if condition else detail)


def print_check(check: Check) -> None:
    if check.passed:
        print(f"  {GREEN}PASS{RESET} {check.name}")
    else:
        print(f"  {RED}FAIL{RESET} {check.name}: {check.detail}")


def post_message(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    *,
    req_id: str,
    message_id: str | None,
    text: str,
    metadata: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    message: dict[str, Any] = {
        "role": "user",
        "parts": [{"text": text}],
    }
    if message_id is not None:
        message["messageId"] = message_id

    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": req_id,
        "params": {"message": message},
    }
    if metadata:
        payload["params"]["metadata"] = metadata

    merged_headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    if headers:
        merged_headers.update(headers)

    return client.post(endpoint(base_url), headers=merged_headers, json=payload)


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


def check_agent_card(client: httpx.Client, base_url: str) -> list[Check]:
    print(f"\n{BOLD}Agent Card{RESET}")
    resp = client.get(endpoint(base_url, "/.well-known/agent-card.json"))
    checks = [pass_if("agent card HTTP 200", resp.status_code == 200, f"HTTP {resp.status_code}")]
    if resp.status_code != 200:
        return checks

    card = resp.json()
    extensions = card.get("capabilities", {}).get("extensions", [])
    fhir_ext = next((e for e in extensions if e.get("uri") == FHIR_EXTENSION_URI), None)
    skills = card.get("skills") or []
    skill_ids = {s.get("id") for s in skills}
    expected_skills = {
        "maternal-risk-assessment",
        "pediatric-care-transition",
        "sdoh-screening-outreach",
        "comprehensive-care-plan",
    }

    supported_ifaces = card.get("supportedInterfaces") or []
    primary_iface = supported_ifaces[0] if supported_ifaces else {}
    fhir_scopes = {s.get("name") for s in (fhir_ext or {}).get("params", {}).get("scopes", [])}

    checks.extend([
        pass_if("name is MamaGuard Care Coordinator", card.get("name") == "MamaGuard Care Coordinator", str(card.get("name"))),
        pass_if("supportedInterfaces[0].url matches target", primary_iface.get("url") == base_url.rstrip("/"), str(primary_iface.get("url"))),
        pass_if("supportedInterfaces[0].protocolBinding is JSONRPC", primary_iface.get("protocolBinding") == "JSONRPC", str(primary_iface.get("protocolBinding"))),
        pass_if("supportedInterfaces[0].protocolVersion is 1.0", primary_iface.get("protocolVersion") == "1.0", str(primary_iface.get("protocolVersion"))),
        pass_if("legacy v0.3 fields stripped", not any(k in card for k in ("url", "preferredTransport", "additionalInterfaces")), "still present: " + ", ".join(k for k in ("url", "preferredTransport", "additionalInterfaces") if k in card)),
        pass_if("apiKey security scheme declared", (card.get("securitySchemes") or {}).get("apiKey", {}).get("name") == "X-API-Key", str(card.get("securitySchemes"))[:180]),
        pass_if("FHIR extension declared", fhir_ext is not None, "missing fhir-context extension"),
        pass_if("FHIR extension required", bool(fhir_ext and fhir_ext.get("required") is True), str(fhir_ext)),
        pass_if("FHIR extension declares Patient.rs scope", "patient/Patient.rs" in fhir_scopes, str(sorted(fhir_scopes))),
        pass_if("exactly four skills", len(skills) == 4, f"{len(skills)} skills"),
        pass_if("expected skill ids present", skill_ids == expected_skills, str(sorted(skill_ids))),
    ])
    return checks


def check_auth_and_protocol(client: httpx.Client, base_url: str, api_key: str) -> list[Check]:
    print(f"\n{BOLD}Auth And Protocol{RESET}")
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": "hard-unauth",
        "params": {
            "message": {
                "messageId": "msg-hard-unauth",
                "role": "user",
                "parts": [{"text": "hello"}],
            }
        },
    }
    missing = client.post(endpoint(base_url), headers={"Content-Type": "application/json"}, json=payload)
    wrong = client.post(
        endpoint(base_url),
        headers={"Content-Type": "application/json", "X-API-Key": "wrong-key-hard-smoke"},
        json=payload,
    )
    malformed = post_message(
        client,
        base_url,
        api_key,
        req_id="hard-missing-message-id",
        message_id=None,
        text="hello",
    )
    malformed_ok = malformed.status_code in {400, 422} or (
        malformed.status_code == 200
        and (
            bool((malformed.json() if malformed.content else {}).get("error"))
            or task_state(malformed.json()) in {"failed", "rejected", "input-required"}
        )
    )
    return [
        pass_if("missing API key rejected", missing.status_code == 401, f"HTTP {missing.status_code}"),
        pass_if("wrong API key rejected", wrong.status_code == 403, f"HTTP {wrong.status_code}"),
        pass_if("payload without messageId rejected", malformed_ok, f"HTTP {malformed.status_code}: {malformed.text[:220]}"),
    ]


def check_clinical_completion(client: httpx.Client, base_url: str, api_key: str) -> list[Check]:
    print(f"\n{BOLD}Clinical Completion{RESET}")
    metadata = {
        "fhir-context": {
            "fhirUrl": "https://hard-smoke.invalid/fhir",
            "patientId": "bench-maria-001",
            "accessToken": "hard-smoke-token",
        }
    }
    headers = {"X-A2A-Extensions": FHIR_EXTENSION_URI}
    t0 = time.monotonic()
    resp = post_message(
        client,
        base_url,
        api_key,
        req_id="hard-clinical-1",
        message_id="msg-hard-clinical-1",
        text=(
            "Maria is 28 weeks pregnant with diabetes, missed prenatal visits, "
            "food insecurity, and insurance gaps. Coordinate maternal, SDOH, "
            "and pediatric next steps. Do not prescribe medications."
        ),
        metadata=metadata,
        headers=headers,
    )
    elapsed = time.monotonic() - t0
    checks = [
        pass_if("authenticated POST HTTP 200", resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:220]}"),
        pass_if("FHIR extension echoed", FHIR_EXTENSION_URI in resp.headers.get("X-A2A-Extensions", ""), str(resp.headers.get("X-A2A-Extensions"))),
    ]
    if resp.status_code != 200:
        return checks

    body = resp.json()
    text = response_text(body)
    upper = text.upper()
    checks.extend([
        pass_if("JSON-RPC id echoed", body.get("id") == "hard-clinical-1", str(body.get("id"))),
        pass_if("no JSON-RPC error", not body.get("error"), str(body.get("error"))),
        pass_if("A2A task completed", task_state(body) == "completed", str((body.get("result") or {}).get("status"))[:240]),
        pass_if("response text present", bool(text.strip()), "empty response"),
        pass_if("all 5T sections present", all(f"**{s}**" in text for s in FIVE_T_SECTIONS), text[:500]),
        pass_if("clinician review marker present", "CLINICIAN REVIEW" in upper, text[:500]),
        pass_if("maternal domain mentioned", "MATERNAL" in upper, text[:500]),
        pass_if("SDOH domain mentioned", "SDOH" in upper or "FOOD" in upper or "INSURANCE" in upper, text[:500]),
        pass_if("pediatric domain mentioned", "PEDIATRIC" in upper or "NEWBORN" in upper, text[:500]),
        pass_if("finished within timeout budget", elapsed < 180, f"{elapsed:.1f}s"),
    ])
    print(f"  {DIM}clinical call: {elapsed:.1f}s, {len(text)} chars{RESET}")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description="Hard MamaGuard A2A smoke test")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Agent URL (default: {DEFAULT_URL})")
    parser.add_argument("--api-key", default=None, help="API key; otherwise env/file fallback is used")
    parser.add_argument("--api-key-file", default=DEFAULT_API_KEY_FILE, help=f"API key file fallback (default: {DEFAULT_API_KEY_FILE})")
    parser.add_argument("--timeout", type=float, default=240.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    api_key = load_api_key(args.api_key, args.api_key_file)
    base_url = args.url.rstrip("/")
    print(f"{BOLD}=== Hard MamaGuard A2A Smoke ==={RESET}")
    print(f"  Target: {base_url}")
    print(f"  API key: present ({len(api_key)} chars, value hidden)")

    all_checks: list[Check] = []
    with httpx.Client(timeout=args.timeout) as client:
        groups = (
            lambda: check_agent_card(client, base_url),
            lambda: check_auth_and_protocol(client, base_url, api_key),
            lambda: check_clinical_completion(client, base_url, api_key),
        )
        for run_group in groups:
            group = run_group()
            all_checks.extend(group)
            for check in group:
                print_check(check)

    failed = [c for c in all_checks if not c.passed]
    print(f"\n{BOLD}Results{RESET}: {len(all_checks) - len(failed)}/{len(all_checks)} checks passed")
    if failed:
        print(f"{RED}HARD SMOKE FAILED{RESET}")
        sys.exit(1)
    print(f"{GREEN}HARD SMOKE PASSED{RESET}")


if __name__ == "__main__":
    main()
