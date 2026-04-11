"""Benchmark configuration."""

# Thresholds for clinical alert detection
BP_ELEVATED_SYSTOLIC = 140
BP_ELEVATED_DIASTOLIC = 90
BP_SEVERE_SYSTOLIC = 160
BP_SEVERE_DIASTOLIC = 110
HBA1C_DIABETES = 6.5
HBA1C_POORLY_CONTROLLED = 9.0
PREGNANCY_LOSS_HIGH_RISK = 2

# Scoring weights by category.
# The e2e and medagent categories dominate because they reflect real behavior;
# the Tier-1 deterministic categories are left at low weight so a run that
# includes all tiers is dominated by the real-world metrics.
CATEGORY_WEIGHTS = {
    # Tier 2b + Tier 3 — the real benchmarks
    "e2e": 0.40,
    "medagent": 0.30,
    "safety": 0.10,
    # Tier 1 — unit regression (kept for CI but low weight)
    "fhir_tools": 0.05,
    "clinical_reasoning": 0.05,
    "orchestration": 0.05,
    "other": 0.05,
}
