"""
GraphQL query mixin for pipeline queries.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

import graphene
from graphql_jwt.decorators import login_required

from config.graphql.graphene_types import (
    ComponentSettingSchemaType,
    FileTypeEnum,
    PipelineComponentsType,
    PipelineComponentType,
    PipelineSettingsType,
    StageCoverageType,
    SupportedMimeTypeType,
)
from opencontractserver.pipeline.base.file_types import FILE_TYPE_TO_MIME
from opencontractserver.pipeline.registry import (
    PipelineComponentDefinition,
    get_all_components_cached,
    get_components_by_mimetype_cached,
    get_supported_mime_types,
)

logger = logging.getLogger(__name__)


class PipelineQueryMixin:
    """Query fields and resolvers for pipeline component and settings queries."""

    # PIPELINE COMPONENT RESOLVERS #####################################
    pipeline_components = graphene.Field(
        PipelineComponentsType,
        mimetype=graphene.Argument(FileTypeEnum, required=False),
        description="Retrieve all registered pipeline components, optionally filtered by MIME type.",
    )

    @login_required
    def resolve_pipeline_components(
        self,
        info: graphene.ResolveInfo,
        mimetype: FileTypeEnum | None = None,
    ) -> PipelineComponentsType:
        """
        Resolver for the pipeline_components query.

        Uses cached registry for fast response times. The registry is
        initialized once on first access and cached permanently.

        Args:
            info: GraphQL execution info.
            mimetype (Optional[FileTypeEnum]): MIME type to filter pipeline components.

        Returns:
            PipelineComponentsType: The pipeline components grouped by type.
        """
        components_data: Mapping[str, Sequence[PipelineComponentDefinition]]
        if mimetype:
            mime_type_str = FILE_TYPE_TO_MIME.get(mimetype.value)
            if mime_type_str is None:
                components_data = {
                    "parsers": [],
                    "embedders": [],
                    "thumbnailers": [],
                    "post_processors": [],
                }
            else:
                # Get compatible components from cached registry
                components_data = get_components_by_mimetype_cached(mime_type_str)
            # MIME-filtered queries do not return LLM providers or file
            # converters (neither is file-type-scoped — converters are keyed
            # by source-file EXTENSION), so we leave them out of the response
            # to keep the contract explicit.
            llm_providers_data: Sequence[PipelineComponentDefinition] = ()
            file_converters_data: Sequence[PipelineComponentDefinition] = ()
        else:
            # Get all components from cached registry
            components_data = get_all_components_cached()
            llm_providers_data = components_data.get("llm_providers", ())
            file_converters_data = components_data.get("file_converters", ())

        user = info.context.user

        # Get PipelineSettings instance for configured component filtering
        from opencontractserver.documents.models import PipelineSettings

        settings_instance = PipelineSettings.get_instance()

        if not user.is_superuser:
            configured_components: set[str] = set()

            preferred_parsers = settings_instance.preferred_parsers or {}
            preferred_embedders = settings_instance.preferred_embedders or {}
            preferred_thumbnailers = settings_instance.preferred_thumbnailers or {}
            preferred_enrichers = settings_instance.preferred_enrichers or {}

            configured_components.update(preferred_parsers.values())
            configured_components.update(preferred_embedders.values())
            configured_components.update(preferred_thumbnailers.values())
            for mimetype_key, enricher_list in preferred_enrichers.items():
                if isinstance(enricher_list, list):
                    configured_components.update(enricher_list)
                else:
                    # Mirror PipelineSettings.get_preferred_enrichers()'s
                    # defensive guard: a misconfigured non-list value (e.g. a
                    # bare string or None from a shell/migration edit that
                    # bypassed validate_enricher_mapping()) would otherwise
                    # raise (None) or character-split a string via
                    # set.update() -- ignore it rather than crash the query.
                    logger.warning(
                        "PipelineSettings.preferred_enrichers[%r] is %s, not a "
                        "list; ignoring for component visibility filtering.",
                        mimetype_key,
                        type(enricher_list).__name__,
                    )

            if settings_instance.default_embedder:
                configured_components.add(settings_instance.default_embedder)

            if settings_instance.default_reranker:
                configured_components.add(settings_instance.default_reranker)

            if settings_instance.default_file_converter:
                configured_components.add(settings_instance.default_file_converter)

            if settings_instance.parser_kwargs:
                configured_components.update(settings_instance.parser_kwargs.keys())

            if settings_instance.component_settings:
                configured_components.update(
                    settings_instance.component_settings.keys()
                )

            def filter_configured(
                definitions: Sequence[PipelineComponentDefinition],
            ) -> list[PipelineComponentDefinition]:
                return [
                    defn
                    for defn in definitions
                    if defn.class_name in configured_components
                ]

            components_data = {
                "parsers": filter_configured(components_data["parsers"]),
                "embedders": filter_configured(components_data["embedders"]),
                "thumbnailers": filter_configured(components_data["thumbnailers"]),
                "post_processors": filter_configured(
                    components_data["post_processors"]
                ),
                "rerankers": filter_configured(components_data.get("rerankers", [])),
                "enrichers": filter_configured(components_data.get("enrichers", [])),
            }
            file_converters_data = filter_configured(list(file_converters_data))

        # Convert PipelineComponentDefinition objects to GraphQL types
        enabled_set = set(settings_instance.enabled_components or [])

        def to_graphql_type(
            defn: PipelineComponentDefinition, component_type: str
        ) -> PipelineComponentType:
            is_enabled = (not enabled_set) or (defn.class_name in enabled_set)
            settings_schema: list[ComponentSettingSchemaType] | None = None
            if user.is_superuser:
                # Get schema augmented with has_value/current_value from DB
                augmented_schema = settings_instance.get_component_schema(
                    defn.class_name
                )
                if augmented_schema:
                    settings_schema = [
                        ComponentSettingSchemaType(
                            name=name,
                            setting_type=info.get("type", "optional"),
                            python_type=info.get("python_type"),
                            required=info.get("required", False),
                            description=info.get("description", ""),
                            default=info.get("default"),
                            env_var=info.get("env_var"),
                            has_value=info.get("has_value", False),
                            current_value=info.get("current_value"),
                        )
                        for name, info in augmented_schema.items()
                    ]

            component_info = PipelineComponentType(
                name=defn.name,
                class_name=defn.class_name,
                title=defn.title,
                module_name=defn.module_name,
                description=defn.description,
                author=defn.author,
                dependencies=list(defn.dependencies),
                supported_file_types=list(defn.supported_file_types),
                supported_extensions=list(defn.supported_extensions),
                component_type=component_type,
                input_schema=defn.input_schema,
                settings_schema=settings_schema,
                enabled=is_enabled,
            )
            if defn.vector_size is not None:
                component_info.vector_size = defn.vector_size
            # LLM-provider routing fields (set only for LLM providers).
            if defn.provider_key:
                component_info.provider_key = defn.provider_key
                component_info.supported_models = list(defn.supported_models)
                component_info.requires_api_key = defn.requires_api_key
            return component_info

        return PipelineComponentsType(
            parsers=[to_graphql_type(d, "parser") for d in components_data["parsers"]],
            embedders=[
                to_graphql_type(d, "embedder") for d in components_data["embedders"]
            ],
            thumbnailers=[
                to_graphql_type(d, "thumbnailer")
                for d in components_data["thumbnailers"]
            ],
            post_processors=[
                to_graphql_type(d, "post_processor")
                for d in components_data["post_processors"]
            ],
            rerankers=[
                to_graphql_type(d, "reranker")
                for d in components_data.get("rerankers", [])
            ],
            enrichers=[
                to_graphql_type(d, "enricher")
                for d in components_data.get("enrichers", [])
            ],
            llm_providers=[
                # LLM providers are intentionally NOT run through
                # ``filter_configured`` for non-superusers: a corpus editor must
                # see every registered provider to choose one for
                # ``Corpus.preferred_llm`` (via the per-corpus model picker). No
                # credentials leak — ``settings_schema`` (has_value/current_value)
                # is built only for superusers in ``to_graphql_type`` above.
                to_graphql_type(d, "llm_provider")
                for d in llm_providers_data
            ],
            file_converters=[
                to_graphql_type(d, "file_converter") for d in file_converters_data
            ],
        )

    # SUPPORTED MIME TYPES #####################################
    supported_mime_types = graphene.List(
        SupportedMimeTypeType,
        description="Dynamically derived list of MIME types supported by registered "
        "pipeline components. Each entry indicates per-stage availability "
        "(parser, embedder, thumbnailer) and whether required stages "
        "(parser and embedder) are covered.",
    )

    def resolve_supported_mime_types(
        self, info: graphene.ResolveInfo
    ) -> list[SupportedMimeTypeType]:
        """
        Resolver for the supported_mime_types query.

        Derives supported file types from the pipeline component registry
        rather than static configuration. Available to anonymous users so
        that uploaders/landing pages can advertise accepted file formats
        without requiring login.
        """
        entries = get_supported_mime_types()
        return [
            SupportedMimeTypeType(
                mimetype=entry["mimetype"],
                file_type=entry["file_type"],
                label=entry["label"],
                fully_supported=entry["fully_supported"],
                stage_coverage=StageCoverageType(
                    parser=entry["stage_coverage"]["parser"],
                    embedder=entry["stage_coverage"]["embedder"],
                    thumbnailer=entry["stage_coverage"]["thumbnailer"],
                ),
            )
            for entry in entries
        ]

    # CONVERTIBLE EXTENSIONS ###################################
    convertible_extensions = graphene.List(
        graphene.String,
        description="File extensions the configured pre-parse file converter "
        "will convert to PDF. Empty when no converter is configured. "
        "Upload UIs merge these into the accepted-format set alongside "
        "supported_mime_types.",
    )

    def resolve_convertible_extensions(self, info: graphene.ResolveInfo) -> list[str]:
        """
        Resolver for the convertible_extensions query.

        Like supported_mime_types, available to anonymous users so uploaders
        and landing pages can advertise accepted file formats without login.
        """
        from opencontractserver.pipeline.utils import get_convertible_extensions

        return sorted(get_convertible_extensions())

    # PIPELINE SETTINGS ########################################
    pipeline_settings = graphene.Field(
        "config.graphql.graphene_types.PipelineSettingsType",
        description="Retrieve the singleton pipeline settings for document processing configuration.",
    )

    @login_required
    def resolve_pipeline_settings(
        self, info: graphene.ResolveInfo
    ) -> PipelineSettingsType:
        """
        Resolve the singleton PipelineSettings instance.

        This query returns the runtime-configurable document processing settings.
        Any authenticated user can read these settings, but only superusers can
        modify them via the UpdatePipelineSettings mutation.

        Returns:
            PipelineSettingsType: The singleton pipeline settings.
        """
        from opencontractserver.documents.models import PipelineSettings

        settings_instance = PipelineSettings.get_instance()

        # Get list of components that have secrets (don't expose actual secrets)
        components_with_secrets = settings_instance.get_components_with_secrets()

        return PipelineSettingsType(
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
            components_with_secrets=components_with_secrets,
            tools_with_secrets=settings_instance.get_tools_with_secrets(),
            enabled_components=settings_instance.enabled_components or [],
            modified=settings_instance.modified,
            modified_by=settings_instance.modified_by,
        )
