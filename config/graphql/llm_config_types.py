"""GraphQL types for the LLM configuration system.

Mirrors the shape of ``config.graphql.pipeline_types`` so admin UIs can
reuse the same conventions.
"""

from __future__ import annotations

from typing import Any

import graphene
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType

from opencontractserver.llms.models import LLMConfigSettings, LLMModel
from opencontractserver.llms.providers import (
    LLMProviderDefinition,
    get_provider_registry,
)


# --------------------------------------------------------------------------- #
# Provider (registry-derived, read-only)
# --------------------------------------------------------------------------- #


class LLMCredentialFieldType(graphene.ObjectType):
    """Schema entry describing one credential the provider expects."""

    name = graphene.String()
    label = graphene.String()
    description = graphene.String()
    is_secret = graphene.Boolean()
    required = graphene.Boolean()
    default = graphene.String(required=False)


class LLMProviderType(graphene.ObjectType):
    """A provider class registered in code (OpenAI, Anthropic, …).

    Read-only — providers are not stored in the DB; they're discovered at
    boot. The ``is_configured`` flag reflects whether an admin has supplied
    credentials for this provider.
    """

    key = graphene.String()
    title = graphene.String()
    description = graphene.String()
    pydantic_ai_prefix = graphene.String()
    credential_schema = graphene.List(LLMCredentialFieldType)
    default_models = graphene.List(graphene.String)
    supports_structured_output = graphene.Boolean()
    supports_tools = graphene.Boolean()
    is_configured = graphene.Boolean()

    @classmethod
    def from_definition(
        cls, definition: LLMProviderDefinition, *, is_configured: bool
    ) -> "LLMProviderType":
        return cls(
            key=definition.key,
            title=definition.title,
            description=definition.description,
            pydantic_ai_prefix=definition.pydantic_ai_prefix,
            credential_schema=[
                LLMCredentialFieldType(
                    name=f.name,
                    label=f.label,
                    description=f.description,
                    is_secret=f.is_secret,
                    required=f.required,
                    default=f.default,
                )
                for f in definition.credential_schema
            ],
            default_models=list(definition.default_models),
            supports_structured_output=definition.supports_structured_output,
            supports_tools=definition.supports_tools,
            is_configured=is_configured,
        )


# --------------------------------------------------------------------------- #
# LLMModel (DB rows)
# --------------------------------------------------------------------------- #


class LLMModelType(DjangoObjectType):
    """One admin-curated model row.

    Adds two computed fields on top of the bare DjangoObjectType:

    * ``provider``: resolved registry entry (or null if the provider's code
      was removed in a later release);
    * ``is_available``: combined ``is_enabled`` + ``provider_configured`` —
      used by the column-editor frontend to grey out unusable choices.
    """

    provider = graphene.Field(LLMProviderType)
    pydantic_ai_string = graphene.String()
    is_available = graphene.Boolean()

    class Meta:
        model = LLMModel
        fields = (
            "id",
            "provider_key",
            "model_name",
            "display_name",
            "description",
            "is_enabled",
            "supports_vision",
            "supports_tools",
            "supports_structured_output",
            "max_context_tokens",
            "default_temperature",
            "extra_settings",
            "created",
            "modified",
        )

    @staticmethod
    def resolve_provider(parent: LLMModel, info: Any) -> LLMProviderType | None:
        defn = parent.provider_definition
        if defn is None:
            return None
        settings = LLMConfigSettings.get_instance()
        return LLMProviderType.from_definition(
            defn, is_configured=settings.is_provider_configured(parent.provider_key)
        )

    @staticmethod
    def resolve_pydantic_ai_string(parent: LLMModel, info: Any) -> str:
        return parent.pydantic_ai_string()

    @staticmethod
    def resolve_is_available(parent: LLMModel, info: Any) -> bool:
        return parent.is_available()


# --------------------------------------------------------------------------- #
# Settings singleton (no secrets in payload)
# --------------------------------------------------------------------------- #


class LLMProviderConfigEntryType(graphene.ObjectType):
    """A provider's *non-secret* configuration as currently stored.

    Secret values (api_key, …) are NEVER returned — only ``is_configured``
    + the non-secret fields. Mirrors how PipelineSettings exposes secrets.
    """

    provider_key = graphene.String()
    is_configured = graphene.Boolean()
    config = GenericScalar()  # non-secret only
    secret_fields_set = graphene.List(graphene.String)


class LLMConfigSettingsType(graphene.ObjectType):
    default_model = graphene.Field(LLMModelType)
    provider_configs = graphene.List(LLMProviderConfigEntryType)
    modified = graphene.DateTime()
    modified_by_id = graphene.Int(required=False)

    @classmethod
    def from_instance(cls, instance: LLMConfigSettings) -> "LLMConfigSettingsType":
        registry = get_provider_registry()
        secrets = instance.get_secrets()
        entries: list[LLMProviderConfigEntryType] = []
        for definition in registry.providers:
            non_secret_config = instance.get_provider_config(definition.key)
            secret_fields = [
                k for k in secrets.get(definition.key, {}) if secrets[definition.key][k]
            ]
            entries.append(
                LLMProviderConfigEntryType(
                    provider_key=definition.key,
                    is_configured=instance.is_provider_configured(definition.key),
                    config=non_secret_config,
                    secret_fields_set=secret_fields,
                )
            )

        return cls(
            default_model=instance.default_model,
            provider_configs=entries,
            modified=instance.modified,
            modified_by_id=instance.modified_by_id,
        )
