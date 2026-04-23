"""GraphQL type definitions for pipeline-related types."""

import graphene
from graphene.types.generic import GenericScalar

from config.graphql.user_types import UserType
from opencontractserver.pipeline.base.file_types import (
    FileTypeEnum as BackendFileTypeEnum,
)


class FileTypeEnum(graphene.Enum):
    """Graphene enum for FileTypeEnum."""

    PDF = BackendFileTypeEnum.PDF.value
    TXT = BackendFileTypeEnum.TXT.value
    DOCX = BackendFileTypeEnum.DOCX.value
    # HTML has been removed as we don't support it


class ComponentSettingSchemaType(graphene.ObjectType):
    """
    Schema for a single pipeline component setting.

    Describes a configuration option that can be set in PipelineSettings
    for a specific component.
    """

    name = graphene.String(
        required=True,
        description="Setting name (used as key in component_settings dict).",
    )
    setting_type = graphene.String(
        required=True, description="Type: 'required', 'optional', or 'secret'."
    )
    python_type = graphene.String(
        description="Python type hint (e.g., 'str', 'int', 'bool')."
    )
    required = graphene.Boolean(
        required=True,
        description="Whether this setting must have a value for the component to work.",
    )
    description = graphene.String(
        description="Human-readable description of the setting."
    )
    default = GenericScalar(description="Default value if not configured.")
    env_var = graphene.String(
        description="Environment variable name used during migration seeding."
    )
    has_value = graphene.Boolean(
        description="Whether this setting currently has a value configured."
    )
    current_value = GenericScalar(
        description="Current value (always null for secrets to avoid exposure)."
    )


class PipelineComponentType(graphene.ObjectType):
    """Graphene type for pipeline components."""

    name = graphene.String(description="Name of the component class.")
    class_name = graphene.String(description="Full Python path to the component class.")
    module_name = graphene.String(description="Name of the module the component is in.")
    title = graphene.String(description="Title of the component.")
    description = graphene.String(description="Description of the component.")
    author = graphene.String(description="Author of the component.")
    dependencies = graphene.List(
        graphene.String, description="List of dependencies required by the component."
    )
    vector_size = graphene.Int(description="Vector size for embedders.", required=False)
    supported_file_types = graphene.List(
        FileTypeEnum, description="List of supported file types."
    )
    component_type = graphene.String(
        description="Type of the component (parser, embedder, or thumbnailer)."
    )
    input_schema = GenericScalar(
        description="JSONSchema schema for inputs supported from user (experimental - not fully implemented)."
    )
    settings_schema = graphene.List(
        ComponentSettingSchemaType,
        description="Schema for component configuration settings stored in PipelineSettings.",
    )
    # Multimodal support flags (for embedders)
    is_multimodal = graphene.Boolean(
        description="Whether this embedder supports multiple modalities (text + images).",
        required=False,
    )
    supports_text = graphene.Boolean(
        description="Whether this embedder supports text input.", required=False
    )
    supports_images = graphene.Boolean(
        description="Whether this embedder supports image input.", required=False
    )
    enabled = graphene.Boolean(
        description="Whether this component is enabled for use in pipeline configuration.",
        required=True,
    )


class PipelineComponentsType(graphene.ObjectType):
    """Graphene type for grouping pipeline components."""

    parsers = graphene.List(
        PipelineComponentType, description="List of available parsers."
    )
    embedders = graphene.List(
        PipelineComponentType, description="List of available embedders."
    )
    thumbnailers = graphene.List(
        PipelineComponentType, description="List of available thumbnail generators."
    )
    post_processors = graphene.List(
        PipelineComponentType, description="List of available post-processors."
    )
    rerankers = graphene.List(
        PipelineComponentType,
        description="List of available post-retrieval rerankers.",
    )


# ==============================================================================
# PIPELINE SETTINGS TYPES (Runtime-configurable document processing settings)
# ==============================================================================


class StageCoverageType(graphene.ObjectType):
    """Coverage of pipeline stages for a given file type."""

    parser = graphene.Boolean(
        required=True,
        description="Whether at least one parser supports this file type.",
    )
    embedder = graphene.Boolean(
        required=True,
        description="GLOBAL flag: True when at least one text embedder is registered "
        "anywhere in the pipeline — does NOT indicate per-file-type coverage. "
        "All current embedders operate on extracted text regardless of source "
        "format, so this value is identical across all file types. Do not use "
        "this field to determine whether a specific MIME type can be embedded.",
    )
    thumbnailer = graphene.Boolean(
        required=True,
        description="Whether at least one thumbnailer supports this file type.",
    )


class SupportedMimeTypeType(graphene.ObjectType):
    """
    Information about a MIME type's support level in the pipeline.

    Derived dynamically from registered pipeline components.
    """

    mimetype = graphene.String(
        required=True,
        description="Canonical MIME type string (e.g. 'application/pdf').",
    )
    file_type = graphene.String(
        required=True, description="Short file type label (e.g. 'pdf')."
    )
    label = graphene.String(
        required=True, description="Human-readable label (e.g. 'PDF')."
    )
    fully_supported = graphene.Boolean(
        required=True,
        description="Whether the required pipeline stages (parser and embedder) "
        "have at least one component for this file type. "
        "Thumbnailer is optional — file types without one are still uploadable.",
    )
    stage_coverage = graphene.Field(
        StageCoverageType,
        required=True,
        description="Per-stage availability for this file type.",
    )


class PipelineSettingsType(graphene.ObjectType):
    """
    GraphQL type for PipelineSettings singleton.

    Exposes the runtime-configurable document processing pipeline settings.
    Only superusers can modify these settings via mutation.
    """

    # Preferred components per MIME type
    preferred_parsers = GenericScalar(
        description="Mapping of MIME types to preferred parser class paths"
    )
    preferred_embedders = GenericScalar(
        description="Mapping of MIME types to preferred embedder class paths"
    )
    preferred_thumbnailers = GenericScalar(
        description="Mapping of MIME types to preferred thumbnailer class paths"
    )

    # Component configuration
    parser_kwargs = GenericScalar(
        description="Mapping of parser class paths to their configuration kwargs"
    )
    component_settings = GenericScalar(
        description="Mapping of component class paths to settings overrides"
    )

    # Default embedder
    default_embedder = graphene.String(
        description="Default embedder class path when no MIME-specific embedder is found"
    )

    # Default reranker (post-retrieval). Empty string means reranking disabled.
    default_reranker = graphene.String(
        description="Default post-retrieval reranker class path. Empty string "
        "means reranking is disabled and first-stage retrieval "
        "results are returned as-is.",
        required=False,
    )

    # Secrets indicator (actual secrets are never exposed via GraphQL)
    components_with_secrets = graphene.List(
        graphene.String,
        description="List of component paths that have encrypted secrets configured. "
        "Actual secret values are never exposed via GraphQL.",
    )

    # Tool secrets indicator
    tools_with_secrets = graphene.List(
        graphene.String,
        description="List of tool keys (e.g. 'tool:web_search') that have encrypted "
        "secrets configured. Actual secret values are never exposed.",
    )

    # Enabled components filter
    enabled_components = graphene.List(
        graphene.String,
        description="List of enabled component class paths. Empty means all enabled.",
    )

    # Audit fields
    modified = graphene.DateTime(description="When these settings were last modified")
    modified_by = graphene.Field(
        UserType, description="User who last modified these settings"
    )
