"""Resolution layer between admin-managed LLM config and runtime callers.

This module is the single chokepoint that takes a *consumer* (today: an
``extracts.Column``; tomorrow: chat sessions, agent runs, …) and produces
everything pydantic-ai needs to invoke a model: the model string, the
credentials packaged as env-var overrides, and the model defaults.

Failure modes:

* ``LLMUnavailableError`` is raised when neither the consumer nor the system
  default points at a usable model. This is *operational* — surface it to
  the user via the cell's failure message, don't crash the worker.
* ``LLMNotConfiguredError`` is raised when no models are registered at all.

Both inherit from ``LLMConfigError`` so callers can decide how granular to be.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator, Optional

from opencontractserver.llms.models import LLMConfigSettings, LLMModel
from opencontractserver.llms.providers import (
    BaseLLMProvider,
    get_provider_registry,
)

if TYPE_CHECKING:
    from opencontractserver.extracts.models import Column

logger = logging.getLogger(__name__)


class LLMConfigError(Exception):
    """Base class for LLM-config resolution errors."""


class LLMUnavailableError(LLMConfigError):
    """The model the caller asked for exists but is not currently usable."""


class LLMNotConfiguredError(LLMConfigError):
    """No usable model is registered at all (system has not been configured)."""


@dataclass(frozen=True)
class ResolvedLLM:
    """Materialised configuration ready to hand to the agent factory."""

    model: LLMModel
    provider: BaseLLMProvider
    pydantic_ai_model_string: str
    environment_overrides: dict[str, str | None]
    default_temperature: float
    extra_settings: dict


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def list_available_models(*, include_disabled: bool = False) -> list[LLMModel]:
    """Return models that admins have enabled *and* whose provider is configured.

    Used by:

    * the column-editor dropdown (``include_disabled=False``);
    * the admin "Models" tab (``include_disabled=True`` — show everything but
      mark availability per-row in the UI).
    """
    settings = LLMConfigSettings.get_instance()
    registry = get_provider_registry()

    queryset = LLMModel.objects.all()
    if not include_disabled:
        queryset = queryset.filter(is_enabled=True)

    available: list[LLMModel] = []
    for model in queryset:
        if registry.get(model.provider_key) is None:
            continue
        if not include_disabled and not settings.is_provider_configured(
            model.provider_key
        ):
            continue
        available.append(model)
    return available


def resolve_model_for_column(column: "Column") -> ResolvedLLM:
    """Resolve the LLM for an extract column.

    Fallback chain:
        column.preferred_llm_model → settings.default_model → raise.

    Raises:
        LLMUnavailableError: column points at a model that is no longer usable.
        LLMNotConfiguredError: no preferred model and no system default.
    """
    settings = LLMConfigSettings.get_instance()

    chosen: Optional[LLMModel] = column.preferred_llm_model
    if chosen is not None:
        if not chosen.is_available():
            raise LLMUnavailableError(
                _format_unavailable_reason(chosen, settings, "column")
            )
        return _build_resolved(chosen, settings)

    fallback = settings.default_model
    if fallback is None:
        raise LLMNotConfiguredError(
            "No LLM model is configured for this column and no system default "
            "is set. An administrator must register a provider and a default "
            "model in System Settings → LLMs."
        )
    if not fallback.is_available():
        raise LLMUnavailableError(
            _format_unavailable_reason(fallback, settings, "default")
        )
    return _build_resolved(fallback, settings)


def resolve_model_by_id(model_id: int) -> ResolvedLLM:
    """Resolve an explicit ``LLMModel`` row (used by tests and chat callers)."""
    settings = LLMConfigSettings.get_instance()
    try:
        model = LLMModel.objects.get(pk=model_id)
    except LLMModel.DoesNotExist as exc:  # noqa: PERF203
        raise LLMUnavailableError(f"LLMModel id={model_id} does not exist") from exc

    if not model.is_available():
        raise LLMUnavailableError(_format_unavailable_reason(model, settings, "explicit"))
    return _build_resolved(model, settings)


@contextmanager
def applied_environment(
    overrides: dict[str, str | None],
) -> Iterator[None]:
    """Temporarily apply env-var overrides; restore previous values on exit.

    Used to inject per-provider API keys into the process env right before
    invoking pydantic-ai, then unset them afterwards. Single-process safe;
    NOT thread-safe within one process — Celery prefork workers (the typical
    deployment) get one process per worker so this is the right scope.
    """
    saved: dict[str, str | None] = {}
    try:
        for key, value in overrides.items():
            saved[key] = os.environ.get(key)
            if value is None or value == "":
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, prev in saved.items():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _build_resolved(model: LLMModel, settings: LLMConfigSettings) -> ResolvedLLM:
    registry = get_provider_registry()
    provider_instance = registry.get_instance(model.provider_key)
    if provider_instance is None:
        raise LLMUnavailableError(
            f"Provider '{model.provider_key}' is not registered in this build."
        )
    credentials = settings.get_full_provider_credentials(model.provider_key)
    return ResolvedLLM(
        model=model,
        provider=provider_instance,
        pydantic_ai_model_string=provider_instance.build_model_string(model.model_name),
        environment_overrides=provider_instance.build_environment_overrides(credentials),
        default_temperature=model.default_temperature,
        extra_settings=dict(model.extra_settings or {}),
    )


def _format_unavailable_reason(
    model: LLMModel, settings: LLMConfigSettings, source: str
) -> str:
    """Human-readable reason string for unavailable-model errors.

    ``source`` is one of "column" / "default" / "explicit" — used to phrase
    the message so the user knows why this particular model was attempted.
    """
    registry = get_provider_registry()
    if registry.get(model.provider_key) is None:
        reason = f"provider '{model.provider_key}' is not registered"
    elif not model.is_enabled:
        reason = "the model has been disabled by an administrator"
    elif not settings.is_provider_configured(model.provider_key):
        reason = (
            f"the {model.provider_key} provider does not have credentials configured"
        )
    else:
        reason = "the model is not currently usable"

    if source == "column":
        prefix = f"The model '{model.display_name}' selected for this column is unavailable"
    elif source == "default":
        prefix = f"The system default model '{model.display_name}' is unavailable"
    else:
        prefix = f"LLM model '{model.display_name}' is unavailable"

    return f"{prefix}: {reason}."
