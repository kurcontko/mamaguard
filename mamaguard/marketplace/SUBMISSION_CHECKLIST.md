# MamaGuard Submission Checklist

Ordered launch checklist for the Agents Assemble hackathon.
Deadline: **May 11, 2026 @ 11:00pm EDT**.

---

## 1. Accounts & Registration

- [ ] Devpost account created and registered for [Agents Assemble](https://agents-assemble.devpost.com/)
- [ ] Prompt Opinion account created at [promptopinion.ai](https://promptopinion.ai)
- [ ] Google AI Studio API key obtained (for BYO Agent model)
- [ ] Google Cloud project with Cloud Run enabled

## 2. Pre-deploy Verification

- [ ] `make test` passes (all unit tests green)
- [ ] `make tier1` passes (100% deterministic benchmarks)
- [ ] `make smoke` passes (agent smoke test)
- [ ] `make smoke-mcp` passes (MCP server smoke test)
- [ ] `scripts/pre_deploy_check.sh` passes

## 3. Deploy A2A Agent (Azure App Service / Container Apps — production target)

- [ ] Build Docker image (`mamaguard/Dockerfile`) and push to Azure Container Registry
- [ ] Deploy to Azure App Service or Container Apps with env vars (`MAMAGUARD_API_KEY`, `GOOGLE_API_KEY`, `MAMAGUARD_URL`, optional `PO_PLATFORM_BASE_URL`)
- [ ] Verify health: `curl https://<AZURE_URL>/.well-known/agent-card.json` returns 200 with `protocolVersion`, `version: 1.0.0`, 4 skills with `examples`
- [ ] Verify auth: POST to `/` without `X-API-Key` returns 401; with valid key passes through

> Cloud Run alternative: `scripts/deploy.sh` exists for `gcloud`-based deploys.
> Production for the hackathon submission runs on Azure, so use that as the
> canonical path. Keep the GCP script only as fallback.

## 4. Deploy MCP Server (Superpower Track)

- [ ] Deploy MCP server with SSE transport (same image, different entrypoint)
- [ ] Verify MCP endpoint responds: `curl https://<MCP_URL>/sse`
- [ ] Test tool invocation: `get_patient_summary` returns valid response

See: [`mcp_setup.md`](mcp_setup.md)

## 5. Publish to Prompt Opinion Marketplace

### A2A Agent (Agent Track)

- [ ] Register external agent in PO (agent card URL)
- [ ] Create BYO Agent with system prompt from [`byo_system_prompt.md`](byo_system_prompt.md)
- [ ] Set consultation prompt from [`byo_consultation_prompt.md`](byo_consultation_prompt.md)
- [ ] Apply BYO config from [`byo_config.json`](byo_config.json)
- [ ] Enable FHIR context extension
- [ ] Publish BYO Agent to Marketplace
- [ ] Verify: agent appears on PO launchpad and is invokable

### MCP Server (Superpower Track)

- [ ] Register MCP server in PO with SSE endpoint URL
- [ ] Configure MCP tools from [`mcp_config.json`](mcp_config.json)
- [ ] Verify: tools appear in PO and return results

See: [`README.md`](README.md), [`po_integration.md`](po_integration.md)

## 6. End-to-End Validation on Prompt Opinion

- [ ] Launch MamaGuard from PO launchpad
- [ ] Select patient Maria (Patient/bench-maria-001)
- [ ] Run: "Assess maternal risk for this patient" -- verify 5T output
- [ ] Run: "Screen for social determinants" -- verify SDOH findings
- [ ] Run: "Do a full comprehensive assessment" -- verify all 3 agents fire
- [ ] Verify FHIR context flows correctly (check [`po_integration.md`](po_integration.md) troubleshooting if issues)

## 7. Record Demo Video (< 3 minutes)

- [ ] Pre-seed memory note: `uv run python scripts/demo_memory_recall.py --seed-only`
- [ ] Follow script in [`demo_script_v4_azure.md`](demo_script_v4_azure.md) (patient-first, Azure deployment)
- [ ] Pre-copy all inputs (no typing during recording)
- [ ] Scene 1: Intro + architecture (0:00-0:15)
- [ ] Scene 2: Launch from Marketplace (0:15-0:30)
- [ ] Scene 3: Maternal risk assessment (0:30-1:15)
- [ ] Scene 3.5: **Longitudinal memory recall** (insert, ~30s) — the
      differentiator no competitor has. See the v3 ADDENDUM in demo_script.md.
- [ ] Scene 4: SDOH screening (1:15-1:50)
- [ ] Scene 4.5: **Plan/commit approval gate** (insert, ~25s) — Liaison
      pattern turned into demonstrable FHIR write approval flow.
- [ ] Scene 5: Mother-to-child handoff (if time permits; cuttable)
- [ ] Close (~15s)
- [ ] Upload video (YouTube/Loom/Vimeo unlisted link)
- [ ] Cleanup seeded memory after recording: `uv run python scripts/demo_memory_recall.py --cleanup`

## 8. Devpost Submission

- [ ] Title: "MamaGuard: Maternal-Pediatric Care Coordinator"
- [ ] Description: copy from [`devpost_description.md`](devpost_description.md)
- [ ] Attach demo video link
- [ ] Tag: both Agent (A2A) and Superpower (MCP) tracks
- [ ] Link to GitHub repo
- [ ] Link to Prompt Opinion marketplace listing
- [ ] Submit before deadline

## Reference Artifacts

| Artifact | Path | Purpose |
|----------|------|---------|
| Devpost description | [`devpost_description.md`](devpost_description.md) | Submission text |
| Demo script | [`demo_script.md`](demo_script.md) | Video recording guide |
| Why MamaGuard | [`why_mamaguard.md`](why_mamaguard.md) | Judge-facing one-pager |
| PO integration | [`po_integration.md`](po_integration.md) | FHIR context flow reference |
| MCP setup | [`mcp_setup.md`](mcp_setup.md) | MCP server deployment |
| BYO system prompt | [`byo_system_prompt.md`](byo_system_prompt.md) | PO agent system prompt |
| BYO consultation prompt | [`byo_consultation_prompt.md`](byo_consultation_prompt.md) | PO consultation prompt |
| BYO config | [`byo_config.json`](byo_config.json) | PO agent configuration |
| MCP config | [`mcp_config.json`](mcp_config.json) | MCP tool definitions |
| Eval summary | [`../../benchmarks/fixtures/eval_summary.md`](../../benchmarks/fixtures/eval_summary.md) | Benchmark results for Devpost |
| Judge scorecard | [`../../benchmarks/fixtures/judge_scorecard.md`](../../benchmarks/fixtures/judge_scorecard.md) | Detailed scoring breakdown |
| Deploy script | [`../../scripts/deploy.sh`](../../scripts/deploy.sh) | Cloud Run deployment |
| Memory recall demo | [`demo_memory_recall.md`](demo_memory_recall.md) | v3 differentiator talking points |
| Memory recall script | [`../../scripts/demo_memory_recall.py`](../../scripts/demo_memory_recall.py) | Seed / preview / cleanup prior-visit note |
| Submission run harness | [`../../scripts/run_submission_benchmark.sh`](../../scripts/run_submission_benchmark.sh) | Nemotron Tier-2b at T-7 |
| Submission run runbook | [`SUBMISSION_RUN.md`](SUBMISSION_RUN.md) | Nemotron restart + run procedure |
