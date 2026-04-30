"""LLM resolution layer.

Bridges admin-curated :class:`RegisteredLLM` rows to runtime values that
pydantic-ai and the OpenContracts agent factory need:

* Has the row been admin-disabled or archived?
* Is the named provider class actually registered in code?
* Does ``LLMSettings.encrypted_secrets`` carry a non-empty ``api_key``
  for that provider?
* What's the pydantic-ai model identifier and the API key to inject?

Phase 2a (this commit) provides the pure functions and a single
``resolve_extract_llm()`` entry point that picks the
``LLMSettings.default_extract_llm``. Phase 2b will plumb the entry point
into ``data_extract_tasks.doc_extract_query_task`` and ``AgentConfig``.
Phase 4 adds ``Column.preferred_llm`` on top of the same resolver.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """Raised when no resolvable LLM is available for the requested context.

    Carries a structured ``failure_mode`` string matching the vocabulary
    in :mod:`opencontractserver.constants.llm` so call sites that record
    structured failure reasons (notably
    ``data_extract_tasks._classify_none_result``) can persist a coherent
    label without inventing new strings.
    """

    def __init__(self, message: str, *, failure_mode: str = "llm_unavailable") -> None:
        super().__init__(message)
        self.failure_mode = failure_mode


@dataclass(frozen=True)
class ResolvedLLM:
    """Runtime view of a :class:`RegisteredLLM` row ready to be passed to
    pydantic-ai / the agent factory.
    """

    registered_llm_id: int
    provider_class_path: str
    provider_title: str
    pydantic_ai_model_string: str
    api_key: str
    base_url: Optional[str]
    organization_id: Optional[str]
    context_window: Optional[int]
    supports_structured_output: bool
    supports_tools: bool
    max_output_tokens: Optional[int]
    temperature_default: Optional[float]


# ---------------------------------------------------------------------------
# Resolvability
# ---------------------------------------------------------------------------


def is_resolvable(rl, llm_settings=None) -> bool:
    """Return True iff ``rl`` (a :class:`RegisteredLLM`) can run a call now.

    Checks, in order:

    1. ``rl.is_enabled and not rl.is_archived``
    2. ``rl.provider_class_path`` is registered in :class:`LLMProviderRegistry`
    3. ``LLMSettings.has_valid_secrets(rl.provider_class_path)`` (non-empty
       ``api_key`` configured).

    Imports are deferred to keep this module importable from
    ``llm_configs.models`` without creating a circular dependency.
    """
    if not (rl.is_enabled and not rl.is_archived):
        return False

    from opencontractserver.llm_configs.models import LLMSettings
    from opencontractserver.llms.providers.registry import get_provider_registry

    provider = get_provider_registry().get(rl.provider_class_path)
    if provider is None:
        return False

    settings_instance = llm_settings or LLMSettings.get_instance()
    return settings_instance.has_valid_secrets(rl.provider_class_path)


def unavailable_reason(rl, llm_settings=None) -> Optional[str]:
    """Human-readable explanation of why ``rl`` is not resolvable.

    Returns ``None`` when ``rl`` *is* resolvable. The frontend uses this
    string verbatim in the column-picker tooltip when an LLM is greyed
    out, so phrasing should be operator-actionable.
    """
    if not rl.is_enabled:
        return "Disabled by an administrator."
    if rl.is_archived:
        return "Archived (no longer available for new selections)."

    from opencontractserver.llm_configs.models import LLMSettings
    from opencontractserver.llms.providers.registry import get_provider_registry

    provider = get_provider_registry().get(rl.provider_class_path)
    if provider is None:
        return (
            f"Provider class '{rl.provider_class_path}' is not registered in "
            "this deployment. The provider integration may have been removed "
            "or the class path may be wrong."
        )

    settings_instance = llm_settings or LLMSettings.get_instance()
    if not settings_instance.has_valid_secrets(rl.provider_class_path):
        return (
            f"No API key configured for provider '{provider.title or provider.__name__}'. "
            "An administrator must add credentials in /admin/llms."
        )

    return None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve(rl) -> ResolvedLLM:
    """Build a :class:`ResolvedLLM` from a :class:`RegisteredLLM` row.

    Raises :class:`LLMUnavailableError` if the row isn't resolvable.
    Centralising the model-string + api-key materialisation here means
    callers (extract task, agent factory) never assemble ``"openai:"``
    prefixes themselves.
    """
    from opencontractserver.llm_configs.models import LLMSettings
    from opencontractserver.llms.providers.registry import get_provider_registry

    settings_instance = LLMSettings.get_instance()
    reason = unavailable_reason(rl, llm_settings=settings_instance)
    if reason is not None:
        raise LLMUnavailableError(
            f"RegisteredLLM {rl.pk} ({rl.display_name!r}) is not resolvable: {reason}"
        )

    provider = get_provider_registry().get(rl.provider_class_path)
    full_settings = settings_instance.get_full_provider_settings(rl.provider_class_path)
    api_key = str(full_settings.get("api_key", "") or "")
    base_url = full_settings.get("base_url") or None
    organization_id = full_settings.get("organization_id") or None

    return ResolvedLLM(
        registered_llm_id=rl.pk,
        provider_class_path=rl.provider_class_path,
        provider_title=provider.title or provider.__name__,
        pydantic_ai_model_string=f"{provider.pydantic_ai_prefix}:{rl.model_id}",
        api_key=api_key,
        base_url=base_url,
        organization_id=organization_id,
        context_window=rl.context_window,
        supports_structured_output=rl.supports_structured_output,
        supports_tools=rl.supports_tools,
        max_output_tokens=rl.max_output_tokens,
        temperature_default=rl.temperature_default,
    )


def resolve_extract_llm() -> ResolvedLLM:
    """Resolve the LLM the extract pipeline should use right now.

    Phase 2a: walks ``LLMSettings.default_extract_llm`` only. Phase 4 will
    add a ``column`` parameter and prefer ``column.preferred_llm`` when
    set.

    Raises :class:`LLMUnavailableError` if no resolvable default exists,
    so callers can fall back to ``DEFAULT_EXTRACT_MODEL`` (preserves
    pre-Phase-2 behavior on fresh deploys with no admin config).
    """
    from opencontractserver.llm_configs.models import LLMSettings

    settings_instance = LLMSettings.get_instance()
    default = settings_instance.default_extract_llm
    if default is None:
        raise LLMUnavailableError(
            "No default extract LLM configured. An administrator must "
            "register an LLM and set it as the extract default in /admin/llms."
        )
    return resolve(default)
