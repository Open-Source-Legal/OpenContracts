"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums




@strawberry.type(name="PipelineComponentsType", description='Graphene type for grouping pipeline components.')
class PipelineComponentsType:
    @strawberry.field(name="parsers", description='List of available parsers.')
    def parsers(self, info: strawberry.Info) -> Optional[list[Optional["PipelineComponentType"]]]:
        return resolve_django_list(self, info, getattr(self, "parsers"), "PipelineComponentType")
    @strawberry.field(name="embedders", description='List of available embedders.')
    def embedders(self, info: strawberry.Info) -> Optional[list[Optional["PipelineComponentType"]]]:
        return resolve_django_list(self, info, getattr(self, "embedders"), "PipelineComponentType")
    @strawberry.field(name="thumbnailers", description='List of available thumbnail generators.')
    def thumbnailers(self, info: strawberry.Info) -> Optional[list[Optional["PipelineComponentType"]]]:
        return resolve_django_list(self, info, getattr(self, "thumbnailers"), "PipelineComponentType")
    @strawberry.field(name="postProcessors", description='List of available post-processors.')
    def post_processors(self, info: strawberry.Info) -> Optional[list[Optional["PipelineComponentType"]]]:
        return resolve_django_list(self, info, getattr(self, "post_processors"), "PipelineComponentType")
    @strawberry.field(name="rerankers", description='List of available post-retrieval rerankers.')
    def rerankers(self, info: strawberry.Info) -> Optional[list[Optional["PipelineComponentType"]]]:
        return resolve_django_list(self, info, getattr(self, "rerankers"), "PipelineComponentType")
    @strawberry.field(name="enrichers", description='List of available document enrichers (run between parsing and persistence).')
    def enrichers(self, info: strawberry.Info) -> Optional[list[Optional["PipelineComponentType"]]]:
        return resolve_django_list(self, info, getattr(self, "enrichers"), "PipelineComponentType")
    @strawberry.field(name="llmProviders", description='List of available LLM providers (pydantic-ai model families) that can be set as Corpus.preferred_llm or AgentConfiguration.preferred_llm.')
    def llm_providers(self, info: strawberry.Info) -> Optional[list[Optional["PipelineComponentType"]]]:
        return resolve_django_list(self, info, getattr(self, "llm_providers"), "PipelineComponentType")
    @strawberry.field(name="fileConverters", description='List of available pre-parse file converters (convert non-native upload formats to PDF before parsing).')
    def file_converters(self, info: strawberry.Info) -> Optional[list[Optional["PipelineComponentType"]]]:
        return resolve_django_list(self, info, getattr(self, "file_converters"), "PipelineComponentType")


register_type("PipelineComponentsType", PipelineComponentsType, model=None)


