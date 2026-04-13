"""MamaGuard — Maternal-Pediatric Care Coordination Agent."""

from importlib.metadata import version as _pkg_version

try:
    MAMAGUARD_VERSION = _pkg_version("mamaguard")
except Exception:
    MAMAGUARD_VERSION = "0.1.0"
