"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
import re
from typing import Annotated

import strawberry
from django.core.exceptions import ValidationError

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.pipeline_types import PipelineSettingsType
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.pipeline.base.settings_schema import get_secret_settings

# All pipeline mutations use RateLimits.WRITE_LIGHT (30 requests/minute).
# This is appropriate for superuser-only admin operations that are
# infrequent by nature. Secret operations share this limit, which also
# provides brute-force protection for credential storage endpoints.

logger = logging.getLogger(__name__)

# Validation constants
MAX_COMPONENT_PATH_LENGTH = 256
MAX_MIME_TYPE_LENGTH = 128
# Maximum size (bytes) for JSON settings fields (parsers, embedders, kwargs, etc.)
MAX_JSON_FIELD_SIZE_BYTES = 10240  # 10KB
VALID_COMPONENT_PATH_PATTERN = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+$"
)
VALID_MIME_TYPE_PATTERN = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9!#$&\-^_.+]*\/[a-zA-Z0-9][a-zA-Z0-9!#$&\-^_.+]*$"
)


@graphql_ratelimit(rate=RateLimits.WRITE_LIGHT, group="mutate")
def _write_light_rate_gate(root, info, **kwargs):
    """Rate-limit gate with the ``(root, info)`` shape core decorators expect.

    graphene applied ``@graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)``
    directly to each ``mutate(root, info, ...)`` classmethod; the strawberry
    mutate stubs take ``payload_cls`` as their first positional argument, which
    does not match that calling convention, so the decorator is hoisted onto
    this no-op and invoked at the top of each rate-limited stub.
    ``group="mutate"`` preserves the shared graphene bucket (every graphene
    mutation's func was literally named ``mutate``, so they all shared one
    rate group).
    """
    return None


def validate_component_path(path: str) -> str | None:
    """
    Validate a component class path.

    Args:
        path: The component class path to validate

    Returns:
        Error message if invalid, None if valid
    """
    if not path:
        return "Component path cannot be empty"
    if len(path) > MAX_COMPONENT_PATH_LENGTH:
        return f"Component path exceeds maximum length of {MAX_COMPONENT_PATH_LENGTH}"
    if not VALID_COMPONENT_PATH_PATTERN.match(path):
        return f"Invalid component path format: '{path}'. Must be a valid Python module path."
    return None


def validate_mime_type(mime_type: str) -> str | None:
    """
    Validate a MIME type string.

    Args:
        mime_type: The MIME type to validate

    Returns:
        Error message if invalid, None if valid
    """
    if not mime_type:
        return "MIME type cannot be empty"
    if len(mime_type) > MAX_MIME_TYPE_LENGTH:
        return f"MIME type exceeds maximum length of {MAX_MIME_TYPE_LENGTH}"
    if not VALID_MIME_TYPE_PATTERN.match(mime_type):
        return f"Invalid MIME type format: '{mime_type}'"
    return None


def validate_component_mapping(
    mapping: dict, registry, component_type: str, expected_type=None
) -> str | None:
    """
    Validate a mapping of MIME types to component paths.

    Args:
        mapping: Dict mapping MIME types to component class paths
        registry: Pipeline component registry for validation
        component_type: Type name for error messages (e.g., "Parser")
        expected_type: When provided (a ``ComponentType``), require each mapped
            component to actually BE that stage. Registry membership alone is
            insufficient — assigning e.g. a parser class as a thumbnailer passes
            the membership check but blows up at ingest with an ``AttributeError``
            on ``.generate_thumbnail`` and marks every affected document FAILED.
            Mirrors the stricter guard already applied to ``default_file_converter``.

    A ``None`` value for a MIME type is a delete marker (see
    ``merge_mapping_field``) — its MIME type key is still format-checked, but
    the value itself is not resolved against the registry.

    Returns:
        Error message if invalid, None if valid
    """
    if not isinstance(mapping, dict):
        return f"{component_type} mapping must be a dictionary"

    for mime_type, component_path in mapping.items():
        # Validate MIME type
        error = validate_mime_type(mime_type)
        if error:
            return error

        # None is a delete marker (merge_mapping_field drops this key from
        # the stored mapping) — nothing further to validate for this entry.
        if component_path is None:
            continue

        # Validate component path format
        error = validate_component_path(component_path)
        if error:
            return error

        # Validate component exists in registry
        component_def = registry.get_by_class_name(component_path)
        if not component_def:
            return f"{component_type} '{component_path}' not found in registry"

        # Validate the component is the RIGHT KIND for this stage.
        if expected_type is not None and component_def.component_type != expected_type:
            return (
                f"Component '{component_path}' is a "
                f"{component_def.component_type.value}, not a "
                f"{component_type.lower()}."
            )

    return None


def validate_enricher_mapping(mapping: dict, registry) -> str | None:
    """
    Validate a mapping of MIME types to ORDERED LISTS of enricher class paths.

    Unlike ``validate_component_mapping`` (MIME type -> single component
    path), ``preferred_enrichers`` maps each MIME type to an ORDERED LIST of
    enricher class paths run as a chain between parsing and persistence
    (see ``PipelineSettings.get_preferred_enrichers`` and
    ``opencontractserver.pipeline.utils.run_enrichers``).

    Args:
        mapping: Dict mapping MIME types to lists of enricher class paths
        registry: Pipeline component registry for validation

    A ``None`` value for a MIME type is a delete marker (see
    ``merge_mapping_field``) — its MIME type key is still format-checked, but
    the value itself is not required to be a list.

    Returns:
        Error message if invalid, None if valid
    """
    from opencontractserver.pipeline.registry import ComponentType

    if not isinstance(mapping, dict):
        return "Enricher mapping must be a dictionary"

    for mime_type, path_list in mapping.items():
        # Validate MIME type
        error = validate_mime_type(mime_type)
        if error:
            return error

        # None is a delete marker (merge_mapping_field drops this key from
        # the stored mapping) — nothing further to validate for this entry.
        if path_list is None:
            continue

        # preferred_enrichers is a mime -> ORDERED LIST mapping, not mime -> path
        if not isinstance(path_list, list):
            return (
                f"Enricher mapping for '{mime_type}' must be a list of "
                f"class paths, got {type(path_list).__name__}."
            )

        for component_path in path_list:
            error = validate_component_path(component_path)
            if error:
                return error

            component_def = registry.get_by_class_name(component_path)
            if not component_def:
                return f"Enricher '{component_path}' not found in registry"

            if component_def.component_type != ComponentType.ENRICHER:
                return (
                    f"Component '{component_path}' is a "
                    f"{component_def.component_type.value}, not an enricher."
                )

    return None


