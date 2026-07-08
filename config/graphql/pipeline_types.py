"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

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

import datetime
from typing import Annotated, Optional

import strawberry

from config.graphql import enums
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar


@strawberry.type(
    name="PipelineComponentsType",
    description="Graphene type for grouping pipeline components.",
)
class PipelineComponentsType:
    parsers: Optional[list[Optional["PipelineComponentType"]]] = strawberry.field(
        name="parsers", description="List of available parsers.", default=None
    )
    embedders: Optional[list[Optional["PipelineComponentType"]]] = strawberry.field(
        name="embedders", description="List of available embedders.", default=None
    )
    thumbnailers: Optional[list[Optional["PipelineComponentType"]]] = strawberry.field(
        name="thumbnailers",
        description="List of available thumbnail generators.",
        default=None,
    )
    post_processors: Optional[list[Optional["PipelineComponentType"]]] = (
        strawberry.field(
            name="postProcessors",
            description="List of available post-processors.",
            default=None,
        )
    )
    rerankers: Optional[list[Optional["PipelineComponentType"]]] = strawberry.field(
        name="rerankers",
        description="List of available post-retrieval rerankers.",
        default=None,
    )
    enrichers: Optional[list[Optional["PipelineComponentType"]]] = strawberry.field(
        name="enrichers",
        description="List of available document enrichers (run between parsing and persistence).",
        default=None,
    )
    llm_providers: Optional[list[Optional["PipelineComponentType"]]] = strawberry.field(
        name="llmProviders",
        description="List of available LLM providers (pydantic-ai model families) that can be set as Corpus.preferred_llm or AgentConfiguration.preferred_llm.",
        default=None,
    )
    file_converters: Optional[list[Optional["PipelineComponentType"]]] = (
        strawberry.field(
            name="fileConverters",
            description="List of available pre-parse file converters (convert non-native upload formats to PDF before parsing).",
            default=None,
        )
    )


register_type("PipelineComponentsType", PipelineComponentsType, model=None)


@strawberry.type(
    name="PipelineComponentType", description="Graphene type for pipeline components."
)
class PipelineComponentType:
    name: Optional[str] = strawberry.field(
        name="name", description="Name of the component class.", default=None
    )
    class_name: Optional[str] = strawberry.field(
        name="className",
        description="Full Python path to the component class.",
        default=None,
    )
    module_name: Optional[str] = strawberry.field(
        name="moduleName",
        description="Name of the module the component is in.",
        default=None,
    )
    title: Optional[str] = strawberry.field(
        name="title", description="Title of the component.", default=None
    )
    description: Optional[str] = strawberry.field(
        name="description", description="Description of the component.", default=None
    )
    author: Optional[str] = strawberry.field(
        name="author", description="Author of the component.", default=None
    )
    dependencies: Optional[list[Optional[str]]] = strawberry.field(
        name="dependencies",
        description="List of dependencies required by the component.",
        default=None,
    )
    vector_size: Optional[int] = strawberry.field(
        name="vectorSize", description="Vector size for embedders.", default=None
    )
    supported_file_types: Optional[list[Optional[enums.FileTypeEnum]]] = (
        strawberry.field(
            name="supportedFileTypes",
            description="List of supported file types.",
            default=None,
        )
    )
    supported_extensions: Optional[list[Optional[str]]] = strawberry.field(
        name="supportedExtensions",
        description="File converters: source-file extensions the converter can turn into PDF (plain strings, since converters target formats with no FileTypeEnum member). Empty for other component types.",
        default=None,
    )
    component_type: Optional[str] = strawberry.field(
        name="componentType",
        description="Type of the component (parser, embedder, or thumbnailer).",
        default=None,
    )
    input_schema: Optional[GenericScalar] = strawberry.field(
        name="inputSchema",
        description="JSONSchema schema for inputs supported from user (experimental - not fully implemented).",
        default=None,
    )
    settings_schema: Optional[list[Optional["ComponentSettingSchemaType"]]] = (
        strawberry.field(
            name="settingsSchema",
            description="Schema for component configuration settings stored in PipelineSettings.",
            default=None,
        )
    )
    is_multimodal: Optional[bool] = strawberry.field(
        name="isMultimodal",
        description="Whether this embedder supports multiple modalities (text + images).",
        default=None,
    )
    supports_text: Optional[bool] = strawberry.field(
        name="supportsText",
        description="Whether this embedder supports text input.",
        default=None,
    )
    supports_images: Optional[bool] = strawberry.field(
        name="supportsImages",
        description="Whether this embedder supports image input.",
        default=None,
    )
    provider_key: Optional[str] = strawberry.field(
        name="providerKey",
        description="LLM providers: pydantic-ai prefix (e.g. 'anthropic'). Null for other component types.",
        default=None,
    )
    supported_models: Optional[list[Optional[str]]] = strawberry.field(
        name="supportedModels",
        description="LLM providers: suggested bare model names exposed to the UI. Empty for other component types.",
        default=None,
    )
    requires_api_key: Optional[bool] = strawberry.field(
        name="requiresApiKey",
        description="LLM providers: whether the provider needs an API credential.",
        default=None,
    )
    enabled: bool = strawberry.field(
        name="enabled",
        description="Whether this component is enabled for use in pipeline configuration.",
        default=None,
    )


