#!/usr/bin/env python3
"""
Load all benchmark patient bundles into a running HAPI FHIR server.

Usage (from repo root):
    python3 scripts/load_bundles.py                         # default localhost:8090
    python3 scripts/load_bundles.py --fhir-url http://host:port/fhir
    python3 scripts/load_bundles.py --verify                # verify patients exist after load

Designed for the docker-compose local stack:
    docker compose -f mamaguard/docker-compose.yml up -d
    python3 scripts/load_bundles.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Ensure repo root is on sys.path so `benchmarks` package resolves.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx")
    sys.exit(1)

from benchmarks.e2e.fhir_bundles import ALL_PATIENTS


def wait_for_fhir(base_url: str, timeout: int = 120) -> bool:
    """Wait for FHIR metadata endpoint to respond 200."""
    metadata_url = f"{base_url}/metadata"
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(metadata_url, timeout=5)
            if resp.status_code == 200:
                elapsed = time.time() - start
                print(f"  FHIR server ready after {elapsed:.1f}s")
                return True
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass
        time.sleep(2)
    return False


def load_bundles(base_url: str) -> dict[str, int]:
    """POST all patient bundles as FHIR transactions. Returns {patient_id: resource_count}."""
    results = {}
    for patient_id, meta in ALL_PATIENTS.items():
        bundle = meta["bundle"]
        resp = httpx.post(
            base_url,
            json=bundle,
            headers={
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        count = len(bundle.get("entry", []))
        results[patient_id] = count
        print(f"  {meta['label']:30s} ({patient_id}): {count} resources")
    return results


def verify_patients(base_url: str) -> list[str]:
    """Check each patient exists. Returns list of missing patient IDs."""
    missing = []
    for patient_id, meta in ALL_PATIENTS.items():
        try:
            resp = httpx.get(
                f"{base_url}/Patient/{patient_id}",
                headers={"Accept": "application/fhir+json"},
                timeout=10,
            )
            if resp.status_code != 200:
                missing.append(patient_id)
                print(f"  MISSING: {meta['label']} ({patient_id}) — HTTP {resp.status_code}")
            else:
                print(f"  OK:      {meta['label']} ({patient_id})")
        except Exception as e:
            missing.append(patient_id)
            print(f"  ERROR:   {meta['label']} ({patient_id}) — {e}")
    return missing


def main():
    parser = argparse.ArgumentParser(description="Load FHIR bundles into HAPI")
    parser.add_argument(
        "--fhir-url",
        default=os.environ.get("HAPI_FHIR_URL", "http://localhost:8090/fhir"),
        help="FHIR server base URL (default: http://localhost:8090/fhir)",
    )
    parser.add_argument("--verify", action="store_true", help="Verify patients after loading")
    parser.add_argument("--verify-only", action="store_true", help="Only verify, don't load")
    parser.add_argument("--no-wait", action="store_true", help="Skip waiting for server readiness")
    args = parser.parse_args()

    base_url = args.fhir_url.rstrip("/")
    print(f"FHIR server: {base_url}")
    print(f"Patients:    {len(ALL_PATIENTS)}")
    print()

    if not args.no_wait:
        print("Waiting for FHIR server...")
        if not wait_for_fhir(base_url):
            print(f"ERROR: FHIR server not ready at {base_url}")
            sys.exit(1)
        print()

    if not args.verify_only:
        print(f"Loading {len(ALL_PATIENTS)} patient bundle(s)...")
        results = load_bundles(base_url)
        total_resources = sum(results.values())
        print(f"\nLoaded {len(results)} patients ({total_resources} resources total)")
        print()

    if args.verify or args.verify_only:
        print("Verifying patients...")
        missing = verify_patients(base_url)
        print()
        if missing:
            print(f"ERROR: {len(missing)} patient(s) missing")
            sys.exit(1)
        else:
            print(f"All {len(ALL_PATIENTS)} patients verified")


if __name__ == "__main__":
    main()
