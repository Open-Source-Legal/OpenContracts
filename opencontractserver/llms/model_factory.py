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

import inspect
import logging
from typing import Any, Optional

from asgiref.sync import sync_to_async

from opencontractserver.llms.llm_registry import parse_model_spec

logger = logging.getLogger(__name__)


def _provider_class_path(provider_key: str) -> Optional[str]:
    """Return the full class path of the registered provider for ``provider_key``."""
    # Lazy import — the registry pulls Django apps, which is unsafe at module
    # import time during early startup.
    from opencontractserver.pipeline.registry import get_llm_provider_by_key_cached

    definition = get_llm_provider_by_key_cached(provider_key)
    return definition.class_name if definition else None


def _get_db_credentials(provider_key: str) -> dict[str, str]:
    """Read DB-configured credentials for a provider from ``PipelineSettings``.

    Returns a dict with optional ``api_key`` / ``base_url`` keys (only
    present when non-empty). Empty when the provider is unknown or has no
    credentials configured. Performs ORM access — invoke from a sync
    context or via :func:`abuild_agent_model`.
    """
    class_path = _provider_class_path(provider_key)
    if not class_path:
        return {}

    try:
        from opencontractserver.documents.models import PipelineSettings

        stored = PipelineSettings.get_instance().get_full_component_settings(class_path)
    except Exception:
        # DB unavailable (migrations / early startup) — fall back to env.
        logger.debug(
            "Could not read LLM provider settings for %r; using env fallback.",
            provider_key,
            exc_info=True,
        )
        return {}

    creds: dict[str, str] = {}
    for key in ("api_key", "base_url"):
        value = (stored or {}).get(key)
        if isinstance(value, str) and value.strip():
            creds[key] = value.strip()
    return creds


def _provider_init_kwargs(provider_cls: type, creds: dict[str, str]) -> dict[str, str]:
    """Select the credential kwargs a provider ``__init__`` actually accepts.

    Filtering by the real signature means we never pass ``base_url`` to a
    provider that does not support it (which would raise) — a configured
    endpoint for such a provider is simply ignored.
    """
    try:
        params = inspect.signature(provider_cls.__init__).parameters
    except (TypeError, ValueError):
        params = {}
    kwargs: dict[str, str] = {}
    for name in ("api_key", "base_url"):
        if name in params and creds.get(name):
            kwargs[name] = creds[name]
    return kwargs


def _construct_model(
    provider_key: str, model_name: str, creds: dict[str, str]
) -> Optional[Any]:
    """Build a ``pydantic-ai`` model carrying explicit provider credentials.

    Returns ``None`` for providers we have no construction recipe for, so
    the caller can fall back to the bare spec string (env credentials).
    """
    if provider_key in ("openai", "ollama"):
        from pydantic_ai.providers.openai import OpenAIProvider

        try:
            from pydantic_ai.models.openai import OpenAIChatModel as _Model
        except ImportError:  # pragma: no cover - older pydantic-ai alias
            from pydantic_ai.models.openai import OpenAIModel as _Model

        kwargs = _provider_init_kwargs(OpenAIProvider, creds)
        # Ollama (and other OpenAI-compatible local servers) require *some*
        # api_key for the underlying OpenAI client even when the server
        # ignores it. Supply a harmless placeholder when none is configured.
        if provider_key == "ollama" and "api_key" not in kwargs:
            kwargs["api_key"] = "ollama"
        return _Model(model_name, provider=OpenAIProvider(**kwargs))

    if provider_key == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        kwargs = _provider_init_kwargs(AnthropicProvider, creds)
        return AnthropicModel(model_name, provider=AnthropicProvider(**kwargs))

    if provider_key in ("google-gla", "google", "google-vertex"):
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        kwargs = _provider_init_kwargs(GoogleProvider, creds)
        return GoogleModel(model_name, provider=GoogleProvider(**kwargs))

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
    except Exception:
        logger.warning(
            "Failed to build a credentialed model for provider %r; falling "
            "back to environment credentials.",
            provider_key,
            exc_info=True,
        )
        return spec

    if model is None:
        return spec

    logger.info(
        "Using DB-configured credentials for LLM provider %r (custom_endpoint=%s).",
        provider_key,
        bool(creds.get("base_url")),
    )
    return model


async def abuild_agent_model(spec: str) -> Any:
    """Async wrapper around :func:`build_agent_model` (safe ORM access)."""
    return await sync_to_async(build_agent_model)(spec)
