"""Base classes for LLM provider definitions.

A provider is a thin declarative wrapper that tells the rest of the system:

* what string prefix to use when building a pydantic-ai model identifier
  (e.g. ``"openai"`` for ``"openai:gpt-4o-mini"``);
* what credentials it needs (api_key, api_base, organization, …);
* how to map those credentials onto kwargs for ``AgentConfig`` /
  ``pydantic-ai`` at invocation time.

Providers are *code-defined*. Models within a provider are *admin-curated*
rows in ``LLMModel``. This split mirrors the pipeline pattern: parsers /
embedders are code-defined, while which one is preferred per MIME type is
admin-configured.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CredentialField:
    """Schema entry describing one credential a provider accepts.

    ``is_secret=True`` marks the field as something that must be encrypted at
    rest and never returned through GraphQL — analogous to
    ``ComponentSettingSchemaType.setting_type == "secret"`` in the pipeline UI.
    """

    name: str
    label: str
    description: str = ""
    is_secret: bool = True
    required: bool = True
    default: str | None = None


@dataclass(frozen=True)
class LLMProviderDefinition:
    """Immutable metadata captured for each registered provider class.

    Mirrors ``PipelineComponentDefinition`` so the GraphQL serialisation and
    the frontend admin UI can treat it the same way.
    """

    key: str  # stable identifier (used in DB rows, GraphQL inputs)
    title: str  # human label
    description: str
    pydantic_ai_prefix: str  # e.g. "openai", "anthropic", "google-gla"
    credential_schema: tuple[CredentialField, ...]
    default_models: tuple[str, ...] = ()  # autocomplete suggestions in UI
    supports_structured_output: bool = True
    supports_tools: bool = True
    provider_class: type | None = field(default=None, compare=False, hash=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "pydantic_ai_prefix": self.pydantic_ai_prefix,
            "credential_schema": [
                {
                    "name": f.name,
                    "label": f.label,
                    "description": f.description,
                    "is_secret": f.is_secret,
                    "required": f.required,
                    "default": f.default,
                }
                for f in self.credential_schema
            ],
            "default_models": list(self.default_models),
            "supports_structured_output": self.supports_structured_output,
            "supports_tools": self.supports_tools,
        }


class BaseLLMProvider(ABC):
    """Concrete provider classes subclass this and set the class attributes.

    Providers are *not* instantiated frequently — instead the registry caches
    a single instance per class for use as a namespace. Heavy state (HTTP
    clients, model objects) should live inside ``build_pydantic_ai_model``,
    not on the instance.
    """

    # ----- Required class attributes (override in subclasses) ---------------

    key: str = ""
    title: str = ""
    description: str = ""
    pydantic_ai_prefix: str = ""
    credential_schema: tuple[CredentialField, ...] = ()
    default_models: tuple[str, ...] = ()
    supports_structured_output: bool = True
    supports_tools: bool = True

    # ----- Hooks -----------------------------------------------------------

    def build_model_string(self, model_name: str) -> str:
        """Compose the ``provider:model`` identifier pydantic-ai expects."""
        if not self.pydantic_ai_prefix:
            return model_name
        return f"{self.pydantic_ai_prefix}:{model_name}"

    def build_environment_overrides(self, credentials: dict) -> dict[str, str | None]:
        """Map provider credentials to env-var overrides for pydantic-ai.

        pydantic-ai resolves API keys from process env vars (``OPENAI_API_KEY``,
        ``ANTHROPIC_API_KEY``, …) at model invocation time. The config service
        applies these inside a context manager that restores the previous
        values on exit, so per-task per-provider credentials don't leak across
        Celery tasks.

        Default behaviour keys off the ``key`` attribute and assumes an
        ``api_key`` credential — providers that need additional env vars or
        non-standard names should override.
        """
        overrides: dict[str, str | None] = {}
        api_key = credentials.get("api_key")
        if api_key is not None:
            overrides[f"{self.key.upper()}_API_KEY"] = api_key
        return overrides

    def healthcheck(self, credentials: dict) -> bool:  # noqa: ARG002 — default no-op
        """Optional connectivity check. Default: trust the credentials.

        Concrete providers can override to ping a /models endpoint. Should
        never raise — return ``False`` on failure.
        """
        return True

    # ----- Definition factory ----------------------------------------------

    @classmethod
    def to_definition(cls) -> LLMProviderDefinition:
        return LLMProviderDefinition(
            key=cls.key,
            title=cls.title,
            description=cls.description,
            pydantic_ai_prefix=cls.pydantic_ai_prefix,
            credential_schema=tuple(cls.credential_schema),
            default_models=tuple(cls.default_models),
            supports_structured_output=cls.supports_structured_output,
            supports_tools=cls.supports_tools,
            provider_class=cls,
        )
