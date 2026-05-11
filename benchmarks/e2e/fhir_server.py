"""
HAPI FHIR Docker lifecycle manager for end-to-end benchmarks.

Responsibilities:
  - Start HAPI FHIR R4 in a named Docker container (idempotent)
  - Wait for FHIR endpoint to become ready
  - Load benchmark Bundles via transaction POST (idempotent PUT semantics)
  - Optionally tear down on exit

Uses the hapiproject/hapi:latest image on port 8090 by default.

Environment:
    HAPI_FHIR_URL          default http://localhost:8090/fhir
    HAPI_CONTAINER_NAME    default mamaguard-hapi-bench
    HAPI_IMAGE             default hapiproject/hapi:latest
    HAPI_PORT              default 8090
    HAPI_KEEP_RUNNING      if "true", don't stop the container on exit
"""

from __future__ import annotations

import logging
import os
import subprocess
import time

import httpx

from benchmarks.e2e.fhir_bundles import ALL_PATIENTS

logger = logging.getLogger(__name__)


class HapiFhirServer:
    """
    Idempotent HAPI FHIR container manager.

    Usage:
        with HapiFhirServer() as fhir:
            # fhir.base_url -> http://localhost:8090/fhir
            # All bundles loaded, ready for testing
            ...
    """

    def __init__(
        self,
        container_name: str | None = None,
        port: int | None = None,
        image: str | None = None,
        keep_running: bool | None = None,
    ):
        self.container_name = container_name or os.environ.get(
            "HAPI_CONTAINER_NAME", "mamaguard-hapi-bench"
        )
        self.port = int(port or os.environ.get("HAPI_PORT", "8090"))
        self.image = image or os.environ.get("HAPI_IMAGE", "hapiproject/hapi:latest")
        self.keep_running = (
            keep_running
            if keep_running is not None
            else os.environ.get("HAPI_KEEP_RUNNING", "false").lower() == "true"
        )
        self.base_url = f"http://localhost:{self.port}/fhir"
        self._started_by_us = False

    # -- Lifecycle ------------------------------------------------------------

    def start(self) -> None:
        """Start container (or reuse existing). Wait until FHIR endpoint is ready."""
        if self._is_running():
            logger.info("HAPI container '%s' already running — reusing", self.container_name)
        elif self._exists():
            logger.info("HAPI container '%s' exists but stopped — starting", self.container_name)
            self._run(["docker", "start", self.container_name])
            self._started_by_us = True
        else:
            logger.info("Creating HAPI container '%s' (image: %s)", self.container_name, self.image)
            self._run([
                "docker", "run", "-d",
                "--name", self.container_name,
                "-p", f"{self.port}:8080",
                "-e", "spring.datasource.url=jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1",
                "-e", "hapi.fhir.fhir_version=R4",
                "-e", "hapi.fhir.validation.requests_enabled=false",
                "-e", "hapi.fhir.validation.responses_enabled=false",
                self.image,
            ])
            self._started_by_us = True

        self._wait_ready()

    def stop(self) -> None:
        """Stop container unless keep_running is set."""
        if self.keep_running:
            logger.info("HAPI keep_running=true, leaving '%s' up", self.container_name)
            return
        if self._started_by_us and self._is_running():
            logger.info("Stopping HAPI container '%s'", self.container_name)
            self._run(["docker", "stop", self.container_name], check=False)

    def teardown(self) -> None:
        """Full teardown: stop + remove the container."""
        self._run(["docker", "stop", self.container_name], check=False)
        self._run(["docker", "rm", self.container_name], check=False)

    def __enter__(self) -> HapiFhirServer:
        self.start()
        self.load_all_bundles()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # -- Data loading ---------------------------------------------------------

    def load_all_bundles(self) -> dict[str, int]:
        """Load all benchmark patient bundles. Returns {patient_id: resource_count}."""
        results = {}
        for patient_id, meta in ALL_PATIENTS.items():
            count = self.load_bundle(meta["bundle"])
            results[patient_id] = count
            logger.info("loaded patient=%s resources=%d", patient_id, count)
        return results

    def load_bundle(self, bundle: dict) -> int:
        """POST a transaction Bundle and return the count of entries."""
        resp = httpx.post(
            self.base_url,
            json=bundle,
            headers={
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        return len(bundle.get("entry", []))

    def reset(self) -> None:
        """Delete all benchmark resources and reload."""
        for patient_id in ALL_PATIENTS:
            try:
                httpx.delete(
                    f"{self.base_url}/Patient/{patient_id}?_cascade=delete",
                    timeout=30,
                )
            except Exception as e:
                logger.warning("failed to delete %s: %s", patient_id, e)
        self.load_all_bundles()

    def verify_patient(self, patient_id: str) -> bool:
        """Check that a patient exists on the FHIR server."""
        try:
            resp = httpx.get(
                f"{self.base_url}/Patient/{patient_id}",
                headers={"Accept": "application/fhir+json"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # -- Internals ------------------------------------------------------------

    def _exists(self) -> bool:
        result = self._run(
            ["docker", "ps", "-a", "--filter", f"name=^{self.container_name}$", "--format", "{{.Names}}"],
            capture=True, check=False,
        )
        return self.container_name in (result.stdout or "")

    def _is_running(self) -> bool:
        result = self._run(
            ["docker", "ps", "--filter", f"name=^{self.container_name}$", "--format", "{{.Names}}"],
            capture=True, check=False,
        )
        return self.container_name in (result.stdout or "")

    def _wait_ready(self, timeout: int = 180) -> None:
        """Wait for FHIR metadata endpoint to respond 200."""
        metadata_url = f"{self.base_url}/metadata"
        start = time.time()
        last_err = ""
        while time.time() - start < timeout:
            try:
                resp = httpx.get(metadata_url, timeout=5)
                if resp.status_code == 200:
                    elapsed = time.time() - start
                    logger.info("HAPI FHIR ready after %.1fs at %s", elapsed, self.base_url)
                    return
                last_err = f"HTTP {resp.status_code}"
            except (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
                httpx.HTTPError,
            ) as e:
                last_err = f"{type(e).__name__}: {e}"
            time.sleep(2)
        raise TimeoutError(
            f"HAPI FHIR did not become ready within {timeout}s at {metadata_url}. "
            f"Last error: {last_err}"
        )

    def _run(self, cmd: list[str], capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
        )


def ensure_running() -> HapiFhirServer:
    """Convenience: start (or reuse) HAPI, load data, return server handle."""
    server = HapiFhirServer()
    server.start()
    server.load_all_bundles()
    return server