register_type("PipelineComponentType", PipelineComponentType, model=None)


@strawberry.type(
    name="ComponentSettingSchemaType",
    description="Schema for a single pipeline component setting.\n\nDescribes a configuration option that can be set in PipelineSettings\nfor a specific component.",
)
class ComponentSettingSchemaType:
    name: str = strawberry.field(
        name="name",
        description="Setting name (used as key in component_settings dict).",
        default=None,
    )
    setting_type: str = strawberry.field(
        name="settingType",
        description="Type: 'required', 'optional', or 'secret'.",
        default=None,
    )
    python_type: Optional[str] = strawberry.field(
        name="pythonType",
        description="Python type hint (e.g., 'str', 'int', 'bool').",
        default=None,
    )
    required: bool = strawberry.field(
        name="required",
        description="Whether this setting must have a value for the component to work.",
        default=None,
    )
    description: Optional[str] = strawberry.field(
        name="description",
        description="Human-readable description of the setting.",
        default=None,
    )
    default: Optional[GenericScalar] = strawberry.field(
        name="default", description="Default value if not configured.", default=None
    )
    env_var: Optional[str] = strawberry.field(
        name="envVar",
        description="Environment variable name used during migration seeding.",
        default=None,
    )
    has_value: Optional[bool] = strawberry.field(
        name="hasValue",
        description="Whether this setting currently has a value configured.",
        default=None,
    )
    current_value: Optional[GenericScalar] = strawberry.field(
        name="currentValue",
        description="Current value (always null for secrets to avoid exposure).",
        default=None,
    )


register_type("ComponentSettingSchemaType", ComponentSettingSchemaType, model=None)


@strawberry.type(
    name="SupportedMimeTypeType",
    description="Information about a MIME type's support level in the pipeline.\n\nDerived dynamically from registered pipeline components.",
)
class SupportedMimeTypeType:
    mimetype: str = strawberry.field(
        name="mimetype",
        description="Canonical MIME type string (e.g. 'application/pdf').",
        default=None,
    )
    file_type: str = strawberry.field(
        name="fileType", description="Short file type label (e.g. 'pdf').", default=None
    )
    label: str = strawberry.field(
        name="label", description="Human-readable label (e.g. 'PDF').", default=None
    )
    fully_supported: bool = strawberry.field(
        name="fullySupported",
        description="Whether the required pipeline stages (parser and embedder) have at least one component for this file type. Thumbnailer is optional — file types without one are still uploadable.",
        default=None,
    )
    stage_coverage: "StageCoverageType" = strawberry.field(
        name="stageCoverage",
        description="Per-stage availability for this file type.",
        default=None,
    )


register_type("SupportedMimeTypeType", SupportedMimeTypeType, model=None)