def validate_secrets_input(secrets: dict) -> str | None:
    """
    Validate secrets input structure and size.

    Args:
        secrets: Dict of secret key-value pairs

    Returns:
        Error message if invalid, None if valid
    """
    import json

    if not isinstance(secrets, dict):
        return "Secrets must be a dictionary"

    for key, value in secrets.items():
        if not isinstance(key, str):
            return f"Secret key must be a string, got {type(key).__name__}"
        if len(key) > 256:
            return f"Secret key '{key[:50]}...' exceeds maximum length of 256"
        if not isinstance(value, (str, int, float, bool, type(None))):
            return f"Secret value for '{key}' must be a primitive type (string, number, boolean, null)"

    # Validate payload size before encryption attempt
    from opencontractserver.documents.models import PipelineSettings

    max_size = PipelineSettings._get_max_secret_size()
    payload_size = len(json.dumps(secrets).encode("utf-8"))
    if payload_size > max_size:
        return f"Secrets payload ({payload_size} bytes) exceeds maximum size of {max_size} bytes"

    return None


def find_plaintext_secret_keys(
    component_path: str, supplied_kwargs: dict, registry
) -> list[str]:
    """
    Return the list of keys in ``supplied_kwargs`` that the component declares
    as secrets (``SettingType.SECRET``) and whose value is non-empty.

    Empty placeholders (``None`` or ``""``) are allowed as schema markers and
    are not flagged. Real secret values must be stored via the encrypted
    secrets API (``UpdateComponentSecretsMutation``), never inline in
    ``parser_kwargs`` or ``component_settings``.

    Returns an empty list when the component is not registered, has no
    component class, or declares no secret fields — in that case there is
    no schema to enforce against.
    """
    component_def = registry.get_by_class_name(component_path)
    if not component_def or not component_def.component_class:
        return []

    secret_names = set(get_secret_settings(component_def.component_class))
    if not secret_names:
        return []

    return sorted(
        k
        for k, v in supplied_kwargs.items()
        if k in secret_names and v not in (None, "")
    )


def validate_json_field_size(value: dict, field_name: str) -> str | None:
    """
    Validate that a JSON field does not exceed the maximum allowed size.

    Args:
        value: The dict to validate
        field_name: Human-readable field name for error messages

    Returns:
        Error message if too large, None if valid
    """
    import json

    payload_size = len(json.dumps(value).encode("utf-8"))
    if payload_size > MAX_JSON_FIELD_SIZE_BYTES:
        return (
            f"{field_name} payload ({payload_size} bytes) exceeds "
            f"maximum size of {MAX_JSON_FIELD_SIZE_BYTES} bytes"
        )
    return None


def merge_mapping_field(existing: dict | None, incoming: dict) -> dict:
    """
    Shallow-merge ``incoming`` over ``existing`` (top-level keys only).

    The mapping fields on ``PipelineSettings`` (preferred_parsers,
    preferred_embedders, preferred_thumbnailers, preferred_enrichers,
    parser_kwargs, component_settings) are keyed per MIME-type or
    per-component, and each key is independently owned by whichever admin
    action last touched it. A caller updating one key (e.g. the PDF parser)
    must not silently drop sibling keys it never mentioned (e.g. the DOCX
    parser) — that previously happened because the mutation assigned the
    incoming dict wholesale.

    A ``None`` value for a key is a delete marker: that key is dropped from
    the merged result instead of being kept or overwritten. This is required
    by the admin GUI's "-- Unassigned --" / remove-enricher actions
    (``SystemSettings.tsx`` ``handleAssign`` / ``handleAssignEnrichers``),
    which send only the single changed MIME type with ``null`` to clear it —
    a plain ``{**existing, **incoming}`` merge would silently resurrect the
    "removed" key from ``existing`` since the client never re-sends the
    other keys to omit it by.
    """
    merged = {**(existing or {})}
    for key, value in incoming.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


@strawberry.type(
    name="UpdatePipelineSettingsMutation",
    description="Update the singleton pipeline settings.\n\nOnly superusers can modify these settings. Changes take effect immediately\nfor all new document processing tasks.\n\nArguments:\n    preferred_parsers: Dict mapping MIME types to parser class paths\n    preferred_embedders: Dict mapping MIME types to embedder class paths\n    preferred_thumbnailers: Dict mapping MIME types to thumbnailer class paths\n    preferred_enrichers: Dict mapping MIME types to ORDERED LISTS of enricher class paths\n    parser_kwargs: Dict mapping parser class paths to their configuration kwargs\n    component_settings: Dict mapping component class paths to settings overrides\n    default_embedder: Default embedder class path\n\nReturns:\n    ok: Whether the update succeeded\n    message: Status message\n    pipeline_settings: The updated settings",
)
class UpdatePipelineSettingsMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    pipeline_settings: None | (
        Annotated[
            PipelineSettingsType, strawberry.lazy("config.graphql.pipeline_types")
        ]
    ) = strawberry.field(name="pipelineSettings", default=None)


register_type(
    "UpdatePipelineSettingsMutation", UpdatePipelineSettingsMutation, model=None
)


@strawberry.type(
    name="ResetPipelineSettingsMutation",
    description="Reset pipeline settings to Django settings defaults.\n\nThis mutation resets all pipeline settings to their default values from\nDjango settings (PREFERRED_PARSERS, PREFERRED_EMBEDDERS, etc.).\n\nOnly superusers can perform this operation.",
)
class ResetPipelineSettingsMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    pipeline_settings: None | (
        Annotated[
            PipelineSettingsType, strawberry.lazy("config.graphql.pipeline_types")
        ]
    ) = strawberry.field(name="pipelineSettings", default=None)


register_type(
    "ResetPipelineSettingsMutation", ResetPipelineSettingsMutation, model=None
)


@strawberry.type(
    name="UpdateComponentSecretsMutation",
    description="Update encrypted secrets for a specific pipeline component.\n\nThis mutation allows superusers to securely store API keys, tokens, and\nother credentials for pipeline components. The secrets are encrypted at\nrest using Fernet symmetric encryption.\n\nOnly superusers can perform this operation.\n\nArguments:\n    component_path: Full class path of the component (e.g.,\n        'opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser')\n    secrets: Dict of secret key-value pairs to store (e.g., {'api_key': '...'})\n    merge: If True, merge with existing secrets. If False, replace all secrets\n        for this component. Default: True\n\nReturns:\n    ok: Whether the update succeeded\n    message: Status message\n    components_with_secrets: List of component paths that have secrets stored",
)
class UpdateComponentSecretsMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    components_with_secrets: list[str | None] | None = strawberry.field(
        name="componentsWithSecrets",
        description="List of component paths that have secrets stored.",
        default=None,
    )


register_type(
    "UpdateComponentSecretsMutation", UpdateComponentSecretsMutation, model=None
)


@strawberry.type(
    name="DeleteComponentSecretsMutation",
    description="Delete all encrypted secrets for a specific pipeline component.\n\nOnly superusers can perform this operation.\n\nArguments:\n    component_path: Full class path of the component\n\nReturns:\n    ok: Whether the deletion succeeded\n    message: Status message\n    components_with_secrets: Updated list of component paths that have secrets",
)
class DeleteComponentSecretsMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    components_with_secrets: list[str | None] | None = strawberry.field(
        name="componentsWithSecrets", default=None
    )


register_type(
    "DeleteComponentSecretsMutation", DeleteComponentSecretsMutation, model=None
)


