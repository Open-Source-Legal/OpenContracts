"""GraphQL query mixin for the LLM configuration system.

Mirrors :class:`PipelineQueryMixin`:

* ``llmProviders`` — list of code-side provider classes (admin-facing).
  Returns full settings_schema (with secret slots flagged) only for
  superusers; non-superusers see provider metadata without schema /
  has-secrets info.
* ``registeredLlms`` — admin-curated rows. Defaults to "selectable"
  (head AND enabled AND not archived) for the column-picker contract;
  superusers can opt-in to the full lineage / archived set.
* ``llmSettings`` — singleton. Superusers get the full payload;
  non-superusers see only the resolved default model identifier (used
  by the UI to label "Default LLM: gpt-4o-mini" without exposing
  configuration details).
"""

from __future__ import annotations

import logging
from typing import Optional

import graphene
from graphql_jwt.decorators import login_required

from config.graphql.llm_types import (
    LLMProviderType,
    LLMSettingSchemaType,
    LLMSettingsType,
    RegisteredLLMType,
)
from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM
from opencontractserver.llms.providers.base import BaseLLMProvider
from opencontractserver.llms.providers.registry import get_provider_registry
from opencontractserver.pipeline.base.settings_schema import get_settings_schema

logger = logging.getLogger(__name__)


def _build_provider_type(
    provider_cls: type[BaseLLMProvider],
    *,
    settings_instance: LLMSettings,
    include_schema: bool,
) -> LLMProviderType:
    """Build an :class:`LLMProviderType` for ``provider_cls``.

    ``include_schema`` is False for non-superusers — they see only the
    provider's public metadata, not the api_key field's presence.
    """
    class_path = provider_cls.class_path()

    settings_schema_payload: Optional[list[LLMSettingSchemaType]] = None
    if include_schema:
        raw_schema = get_settings_schema(provider_cls)
        merged = settings_instance.get_full_provider_settings(class_path)
        settings_schema_payload = []
        for name, info in raw_schema.items():
            value = merged.get(name)
            if info.get("type") == "secret":
                # Never expose secret values.
                has_value = (
                    bool(value) and isinstance(value, str) and bool(value.strip())
                )
                current_value = None
            else:
                has_value = value is not None and value != ""
                current_value = value
            settings_schema_payload.append(
                LLMSettingSchemaType(
                    name=name,
                    setting_type=info.get("type", "optional"),
                    python_type=info.get("python_type"),
                    required=info.get("required", False),
                    description=info.get("description", ""),
                    default=info.get("default"),
                    env_var=info.get("env_var"),
                    has_value=has_value,
                    current_value=current_value,
                )
            )

    bucket = (
        settings_instance.get_component_secrets(class_path) if include_schema else {}
    )
    has_secrets = include_schema and bool(bucket)
    has_valid_secrets = include_schema and settings_instance.has_valid_secrets(
        class_path
    )

    return LLMProviderType(
        name=provider_cls.__name__,
        class_path=class_path,
        title=provider_cls.title,
        description=provider_cls.description,
        pydantic_ai_prefix=provider_cls.pydantic_ai_prefix,
        default_models=list(provider_cls.default_models),
        supports_structured_output=provider_cls.supports_structured_output,
        supports_tools=provider_cls.supports_tools,
        settings_schema=settings_schema_payload,
        has_secrets=has_secrets,
        has_valid_secrets=has_valid_secrets,
    )


def _build_registered_llm_type(
    rl: RegisteredLLM,
    *,
    settings_instance: LLMSettings,
    include_schema: bool,
) -> RegisteredLLMType:
    """Build a :class:`RegisteredLLMType` for ``rl``.

    Honors single-source-of-truth: ``is_resolvable`` and
    ``unavailable_reason`` come from the model methods (which delegate
    to the resolver), not duplicated logic here.
    """
    provider_cls = get_provider_registry().get(rl.provider_class_path)
    provider_type = (
        _build_provider_type(
            provider_cls,
            settings_instance=settings_instance,
            include_schema=include_schema,
        )
        if provider_cls is not None
        else None
    )
    pydantic_ai_model_string = (
        f"{provider_cls.pydantic_ai_prefix}:{rl.model_id}"
        if provider_cls is not None
        else None
    )
    is_default = (
        settings_instance.default_extract_llm_id == rl.pk
        if settings_instance.default_extract_llm_id is not None
        else False
    )
    return RegisteredLLMType(
        id=rl.pk,
        provider_class_path=rl.provider_class_path,
        provider=provider_type,
        model_id=rl.model_id,
        display_name=rl.display_name,
        pydantic_ai_model_string=pydantic_ai_model_string,
        is_enabled=rl.is_enabled,
        is_archived=rl.is_archived,
        is_head=rl.is_head(),
        is_resolvable=rl.is_resolvable(llm_settings=settings_instance),
        unavailable_reason=rl.unavailable_reason(llm_settings=settings_instance),
        is_default_for_extracts=is_default,
        context_window=rl.context_window,
        supports_structured_output=rl.supports_structured_output,
        supports_tools=rl.supports_tools,
        max_output_tokens=rl.max_output_tokens,
        temperature_default=rl.temperature_default,
        notes=rl.notes,
        previous_version_id=rl.previous_version_id,
        created=rl.created,
        modified=rl.modified,
        creator=rl.creator,
    )


