.PHONY: setup test mypy lint tier1 tier2a tier2a-compare tier2b tier3 bench-all hapi hapi-load serve serve-mcp smoke smoke-mcp clean

# --- Setup ---
setup:
	uv sync --extra dev

# --- Testing ---
test:
	uv run pytest mamaguard/tests/ -x -q

test-verbose:
	uv run pytest mamaguard/tests/ -v

mypy:
	uv run mypy mamaguard/

lint: mypy test

# --- Benchmarks ---
tier1:
	uv run python -m benchmarks.runner

tier2a:
	uv run python -m benchmarks.runner --llm --backend vllm

tier2a-compare:
	@uv run python -m benchmarks.runner --llm --backend vllm --json | uv run python scripts/tier2a_compare.py -

tier2b:
	uv run python -m benchmarks.runner --e2e --backend vllm --no-fhir-setup --verbose

tier2b-judge:
	uv run python -m benchmarks.runner --e2e --backend vllm --judge --no-fhir-setup --verbose

tier3:
	uv run python -m benchmarks.runner --medagent --backend vllm --no-fhir-setup

tier3-judge:
	uv run python -m benchmarks.runner --medagent --backend vllm --judge --no-fhir-setup

bench-all:
	uv run python -m benchmarks.runner --e2e --medagent --backend vllm --judge --no-fhir-setup --verbose

bench-json:
	uv run python -m benchmarks.runner --e2e --medagent --backend vllm --judge --no-fhir-setup --json

# --- HAPI FHIR ---
hapi:
	docker compose -f mamaguard/docker-compose.yml up -d hapi

hapi-load:
	uv run python scripts/load_bundles.py --fhir-url http://localhost:8090/fhir --verify

hapi-stop:
	docker compose -f mamaguard/docker-compose.yml down

# --- Serve ---
serve:
	uv run uvicorn mamaguard.app:a2a_app --host 0.0.0.0 --port 8001

serve-mcp:
	uv run python -m mamaguard.mcp_server.server

# --- Smoke test ---
smoke:
	uv run python scripts/smoke_test.py

smoke-verbose:
	uv run python scripts/smoke_test.py --verbose

smoke-mcp:
	uv run python scripts/smoke_test_mcp.py

# --- Nemotron check ---
nemotron-check:
	@curl -sf http://10.10.10.2:30000/v1/models | python3 -c "import sys,json; d=json.load(sys.stdin); print('Nemotron OK:', d['data'][0]['id'])" 2>/dev/null || echo "Nemotron not reachable at 10.10.10.2:30000"

judge-check:
	@curl -sf https://openrouter.ai/api/v1/models -H "Authorization: Bearer $${JUDGE_API_KEY}" | python3 -c "import sys,json; print('OpenRouter OK')" 2>/dev/null || echo "OpenRouter not reachable"

# --- Clean ---
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	rm -rf .mypy_cache .pytest_cache