@strawberry.type(
    name="UpdateToolSecretsMutation",
    description='Update encrypted secrets for an agent tool (e.g. web search API keys).\n\nTool secrets are stored in PipelineSettings alongside component secrets,\nunder a ``tool:`` namespace prefix. Only superusers can perform this.\n\nArguments:\n    tool_key: Tool identifier, e.g. ``"tool:web_search"``\n    secrets: Dict of secret key-value pairs, e.g. ``{"api_key": "..."}``\n    settings: Optional non-sensitive settings, e.g. ``{"provider": "brave"}``\n    merge: If True (default), merge with existing; if False, replace.',
)
class UpdateToolSecretsMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    tools_with_secrets: list[str | None] | None = strawberry.field(
        name="toolsWithSecrets",
        description="Tool keys that have secrets stored.",
        default=None,
    )


register_type("UpdateToolSecretsMutation", UpdateToolSecretsMutation, model=None)


@strawberry.type(
    name="DeleteToolSecretsMutation",
    description="Delete all settings and secrets for an agent tool.\n\nOnly superusers can perform this operation.",
)
class DeleteToolSecretsMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    tools_with_secrets: list[str | None] | None = strawberry.field(
        name="toolsWithSecrets", default=None
    )


register_type("DeleteToolSecretsMutation", DeleteToolSecretsMutation, model=None)


