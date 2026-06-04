"""Base class for LLM provider pipeline components.

LLM providers describe a model family supported by ``pydantic-ai`` —
OpenAI, Anthropic, Google, Ollama, and so on — together with the
suggested models that ship with the provider's SDK and, crucially, the
**runtime-configurable credentials** (API key + custom endpoint) used to
reach them.

Like every other ``BaseXxx`` pipeline component, providers declare a
nested :class:`Settings` dataclass. The ``api_key`` (``SECRET``) and
``base_url`` (``OPTIONAL``) fields are stored in the ``PipelineSettings``
DB singleton — encrypted for the secret — and managed live by superusers
in the System Settings UI, exactly like a parser's or embedder's
credentials. This means an operator can rotate an API key or point a
provider at a self-hosted / OpenAI-compatible gateway **without editing
environment variables or redeploying**.

Resolution is *DB-wins / env-fallback*: when a credential is configured
in the singleton it overrides the process environment; when it is not,
``pydantic-ai`` resolves the credential from the environment as before.
The DB credentials are threaded into a concrete ``pydantic-ai`` model
object by :mod:`opencontractserver.llms.model_factory`.

Discovery follows the same pattern as :class:`BaseEmbedder` and the
other components — the :class:`PipelineComponentRegistry` walks the
``opencontractserver.pipeline.llm_providers`` package on first access
and registers every concrete subclass, reading the ``Settings`` schema
off the class (providers are never instantiated).
"""

from __future__ import annotations

from abc import ABC
from dataclasses import field
from typing import ClassVar

from opencontractserver.pipeline.base.base_component import PipelineComponentBase
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)


def llm_api_key_field(env_var: str):
    """Build the standard ``api_key`` field for an LLM provider's Settings.

    Marked ``SECRET`` so the value is stored encrypted in the
    ``PipelineSettings`` singleton and never exposed back through GraphQL.
    ``required=False`` because the env var remains a valid fallback — a
    provider works without a DB key as long as the environment supplies
    one. ``env_var`` is the environment variable ``pydantic-ai`` / the
    provider SDK reads when no DB key is set; it is surfaced to the admin
    UI as an "also settable via …" hint.
    """
    return field(
        default="",
        metadata={
            "pipeline_setting": PipelineSetting(
                setting_type=SettingType.SECRET,
                required=False,
                description=(
                    "API key for this provider. Stored encrypted. When set, "
                    f"it overrides the {env_var} environment variable; leave "
                    "blank to fall back to the environment."
                ),
                env_var=env_var,
            )
        },
    )


def llm_base_url_field(default: str = "", env_var: str | None = None):
    """Build the standard ``base_url`` field for an LLM provider's Settings.

    A plaintext ``OPTIONAL`` setting for pointing the provider at a custom
    endpoint — an OpenAI-compatible gateway, a proxy, or a self-hosted
    deployment — without touching the environment. Blank means "use the
    provider SDK default".
    """
    return field(
        default=default,
        metadata={
            "pipeline_setting": PipelineSetting(
                setting_type=SettingType.OPTIONAL,
                required=False,
                description=(
                    "Custom API endpoint / base URL (e.g. an OpenAI-compatible "
                    "gateway, proxy, or self-hosted deployment). Leave blank to "
                    "use the provider's default endpoint."
                ),
                env_var=env_var,
            )
        },
    )


class BaseLLMProvider(PipelineComponentBase, ABC):
    """Base class for LLM provider pipeline components.

    Subclasses declare:

    * ``provider_key`` — pydantic-ai's provider prefix (e.g. ``"openai"``,
      ``"anthropic"``, ``"google-gla"``, ``"ollama"``). Used to build
      the full ``"{provider_key}:{model_name}"`` spec accepted by
      ``pydantic_ai.Agent(model=...)`` and to key credential lookups in
      :mod:`opencontractserver.llms.model_factory`.
    * ``supported_models`` — suggested bare model names exposed to the
      UI (e.g. ``("claude-opus-4-6", "claude-haiku-4-5")``). Not
      strictly enforced at runtime so newer models can be used without
      a code change.
    * ``requires_api_key`` — whether the provider needs a credential.
      Most do; ``ollama`` (local) does not.
    * a nested ``Settings`` dataclass carrying ``api_key`` /
      ``base_url`` — built with :func:`llm_api_key_field` /
      :func:`llm_base_url_field` so the credentials land in the
      ``PipelineSettings`` singleton and the System Settings UI.

    Providers are never instantiated — the registry reads their class
    attributes and ``Settings`` schema directly.
    """

    # Identity used to build pydantic-ai model strings and to key
    # credential lookups. Override in every concrete subclass.
    provider_key: ClassVar[str] = ""

    # Suggested model names exposed to the UI. Not strictly enforced at
    # runtime so users can pass newer models without waiting on a code
    # change.
    supported_models: ClassVar[tuple[str, ...]] = ()

    # Whether the provider needs an API credential (Ollama does not).
    requires_api_key: ClassVar[bool] = True
