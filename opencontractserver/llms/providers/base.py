"""
Abstract base for LLM provider integrations.

Mirrors the ``PipelineComponentBase`` pattern: each provider is a class
declaring class-level metadata for the admin UI plus a nested ``Settings``
dataclass that uses :class:`PipelineSetting` metadata to describe required /
optional / secret config fields. The ``LLMProviderRegistry`` auto-discovers
all subclasses under :mod:`opencontractserver.llms.providers`.

Providers do **not** know how to call an LLM directly — that's still the job
of pydantic-ai. A provider just bundles:

* The pydantic-ai prefix (``"openai"``, ``"anthropic"``, ...) used to build
  the model identifier string.
* A canonical list of admin-facing default model IDs that pre-populate the
  "register a new model" dropdown in the UI (operators can still type any
  string).
* The Settings dataclass describing what credentials / non-secret kwargs
  the provider needs (api_key, base_url, organization_id, ...).
"""

from __future__ import annotations

from typing import ClassVar, Optional


class BaseLLMProvider:
    """Abstract base class for an LLM provider integration.

    Subclasses live under :mod:`opencontractserver.llms.providers` and are
    auto-discovered by :class:`LLMProviderRegistry`.
    """

    # ---- Class-level metadata (override on subclasses) -----------------

    #: Human-readable label shown in the admin UI.
    title: ClassVar[str] = ""

    #: Longer description (provider purpose, links to docs).
    description: ClassVar[str] = ""

    #: pydantic-ai model-string prefix. Combined with a model_id to form
    #: the string passed to ``PydanticAIAgent(model=...)`` — e.g. an
    #: ``OpenAIProvider`` with prefix ``"openai"`` and a ``RegisteredLLM``
    #: with ``model_id="gpt-4o-mini"`` produces ``"openai:gpt-4o-mini"``.
    pydantic_ai_prefix: ClassVar[str] = ""

    #: Canonical model identifiers admins commonly register under this
    #: provider. Pre-populates the "model_id" dropdown in the admin UI;
    #: operators can still type any string. NOT a closed allow-list.
    default_models: ClassVar[tuple[str, ...]] = ()

    #: Whether this provider's models can produce pydantic-ai structured
    #: output. Stored on RegisteredLLM as a per-row override; this is the
    #: registry-default used when a row has no explicit override.
    supports_structured_output: ClassVar[bool] = True

    #: Whether this provider's models support tool/function calling.
    supports_tools: ClassVar[bool] = True

    #: Subclasses override with their nested ``Settings`` dataclass. The
    #: dataclass's fields use ``metadata={"pipeline_setting": PipelineSetting(...)}``
    #: in the same shape as pipeline components, so the existing
    #: ``settings_schema`` machinery applies unchanged.
    Settings: ClassVar[Optional[type]] = None

    @classmethod
    def class_path(cls) -> str:
        """Full module.ClassName path, used as the registry key + the
        ``provider_class_path`` foreign reference on ``RegisteredLLM``.
        """
        return f"{cls.__module__}.{cls.__name__}"
