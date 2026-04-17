#!/usr/bin/env python3
"""
Memory-recall demo -- the hackathon differentiator.

Seeds a prior-visit agent memory note on the FHIR server (as a
`DocumentReference` with category `clinical-reasoning-history`), then
prints what MamaGuard's `inject_memory_block` callback will lift back
into the agent's context on the next run.

This is the "wow" moment: no competitor carries cross-session state,
and MamaGuard's state lives *inside FHIR* — no sidecar DB, full HIPAA
boundary inheritance, readable by any other agent on the marketplace.

Three usage modes:

  # 1. Seed + preview (no agent call) -- deterministic, no LLM required
  uv run python scripts/demo_memory_recall.py --seed-only

  # 2. Seed + simulate what the agent will see on visit 2
  uv run python scripts/demo_memory_recall.py

  # 3. Clean up the seeded note afterwards
  uv run python scripts/demo_memory_recall.py --cleanup

Requires HAPI_FHIR_URL env var or --fhir-url (default http://localhost:8090/fhir).
Target patient defaults to bench-maria-001.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


DEFAULT_FHIR_URL = os.environ.get("HAPI_FHIR_URL", "http://localhost:8090/fhir")
DEFAULT_PATIENT_ID = "bench-maria-001"
MEMORY_SYSTEM = "http://mamaguard.ai/codes"
MEMORY_TYPE_CODE = "agent-memory-note"
MEMORY_CATEGORY_CODE = "clinical-reasoning-history"
SEED_TAG = "mamaguard-demo-memory-recall"


SEED_NOTE_MARKDOWN = textwrap.dedent("""\
    ## Visit 2026-03-10 — Dr. Kim

    **Decision:** Declined metformin titration.

    **Reason:** Patient reported severe GI intolerance at 500 mg bid. Switched
    focus to lifestyle-only management while monitoring HbA1c. Patient also
    declined referral to endocrinology, preferring to defer until postpartum
    period.

    **Plan carryover:**
    - Continue BP monitoring at home (Omron device dispensed)
    - HbA1c recheck in 6 weeks (last 7.2%)
    - Housing referral to Helping Hands submitted 2026-03-12, awaiting response
    - Patient primary language: French — interpreter confirmed for all visits

    **Flag for future MamaGuard runs:** Do NOT re-recommend metformin. Patient
    has explicitly declined due to intolerance; any antidiabetic escalation
    must be coordinated with Dr. Kim (endocrinology referral on hold).
