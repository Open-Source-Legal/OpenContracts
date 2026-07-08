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




@strawberry.type(name="SmartLabelSearchOrCreateMutation", description='Smart mutation that handles label search and creation with automatic labelset management.\n\nThis mutation encapsulates the following logic:\n1. If no labelset exists for the corpus and createIfNotFound is true:\n   - Creates a new labelset\n   - Assigns it to the corpus\n   - Creates the label in the new labelset\n\n2. If labelset exists:\n   - Searches for existing labels matching the search term\n   - If matches found: returns the matching labels\n   - If no matches and createIfNotFound is true: creates the label\n   - If no matches and createIfNotFound is false: returns empty list')
class SmartLabelSearchOrCreateMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="labels", description='List of matching or created labels')
    def labels(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["AnnotationLabelType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        return resolve_django_list(self, info, getattr(self, "labels"), "AnnotationLabelType")
    labelset: Optional[Annotated["LabelSetType", strawberry.lazy("config.graphql.annotation_types")]] = strawberry.field(name="labelset", description='The labelset (existing or newly created)', default=None)
    labelset_created: Optional[bool] = strawberry.field(name="labelsetCreated", description='Whether a new labelset was created', default=None)
    label_created: Optional[bool] = strawberry.field(name="labelCreated", description='Whether a new label was created', default=None)


register_type("SmartLabelSearchOrCreateMutation", SmartLabelSearchOrCreateMutation, model=None)


@strawberry.type(name="SmartLabelListMutation", description='Simplified mutation to get all available labels for a corpus with helpful status info.')
class SmartLabelListMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="labels")
    def labels(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["AnnotationLabelType", strawberry.lazy("config.graphql.annotation_types")]]]]:
        return resolve_django_list(self, info, getattr(self, "labels"), "AnnotationLabelType")
    has_labelset: Optional[bool] = strawberry.field(name="hasLabelset", default=None)
    can_create_labels: Optional[bool] = strawberry.field(name="canCreateLabels", default=None)


register_type("SmartLabelListMutation", SmartLabelListMutation, model=None)


def _mutate_SmartLabelSearchOrCreateMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:92

    Port of SmartLabelSearchOrCreateMutation.mutate
    """
    raise NotImplementedError("_mutate_SmartLabelSearchOrCreateMutation not yet ported — see manifest")


def m_smart_label_search_or_create(info: strawberry.Info, color: Annotated[Optional[str], strawberry.argument(name="color", description='Color for new label (if created)')] = '#1a75bc', corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus to work with')] = strawberry.UNSET, create_if_not_found: Annotated[Optional[bool], strawberry.argument(name="createIfNotFound", description='Whether to create label/labelset if not found')] = False, description: Annotated[Optional[str], strawberry.argument(name="description", description='Description for new label (if created)')] = '', icon: Annotated[Optional[str], strawberry.argument(name="icon", description='Icon for new label (if created)')] = 'tag', label_type: Annotated[str, strawberry.argument(name="labelType", description='The type of label (SPAN_LABEL, TOKEN_LABEL, etc.)')] = strawberry.UNSET, labelset_description: Annotated[Optional[str], strawberry.argument(name="labelsetDescription", description='Description for new labelset (if created)')] = '', labelset_title: Annotated[Optional[str], strawberry.argument(name="labelsetTitle", description="Title for new labelset (if created). Defaults to corpus title + ' Labels'")] = strawberry.UNSET, search_term: Annotated[str, strawberry.argument(name="searchTerm", description='The label text to search for or create')] = strawberry.UNSET) -> Optional["SmartLabelSearchOrCreateMutation"]:
    kwargs = strip_unset({"color": color, "corpus_id": corpus_id, "create_if_not_found": create_if_not_found, "description": description, "icon": icon, "label_type": label_type, "labelset_description": labelset_description, "labelset_title": labelset_title, "search_term": search_term})
    return _mutate_SmartLabelSearchOrCreateMutation(SmartLabelSearchOrCreateMutation, None, info, **kwargs)


def _mutate_SmartLabelListMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:269

    Port of SmartLabelListMutation.mutate
    """
    raise NotImplementedError("_mutate_SmartLabelListMutation not yet ported — see manifest")


def m_smart_label_list(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus')] = strawberry.UNSET, label_type: Annotated[Optional[str], strawberry.argument(name="labelType", description='Optional filter by label type')] = strawberry.UNSET) -> Optional["SmartLabelListMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "label_type": label_type})
    return _mutate_SmartLabelListMutation(SmartLabelListMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "smart_label_search_or_create": strawberry.field(resolver=m_smart_label_search_or_create, name="smartLabelSearchOrCreate", description='Smart mutation that handles label search and creation with automatic labelset management.\n\nThis mutation encapsulates the following logic:\n1. If no labelset exists for the corpus and createIfNotFound is true:\n   - Creates a new labelset\n   - Assigns it to the corpus\n   - Creates the label in the new labelset\n\n2. If labelset exists:\n   - Searches for existing labels matching the search term\n   - If matches found: returns the matching labels\n   - If no matches and createIfNotFound is true: creates the label\n   - If no matches and createIfNotFound is false: returns empty list'),
    "smart_label_list": strawberry.field(resolver=m_smart_label_list, name="smartLabelList", description='Simplified mutation to get all available labels for a corpus with helpful status info.'),
}
