"""GraphQL query mixin for the LLM configuration system.

* ``llmProviders`` — registry-derived list (superusers see configured state).
* ``llmConfigSettings`` — singleton config (superuser only).
* ``llmModels`` — full admin list (superuser only; supports filters).
* ``availableLlmModels`` — column-editor-facing list, scoped by availability;
  callable by any authenticated user.
"""

from __future__ import annotations

import logging
from typing import Optional

import graphene
from graphql_jwt.decorators import login_required, superuser_required

from config.graphql.llm_config_types import (
    LLMConfigSettingsType,
    LLMModelType,
    LLMProviderType,
)
from opencontractserver.llms.config_service import list_available_models
from opencontractserver.llms.models import LLMConfigSettings, LLMModel
from opencontractserver.llms.providers import get_provider_registry

logger = logging.getLogger(__name__)


class LLMConfigQueryMixin:

    # ---- Providers ----------------------------------------------------- #

    llm_providers = graphene.List(
        LLMProviderType,
        description="All providers registered in the LLMProviderRegistry.",
    )

    @login_required
    def resolve_llm_providers(self, info) -> list[LLMProviderType]:
        registry = get_provider_registry()
        settings = LLMConfigSettings.get_instance()
        return [
            LLMProviderType.from_definition(
                d, is_configured=settings.is_provider_configured(d.key)
            )
            for d in registry.providers
        ]

    # ---- Settings singleton -------------------------------------------- #

    llm_config_settings = graphene.Field(
        LLMConfigSettingsType,
        description="Site-wide LLM configuration (superuser only).",
    )

    @superuser_required
    def resolve_llm_config_settings(self, info) -> LLMConfigSettingsType:
        return LLMConfigSettingsType.from_instance(LLMConfigSettings.get_instance())

    # ---- Admin model list ---------------------------------------------- #

    llm_models = graphene.List(
        LLMModelType,
        provider_key=graphene.String(required=False),
        is_enabled=graphene.Boolean(required=False),
        description="Admin-curated LLM model rows (superuser only).",
    )

    @superuser_required
    def resolve_llm_models(
        self,
        info,
        provider_key: Optional[str] = None,
        is_enabled: Optional[bool] = None,
    ) -> list[LLMModel]:
        qs = LLMModel.objects.all()
        if provider_key is not None:
            qs = qs.filter(provider_key=provider_key)
        if is_enabled is not None:
            qs = qs.filter(is_enabled=is_enabled)
        return list(qs)

    # ---- Column-editor facing list ------------------------------------- #

    available_llm_models = graphene.List(
        LLMModelType,
        description=(
            "Models that are enabled and whose provider is currently configured. "
            "Used to populate the column-editor model picker."
        ),
    )

    @login_required
    def resolve_available_llm_models(self, info) -> list[LLMModel]:
        return list_available_models()
