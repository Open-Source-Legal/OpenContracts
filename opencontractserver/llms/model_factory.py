"""Credential-aware construction of ``pydantic-ai`` model objects.

This module bridges the runtime-configurable LLM provider credentials
stored in the ``PipelineSettings`` DB singleton — an encrypted ``api_key``
plus a plaintext ``base_url``, declared on each
:class:`~opencontractserver.pipeline.base.llm_provider.BaseLLMProvider`
``Settings`` dataclass and managed live by superusers in the System
Settings UI — into the model layer that ``pydantic-ai`` actually invokes.

Resolution precedence is **DB-wins / env-fallback**:

* When the spec's provider has an ``api_key`` and/or ``base_url``
  configured in the singleton, :func:`build_agent_model` returns a
  concrete ``pydantic-ai`` ``Model`` whose ``Provider`` carries those
  credentials — overriding whatever is in the process environment.
* When nothing is configured (the default for a fresh install), it
  returns the bare ``"{provider}:{model}"`` spec string and lets
  ``pydantic-ai`` resolve credentials from the environment exactly as
  before. This keeps existing deployments byte-for-byte unchanged.

Any failure to build a credentialed model (unknown provider, a
``pydantic-ai`` API shift, a bad endpoint) degrades to the bare spec
string rather than raising, so a misconfiguration can never take the
chat path down — it simply falls back to environment credentials.

All ``pydantic-ai`` imports live here (not in the framework-agnostic
``opencontractserver.pipeline`` package) and are performed lazily so the
pipeline registry stays importable during early startup / migrations.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from asgiref.sync import sync_to_async
from django.core.exceptions import AppRegistryNotReady, ImproperlyConfigured
from django.db import Error as DatabaseError

from opencontractserver.llms.llm_registry import parse_model_spec

logger = logging.getLogger(__name__)

# Reading DB-configured credentials can legitimately fail when the DB is
# unavailable (migrations / early startup / app registry not ready). Those
# are recoverable — fall back to env credentials. A programming bug
# (TypeError from a wrong signature, etc.) is NOT in this set and is allowed
# to propagate so it surfaces instead of silently degrading.
_DB_READ_RECOVERABLE_ERRORS = (
    DatabaseError,
    AppRegistryNotReady,
    ImproperlyConfigured,
    ImportError,
    OSError,
)

# Building a credentialed pydantic-ai model can fail on an API shift (an
# import that moved, a renamed kwarg) or a bad endpoint value. These degrade
# to the bare spec string; genuine bugs (e.g. TypeError) still propagate.
_MODEL_BUILD_RECOVERABLE_ERRORS = (
    ImportError,
    AttributeError,
    ValueError,
    OSError,
    RuntimeError,
)


def _provider_class_path(provider_key: str) -> str | None:
    """Return the full class path of the registered provider for ``provider_key``."""
    # Lazy import — the registry pulls Django apps, which is unsafe at module
    # import time during early startup.
    from opencontractserver.pipeline.registry import get_llm_provider_by_key_cached

    definition = get_llm_provider_by_key_cached(provider_key)
    return definition.class_name if definition else None


# Process-local cache of resolved per-provider credentials keyed on
# ``(class_path, PipelineSettings.modified)`` — the same key the reranker and
# embedder instance caches use (``opencontractserver/pipeline/utils.py``).
#
# ``_get_db_credentials`` runs on *every* agent build — every chat message,
# every structured-output call, every memory-curation task. ``PipelineSettings``
# already caches the singleton row (Django cache, 5-min TTL), so this is not a
# DB round-trip per call, but resolving a provider's secret still decrypts the
# Fernet store, and that decryption derives its key with a deliberately
# expensive PBKDF2 KDF (hundreds of thousands of HMAC iterations — see
# ``PipelineSettings._derive_key``). ``get_full_component_settings`` reads the
# secret store twice (merged settings + secrets overlay), so two KDF passes ran
# on every build once any provider key was configured (issue #1921).
#
# Caching the *resolved* creds amortises that across calls. Live-rotation is
# preserved: every credential write in production flows through
# ``PipelineSettings.save()``, which bumps ``modified`` (auto_now) and clears
# the singleton cache, so the next lookup misses on the new key and re-decrypts
# — a rotated or cleared key takes effect within the existing cache-TTL window
# with no redeploy (the live-configurability guarantee of issue #1897), and the
# cache adds no staleness beyond ``get_instance``'s own TTL. The same issue
# #1410 caveat applies: code paths that bypass ``save()`` (``QuerySet.update``,
# ``bulk_update``, raw migrations) won't bump ``modified``; call
# :func:`invalidate_credential_cache` explicitly in those cases.
_CREDENTIAL_CACHE: dict[tuple[str, Any], dict[str, str]] = {}
# Guards against two concurrent builds paying the decryption cost twice.
# Lookups after warm-up are read-only, so no lock is held on the hot path.
_CREDENTIAL_CACHE_LOCK = threading.Lock()


def invalidate_credential_cache() -> None:
    """Drop cached per-provider credentials.

    In normal operation this is unnecessary — the cache key includes
    ``PipelineSettings.modified`` so any settings write naturally invalidates
    the cache on the next lookup across all workers. Kept for test isolation
    and for callers that mutate the singleton out-of-band (a path that bypasses
    ``save()`` and so leaves ``modified`` unchanged).
    """
    with _CREDENTIAL_CACHE_LOCK:
        _CREDENTIAL_CACHE.clear()


def _get_db_credentials(provider_key: str) -> dict[str, str]:
    """Read DB-configured credentials for a provider from ``PipelineSettings``.

    Returns a dict with optional ``api_key`` / ``base_url`` keys (only
    present when non-empty). Empty when the provider is unknown or has no
    credentials configured. Performs ORM access — invoke from a sync
    context or via :func:`abuild_agent_model`.

    The resolved creds are memoized per ``(class_path, PipelineSettings.modified)``
    so repeat builds skip the Fernet/PBKDF2 decryption; see the
    ``_CREDENTIAL_CACHE`` comment for the invalidation contract.
    """
    class_path = _provider_class_path(provider_key)
    if not class_path:
        return {}

    try:
        from opencontractserver.documents.models import PipelineSettings

        instance = PipelineSettings.get_instance()
        cache_key = (class_path, instance.modified)

        # Fast path: a copy so callers can never mutate the cached dict.
        cached = _CREDENTIAL_CACHE.get(cache_key)
        if cached is not None:
            return dict(cached)

        with _CREDENTIAL_CACHE_LOCK:
            # Double-check — another thread may have populated it while we waited.
            cached = _CREDENTIAL_CACHE.get(cache_key)
            if cached is not None:
                return dict(cached)

            stored = instance.get_full_component_settings(class_path)
            creds: dict[str, str] = {}
            for key in ("api_key", "base_url"):
                value = (stored or {}).get(key)
                if isinstance(value, str) and value.strip():
                    creds[key] = value.strip()

            _CREDENTIAL_CACHE[cache_key] = creds
            return dict(creds)
    except _DB_READ_RECOVERABLE_ERRORS:
        # DB unavailable (migrations / early startup) — fall back to env.
        logger.debug(
            "Could not read LLM provider settings for %r; using env fallback.",
            provider_key,
            exc_info=True,
        )
        return {}


async def aget_provider_credentials(provider_key: str) -> dict[str, str]:
    """DB-configured ``api_key`` / ``base_url`` for a provider (empty when unset).

    The async, safe-ORM entry point for non-chat consumers (e.g. corpus-logo
    image generation) that need the same live-configured provider credentials
    the chat path threads through :func:`build_agent_model`. Keys are present
    only when non-empty; callers apply their own env fallback.
    """
    return await sync_to_async(_get_db_credentials)(provider_key)


def _construct_model(
    provider_key: str, model_name: str, creds: dict[str, str]
) -> Any | None:
    """Build a ``pydantic-ai`` model carrying explicit provider credentials.

    Each provider's ``Provider`` accepts ``api_key`` / ``base_url`` keyword
    arguments (both optional). We pass whatever the DB supplied and leave
    the rest to ``pydantic-ai`` — a ``None`` ``api_key`` means "read the
    provider-native env var", so a base-URL-only override still picks up
    the environment key.

    Returns ``None`` for providers we have no construction recipe for, so
    the caller can fall back to the bare spec string (env credentials).
    """
    api_key = creds.get("api_key")
    base_url = creds.get("base_url")

    if base_url is not None:
        # Only superusers can write this setting, so the threat model is low,
        # but a malformed endpoint (missing scheme, a typo'd host) otherwise
        # fails opaquely deep inside the HTTP client. A scheme check turns it
        # into an early, clear fallback to env credentials.
        from urllib.parse import urlparse

        if urlparse(base_url).scheme not in ("http", "https"):
            logger.warning(
                "DB-configured base_url for provider %r is not a valid "
                "http(s) URL (%r); ignoring it and using env credentials.",
                provider_key,
                base_url,
            )
            return None
        if api_key is None and provider_key != "ollama":
            # A custom endpoint with no key set: pydantic-ai will fall back to
            # the provider-native env var, which a non-standard gateway may not
            # use. Surface the likely misconfiguration at construction time.
            # (ollama is intentionally keyless — a placeholder is supplied
            # below — so it is excluded.)
            logger.warning(
                "DB-configured base_url for provider %r has no api_key; the "
                "request will rely on the provider's env var, which a custom "
                "gateway may not honour.",
                provider_key,
            )

    if provider_key in ("openai", "ollama"):
        from pydantic_ai.providers.openai import OpenAIProvider

        try:
            from pydantic_ai.models.openai import OpenAIChatModel as _Model
        except ImportError:  # pragma: no cover - older pydantic-ai alias
            from pydantic_ai.models.openai import OpenAIModel as _Model

        # Ollama (and other OpenAI-compatible local servers) require *some*
        # api_key for the underlying OpenAI client even when the server
        # ignores it. Supply a harmless placeholder when none is configured.
        if provider_key == "ollama" and not api_key:
            api_key = "ollama"
        return _Model(
            model_name,
            provider=OpenAIProvider(api_key=api_key, base_url=base_url),
        )

    if provider_key == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(
            model_name,
            provider=AnthropicProvider(api_key=api_key, base_url=base_url),
        )

    if provider_key == "google-gla":
        # Only the AI-Studio (``google-gla``) provider is registered and
        # authenticates with an API key. ``google-vertex`` uses
        # service-account ADC credentials, not an api_key — building a
        # ``GoogleProvider(api_key=...)`` for it would construct cleanly
        # but fail at request time. We therefore handle only ``google-gla``
        # here and let any future Vertex provider fall through to the
        # warning + ``None`` (env-fallback) below.
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        # AI-Studio takes no caller-supplied endpoint, so only the key flows
        # through (GoogleProvider has no base_url field on this path).
        return GoogleModel(model_name, provider=GoogleProvider(api_key=api_key))

    # When adding a new provider under ``pipeline/llm_providers/``, add a
    # matching branch above so DB-configured credentials are threaded through
    # to its pydantic-ai ``Model``. Without a branch the provider still works,
    # but silently via env credentials only — the warning below is the only
    # signal that its DB-configured api_key/base_url are being ignored.
    logger.warning(
        "No credentialed-model recipe for provider %r; using environment "
        "credentials (bare model spec).",
        provider_key,
    )
    return None


def build_agent_model(spec: str) -> Any:
    """Resolve a model spec into a bare string or a credentialed ``Model``.

    DB-wins / env-fallback (see module docstring). Synchronous — performs
    ORM access; from an async context use :func:`abuild_agent_model`.

    Args:
        spec: A pydantic-ai model spec, e.g. ``"anthropic:claude-opus-4-6"``.

    Returns:
        Either ``spec`` unchanged (env credentials) or a ``pydantic-ai``
        ``Model`` instance carrying DB-configured credentials.
    """
    try:
        provider_key, model_name = parse_model_spec(spec)
    except ValueError:
        # Malformed spec — let pydantic-ai raise its own clear error later.
        return spec

    creds = _get_db_credentials(provider_key)
    if not creds:
        return spec

    try:
        model = _construct_model(provider_key, model_name, creds)
    except _MODEL_BUILD_RECOVERABLE_ERRORS:
        logger.warning(
            "Failed to build a credentialed model for provider %r; falling "
            "back to environment credentials.",
            provider_key,
            exc_info=True,
        )
        return spec

    if model is None:
        return spec

    # debug, not info: once DB credentials are configured this runs on every
    # single agent build (every chat message, structured call, memory task).
    logger.debug(
        "Using DB-configured credentials for LLM provider %r (custom_endpoint=%s).",
        provider_key,
        bool(creds.get("base_url")),
    )
    return model


async def abuild_agent_model(spec: str) -> Any:
    """Async wrapper around :func:`build_agent_model` (safe ORM access)."""
    return await sync_to_async(build_agent_model)(spec)
