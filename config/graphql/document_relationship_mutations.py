"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
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

import logging
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import login_required
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services import CorpusDocumentService
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.documents.services import DocumentRelationshipService
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import get_for_user_or_none

logger = logging.getLogger(__name__)


@strawberry.type(
    name="CreateDocumentRelationship",
    description="Create a new relationship between two documents in the same corpus.\n\nPermission requirements:\n- User must have CREATE permission on BOTH source and target documents\n- User must have CREATE permission on the corpus\n\nValidation:\n- Both documents must be in the specified corpus\n- For RELATIONSHIP type: annotation_label_id is required\n- For NOTES type: annotation_label_id is optional",
)
class CreateDocumentRelationship:
    ok: bool | None = strawberry.field(name="ok", default=None)
    document_relationship: None | (
        Annotated[
            DocumentRelationshipType, strawberry.lazy("config.graphql.document_types")
        ]
    ) = strawberry.field(name="documentRelationship", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("CreateDocumentRelationship", CreateDocumentRelationship, model=None)


@strawberry.type(
    name="UpdateDocumentRelationship",
    description="Update an existing document relationship.\n\nPermission requirements:\n- User must have UPDATE permission on the document relationship\n- OR UPDATE permission on BOTH source and target documents\n\nUpdatable fields:\n- relationship_type (with validation for annotation_label requirement)\n- annotation_label_id\n- data (JSON payload)\n- corpus_id",
)
class UpdateDocumentRelationship:
    ok: bool | None = strawberry.field(name="ok", default=None)
    document_relationship: None | (
        Annotated[
            DocumentRelationshipType, strawberry.lazy("config.graphql.document_types")
        ]
    ) = strawberry.field(name="documentRelationship", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("UpdateDocumentRelationship", UpdateDocumentRelationship, model=None)


@strawberry.type(
    name="DeleteDocumentRelationship",
    description="Delete a document relationship.\n\nPermission requirements:\n- User must have DELETE permission on the document relationship\n- OR DELETE permission on BOTH source and target documents",
)
class DeleteDocumentRelationship:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteDocumentRelationship", DeleteDocumentRelationship, model=None)


@strawberry.type(
    name="DeleteDocumentRelationships",
    description="Delete multiple document relationships at once.\n\nPermission requirements:\n- User must have DELETE permission on each document relationship",
)
class DeleteDocumentRelationships:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    deleted_count: int | None = strawberry.field(name="deletedCount", default=None)


register_type("DeleteDocumentRelationships", DeleteDocumentRelationships, model=None)


def _mutate_CreateDocumentRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:66

    Port of CreateDocumentRelationship.mutate
    """

    # Decorator applied to an inner function because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not match
    # the ``(root, info, ...)`` calling convention the decorators expect.
    @login_required
    def mutate(
        root,
        info,
        source_document_id,
        target_document_id,
        relationship_type,
        corpus_id,
        annotation_label_id=None,
        data=None,
    ) -> CreateDocumentRelationship:
        try:
            # Decode global IDs
            source_doc_pk = from_global_id(source_document_id)[1]
            target_doc_pk = from_global_id(target_document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # Validate relationship_type (use model constant)
            valid_types = [
                choice[0] for choice in DocumentRelationship.RELATIONSHIP_TYPE_CHOICES
            ]
            if relationship_type not in valid_types:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message=f"Invalid relationship_type. Must be one of: {valid_types}",
                )

            # Validate that RELATIONSHIP type has annotation_label
            if relationship_type == "RELATIONSHIP" and not annotation_label_id:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="annotation_label_id is required for RELATIONSHIP type",
                )

            # Fetch corpus + check CREATE permission. ``get_for_user_or_none``
            # collapses missing-pk and inaccessible-pk into the same response
            # per the Phase D IDOR contract.
            corpus = get_for_user_or_none(Corpus, corpus_pk, info.context.user)
            if corpus is None or BaseService.require_permission(
                corpus,
                info.context.user,
                PermissionTypes.CREATE,
                request=info.context,
            ):
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Corpus not found",
                )

            # Source document — same unified pattern.
            source_doc = get_for_user_or_none(
                Document, source_doc_pk, info.context.user
            )
            if source_doc is None or BaseService.require_permission(
                source_doc,
                info.context.user,
                PermissionTypes.CREATE,
                request=info.context,
            ):
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Source document not found",
                )

            # Target document — same unified pattern.
            target_doc = get_for_user_or_none(
                Document, target_doc_pk, info.context.user
            )
            if target_doc is None or BaseService.require_permission(
                target_doc,
                info.context.user,
                PermissionTypes.CREATE,
                request=info.context,
            ):
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Target document not found",
                )

            # Validate both docs are in the corpus via DocumentPath
            # Use distinct document IDs to handle cases where a document
            # has multiple paths in the corpus (e.g., different folders)
            from opencontractserver.documents.models import DocumentPath

            docs_in_corpus = set(
                DocumentPath.objects.filter(
                    corpus_id=corpus_pk,
                    document_id__in=[source_doc_pk, target_doc_pk],
                    is_current=True,
                    is_deleted=False,
                ).values_list("document_id", flat=True)
            )

            if len(docs_in_corpus) != 2:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Both documents must be in the same corpus",
                )

            # Handle optional annotation_label
            annotation_label_pk = None
            if annotation_label_id:
                annotation_label_pk = from_global_id(annotation_label_id)[1]
                try:
                    AnnotationLabel.objects.get(pk=annotation_label_pk)
                except AnnotationLabel.DoesNotExist:
                    return CreateDocumentRelationship(
                        ok=False,
                        document_relationship=None,
                        message="Annotation label not found",
                    )

            # Create the document relationship
            #
            # PERMISSION MODEL: DocumentRelationship uses inherited permissions
            # (not guardian object permissions). Access is determined by:
            #   Effective Permission = MIN(source_doc_perm, target_doc_perm, corpus_perm)
            # See: docs/permissioning/consolidated_permissioning_guide.md
            #
            doc_relationship = DocumentRelationship.objects.create(
                creator=info.context.user,
                source_document_id=source_doc_pk,
                target_document_id=target_doc_pk,
                relationship_type=relationship_type,
                annotation_label_id=annotation_label_pk,
                corpus_id=corpus_pk,
                data=data or {},
            )

            return CreateDocumentRelationship(
                ok=True,
                document_relationship=doc_relationship,
                message="Document relationship created successfully",
            )

        except Exception as e:
            logger.error(f"Error creating document relationship: {e}")
            return CreateDocumentRelationship(
                ok=False,
                document_relationship=None,
                message=f"Error creating document relationship: {str(e)}",
            )

    return mutate(root, info, **kwargs)


def m_create_document_relationship(
    info: strawberry.Info,
    annotation_label_id: Annotated[
        str | None,
        strawberry.argument(
            name="annotationLabelId",
            description="ID of the annotation label (required for RELATIONSHIP type)",
        ),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId",
            description="ID of the corpus (both documents must be in this corpus)",
        ),
    ] = strawberry.UNSET,
    data: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="data", description="JSON data payload (e.g., for notes content)"
        ),
    ] = strawberry.UNSET,
    relationship_type: Annotated[
        str,
        strawberry.argument(
            name="relationshipType",
            description="Type of relationship: 'RELATIONSHIP' or 'NOTES'",
        ),
    ] = strawberry.UNSET,
    source_document_id: Annotated[
        str,
        strawberry.argument(
            name="sourceDocumentId", description="ID of the source document"
        ),
    ] = strawberry.UNSET,
    target_document_id: Annotated[
        str,
        strawberry.argument(
            name="targetDocumentId", description="ID of the target document"
        ),
    ] = strawberry.UNSET,
) -> CreateDocumentRelationship | None:
    kwargs = strip_unset(
        {
            "annotation_label_id": annotation_label_id,
            "corpus_id": corpus_id,
            "data": data,
            "relationship_type": relationship_type,
            "source_document_id": source_document_id,
            "target_document_id": target_document_id,
        }
    )
    return _mutate_CreateDocumentRelationship(
        CreateDocumentRelationship, None, info, **kwargs
    )


def _mutate_UpdateDocumentRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:249

    Port of UpdateDocumentRelationship.mutate
    """

    # Decorator applied to an inner function — see _mutate_CreateDocumentRelationship.
    @login_required
    def mutate(
        root,
        info,
        document_relationship_id,
        relationship_type=None,
        annotation_label_id=None,
        corpus_id=None,
        data=None,
    ) -> UpdateDocumentRelationship:
        try:
            # Decode global ID
            doc_rel_pk = from_global_id(document_relationship_id)[1]

            # Use service for IDOR-safe fetch with visibility check
            doc_relationship = DocumentRelationshipService.get_relationship_by_id(
                user=info.context.user,
                relationship_id=int(doc_rel_pk),
                request=info.context,
            )

            # IDOR protection: same message for not found or not accessible
            if doc_relationship is None:
                return UpdateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Document relationship not found",
                )

            # Check UPDATE permission (inherited from source_doc + target_doc + corpus)
            if not DocumentRelationshipService.user_has_permission(
                info.context.user,
                doc_relationship,
                "UPDATE",
                request=info.context,
            ):
                return UpdateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="You don't have permission to update this document relationship",
                )

            # Validate relationship_type if provided (use model constant)
            valid_types = [
                choice[0] for choice in DocumentRelationship.RELATIONSHIP_TYPE_CHOICES
            ]
            if relationship_type is not None:
                if relationship_type not in valid_types:
                    return UpdateDocumentRelationship(
                        ok=False,
                        document_relationship=None,
                        message=f"Invalid relationship_type. Must be one of: {valid_types}",
                    )
                doc_relationship.relationship_type = relationship_type

            # Handle annotation_label update
            if annotation_label_id is not None:
                if annotation_label_id == "":
                    # Explicitly clearing the annotation label
                    doc_relationship.annotation_label_id = None
                else:
                    annotation_label_pk = from_global_id(annotation_label_id)[1]
                    try:
                        AnnotationLabel.objects.get(pk=annotation_label_pk)
                    except AnnotationLabel.DoesNotExist:
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Annotation label not found",
                        )
                    doc_relationship.annotation_label_id = annotation_label_pk

            # Explicit validation: RELATIONSHIP type requires annotation_label
            # (Check before full_clean for clearer error message)
            final_type = relationship_type or doc_relationship.relationship_type
            final_label = (
                doc_relationship.annotation_label_id
                if annotation_label_id != ""
                else None
            )
            if final_type == "RELATIONSHIP" and not final_label:
                return UpdateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="annotation_label_id is required for RELATIONSHIP type",
                )

            # Handle corpus update
            if corpus_id is not None:
                if corpus_id == "":
                    return UpdateDocumentRelationship(
                        ok=False,
                        document_relationship=None,
                        message="Corpus is required for document relationships",
                    )
                else:
                    corpus_pk = from_global_id(corpus_id)[1]
                    # IDOR-safe: same message for not found or no permission.
                    corpus = get_for_user_or_none(Corpus, corpus_pk, info.context.user)
                    if corpus is None or BaseService.require_permission(
                        corpus,
                        info.context.user,
                        PermissionTypes.UPDATE,
                        request=info.context,
                    ):
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Corpus not found",
                        )

                    # Validate both documents are in the new corpus.
                    # Routes through the canonical service so corpus READ is
                    # enforced against the requesting user.
                    docs_in_corpus = (
                        CorpusDocumentService.get_corpus_documents(
                            user=info.context.user, corpus=corpus
                        )
                        .filter(
                            id__in=[
                                doc_relationship.source_document_id,
                                doc_relationship.target_document_id,
                            ]
                        )
                        .count()
                    )
                    if docs_in_corpus != 2:
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Both documents must be in the specified corpus",
                        )
                    doc_relationship.corpus_id = corpus_pk

            # Handle data update
            if data is not None:
                doc_relationship.data = data

            # Validate before saving
            doc_relationship.full_clean()
            doc_relationship.save()

            return UpdateDocumentRelationship(
                ok=True,
                document_relationship=doc_relationship,
                message="Document relationship updated successfully",
            )

        except Exception as e:
            logger.error(f"Error updating document relationship: {e}")
            return UpdateDocumentRelationship(
                ok=False,
                document_relationship=None,
                message=f"Error updating document relationship: {str(e)}",
            )

    return mutate(root, info, **kwargs)


