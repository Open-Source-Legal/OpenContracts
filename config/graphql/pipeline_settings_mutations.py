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




@strawberry.type(name="UpdatePipelineSettingsMutation", description='Update the singleton pipeline settings.\n\nOnly superusers can modify these settings. Changes take effect immediately\nfor all new document processing tasks.\n\nArguments:\n    preferred_parsers: Dict mapping MIME types to parser class paths\n    preferred_embedders: Dict mapping MIME types to embedder class paths\n    preferred_thumbnailers: Dict mapping MIME types to thumbnailer class paths\n    preferred_enrichers: Dict mapping MIME types to ORDERED LISTS of enricher class paths\n    parser_kwargs: Dict mapping parser class paths to their configuration kwargs\n    component_settings: Dict mapping component class paths to settings overrides\n    default_embedder: Default embedder class path\n\nReturns:\n    ok: Whether the update succeeded\n    message: Status message\n    pipeline_settings: The updated settings')
class UpdatePipelineSettingsMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    pipeline_settings: Optional[Annotated["PipelineSettingsType", strawberry.lazy("config.graphql.pipeline_types")]] = strawberry.field(name="pipelineSettings", default=None)


register_type("UpdatePipelineSettingsMutation", UpdatePipelineSettingsMutation, model=None)


@strawberry.type(name="ResetPipelineSettingsMutation", description='Reset pipeline settings to Django settings defaults.\n\nThis mutation resets all pipeline settings to their default values from\nDjango settings (PREFERRED_PARSERS, PREFERRED_EMBEDDERS, etc.).\n\nOnly superusers can perform this operation.')
class ResetPipelineSettingsMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    pipeline_settings: Optional[Annotated["PipelineSettingsType", strawberry.lazy("config.graphql.pipeline_types")]] = strawberry.field(name="pipelineSettings", default=None)


register_type("ResetPipelineSettingsMutation", ResetPipelineSettingsMutation, model=None)


@strawberry.type(name="UpdateComponentSecretsMutation", description="Update encrypted secrets for a specific pipeline component.\n\nThis mutation allows superusers to securely store API keys, tokens, and\nother credentials for pipeline components. The secrets are encrypted at\nrest using Fernet symmetric encryption.\n\nOnly superusers can perform this operation.\n\nArguments:\n    component_path: Full class path of the component (e.g.,\n        'opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser')\n    secrets: Dict of secret key-value pairs to store (e.g., {'api_key': '...'})\n    merge: If True, merge with existing secrets. If False, replace all secrets\n        for this component. Default: True\n\nReturns:\n    ok: Whether the update succeeded\n    message: Status message\n    components_with_secrets: List of component paths that have secrets stored")
class UpdateComponentSecretsMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="componentsWithSecrets", description='List of component paths that have secrets stored.')
    def components_with_secrets(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "components_with_secrets", None))


register_type("UpdateComponentSecretsMutation", UpdateComponentSecretsMutation, model=None)


@strawberry.type(name="DeleteComponentSecretsMutation", description='Delete all encrypted secrets for a specific pipeline component.\n\nOnly superusers can perform this operation.\n\nArguments:\n    component_path: Full class path of the component\n\nReturns:\n    ok: Whether the deletion succeeded\n    message: Status message\n    components_with_secrets: Updated list of component paths that have secrets')
class DeleteComponentSecretsMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="componentsWithSecrets")
    def components_with_secrets(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "components_with_secrets", None))


register_type("DeleteComponentSecretsMutation", DeleteComponentSecretsMutation, model=None)


@strawberry.type(name="UpdateToolSecretsMutation", description='Update encrypted secrets for an agent tool (e.g. web search API keys).\n\nTool secrets are stored in PipelineSettings alongside component secrets,\nunder a ``tool:`` namespace prefix. Only superusers can perform this.\n\nArguments:\n    tool_key: Tool identifier, e.g. ``"tool:web_search"``\n    secrets: Dict of secret key-value pairs, e.g. ``{"api_key": "..."}``\n    settings: Optional non-sensitive settings, e.g. ``{"provider": "brave"}``\n    merge: If True (default), merge with existing; if False, replace.')
class UpdateToolSecretsMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="toolsWithSecrets", description='Tool keys that have secrets stored.')
    def tools_with_secrets(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "tools_with_secrets", None))


register_type("UpdateToolSecretsMutation", UpdateToolSecretsMutation, model=None)


@strawberry.type(name="DeleteToolSecretsMutation", description='Delete all settings and secrets for an agent tool.\n\nOnly superusers can perform this operation.')
class DeleteToolSecretsMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="toolsWithSecrets")
    def tools_with_secrets(self, info: strawberry.Info) -> Optional[list[Optional[str]]]:
        return coerce_str(getattr(self, "tools_with_secrets", None))


register_type("DeleteToolSecretsMutation", DeleteToolSecretsMutation, model=None)


def _mutate_UpdatePipelineSettingsMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:412

    Port of UpdatePipelineSettingsMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdatePipelineSettingsMutation not yet ported — see manifest")


