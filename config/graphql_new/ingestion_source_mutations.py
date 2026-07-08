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




@strawberry.type(name="CreateIngestionSourceMutation", description='Create a new ingestion source for document lineage tracking.')
class CreateIngestionSourceMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    ingestion_source: Optional[Annotated["IngestionSourceType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="ingestionSource")


register_type("CreateIngestionSourceMutation", CreateIngestionSourceMutation, model=None)


@strawberry.type(name="UpdateIngestionSourceMutation", description='Update an existing ingestion source.')
class UpdateIngestionSourceMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    ingestion_source: Optional[Annotated["IngestionSourceType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="ingestionSource")


register_type("UpdateIngestionSourceMutation", UpdateIngestionSourceMutation, model=None)


@strawberry.type(name="DeleteIngestionSourceMutation", description='Delete an ingestion source. Existing DocumentPath references become NULL.')
class DeleteIngestionSourceMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteIngestionSourceMutation", DeleteIngestionSourceMutation, model=None)


def _mutate_CreateIngestionSourceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:77

    Port of CreateIngestionSourceMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateIngestionSourceMutation not yet ported — see manifest")


def m_create_ingestion_source(info: strawberry.Info, config: Annotated[Optional[GenericScalar], strawberry.argument(name="config", description='Connection details, schedule, etc.')] = strawberry.UNSET, name: Annotated[str, strawberry.argument(name="name", description="Human-readable name (e.g. 'alpha_site_crawler')")] = strawberry.UNSET, source_type: Annotated[Optional[enums.IngestionSourceTypeEnum], strawberry.argument(name="sourceType", description='Category of source (default: MANUAL)')] = strawberry.UNSET) -> Optional["CreateIngestionSourceMutation"]:
    kwargs = strip_unset({"config": config, "name": name, "source_type": source_type})
    return _mutate_CreateIngestionSourceMutation(CreateIngestionSourceMutation, None, info, **kwargs)


def _mutate_UpdateIngestionSourceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:128

    Port of UpdateIngestionSourceMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateIngestionSourceMutation not yet ported — see manifest")


def m_update_ingestion_source(info: strawberry.Info, active: Annotated[Optional[bool], strawberry.argument(name="active")] = strawberry.UNSET, config: Annotated[Optional[GenericScalar], strawberry.argument(name="config")] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, source_type: Annotated[Optional[enums.IngestionSourceTypeEnum], strawberry.argument(name="sourceType")] = strawberry.UNSET) -> Optional["UpdateIngestionSourceMutation"]:
    kwargs = strip_unset({"active": active, "config": config, "id": id, "name": name, "source_type": source_type})
    return _mutate_UpdateIngestionSourceMutation(UpdateIngestionSourceMutation, None, info, **kwargs)


def _mutate_DeleteIngestionSourceMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:196

    Port of DeleteIngestionSourceMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteIngestionSourceMutation not yet ported — see manifest")


def m_delete_ingestion_source(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteIngestionSourceMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteIngestionSourceMutation(DeleteIngestionSourceMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_ingestion_source": strawberry.field(resolver=m_create_ingestion_source, name="createIngestionSource", description='Create a new ingestion source for document lineage tracking.'),
    "update_ingestion_source": strawberry.field(resolver=m_update_ingestion_source, name="updateIngestionSource", description='Update an existing ingestion source.'),
    "delete_ingestion_source": strawberry.field(resolver=m_delete_ingestion_source, name="deleteIngestionSource", description='Delete an ingestion source. Existing DocumentPath references become NULL.'),
}
