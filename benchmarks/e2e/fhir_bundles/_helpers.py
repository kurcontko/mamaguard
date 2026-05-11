"""Helpers for building FHIR R4 transaction bundles."""

from __future__ import annotations


def transaction_bundle(resources: list[dict]) -> dict:
    """
    Wrap a list of resources into a FHIR R4 transaction Bundle.
    Each resource must have a stable id so PUT is idempotent.
    """
    entries = []
    for res in resources:
        rtype = res["resourceType"]
        rid = res["id"]
        entries.append({
            "fullUrl": f"{rtype}/{rid}",
            "resource": res,
            "request": {
                "method": "PUT",
                "url": f"{rtype}/{rid}",
            },
        })
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries,
    }


def patient(
    id: str,
    given: str,
    family: str,
    birth_date: str,
    gender: str = "female",
    language: str | None = None,
) -> dict:
    p = {
        "resourceType": "Patient",
        "id": id,
        "name": [{"use": "official", "given": [given], "family": family}],
        "birthDate": birth_date,
        "gender": gender,
    }
    if language:
        p["communication"] = [
            {"language": {"text": language, "coding": [{"display": language}]}}
        ]
    return p


def condition(
    id: str,
    patient_id: str,
    snomed: str | None,
    text: str,
    clinical_status: str = "active",
    onset: str | None = None,
    abatement: str | None = None,
) -> dict:
    coding = []
    if snomed:
        coding.append({
            "system": "http://snomed.info/sct",
            "code": snomed,
            "display": text,
        })
    res = {
        "resourceType": "Condition",
        "id": id,
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": clinical_status,
            }],
        },
        "code": {"text": text, "coding": coding} if coding else {"text": text},
        "subject": {"reference": f"Patient/{patient_id}"},
    }
    if onset:
        res["onsetDateTime"] = onset
    if abatement:
        res["abatementDateTime"] = abatement
    return res


def bp_observation(id: str, patient_id: str, date: str, sys: float, dia: float) -> dict:
    return {
        "resourceType": "Observation",
        "id": id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "vital-signs",
                "display": "Vital Signs",
            }],
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "55284-4",
                "display": "Blood pressure panel",
            }],
            "text": "Blood pressure panel",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": date,
        "component": [
            {
                "code": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": "8480-6",
                        "display": "Systolic",
                    }],
                },
                "valueQuantity": {
                    "value": sys, "unit": "mmHg",
                    "system": "http://unitsofmeasure.org", "code": "mm[Hg]",
                },
            },
            {
                "code": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": "8462-4",
                        "display": "Diastolic",
                    }],
                },
                "valueQuantity": {
                    "value": dia, "unit": "mmHg",
                    "system": "http://unitsofmeasure.org", "code": "mm[Hg]",
                },
            },
        ],
    }


def hba1c_observation(id: str, patient_id: str, date: str, value: float) -> dict:
    return {
        "resourceType": "Observation",
        "id": id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory",
            }],
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "4548-4",
                "display": "Hemoglobin A1c/Hemoglobin.total in Blood",
            }],
            "text": "HbA1c",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": date,
        "valueQuantity": {
            "value": value, "unit": "%",
            "system": "http://unitsofmeasure.org", "code": "%",
        },
    }


def glucose_observation(id: str, patient_id: str, date: str, value: float) -> dict:
    return {
        "resourceType": "Observation",
        "id": id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory",
            }],
        }],
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "2339-0",
                "display": "Glucose [Mass/volume] in Blood",
            }],
            "text": "Glucose",
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": date,
        "valueQuantity": {
            "value": value, "unit": "mg/dL",
            "system": "http://unitsofmeasure.org", "code": "mg/dL",
        },
    }


def survey_observation(id: str, patient_id: str, date: str, name: str) -> dict:
    return {
        "resourceType": "Observation",
        "id": id,
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "survey",
            }],
        }],
        "code": {"text": name},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": date,
    }


def medication_request(id: str, patient_id: str, name: str, dosage: str, authored: str) -> dict:
    return {
        "resourceType": "MedicationRequest",
        "id": id,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {"text": name},
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": authored,
        "dosageInstruction": [{"text": dosage}],
    }


def immunization(id: str, patient_id: str, vaccine: str, date: str) -> dict:
    return {
        "resourceType": "Immunization",
        "id": id,
        "status": "completed",
        "vaccineCode": {"text": vaccine},
        "patient": {"reference": f"Patient/{patient_id}"},
        "occurrenceDateTime": date,
    }


def coverage(
    id: str,
    patient_id: str,
    cov_type: str,
    status: str = "active",
    start: str = "2025-01-01",
    end: str | None = None,
) -> dict:
    period = {"start": start}
    if end:
        period["end"] = end
    return {
        "resourceType": "Coverage",
        "id": id,
        "status": status,
        "type": {"text": cov_type},
        "beneficiary": {"reference": f"Patient/{patient_id}"},
        "payor": [{"display": cov_type}],
        "period": period,
    }


def related_child(
    id: str,
    mother_patient_id: str,
    child_patient_id: str,
    given: str,
    family: str,
    birth_date: str,
    gender: str = "unknown",
) -> dict:
    """RelatedPerson link used by MamaGuard's mother-to-child handoff tool."""
    return {
        "resourceType": "RelatedPerson",
        "id": id,
        "patient": {"reference": f"Patient/{mother_patient_id}"},
        "relationship": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                "code": "CHILD",
                "display": "child",
            }],
        }],
        "identifier": [{
            "system": "urn:mamaguard:linked-patient-id",
            "value": child_patient_id,
        }],
        "name": [{"use": "official", "given": [given], "family": family}],
        "birthDate": birth_date,
        "gender": gender,
    }
