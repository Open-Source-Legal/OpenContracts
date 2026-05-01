"""LLM resolution layer.

Bridges admin-curated :class:`RegisteredLLM` rows to runtime values that
pydantic-ai and the OpenContracts agent factory need:

* Has the row been admin-disabled or archived?
* Is the named provider class actually registered in code?
* Does ``LLMSettings.encrypted_secrets`` carry a non-empty ``api_key``
  for that provider?
* What's the pydantic-ai model identifier and the API key to inject?

Phase 2a provides the pure functions and a single ``resolve_extract_llm()``
entry point. Phase 2b plumbs the entry point into
``data_extract_tasks.doc_extract_query_task`` and the structured-response
agent path. Phase 4 adds ``Column.preferred_llm`` on top of the same
resolver.

Failure-mode vocabulary (carried on ``LLMUnavailableError.failure_mode``)
gives callers a way to distinguish between "no admin config exists yet —
fall back to legacy DEFAULT_EXTRACT_MODEL" and "admin config exists but
is broken — fail loudly so the misconfiguration is visible":

* ``"llm_not_configured"`` — ``LLMSettings.default_extract_llm`` is
  unset. Pre-Phase-2 deploys are always in this state; callers should
  fall back to ``DEFAULT_EXTRACT_MODEL`` + env-var keys.
* ``"llm_unavailable"`` — a default *was* set but isn't currently
  resolvable (provider de-registered, API key cleared, row archived,
  etc.). Callers should record this verbatim as the failure mode and
  fail the operation rather than silently substituting another model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Failure-mode strings — kept in this module rather than constants/llm.py
# because they're produced and consumed entirely within the resolver +
# its callers. Do not rename without grepping for grep-able dashboards.
FAILURE_MODE_NOT_CONFIGURED = "llm_not_configured"
FAILURE_MODE_UNAVAILABLE = "llm_unavailable"


class LLMUnavailableError(RuntimeError):
    """Raised when no resolvable LLM is available for the requested context.

    Carries a structured ``failure_mode`` string so call sites that record
    structured failure reasons (notably ``data_extract_tasks``) can
    persist a coherent label and so callers can branch on
    ``"llm_not_configured"`` (legacy fallback) vs ``"llm_unavailable"``
    (loud failure).
    """

    def __init__(
        self,
        message: str,
        *,
        failure_mode: str = FAILURE_MODE_UNAVAILABLE,
    ) -> None:
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

    def to_pydantic_ai_model(self) -> Any:
        """Materialise an explicit pydantic-ai ``Model`` instance.

        Looks the provider class up in the registry and dispatches to its
        ``build_pydantic_ai_model`` classmethod, which constructs the
        right ``pydantic_ai.models.*`` object with the resolved api_key /
        base_url / organization_id baked in. The returned object is what
        ``PydanticAIAgent(model=...)`` should receive when an admin has
        configured an explicit api_key — so pydantic-ai uses *that* key
        and not whatever's in ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``
        in the worker's environment.

        Raises :class:`LLMUnavailableError` (failure_mode=
        ``llm_unavailable``) if the provider is no longer registered;
        this should not happen on resolved rows in practice, but the
        defensive branch keeps the contract clean.
        """
        from opencontractserver.llms.providers.registry import get_provider_registry

        provider_cls = get_provider_registry().get(self.provider_class_path)
        if provider_cls is None:
            raise LLMUnavailableError(
                f"Provider class {self.provider_class_path!r} is not registered "
                "(was it removed between resolution and call time?)",
                failure_mode=FAILURE_MODE_UNAVAILABLE,
            )
        return provider_cls.build_pydantic_ai_model(
            model_id=self.pydantic_ai_model_string.split(":", 1)[1],
            api_key=self.api_key,
            base_url=self.base_url,
            organization_id=self.organization_id,
        )


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

    Raises :class:`LLMUnavailableError` (failure_mode=``llm_unavailable``)
    if the row isn't resolvable. Centralising the model-string + api-key
    materialisation here means callers (extract task, agent factory)
    never assemble ``"openai:"`` prefixes themselves.
    """
    from opencontractserver.llm_configs.models import LLMSettings
    from opencontractserver.llms.providers.registry import get_provider_registry

    settings_instance = LLMSettings.get_instance()
    reason = unavailable_reason(rl, llm_settings=settings_instance)
    if reason is not None:
        raise LLMUnavailableError(
            f"RegisteredLLM {rl.pk} ({rl.display_name!r}) is not resolvable: {reason}",
            failure_mode=FAILURE_MODE_UNAVAILABLE,
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


def resolve_default_llm() -> ResolvedLLM:
    """Resolve the default LLM for non-extract agent paths (chat, corpus
    actions, websocket sessions).

    Phase 2b: shares the same ``LLMSettings.default_extract_llm`` row as
    :func:`resolve_extract_llm`. The naming asymmetry is deliberate —
    callers should use this function for non-extract agent contexts so
    that a future migration introducing a separate
    ``LLMSettings.default_chat_llm`` (or similar) only needs to update
    this one function. The two-failure-mode contract is identical.
    """
    return resolve_extract_llm()


def resolve_extract_llm() -> ResolvedLLM:
    """Resolve the LLM the extract pipeline should use right now.

    Phase 2a/b: walks ``LLMSettings.default_extract_llm`` only. Phase 4
    will add a ``column`` parameter and prefer ``column.preferred_llm``
    when set.

    Raises :class:`LLMUnavailableError` with one of two failure modes:

    * ``"llm_not_configured"`` if no default is set (pre-Phase-2 deploy).
      Callers should fall back to ``DEFAULT_EXTRACT_MODEL`` + env-var keys.
    * ``"llm_unavailable"`` if a default *is* set but isn't resolvable.
      Callers should fail the operation and persist the failure_mode.
    """
    from opencontractserver.llm_configs.models import LLMSettings

    settings_instance = LLMSettings.get_instance()
    default = settings_instance.default_extract_llm
    if default is None:
        raise LLMUnavailableError(
            "No default extract LLM configured. An administrator must "
            "register an LLM and set it as the extract default in /admin/llms.",
            failure_mode=FAILURE_MODE_NOT_CONFIGURED,
        )
    return resolve(default)
