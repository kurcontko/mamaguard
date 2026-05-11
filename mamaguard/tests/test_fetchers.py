"""
Unit tests for the v2 async domain fetchers.

These tests patch the underlying sync tools so no real FHIR server is
needed.  They verify:
  - each fetcher aggregates tool results into the correct dataclass
  - errors from one tool do not prevent other tools from contributing
  - pediatric fetch follows the find_linked_newborn -> child-context chain
  - SDOH category inference works across the three signal lists
"""

from __future__ import annotations

import asyncio
from unittest import mock

import pytest

from mamaguard.shared import fetchers as f
from mamaguard.shared.fetchers import (
    MaternalData,
    PediatricData,
    SdohData,
    _infer_sdoh_categories,
    fetch_maternal_data,
    fetch_pediatric_data,
    fetch_sdoh_data,
)


@pytest.fixture(autouse=True)
def _run_fetcher_threads_inline(monkeypatch):
    async def _inline_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(f.asyncio, "to_thread", _inline_to_thread)


# -- Maternal ----------------------------------------------------------------

def test_maternal_fetch_happy_path():
    with mock.patch.object(f, "get_patient_summary") as ps, \
         mock.patch.object(f, "get_maternal_risk_profile") as rp, \
         mock.patch.object(f, "get_active_medications") as am:
        ps.return_value = {"status": "success", "patient_id": "mom-1"}
        rp.return_value = {"status": "success", "bp_trend": {"latest": "162/104"}}
        am.return_value = {"status": "success", "medications": []}

        data = asyncio.run(fetch_maternal_data("https://fhir", "tok", "mom-1"))

    assert isinstance(data, MaternalData)
    assert data.status == "ok"
    assert data.errors == []
    assert data.patient_summary["patient_id"] == "mom-1"
    assert data.risk_profile["bp_trend"]["latest"] == "162/104"


def test_maternal_fetch_partial_failure():
    with mock.patch.object(f, "get_patient_summary") as ps, \
         mock.patch.object(f, "get_maternal_risk_profile") as rp, \
         mock.patch.object(f, "get_active_medications") as am:
        ps.return_value = {"status": "success", "patient_id": "mom-1"}
        rp.return_value = {"status": "error", "error_message": "FHIR 503"}
        am.return_value = {"status": "success", "medications": []}

        data = asyncio.run(fetch_maternal_data("https://fhir", "tok", "mom-1"))

    assert data.status == "partial"
    assert any("risk_profile" in e for e in data.errors)
    assert data.patient_summary  # other domain succeeded
    assert data.medications


# -- Pediatric ---------------------------------------------------------------

def test_pediatric_no_linked_child():
    with mock.patch.object(f, "find_linked_newborn") as fln:
        fln.return_value = {
            "status": "success",
            "mother_patient_id": "mom-1",
            "count": 0,
            "linked_newborns": [],
        }
        data = asyncio.run(fetch_pediatric_data("https://fhir", "tok", "mom-1"))

    assert isinstance(data, PediatricData)
    assert data.status == "no_linked_child"
    assert data.linked_child is None


def test_pediatric_with_linked_child():
    with mock.patch.object(f, "find_linked_newborn") as fln, \
         mock.patch.object(f, "get_immunization_gaps") as ig, \
         mock.patch.object(f, "get_developmental_screening_status") as dss, \
         mock.patch.object(f, "get_care_gaps") as cg:
        fln.return_value = {
            "status": "success",
            "count": 1,
            "linked_newborns": [{
                "child_patient_id": "baby-1",
                "name": "Baby Smith",
                "birth_date": "2026-02-09",
            }],
        }
        ig.return_value = {"status": "success", "due": ["DTaP"]}
        dss.return_value = {"status": "success", "due": []}
        cg.return_value = {"status": "success", "gaps": []}

        data = asyncio.run(fetch_pediatric_data("https://fhir", "tok", "mom-1"))

    assert data.status == "ok"
    assert data.linked_child["child_patient_id"] == "baby-1"
    assert data.immunizations["due"] == ["DTaP"]
    # Child-context was used: assert all three tools got called with the
    # state carrying baby-1 (not mom-1)
    for call in ig.call_args_list + dss.call_args_list + cg.call_args_list:
        assert call.args[0].state["patient_id"] == "baby-1"


def test_pediatric_linked_newborn_error_fails_fast():
    with mock.patch.object(f, "find_linked_newborn") as fln:
        fln.return_value = {"status": "error", "error_message": "boom"}
        data = asyncio.run(fetch_pediatric_data("https://fhir", "tok", "mom-1"))

    assert data.status == "error"
    assert any("linked_newborn" in e for e in data.errors)


# -- SDOH --------------------------------------------------------------------

def test_sdoh_category_inference_covers_all_signals():
    screening = {
        "data": {
            "coverage": [],                              # -> insurance
            "language": "Spanish",                       # -> language
            "sdoh_conditions": [{"condition": "Homelessness"}],  # -> housing
            "risk_factors": ["food insecurity reported"],        # -> food
        }
    }
    cats = _infer_sdoh_categories(screening)
    assert "insurance" in cats
    assert "language" in cats
    assert "housing" in cats
    assert "food" in cats


def test_sdoh_category_inference_empty_when_no_signals():
    screening = {
        "data": {
            "coverage": [{"type": "Medicaid"}],  # has coverage
            "language": "English",
            "sdoh_conditions": [],
            "risk_factors": [],
        }
    }
    assert _infer_sdoh_categories(screening) == []


def test_sdoh_fetch_calls_resources_for_each_category():
    with mock.patch.object(f, "get_sdoh_screening") as gss, \
         mock.patch.object(f, "get_care_gaps") as cg, \
         mock.patch.object(f, "find_sdoh_resources") as fsr:
        gss.return_value = {
            "status": "success",
            "data": {
                "coverage": [],
                "language": "Spanish",
                "sdoh_conditions": [],
                "risk_factors": [],
            },
        }
        cg.return_value = {"status": "success", "gaps": []}
        fsr.return_value = {
            "status": "success",
            "category": "insurance",
            "resources": [],
        }

        data = asyncio.run(fetch_sdoh_data("https://fhir", "tok", "mom-1"))

    assert isinstance(data, SdohData)
    assert data.status == "ok"
    # Two categories inferred: insurance + language -> 2 lookup calls
    assert fsr.call_count == 2
    assert {r["category"] for r in data.resources} == {"insurance", "language"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
