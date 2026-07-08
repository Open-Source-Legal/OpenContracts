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
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums




def _resolve_Query_pipeline_components(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:43

    Port of PipelineQueryMixin.resolve_pipeline_components
    """
    raise NotImplementedError("_resolve_Query_pipeline_components not yet ported — see manifest")


def q_pipeline_components(info: strawberry.Info, mimetype: Annotated[Optional[enums.FileTypeEnum], strawberry.argument(name="mimetype")] = strawberry.UNSET) -> Optional[Annotated["PipelineComponentsType", strawberry.lazy("config.graphql.pipeline_types")]]:
    kwargs = strip_unset({"mimetype": mimetype})
    return _resolve_Query_pipeline_components(None, info, **kwargs)


def _resolve_Query_supported_mime_types(root, info, **kwargs):
    """PORT: config/graphql/pipeline_queries.py:258

    Port of PipelineQueryMixin.resolve_supported_mime_types
    """
    raise NotImplementedError("_resolve_Query_supported_mime_types not yet ported — see manifest")


def q_supported_mime_types(info: strawberry.Info) -> Optional[list[Optional[Annotated["SupportedMimeTypeType", strawberry.lazy("config.graphql.pipeline_types")]]]]:
    kwargs = strip_unset({})
    return _resolve_Query_supported_mime_types(None, info, **kwargs)


def _resolve_Query_convertible_extensions(root, info, **kwargs):
    """PORT: config/graphql/pipeline_queries.py:294

    Port of PipelineQueryMixin.resolve_convertible_extensions
    """
    raise NotImplementedError("_resolve_Query_convertible_extensions not yet ported — see manifest")


def q_convertible_extensions(info: strawberry.Info) -> Optional[list[Optional[str]]]:
    kwargs = strip_unset({})
    return _resolve_Query_convertible_extensions(None, info, **kwargs)


def _resolve_Query_pipeline_settings(root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:311

    Port of PipelineQueryMixin.resolve_pipeline_settings
    """
    raise NotImplementedError("_resolve_Query_pipeline_settings not yet ported — see manifest")


def q_pipeline_settings(info: strawberry.Info) -> Optional[Annotated["PipelineSettingsType", strawberry.lazy("config.graphql.pipeline_types")]]:
    kwargs = strip_unset({})
    return _resolve_Query_pipeline_settings(None, info, **kwargs)



QUERY_FIELDS = {
    "pipeline_components": strawberry.field(resolver=q_pipeline_components, name="pipelineComponents", description='Retrieve all registered pipeline components, optionally filtered by MIME type.'),
    "supported_mime_types": strawberry.field(resolver=q_supported_mime_types, name="supportedMimeTypes", description='Dynamically derived list of MIME types supported by registered pipeline components. Each entry indicates per-stage availability (parser, embedder, thumbnailer) and whether required stages (parser and embedder) are covered.'),
    "convertible_extensions": strawberry.field(resolver=q_convertible_extensions, name="convertibleExtensions", description='File extensions the configured pre-parse file converter will convert to PDF. Empty when no converter is configured. Upload UIs merge these into the accepted-format set alongside supported_mime_types.'),
    "pipeline_settings": strawberry.field(resolver=q_pipeline_settings, name="pipelineSettings", description='Retrieve the singleton pipeline settings for document processing configuration.'),
}
