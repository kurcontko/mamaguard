"""
SHARP context adapter for MCP.

Bridges FHIR session credentials from MCP tool arguments into the
ToolContext.state shape expected by shared/tools/*.

The SHARP extension spec (March 2026) passes EHR session context as:
  { "fhirUrl": "...", "fhirToken": "...", "patientId": "..." }

For MCP invocations the caller passes these as explicit tool parameters.
This module wraps them into a minimal ToolContext stand-in so the shared
tool implementations can be reused without modification.
"""

from __future__ import annotations


class FhirContext:
    """
    Minimal stand-in for google.adk.tools.ToolContext.

    Only the `.state` dict is used by shared/tools implementations.
    """

    def __init__(self, fhir_url: str, fhir_token: str, patient_id: str) -> None:
        self.state: dict[str, str] = {
            "fhir_url": fhir_url.rstrip("/"),
            "fhir_token": fhir_token,
            "patient_id": patient_id,
        }

    @classmethod
    def from_sharp(cls, sharp_context: dict) -> FhirContext:
        """
        Build a FhirContext from a SHARP extension context dict.

        Expected shape:
            { "fhirUrl": "...", "fhirToken": "...", "patientId": "..." }
        """
        return cls(
            fhir_url=sharp_context.get("fhirUrl", ""),
            fhir_token=sharp_context.get("fhirToken", ""),
            patient_id=sharp_context.get("patientId", ""),
        )