def m_update_pipeline_settings(info: strawberry.Info, component_settings: Annotated[Optional[GenericScalar], strawberry.argument(name="componentSettings", description='Mapping of component class paths to settings overrides.')] = strawberry.UNSET, default_embedder: Annotated[Optional[str], strawberry.argument(name="defaultEmbedder", description='Default embedder class path used for all ingest embedding. There is no MIME-specific override; see preferred_embedders.')] = strawberry.UNSET, default_file_converter: Annotated[Optional[str], strawberry.argument(name="defaultFileConverter", description='File converter class path used to convert non-native upload formats to PDF before parsing. Empty string disables the conversion step.')] = strawberry.UNSET, default_llm: Annotated[Optional[str], strawberry.argument(name="defaultLlm", description="Install-wide default LLM model spec (pydantic-ai '{provider}:{model}' form, e.g. 'anthropic:claude-opus-4-6') for agents when no per-corpus or per-agent override is set. Empty string falls back to the Django settings default. The provider prefix must be a registered LLM provider.")] = strawberry.UNSET, default_reranker: Annotated[Optional[str], strawberry.argument(name="defaultReranker", description='Default post-retrieval reranker class path. Empty string disables reranking (first-stage vector / hybrid search only).')] = strawberry.UNSET, enabled_components: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="enabledComponents", description='List of enabled component class paths. Components assigned as filetype defaults must be included.')] = strawberry.UNSET, parser_kwargs: Annotated[Optional[GenericScalar], strawberry.argument(name="parserKwargs", description="Mapping of parser class paths to their configuration kwargs. Example: {'DoclingParser': {'force_ocr': true}}")] = strawberry.UNSET, preferred_embedders: Annotated[Optional[GenericScalar], strawberry.argument(name="preferredEmbedders", description='Mapping of MIME types to preferred embedder class paths. API-only (issue #2114): has no effect at ingest, which always resolves the single global default_embedder to keep the cross-corpus vector index on one embedding space.')] = strawberry.UNSET, preferred_enrichers: Annotated[Optional[GenericScalar], strawberry.argument(name="preferredEnrichers", description='Mapping of MIME types to ordered lists of preferred enricher class paths.')] = strawberry.UNSET, preferred_parsers: Annotated[Optional[GenericScalar], strawberry.argument(name="preferredParsers", description="Mapping of MIME types to preferred parser class paths. Example: {'application/pdf': 'opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser'}")] = strawberry.UNSET, preferred_thumbnailers: Annotated[Optional[GenericScalar], strawberry.argument(name="preferredThumbnailers", description='Mapping of MIME types to preferred thumbnailer class paths.')] = strawberry.UNSET) -> Optional["UpdatePipelineSettingsMutation"]:
    kwargs = strip_unset({"component_settings": component_settings, "default_embedder": default_embedder, "default_file_converter": default_file_converter, "default_llm": default_llm, "default_reranker": default_reranker, "enabled_components": enabled_components, "parser_kwargs": parser_kwargs, "preferred_embedders": preferred_embedders, "preferred_enrichers": preferred_enrichers, "preferred_parsers": preferred_parsers, "preferred_thumbnailers": preferred_thumbnailers})
    return _mutate_UpdatePipelineSettingsMutation(UpdatePipelineSettingsMutation, None, info, **kwargs)


