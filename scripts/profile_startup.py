#!/usr/bin/env python3
"""Profile MamaGuard agent startup time.

Measures how long ``from mamaguard.app import a2a_app`` takes and breaks
down the cost into third-party dependencies vs mamaguard-internal code.

Usage:
    python scripts/profile_startup.py           # default (3 runs)
    python scripts/profile_startup.py -n 5      # 5 runs
    python scripts/profile_startup.py --detail   # per-dependency breakdown

Exit 0 if average import time < 2s, exit 1 otherwise.
"""
from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import time

# -- ANSI colors ---------------------------------------------------------------
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"

# -- Key third-party deps (ordered by typical cost) ----------------------------
THIRD_PARTY_DEPS = [
    "google.genai.types",
    "google.adk.agents",
    "google.adk.a2a.utils.agent_to_a2a",
    "a2a.types",
    "mcp.types",
    "httpx",
    "fastapi",
]

THRESHOLD_S = 2.0


def measure_single_import(module: str) -> float:
    """Import a module and return elapsed seconds."""
    start = time.perf_counter()
    importlib.import_module(module)
    return time.perf_counter() - start


def measure_full_startup() -> float:
    """Measure import time in a clean subprocess (no module cache)."""
    code = (
        "import time; s=time.perf_counter(); "
        "from mamaguard.app import a2a_app; "
        "print(f'{time.perf_counter()-s:.6f}')"
    )
    result = subprocess.run(
        [sys.executable, "-W", "ignore", "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"{RED}ERROR{RESET}: subprocess failed:\n{result.stderr[:500]}")
        sys.exit(1)
    # Last line of stdout has the timing
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return float(line.strip())
        except ValueError:
            continue
    print(f"{RED}ERROR{RESET}: could not parse timing from subprocess output")
    sys.exit(1)


def measure_dep_breakdown() -> list[tuple[str, float]]:
    """Import each dependency sequentially and measure individual cost."""
    results = []
    for mod in THIRD_PARTY_DEPS:
        elapsed = measure_single_import(mod)
        results.append((mod, elapsed))

    # Now measure mamaguard with deps already cached
    start = time.perf_counter()
    import mamaguard.app  # noqa: F401
    mamaguard_elapsed = time.perf_counter() - start
    results.append(("mamaguard.app (after deps cached)", mamaguard_elapsed))
    return results


def run_profile(runs: int, detail: bool) -> bool:
    """Run the profiling suite. Returns True if under threshold."""
    print(f"{BOLD}MamaGuard Startup Profiler{RESET}")
    print(f"Threshold: {THRESHOLD_S:.1f}s | Runs: {runs}\n")

    # --- Full startup timing (subprocess, clean cache each run) ---
    print(f"{BOLD}Full startup timing{RESET} (from mamaguard.app import a2a_app):")
    timings: list[float] = []
    for i in range(runs):
        elapsed = measure_full_startup()
        timings.append(elapsed)
        bar = "=" * int(elapsed * 40)
        color = GREEN if elapsed < THRESHOLD_S else RED
        print(f"  Run {i+1}: {color}{elapsed:.3f}s{RESET} |{bar}|")

    avg = sum(timings) / len(timings)
    best = min(timings)
    worst = max(timings)
    color = GREEN if avg < THRESHOLD_S else RED
    print(f"\n  Average: {color}{BOLD}{avg:.3f}s{RESET}  (best: {best:.3f}s, worst: {worst:.3f}s)")
    passed = avg < THRESHOLD_S
    if passed:
        print(f"  {GREEN}PASS{RESET} — under {THRESHOLD_S:.1f}s threshold\n")
    else:
        print(f"  {RED}FAIL{RESET} — over {THRESHOLD_S:.1f}s threshold\n")

    # --- Per-dependency breakdown (optional) ---
    if detail:
        print(f"{BOLD}Dependency breakdown{RESET} (single process, sequential imports):")
        breakdown = measure_dep_breakdown()
        total = sum(t for _, t in breakdown)
        for mod, elapsed in sorted(breakdown, key=lambda x: -x[1]):
            pct = (elapsed / total * 100) if total > 0 else 0
            bar = "=" * int(pct)
            print(f"  {mod:50s} {elapsed*1000:7.1f}ms  ({pct:4.1f}%) |{bar}|")
        print(f"\n  Total (sequential): {total*1000:.1f}ms")
        third_party = sum(t for m, t in breakdown if not m.startswith("mamaguard"))
        internal = sum(t for m, t in breakdown if m.startswith("mamaguard"))
        print(f"  Third-party: {third_party*1000:.1f}ms ({third_party/total*100:.0f}%)")
        print(f"  MamaGuard:   {internal*1000:.1f}ms ({internal/total*100:.0f}%)")
        print()

    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile MamaGuard startup time")
    parser.add_argument("-n", "--runs", type=int, default=3, help="Number of runs (default: 3)")
    parser.add_argument("--detail", action="store_true", help="Show per-dependency breakdown")
    args = parser.parse_args()

    passed = run_profile(args.runs, args.detail)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
