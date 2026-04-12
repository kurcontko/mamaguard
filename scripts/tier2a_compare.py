#!/usr/bin/env python3
"""Compare a Tier-2a run against the baseline JSON and highlight changes.

Usage:
    # Compare two saved results:
    python scripts/tier2a_compare.py benchmarks/fixtures/tier2a_post_safety.json

    # Run Tier-2a live and compare (piped):
    python -m benchmarks.runner --llm --backend vllm --json | python scripts/tier2a_compare.py -

    # Specify a different baseline:
    python scripts/tier2a_compare.py new.json --baseline benchmarks/fixtures/tier2a_post_safety.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_BASELINE = Path(__file__).resolve().parent.parent / "benchmarks" / "fixtures" / "tier2a_baseline.json"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"


def load_json(path_or_stdin: str) -> dict:
    if path_or_stdin == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path_or_stdin).read_text())


def compare(baseline: dict, current: dict) -> int:
    """Print a diff report and return exit code (0 = no regressions, 1 = regressions)."""
    b_suites = baseline["scores"]["suites"]
    c_suites = current["scores"]["suites"]
    b_results = baseline.get("results", {})
    c_results = current.get("results", {})

    improved: list[str] = []
    regressed: list[str] = []
    new_cases: list[str] = []
    removed_cases: list[str] = []

    all_suites = sorted(set(list(b_suites.keys()) + list(c_suites.keys())))

    print(f"\n{BOLD}Tier-2a Comparison Report{RESET}")
    print("=" * 60)

    # Per-suite summary
    print(f"\n{BOLD}Suite Summary:{RESET}")
    print(f"  {'Suite':<25} {'Baseline':>10} {'Current':>10} {'Delta':>10}")
    print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10}")

    for suite in all_suites:
        b = b_suites.get(suite, {})
        c = c_suites.get(suite, {})
        bp = b.get("passed", 0)
        bt = b.get("total", 0)
        cp = c.get("passed", 0)
        ct = c.get("total", 0)
        delta = cp - bp
        color = GREEN if delta > 0 else RED if delta < 0 else ""
        reset = RESET if color else ""
        sign = "+" if delta > 0 else ""
        print(f"  {suite:<25} {bp:>4}/{bt:<4}   {cp:>4}/{ct:<4}   {color}{sign}{delta}{reset}")

    # Per-case diffs
    print(f"\n{BOLD}Case-level Changes:{RESET}")
    any_change = False

    for suite in all_suites:
        b_cases = {c["name"]: c for c in b_results.get(suite, [])}
        c_cases = {c["name"]: c for c in c_results.get(suite, [])}

        for name in sorted(set(list(b_cases.keys()) + list(c_cases.keys()))):
            if name in b_cases and name in c_cases:
                bs = b_cases[name]["score"]
                cs = c_cases[name]["score"]
                if bs != cs:
                    any_change = True
                    delta = cs - bs
                    if delta > 0:
                        improved.append(f"{suite}/{name}")
                        print(f"  {GREEN}+IMPROVED{RESET}  {suite}/{name}: {bs} -> {cs}")
                    else:
                        regressed.append(f"{suite}/{name}")
                        print(f"  {RED}-REGRESSED{RESET} {suite}/{name}: {bs} -> {cs}")
            elif name not in b_cases:
                any_change = True
                cs = c_cases[name]["score"]
                new_cases.append(f"{suite}/{name}")
                print(f"  {YELLOW}+NEW{RESET}       {suite}/{name}: score={cs}")
            else:
                any_change = True
                removed_cases.append(f"{suite}/{name}")
                print(f"  {YELLOW}-REMOVED{RESET}   {suite}/{name}")

    if not any_change:
        print("  (no case-level changes)")

    # Overall
    b_overall = baseline["scores"].get("overall_score", 0)
    c_overall = current["scores"].get("overall_score", 0)
    b_total = sum(s.get("passed", 0) for s in b_suites.values())
    b_count = sum(s.get("total", 0) for s in b_suites.values())
    c_total = sum(s.get("passed", 0) for s in c_suites.values())
    c_count = sum(s.get("total", 0) for s in c_suites.values())

    print(f"\n{BOLD}Overall:{RESET}")
    print(f"  Baseline:  {b_total}/{b_count} ({b_overall:.1%})")
    print(f"  Current:   {c_total}/{c_count} ({c_overall:.1%})")

    delta_pct = c_overall - b_overall
    color = GREEN if delta_pct > 0 else RED if delta_pct < 0 else ""
    reset = RESET if color else ""
    sign = "+" if delta_pct > 0 else ""
    print(f"  Delta:     {color}{sign}{delta_pct:.1%}{reset}")

    print(f"\n  Improved:  {len(improved)}")
    print(f"  Regressed: {len(regressed)}")
    print(f"  New:       {len(new_cases)}")
    print(f"  Removed:   {len(removed_cases)}")
    print()

    return 1 if regressed else 0


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compare Tier-2a results against baseline")
    parser.add_argument("current", help="Path to current results JSON, or '-' for stdin")
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help=f"Path to baseline JSON (default: {DEFAULT_BASELINE.name})",
    )
    args = parser.parse_args()

    baseline = load_json(args.baseline)
    current = load_json(args.current)
    exit_code = compare(baseline, current)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
