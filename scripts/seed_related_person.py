#!/usr/bin/env python3
"""
Seed a FHIR RelatedPerson linking Maria Santos -> Lucas Santos.

Creates a RelatedPerson resource on the FHIR server that establishes
the mother-child relationship between Maria (bench-maria-001) and
Lucas (bench-baby-santos-001). This enables the find_linked_newborn
tool to discover the child from the mother's Patient ID.

Usage (from repo root):
    python3 scripts/seed_related_person.py                         # default localhost:8090
    python3 scripts/seed_related_person.py --fhir-url http://host:port/fhir
"""

from __future__ import annotations

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx")
    sys.exit(1)

# Patient IDs from benchmark bundles
MARIA_PATIENT_ID = "bench-maria-001"
LUCAS_PATIENT_ID = "bench-baby-santos-001"
RELATED_PERSON_ID = "rp-maria-lucas-001"

RELATED_PERSON_RESOURCE = {
    "resourceType": "RelatedPerson",
    "id": RELATED_PERSON_ID,
    "patient": {"reference": f"Patient/{MARIA_PATIENT_ID}"},
    "relationship": [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                    "code": "CHILD",
                    "display": "child",
                }
            ],
            "text": "child",
        }
    ],
    "name": [{"family": "Santos", "given": ["Lucas"]}],
    "birthDate": "2026-02-09",
    "gender": "male",
    "identifier": [
        {
            "system": "urn:mamaguard:linked-patient-id",
            "value": LUCAS_PATIENT_ID,
        }
    ],
}


def seed_related_person(base_url: str) -> dict:
    """PUT the RelatedPerson resource (idempotent)."""
    url = f"{base_url}/RelatedPerson/{RELATED_PERSON_ID}"
    resp = httpx.put(
        url,
        json=RELATED_PERSON_RESOURCE,
        headers={
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(
        description="Seed RelatedPerson linking Maria -> Lucas"
    )
    parser.add_argument(
        "--fhir-url",
        default=os.environ.get("HAPI_FHIR_URL", "http://localhost:8090/fhir"),
        help="FHIR server base URL (default: http://localhost:8090/fhir)",
    )
    args = parser.parse_args()

    base_url = args.fhir_url.rstrip("/")
    print(f"FHIR server: {base_url}")
    print(f"Linking: Maria ({MARIA_PATIENT_ID}) -> Lucas ({LUCAS_PATIENT_ID})")
    print()

    result = seed_related_person(base_url)
    rid = result.get("id", RELATED_PERSON_ID)
    print(f"  RelatedPerson/{rid} created/updated")
    print(f"  patient: Patient/{MARIA_PATIENT_ID}")
    print(f"  relationship: CHILD")
    print(f"  linked child: Patient/{LUCAS_PATIENT_ID}")
    print()
    print("Done. find_linked_newborn can now discover Lucas from Maria's record.")


if __name__ == "__main__":
    main()
