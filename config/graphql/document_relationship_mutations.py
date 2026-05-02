"""
GraphQL mutations for document relationship operations.
"""

import logging

import graphene
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import DocumentRelationshipType
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentRelationship
from opencontractserver.documents.query_optimizer import (
    DocumentRelationshipQueryOptimizer,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import user_has_permission_for_obj

logger = logging.getLogger(__name__)


class CreateDocumentRelationship(graphene.Mutation):
    """
    Create a new relationship between two documents in the same corpus.

    Permission requirements:
    - User must have CREATE permission on BOTH source and target documents
    - User must have CREATE permission on the corpus

    Validation:
    - Both documents must be in the specified corpus
    - For RELATIONSHIP type: annotation_label_id is required
    - For NOTES type: annotation_label_id is optional
    """

    class Arguments:
        source_document_id = graphene.String(
            required=True, description="ID of the source document"
        )
        target_document_id = graphene.String(
            required=True, description="ID of the target document"
        )
        relationship_type = graphene.String(
            required=True,
            description="Type of relationship: 'RELATIONSHIP' or 'NOTES'",
        )
        annotation_label_id = graphene.String(
            required=False,
            description="ID of the annotation label (required for RELATIONSHIP type)",
        )
        corpus_id = graphene.String(
            required=True,
            description="ID of the corpus (both documents must be in this corpus)",
        )
        data = GenericScalar(
            required=False, description="JSON data payload (e.g., for notes content)"
        )

    ok = graphene.Boolean()
    document_relationship = graphene.Field(DocumentRelationshipType)
    message = graphene.String()

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
    ) -> "CreateDocumentRelationship":
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

            # Fetch corpus first and check permission
            try:
                corpus = Corpus.objects.get(pk=corpus_pk)
            except Corpus.DoesNotExist:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Corpus not found",
                )

            # IDOR-safe: same message for not found or no permission
            if not user_has_permission_for_obj(
                info.context.user,
                corpus,
                PermissionTypes.CREATE,
                include_group_permissions=True,
            ):
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Corpus not found",
                )

            # Fetch source document and check permission (before same-corpus check
            # for better error messages)
            try:
                source_doc = Document.objects.get(pk=source_doc_pk)
            except Document.DoesNotExist:
                source_doc = None

            if source_doc is None or not user_has_permission_for_obj(
                info.context.user,
                source_doc,
                PermissionTypes.CREATE,
                include_group_permissions=True,
            ):
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Source document not found",
                )

            # Fetch target document and check permission
            try:
                target_doc = Document.objects.get(pk=target_doc_pk)
            except Document.DoesNotExist:
                target_doc = None

            if target_doc is None or not user_has_permission_for_obj(
                info.context.user,
                target_doc,
                PermissionTypes.CREATE,
                include_group_permissions=True,
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


class UpdateDocumentRelationship(graphene.Mutation):
    """
    Update an existing document relationship.

    Permission requirements:
    - User must have UPDATE permission on the document relationship
    - OR UPDATE permission on BOTH source and target documents

    Updatable fields:
    - relationship_type (with validation for annotation_label requirement)
    - annotation_label_id
    - data (JSON payload)
    - corpus_id
    """

    class Arguments:
        document_relationship_id = graphene.String(
            required=True, description="ID of the document relationship to update"
        )
        relationship_type = graphene.String(
            required=False,
            description="New relationship type: 'RELATIONSHIP' or 'NOTES'",
        )
        annotation_label_id = graphene.String(
            required=False, description="New annotation label ID"
        )
        corpus_id = graphene.String(required=False, description="New corpus ID")
        data = GenericScalar(required=False, description="Updated JSON data payload")

    ok = graphene.Boolean()
    document_relationship = graphene.Field(DocumentRelationshipType)
    message = graphene.String()

    @login_required
    def mutate(
        root,
        info,
        document_relationship_id,
        relationship_type=None,
        annotation_label_id=None,
        corpus_id=None,
        data=None,
    ) -> "UpdateDocumentRelationship":
        try:
            # Decode global ID
            doc_rel_pk = from_global_id(document_relationship_id)[1]

            # Use optimizer for IDOR-safe fetch with visibility check
            doc_relationship = (
                DocumentRelationshipQueryOptimizer.get_relationship_by_id(
                    user=info.context.user,
                    relationship_id=int(doc_rel_pk),
                )
            )

            # IDOR protection: same message for not found or not accessible
            if doc_relationship is None:
                return UpdateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Document relationship not found",
                )

            # Check UPDATE permission (inherited from source_doc + target_doc + corpus)
            if not DocumentRelationshipQueryOptimizer.user_has_permission(
                info.context.user,
                doc_relationship,
                "UPDATE",
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
                    try:
                        corpus = Corpus.objects.get(pk=corpus_pk)
                    except Corpus.DoesNotExist:
                        # IDOR-safe: same message for not found or no permission
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Corpus not found",
                        )

                    # Check permission on the new corpus (IDOR-safe message)
                    if not user_has_permission_for_obj(
                        info.context.user,
                        corpus,
                        PermissionTypes.UPDATE,
                        include_group_permissions=True,
                    ):
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Corpus not found",
                        )

                    # Validate both documents are in the new corpus
                    docs_in_corpus = (
                        corpus.get_documents()
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


class DeleteDocumentRelationship(graphene.Mutation):
    """
    Delete a document relationship.

    Permission requirements:
    - User must have DELETE permission on the document relationship
    - OR DELETE permission on BOTH source and target documents
    """

    class Arguments:
        document_relationship_id = graphene.String(
            required=True, description="ID of the document relationship to delete"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, document_relationship_id) -> "DeleteDocumentRelationship":
        try:
            # Decode global ID
            doc_rel_pk = from_global_id(document_relationship_id)[1]

            # Use optimizer for IDOR-safe fetch with visibility check
            doc_relationship = (
                DocumentRelationshipQueryOptimizer.get_relationship_by_id(
                    user=info.context.user,
                    relationship_id=int(doc_rel_pk),
                )
            )

            # IDOR protection: same message for not found or not accessible
            if doc_relationship is None:
                return DeleteDocumentRelationship(
                    ok=False, message="Document relationship not found"
                )

            # Check DELETE permission (inherited from source_doc + target_doc + corpus)
            if not DocumentRelationshipQueryOptimizer.user_has_permission(
                info.context.user,
                doc_relationship,
                "DELETE",
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


class DeleteDocumentRelationships(graphene.Mutation):
    """
    Delete multiple document relationships at once.

    Permission requirements:
    - User must have DELETE permission on each document relationship
    """

    class Arguments:
        document_relationship_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of document relationship IDs to delete",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    deleted_count = graphene.Int()

    @login_required
    def mutate(root, info, document_relationship_ids) -> "DeleteDocumentRelationships":
        user = info.context.user

        try:
            # Decode all IDs first
            relationship_pks = [
                int(from_global_id(gid)[1]) for gid in document_relationship_ids
            ]

            # Fetch all relationships in a single query (fixes N+1)
            visible_relationships = (
                DocumentRelationshipQueryOptimizer.get_visible_relationships(
                    user=user
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
                if not DocumentRelationshipQueryOptimizer.user_has_permission(
                    user,
                    doc_relationship,
                    "DELETE",
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