@strawberry.type(name="PipelineComponentType", description='Graphene type for pipeline components.')
class PipelineComponentType:
    @strawberry.field(name="name", description='Name of the component class.')
    def name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="className", description='Full Python path to the component class.')
    def class_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "class_name", None))
    @strawberry.field(name="moduleName", description='Name of the module the component is in.')
    def module_name(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "module_name", None))
    @strawberry.field(name="title", description='Title of the component.')
    def title(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "title", None))
    @strawberry.field(name="description", description='Description of the component.')
    def description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "description", None))
    @strawberry.field(name="author", description='Author of the component.')
    def author(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "author", None))
    @strawberry.field(name="dependencies", description='List of dependencies required by the component.')
    def dependencies(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "dependencies", None))
    vector_size: Optional[int] = strawberry.field(name="vectorSize", description='Vector size for embedders.')
    @strawberry.field(name="supportedFileTypes", description='List of supported file types.')
    def supported_file_types(self, info: strawberry.Info) -> Optional[list[Optional[enums.FileTypeEnum]]]:
        return coerce_enum(enums.FileTypeEnum, getattr(self, "supported_file_types", None))
    @strawberry.field(name="supportedExtensions", description='File converters: source-file extensions the converter can turn into PDF (plain strings, since converters target formats with no FileTypeEnum member). Empty for other component types.')
    def supported_extensions(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "supported_extensions", None))
    @strawberry.field(name="componentType", description='Type of the component (parser, embedder, or thumbnailer).')
    def component_type(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "component_type", None))
    input_schema: Optional[GenericScalar] = strawberry.field(name="inputSchema", description='JSONSchema schema for inputs supported from user (experimental - not fully implemented).')
    @strawberry.field(name="settingsSchema", description='Schema for component configuration settings stored in PipelineSettings.')
    def settings_schema(self, info: strawberry.Info) -> Optional[list[Optional["ComponentSettingSchemaType"]]]:
        return resolve_django_list(self, info, getattr(self, "settings_schema"), "ComponentSettingSchemaType")
    is_multimodal: Optional[bool] = strawberry.field(name="isMultimodal", description='Whether this embedder supports multiple modalities (text + images).')
    supports_text: Optional[bool] = strawberry.field(name="supportsText", description='Whether this embedder supports text input.')
    supports_images: Optional[bool] = strawberry.field(name="supportsImages", description='Whether this embedder supports image input.')
    @strawberry.field(name="providerKey", description="LLM providers: pydantic-ai prefix (e.g. 'anthropic'). Null for other component types.")
    def provider_key(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "provider_key", None))
    @strawberry.field(name="supportedModels", description='LLM providers: suggested bare model names exposed to the UI. Empty for other component types.')
    def supported_models(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "supported_models", None))
    requires_api_key: Optional[bool] = strawberry.field(name="requiresApiKey", description='LLM providers: whether the provider needs an API credential.')
    enabled: bool = strawberry.field(name="enabled", description='Whether this component is enabled for use in pipeline configuration.')


register_type("PipelineComponentType", PipelineComponentType, model=None)


@strawberry.type(name="ComponentSettingSchemaType", description='Schema for a single pipeline component setting.\n\nDescribes a configuration option that can be set in PipelineSettings\nfor a specific component.')
class ComponentSettingSchemaType:
    @strawberry.field(name="name", description='Setting name (used as key in component_settings dict).')
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))
    @strawberry.field(name="settingType", description="Type: 'required', 'optional', or 'secret'.")
    def setting_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "setting_type", None))
    @strawberry.field(name="pythonType", description="Python type hint (e.g., 'str', 'int', 'bool').")
    def python_type(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "python_type", None))
    required: bool = strawberry.field(name="required", description='Whether this setting must have a value for the component to work.')
    @strawberry.field(name="description", description='Human-readable description of the setting.')
    def description(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "description", None))
    default: Optional[GenericScalar] = strawberry.field(name="default", description='Default value if not configured.')
    @strawberry.field(name="envVar", description='Environment variable name used during migration seeding.')
    def env_var(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "env_var", None))
    has_value: Optional[bool] = strawberry.field(name="hasValue", description='Whether this setting currently has a value configured.')
    current_value: Optional[GenericScalar] = strawberry.field(name="currentValue", description='Current value (always null for secrets to avoid exposure).')


register_type("ComponentSettingSchemaType", ComponentSettingSchemaType, model=None)


@strawberry.type(name="SupportedMimeTypeType", description="Information about a MIME type's support level in the pipeline.\n\nDerived dynamically from registered pipeline components.")
class SupportedMimeTypeType:
    @strawberry.field(name="mimetype", description="Canonical MIME type string (e.g. 'application/pdf').")
    def mimetype(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "mimetype", None))
    @strawberry.field(name="fileType", description="Short file type label (e.g. 'pdf').")
    def file_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "file_type", None))
    @strawberry.field(name="label", description="Human-readable label (e.g. 'PDF').")
    def label(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "label", None))
    fully_supported: bool = strawberry.field(name="fullySupported", description='Whether the required pipeline stages (parser and embedder) have at least one component for this file type. Thumbnailer is optional — file types without one are still uploadable.')
    stage_coverage: "StageCoverageType" = strawberry.field(name="stageCoverage", description='Per-stage availability for this file type.')


