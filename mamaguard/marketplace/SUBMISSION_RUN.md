# Submission benchmark run — Nemotron Tier-2b

This is the "locked codebase" run that produces the headline number for the
Devpost submission. It is **intentionally deferred** until T-7 before the
deadline so the number matches the code we actually ship.

## When to run

Run between **2026-05-03 and 2026-05-05** (T-8 to T-6 before 2026-05-11).
That leaves 6-8 days of buffer for:
- re-runs if a timeout or judge flake produces a weird number
- final demo video recording
- Devpost submission paperwork

**Do not run this earlier**: every iteration commit invalidates the number
and wastes 8-10 hours of DGX time. Gemma iteration runs (Tier-2b ~25 min)
are the right tool for day-to-day work.

## Preconditions

1. **Gemma can go offline**. The DGX `vllm_node` container currently serves
   Gemma on `:8000` with `/model` bind-mounted to `gemma-4-26B-A4B-it`. Starting
   Nemotron on `:30000` either needs a second container or a swap. Decide the
   trade-off before starting:
   - Option A: run both (RAM permitting; Nemotron ~60GB, Gemma ~7GB).
   - Option B: swap — stop Gemma, start Nemotron, accept no iteration model
     for the 8-10h benchmark window.

2. **Tier-1 is green on the locked commit**: the submission script enforces
   this with a preflight.

3. **HAPI is up with bench bundles loaded**: `scripts/load_bundles.py` has
   been run.

4. **`.env` has a valid `JUDGE_API_KEY`** for OpenRouter / DeepSeek.

## Starting Nemotron on DGX

SSH to `qrc@10.10.10.2` (10GbE) and follow `~/repos/nemotron.md`. The
canonical `docker run` invocation (copied from that file so we do not depend
on DGX file availability):

```bash
docker run \
  --privileged \
  --gpus all \
  -it --rm \
  --network=host --ipc=host \
  --shm-size 64g \
  -v "$HOME/models/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4:/model" \
  -e VLLM_NVFP4_GEMM_BACKEND=marlin \
  -e VLLM_TEST_FORCE_FP8_MARLIN=1 \
  -e VLLM_MARLIN_USE_ATOMIC_ADD=1 \
  vllm-node \
  bash -c '
    wget -q https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4/resolve/main/super_v3_reasoning_parser.py &&
    vllm serve /model \
      --served-model-name nemotron \
      --host 0.0.0.0 --port 30000 \
      --trust-remote-code \
      --load-format fastsafetensors \
      --gpu-memory-utilization 0.7 \
      --max-model-len 262144 \
      --max-num-seqs 10 \
      --kv-cache-dtype fp8 \
      --enable-prefix-caching \
      --enable-auto-tool-choice \
      --tool-call-parser qwen3_coder \
      --reasoning-parser-plugin super_v3_reasoning_parser.py \
      --reasoning-parser super_v3
  '
```

Wait for "Application startup complete" in the serve logs. Verify:

```bash
curl -s http://10.10.10.2:30000/v1/models | head -c 200
```

## Running the submission benchmark

From the repo root:

```bash
# Smoke first -- verifies wiring, single category, ~15 minutes
./scripts/run_submission_benchmark.sh --smoke

# Full Tier-2b run -- 8-10 hours, 47 cases, DeepSeek judge enabled
./scripts/run_submission_benchmark.sh
```

The script enforces Tier-1 green before firing, probes both Nemotron and HAPI,
streams the output log to `benchmarks/fixtures/submission_runs/tier2b_nemotron_<ts>.log`,
and exits on any preflight failure.

## After the run

1. Open the log file and extract the overall Tier-2b score + per-category
   breakdown.
2. Update `mamaguard/marketplace/devpost_description.md` with the real number
   (replace the existing 90.0% Gemma result if Nemotron beats it; otherwise
   keep the Gemma number and note the judge model).
3. Copy the JSON fixture into `benchmarks/fixtures/` as the authoritative
   submission artefact.
4. Commit with `chore(submission): Tier-2b Nemotron <score>% on <commit>`.

## Target

We already have 90.0% on v3/Gemma (2026-04-16, 44/47). v1 scored 88.3% on
Nemotron (2026-04-15). The submission target is therefore **≥90.0% on Nemotron**
— matching Gemma would validate that v3 architectural changes (SubagentTool
isolation, FHIR memory, plan/commit, vaccine normalization) carry across
backends; beating Gemma would be the headline number.