class LLMQueryMixin:
    """Query fields for the LLM configuration system."""

    # -------------------------------------------------------------- #
    # llmProviders
    # -------------------------------------------------------------- #
    llm_providers = graphene.List(
        LLMProviderType,
        description=(
            "All LLM provider classes registered in this deployment. "
            "Settings schema and has-secrets flags are exposed only to "
            "superusers; non-superusers see public metadata only."
        ),
    )

    @login_required
    def resolve_llm_providers(
        self, info: graphene.ResolveInfo
    ) -> list[LLMProviderType]:
        user = info.context.user
        registry = get_provider_registry()
        settings_instance = LLMSettings.get_instance()
        return [
            _build_provider_type(
                cls,
                settings_instance=settings_instance,
                include_schema=user.is_superuser,
            )
            for cls in registry.all()
        ]

    # -------------------------------------------------------------- #
    # registeredLlms
    # -------------------------------------------------------------- #
    registered_llms = graphene.List(
        RegisteredLLMType,
        only_selectable=graphene.Boolean(
            default_value=True,
            description=(
                "When True (default), return only rows that are selectable "
                "in the column picker (head AND enabled AND not archived). "
                "Set to False (superuser-only) to walk the full lineage / "
                "archived set."
            ),
        ),
        description=(
            "Admin-curated LLM rows. Non-superusers always see only "
            "selectable rows regardless of the only_selectable flag."
        ),
    )

    @login_required
    def resolve_registered_llms(
        self,
        info: graphene.ResolveInfo,
        only_selectable: bool = True,
    ) -> list[RegisteredLLMType]:
        user = info.context.user
        settings_instance = LLMSettings.get_instance()

        # Non-superusers can never see archived / disabled / non-head
        # rows, regardless of the flag.
        if not user.is_superuser:
            only_selectable = True

        if only_selectable:
            qs = RegisteredLLM.objects.selectable()
        else:
            qs = RegisteredLLM.objects.all()

        rows = list(qs.select_related("creator", "previous_version").order_by("pk"))
        return [
            _build_registered_llm_type(
                rl,
                settings_instance=settings_instance,
                include_schema=user.is_superuser,
            )
            for rl in rows
        ]

    # -------------------------------------------------------------- #
    # llmSettings
    # -------------------------------------------------------------- #
    llm_settings = graphene.Field(
        LLMSettingsType,
        description=(
            "The singleton LLM settings row. Non-superusers see only the "
            "resolved default model identifier; superusers see the full "
            "payload (provider_settings, providers_with_secrets, "
            "audit fields)."
        ),
    )

    @login_required
    def resolve_llm_settings(self, info: graphene.ResolveInfo) -> LLMSettingsType:
        user = info.context.user
        settings_instance = LLMSettings.get_instance()

        default_rl_payload: Optional[RegisteredLLMType] = None
        if settings_instance.default_extract_llm_id is not None:
            try:
                default_rl_payload = _build_registered_llm_type(
                    settings_instance.default_extract_llm,
                    settings_instance=settings_instance,
                    include_schema=user.is_superuser,
                )
            except Exception:
                logger.exception(
                    "Failed to materialise default_extract_llm for GraphQL"
                )

        if not user.is_superuser:
            # Public surface: just the default RegisteredLLM (no
            # provider_settings, no providers_with_secrets, no audit).
            return LLMSettingsType(
                provider_settings=None,
                default_extract_llm=default_rl_payload,
                providers_with_secrets=[],
                modified=None,
                modified_by=None,
            )

        return LLMSettingsType(
            provider_settings=settings_instance.provider_settings or {},
            default_extract_llm=default_rl_payload,
            providers_with_secrets=list(settings_instance.get_secrets().keys()),
            modified=settings_instance.modified,
            modified_by=settings_instance.modified_by,
        )
