"""
MedAgentBench-style benchmark cases.

Methodology mirrors Stanford MedAgentBench (ai.nejm.org/doi/10.1056/AIdbp2500144,
github.com/stanfordmlgroup/MedAgentBench): two task families (query + action)
against a FHIR-compliant virtual EHR, scored on tool-selection correctness
and answer correctness.

Our implementation uses synthetic patient Bundles (see benchmarks/e2e/fhir_bundles)
rather than MIMIC-IV-FHIR (which requires PhysioNet credentialed access).
Scores are not directly comparable to the published MedAgentBench leaderboard,
but the task structure is the same — giving us a methodology that reviewers
(e.g. Josh Mandel, Piyush Mathur) will recognize.
"""
