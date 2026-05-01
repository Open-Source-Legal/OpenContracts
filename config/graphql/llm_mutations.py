"""GraphQL mutations for the LLM configuration system.

Superuser-only mutations to register / update / archive
:class:`RegisteredLLM` rows and to manage encrypted provider secrets in
:class:`LLMSettings`. Mirrors the rate-limit + validation patterns from
``pipeline_settings_mutations.py``:

* ``RateLimits.WRITE_LIGHT`` (30 req/min) — these are infrequent admin
  operations.
* Single error message regardless of "object doesn't exist" vs.
  "permission denied" so non-superusers can't enumerate via timing.

Immutable lineage contract:

* ``RegisterLLM`` creates a new lineage root (``previous_version=None``).
* ``UpdateRegisteredLLM`` creates a new row with ``previous_version``
  pointing at the prior one and copies forward any unchanged fields.
* ``ArchiveRegisteredLLM`` is a special case of update that creates a
  new row with ``is_archived=True``. Once archived, a lineage cannot be
  un-archived through any mutation (the archived row is permanently
  hidden from pickers; resurrect by registering a new lineage if
  needed).
* No delete mutation. Ever. ``Column.preferred_llm`` and
  ``Datacell.executed_llm`` (Phase 4) use ``on_delete=PROTECT`` against
  this guarantee.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import graphene
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required

from config.graphql.llm_types import LLMSettingsType, RegisteredLLMType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.llm_configs.models import LLMSettings, RegisteredLLM
from opencontractserver.llms.providers.registry import get_provider_registry

logger = logging.getLogger(__name__)

# Validation constants — same caps as pipeline_settings_mutations.py for
# operator-facing consistency.
MAX_CLASS_PATH_LENGTH = 256
MAX_MODEL_ID_LENGTH = 128
MAX_DISPLAY_NAME_LENGTH = 256
MAX_NOTES_LENGTH = 4096
MAX_JSON_FIELD_SIZE_BYTES = 10240
VALID_CLASS_PATH_PATTERN = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+$"
)


def _validate_provider_class_path(path: str) -> Optional[str]:
    if not path:
        return "provider_class_path cannot be empty"
    if len(path) > MAX_CLASS_PATH_LENGTH:
        return f"provider_class_path exceeds maximum length of {MAX_CLASS_PATH_LENGTH}"
    if not VALID_CLASS_PATH_PATTERN.match(path):
        return f"Invalid provider_class_path format: {path!r}"
    if get_provider_registry().get(path) is None:
        return f"Provider class {path!r} is not registered in this deployment"
    return None


def _validate_model_id(model_id: str) -> Optional[str]:
    if not model_id or not model_id.strip():
        return "model_id cannot be empty"
    if len(model_id) > MAX_MODEL_ID_LENGTH:
        return f"model_id exceeds maximum length of {MAX_MODEL_ID_LENGTH}"
    return None


def _validate_display_name(display_name: str) -> Optional[str]:
    if not display_name or not display_name.strip():
        return "display_name cannot be empty"
    if len(display_name) > MAX_DISPLAY_NAME_LENGTH:
        return f"display_name exceeds maximum length of {MAX_DISPLAY_NAME_LENGTH}"
    return None


def _validate_secrets_input(secrets: dict) -> Optional[str]:
    """Validate a secrets dict. Mirrors the pipeline-settings checker."""
    import json

    if not isinstance(secrets, dict):
        return "secrets must be a dictionary"
    for key, value in secrets.items():
        if not isinstance(key, str):
            return f"Secret key must be a string, got {type(key).__name__}"
        if len(key) > 256:
            return f"Secret key {key[:50]!r}... exceeds maximum length of 256"
        if not isinstance(value, (str, int, float, bool, type(None))):
            return (
                f"Secret value for {key!r} must be a primitive type "
                "(string, number, boolean, null)"
            )
    max_size = LLMSettings._get_max_secret_size()
    payload_size = len(json.dumps(secrets).encode("utf-8"))
    if payload_size > max_size:
        return (
            f"Secrets payload ({payload_size} bytes) exceeds maximum size "
            f"of {max_size} bytes"
        )
    return None


def _build_registered_llm_payload(
    rl: RegisteredLLM,
    settings_instance: LLMSettings,
) -> RegisteredLLMType:
    """Shared between every mutation that returns a RegisteredLLMType.

    Defers to the queries-side helper for shape consistency.
    """
    # Local import to avoid a circular module load at decoration time.
    from config.graphql.llm_queries import _build_registered_llm_type

    return _build_registered_llm_type(
        rl, settings_instance=settings_instance, include_schema=True
    )


def _superuser_only(user) -> Optional[str]:
    """Return an error message if ``user`` is not a superuser, else None."""
    if not user or not user.is_authenticated or not user.is_superuser:
        return "Only superusers can perform this operation."
    return None


# ---------------------------------------------------------------------------
# RegisterLLMMutation
# ---------------------------------------------------------------------------


class RegisterLLMMutation(graphene.Mutation):
    """Create a new lineage root.

    Use this for *new* (provider, model) combinations. To edit an
    existing row, use :class:`UpdateRegisteredLLMMutation` (creates a
    new lineage version instead of mutating).
    """

    class Arguments:
        provider_class_path = graphene.String(required=True)
        model_id = graphene.String(required=True)
        display_name = graphene.String(required=True)
        is_enabled = graphene.Boolean(default_value=True)
        context_window = graphene.Int(required=False)
        supports_structured_output = graphene.Boolean(
            required=False, default_value=True
        )
        supports_tools = graphene.Boolean(required=False, default_value=True)
        max_output_tokens = graphene.Int(required=False)
        temperature_default = graphene.Float(required=False)
        notes = graphene.String(required=False, default_value="")

    ok = graphene.Boolean()
    message = graphene.String()
    registered_llm = graphene.Field(RegisteredLLMType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        provider_class_path: str,
        model_id: str,
        display_name: str,
        is_enabled: bool = True,
        context_window: Optional[int] = None,
        supports_structured_output: bool = True,
        supports_tools: bool = True,
        max_output_tokens: Optional[int] = None,
        temperature_default: Optional[float] = None,
        notes: str = "",
    ) -> "RegisterLLMMutation":
        denied = _superuser_only(info.context.user)
        if denied:
            return RegisterLLMMutation(ok=False, message=denied, registered_llm=None)

        for err in (
            _validate_provider_class_path(provider_class_path),
            _validate_model_id(model_id),
            _validate_display_name(display_name),
        ):
            if err:
                return RegisterLLMMutation(ok=False, message=err, registered_llm=None)
        if notes and len(notes) > MAX_NOTES_LENGTH:
            return RegisterLLMMutation(
                ok=False,
                message=f"notes exceeds maximum length of {MAX_NOTES_LENGTH}",
                registered_llm=None,
            )

        try:
            rl = RegisteredLLM.objects.create(
                provider_class_path=provider_class_path,
                model_id=model_id.strip(),
                display_name=display_name.strip(),
                is_enabled=is_enabled,
                is_archived=False,
                context_window=context_window,
                supports_structured_output=supports_structured_output,
                supports_tools=supports_tools,
                max_output_tokens=max_output_tokens,
                temperature_default=temperature_default,
                notes=notes or "",
                creator=info.context.user,
            )
        except Exception:
            logger.exception("Unexpected error creating RegisteredLLM")
            return RegisterLLMMutation(
                ok=False,
                message="Unexpected error creating RegisteredLLM.",
                registered_llm=None,
            )

        settings_instance = LLMSettings.get_instance(use_cache=False)
        logger.info(
            "RegisteredLLM #%d created by %s (%s:%s)",
            rl.pk,
            info.context.user.username,
            provider_class_path,
            model_id,
        )
        return RegisterLLMMutation(
            ok=True,
            message=f"RegisteredLLM #{rl.pk} created.",
            registered_llm=_build_registered_llm_payload(rl, settings_instance),
        )


# ---------------------------------------------------------------------------
# UpdateRegisteredLLMMutation
# ---------------------------------------------------------------------------


class UpdateRegisteredLLMMutation(graphene.Mutation):
    """Create a new lineage version with the supplied changes.

    Old row is preserved verbatim; the new row's ``previous_version``
    points at it. Only fields with non-null arguments are changed; all
    other fields are copied forward.
    """

    class Arguments:
        id = graphene.ID(
            required=True,
            description=(
                "ID of the row to supersede. Must be a head (no newer version "
                "already supersedes it)."
            ),
        )
        display_name = graphene.String(required=False)
        is_enabled = graphene.Boolean(required=False)
        context_window = graphene.Int(required=False)
        supports_structured_output = graphene.Boolean(required=False)
        supports_tools = graphene.Boolean(required=False)
        max_output_tokens = graphene.Int(required=False)
        temperature_default = graphene.Float(required=False)
        notes = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    registered_llm = graphene.Field(RegisteredLLMType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        id: str,
        **changes: Any,
    ) -> "UpdateRegisteredLLMMutation":
        denied = _superuser_only(info.context.user)
        if denied:
            return UpdateRegisteredLLMMutation(
                ok=False, message=denied, registered_llm=None
            )

        try:
            prior = RegisteredLLM.objects.get(pk=id)
        except (RegisteredLLM.DoesNotExist, ValueError, TypeError):
            return UpdateRegisteredLLMMutation(
                ok=False,
                message="RegisteredLLM not found.",
                registered_llm=None,
            )

        if not prior.is_head():
            return UpdateRegisteredLLMMutation(
                ok=False,
                message=(
                    "RegisteredLLM is not the head of its lineage; another "
                    "version already supersedes it. Update the head version "
                    "instead."
                ),
                registered_llm=None,
            )
        if prior.is_archived:
            return UpdateRegisteredLLMMutation(
                ok=False,
                message=(
                    "RegisteredLLM is archived. Register a new lineage " "instead."
                ),
                registered_llm=None,
            )

        if "display_name" in changes and changes["display_name"] is not None:
            err = _validate_display_name(changes["display_name"])
            if err:
                return UpdateRegisteredLLMMutation(
                    ok=False, message=err, registered_llm=None
                )
        if (
            "notes" in changes
            and changes["notes"] is not None
            and len(changes["notes"]) > MAX_NOTES_LENGTH
        ):
            return UpdateRegisteredLLMMutation(
                ok=False,
                message=f"notes exceeds maximum length of {MAX_NOTES_LENGTH}",
                registered_llm=None,
            )

        # Copy forward every field, then overlay the supplied changes.
        merged: dict[str, Any] = {
            "provider_class_path": prior.provider_class_path,
            "model_id": prior.model_id,
            "display_name": prior.display_name,
            "is_enabled": prior.is_enabled,
            "is_archived": prior.is_archived,
            "context_window": prior.context_window,
            "supports_structured_output": prior.supports_structured_output,
            "supports_tools": prior.supports_tools,
            "max_output_tokens": prior.max_output_tokens,
            "temperature_default": prior.temperature_default,
            "notes": prior.notes,
        }
        for k, v in changes.items():
            if v is not None and k in merged:
                merged[k] = v

        new_row = RegisteredLLM.objects.create(
            previous_version=prior,
            creator=info.context.user,
            **merged,
        )

        # If the prior row was the default, point the singleton at the
        # new version so resolution keeps working without operator action.
        settings_instance = LLMSettings.get_instance(use_cache=False)
        if settings_instance.default_extract_llm_id == prior.pk:
            settings_instance.default_extract_llm = new_row
            settings_instance.modified_by = info.context.user
            settings_instance.save()

        logger.info(
            "RegisteredLLM #%d (head of lineage from #%d) created by %s",
            new_row.pk,
            prior.pk,
            info.context.user.username,
        )
        return UpdateRegisteredLLMMutation(
            ok=True,
            message=f"New lineage version #{new_row.pk} created (supersedes #{prior.pk}).",
            registered_llm=_build_registered_llm_payload(new_row, settings_instance),
        )


# ---------------------------------------------------------------------------
# ArchiveRegisteredLLMMutation
# ---------------------------------------------------------------------------


class ArchiveRegisteredLLMMutation(graphene.Mutation):
    """One-way archive: create a new lineage version with is_archived=True.

    The archived row is hidden from the column picker entirely (more
    restrictive than is_enabled=False, which keeps the row visible-but-
    greyed). Existing FKs from Columns / Datacells survive intact via
    ``on_delete=PROTECT``.

    Refuses if the row is currently set as
    ``LLMSettings.default_extract_llm`` — operators must promote a new
    default first via ``SetDefaultExtractLLMMutation``.
    """

    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    registered_llm = graphene.Field(RegisteredLLMType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id: str) -> "ArchiveRegisteredLLMMutation":
        denied = _superuser_only(info.context.user)
        if denied:
            return ArchiveRegisteredLLMMutation(
                ok=False, message=denied, registered_llm=None
            )

        try:
            prior = RegisteredLLM.objects.get(pk=id)
        except (RegisteredLLM.DoesNotExist, ValueError, TypeError):
            return ArchiveRegisteredLLMMutation(
                ok=False, message="RegisteredLLM not found.", registered_llm=None
            )

        if not prior.is_head():
            return ArchiveRegisteredLLMMutation(
                ok=False,
                message=(
                    "RegisteredLLM is not the head of its lineage; archive "
                    "the head version instead."
                ),
                registered_llm=None,
            )
        if prior.is_archived:
            return ArchiveRegisteredLLMMutation(
                ok=False,
                message="RegisteredLLM is already archived.",
                registered_llm=None,
            )

        settings_instance = LLMSettings.get_instance(use_cache=False)
        if settings_instance.default_extract_llm_id == prior.pk:
            return ArchiveRegisteredLLMMutation(
                ok=False,
                message=(
                    "Cannot archive the current default extract LLM. Promote "
                    "another row first via setDefaultExtractLlm."
                ),
                registered_llm=None,
            )

        new_row = RegisteredLLM.objects.create(
            provider_class_path=prior.provider_class_path,
            model_id=prior.model_id,
            display_name=prior.display_name,
            is_enabled=prior.is_enabled,
            is_archived=True,
            context_window=prior.context_window,
            supports_structured_output=prior.supports_structured_output,
            supports_tools=prior.supports_tools,
            max_output_tokens=prior.max_output_tokens,
            temperature_default=prior.temperature_default,
            notes=prior.notes,
            previous_version=prior,
            creator=info.context.user,
        )

        logger.info(
            "RegisteredLLM lineage from #%d archived (new head #%d) by %s",
            prior.pk,
            new_row.pk,
            info.context.user.username,
        )
        return ArchiveRegisteredLLMMutation(
            ok=True,
            message=f"RegisteredLLM lineage archived (head now #{new_row.pk}).",
            registered_llm=_build_registered_llm_payload(new_row, settings_instance),
        )


# ---------------------------------------------------------------------------
# UpdateLLMProviderSecretsMutation
# ---------------------------------------------------------------------------


class UpdateLLMProviderSecretsMutation(graphene.Mutation):
    """Set / update encrypted secrets for one provider class path.

    Mirrors :class:`UpdateComponentSecretsMutation` shape. Secrets are
    Fernet-encrypted (PBKDF2-from-SECRET_KEY); rotating SECRET_KEY
    permanently invalidates everything.
    """

    class Arguments:
        provider_class_path = graphene.String(required=True)
        secrets = GenericScalar(
            required=True,
            description='Dict of secret key/values, e.g. {"api_key": "sk-..."}',
        )
        provider_settings = GenericScalar(
            required=False,
            description=(
                "Optional non-secret kwargs (base_url, organization_id, …) "
                "to merge into LLMSettings.provider_settings[class_path]."
            ),
        )
        merge = graphene.Boolean(
            default_value=True,
            description=(
                "If True (default), merge with existing secrets / settings; "
                "otherwise replace."
            ),
        )

    ok = graphene.Boolean()
    message = graphene.String()
    llm_settings = graphene.Field(LLMSettingsType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root,
        info,
        provider_class_path: str,
        secrets: dict,
        provider_settings: Optional[dict] = None,
        merge: bool = True,
    ) -> "UpdateLLMProviderSecretsMutation":
        denied = _superuser_only(info.context.user)
        if denied:
            return UpdateLLMProviderSecretsMutation(
                ok=False, message=denied, llm_settings=None
            )

        path_err = _validate_provider_class_path(provider_class_path)
        if path_err:
            return UpdateLLMProviderSecretsMutation(
                ok=False, message=path_err, llm_settings=None
            )
        secrets_err = _validate_secrets_input(secrets)
        if secrets_err:
            return UpdateLLMProviderSecretsMutation(
                ok=False, message=secrets_err, llm_settings=None
            )
        if provider_settings is not None and not isinstance(provider_settings, dict):
            return UpdateLLMProviderSecretsMutation(
                ok=False,
                message="provider_settings must be a dictionary",
                llm_settings=None,
            )

        try:
            settings_instance = LLMSettings.get_instance(use_cache=False)
            if not merge:
                settings_instance.delete_component_secrets(provider_class_path)
                if (
                    provider_settings is not None
                    and settings_instance.provider_settings
                    and provider_class_path in settings_instance.provider_settings
                ):
                    del settings_instance.provider_settings[provider_class_path]

            settings_instance.update_secrets(provider_class_path, secrets)
            if provider_settings:
                current = settings_instance.provider_settings or {}
                bucket = current.get(provider_class_path) or {}
                bucket.update(provider_settings)
                current[provider_class_path] = bucket
                settings_instance.provider_settings = current

            settings_instance.modified_by = info.context.user
            settings_instance.save()
        except ValueError as e:
            return UpdateLLMProviderSecretsMutation(
                ok=False,
                message=f"Failed to update secrets: {e}",
                llm_settings=None,
            )
        except Exception:
            logger.exception("Unexpected error updating LLM provider secrets")
            return UpdateLLMProviderSecretsMutation(
                ok=False,
                message="Unexpected error updating provider secrets.",
                llm_settings=None,
            )

        logger.info(
            "LLM provider secrets for %s updated by %s (keys=%s, merge=%s)",
            provider_class_path,
            info.context.user.username,
            ", ".join(sorted(secrets.keys())),
            merge,
        )
        # Reuse the queries resolver shape.
        from config.graphql.llm_queries import LLMQueryMixin

        return UpdateLLMProviderSecretsMutation(
            ok=True,
            message=f"Secrets updated for {provider_class_path}.",
            llm_settings=LLMQueryMixin.resolve_llm_settings(None, info),
        )


# ---------------------------------------------------------------------------
# DeleteLLMProviderSecretsMutation
# ---------------------------------------------------------------------------


class DeleteLLMProviderSecretsMutation(graphene.Mutation):
    """Clear all encrypted secrets + non-secret settings for one provider."""

    class Arguments:
        provider_class_path = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    llm_settings = graphene.Field(LLMSettingsType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(
        root, info, provider_class_path: str
    ) -> "DeleteLLMProviderSecretsMutation":
        denied = _superuser_only(info.context.user)
        if denied:
            return DeleteLLMProviderSecretsMutation(
                ok=False, message=denied, llm_settings=None
            )
        # Note: we deliberately allow deletion for paths not currently
        # registered in code — operators must be able to clear stale
        # secrets after a provider is removed from the codebase.

        try:
            settings_instance = LLMSettings.get_instance(use_cache=False)
            settings_instance.delete_component_secrets(provider_class_path)
            if (
                settings_instance.provider_settings
                and provider_class_path in settings_instance.provider_settings
            ):
                del settings_instance.provider_settings[provider_class_path]
            settings_instance.modified_by = info.context.user
            settings_instance.save()
        except Exception:
            logger.exception("Unexpected error deleting LLM provider secrets")
            return DeleteLLMProviderSecretsMutation(
                ok=False,
                message="Unexpected error deleting provider secrets.",
                llm_settings=None,
            )

        from config.graphql.llm_queries import LLMQueryMixin

        return DeleteLLMProviderSecretsMutation(
            ok=True,
            message=f"Secrets cleared for {provider_class_path}.",
            llm_settings=LLMQueryMixin.resolve_llm_settings(None, info),
        )


# ---------------------------------------------------------------------------
# SetDefaultExtractLLMMutation
# ---------------------------------------------------------------------------


class SetDefaultExtractLLMMutation(graphene.Mutation):
    """Point ``LLMSettings.default_extract_llm`` at a row (or clear it).

    Pass ``id=None`` (or omit) to unset and revert to the legacy
    ``DEFAULT_EXTRACT_MODEL`` env-var fallback.
    """

    class Arguments:
        id = graphene.ID(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    llm_settings = graphene.Field(LLMSettingsType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id: Optional[str] = None) -> "SetDefaultExtractLLMMutation":
        denied = _superuser_only(info.context.user)
        if denied:
            return SetDefaultExtractLLMMutation(
                ok=False, message=denied, llm_settings=None
            )

        target: Optional[RegisteredLLM] = None
        if id is not None:
            try:
                target = RegisteredLLM.objects.get(pk=id)
            except (RegisteredLLM.DoesNotExist, ValueError, TypeError):
                return SetDefaultExtractLLMMutation(
                    ok=False,
                    message="RegisteredLLM not found.",
                    llm_settings=None,
                )
            if target.is_archived:
                return SetDefaultExtractLLMMutation(
                    ok=False,
                    message="Cannot set archived row as default.",
                    llm_settings=None,
                )
            if not target.is_enabled:
                return SetDefaultExtractLLMMutation(
                    ok=False,
                    message="Cannot set disabled row as default.",
                    llm_settings=None,
                )
            if not target.is_head():
                return SetDefaultExtractLLMMutation(
                    ok=False,
                    message=(
                        "Cannot set a non-head lineage version as default; "
                        "promote the head version instead."
                    ),
                    llm_settings=None,
                )

        try:
            settings_instance = LLMSettings.get_instance(use_cache=False)
            settings_instance.default_extract_llm = target
            settings_instance.modified_by = info.context.user
            settings_instance.save()
        except Exception:
            logger.exception("Unexpected error setting default_extract_llm")
            return SetDefaultExtractLLMMutation(
                ok=False,
                message="Unexpected error setting default extract LLM.",
                llm_settings=None,
            )

        logger.info(
            "LLMSettings.default_extract_llm set to %s by %s",
            target.pk if target else None,
            info.context.user.username,
        )
        from config.graphql.llm_queries import LLMQueryMixin

        return SetDefaultExtractLLMMutation(
            ok=True,
            message=(
                f"Default extract LLM set to RegisteredLLM #{target.pk}."
                if target
                else "Default extract LLM cleared."
            ),
            llm_settings=LLMQueryMixin.resolve_llm_settings(None, info),
        )
