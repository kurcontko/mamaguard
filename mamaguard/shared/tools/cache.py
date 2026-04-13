"""
Session-level tool response cache.

Stores successful FHIR tool results in ``tool_context.state["_tool_cache"]``
so that repeated calls for the same patient within a single A2A request
(e.g. comprehensive assessment routing through multiple sub-agents) return
cached data instead of hitting the FHIR server again.

Cache lifetime is a single agent session — state is discarded when the
A2A request completes, so there is no cross-session staleness risk.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_CACHE_STATE_KEY = "_tool_cache"


def _build_cache_key(tool_name: str, patient_id: str, extra_args: tuple) -> str:
    """Build a deterministic cache key from tool name, patient, and args."""
    parts = [tool_name, patient_id]
    parts.extend(str(a) for a in extra_args)
    return "|".join(parts)


def get_cache(state: dict, tool_name: str, patient_id: str, extra_args: tuple = ()) -> Any | None:
    """Return cached result or None if not cached."""
    cache = state.get(_CACHE_STATE_KEY)
    if cache is None:
        return None
    key = _build_cache_key(tool_name, patient_id, extra_args)
    return cache.get(key)


def put_cache(state: dict, tool_name: str, patient_id: str, result: dict, extra_args: tuple = ()) -> None:
    """Store a successful result in the session cache."""
    if result.get("status") != "success":
        return
    if _CACHE_STATE_KEY not in state:
        state[_CACHE_STATE_KEY] = {}
    key = _build_cache_key(tool_name, patient_id, extra_args)
    state[_CACHE_STATE_KEY][key] = result
    logger.debug("tool_cache_put key=%s", key)


def invalidate_cache(state: dict, patient_id: str | None = None) -> None:
    """Remove cached entries. If patient_id given, only remove that patient's entries."""
    cache = state.get(_CACHE_STATE_KEY)
    if cache is None:
        return
    if patient_id is None:
        state[_CACHE_STATE_KEY] = {}
    else:
        keys_to_remove = [k for k in cache if f"|{patient_id}|" in k or k.split("|")[1] == patient_id]
        for k in keys_to_remove:
            del cache[k]


def cached_tool(tool_func: Callable) -> Callable:
    """Decorator that adds session-level caching to a FHIR read tool.

    The decorated function must accept ``tool_context`` as a keyword-or-positional
    argument.  Any additional keyword arguments (e.g. ``months_back``) are included
    in the cache key so that ``get_bp_trend(months_back=6)`` and
    ``get_bp_trend(months_back=24)`` cache independently.

    Only results with ``status == "success"`` are cached.  Error responses always
    pass through uncached so that transient failures can be retried.
    """
    tool_name = tool_func.__name__

    @functools.wraps(tool_func)
    def wrapper(*args, **kwargs):
        # Locate tool_context from args or kwargs
        import inspect
        sig = inspect.signature(tool_func)
        param_names = list(sig.parameters.keys())

        tool_context = kwargs.get("tool_context")
        if tool_context is None:
            # Find tool_context positionally
            for i, name in enumerate(param_names):
                if name == "tool_context" and i < len(args):
                    tool_context = args[i]
                    break

        if tool_context is None or not hasattr(tool_context, "state"):
            return tool_func(*args, **kwargs)

        patient_id = tool_context.state.get("patient_id", "")
        if not patient_id:
            return tool_func(*args, **kwargs)

        # Build extra_args from non-tool_context arguments
        extra = []
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        for name, val in bound.arguments.items():
            if name != "tool_context":
                extra.append(val)

        extra_args = tuple(extra)

        # Check cache
        cached = get_cache(tool_context.state, tool_name, patient_id, extra_args)
        if cached is not None:
            logger.debug("tool_cache_hit tool=%s patient=%s", tool_name, patient_id)
            return cached

        # Execute and cache
        result = tool_func(*args, **kwargs)
        put_cache(tool_context.state, tool_name, patient_id, result, extra_args)
        return result

    return wrapper
