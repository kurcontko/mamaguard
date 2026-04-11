"""Base classes and utilities for benchmark cases."""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Verdict(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"


@dataclass
class BenchmarkResult:
    name: str
    verdict: Verdict
    score: float  # 0.0 - 1.0
    elapsed_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class BenchmarkCase:
    """A single benchmark test case."""

    name: str
    description: str
    category: str  # e.g. "fhir_tools", "clinical_reasoning", "orchestration"
    fn: Callable[[], BenchmarkResult] | None = None

    def run(self) -> BenchmarkResult:
        if self.fn is None:
            return BenchmarkResult(
                name=self.name, verdict=Verdict.SKIP, score=0.0,
                details={"reason": "no test function"},
            )
        t0 = time.perf_counter()
        try:
            result = self.fn()
            result.elapsed_ms = (time.perf_counter() - t0) * 1000
            return result
        except Exception as e:
            return BenchmarkResult(
                name=self.name,
                verdict=Verdict.ERROR,
                score=0.0,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )


class BenchmarkSuite:
    """Collection of benchmark cases with scoring."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.cases: list[BenchmarkCase] = []

    def add(self, case: BenchmarkCase):
        self.cases.append(case)

    def case(self, name: str, description: str = "", category: str = ""):
        """Decorator to register a benchmark function."""
        def decorator(fn: Callable[[], BenchmarkResult]):
            self.cases.append(BenchmarkCase(
                name=name,
                description=description or name,
                category=category or self.name,
                fn=fn,
            ))
            return fn
        return decorator

    def run_all(self) -> list[BenchmarkResult]:
        return [case.run() for case in self.cases]


class MockToolContext:
    """Reusable mock for google.adk.tools.ToolContext."""

    def __init__(
        self,
        fhir_url: str = "https://fhir.example.org",
        fhir_token: str = "bench-token",
        patient_id: str = "bench-patient-1",
    ):
        self.state = {
            "fhir_url": fhir_url,
            "fhir_token": fhir_token,
            "patient_id": patient_id,
        }
