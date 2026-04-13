#!/usr/bin/env python3
"""MamaGuard MCP server smoke test -- pre-publish validation.

Starts the MCP server in-process, sends 3 tool invocations via the MCP
protocol with mock FHIR responses, and verifies each response has the
expected shape.

Tested tools:
  1. get_patient_summary
  2. get_maternal_risk_profile
  3. find_sdoh_resources

Usage:
    python scripts/smoke_test_mcp.py            # default (quiet)
    python scripts/smoke_test_mcp.py --verbose   # print response previews

Exit 0 if all checks pass, exit 1 if any fail.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from unittest.mock import patch

import anyio
from anyio import create_memory_object_stream
from mcp.shared.message import SessionMessage
from mcp.client.session import ClientSession
from mcp.types import Implementation

# -- ANSI colors ---------------------------------------------------------------

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# -- Mock FHIR data -----------------------------------------------------------

MOCK_PATIENT = {
    "resourceType": "Patient",
    "id": "smoke-maria-001",
    "name": [{"use": "official", "family": "Garcia", "given": ["Maria"]}],
    "birthDate": "1990-03-15",
    "gender": "female",
}

MOCK_CONDITIONS_BUNDLE = {
    "resourceType": "Bundle",
    "entry": [
        {
            "resource": {
                "resourceType": "Condition",
                "clinicalStatus": {
                    "coding": [{"code": "active"}],
                },
                "code": {
                    "coding": [{"system": "http://snomed.info/sct", "code": "398254007"}],
                    "text": "Pre-eclampsia",
                },
                "onsetDateTime": "2025-06-15",
            }
        }
    ],
}

MOCK_MEDS_BUNDLE = {
    "resourceType": "Bundle",
    "entry": [
        {
            "resource": {
                "resourceType": "MedicationRequest",
                "status": "active",
                "medicationCodeableConcept": {"text": "Labetalol 200mg"},
                "dosageInstruction": [{"text": "twice daily"}],
                "authoredOn": "2025-01-10",
            }
        }
    ],
}

MOCK_VITALS_BUNDLE = {
    "resourceType": "Bundle",
    "entry": [
        {
            "resource": {
                "resourceType": "Observation",
                "effectiveDateTime": "2025-10-01",
                "code": {
                    "coding": [{"system": "http://loinc.org", "code": "55284-4"}],
                },
                "component": [
                    {
                        "code": {"coding": [{"code": "8480-6"}]},
                        "valueQuantity": {"value": 142, "unit": "mmHg"},
                    },
                    {
                        "code": {"coding": [{"code": "8462-4"}]},
                        "valueQuantity": {"value": 88, "unit": "mmHg"},
                    },
                ],
            }
        }
    ],
}

MOCK_EMPTY_BUNDLE = {"resourceType": "Bundle", "entry": []}

# SHARP credentials for all invocations
SHARP = {
    "fhir_url": "https://smoke-test.example.org/fhir",
    "fhir_token": "smoke-bearer-token",
    "patient_id": "smoke-maria-001",
}


# -- Result tracking -----------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ToolResult:
    name: str
    checks: list[CheckResult] = field(default_factory=list)
    response_data: dict | None = None
    error: str | None = None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks) and self.error is None


# -- Tool invocation definitions -----------------------------------------------

TOOL_INVOCATIONS = [
    {
        "name": "get_patient_summary",
        "description": "Patient summary retrieval",
        "args": {**SHARP},
        "mock_fhir_get_responses": [
            MOCK_PATIENT,
            MOCK_CONDITIONS_BUNDLE,
            MOCK_MEDS_BUNDLE,
            MOCK_VITALS_BUNDLE,
        ],
        "checks": [
            ("status", "success"),
            ("patient_id", "smoke-maria-001"),
        ],
        "required_keys": ["status", "patient_id", "name"],
    },
    {
        "name": "get_maternal_risk_profile",
        "description": "Maternal risk profile generation",
        "args": {**SHARP},
        # get_maternal_risk_profile makes multiple FHIR calls internally
        # (patient, conditions, meds, vitals/BP, vitals/glucose, pregnancies)
        "mock_fhir_get_responses": [
            MOCK_PATIENT,
            MOCK_CONDITIONS_BUNDLE,
            MOCK_MEDS_BUNDLE,
            MOCK_VITALS_BUNDLE,
            MOCK_EMPTY_BUNDLE,  # glucose
            MOCK_EMPTY_BUNDLE,  # pregnancy history
        ],
        "checks": [
            ("status", "success"),
        ],
        "required_keys": ["status"],
    },
    {
        "name": "find_sdoh_resources",
        "description": "SDOH resource lookup",
        "args": {
            **SHARP,
            "category_or_code": "Z59.0",
            "zip_code": "02139",
        },
        "mock_fhir_get_responses": None,  # uses offline fallback, no FHIR calls
        "checks": [
            ("status", "success"),
            ("category", "housing"),
        ],
        "required_keys": ["status", "category", "resource_count", "resources"],
    },
]


# -- MCP client helper ---------------------------------------------------------


async def _create_mcp_session():
    """Create an in-memory MCP client<->server pair."""
    from mamaguard.mcp_server.server import mcp as mcp_server

    client_to_server_send, client_to_server_recv = (
        create_memory_object_stream[SessionMessage | Exception](100)
    )
    server_to_client_send, server_to_client_recv = (
        create_memory_object_stream[SessionMessage | Exception](100)
    )

    low_server = mcp_server._mcp_server
    init_opts = low_server.create_initialization_options()

    client = ClientSession(
        read_stream=server_to_client_recv,
        write_stream=client_to_server_send,
        client_info=Implementation(name="mamaguard-mcp-smoke", version="0.1"),
    )

    return low_server, init_opts, client_to_server_recv, server_to_client_send, client


# -- Smoke test runner ---------------------------------------------------------


async def _run_tool_invocation(
    client: ClientSession,
    invocation: dict,
    verbose: bool,
) -> ToolResult:
    """Invoke one MCP tool and validate the response."""
    tr = ToolResult(name=invocation["description"])

    try:
        mock_responses = invocation["mock_fhir_get_responses"]

        if mock_responses is not None:
            with patch("mamaguard.shared.tools.fhir_base._fhir_get") as mock_get:
                mock_get.side_effect = list(mock_responses)
                result = await client.call_tool(
                    invocation["name"], invocation["args"]
                )
        else:
            # No mock needed (e.g. find_sdoh_resources uses offline fallback)
            import os
            os.environ.pop("MAMAGUARD_SDOH_API_URL", None)
            result = await client.call_tool(
                invocation["name"], invocation["args"]
            )

        # Parse the response
        if not result.content:
            tr.error = "Empty response content"
            tr.checks.append(CheckResult("Non-empty response", False, "No content"))
            return tr

        text = result.content[0].text
        data = json.loads(text)
        tr.response_data = data

        if verbose:
            print(f"  {DIM}Response: {json.dumps(data, indent=2)[:500]}{RESET}")

        # Check: valid JSON parsed
        tr.checks.append(CheckResult("Valid JSON response", True))

        # Check: required keys present
        for key in invocation["required_keys"]:
            present = key in data
            tr.checks.append(
                CheckResult(
                    f"Key '{key}' present",
                    present,
                    "" if present else f"Missing key '{key}' in response",
                )
            )

        # Check: expected values
        for key, expected in invocation["checks"]:
            actual = data.get(key)
            match = actual == expected
            tr.checks.append(
                CheckResult(
                    f"{key}={expected!r}",
                    match,
                    "" if match else f"Expected {expected!r}, got {actual!r}",
                )
            )

    except Exception as e:
        tr.error = str(e)
        tr.checks.append(CheckResult("Tool invocation succeeded", False, str(e)))

    return tr


async def _run_all(verbose: bool) -> list[ToolResult]:
    """Run all MCP tool invocations inside a single in-memory session."""
    low_server, init_opts, c2s_recv, s2c_send, client = await _create_mcp_session()
    results: list[ToolResult] = []

    async with anyio.create_task_group() as tg:
        tg.start_soon(low_server.run, c2s_recv, s2c_send, init_opts)

        async with client:
            init_result = await client.initialize()
            print(f"  {DIM}Server: {init_result.serverInfo.name} v{init_result.serverInfo.version}{RESET}")

            # Verify tool count
            tools_result = await client.list_tools()
            tool_count = len(tools_result.tools)
            print(f"  {DIM}Tools available: {tool_count}{RESET}")

            for i, invocation in enumerate(TOOL_INVOCATIONS, 1):
                print(f"\n{BOLD}[{i}/{len(TOOL_INVOCATIONS)}] {invocation['description']}{RESET}")
                print(f"  {DIM}Tool: {invocation['name']}{RESET}")

                tr = await _run_tool_invocation(client, invocation, verbose)
                results.append(tr)

                # Print check results
                for check in tr.checks:
                    if check.passed:
                        print(f"  {GREEN}PASS{RESET} {check.name}")
                    else:
                        print(f"  {RED}FAIL{RESET} {check.name}: {check.detail}")

                if tr.error:
                    print(f"  {RED}ERROR: {tr.error}{RESET}")

        tg.cancel_scope.cancel()

    return results


# -- Main ----------------------------------------------------------------------


def main() -> None:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print(f"{BOLD}=== MamaGuard MCP Smoke Test ==={RESET}")
    print(f"  Mode: in-process (no server required)")
    print(f"  Tools under test: {', '.join(t['name'] for t in TOOL_INVOCATIONS)}")

    results = asyncio.run(_run_all(verbose))

    # Summary
    total_checks = sum(len(r.checks) for r in results)
    passed_checks = sum(sum(1 for c in r.checks if c.passed) for r in results)
    failed_tools = [r for r in results if not r.passed]

    print(f"\n{BOLD}=== Results ==={RESET}")
    for r in results:
        status = f"{GREEN}PASS{RESET}" if r.passed else f"{RED}FAIL{RESET}"
        print(f"  {status} {r.name}")

    print(f"\n  Checks: {passed_checks}/{total_checks} passed")
    print(f"  Tools:  {len(results) - len(failed_tools)}/{len(results)} passed")

    if failed_tools:
        print(f"\n  {RED}MCP SMOKE TEST FAILED{RESET}")
        sys.exit(1)
    else:
        print(f"\n  {GREEN}MCP SMOKE TEST PASSED{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
