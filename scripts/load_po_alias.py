#!/usr/bin/env python3
"""
Load Maria Santos under Prompt Opinion's workspace patient UUID into HAPI.

PO's BYO consultation tool injects the workspace patient UUID into the
A2A request body (e.g. ``Patient id: 526f3089-77ce-47bd-ab6a-70a54bcfeddb``)
but DOES NOT forward the FHIR session headers it displays in the workspace
UI — confirmed via direct curl 2026-05-10. So for the live PO demo to query
real FHIR data, we mirror the existing bench-maria-001 fixture under PO's
UUID on our own HAPI server.

This script:
  1. Deep-clones Maria's existing bundle.
  2. Rewrites the Patient resource ID and every ``Patient/bench-maria-001``
     reference to PO's UUID.
  3. Prefixes every other resource ID (Observations, Conditions, etc.) with
     ``po-`` so the clone coexists with the original bench fixtures without
     overwriting them — both patients stay queryable.
  4. RelatedPerson's ``target`` reference is preserved (still points at
     ``bench-baby-santos-001``), so ``find_linked_newborn`` discovers Lucas.

Usage:
    python3 scripts/load_po_alias.py \\
        --fhir-url https://ca-hapi-fhir.gentleisland-cc083285.eastus.azurecontainerapps.io/fhir \\
        --po-patient-id 526f3089-77ce-47bd-ab6a-70a54bcfeddb
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys

# Repo root on sys.path so `benchmarks.*` resolves.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx")
    sys.exit(1)

from benchmarks.e2e.fhir_bundles import maria_high_risk

SOURCE_PATIENT_ID = maria_high_risk.PATIENT_ID  # "bench-maria-001"
SOURCE_PATIENT_REF = f"Patient/{SOURCE_PATIENT_ID}"


def _rewrite_bundle_for_po(bundle: dict, po_patient_id: str, prefix: str) -> dict:
    """Return a cloned bundle where the Patient resource and all references
    point at ``po_patient_id``; non-Patient resource IDs are prefixed."""
    cloned = copy.deepcopy(bundle)
    target_patient_ref = f"Patient/{po_patient_id}"

    for entry in cloned.get("entry", []):
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            continue

        resource_type = resource.get("resourceType")
        old_id = resource.get("id")

        # 1. Rewrite the resource's own id.
        if resource_type == "Patient" and old_id == SOURCE_PATIENT_ID:
            new_id = po_patient_id
        elif old_id:
            new_id = f"{prefix}{old_id}"
        else:
            new_id = old_id

        resource["id"] = new_id

        # 2. Rewrite the fullUrl + request.url to match the new id.
        if "fullUrl" in entry:
            entry["fullUrl"] = f"{resource_type}/{new_id}"
        request = entry.get("request")
        if isinstance(request, dict) and "url" in request:
            request["url"] = f"{resource_type}/{new_id}"

        # 3. Walk every nested reference field; rewrite Maria-pointers only.
        _rewrite_patient_references(resource, target_patient_ref)

    return cloned


def _rewrite_patient_references(node, target_patient_ref: str) -> None:
    """Walk dict/list nodes recursively and replace every
    ``Patient/bench-maria-001`` reference value with ``target_patient_ref``.
    Other Patient references (e.g. Lucas) are preserved."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "reference" and value == SOURCE_PATIENT_REF:
                node[key] = target_patient_ref
            else:
                _rewrite_patient_references(value, target_patient_ref)
    elif isinstance(node, list):
        for item in node:
            _rewrite_patient_references(item, target_patient_ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fhir-url",
        required=True,
        help="HAPI FHIR base URL, e.g. https://ca-hapi-fhir.../fhir",
    )
    parser.add_argument(
        "--po-patient-id",
        required=True,
        help="PO workspace patient UUID to mirror Maria under",
    )
    parser.add_argument(
        "--prefix",
        default="po-",
        help="Resource ID prefix for the cloned bundle (default: po-)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rewritten bundle but skip the POST",
    )
    args = parser.parse_args()

    base_url = args.fhir_url.rstrip("/")
    cloned = _rewrite_bundle_for_po(
        maria_high_risk.BUNDLE,
        po_patient_id=args.po_patient_id,
        prefix=args.prefix,
    )

    entry_count = len(cloned.get("entry", []))
    print(f"Source patient : {SOURCE_PATIENT_ID}")
    print(f"Target patient : {args.po_patient_id}")
    print(f"Resource prefix: {args.prefix}")
    print(f"Entries        : {entry_count}")

    if args.dry_run:
        print()
        print(json.dumps(cloned, indent=2))
        return

    print(f"POST {base_url} ...")
    resp = httpx.post(
        base_url,
        json=cloned,
        headers={
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        print(f"ERROR: HTTP {resp.status_code}")
        print(resp.text[:2000])
        sys.exit(1)

    print(f"OK: HTTP {resp.status_code}")

    # Quick verification: GET the Patient resource we just created.
    verify_url = f"{base_url}/Patient/{args.po_patient_id}"
    v = httpx.get(verify_url, headers={"Accept": "application/fhir+json"}, timeout=10)
    if v.status_code == 200:
        print(f"VERIFIED: {verify_url} -> 200")
    else:
        print(f"WARN: Patient verify returned HTTP {v.status_code} at {verify_url}")
        sys.exit(1)


if __name__ == "__main__":
    main()