def _mutate_ResetPipelineSettingsMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:999

    Port of ResetPipelineSettingsMutation.mutate
    """
    raise NotImplementedError("_mutate_ResetPipelineSettingsMutation not yet ported — see manifest")


def m_reset_pipeline_settings(info: strawberry.Info) -> Optional["ResetPipelineSettingsMutation"]:
    kwargs = strip_unset({})
    return _mutate_ResetPipelineSettingsMutation(ResetPipelineSettingsMutation, None, info, **kwargs)


def _mutate_UpdateComponentSecretsMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1144

    Port of UpdateComponentSecretsMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateComponentSecretsMutation not yet ported — see manifest")


def m_update_component_secrets(info: strawberry.Info, component_path: Annotated[str, strawberry.argument(name="componentPath", description='Full class path of the component.')] = strawberry.UNSET, merge: Annotated[Optional[bool], strawberry.argument(name="merge", description='If True, merge with existing secrets. If False, replace all secrets for this component.')] = True, secrets: Annotated[GenericScalar, strawberry.argument(name="secrets", description="Dict of secret key-value pairs to store. Example: {'api_key': 'sk-...', 'secret_token': '...'}")] = strawberry.UNSET) -> Optional["UpdateComponentSecretsMutation"]:
    kwargs = strip_unset({"component_path": component_path, "merge": merge, "secrets": secrets})
    return _mutate_UpdateComponentSecretsMutation(UpdateComponentSecretsMutation, None, info, **kwargs)


def _mutate_DeleteComponentSecretsMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1487

    Port of DeleteComponentSecretsMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteComponentSecretsMutation not yet ported — see manifest")


def m_delete_component_secrets(info: strawberry.Info, component_path: Annotated[str, strawberry.argument(name="componentPath", description='Full class path of the component.')] = strawberry.UNSET) -> Optional["DeleteComponentSecretsMutation"]:
    kwargs = strip_unset({"component_path": component_path})
    return _mutate_DeleteComponentSecretsMutation(DeleteComponentSecretsMutation, None, info, **kwargs)


def _mutate_UpdateToolSecretsMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1269

    Port of UpdateToolSecretsMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateToolSecretsMutation not yet ported — see manifest")


def m_update_tool_secrets(info: strawberry.Info, merge: Annotated[Optional[bool], strawberry.argument(name="merge", description='If True, merge with existing. If False, replace.')] = True, secrets: Annotated[Optional[GenericScalar], strawberry.argument(name="secrets", description='Dict of secret values to encrypt (e.g. api_key).')] = None, settings: Annotated[Optional[GenericScalar], strawberry.argument(name="settings", description='Dict of non-sensitive settings (e.g. provider).')] = None, tool_key: Annotated[str, strawberry.argument(name="toolKey", description='Tool identifier, e.g. "tool:web_search".')] = strawberry.UNSET) -> Optional["UpdateToolSecretsMutation"]:
    kwargs = strip_unset({"merge": merge, "secrets": secrets, "settings": settings, "tool_key": tool_key})
    return _mutate_UpdateToolSecretsMutation(UpdateToolSecretsMutation, None, info, **kwargs)


def _mutate_DeleteToolSecretsMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1414

    Port of DeleteToolSecretsMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteToolSecretsMutation not yet ported — see manifest")


def m_delete_tool_secrets(info: strawberry.Info, tool_key: Annotated[str, strawberry.argument(name="toolKey", description='Tool identifier, e.g. "tool:web_search".')] = strawberry.UNSET) -> Optional["DeleteToolSecretsMutation"]:
    kwargs = strip_unset({"tool_key": tool_key})
    return _mutate_DeleteToolSecretsMutation(DeleteToolSecretsMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "update_pipeline_settings": strawberry.field(resolver=m_update_pipeline_settings, name="updatePipelineSettings", description='Update the singleton pipeline settings.\n\nOnly superusers can modify these settings. Changes take effect immediately\nfor all new document processing tasks.\n\nArguments:\n    preferred_parsers: Dict mapping MIME types to parser class paths\n    preferred_embedders: Dict mapping MIME types to embedder class paths\n    preferred_thumbnailers: Dict mapping MIME types to thumbnailer class paths\n    preferred_enrichers: Dict mapping MIME types to ORDERED LISTS of enricher class paths\n    parser_kwargs: Dict mapping parser class paths to their configuration kwargs\n    component_settings: Dict mapping component class paths to settings overrides\n    default_embedder: Default embedder class path\n\nReturns:\n    ok: Whether the update succeeded\n    message: Status message\n    pipeline_settings: The updated settings'),
    "reset_pipeline_settings": strawberry.field(resolver=m_reset_pipeline_settings, name="resetPipelineSettings", description='Reset pipeline settings to Django settings defaults.\n\nThis mutation resets all pipeline settings to their default values from\nDjango settings (PREFERRED_PARSERS, PREFERRED_EMBEDDERS, etc.).\n\nOnly superusers can perform this operation.'),
    "update_component_secrets": strawberry.field(resolver=m_update_component_secrets, name="updateComponentSecrets", description="Update encrypted secrets for a specific pipeline component.\n\nThis mutation allows superusers to securely store API keys, tokens, and\nother credentials for pipeline components. The secrets are encrypted at\nrest using Fernet symmetric encryption.\n\nOnly superusers can perform this operation.\n\nArguments:\n    component_path: Full class path of the component (e.g.,\n        'opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser')\n    secrets: Dict of secret key-value pairs to store (e.g., {'api_key': '...'})\n    merge: If True, merge with existing secrets. If False, replace all secrets\n        for this component. Default: True\n\nReturns:\n    ok: Whether the update succeeded\n    message: Status message\n    components_with_secrets: List of component paths that have secrets stored"),
    "delete_component_secrets": strawberry.field(resolver=m_delete_component_secrets, name="deleteComponentSecrets", description='Delete all encrypted secrets for a specific pipeline component.\n\nOnly superusers can perform this operation.\n\nArguments:\n    component_path: Full class path of the component\n\nReturns:\n    ok: Whether the deletion succeeded\n    message: Status message\n    components_with_secrets: Updated list of component paths that have secrets'),
    "update_tool_secrets": strawberry.field(resolver=m_update_tool_secrets, name="updateToolSecrets", description='Update encrypted secrets for an agent tool (e.g. web search API keys).\n\nTool secrets are stored in PipelineSettings alongside component secrets,\nunder a ``tool:`` namespace prefix. Only superusers can perform this.\n\nArguments:\n    tool_key: Tool identifier, e.g. ``"tool:web_search"``\n    secrets: Dict of secret key-value pairs, e.g. ``{"api_key": "..."}``\n    settings: Optional non-sensitive settings, e.g. ``{"provider": "brave"}``\n    merge: If True (default), merge with existing; if False, replace.'),
    "delete_tool_secrets": strawberry.field(resolver=m_delete_tool_secrets, name="deleteToolSecrets", description='Delete all settings and secrets for an agent tool.\n\nOnly superusers can perform this operation.'),
}
