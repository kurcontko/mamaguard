#!/usr/bin/env python3
"""Fail fast on known LiteLLM supply-chain compromise indicators."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path


COMPROMISED_LITELLM = {"1.82.7", "1.82.8"}
PERSISTENCE_FILE = "litellm_init.pth"
SUSPICIOUS_DOMAIN = "models.litellm.cloud"


def main() -> int:
    version = importlib.metadata.version("litellm")
    if version in COMPROMISED_LITELLM:
        print(f"FAIL: compromised litellm version installed: {version}")
        return 1

    roots = [Path.cwd()]
    venv = Path.cwd() / ".venv"
    if venv.exists():
        roots.append(venv)

    for root in roots:
        if any(root.rglob(PERSISTENCE_FILE)):
            print(f"FAIL: found known LiteLLM persistence file: {PERSISTENCE_FILE}")
            return 1

    text_files = [
        Path("pyproject.toml"),
        Path("uv.lock"),
        Path("mamaguard/requirements.txt"),
        Path("mamaguard/requirements.lock.txt"),
    ]
    for path in text_files:
        if path.exists() and SUSPICIOUS_DOMAIN in path.read_text(errors="ignore"):
            print(f"FAIL: found known LiteLLM exfiltration domain in {path}")
            return 1

    print(f"OK: litellm {version}; no known compromise indicators found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

