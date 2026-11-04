"""Dynamic context-window resolution for ``orcarouter:`` model specs.

OrcaRouter fronts many upstream models, so their context windows cannot be
listed statically in ``MODEL_CONTEXT_WINDOWS``. Instead the gateway's
OpenAI-compatible ``GET {base_url}/models`` listing is fetched and each
entry's context length (see ``ORCAROUTER_CONTEXT_LENGTH_KEYS``) is cached.

The two halves run in different contexts on purpose:

* :func:`refresh_orcarouter_context_windows` performs network I/O. It is
  called from ``model_factory._construct_orcarouter_model``, which already
  runs off the event loop (``abuild_agent_model`` wraps it in
  ``sync_to_async``) and holds the resolved gateway URL and key.
* :func:`get_orcarouter_context_window` only reads the cache. It is called
  from ``get_context_window_for_model``, which runs inside async agent code
  where blocking I/O (and ORM access for credentials) is not allowed.

Until a listing has been fetched, or when the gateway is unreachable or omits
the model's window, the lookup returns
``ORCAROUTER_FALLBACK_CONTEXT_WINDOW``. A fetch never raises into the caller.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx

from opencontractserver.constants.context_guardrails import (
    ORCAROUTER_CONTEXT_LENGTH_KEYS,
    ORCAROUTER_FALLBACK_CONTEXT_WINDOW,
    ORCAROUTER_MODELS_CACHE_TTL_SECONDS,
    ORCAROUTER_MODELS_FETCH_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class _CacheState:
    """Process-local cache of gateway-reported context windows."""

    def __init__(self) -> None:
        # model id -> context window (tokens), from the last successful fetch.
        self.windows: dict[str, int] = {}
        # ``time.monotonic()`` of the last fetch attempt (success or failure),
        # so a down gateway is not re-queried on every agent build.
        self.last_fetch_at: float | None = None
        self.lock = threading.Lock()


_cache = _CacheState()


def _extract_context_length(entry: dict) -> int | None:
    """Return the first positive integer context length in a ``/models`` entry."""
    for key in ORCAROUTER_CONTEXT_LENGTH_KEYS:
        value = entry.get(key)
        # bool is an int subclass; a ``true`` flag is not a window size.
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None


def _parse_models_listing(payload: object) -> dict[str, int]:
    """Map model id -> context length from an OpenAI-style ``{"data": [...]}``."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return {}
    windows: dict[str, int] = {}
    for entry in payload["data"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        length = _extract_context_length(entry)
        if length is not None:
            windows[entry["id"]] = length
    return windows


def refresh_orcarouter_context_windows(base_url: str, api_key: str) -> None:
    """Fetch ``{base_url}/models`` into the cache if the cache is stale.

    Safe to call on every agent build: it is a no-op while the last attempt is
    younger than ``ORCAROUTER_MODELS_CACHE_TTL_SECONDS``. Failures are logged
    and cached for the same TTL; the previous successful listing, if any, is
    kept.
    """
    with _cache.lock:
        now = time.monotonic()
        if (
            _cache.last_fetch_at is not None
            and now - _cache.last_fetch_at < ORCAROUTER_MODELS_CACHE_TTL_SECONDS
        ):
            return
        _cache.last_fetch_at = now

    url = f"{base_url.rstrip('/')}/models"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=ORCAROUTER_MODELS_FETCH_TIMEOUT_SECONDS,
            # Never forward the key to wherever a redirect points.
            follow_redirects=False,
        )
        response.raise_for_status()
        windows = _parse_models_listing(response.json())
    # ``httpx.InvalidURL`` is not an ``HTTPError``: a scheme-valid but
    # malformed endpoint (e.g. ``http://[::1``) raises it while building the
    # request, before any I/O.
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        logger.warning(
            "Could not fetch OrcaRouter model listing (%s); using cached or "
            "fallback context windows.",
            type(exc).__name__,
        )
        return

    if not windows:
        logger.warning(
            "OrcaRouter model listing reported no context lengths; using the "
            "fallback context window."
        )
        return

    with _cache.lock:
        _cache.windows = windows


def get_orcarouter_context_window(model_name: str) -> int:
    """Cached context window for a bare OrcaRouter model id (no I/O)."""
    return _cache.windows.get(model_name, ORCAROUTER_FALLBACK_CONTEXT_WINDOW)


def clear_orcarouter_context_cache() -> None:
    """Drop cached windows and the fetch timestamp (test isolation)."""
    with _cache.lock:
        _cache.windows = {}
        _cache.last_fetch_at = None