register_type("SupportedMimeTypeType", SupportedMimeTypeType, model=None)


@strawberry.type(name="StageCoverageType", description='Coverage of pipeline stages for a given file type.')
class StageCoverageType:
    parser: bool = strawberry.field(name="parser", description='Whether at least one parser supports this file type.')
    embedder: bool = strawberry.field(name="embedder", description='GLOBAL flag: True when at least one text embedder is registered anywhere in the pipeline — does NOT indicate per-file-type coverage. All current embedders operate on extracted text regardless of source format, so this value is identical across all file types. Do not use this field to determine whether a specific MIME type can be embedded.')
    thumbnailer: bool = strawberry.field(name="thumbnailer", description='Whether at least one thumbnailer supports this file type.')


register_type("StageCoverageType", StageCoverageType, model=None)


@strawberry.type(name="PipelineSettingsType", description='GraphQL type for PipelineSettings singleton.\n\nExposes the runtime-configurable document processing pipeline settings.\nOnly superusers can modify these settings via mutation.')
class PipelineSettingsType:
    preferred_parsers: Optional[GenericScalar] = strawberry.field(name="preferredParsers", description='Mapping of MIME types to preferred parser class paths')
    preferred_embedders: Optional[GenericScalar] = strawberry.field(name="preferredEmbedders", description='Mapping of MIME types to preferred embedder class paths. API-only (issue #2114): has no effect at ingest, which always resolves the single global default_embedder to keep the cross-corpus vector index on one embedding space.')
    preferred_thumbnailers: Optional[GenericScalar] = strawberry.field(name="preferredThumbnailers", description='Mapping of MIME types to preferred thumbnailer class paths')
    preferred_enrichers: Optional[GenericScalar] = strawberry.field(name="preferredEnrichers", description='Mapping of MIME types to ORDERED LISTS of preferred enricher class paths (the enrichment chain run between parsing and persistence).')
    parser_kwargs: Optional[GenericScalar] = strawberry.field(name="parserKwargs", description='Mapping of parser class paths to their configuration kwargs')
    component_settings: Optional[GenericScalar] = strawberry.field(name="componentSettings", description='Mapping of component class paths to settings overrides')
    @strawberry.field(name="defaultEmbedder", description='Default embedder class path used for all ingest embedding. There is no MIME-specific override; see preferred_embedders.')
    def default_embedder(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "default_embedder", None))
    @strawberry.field(name="defaultReranker", description='Default post-retrieval reranker class path. Empty string means reranking is disabled and first-stage retrieval results are returned as-is.')
    def default_reranker(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "default_reranker", None))
    @strawberry.field(name="defaultFileConverter", description='File converter class path used to convert non-native upload formats to PDF before parsing. Empty string disables the conversion step.')
    def default_file_converter(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "default_file_converter", None))
    @strawberry.field(name="defaultLlm", description="Install-wide default LLM model spec (pydantic-ai '{provider}:{model}' form, e.g. 'anthropic:claude-opus-4-6') used by agents when no per-corpus or per-agent override is set. Empty string means the Django settings default is used.")
    def default_llm(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "default_llm", None))
    @strawberry.field(name="componentsWithSecrets", description='List of component paths that have encrypted secrets configured. Actual secret values are never exposed via GraphQL.')
    def components_with_secrets(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "components_with_secrets", None))
    @strawberry.field(name="toolsWithSecrets", description="List of tool keys (e.g. 'tool:web_search') that have encrypted secrets configured. Actual secret values are never exposed.")
    def tools_with_secrets(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "tools_with_secrets", None))
    @strawberry.field(name="enabledComponents", description='List of enabled component class paths. Empty means all enabled.')
    def enabled_components(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "enabled_components", None))
    modified: Optional[datetime.datetime] = strawberry.field(name="modified", description='When these settings were last modified')
    modified_by: Optional[Annotated["UserType", strawberry.lazy("config.graphql_new.user_types")]] = strawberry.field(name="modifiedBy", description='User who last modified these settings')


register_type("PipelineSettingsType", PipelineSettingsType, model=None)