""")


def _headers(token: str = "demo-token") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
    }


def _build_memory_doc(patient_id: str, content_md: str, when: datetime) -> dict[str, Any]:
    b64 = base64.b64encode(content_md.encode("utf-8")).decode("ascii")
    return {
        "resourceType": "DocumentReference",
        "status": "current",
        "subject": {"reference": f"Patient/{patient_id}"},
        "date": when.isoformat(),
        "type": {
            "coding": [
                {"system": MEMORY_SYSTEM, "code": MEMORY_TYPE_CODE},
                {"system": MEMORY_SYSTEM, "code": "trajectory-elevated"},
            ]
        },
        "category": [
            {
                "coding": [
                    {"system": MEMORY_SYSTEM, "code": MEMORY_CATEGORY_CODE}
                ]
            }
        ],
        "author": [{"display": "MamaGuard v3"}],
        "meta": {
            "tag": [
                {"system": MEMORY_SYSTEM, "code": SEED_TAG}
            ]
        },
        "content": [
            {
                "attachment": {
                    "contentType": "text/markdown",
                    "data": b64,
                }
            }
        ],
    }


def seed_memory(fhir_url: str, patient_id: str) -> str:
    """POST the prior-visit memory note. Returns the created DocumentReference id."""
    when = datetime.now(timezone.utc) - timedelta(days=38)
    body = _build_memory_doc(patient_id, SEED_NOTE_MARKDOWN, when)
    resp = httpx.post(
        f"{fhir_url}/DocumentReference",
        json=body,
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    created = resp.json()
    return created["id"]


def read_memory_as_agent_would(fhir_url: str, patient_id: str, count: int = 5) -> list[dict]:
    """Mimic the `inject_memory_block` callback's query against HAPI."""
    resp = httpx.get(
        f"{fhir_url}/DocumentReference",
        params={
            "subject": f"Patient/{patient_id}",
            "category": MEMORY_CATEGORY_CODE,
            "_sort": "-date",
            "_count": str(count),
        },
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    bundle = resp.json()
    notes: list[dict] = []
    for entry in bundle.get("entry", []) or []:
        res = entry.get("resource", {})
        content = (res.get("content") or [{}])[0]
        b64 = (content.get("attachment") or {}).get("data", "")
        try:
            decoded = base64.b64decode(b64).decode("utf-8") if b64 else ""
        except Exception:
            decoded = ""
        subtype = ""
        for c in (res.get("type") or {}).get("coding", []):
            if c.get("code") not in (MEMORY_TYPE_CODE, ""):
                subtype = c.get("code", "")
                break
        notes.append({
            "date": res.get("date", ""),
            "subtype": subtype,
            "resource_id": res.get("id", ""),
            "markdown": decoded,
        })
    return notes


def cleanup_seeded(fhir_url: str, patient_id: str = DEFAULT_PATIENT_ID) -> int:
    """Delete demo-tagged DocumentReferences for a patient.

    HAPI's `_tag` search is often not indexed, so we fetch the patient's
    memory bundle and filter client-side by our demo tag.
    """
    resp = httpx.get(
        f"{fhir_url}/DocumentReference",
        params={
            "subject": f"Patient/{patient_id}",
            "category": MEMORY_CATEGORY_CODE,
            "_count": "50",
        },
        headers=_headers(),
        timeout=15,
    )
    if resp.status_code != 200:
        return 0
    bundle = resp.json()
    deleted = 0
    for entry in bundle.get("entry", []) or []:
        res = entry.get("resource", {})
        tags = (res.get("meta") or {}).get("tag") or []
        has_demo_tag = any(
            t.get("system") == MEMORY_SYSTEM and t.get("code") == SEED_TAG
            for t in tags
        )
        if not has_demo_tag:
            continue
        res_id = res.get("id", "")
        if not res_id:
            continue
        d = httpx.delete(
            f"{fhir_url}/DocumentReference/{res_id}",
            headers=_headers(),
            timeout=15,
        )
        if d.status_code in (200, 204):
            deleted += 1
    return deleted


def _print_header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}━━ {title} ━━{RESET}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fhir-url", default=DEFAULT_FHIR_URL)
    parser.add_argument("--patient-id", default=DEFAULT_PATIENT_ID)
    parser.add_argument("--seed-only", action="store_true",
                        help="Write the prior-visit memory note but do not simulate recall")
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete all demo-tagged memory notes and exit")
    args = parser.parse_args()

    if args.cleanup:
        _print_header("Cleanup: removing demo memory notes")
        removed = cleanup_seeded(args.fhir_url, args.patient_id)
        print(f"  removed {removed} DocumentReference(s)")
        return 0

    _print_header("Step 1 / Seed prior-visit memory note")
    print(f"  FHIR:    {args.fhir_url}")
    print(f"  Patient: {args.patient_id}")
    print(f"  Note:    Dr. Kim declined metformin (GI intolerance), 38 days ago")
    try:
        doc_id = seed_memory(args.fhir_url, args.patient_id)
    except httpx.HTTPError as exc:
        print(f"{YELLOW}  FHIR write failed: {exc}{RESET}")
        return 2
    print(f"  {GREEN}seeded DocumentReference/{doc_id}{RESET}")

    if args.seed_only:
        print(f"\n{DIM}  --seed-only: skipping recall simulation. "
              f"Run without the flag (or hit the live A2A endpoint) to see MamaGuard "
              f"lift this into context.{RESET}")
        return 0

    _print_header("Step 2 / What MamaGuard's inject_memory_block will lift into context")
    notes = read_memory_as_agent_would(args.fhir_url, args.patient_id)
    if not notes:
        print(f"{YELLOW}  no memory notes found -- seed did not index{RESET}")
        return 2
    print(f"  {len(notes)} note(s) retrieved (most recent first):\n")
    for i, note in enumerate(notes, 1):
        subtype = note.get("subtype") or "trajectory"
        print(f"  {BOLD}[{i}] {note['date']}  ({subtype}){RESET}")
        for line in note["markdown"].splitlines()[:8]:
            print(f"      {DIM}{line}{RESET}")
        if len(note["markdown"].splitlines()) > 8:
            print(f"      {DIM}...{RESET}")
        print()

    _print_header("Step 3 / What this changes in the next agent run")
    print(textwrap.dedent(f"""\
        On the next `/run` against Patient/{args.patient_id}, the orchestrator's
        `before_model_callback` chain calls `inject_memory_block`, which injects
        the {len(notes)} note(s) above as a `<patient-memory>` block at the top of
        the system prompt.

        The agent then:
        - Will NOT re-recommend metformin (the note explicitly flags it as declined)
        - Will reference Dr. Kim's prior decision in the Talk section
        - Will incorporate the housing referral status into SDOH assessment
        - Will default to the French interpreter without re-asking

        No competitor submission (AuthPilot, Clinical Oracle, Aether, etc.) has
        this capability. MamaGuard's memory lives inside FHIR itself -- zero new
        infrastructure, full HIPAA boundary inheritance, readable by any other
        A2A agent via a standard DocumentReference query.

        To see it live, run:
            uv run python scripts/smoke_test.py --patient-id {args.patient_id}

        To clean up after the demo:
            uv run python scripts/demo_memory_recall.py --cleanup
    """))
    return 0


if __name__ == "__main__":
    sys.exit(main())
