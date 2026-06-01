"""Helpers for resolving LLM model specs.

OpenContracts uses ``pydantic-ai``'s provider-prefixed model strings —
``{provider_key}:{model_name}`` (e.g. ``"anthropic:claude-opus-4-6"``)
— as the single source of truth for which LLM to invoke. Unprefixed
strings default to the ``openai`` provider so legacy ``OPENAI_MODEL``
values (``"gpt-4o"``) keep working untouched.

This module is the single resolver consulted by the agent factory; it
walks the per-call → per-agent → per-corpus → settings-default
priority order and returns the canonical model spec.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Default provider for bare model strings — back-compat with the legacy
# ``OPENAI_MODEL`` setting, which never carried a prefix.
DEFAULT_PROVIDER_KEY: str = "openai"

# Hard fallback when neither DEFAULT_LLM nor OPENAI_MODEL is configured.
_HARD_DEFAULT_MODEL: str = "gpt-4o"


class LLMProviderNotRegistered(ValueError):
    """The provider prefix on a model spec has no registered LLMProvider component."""


def parse_model_spec(spec: str) -> tuple[str, str]:
    """Split a pydantic-ai model spec into ``(provider_key, bare_model)``.

    ``"anthropic:claude-opus-4-6"`` → ``("anthropic", "claude-opus-4-6")``.
    A bare model name (no colon) is treated as an OpenAI model so legacy
    ``OPENAI_MODEL`` values keep working.

    Raises:
        ValueError: If ``spec`` is empty or malformed.
    """
    if not spec or not spec.strip():
        raise ValueError("Empty model spec")
    cleaned = spec.strip()
    if ":" in cleaned:
        provider, _, model = cleaned.partition(":")
        provider = provider.strip()
        model = model.strip()
        if not provider or not model:
            raise ValueError(f"Malformed model spec: {spec!r}")
        return provider, model
    return DEFAULT_PROVIDER_KEY, cleaned


def normalise_model_spec(spec: str) -> str:
    """Return the canonical ``"{provider}:{model}"`` form of a spec."""
    provider, model = parse_model_spec(spec)
    return f"{provider}:{model}"


def validate_model_spec(spec: str) -> None:
    """Validate that ``spec`` parses and its provider is registered.

    The bare model name itself is not strictly checked against
    ``supported_models``: that list is a UI suggestion, and we want
    callers to be able to use newly-released models without waiting on
    a code change.

    Raises:
        ValueError: If the spec is malformed.
        LLMProviderNotRegistered: If the provider prefix has no
            matching registered :class:`BaseLLMProvider` component.
    """
    provider_key, _ = parse_model_spec(spec)
    # Lazy import — the pipeline registry pulls Django apps, which is
    # not safe at module-import time during early startup.
    from opencontractserver.pipeline.registry import get_llm_provider_by_key_cached

    if get_llm_provider_by_key_cached(provider_key) is None:
        raise LLMProviderNotRegistered(
            f"Provider {provider_key!r} (from spec {spec!r}) is not registered. "
            "Add a BaseLLMProvider subclass under "
            "opencontractserver/pipeline/llm_providers/."
        )


def resolve_model_spec(
    *,
    explicit: str | None = None,
    agent_preferred: str | None = None,
    corpus_preferred: str | None = None,
    settings_default: str | None = None,
) -> str:
    """Resolve a model spec by walking the documented priority order.

    Priority (highest wins):

        ``explicit`` → ``agent_preferred`` → ``corpus_preferred`` →
        ``settings_default`` → Django settings.

    ``settings_default`` is the install-wide default configured at runtime
    via ``PipelineSettings.default_llm`` (set by superusers in the admin
    System Settings UI). It is threaded in by callers rather than read here
    so this resolver stays free of ORM access and safe to call from async
    contexts. When unset, the chain falls back to ``settings.DEFAULT_LLM``
    and finally the legacy ``settings.OPENAI_MODEL``.

    Empty / whitespace-only values are skipped at every tier so callers can
    pass through ``None`` or ``""`` without poisoning the chain.

    Returns:
        A non-empty, normalised pydantic-ai model spec.
    """
    for candidate in (explicit, agent_preferred, corpus_preferred, settings_default):
        if candidate and candidate.strip():
            return normalise_model_spec(candidate)

    default = (
        getattr(settings, "DEFAULT_LLM", None)
        or getattr(settings, "OPENAI_MODEL", None)
        or _HARD_DEFAULT_MODEL
    )
    return normalise_model_spec(default)