def _mutate_UpdatePipelineSettingsMutation(
    payload_cls,
    root,
    info,
    preferred_parsers=None,
    preferred_embedders=None,
    preferred_thumbnailers=None,
    preferred_enrichers=None,
    parser_kwargs=None,
    component_settings=None,
    default_embedder=None,
    default_reranker=None,
    default_file_converter=None,
    default_llm=None,
    enabled_components=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/pipeline_settings_mutations.py:412

    Port of UpdatePipelineSettingsMutation.mutate

    Update the pipeline settings.

    Security: Only superusers can update these settings.
    """
    # @login_required + @graphql_ratelimit(WRITE_LIGHT) — inlined because the
    # mutate stub takes ``payload_cls`` first, breaking the ``(root, info)``
    # calling convention the core decorators expect.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    _write_light_rate_gate(root, info)

    from opencontractserver.documents.models import PipelineSettings
    from opencontractserver.pipeline.registry import ComponentType, get_registry

    user = info.context.user

    # SECURITY: Only superusers can update pipeline settings
    if not user.is_superuser:
        return payload_cls(
            ok=False,
            message="Only superusers can update pipeline settings.",
            pipeline_settings=None,
        )

    try:
        settings_instance = PipelineSettings.get_instance()
        registry = get_registry()

        # Validate and merge preferred_parsers. Only the incoming (changed)
        # entries are validated — previously-stored entries were already
        # validated when they were set — but the size cap is checked
        # against the merged result so repeated small updates can't
        # accumulate past the limit.
        if preferred_parsers is not None:
            merged_parsers = merge_mapping_field(
                settings_instance.preferred_parsers, preferred_parsers
            )
            error = validate_component_mapping(
                preferred_parsers, registry, "Parser", ComponentType.PARSER
            ) or validate_json_field_size(merged_parsers, "preferred_parsers")
            if error:
                return payload_cls(ok=False, message=error, pipeline_settings=None)
            settings_instance.preferred_parsers = merged_parsers

        # Validate and merge preferred_embedders
        if preferred_embedders is not None:
            merged_embedders = merge_mapping_field(
                settings_instance.preferred_embedders, preferred_embedders
            )
            error = validate_component_mapping(
                preferred_embedders, registry, "Embedder", ComponentType.EMBEDDER
            ) or validate_json_field_size(merged_embedders, "preferred_embedders")
            if error:
                return payload_cls(ok=False, message=error, pipeline_settings=None)
            settings_instance.preferred_embedders = merged_embedders

        # Validate and merge preferred_thumbnailers
        if preferred_thumbnailers is not None:
            merged_thumbnailers = merge_mapping_field(
                settings_instance.preferred_thumbnailers, preferred_thumbnailers
            )
            error = validate_component_mapping(
                preferred_thumbnailers,
                registry,
                "Thumbnailer",
                ComponentType.THUMBNAILER,
            ) or validate_json_field_size(merged_thumbnailers, "preferred_thumbnailers")
            if error:
                return payload_cls(ok=False, message=error, pipeline_settings=None)
            settings_instance.preferred_thumbnailers = merged_thumbnailers

        # Validate and merge preferred_enrichers (per MIME type — each
        # entry is an ordered enricher-chain list, atomically replaced
        # for the MIME types the caller names; sibling MIME types keep
        # their existing chains).
        if preferred_enrichers is not None:
            merged_enrichers = merge_mapping_field(
                settings_instance.preferred_enrichers, preferred_enrichers
            )
            error = validate_enricher_mapping(
                preferred_enrichers, registry
            ) or validate_json_field_size(merged_enrichers, "preferred_enrichers")
            if error:
                return payload_cls(ok=False, message=error, pipeline_settings=None)
            settings_instance.preferred_enrichers = merged_enrichers

        # Validate and merge parser_kwargs (per parser class path — setting
        # one parser's kwargs must not drop another parser's kwargs).
        if parser_kwargs is not None:
            if not isinstance(parser_kwargs, dict):
                return payload_cls(
                    ok=False,
                    message="parser_kwargs must be a dictionary.",
                    pipeline_settings=None,
                )
            merged_parser_kwargs = merge_mapping_field(
                settings_instance.parser_kwargs, parser_kwargs
            )
            error = validate_json_field_size(merged_parser_kwargs, "parser_kwargs")
            if error:
                return payload_cls(ok=False, message=error, pipeline_settings=None)

            # Reject plaintext secrets in parser_kwargs. Operators must
            # store API keys / credentials via UpdateComponentSecretsMutation
            # so they are encrypted at rest. Empty placeholders are allowed
            # as schema markers.
            for parser_path, kwargs in parser_kwargs.items():
                # None is a delete marker (merge_mapping_field drops this
                # parser's kwargs entirely) — nothing to validate.
                if kwargs is None:
                    continue
                if not isinstance(kwargs, dict):
                    return payload_cls(
                        ok=False,
                        message=(
                            f"parser_kwargs entries must be dicts; got "
                            f"{type(kwargs).__name__} for '{parser_path}'."
                        ),
                        pipeline_settings=None,
                    )
                plaintext = find_plaintext_secret_keys(parser_path, kwargs, registry)
                if plaintext:
                    return payload_cls(
                        ok=False,
                        message=(
                            f"parser_kwargs for '{parser_path}' contains "
                            f"plaintext values for secret fields: "
                            f"{', '.join(plaintext)}. Store these via "
                            f"the updateComponentSecrets mutation instead. "
                            f"Empty values are permitted as schema markers."
                        ),
                        pipeline_settings=None,
                    )
            settings_instance.parser_kwargs = merged_parser_kwargs

        # Validate and merge component_settings (per component class path —
        # setting one component's settings must not drop another
        # component's settings).
        if component_settings is not None:
            if not isinstance(component_settings, dict):
                return payload_cls(
                    ok=False,
                    message="component_settings must be a dictionary.",
                    pipeline_settings=None,
                )
            merged_component_settings = merge_mapping_field(
                settings_instance.component_settings, component_settings
            )
            error = validate_json_field_size(
                merged_component_settings, "component_settings"
            )
            if error:
                return payload_cls(ok=False, message=error, pipeline_settings=None)

            # Validate each component's settings against its schema
            for comp_path, comp_settings in component_settings.items():
                # Validate component path format
                error = validate_component_path(comp_path)
                if error:
                    return payload_cls(
                        ok=False,
                        message=f"Invalid component path in component_settings: {error}",
                        pipeline_settings=None,
                    )

                # None is a delete marker (merge_mapping_field drops this
                # component's settings entirely) — nothing to validate.
                if comp_settings is None:
                    continue

                if not isinstance(comp_settings, dict):
                    return payload_cls(
                        ok=False,
                        message=f"Settings for '{comp_path}' must be a dictionary.",
                        pipeline_settings=None,
                    )

                # Reject plaintext secrets in component_settings. Empty
                # placeholders are allowed as schema markers; real secret
                # values must go through updateComponentSecrets.
                plaintext = find_plaintext_secret_keys(
                    comp_path, comp_settings, registry
                )
                if plaintext:
                    return payload_cls(
                        ok=False,
                        message=(
                            f"component_settings for '{comp_path}' contains "
                            f"plaintext values for secret fields: "
                            f"{', '.join(plaintext)}. Store these via "
                            f"the updateComponentSecrets mutation instead. "
                            f"Empty values are permitted as schema markers."
                        ),
                        pipeline_settings=None,
                    )

                # Validate settings values against component schema
                component_def = registry.get_by_class_name(comp_path)
                if component_def and component_def.component_class:
                    from opencontractserver.pipeline.base.settings_schema import (
                        get_secret_settings,
                        validate_settings,
                    )

                    # Filter out secrets from validation (they're stored separately)
                    secret_names = get_secret_settings(component_def.component_class)
                    non_secret_settings = {
                        k: v for k, v in comp_settings.items() if k not in secret_names
                    }

                    is_valid, errors = validate_settings(
                        component_def.component_class, non_secret_settings
                    )
                    if not is_valid:
                        return payload_cls(
                            ok=False,
                            message=f"Invalid settings for '{comp_path}': {'; '.join(errors)}",
                            pipeline_settings=None,
                        )

            settings_instance.component_settings = merged_component_settings

        # Validate default_embedder
        if default_embedder is not None:
            if default_embedder:
                error = validate_component_path(default_embedder)
                if error:
                    return payload_cls(ok=False, message=error, pipeline_settings=None)
                if not registry.get_by_class_name(default_embedder):
                    return payload_cls(
                        ok=False,
                        message=f"Default embedder '{default_embedder}' not found in registry.",
                        pipeline_settings=None,
                    )
            settings_instance.default_embedder = default_embedder

        # Validate default_reranker (empty string = disabled)
        if default_reranker is not None:
            if default_reranker:
                error = validate_component_path(default_reranker)
                if error:
                    return payload_cls(ok=False, message=error, pipeline_settings=None)
                if not registry.get_by_class_name(default_reranker):
                    return payload_cls(
                        ok=False,
                        message=(
                            f"Default reranker '{default_reranker}' "
                            "not found in registry."
                        ),
                        pipeline_settings=None,
                    )
            settings_instance.default_reranker = default_reranker

        # Validate default_file_converter (empty string = conversion
        # disabled). Beyond registry presence, require the component to
        # actually BE a file converter — assigning e.g. a parser here
        # would silently break the ingest conversion step.
        if default_file_converter is not None:
            if default_file_converter:
                error = validate_component_path(default_file_converter)
                if error:
                    return payload_cls(ok=False, message=error, pipeline_settings=None)
                converter_def = registry.get_by_class_name(default_file_converter)
                if not converter_def:
                    return payload_cls(
                        ok=False,
                        message=(
                            f"File converter '{default_file_converter}' "
                            "not found in registry."
                        ),
                        pipeline_settings=None,
                    )
                from opencontractserver.pipeline.registry import ComponentType

                if converter_def.component_type != ComponentType.FILE_CONVERTER:
                    return payload_cls(
                        ok=False,
                        message=(
                            f"Component '{default_file_converter}' is a "
                            f"{converter_def.component_type.value}, not a "
                            "file converter."
                        ),
                        pipeline_settings=None,
                    )
            settings_instance.default_file_converter = default_file_converter

        # Validate default_llm (empty string = fall back to Django settings).
        # Unlike the other defaults this is a pydantic-ai model spec
        # ("{provider}:{model}"), not a component class path, so it is
        # validated with the LLM registry rather than validate_component_path.
        if default_llm is not None:
            if default_llm:
                from opencontractserver.llms.llm_registry import (
                    LLMProviderNotRegistered,
                    normalise_model_spec,
                    validate_model_spec,
                )

                # Both calls are required and complementary, NOT redundant:
                # validate_model_spec is the only one that checks the
                # provider is registered (raises LLMProviderNotRegistered);
                # normalise_model_spec only parses/formats and raises
                # ValueError on a malformed spec. Collapsing to a single
                # normalise call would silently accept an unregistered
                # provider. Both live in the same try/except so either error
                # returns a clean ok=False response instead of a 500.
                try:
                    validate_model_spec(default_llm)
                    # Persist the canonical "{provider}:{model}" form so the
                    # stored value is unambiguous (bare names get the default
                    # provider prefix applied).
                    normalised_llm = normalise_model_spec(default_llm)
                except LLMProviderNotRegistered as exc:
                    return payload_cls(
                        ok=False, message=str(exc), pipeline_settings=None
                    )
                except ValueError as exc:
                    return payload_cls(
                        ok=False,
                        message=f"Invalid default LLM spec: {exc}",
                        pipeline_settings=None,
                    )
                settings_instance.default_llm = normalised_llm
            else:
                settings_instance.default_llm = ""

        # Validate enabled_components
        if enabled_components is not None:
            if not isinstance(enabled_components, list):
                return payload_cls(
                    ok=False,
                    message="enabled_components must be a list.",
                    pipeline_settings=None,
                )

            if any(p is None for p in enabled_components):
                return payload_cls(
                    ok=False,
                    message="enabled_components must not contain null values.",
                    pipeline_settings=None,
                )

            for comp_path in enabled_components:
                error = validate_component_path(comp_path)
                if error:
                    return payload_cls(
                        ok=False,
                        message=f"Invalid path in enabled_components: {error}",
                        pipeline_settings=None,
                    )
                if not registry.get_by_class_name(comp_path):
                    return payload_cls(
                        ok=False,
                        message=f"Component '{comp_path}' in enabled_components not found in registry.",
                        pipeline_settings=None,
                    )

            # The "assigned components must stay enabled" check used to
            # live here, scoped to only this branch. It's now handled
            # uniformly below by `_find_disabled_but_assigned`, which
            # covers this same case (enabled_components touched) plus
            # every other field whose assignment can conflict with it —
            # see the "Consistency check (issue #2116)" comment below.
            settings_instance.enabled_components = list(
                dict.fromkeys(enabled_components)
            )

        # Consistency check (issue #2116): assigned components must be a
        # subset of enabled_components. This must run whenever EITHER
        # enabled_components OR any of the assignment fields
        # (preferred_parsers/preferred_embedders/preferred_thumbnailers/
        # default_embedder/default_file_converter/default_reranker)
        # changes in this call — not only when enabled_components itself
        # is touched. Previously
        # this check lived solely inside `if enabled_components is not
        # None:` above, so a call that assigned a NEW disabled component
        # without also re-sending enabled_components skipped the check
        # entirely, even though a prior save had already set a non-empty
        # enabled_components list.
        def _find_disabled_but_assigned() -> str | None:
            """Return a comma-joined list of assigned-but-disabled
            component paths, or None if everything assigned is enabled
            (including the "empty enabled_components = all enabled"
            backward-compatible default)."""
            resolved_enabled_components = (
                enabled_components
                if enabled_components is not None
                else settings_instance.enabled_components or []
            )
            enabled_set = set(resolved_enabled_components)
            if not enabled_set:
                return None

            # preferred_parsers/embedders/thumbnailers are read straight
            # off settings_instance (not the raw request args) because
            # the blocks above already merged any incoming update into
            # it — settings_instance reflects the full post-merge state
            # whether or not this call touched each field. Using the raw
            # arg here would only see this call's partial delta and miss
            # pre-existing sibling assignments the merge preserved.
            assigned_parsers = settings_instance.preferred_parsers or {}
            assigned_embedders = settings_instance.preferred_embedders or {}
            assigned_thumbnailers = settings_instance.preferred_thumbnailers or {}
            assigned_default = (
                default_embedder
                if default_embedder is not None
                else settings_instance.default_embedder or ""
            )
            assigned_converter = (
                default_file_converter
                if default_file_converter is not None
                else settings_instance.default_file_converter or ""
            )
            assigned_reranker = (
                default_reranker
                if default_reranker is not None
                else settings_instance.default_reranker or ""
            )

            all_assigned = {
                path
                for path in (
                    *assigned_parsers.values(),
                    *assigned_embedders.values(),
                    *assigned_thumbnailers.values(),
                )
                if path
            }
            if assigned_default:
                all_assigned.add(assigned_default)
            if assigned_converter:
                all_assigned.add(assigned_converter)
            if assigned_reranker:
                all_assigned.add(assigned_reranker)

            disabled_but_assigned = all_assigned - enabled_set
            if not disabled_but_assigned:
                return None
            return ", ".join(sorted(disabled_but_assigned))

        if (
            enabled_components is not None
            or preferred_parsers is not None
            or preferred_embedders is not None
            or preferred_thumbnailers is not None
            or default_embedder is not None
            or default_file_converter is not None
            or default_reranker is not None
        ):
            names = _find_disabled_but_assigned()
            if names:
                return payload_cls(
                    ok=False,
                    message=f"Cannot disable components that are assigned as filetype defaults: {names}",
                    pipeline_settings=None,
                )

        # Record who made the change
        settings_instance.modified_by = user
        settings_instance.save()

        if default_reranker is not None:
            # Drop cached reranker instance so the next retrieval picks
            # up the new configuration without a worker restart. Runs
            # only after save() so a mutation rejected by the
            # disabled-but-assigned consistency check above never
            # invalidates the cache for a change that wasn't persisted.
            from opencontractserver.pipeline.utils import (
                invalidate_reranker_cache,
            )

            invalidate_reranker_cache()

        updated_fields = [
            name
            for name, val in [
                ("preferred_parsers", preferred_parsers),
                ("preferred_embedders", preferred_embedders),
                ("preferred_thumbnailers", preferred_thumbnailers),
                ("preferred_enrichers", preferred_enrichers),
                ("parser_kwargs", parser_kwargs),
                ("component_settings", component_settings),
                ("default_embedder", default_embedder),
                ("default_reranker", default_reranker),
                ("default_file_converter", default_file_converter),
                ("default_llm", default_llm),
                ("enabled_components", enabled_components),
            ]
            if val is not None
        ]
        logger.info(
            "Pipeline settings updated by %s: fields=%s",
            user.username,
            ", ".join(updated_fields),
        )

        return payload_cls(
            ok=True,
            message="Pipeline settings updated successfully.",
            pipeline_settings=PipelineSettingsType(
                preferred_parsers=settings_instance.preferred_parsers or {},
                preferred_embedders=settings_instance.preferred_embedders or {},
                preferred_thumbnailers=settings_instance.preferred_thumbnailers or {},
                preferred_enrichers=settings_instance.preferred_enrichers or {},
                parser_kwargs=settings_instance.parser_kwargs or {},
                component_settings=settings_instance.component_settings or {},
                default_embedder=settings_instance.default_embedder or "",
                default_reranker=settings_instance.default_reranker or "",
                default_file_converter=settings_instance.default_file_converter or "",
                default_llm=settings_instance.default_llm or "",
                enabled_components=settings_instance.enabled_components or [],
                components_with_secrets=(
                    settings_instance.get_components_with_secrets()
                ),
                modified=settings_instance.modified,
                modified_by=settings_instance.modified_by,
            ),
        )

    except (ValidationError, ValueError) as e:
        return payload_cls(
            ok=False,
            message=f"Failed to update pipeline settings: {e}",
            pipeline_settings=None,
        )
    except Exception:
        logger.exception("Unexpected error updating pipeline settings")
        return payload_cls(
            ok=False,
            message="An unexpected error occurred while updating pipeline settings.",
            pipeline_settings=None,
        )


def m_update_pipeline_settings(
    info: strawberry.Info,
    component_settings: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="componentSettings",
            description="Mapping of component class paths to settings overrides.",
        ),
    ] = strawberry.UNSET,
    default_embedder: Annotated[
        str | None,
        strawberry.argument(
            name="defaultEmbedder",
            description="Default embedder class path used for all ingest embedding. There is no MIME-specific override; see preferred_embedders.",
        ),
    ] = strawberry.UNSET,
    default_file_converter: Annotated[
        str | None,
        strawberry.argument(
            name="defaultFileConverter",
            description="File converter class path used to convert non-native upload formats to PDF before parsing. Empty string disables the conversion step.",
        ),
    ] = strawberry.UNSET,
    default_llm: Annotated[
        str | None,
        strawberry.argument(
            name="defaultLlm",
            description="Install-wide default LLM model spec (pydantic-ai '{provider}:{model}' form, e.g. 'anthropic:claude-opus-4-6') for agents when no per-corpus or per-agent override is set. Empty string falls back to the Django settings default. The provider prefix must be a registered LLM provider.",
        ),
    ] = strawberry.UNSET,
    default_reranker: Annotated[
        str | None,
        strawberry.argument(
            name="defaultReranker",
            description="Default post-retrieval reranker class path. Empty string disables reranking (first-stage vector / hybrid search only).",
        ),
    ] = strawberry.UNSET,
    enabled_components: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="enabledComponents",
            description="List of enabled component class paths. Components assigned as filetype defaults must be included.",
        ),
    ] = strawberry.UNSET,
    parser_kwargs: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="parserKwargs",
            description="Mapping of parser class paths to their configuration kwargs. Example: {'DoclingParser': {'force_ocr': true}}",
        ),
    ] = strawberry.UNSET,
    preferred_embedders: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="preferredEmbedders",
            description="Mapping of MIME types to preferred embedder class paths. API-only (issue #2114): has no effect at ingest, which always resolves the single global default_embedder to keep the cross-corpus vector index on one embedding space.",
        ),
    ] = strawberry.UNSET,
    preferred_enrichers: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="preferredEnrichers",
            description="Mapping of MIME types to ordered lists of preferred enricher class paths.",
        ),
    ] = strawberry.UNSET,
    preferred_parsers: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="preferredParsers",
            description="Mapping of MIME types to preferred parser class paths. Example: {'application/pdf': 'opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser'}",
        ),
    ] = strawberry.UNSET,
    preferred_thumbnailers: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="preferredThumbnailers",
            description="Mapping of MIME types to preferred thumbnailer class paths.",
        ),
    ] = strawberry.UNSET,
) -> UpdatePipelineSettingsMutation | None:
    kwargs = strip_unset(
        {
            "component_settings": component_settings,
            "default_embedder": default_embedder,
            "default_file_converter": default_file_converter,
            "default_llm": default_llm,
            "default_reranker": default_reranker,
            "enabled_components": enabled_components,
            "parser_kwargs": parser_kwargs,
            "preferred_embedders": preferred_embedders,
            "preferred_enrichers": preferred_enrichers,
            "preferred_parsers": preferred_parsers,
            "preferred_thumbnailers": preferred_thumbnailers,
        }
    )
    return _mutate_UpdatePipelineSettingsMutation(
        UpdatePipelineSettingsMutation, None, info, **kwargs
    )


def _mutate_ResetPipelineSettingsMutation(payload_cls, root, info):
    """PORT: /home/user/oc-graphene-ref/config/graphql/pipeline_settings_mutations.py:1001

    Port of ResetPipelineSettingsMutation.mutate

    Reset pipeline settings to Django settings defaults.
    """
    # @login_required + @graphql_ratelimit(WRITE_LIGHT) — inlined (see
    # _mutate_UpdatePipelineSettingsMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    _write_light_rate_gate(root, info)

    from django.conf import settings as django_settings

    from opencontractserver.documents.models import PipelineSettings

    user = info.context.user

    # SECURITY: Only superusers can reset pipeline settings
    if not user.is_superuser:
        return payload_cls(
            ok=False,
            message="Only superusers can reset pipeline settings.",
            pipeline_settings=None,
        )

    try:
        settings_instance = PipelineSettings.get_instance()

        # Reset to Django settings defaults
        settings_instance.preferred_parsers = getattr(
            django_settings, "PREFERRED_PARSERS", {}
        )
        settings_instance.preferred_embedders = getattr(
            django_settings, "PREFERRED_EMBEDDERS", {}
        )
        settings_instance.preferred_thumbnailers = {}
        settings_instance.preferred_enrichers = getattr(
            django_settings, "PREFERRED_ENRICHERS", {}
        )
        settings_instance.parser_kwargs = getattr(django_settings, "PARSER_KWARGS", {})
        settings_instance.component_settings = getattr(
            django_settings, "PIPELINE_SETTINGS", {}
        )
        settings_instance.default_embedder = (
            getattr(django_settings, "DEFAULT_EMBEDDER", "") or ""
        )
        settings_instance.default_reranker = (
            getattr(django_settings, "DEFAULT_RERANKER", "") or ""
        )
        settings_instance.default_file_converter = (
            getattr(django_settings, "DEFAULT_FILE_CONVERTER", "") or ""
        )
        # ``DEFAULT_LLM`` may be explicitly None; coerce to "" so the NOT NULL
        # default_llm column is never assigned a null value.
        settings_instance.default_llm = (
            getattr(django_settings, "DEFAULT_LLM", "") or ""
        )
        settings_instance.enabled_components = []
        settings_instance.modified_by = user
        settings_instance.save()

        logger.info(f"Pipeline settings reset to defaults by {user.username}")

        return payload_cls(
            ok=True,
            message="Pipeline settings reset to defaults successfully.",
            pipeline_settings=PipelineSettingsType(
                preferred_parsers=settings_instance.preferred_parsers or {},
                preferred_embedders=settings_instance.preferred_embedders or {},
                preferred_thumbnailers=settings_instance.preferred_thumbnailers or {},
                preferred_enrichers=settings_instance.preferred_enrichers or {},
                parser_kwargs=settings_instance.parser_kwargs or {},
                component_settings=settings_instance.component_settings or {},
                default_embedder=settings_instance.default_embedder or "",
                default_reranker=settings_instance.default_reranker or "",
                default_file_converter=settings_instance.default_file_converter or "",
                default_llm=settings_instance.default_llm or "",
                enabled_components=[],
                components_with_secrets=(
                    settings_instance.get_components_with_secrets()
                ),
                modified=settings_instance.modified,
                modified_by=settings_instance.modified_by,
            ),
        )

    except (ValidationError, ValueError) as e:
        return payload_cls(
            ok=False,
            message=f"Failed to reset pipeline settings: {e}",
            pipeline_settings=None,
        )
    except Exception:
        logger.exception("Unexpected error resetting pipeline settings")
        return payload_cls(
            ok=False,
            message="An unexpected error occurred while resetting pipeline settings.",
            pipeline_settings=None,
        )


def m_reset_pipeline_settings(
    info: strawberry.Info,
) -> ResetPipelineSettingsMutation | None:
    kwargs = strip_unset({})
    return _mutate_ResetPipelineSettingsMutation(
        ResetPipelineSettingsMutation, None, info, **kwargs
    )


def _mutate_UpdateComponentSecretsMutation(
    payload_cls, root, info, component_path, secrets, merge=True
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/pipeline_settings_mutations.py:1146

    Port of UpdateComponentSecretsMutation.mutate

    Update encrypted secrets for a component.
    """
    # @login_required + @graphql_ratelimit(WRITE_LIGHT) — inlined (see
    # _mutate_UpdatePipelineSettingsMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    _write_light_rate_gate(root, info)

    from opencontractserver.documents.models import PipelineSettings

    user = info.context.user

    # SECURITY: Only superusers can update secrets
    if not user.is_superuser:
        return payload_cls(
            ok=False,
            message="Only superusers can update component secrets.",
            components_with_secrets=None,
        )

    # Validate component path
    error = validate_component_path(component_path)
    if error:
        return payload_cls(ok=False, message=error, components_with_secrets=None)

    # Validate secrets structure
    error = validate_secrets_input(secrets)
    if error:
        return payload_cls(ok=False, message=error, components_with_secrets=None)

    try:
        settings_instance = PipelineSettings.get_instance()

        if merge:
            # Merge with existing secrets
            settings_instance.update_secrets(component_path, secrets)
        else:
            # Replace all secrets for this component
            all_secrets = settings_instance.get_secrets()
            all_secrets[component_path] = secrets
            settings_instance.set_secrets(all_secrets)

        settings_instance.modified_by = user
        settings_instance.save()

        # Return list of components that have secrets (don't return actual
        # secrets). Excludes tool: keys, which are tracked separately.
        components_with_secrets = settings_instance.get_components_with_secrets()

        logger.info(
            "Secrets updated for component '%s' by %s (keys=%s, merge=%s)",
            component_path,
            user.username,
            ", ".join(secrets.keys()),
            merge,
        )

        return payload_cls(
            ok=True,
            message=f"Secrets updated successfully for '{component_path}'.",
            components_with_secrets=components_with_secrets,
        )

    except ValueError as e:
        return payload_cls(
            ok=False,
            message=f"Failed to update secrets for '{component_path}': {e}",
            components_with_secrets=None,
        )
    except Exception:
        logger.exception(
            "Unexpected error updating secrets for component '%s'",
            component_path,
        )
        return payload_cls(
            ok=False,
            message=f"An unexpected error occurred while updating secrets for '{component_path}'.",
            components_with_secrets=None,
        )


def m_update_component_secrets(
    info: strawberry.Info,
    component_path: Annotated[
        str,
        strawberry.argument(
            name="componentPath", description="Full class path of the component."
        ),
    ] = strawberry.UNSET,
    merge: Annotated[
        bool | None,
        strawberry.argument(
            name="merge",
            description="If True, merge with existing secrets. If False, replace all secrets for this component.",
        ),
    ] = True,
    secrets: Annotated[
        GenericScalar,
        strawberry.argument(
            name="secrets",
            description="Dict of secret key-value pairs to store. Example: {'api_key': 'sk-...', 'secret_token': '...'}",
        ),
    ] = strawberry.UNSET,
) -> UpdateComponentSecretsMutation | None:
    kwargs = strip_unset(
        {"component_path": component_path, "merge": merge, "secrets": secrets}
    )
    return _mutate_UpdateComponentSecretsMutation(
        UpdateComponentSecretsMutation, None, info, **kwargs
    )


def _mutate_DeleteComponentSecretsMutation(payload_cls, root, info, component_path):
    """PORT: /home/user/oc-graphene-ref/config/graphql/pipeline_settings_mutations.py:1489

    Port of DeleteComponentSecretsMutation.mutate

    Delete all secrets for a component.
    """
    # @login_required + @graphql_ratelimit(WRITE_LIGHT) — inlined (see
    # _mutate_UpdatePipelineSettingsMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    _write_light_rate_gate(root, info)

    from opencontractserver.documents.models import PipelineSettings

    user = info.context.user

    # SECURITY: Only superusers can delete secrets
    if not user.is_superuser:
        return payload_cls(
            ok=False,
            message="Only superusers can delete component secrets.",
            components_with_secrets=None,
        )

    try:
        settings_instance = PipelineSettings.get_instance()
        settings_instance.delete_component_secrets(component_path)
        settings_instance.modified_by = user
        settings_instance.save()

        # Return updated list of components with secrets (excludes tool: keys).
        components_with_secrets = settings_instance.get_components_with_secrets()

        logger.info(
            f"Secrets deleted for component '{component_path}' by {user.username}"
        )

        return payload_cls(
            ok=True,
            message=f"Secrets deleted for '{component_path}'.",
            components_with_secrets=components_with_secrets,
        )

    except Exception:
        logger.exception(
            "Unexpected error deleting secrets for component '%s'",
            component_path,
        )
        return payload_cls(
            ok=False,
            message=f"An unexpected error occurred while deleting secrets for '{component_path}'.",
            components_with_secrets=None,
        )


def m_delete_component_secrets(
    info: strawberry.Info,
    component_path: Annotated[
        str,
        strawberry.argument(
            name="componentPath", description="Full class path of the component."
        ),
    ] = strawberry.UNSET,
) -> DeleteComponentSecretsMutation | None:
    kwargs = strip_unset({"component_path": component_path})
    return _mutate_DeleteComponentSecretsMutation(
        DeleteComponentSecretsMutation, None, info, **kwargs
    )


def _mutate_UpdateToolSecretsMutation(
    payload_cls, root, info, tool_key, secrets=None, settings=None, merge=True
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/pipeline_settings_mutations.py:1271

    Port of UpdateToolSecretsMutation.mutate

    Update secrets and/or settings for an agent tool.
    """
    # @login_required + @graphql_ratelimit(WRITE_LIGHT) — inlined (see
    # _mutate_UpdatePipelineSettingsMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    _write_light_rate_gate(root, info)

    from opencontractserver.constants.tools import TOOL_SETTINGS_PREFIX
    from opencontractserver.documents.models import PipelineSettings

    user = info.context.user

    if not user.is_superuser:
        return payload_cls(
            ok=False,
            message="Only superusers can update tool secrets.",
            tools_with_secrets=None,
        )

    # Validate tool key format
    if not tool_key or not tool_key.startswith(TOOL_SETTINGS_PREFIX):
        return payload_cls(
            ok=False,
            message=f"Tool key must start with '{TOOL_SETTINGS_PREFIX}'.",
            tools_with_secrets=None,
        )

    # Validate key length and characters
    if len(tool_key) > MAX_COMPONENT_PATH_LENGTH:
        return payload_cls(
            ok=False,
            message=f"Tool key exceeds maximum length of {MAX_COMPONENT_PATH_LENGTH}.",
            tools_with_secrets=None,
        )

    if not secrets and not settings:
        return payload_cls(
            ok=False,
            message="At least one of 'secrets' or 'settings' must be provided.",
            tools_with_secrets=None,
        )

    # Validate secrets structure
    if secrets is not None:
        error = validate_secrets_input(secrets)
        if error:
            return payload_cls(ok=False, message=error, tools_with_secrets=None)

    # Validate settings structure
    if settings is not None and not isinstance(settings, dict):
        return payload_cls(
            ok=False,
            message="settings must be a dictionary.",
            tools_with_secrets=None,
        )

    # Validate provider value for web_search tool
    if settings and "provider" in settings:
        from opencontractserver.constants.web_search import (
            SUPPORTED_PROVIDERS,
            WEB_SEARCH_SETTINGS_KEY,
        )

        if (
            tool_key == WEB_SEARCH_SETTINGS_KEY
            and settings["provider"] not in SUPPORTED_PROVIDERS
        ):
            return payload_cls(
                ok=False,
                message=(
                    f"Unsupported provider '{settings['provider']}'. "
                    f"Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
                ),
                tools_with_secrets=None,
            )

    try:
        ps = PipelineSettings.get_instance()

        if not merge:
            # Replace mode: wipe all existing secrets AND settings for this
            # tool key before writing the new values.  This guarantees that
            # stale keys from a previous provider configuration do not
            # linger in the encrypted store.
            ps.delete_tool_settings(tool_key)

        # Apply settings and secrets
        ps.update_tool_settings(
            tool_key,
            settings=settings or {},
            secrets=secrets,
        )
        ps.modified_by = user
        ps.save()

        logger.info(
            "Tool settings updated for '%s' by %s (has_secrets=%s, has_settings=%s, merge=%s)",
            tool_key,
            user.username,
            secrets is not None,
            settings is not None,
            merge,
        )

        return payload_cls(
            ok=True,
            message=f"Tool settings updated for '{tool_key}'.",
            tools_with_secrets=ps.get_tools_with_secrets(),
        )

    except ValueError as e:
        return payload_cls(
            ok=False,
            message=f"Failed to update tool settings: {e}",
            tools_with_secrets=None,
        )
    except Exception:
        logger.exception("Unexpected error updating tool settings for '%s'", tool_key)
        return payload_cls(
            ok=False,
            message="An unexpected error occurred.",
            tools_with_secrets=None,
        )


def m_update_tool_secrets(
    info: strawberry.Info,
    merge: Annotated[
        bool | None,
        strawberry.argument(
            name="merge", description="If True, merge with existing. If False, replace."
        ),
    ] = True,
    secrets: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="secrets",
            description="Dict of secret values to encrypt (e.g. api_key).",
        ),
    ] = None,
    settings: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="settings",
            description="Dict of non-sensitive settings (e.g. provider).",
        ),
    ] = None,
    tool_key: Annotated[
        str,
        strawberry.argument(
            name="toolKey", description='Tool identifier, e.g. "tool:web_search".'
        ),
    ] = strawberry.UNSET,
) -> UpdateToolSecretsMutation | None:
    kwargs = strip_unset(
        {"merge": merge, "secrets": secrets, "settings": settings, "tool_key": tool_key}
    )
    return _mutate_UpdateToolSecretsMutation(
        UpdateToolSecretsMutation, None, info, **kwargs
    )


def _mutate_DeleteToolSecretsMutation(payload_cls, root, info, tool_key):
    """PORT: /home/user/oc-graphene-ref/config/graphql/pipeline_settings_mutations.py:1416

    Port of DeleteToolSecretsMutation.mutate

    Delete all settings and secrets for a tool.
    """
    # @login_required + @graphql_ratelimit(WRITE_LIGHT) — inlined (see
    # _mutate_UpdatePipelineSettingsMutation).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    _write_light_rate_gate(root, info)

    from opencontractserver.constants.tools import TOOL_SETTINGS_PREFIX
    from opencontractserver.documents.models import PipelineSettings

    user = info.context.user

    if not user.is_superuser:
        return payload_cls(
            ok=False,
            message="Only superusers can delete tool secrets.",
            tools_with_secrets=None,
        )

    if not tool_key or not tool_key.startswith(TOOL_SETTINGS_PREFIX):
        return payload_cls(
            ok=False,
            message=f"Tool key must start with '{TOOL_SETTINGS_PREFIX}'.",
            tools_with_secrets=None,
        )

    try:
        ps = PipelineSettings.get_instance()
        ps.delete_tool_settings(tool_key)
        ps.modified_by = user
        ps.save()

        logger.info("Tool settings deleted for '%s' by %s", tool_key, user.username)

        return payload_cls(
            ok=True,
            message=f"Tool settings deleted for '{tool_key}'.",
            tools_with_secrets=ps.get_tools_with_secrets(),
        )

    except Exception:
        logger.exception("Unexpected error deleting tool settings for '%s'", tool_key)
        return payload_cls(
            ok=False,
            message="An unexpected error occurred.",
            tools_with_secrets=None,
        )


def m_delete_tool_secrets(
    info: strawberry.Info,
    tool_key: Annotated[
        str,
        strawberry.argument(
            name="toolKey", description='Tool identifier, e.g. "tool:web_search".'
        ),
    ] = strawberry.UNSET,
) -> DeleteToolSecretsMutation | None:
    kwargs = strip_unset({"tool_key": tool_key})
    return _mutate_DeleteToolSecretsMutation(
        DeleteToolSecretsMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "update_pipeline_settings": strawberry.field(
        resolver=m_update_pipeline_settings,
        name="updatePipelineSettings",
        description="Update the singleton pipeline settings.\n\nOnly superusers can modify these settings. Changes take effect immediately\nfor all new document processing tasks.\n\nArguments:\n    preferred_parsers: Dict mapping MIME types to parser class paths\n    preferred_embedders: Dict mapping MIME types to embedder class paths\n    preferred_thumbnailers: Dict mapping MIME types to thumbnailer class paths\n    preferred_enrichers: Dict mapping MIME types to ORDERED LISTS of enricher class paths\n    parser_kwargs: Dict mapping parser class paths to their configuration kwargs\n    component_settings: Dict mapping component class paths to settings overrides\n    default_embedder: Default embedder class path\n\nReturns:\n    ok: Whether the update succeeded\n    message: Status message\n    pipeline_settings: The updated settings",
    ),
    "reset_pipeline_settings": strawberry.field(
        resolver=m_reset_pipeline_settings,
        name="resetPipelineSettings",
        description="Reset pipeline settings to Django settings defaults.\n\nThis mutation resets all pipeline settings to their default values from\nDjango settings (PREFERRED_PARSERS, PREFERRED_EMBEDDERS, etc.).\n\nOnly superusers can perform this operation.",
    ),
    "update_component_secrets": strawberry.field(
        resolver=m_update_component_secrets,
        name="updateComponentSecrets",
        description="Update encrypted secrets for a specific pipeline component.\n\nThis mutation allows superusers to securely store API keys, tokens, and\nother credentials for pipeline components. The secrets are encrypted at\nrest using Fernet symmetric encryption.\n\nOnly superusers can perform this operation.\n\nArguments:\n    component_path: Full class path of the component (e.g.,\n        'opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser')\n    secrets: Dict of secret key-value pairs to store (e.g., {'api_key': '...'})\n    merge: If True, merge with existing secrets. If False, replace all secrets\n        for this component. Default: True\n\nReturns:\n    ok: Whether the update succeeded\n    message: Status message\n    components_with_secrets: List of component paths that have secrets stored",
    ),
    "delete_component_secrets": strawberry.field(
        resolver=m_delete_component_secrets,
        name="deleteComponentSecrets",
        description="Delete all encrypted secrets for a specific pipeline component.\n\nOnly superusers can perform this operation.\n\nArguments:\n    component_path: Full class path of the component\n\nReturns:\n    ok: Whether the deletion succeeded\n    message: Status message\n    components_with_secrets: Updated list of component paths that have secrets",
    ),
    "update_tool_secrets": strawberry.field(
        resolver=m_update_tool_secrets,
        name="updateToolSecrets",
        description='Update encrypted secrets for an agent tool (e.g. web search API keys).\n\nTool secrets are stored in PipelineSettings alongside component secrets,\nunder a ``tool:`` namespace prefix. Only superusers can perform this.\n\nArguments:\n    tool_key: Tool identifier, e.g. ``"tool:web_search"``\n    secrets: Dict of secret key-value pairs, e.g. ``{"api_key": "..."}``\n    settings: Optional non-sensitive settings, e.g. ``{"provider": "brave"}``\n    merge: If True (default), merge with existing; if False, replace.',
    ),
    "delete_tool_secrets": strawberry.field(
        resolver=m_delete_tool_secrets,
        name="deleteToolSecrets",
        description="Delete all settings and secrets for an agent tool.\n\nOnly superusers can perform this operation.",
    ),
}
