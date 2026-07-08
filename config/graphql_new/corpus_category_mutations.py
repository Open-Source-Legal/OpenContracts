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




@strawberry.type(name="CreateCorpusCategory", description='Create a new corpus category. Superuser-only.')
class CreateCorpusCategory:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusCategoryType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="obj")


register_type("CreateCorpusCategory", CreateCorpusCategory, model=None)


@strawberry.type(name="UpdateCorpusCategory", description='Update an existing corpus category. Superuser-only.')
class UpdateCorpusCategory:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusCategoryType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="obj")


register_type("UpdateCorpusCategory", UpdateCorpusCategory, model=None)


@strawberry.type(name="DeleteCorpusCategory", description='Delete a corpus category. Superuser-only.\n\nDeleting a category removes it from every corpus that referenced it (the\n``Corpus.categories`` M2M through-rows are cleaned up automatically) but\ndoes not affect the corpuses themselves.')
class DeleteCorpusCategory:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteCorpusCategory", DeleteCorpusCategory, model=None)


def _mutate_CreateCorpusCategory(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:80

    Port of CreateCorpusCategory.mutate
    """
    raise NotImplementedError("_mutate_CreateCorpusCategory not yet ported — see manifest")


def m_create_corpus_category(info: strawberry.Info, color: Annotated[Optional[str], strawberry.argument(name="color", description="Hex color for the badge (e.g. '#3B82F6'). Defaults to blue.")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description", description='Optional human-readable description')] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon", description="Lucide icon name (e.g. 'scroll', 'gavel'). Defaults to 'folder'.")] = strawberry.UNSET, name: Annotated[str, strawberry.argument(name="name", description='Unique category name')] = strawberry.UNSET, sort_order: Annotated[Optional[int], strawberry.argument(name="sortOrder", description='Display order; lower sorts first')] = strawberry.UNSET) -> Optional["CreateCorpusCategory"]:
    kwargs = strip_unset({"color": color, "description": description, "icon": icon, "name": name, "sort_order": sort_order})
    return _mutate_CreateCorpusCategory(CreateCorpusCategory, None, info, **kwargs)


def _mutate_UpdateCorpusCategory(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:126

    Port of UpdateCorpusCategory.mutate
    """
    raise NotImplementedError("_mutate_UpdateCorpusCategory not yet ported — see manifest")


def m_update_corpus_category(info: strawberry.Info, color: Annotated[Optional[str], strawberry.argument(name="color")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon")] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='Global ID of the category')] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name")] = strawberry.UNSET, sort_order: Annotated[Optional[int], strawberry.argument(name="sortOrder")] = strawberry.UNSET) -> Optional["UpdateCorpusCategory"]:
    kwargs = strip_unset({"color": color, "description": description, "icon": icon, "id": id, "name": name, "sort_order": sort_order})
    return _mutate_UpdateCorpusCategory(UpdateCorpusCategory, None, info, **kwargs)


def _mutate_DeleteCorpusCategory(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:181

    Port of DeleteCorpusCategory.mutate
    """
    raise NotImplementedError("_mutate_DeleteCorpusCategory not yet ported — see manifest")


def m_delete_corpus_category(info: strawberry.Info, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='Global ID of the category')] = strawberry.UNSET) -> Optional["DeleteCorpusCategory"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteCorpusCategory(DeleteCorpusCategory, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_corpus_category": strawberry.field(resolver=m_create_corpus_category, name="createCorpusCategory", description='Create a new corpus category. Superuser-only.'),
    "update_corpus_category": strawberry.field(resolver=m_update_corpus_category, name="updateCorpusCategory", description='Update an existing corpus category. Superuser-only.'),
    "delete_corpus_category": strawberry.field(resolver=m_delete_corpus_category, name="deleteCorpusCategory", description='Delete a corpus category. Superuser-only.\n\nDeleting a category removes it from every corpus that referenced it (the\n``Corpus.categories`` M2M through-rows are cleaned up automatically) but\ndoes not affect the corpuses themselves.'),
}