def m_update_document_relationship(
    info: strawberry.Info,
    annotation_label_id: Annotated[
        str | None,
        strawberry.argument(
            name="annotationLabelId", description="New annotation label ID"
        ),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        str | None, strawberry.argument(name="corpusId", description="New corpus ID")
    ] = strawberry.UNSET,
    data: Annotated[
        GenericScalar | None,
        strawberry.argument(name="data", description="Updated JSON data payload"),
    ] = strawberry.UNSET,
    document_relationship_id: Annotated[
        str,
        strawberry.argument(
            name="documentRelationshipId",
            description="ID of the document relationship to update",
        ),
    ] = strawberry.UNSET,
    relationship_type: Annotated[
        str | None,
        strawberry.argument(
            name="relationshipType",
            description="New relationship type: 'RELATIONSHIP' or 'NOTES'",
        ),
    ] = strawberry.UNSET,
) -> UpdateDocumentRelationship | None:
    kwargs = strip_unset(
        {
            "annotation_label_id": annotation_label_id,
            "corpus_id": corpus_id,
            "data": data,
            "document_relationship_id": document_relationship_id,
            "relationship_type": relationship_type,
        }
    )
    return _mutate_UpdateDocumentRelationship(
        UpdateDocumentRelationship, None, info, **kwargs
    )


