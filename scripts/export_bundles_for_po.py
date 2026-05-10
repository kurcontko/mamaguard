#!/usr/bin/env python3
"""
Export benchmark FHIR bundles to standalone .json files for upload via the
Prompt Opinion Marketplace "Import" button on the Patients page.

Each output file is the same FHIR R4 transaction Bundle that scripts/load_bundles.py
POSTs to HAPI — just serialised to disk so the PO web UI can take it.

Usage:
    python3 scripts/export_bundles_for_po.py
    python3 scripts/export_bundles_for_po.py --only bench-maria-001 bench-baby-santos-001
    python3 scripts/export_bundles_for_po.py --out-dir mamaguard/marketplace/po_imports
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import uuid

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.e2e.fhir_bundles import ALL_PATIENTS


def _slug(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    return cleaned or "patient"


def _rewrite_refs(node, ref_map: dict[str, str]) -> None:
    """Walk a resource dict in place; rewrite {"reference": "Type/id"} → urn:uuid."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "reference" and isinstance(value, str) and value in ref_map:
                node[key] = ref_map[value]
            else:
                _rewrite_refs(value, ref_map)
    elif isinstance(node, list):
        for item in node:
            _rewrite_refs(item, ref_map)


def to_post_bundle(bundle: dict) -> dict:
    """Convert a PUT-style transaction Bundle (stable ids, idempotent on HAPI)
    to a POST/urn:uuid form that FHIR servers without `updateCreate` accept
    (e.g. Prompt Opinion's import endpoint).

    - Strips Resource.id (server assigns).
    - Rewrites every {"reference": "Type/id"} pointing at a bundle-internal
      resource to its urn:uuid fullUrl.
    - Per-entry request becomes POST <ResourceType>.

    Identifiers (RelatedPerson.identifier with system urn:mamaguard:...) are
    preserved verbatim. Mother→child resolution must use Patient.identifier on
    the server, not the original `bench-*` ids.
    """
    ref_map: dict[str, str] = {}
    new_entries: list[dict] = []

    for entry in bundle.get("entry", []):
        res = entry["resource"]
        rtype = res["resourceType"]
        rid = res.get("id")
        urn = f"urn:uuid:{uuid.uuid4()}"
        if rid:
            ref_map[f"{rtype}/{rid}"] = urn
        new_entries.append({"_urn": urn, "_resource": res, "_rtype": rtype})

    out_entries: list[dict] = []
    for staged in new_entries:
        res = copy.deepcopy(staged["_resource"])
        res.pop("id", None)
        _rewrite_refs(res, ref_map)
        out_entries.append({
            "fullUrl": staged["_urn"],
            "resource": res,
            "request": {"method": "POST", "url": staged["_rtype"]},
        })

    return {"resourceType": "Bundle", "type": "transaction", "entry": out_entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default=os.path.join(_REPO_ROOT, "mamaguard/marketplace/po_imports"),
        help="Directory to write JSON files into.",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="Subset of patient IDs to export (default: all).",
    )
    parser.add_argument(
        "--keep-put",
        action="store_true",
        help="Emit the original PUT/stable-id bundle (HAPI-style). "
             "Default rewrites to POST + urn:uuid for FHIR servers that "
             "reject updateCreate (e.g. Prompt Opinion).",
    )
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    targets = ALL_PATIENTS
    if args.only:
        unknown = [pid for pid in args.only if pid not in ALL_PATIENTS]
        if unknown:
            print(f"Unknown patient IDs: {unknown}", file=sys.stderr)
            return 2
        targets = {pid: ALL_PATIENTS[pid] for pid in args.only}

    for patient_id, meta in targets.items():
        slug = _slug(meta["label"])
        path = os.path.join(args.out_dir, f"{slug}.json")
        bundle = meta["bundle"] if args.keep_put else to_post_bundle(meta["bundle"])
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, indent=2)
            fh.write("\n")
        entry_count = len(bundle.get("entry", []))
        method = "PUT" if args.keep_put else "POST"
        print(f"  {patient_id:30s} -> {path}  ({entry_count} resources, {method})")

    print(f"\nWrote {len(targets)} bundle(s) to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
