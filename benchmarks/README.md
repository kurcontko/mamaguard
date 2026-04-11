# MamaGuard Benchmarks

Two tiers of evaluation with very different semantics. Don't conflate them.

## Tier 1 — Unit regression (`fhir_tools/`, `clinical_reasoning/`, `orchestration/`)

These are **unit tests dressed as benchmarks**. They mock `_fhir_get` and
verify the Python tool logic behaves per spec. Useful as refactor safety net;
**not meaningful as a benchmark** of MamaGuard. A model isn't even involved.

Run with:

```bash
python3.11 -m benchmarks.runner
```

## Tier 2 — End-to-end real benchmarks (`e2e/`)

Runs the **actual MamaGuard agent** against a real HAPI FHIR server loaded
with patient Bundles. Captures real tool-call traces via ADK callbacks and
evaluates both tool-selection correctness and final answer quality.

Supports two backends:
- **Gemini** (production): requires `GOOGLE_API_KEY`
- **vLLM via LiteLLM** (swap test): requires `BENCH_API_BASE` + `BENCH_MODEL`

```bash
# Prerequisite: Docker must be running (HAPI FHIR container)

# Benchmark Gemini (real MamaGuard)
export GOOGLE_API_KEY=...
python3.11 -m benchmarks.runner --e2e

# Benchmark your vLLM model as a Gemini replacement
export BENCH_API_BASE=http://your-vllm:8000/v1
export BENCH_MODEL=meta-llama/Llama-3.1-70B-Instruct
python3.11 -m benchmarks.runner --e2e --backend vllm
```

## Tier 3 — MedAgentBench-style cases (`medagent/`)

Externally comparable methodology from Stanford MedAgentBench. Uses the same
task format (query tasks + action tasks) against our synthetic FHIR data.
Gives you numbers you can cite in a submission.

```bash
python3.11 -m benchmarks.runner --medagent
```

## Environment variables

| Var | Purpose | Default |
|---|---|---|
| `BENCH_API_BASE` | vLLM OpenAI endpoint | `http://localhost:8000/v1` |
| `BENCH_MODEL` | vLLM model id | (required for vllm backend) |
| `BENCH_API_KEY` | vLLM API key | `EMPTY` |
| `JUDGE_API_BASE` | Judge LLM endpoint | falls back to `BENCH_API_BASE` |
| `JUDGE_MODEL` | Judge LLM id | falls back to `BENCH_MODEL` |
| `GOOGLE_API_KEY` | Gemini API key | (required for gemini backend) |
| `HAPI_FHIR_URL` | HAPI endpoint | `http://localhost:8090/fhir` |
| `HAPI_CONTAINER_NAME` | Docker container name | `mamaguard-hapi-bench` |
| `HAPI_KEEP_RUNNING` | Don't tear down HAPI after run | `false` |
