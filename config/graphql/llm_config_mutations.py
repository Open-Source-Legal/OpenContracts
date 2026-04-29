"""GraphQL mutations for the LLM configuration system.

All write mutations are superuser-only and rate-limited (30 req/min) — same
posture as ``pipeline_settings_mutations``. Secrets are written via
``LLMConfigSettings.update_provider_secrets`` (Fernet-encrypted at rest) and
NEVER returned in any response payload.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import graphene
from django.db import transaction
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required

from config.graphql.llm_config_types import LLMConfigSettingsType, LLMModelType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.llms.models import LLMConfigSettings, LLMModel
from opencontractserver.llms.providers import get_provider_registry

logger = logging.getLogger(__name__)


# Validation -------------------------------------------------------------- #

PROVIDER_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")
MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._:\-/]+$")
MAX_DISPLAY_NAME = 255
MAX_DESCRIPTION = 4096
MAX_EXTRA_SETTINGS_BYTES = 4096


def _validate_provider_key(key: str) -> Optional[str]:
    if not key:
        return "Provider key cannot be empty"
    if len(key) > 64:
        return "Provider key exceeds maximum length of 64"
    if not PROVIDER_KEY_PATTERN.match(key):
        return f"Provider key '{key}' must be lowercase alphanumeric / dash / underscore"
    if get_provider_registry().get(key) is None:
        return f"Provider '{key}' is not registered"
    return None


def _validate_model_name(model_name: str) -> Optional[str]:
    if not model_name:
        return "Model name cannot be empty"
    if len(model_name) > 255:
        return "Model name exceeds maximum length of 255"
    if not MODEL_NAME_PATTERN.match(model_name):
        return f"Model name '{model_name}' contains disallowed characters"
    return None


def _superuser_or_error(user, mutation_cls):
    if not user.is_authenticated or not user.is_superuser:
        return mutation_cls(
            ok=False,
            message="Only superusers can modify LLM configuration.",
        )
    return None


# --------------------------------------------------------------------------- #
# Provider credentials
# --------------------------------------------------------------------------- #


class UpdateLLMProviderCredentialsMutation(graphene.Mutation):
    """Encrypt and store credentials (api_key, base_url, …) for a provider.

    The mutation accepts a flat ``credentials`` dict; each key is matched
    against the provider's ``credential_schema``. ``is_secret=True`` fields go
    into the encrypted blob; non-secret fields go into ``provider_configs``.
    Unknown keys are rejected to avoid silently storing garbage.
    """

    class Arguments:
        provider_key = graphene.String(required=True)
        credentials = GenericScalar(
            required=True,
            description=(
                "Flat dict of credential field name -> value. Schema is the "
                "provider's credential_schema."
            ),
        )

    ok = graphene.Boolean()
    message = graphene.String()
    settings = graphene.Field(LLMConfigSettingsType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, provider_key, credentials):
        denied = _superuser_or_error(info.context.user, UpdateLLMProviderCredentialsMutation)
        if denied is not None:
            return denied

        error = _validate_provider_key(provider_key)
        if error:
            return UpdateLLMProviderCredentialsMutation(ok=False, message=error)

        if not isinstance(credentials, dict):
            return UpdateLLMProviderCredentialsMutation(
                ok=False, message="credentials must be a dictionary"
            )

        defn = get_provider_registry().get(provider_key)
        valid_field_names = {f.name for f in defn.credential_schema}
        unknown = set(credentials) - valid_field_names
        if unknown:
            return UpdateLLMProviderCredentialsMutation(
                ok=False,
                message=(
                    f"Unknown credential fields for provider '{provider_key}': "
                    + ", ".join(sorted(unknown))
                ),
            )

        # Reject obviously-invalid value types early — keep encryption layer
        # focused on serialisation, not validation.
        for k, v in credentials.items():
            if v is not None and not isinstance(v, (str, int, float, bool)):
                return UpdateLLMProviderCredentialsMutation(
                    ok=False,
                    message=f"Credential '{k}' must be a primitive type (string/number/boolean/null)",
                )

        with transaction.atomic():
            instance = LLMConfigSettings.get_instance(use_cache=False)

            secret_values: dict = {}
            non_secret_values: dict = {}
            for field in defn.credential_schema:
                if field.name not in credentials:
                    continue
                value = credentials[field.name]
                if field.is_secret:
                    secret_values[field.name] = value
                else:
                    non_secret_values[field.name] = value

            if non_secret_values:
                instance.update_provider_config(provider_key, non_secret_values)

            if secret_values:
                # Empty string clears a secret rather than storing literal "".
                cleansed = {k: v for k, v in secret_values.items() if v not in ("", None)}
                cleared = [k for k, v in secret_values.items() if v in ("", None)]
                if cleansed:
                    try:
                        instance.update_provider_secrets(provider_key, cleansed)
                    except ValueError as exc:
                        return UpdateLLMProviderCredentialsMutation(
                            ok=False, message=str(exc)
                        )
                if cleared:
                    existing = instance.get_provider_secrets(provider_key)
                    for k in cleared:
                        existing.pop(k, None)
                    secrets = instance.get_secrets()
                    secrets[provider_key] = existing
                    instance.set_secrets(secrets)

            instance.modified_by = info.context.user
            instance.save()

        return UpdateLLMProviderCredentialsMutation(
            ok=True,
            message=f"Credentials for '{provider_key}' updated.",
            settings=LLMConfigSettingsType.from_instance(
                LLMConfigSettings.get_instance(use_cache=False)
            ),
        )


class DeleteLLMProviderCredentialsMutation(graphene.Mutation):
    class Arguments:
        provider_key = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    settings = graphene.Field(LLMConfigSettingsType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, provider_key):
        denied = _superuser_or_error(info.context.user, DeleteLLMProviderCredentialsMutation)
        if denied is not None:
            return denied

        error = _validate_provider_key(provider_key)
        if error:
            return DeleteLLMProviderCredentialsMutation(ok=False, message=error)

        with transaction.atomic():
            instance = LLMConfigSettings.get_instance(use_cache=False)
            instance.delete_provider_secrets(provider_key)
            instance.delete_provider_config(provider_key)
            instance.modified_by = info.context.user
            instance.save()

        return DeleteLLMProviderCredentialsMutation(
            ok=True,
            message=f"Credentials for '{provider_key}' removed.",
            settings=LLMConfigSettingsType.from_instance(
                LLMConfigSettings.get_instance(use_cache=False)
            ),
        )


# --------------------------------------------------------------------------- #
# LLM model CRUD
# --------------------------------------------------------------------------- #


def _validate_model_payload(
    *, provider_key: str, model_name: str, display_name: str,
    description: str, extra_settings: Optional[dict],
) -> Optional[str]:
    error = _validate_provider_key(provider_key) or _validate_model_name(model_name)
    if error:
        return error
    if not display_name or len(display_name) > MAX_DISPLAY_NAME:
        return f"display_name must be 1..{MAX_DISPLAY_NAME} characters"
    if description and len(description) > MAX_DESCRIPTION:
        return f"description exceeds maximum length of {MAX_DESCRIPTION}"
    if extra_settings is not None:
        if not isinstance(extra_settings, dict):
            return "extra_settings must be a dictionary"
        if len(json.dumps(extra_settings).encode()) > MAX_EXTRA_SETTINGS_BYTES:
            return (
                f"extra_settings exceeds maximum size of {MAX_EXTRA_SETTINGS_BYTES} bytes"
            )
    return None


class CreateLLMModelMutation(graphene.Mutation):
    class Arguments:
        provider_key = graphene.String(required=True)
        model_name = graphene.String(required=True)
        display_name = graphene.String(required=True)
        description = graphene.String(required=False)
        is_enabled = graphene.Boolean(required=False)
        supports_vision = graphene.Boolean(required=False)
        supports_tools = graphene.Boolean(required=False)
        supports_structured_output = graphene.Boolean(required=False)
        max_context_tokens = graphene.Int(required=False)
        default_temperature = graphene.Float(required=False)
        extra_settings = GenericScalar(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    llm_model = graphene.Field(LLMModelType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root, info, provider_key, model_name, display_name,
        description=None, is_enabled=None, supports_vision=None,
        supports_tools=None, supports_structured_output=None,
        max_context_tokens=None, default_temperature=None, extra_settings=None,
    ):
        denied = _superuser_or_error(info.context.user, CreateLLMModelMutation)
        if denied is not None:
            return denied

        error = _validate_model_payload(
            provider_key=provider_key,
            model_name=model_name,
            display_name=display_name,
            description=description or "",
            extra_settings=extra_settings,
        )
        if error:
            return CreateLLMModelMutation(ok=False, message=error)

        if LLMModel.objects.filter(
            provider_key=provider_key, model_name=model_name
        ).exists():
            return CreateLLMModelMutation(
                ok=False,
                message=(
                    f"Model '{model_name}' is already registered under provider "
                    f"'{provider_key}'."
                ),
            )

        kwargs = {
            "provider_key": provider_key,
            "model_name": model_name,
            "display_name": display_name,
            "description": description or "",
            "created_by": info.context.user,
        }
        for field, value in (
            ("is_enabled", is_enabled),
            ("supports_vision", supports_vision),
            ("supports_tools", supports_tools),
            ("supports_structured_output", supports_structured_output),
            ("max_context_tokens", max_context_tokens),
            ("default_temperature", default_temperature),
            ("extra_settings", extra_settings),
        ):
            if value is not None:
                kwargs[field] = value

        try:
            model = LLMModel.objects.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return CreateLLMModelMutation(ok=False, message=str(exc))

        return CreateLLMModelMutation(ok=True, message="LLM model created", llm_model=model)


class UpdateLLMModelMutation(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)
        display_name = graphene.String(required=False)
        description = graphene.String(required=False)
        is_enabled = graphene.Boolean(required=False)
        supports_vision = graphene.Boolean(required=False)
        supports_tools = graphene.Boolean(required=False)
        supports_structured_output = graphene.Boolean(required=False)
        max_context_tokens = graphene.Int(required=False)
        default_temperature = graphene.Float(required=False)
        extra_settings = GenericScalar(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    llm_model = graphene.Field(LLMModelType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id, **fields):
        denied = _superuser_or_error(info.context.user, UpdateLLMModelMutation)
        if denied is not None:
            return denied

        try:
            model = LLMModel.objects.get(pk=id)
        except LLMModel.DoesNotExist:
            return UpdateLLMModelMutation(ok=False, message="LLM model not found")

        # Re-validate display name / description / extra_settings when present.
        error = _validate_model_payload(
            provider_key=model.provider_key,
            model_name=model.model_name,
            display_name=fields.get("display_name", model.display_name),
            description=fields.get("description", model.description) or "",
            extra_settings=fields.get("extra_settings"),
        )
        if error:
            return UpdateLLMModelMutation(ok=False, message=error)

        for field, value in fields.items():
            if value is None:
                continue
            setattr(model, field, value)

        try:
            model.save()
        except Exception as exc:  # noqa: BLE001
            return UpdateLLMModelMutation(ok=False, message=str(exc))

        return UpdateLLMModelMutation(ok=True, message="LLM model updated", llm_model=model)


class DeleteLLMModelMutation(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id):
        denied = _superuser_or_error(info.context.user, DeleteLLMModelMutation)
        if denied is not None:
            return denied

        deleted, _ = LLMModel.objects.filter(pk=id).delete()
        if deleted == 0:
            return DeleteLLMModelMutation(ok=False, message="LLM model not found")
        # SET_NULL fallout on Column.preferred_llm_model is intentional.
        return DeleteLLMModelMutation(ok=True, message="LLM model deleted")


class SetDefaultLLMModelMutation(graphene.Mutation):
    """Set or clear the system-wide default LLM model.

    Pass ``id=None`` (or omit) to clear. The default is used whenever a
    Column has no ``preferred_llm_model`` set.
    """

    class Arguments:
        id = graphene.ID(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    settings = graphene.Field(LLMConfigSettingsType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id=None):
        denied = _superuser_or_error(info.context.user, SetDefaultLLMModelMutation)
        if denied is not None:
            return denied

        instance = LLMConfigSettings.get_instance(use_cache=False)
        if id is None:
            instance.default_model = None
        else:
            try:
                instance.default_model = LLMModel.objects.get(pk=id)
            except LLMModel.DoesNotExist:
                return SetDefaultLLMModelMutation(ok=False, message="LLM model not found")
        instance.modified_by = info.context.user
        instance.save()

        return SetDefaultLLMModelMutation(
            ok=True,
            message="Default LLM model updated.",
            settings=LLMConfigSettingsType.from_instance(
                LLMConfigSettings.get_instance(use_cache=False)
            ),
        )
