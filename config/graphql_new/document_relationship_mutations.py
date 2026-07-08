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




@strawberry.type(name="CreateDocumentRelationship", description='Create a new relationship between two documents in the same corpus.\n\nPermission requirements:\n- User must have CREATE permission on BOTH source and target documents\n- User must have CREATE permission on the corpus\n\nValidation:\n- Both documents must be in the specified corpus\n- For RELATIONSHIP type: annotation_label_id is required\n- For NOTES type: annotation_label_id is optional')
class CreateDocumentRelationship:
    ok: Optional[bool] = strawberry.field(name="ok")
    document_relationship: Optional[Annotated["DocumentRelationshipType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="documentRelationship")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("CreateDocumentRelationship", CreateDocumentRelationship, model=None)


@strawberry.type(name="UpdateDocumentRelationship", description='Update an existing document relationship.\n\nPermission requirements:\n- User must have UPDATE permission on the document relationship\n- OR UPDATE permission on BOTH source and target documents\n\nUpdatable fields:\n- relationship_type (with validation for annotation_label requirement)\n- annotation_label_id\n- data (JSON payload)\n- corpus_id')
class UpdateDocumentRelationship:
    ok: Optional[bool] = strawberry.field(name="ok")
    document_relationship: Optional[Annotated["DocumentRelationshipType", strawberry.lazy("config.graphql_new.document_types")]] = strawberry.field(name="documentRelationship")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("UpdateDocumentRelationship", UpdateDocumentRelationship, model=None)


@strawberry.type(name="DeleteDocumentRelationship", description='Delete a document relationship.\n\nPermission requirements:\n- User must have DELETE permission on the document relationship\n- OR DELETE permission on BOTH source and target documents')
class DeleteDocumentRelationship:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteDocumentRelationship", DeleteDocumentRelationship, model=None)


@strawberry.type(name="DeleteDocumentRelationships", description='Delete multiple document relationships at once.\n\nPermission requirements:\n- User must have DELETE permission on each document relationship')
class DeleteDocumentRelationships:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    deleted_count: Optional[int] = strawberry.field(name="deletedCount")


register_type("DeleteDocumentRelationships", DeleteDocumentRelationships, model=None)


def _mutate_CreateDocumentRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:66

    Port of CreateDocumentRelationship.mutate
    """
    raise NotImplementedError("_mutate_CreateDocumentRelationship not yet ported — see manifest")


def m_create_document_relationship(info: strawberry.Info, annotation_label_id: Annotated[Optional[str], strawberry.argument(name="annotationLabelId", description='ID of the annotation label (required for RELATIONSHIP type)')] = strawberry.UNSET, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of the corpus (both documents must be in this corpus)')] = strawberry.UNSET, data: Annotated[Optional[GenericScalar], strawberry.argument(name="data", description='JSON data payload (e.g., for notes content)')] = strawberry.UNSET, relationship_type: Annotated[str, strawberry.argument(name="relationshipType", description="Type of relationship: 'RELATIONSHIP' or 'NOTES'")] = strawberry.UNSET, source_document_id: Annotated[str, strawberry.argument(name="sourceDocumentId", description='ID of the source document')] = strawberry.UNSET, target_document_id: Annotated[str, strawberry.argument(name="targetDocumentId", description='ID of the target document')] = strawberry.UNSET) -> Optional["CreateDocumentRelationship"]:
    kwargs = strip_unset({"annotation_label_id": annotation_label_id, "corpus_id": corpus_id, "data": data, "relationship_type": relationship_type, "source_document_id": source_document_id, "target_document_id": target_document_id})
    return _mutate_CreateDocumentRelationship(CreateDocumentRelationship, None, info, **kwargs)


def _mutate_UpdateDocumentRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:249

    Port of UpdateDocumentRelationship.mutate
    """
    raise NotImplementedError("_mutate_UpdateDocumentRelationship not yet ported — see manifest")


def m_update_document_relationship(info: strawberry.Info, annotation_label_id: Annotated[Optional[str], strawberry.argument(name="annotationLabelId", description='New annotation label ID')] = strawberry.UNSET, corpus_id: Annotated[Optional[str], strawberry.argument(name="corpusId", description='New corpus ID')] = strawberry.UNSET, data: Annotated[Optional[GenericScalar], strawberry.argument(name="data", description='Updated JSON data payload')] = strawberry.UNSET, document_relationship_id: Annotated[str, strawberry.argument(name="documentRelationshipId", description='ID of the document relationship to update')] = strawberry.UNSET, relationship_type: Annotated[Optional[str], strawberry.argument(name="relationshipType", description="New relationship type: 'RELATIONSHIP' or 'NOTES'")] = strawberry.UNSET) -> Optional["UpdateDocumentRelationship"]:
    kwargs = strip_unset({"annotation_label_id": annotation_label_id, "corpus_id": corpus_id, "data": data, "document_relationship_id": document_relationship_id, "relationship_type": relationship_type})
    return _mutate_UpdateDocumentRelationship(UpdateDocumentRelationship, None, info, **kwargs)


def _mutate_DeleteDocumentRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:423

    Port of DeleteDocumentRelationship.mutate
    """
    raise NotImplementedError("_mutate_DeleteDocumentRelationship not yet ported — see manifest")


def m_delete_document_relationship(info: strawberry.Info, document_relationship_id: Annotated[str, strawberry.argument(name="documentRelationshipId", description='ID of the document relationship to delete')] = strawberry.UNSET) -> Optional["DeleteDocumentRelationship"]:
    kwargs = strip_unset({"document_relationship_id": document_relationship_id})
    return _mutate_DeleteDocumentRelationship(DeleteDocumentRelationship, None, info, **kwargs)


def _mutate_DeleteDocumentRelationships(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:486

    Port of DeleteDocumentRelationships.mutate
    """
    raise NotImplementedError("_mutate_DeleteDocumentRelationships not yet ported — see manifest")


def m_delete_document_relationships(info: strawberry.Info, document_relationship_ids: Annotated[list[Optional[str]], strawberry.argument(name="documentRelationshipIds", description='List of document relationship IDs to delete')] = strawberry.UNSET) -> Optional["DeleteDocumentRelationships"]:
    kwargs = strip_unset({"document_relationship_ids": document_relationship_ids})
    return _mutate_DeleteDocumentRelationships(DeleteDocumentRelationships, None, info, **kwargs)



MUTATION_FIELDS = {
    "create_document_relationship": strawberry.field(resolver=m_create_document_relationship, name="createDocumentRelationship", description='Create a new relationship between two documents in the same corpus.\n\nPermission requirements:\n- User must have CREATE permission on BOTH source and target documents\n- User must have CREATE permission on the corpus\n\nValidation:\n- Both documents must be in the specified corpus\n- For RELATIONSHIP type: annotation_label_id is required\n- For NOTES type: annotation_label_id is optional'),
    "update_document_relationship": strawberry.field(resolver=m_update_document_relationship, name="updateDocumentRelationship", description='Update an existing document relationship.\n\nPermission requirements:\n- User must have UPDATE permission on the document relationship\n- OR UPDATE permission on BOTH source and target documents\n\nUpdatable fields:\n- relationship_type (with validation for annotation_label requirement)\n- annotation_label_id\n- data (JSON payload)\n- corpus_id'),
    "delete_document_relationship": strawberry.field(resolver=m_delete_document_relationship, name="deleteDocumentRelationship", description='Delete a document relationship.\n\nPermission requirements:\n- User must have DELETE permission on the document relationship\n- OR DELETE permission on BOTH source and target documents'),
    "delete_document_relationships": strawberry.field(resolver=m_delete_document_relationships, name="deleteDocumentRelationships", description='Delete multiple document relationships at once.\n\nPermission requirements:\n- User must have DELETE permission on each document relationship'),
}