@strawberry.type(
    name="StageCoverageType",
    description="Coverage of pipeline stages for a given file type.",
)
class StageCoverageType:
    parser: bool = strawberry.field(
        name="parser",
        description="Whether at least one parser supports this file type.",
        default=None,
    )
    embedder: bool = strawberry.field(
        name="embedder",
        description="GLOBAL flag: True when at least one text embedder is registered anywhere in the pipeline — does NOT indicate per-file-type coverage. All current embedders operate on extracted text regardless of source format, so this value is identical across all file types. Do not use this field to determine whether a specific MIME type can be embedded.",
        default=None,
    )
    thumbnailer: bool = strawberry.field(
        name="thumbnailer",
        description="Whether at least one thumbnailer supports this file type.",
        default=None,
    )


register_type("StageCoverageType", StageCoverageType, model=None)


@strawberry.type(
    name="PipelineSettingsType",
    description="GraphQL type for PipelineSettings singleton.\n\nExposes the runtime-configurable document processing pipeline settings.\nOnly superusers can modify these settings via mutation.",
)
class PipelineSettingsType:
    preferred_parsers: Optional[GenericScalar] = strawberry.field(
        name="preferredParsers",
        description="Mapping of MIME types to preferred parser class paths",
        default=None,
    )
    preferred_embedders: Optional[GenericScalar] = strawberry.field(
        name="preferredEmbedders",
        description="Mapping of MIME types to preferred embedder class paths. API-only (issue #2114): has no effect at ingest, which always resolves the single global default_embedder to keep the cross-corpus vector index on one embedding space.",
        default=None,
    )
    preferred_thumbnailers: Optional[GenericScalar] = strawberry.field(
        name="preferredThumbnailers",
        description="Mapping of MIME types to preferred thumbnailer class paths",
        default=None,
    )
    preferred_enrichers: Optional[GenericScalar] = strawberry.field(
        name="preferredEnrichers",
        description="Mapping of MIME types to ORDERED LISTS of preferred enricher class paths (the enrichment chain run between parsing and persistence).",
        default=None,
    )
    parser_kwargs: Optional[GenericScalar] = strawberry.field(
        name="parserKwargs",
        description="Mapping of parser class paths to their configuration kwargs",
        default=None,
    )
    component_settings: Optional[GenericScalar] = strawberry.field(
        name="componentSettings",
        description="Mapping of component class paths to settings overrides",
        default=None,
    )
    default_embedder: Optional[str] = strawberry.field(
        name="defaultEmbedder",
        description="Default embedder class path used for all ingest embedding. There is no MIME-specific override; see preferred_embedders.",
        default=None,
    )
    default_reranker: Optional[str] = strawberry.field(
        name="defaultReranker",
        description="Default post-retrieval reranker class path. Empty string means reranking is disabled and first-stage retrieval results are returned as-is.",
        default=None,
    )
    default_file_converter: Optional[str] = strawberry.field(
        name="defaultFileConverter",
        description="File converter class path used to convert non-native upload formats to PDF before parsing. Empty string disables the conversion step.",
        default=None,
    )
    default_llm: Optional[str] = strawberry.field(
        name="defaultLlm",
        description="Install-wide default LLM model spec (pydantic-ai '{provider}:{model}' form, e.g. 'anthropic:claude-opus-4-6') used by agents when no per-corpus or per-agent override is set. Empty string means the Django settings default is used.",
        default=None,
    )
    components_with_secrets: Optional[list[Optional[str]]] = strawberry.field(
        name="componentsWithSecrets",
        description="List of component paths that have encrypted secrets configured. Actual secret values are never exposed via GraphQL.",
        default=None,
    )
    tools_with_secrets: Optional[list[Optional[str]]] = strawberry.field(
        name="toolsWithSecrets",
        description="List of tool keys (e.g. 'tool:web_search') that have encrypted secrets configured. Actual secret values are never exposed.",
        default=None,
    )
    enabled_components: Optional[list[Optional[str]]] = strawberry.field(
        name="enabledComponents",
        description="List of enabled component class paths. Empty means all enabled.",
        default=None,
    )
    modified: Optional[datetime.datetime] = strawberry.field(
        name="modified",
        description="When these settings were last modified",
        default=None,
    )
    modified_by: Optional[
        Annotated["UserType", strawberry.lazy("config.graphql.user_types")]
    ] = strawberry.field(
        name="modifiedBy",
        description="User who last modified these settings",
        default=None,
    )


register_type("PipelineSettingsType", PipelineSettingsType, model=None)