def _mutate_DeleteDocumentRelationship(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:423

    Port of DeleteDocumentRelationship.mutate
    """

    # Decorator applied to an inner function — see _mutate_CreateDocumentRelationship.
    @login_required
    def mutate(root, info, document_relationship_id) -> DeleteDocumentRelationship:
        try:
            # Decode global ID
            doc_rel_pk = from_global_id(document_relationship_id)[1]

            # Use service for IDOR-safe fetch with visibility check
            doc_relationship = DocumentRelationshipService.get_relationship_by_id(
                user=info.context.user,
                relationship_id=int(doc_rel_pk),
                request=info.context,
            )

            # IDOR protection: same message for not found or not accessible
            if doc_relationship is None:
                return DeleteDocumentRelationship(
                    ok=False, message="Document relationship not found"
                )

            # Check DELETE permission (inherited from source_doc + target_doc + corpus)
            if not DocumentRelationshipService.user_has_permission(
                info.context.user,
                doc_relationship,
                "DELETE",
                request=info.context,
            ):
                return DeleteDocumentRelationship(
                    ok=False,
                    message="You don't have permission to delete this document relationship",
                )

            doc_relationship.delete()

            return DeleteDocumentRelationship(
                ok=True, message="Document relationship deleted successfully"
            )

        except Exception as e:
            logger.error(f"Error deleting document relationship: {e}")
            return DeleteDocumentRelationship(
                ok=False, message=f"Error deleting document relationship: {str(e)}"
            )

    return mutate(root, info, **kwargs)


def m_delete_document_relationship(
    info: strawberry.Info,
    document_relationship_id: Annotated[
        str,
        strawberry.argument(
            name="documentRelationshipId",
            description="ID of the document relationship to delete",
        ),
    ] = strawberry.UNSET,
) -> DeleteDocumentRelationship | None:
    kwargs = strip_unset({"document_relationship_id": document_relationship_id})
    return _mutate_DeleteDocumentRelationship(
        DeleteDocumentRelationship, None, info, **kwargs
    )


def _mutate_DeleteDocumentRelationships(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:486

    Port of DeleteDocumentRelationships.mutate
    """

    # Decorator applied to an inner function — see _mutate_CreateDocumentRelationship.
    @login_required
    def mutate(root, info, document_relationship_ids) -> DeleteDocumentRelationships:
        user = info.context.user

        try:
            # Decode all IDs first
            relationship_pks = [
                int(from_global_id(gid)[1]) for gid in document_relationship_ids
            ]

            # Fetch all relationships in a single query (fixes N+1)
            visible_relationships = (
                DocumentRelationshipService.get_visible_relationships(
                    user=user, request=info.context
                ).filter(id__in=relationship_pks)
            )

            # Build a dict for O(1) lookup
            relationship_map = {rel.id: rel for rel in visible_relationships}

            # Check all relationships are visible (IDOR protection)
            for pk in relationship_pks:
                if pk not in relationship_map:
                    return DeleteDocumentRelationships(
                        ok=False,
                        message="Document relationship not found",
                        deleted_count=0,
                    )

            # Check DELETE permission for each relationship
            # (inherited from source_doc + target_doc + corpus)
            for pk, doc_relationship in relationship_map.items():
                if not DocumentRelationshipService.user_has_permission(
                    user,
                    doc_relationship,
                    "DELETE",
                    request=info.context,
                ):
                    return DeleteDocumentRelationships(
                        ok=False,
                        message="Document relationship not found",
                        deleted_count=0,
                    )

            # Delete all at once
            deleted_count = len(relationship_pks)
            DocumentRelationship.objects.filter(id__in=relationship_pks).delete()

            return DeleteDocumentRelationships(
                ok=True,
                message=f"Successfully deleted {deleted_count} document relationship(s)",
                deleted_count=deleted_count,
            )

        except Exception as e:
            logger.error(f"Error deleting document relationships: {e}")
            return DeleteDocumentRelationships(
                ok=False,
                message=f"Error deleting document relationships: {str(e)}",
                deleted_count=0,
            )

    return mutate(root, info, **kwargs)


def m_delete_document_relationships(
    info: strawberry.Info,
    document_relationship_ids: Annotated[
        list[str | None],
        strawberry.argument(
            name="documentRelationshipIds",
            description="List of document relationship IDs to delete",
        ),
    ] = strawberry.UNSET,
) -> DeleteDocumentRelationships | None:
    kwargs = strip_unset({"document_relationship_ids": document_relationship_ids})
    return _mutate_DeleteDocumentRelationships(
        DeleteDocumentRelationships, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "create_document_relationship": strawberry.field(
        resolver=m_create_document_relationship,
        name="createDocumentRelationship",
        description="Create a new relationship between two documents in the same corpus.\n\nPermission requirements:\n- User must have CREATE permission on BOTH source and target documents\n- User must have CREATE permission on the corpus\n\nValidation:\n- Both documents must be in the specified corpus\n- For RELATIONSHIP type: annotation_label_id is required\n- For NOTES type: annotation_label_id is optional",
    ),
    "update_document_relationship": strawberry.field(
        resolver=m_update_document_relationship,
        name="updateDocumentRelationship",
        description="Update an existing document relationship.\n\nPermission requirements:\n- User must have UPDATE permission on the document relationship\n- OR UPDATE permission on BOTH source and target documents\n\nUpdatable fields:\n- relationship_type (with validation for annotation_label requirement)\n- annotation_label_id\n- data (JSON payload)\n- corpus_id",
    ),
    "delete_document_relationship": strawberry.field(
        resolver=m_delete_document_relationship,
        name="deleteDocumentRelationship",
        description="Delete a document relationship.\n\nPermission requirements:\n- User must have DELETE permission on the document relationship\n- OR DELETE permission on BOTH source and target documents",
    ),
    "delete_document_relationships": strawberry.field(
        resolver=m_delete_document_relationships,
        name="deleteDocumentRelationships",
        description="Delete multiple document relationships at once.\n\nPermission requirements:\n- User must have DELETE permission on each document relationship",
    ),
}
