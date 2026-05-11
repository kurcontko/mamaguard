# Why MamaGuard

A judge-facing summary mapping MamaGuard's capabilities to the three hackathon judging criteria.

---

## 1. AI Factor — GenAI beyond what rules can do

A naive LLM given the same FHIR data scores **52%** on clinical rubrics. MamaGuard scores **82%** — a **+30% lift** validated by DeepSeek v3.2 judge across three severity tiers.

| Dimension | Naive LLM | MamaGuard | Lift |
|-----------|-----------|-----------|------|
| Clinical accuracy | 65% | 85% | +20% |
| Risk assessment | 47% | 82% | +35% |
| Safety | 38% | 80% | +42% |
| Completeness | 45% | 80% | +35% |
| Output quality | 65% | 83% | +18% |

**What rules can't do, MamaGuard can:**

- **Cross-resource synthesis** — A rule engine flags BP >140/90. MamaGuard reads 6 pregnancies with 5 losses, concurrent diabetes, postpartum timing, and housing instability — then explains why the combination is dangerous, citing 7+ FHIR evidence references.
- **SDOH-clinical integration** — Connects a Medicaid gap + language barrier + food insecurity + postpartum BP crisis into a unified outreach plan with concrete community resources (211/WIC/SNAP) and trackable FHIR CarePlan + Goal pairs.
- **Compound risk elevation** — A rule engine produces 5 flat flags; MamaGuard synthesizes URGENT compound risk across BP + HbA1c + pregnancy loss + housing + Medicaid gap with 5 cross-factor clinical-SDOH interactions the rule engine cannot produce.

*Evidence: `benchmarks/fixtures/ai_factor_comparison.md`, `benchmarks/fixtures/ai_factor_comparison.json`*

---

## 2. Potential Impact — Clear hypothesis for improving outcomes

| Metric | Current Baseline | Target with MamaGuard |
|--------|-----------------|----------------------|
| Postpartum follow-up completion | 60% attend | 85%+ via proactive gap detection |
| Hypertensive crisis detection | Median 5 days | Same-day via automated BP trend analysis |
| Childhood immunization adherence | 70.4% on time | 90%+ via automated gap detection |
| Clinician chart-review time | 15–20 min | <2 min AI-synthesized risk summary |
| SDOH screening completion | <25% eligible | 80%+ via automated Z-code + Coverage analysis |

**Cost context:** Preventable maternal morbidity costs $32.3B/year in the US. Each avoided severe maternal morbidity event saves ~$115K in acute care costs.

**Three specialist agents, one interface:**
- Maternal Risk Monitor (7 tools) — BP trends, glucose, pregnancy history, postpartum complications
- Pediatric Transition Agent (5 tools) — immunization gaps, developmental milestones, mother-to-child handoff
- SDOH & Outreach Agent (6 tools) — insurance gaps, language barriers, food/housing insecurity, community resource lookup, FHIR CarePlan + Goal writeback

---

## 3. Feasibility — Realistic for real healthcare

### Safety: Zero autonomous actions

MamaGuard enforces a **Liaison Pattern** — AI recommends, clinician decides. Every clinical recommendation flags clinician review. No autonomous prescriptions.

| Safety Control | Evidence |
|----------------|----------|
| 100% clinician review on URGENT/HIGH | Verified across all Tier-2a runs (3/3 URGENT cases flagged every run) |
| No autonomous prescriptions | Runtime safety filter (`safety_filter.py`) redacts prescribing language; 53 unit tests |
| No fabricated assessments without data | FHIR hooks on all 4 agents; missing-context → structured error, not guesswork |
| Write-back scoped | Only maternal agent can write RiskAssessment; pediatric/SDOH are read-only |
| Audit trail | Every tool invocation emits a FHIR R4 AuditEvent (HIPAA compliance) |
| FHIR resource validation | Required fields, risk level enum, patient ID match — checked before every POST |

### Benchmark evidence

| Tier | Scope | Result |
|------|-------|--------|
| Tier-1 (deterministic) | 57 cases — config, risk classification, tool correctness, safety flags | **57/57 (100%)** |
| Tier-2a (LLM eval) | 13 cases — routing, clinical reasoning, safety scenarios | **11/13 (94.0%)** |
| Overall weighted | All suites combined | **94.0%** (up from 88.2% baseline) |
| Safety category | Fabrication, prescribing, clinician review | **83.3%** (up from 72.2% baseline) |

*Evidence: `benchmarks/fixtures/judge_scorecard.md`, `benchmarks/fixtures/safety_report.md`*

### Privacy and regulation

- **SMART on FHIR** credential isolation — tokens flow from EHR session via SHARP extensions, never stored
- **On-prem model option** — validated with Nemotron-3-Super-120B on DGX Spark; no patient data leaves the network
- **5T structured output** (Talk/Template/Table/Task/Transaction) — standardized clinical reporting format, auditable and parseable
- **FHIR R4 native** — reads and writes standard resources (RiskAssessment, CarePlan, Goal, CommunicationRequest, AuditEvent)

### Interoperability

- **Dual submission**: A2A agent (BYO on Prompt Opinion) + standalone MCP server — 16 shared FHIR tools plus compound MCP assessments, two integration paths
- **Mother-to-child handoff**: `find_linked_newborn` discovers children via FHIR RelatedPerson, enabling seamless maternal-to-pediatric transitions in a single session
- **Multilingual**: Patient summaries in Spanish, Arabic, and Hindi when Patient.communication indicates a non-English primary language

---

*One-pager for hackathon judges. Full details: `devpost_description.md` (submission), `demo_script.md` (video guide), `safety_report.md` (safety deep-dive), `ai_factor_comparison.md` (benchmark methodology).*
