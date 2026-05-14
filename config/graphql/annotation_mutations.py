"""
GraphQL mutations for annotation, relationship, and note operations.
"""

import logging

import graphene
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.base import DRFDeletion, DRFMutation
from config.graphql.graphene_types import (
    AnnotationType,
    NoteType,
    RelationInputType,
    RelationshipType,
    UserFeedbackType,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from config.graphql.serializers import AnnotationSerializer
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Note,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.types.enums import LabelType, PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


class RemoveAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.String(
            required=True, description="Id of the annotation that is to be deleted."
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, annotation_id) -> "RemoveAnnotation":
        try:
            user = info.context.user
            annotation_pk = from_global_id(annotation_id)[1]

            # Use visible_to_user for IDOR protection - unified error for not found/no permission
            try:
                annotation_obj = Annotation.objects.visible_to_user(user).get(
                    pk=annotation_pk
                )
            except Annotation.DoesNotExist:
                return RemoveAnnotation(
                    ok=False,
                    message="Annotation not found or you do not have permission to access it",
                )

            # Check if user has permission to delete this annotation
            # This now handles privacy-aware permissions for annotations with created_by_* fields
            if not user_has_permission_for_obj(
                user,
                annotation_obj,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            ):
                return RemoveAnnotation(
                    ok=False,
                    message="Annotation not found or you do not have permission to access it",
                )

            annotation_obj.delete()
            return RemoveAnnotation(ok=True, message="Annotation deleted successfully")
        except Exception as e:
            logger.error(f"Error deleting annotation {annotation_id}: {e}")
            return RemoveAnnotation(ok=False, message="An unexpected error occurred")


class RejectAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.ID(
            required=True, description="ID of the annotation to reject"
        )
        comment = graphene.String(description="Optional comment for the rejection")

    ok = graphene.Boolean()
    user_feedback = graphene.Field(UserFeedbackType)
    message = graphene.String()

    @login_required
    @transaction.atomic
    def mutate(root, info, annotation_id, comment=None) -> "RejectAnnotation":
        user = info.context.user
        annotation_pk = from_global_id(annotation_id)[1]

        # Use visible_to_user for IDOR protection - unified error for not found/no permission
        try:
            annotation = Annotation.objects.visible_to_user(user).get(pk=annotation_pk)
        except (ObjectDoesNotExist, Annotation.DoesNotExist):
            return RejectAnnotation(
                ok=False,
                user_feedback=None,
                message="Annotation not found or you do not have permission to access it",
            )

        # Check if user has COMMENT permission on this annotation
        # COMMENT permission respects document+corpus inheritance and corpus.allow_comments
        can_comment = user_has_permission_for_obj(
            user, annotation, PermissionTypes.COMMENT, include_group_permissions=True
        )

        if not can_comment:
            return RejectAnnotation(
                ok=False,
                user_feedback=None,
                message="Annotation not found or you do not have permission to access it",
            )

        user_feedback, created = UserFeedback.objects.get_or_create(
            commented_annotation=annotation,
            defaults={
                "creator": user,
                "approved": False,
                "rejected": True,
                "comment": comment or "",
            },
        )

        if not created:
            user_feedback.approved = False
            user_feedback.rejected = True
            user_feedback.comment = comment or user_feedback.comment
            user_feedback.save()

        set_permissions_for_obj_to_user(user, user_feedback, [PermissionTypes.CRUD])

        return RejectAnnotation(
            ok=True, user_feedback=user_feedback, message="Annotation rejected"
        )


class ApproveAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.ID(
            required=True, description="ID of the annotation to approve"
        )
        comment = graphene.String(description="Optional comment for the approval")

    ok = graphene.Boolean()
    user_feedback = graphene.Field(UserFeedbackType)
    message = graphene.String()

    @login_required
    @transaction.atomic
    def mutate(root, info, annotation_id, comment=None) -> "ApproveAnnotation":
        user = info.context.user
        annotation_pk = from_global_id(annotation_id)[1]

        # Use visible_to_user for IDOR protection - unified error for not found/no permission
        try:
            annotation = Annotation.objects.visible_to_user(user).get(pk=annotation_pk)
        except (ObjectDoesNotExist, Annotation.DoesNotExist):
            return ApproveAnnotation(
                ok=False,
                user_feedback=None,
                message="Annotation not found or you do not have permission to access it",
            )

        # Check if user has COMMENT permission on this annotation
        # COMMENT permission respects document+corpus inheritance and corpus.allow_comments
        can_comment = user_has_permission_for_obj(
            user, annotation, PermissionTypes.COMMENT, include_group_permissions=True
        )

        if not can_comment:
            return ApproveAnnotation(
                ok=False,
                user_feedback=None,
                message="Annotation not found or you do not have permission to access it",
            )

        user_feedback, created = UserFeedback.objects.get_or_create(
            commented_annotation=annotation,
            defaults={
                "creator": user,
                "approved": True,
                "rejected": False,
                "comment": comment or "",
            },
        )

        if not created:
            user_feedback.approved = True
            user_feedback.rejected = False
            user_feedback.comment = comment or user_feedback.comment
            user_feedback.save()

        set_permissions_for_obj_to_user(user, user_feedback, [PermissionTypes.CRUD])

        return ApproveAnnotation(
            ok=True, user_feedback=user_feedback, message="Annotation approved"
        )


_ANNOTATION_PARENT_NOT_FOUND_MSG = (
    "Document or corpus not found, or you do not have " "permission to annotate it."
)


def _resolve_annotation_parents(
    user, corpus_pk: int | str, document_pk: int | str
) -> tuple["Document", "Corpus"] | None:
    """Resolve and validate the (document, corpus) parents for a new annotation.

    Returns the (document, corpus) tuple when:
        - both rows are visible to the user,
        - the user has CREATE permission on the corpus,
        - the document is a current member of the corpus (via DocumentPath).

    Returns None on any failure so callers can surface a single uniform
    "not found" error and avoid leaking existence/permission state. The
    DocumentPath check closes a cross-corpus IDOR (user has visibility to
    doc D in corpus A and CREATE on corpus B → would otherwise be allowed
    to write `Annotation(document=D, corpus=B)`).
    """
    try:
        document = Document.objects.visible_to_user(user).get(pk=document_pk)
        corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
    except (Document.DoesNotExist, Corpus.DoesNotExist):
        return None

    if not user_has_permission_for_obj(
        user, corpus, PermissionTypes.CREATE, include_group_permissions=True
    ):
        return None

    if not DocumentPath.objects.filter(
        document=document, corpus=corpus, is_current=True, is_deleted=False
    ).exists():
        return None

    return document, corpus


class AddAnnotation(graphene.Mutation):
    class Arguments:
        json = GenericScalar(
            required=True, description="New-style JSON for multipage annotations"
        )
        page = graphene.Int(
            required=True, description="What page is this annotation on (0-indexed)"
        )
        raw_text = graphene.String(
            required=True, description="What is the raw text of the annotation?"
        )
        corpus_id = graphene.String(
            required=True, description="ID of the corpus this annotation is for."
        )
        document_id = graphene.String(
            required=True, description="Id of the document this annotation is on."
        )
        annotation_label_id = graphene.String(
            required=True,
            description="Id of the label that is applied via this annotation.",
        )
        annotation_type = graphene.Argument(
            graphene.Enum.from_enum(LabelType), required=True
        )
        long_description = graphene.String(
            required=False,
            description="Optional markdown description for this annotation.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    annotation = graphene.Field(AnnotationType)

    @login_required
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_LIGHT"))
    def mutate(
        root,
        info,
        json,
        page,
        raw_text,
        corpus_id,
        document_id,
        annotation_label_id,
        annotation_type,
        long_description=None,
    ) -> "AddAnnotation":
        corpus_pk = from_global_id(corpus_id)[1]
        document_pk = from_global_id(document_id)[1]
        label_pk = from_global_id(annotation_label_id)[1]

        user = info.context.user

        parents = _resolve_annotation_parents(user, corpus_pk, document_pk)
        if parents is None:
            return AddAnnotation(
                ok=False,
                annotation=None,
                message=_ANNOTATION_PARENT_NOT_FOUND_MSG,
            )
        document, corpus = parents

        annotation = Annotation(
            page=page,
            raw_text=raw_text,
            long_description=long_description,
            corpus_id=corpus.pk,
            document_id=document.pk,
            annotation_label_id=label_pk,
            creator=user,
            json=json,
            annotation_type=annotation_type.value,
        )
        annotation.save()
        set_permissions_for_obj_to_user(user, annotation, [PermissionTypes.CRUD])

        return AddAnnotation(
            ok=True, message="Annotation created", annotation=annotation
        )


class AddDocTypeAnnotation(graphene.Mutation):
    class Arguments:
        corpus_id = graphene.String(
            required=True, description="ID of the corpus this annotation is for."
        )
        document_id = graphene.String(
            required=True, description="Id of the document this annotation is on."
        )
        annotation_label_id = graphene.String(
            required=True,
            description="Id of the label that is applied via this annotation.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    annotation = graphene.Field(AnnotationType)

    @login_required
    def mutate(
        root, info, corpus_id, document_id, annotation_label_id
    ) -> "AddDocTypeAnnotation":
        corpus_pk = from_global_id(corpus_id)[1]
        document_pk = from_global_id(document_id)[1]
        annotation_label_pk = from_global_id(annotation_label_id)[1]

        user = info.context.user

        parents = _resolve_annotation_parents(user, corpus_pk, document_pk)
        if parents is None:
            return AddDocTypeAnnotation(
                ok=False,
                annotation=None,
                message=_ANNOTATION_PARENT_NOT_FOUND_MSG,
            )
        document, corpus = parents

        annotation = Annotation.objects.create(
            corpus_id=corpus.pk,
            document_id=document.pk,
            annotation_label_id=annotation_label_pk,
            creator=user,
        )
        set_permissions_for_obj_to_user(user, annotation, [PermissionTypes.CRUD])

        return AddDocTypeAnnotation(
            ok=True, message="Annotation created", annotation=annotation
        )


class RemoveRelationship(graphene.Mutation):
    class Arguments:
        relationship_id = graphene.String(
            required=True, description="Id of the relationship that is to be deleted."
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationship_id) -> "RemoveRelationship":
        try:
            user = info.context.user
            relationship_pk = from_global_id(relationship_id)[1]

            # Use visible_to_user for IDOR protection - unified error for not found/no permission
            try:
                relationship_obj = Relationship.objects.visible_to_user(user).get(
                    pk=relationship_pk
                )
            except Relationship.DoesNotExist:
                return RemoveRelationship(
                    ok=False,
                    message="Relationship not found or you do not have permission to access it",
                )

            # Check if user has permission to delete this relationship
            if not user_has_permission_for_obj(
                user,
                relationship_obj,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            ):
                return RemoveRelationship(
                    ok=False,
                    message="Relationship not found or you do not have permission to access it",
                )

            relationship_obj.delete()
            return RemoveRelationship(
                ok=True, message="Relationship deleted successfully"
            )
        except Exception as e:
            logger.error(f"Error deleting relationship {relationship_id}: {e}")
            return RemoveRelationship(ok=False, message="An unexpected error occurred")


class AddRelationship(graphene.Mutation):
    class Arguments:
        source_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the tokens in the source annotation",
        )
        target_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the target tokens in the label",
        )
        relationship_label_id = graphene.String(
            required=True, description="ID of the label for this relationship."
        )
        corpus_id = graphene.String(
            required=True, description="ID of the corpus for this relationship."
        )
        document_id = graphene.String(
            required=True, description="ID of the document for this relationship."
        )

    ok = graphene.Boolean()
    relationship = graphene.Field(RelationshipType)
    message = graphene.String()

    @login_required
    def mutate(
        root,
        info,
        source_ids,
        target_ids,
        relationship_label_id,
        corpus_id,
        document_id,
    ) -> "AddRelationship":
        user = info.context.user
        # Unified message blocks IDOR enumeration of corpora, documents, and
        # annotations the caller cannot see. Both "does not exist" and "no
        # permission" branches must collapse to this string.
        not_found_msg = (
            "Relationship target(s) not found or you do not have permission "
            "to create a relationship here."
        )

        try:
            # Cast each parsed pk to int so non-numeric payloads (a global ID
            # of "BogusType:not-an-int" decodes successfully but yields a
            # string pk) fail closed inside this try/except instead of later
            # at the queryset boundary. This keeps the IDOR surface flat:
            # every bad-input path collapses to ``not_found_msg``.
            source_pks = [
                int(from_global_id(graphene_id)[1]) for graphene_id in source_ids
            ]
            target_pks = [
                int(from_global_id(graphene_id)[1]) for graphene_id in target_ids
            ]
            relationship_label_pk = int(from_global_id(relationship_label_id)[1])
            corpus_pk = int(from_global_id(corpus_id)[1])
            document_pk = int(from_global_id(document_id)[1])
        except Exception:
            # Bad / unparseable / non-integer global IDs are indistinguishable
            # from not-found to keep the IDOR surface flat. ``Exception``
            # catches ``binascii.Error`` from ``from_global_id`` on
            # undecodable input AND ``ValueError`` from the ``int()`` cast.
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

        # Filter annotations through visible_to_user so unauthorized or
        # non-existent IDs collapse into the same "missing" branch. Comparing
        # counts catches both cases without echoing IDs back to the caller.
        source_annotations = Annotation.objects.visible_to_user(user).filter(
            id__in=source_pks
        )
        target_annotations = Annotation.objects.visible_to_user(user).filter(
            id__in=target_pks
        )
        if source_annotations.count() != len(
            set(source_pks)
        ) or target_annotations.count() != len(set(target_pks)):
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

        # Filter corpus through visible_to_user so a non-existent or
        # inaccessible corpus pk yields the same not-found branch as a
        # corpus the caller cannot CREATE in.
        try:
            corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
        except Corpus.DoesNotExist:
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

        if not user_has_permission_for_obj(
            user,
            corpus,
            PermissionTypes.CREATE,
            include_group_permissions=True,
        ):
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

        # Document visibility check: without this, a caller with CREATE on
        # `corpus` could create a Relationship pointing at any document_id
        # they happen to guess — including documents in a corpus they cannot
        # see. Collapse the failure into the same not-found message to keep
        # the IDOR surface flat with the source/target/corpus checks above.
        if not Document.objects.visible_to_user(user).filter(pk=document_pk).exists():
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

        # Relationship label visibility check: closes the residual oracle
        # where a caller could probe private ``AnnotationLabel`` IDs by
        # supplying them and observing whether the create succeeds vs.
        # raises an FK constraint. Same not-found message.
        if (
            not AnnotationLabel.objects.visible_to_user(user)
            .filter(pk=relationship_label_pk)
            .exists()
        ):
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

        try:
            relationship = Relationship.objects.create(
                creator=user,
                relationship_label_id=relationship_label_pk,
                corpus_id=corpus_pk,
                document_id=document_pk,
            )
            set_permissions_for_obj_to_user(user, relationship, [PermissionTypes.CRUD])
            relationship.target_annotations.set(target_annotations)
            relationship.source_annotations.set(source_annotations)
        except Exception:
            # Don't surface ORM or constraint messages to the caller — they
            # leak schema/existence information. Log server-side instead.
            # ``logger.exception`` already appends the traceback + message,
            # so we omit the redundant exception variable.
            logger.exception("Error creating relationship")
            return AddRelationship(
                ok=False,
                relationship=None,
                message="Error creating relationship.",
            )

        return AddRelationship(
            ok=True,
            relationship=relationship,
            message="Relationship created successfully",
        )


class RemoveRelationships(graphene.Mutation):
    class Arguments:
        relationship_ids = graphene.List(graphene.String)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationship_ids) -> "RemoveRelationships":
        user = info.context.user
        # Unified error message prevents IDOR enumeration of relationship IDs
        not_found_msg = (
            "Relationship not found or you do not have permission to access it"
        )
        for graphene_id in relationship_ids:
            pk = from_global_id(graphene_id)[1]
            try:
                relationship = Relationship.objects.visible_to_user(user).get(pk=pk)
            except Relationship.DoesNotExist:
                return RemoveRelationships(ok=False, message=not_found_msg)
            if not user_has_permission_for_obj(
                user,
                relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            ):
                return RemoveRelationships(ok=False, message=not_found_msg)
            relationship.delete()
        return RemoveRelationships(ok=True, message="Success")


class UpdateRelationship(graphene.Mutation):
    """
    Update an existing relationship by adding or removing annotations
    from source or target sets.
    """

    class Arguments:
        relationship_id = graphene.String(
            required=True, description="ID of the relationship to update"
        )
        add_source_ids = graphene.List(
            graphene.String,
            required=False,
            description="List of annotation IDs to add as sources",
        )
        add_target_ids = graphene.List(
            graphene.String,
            required=False,
            description="List of annotation IDs to add as targets",
        )
        remove_source_ids = graphene.List(
            graphene.String,
            required=False,
            description="List of annotation IDs to remove from sources",
        )
        remove_target_ids = graphene.List(
            graphene.String,
            required=False,
            description="List of annotation IDs to remove from targets",
        )

    ok = graphene.Boolean()
    relationship = graphene.Field(RelationshipType)
    message = graphene.String()

    @login_required
    def mutate(
        root,
        info,
        relationship_id,
        add_source_ids=None,
        add_target_ids=None,
        remove_source_ids=None,
        remove_target_ids=None,
    ) -> "UpdateRelationship":
        user = info.context.user
        # Unified error message prevents IDOR enumeration of relationship/annotation IDs
        not_found_msg = (
            "Relationship not found or you do not have permission to access it"
        )
        try:
            relationship_pk = from_global_id(relationship_id)[1]
            try:
                relationship = Relationship.objects.visible_to_user(user).get(
                    pk=relationship_pk
                )
            except Relationship.DoesNotExist:
                return UpdateRelationship(
                    ok=False,
                    relationship=None,
                    message=not_found_msg,
                )

            # Check UPDATE permission on the relationship
            if not user_has_permission_for_obj(
                user,
                relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            ):
                return UpdateRelationship(
                    ok=False,
                    relationship=None,
                    message=not_found_msg,
                )

            # Filter annotations through visible_to_user so unauthorized IDs are dropped
            # at the DB layer instead of after a per-row permission check
            def _load_visible_annotations(global_ids):
                pks = {from_global_id(g)[1] for g in global_ids}
                return (
                    list(Annotation.objects.visible_to_user(user).filter(id__in=pks)),
                    pks,
                )

            # Add source annotations. ``visible_to_user`` already enforces
            # READ — every returned annotation is by definition readable, so
            # no per-row permission re-check is needed. Compare resolved PKs
            # against requested PKs as sets so the equivalence is unambiguous
            # under duplicate input IDs.
            if add_source_ids:
                source_annotations, source_pks = _load_visible_annotations(
                    add_source_ids
                )
                if {str(a.pk) for a in source_annotations} != source_pks:
                    return UpdateRelationship(
                        ok=False,
                        relationship=None,
                        message=not_found_msg,
                    )
                relationship.source_annotations.add(*source_annotations)

            # Add target annotations (same READ-via-visibility guarantee).
            if add_target_ids:
                target_annotations, target_pks = _load_visible_annotations(
                    add_target_ids
                )
                if {str(a.pk) for a in target_annotations} != target_pks:
                    return UpdateRelationship(
                        ok=False,
                        relationship=None,
                        message=not_found_msg,
                    )
                relationship.target_annotations.add(*target_annotations)

            # Removal is gated by UPDATE on the relationship itself (already
            # checked above). Restrict removal to annotations actually attached
            # to this relationship to avoid leaking the existence of unrelated
            # annotation IDs the caller may not be able to see.
            if remove_source_ids:
                source_pks = [from_global_id(sid)[1] for sid in remove_source_ids]
                relationship.source_annotations.remove(
                    *relationship.source_annotations.filter(id__in=source_pks)
                )

            if remove_target_ids:
                target_pks = [from_global_id(tid)[1] for tid in remove_target_ids]
                relationship.target_annotations.remove(
                    *relationship.target_annotations.filter(id__in=target_pks)
                )

            relationship.save()

            return UpdateRelationship(
                ok=True,
                relationship=relationship,
                message="Relationship updated successfully",
            )

        except Exception as e:
            logger.error(f"Error updating relationship: {e}")
            return UpdateRelationship(
                ok=False,
                relationship=None,
                message=f"Error updating relationship: {str(e)}",
            )


class UpdateAnnotation(DRFMutation):
    class IOSettings:
        pk_fields = ["annotation_label"]
        lookup_field = "id"
        serializer = AnnotationSerializer
        model = Annotation
        graphene_model = AnnotationType

    class Arguments:
        id = graphene.String(required=True)
        page = graphene.Int()
        raw_text = graphene.String()
        long_description = graphene.String()
        json = GenericScalar()
        annotation_label = graphene.String()


class UpdateRelations(graphene.Mutation):
    class Arguments:
        relationships = graphene.List(RelationInputType)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationships) -> "UpdateRelations":
        user = info.context.user
        # Unified error message prevents IDOR enumeration of relationship IDs
        not_found_msg = (
            "Relationship not found or you do not have permission to access it"
        )
        for relationship in relationships:
            pk = from_global_id(relationship["id"])[1]
            source_pks = list(
                map(
                    lambda graphene_id: from_global_id(graphene_id)[1],
                    relationship["source_ids"],
                )
            )
            target_pks = list(
                map(
                    lambda graphene_id: from_global_id(graphene_id)[1],
                    relationship["target_ids"],
                )
            )
            relationship_label_pk = from_global_id(
                relationship["relationship_label_id"]
            )[1]
            corpus_pk = from_global_id(relationship["corpus_id"])[1]
            document_pk = from_global_id(relationship["document_id"])[1]

            try:
                relationship = Relationship.objects.visible_to_user(user).get(id=pk)
            except Relationship.DoesNotExist:
                return UpdateRelations(ok=False, message=not_found_msg)
            if not user_has_permission_for_obj(
                user,
                relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            ):
                return UpdateRelations(ok=False, message=not_found_msg)

            relationship.relationship_label_id = relationship_label_pk
            relationship.document_id = document_pk
            relationship.corpus_id = corpus_pk
            relationship.save()

            relationship.target_annotations.set(target_pks)
            relationship.source_annotations.set(source_pks)

        return UpdateRelations(ok=True, message="Success")


class UpdateNote(graphene.Mutation):
    """
    Mutation to update a note's content, creating a new version in the process.
    Only the note creator can update their notes.
    """

    class Arguments:
        note_id = graphene.ID(required=True, description="ID of the note to update")
        new_content = graphene.String(
            required=True, description="New markdown content for the note"
        )
        title = graphene.String(
            required=False, description="Optional new title for the note"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(NoteType)
    version = graphene.Int(description="The new version number after update")

    @login_required
    def mutate(root, info, note_id, new_content, title=None) -> "UpdateNote":
        from opencontractserver.annotations.models import Note

        try:
            user = info.context.user
            note_pk = from_global_id(note_id)[1]

            # Unified "not found" message avoids leaking note existence to non-creators
            not_found_msg = "Note not found or you do not have permission to update it."

            # Filter through visible_to_user first so unauthorized IDs hit the same
            # branch as truly-missing IDs
            try:
                note = Note.objects.visible_to_user(user).get(pk=note_pk)
            except Note.DoesNotExist:
                return UpdateNote(
                    ok=False, message=not_found_msg, obj=None, version=None
                )

            # Only the creator may edit a note (visibility != edit rights)
            if note.creator != user:
                return UpdateNote(
                    ok=False,
                    message=not_found_msg,
                    obj=None,
                    version=None,
                )

            # Update title if provided
            if title is not None:
                note.title = title

            # Use the version_up method to create a new version
            revision = note.version_up(new_content=new_content, author=user)

            if revision is None:
                # No changes were made
                return UpdateNote(
                    ok=True,
                    message="No changes detected. Note remains at current version.",
                    obj=note,
                    version=note.revisions.count(),
                )

            # Refresh the note to get the updated state
            note.refresh_from_db()

            return UpdateNote(
                ok=True,
                message=f"Note updated successfully. Now at version {revision.version}.",
                obj=note,
                version=revision.version,
            )

        except Exception as e:
            logger.error(f"Error updating note: {e}")
            return UpdateNote(
                ok=False,
                message=f"Failed to update note: {str(e)}",
                obj=None,
                version=None,
            )


class DeleteNote(DRFDeletion):
    """
    Mutation to delete a note. Only the creator can delete their notes.
    """

    class IOSettings:
        model = Note
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class CreateNote(graphene.Mutation):
    """
    Mutation to create a new note for a document.
    """

    class Arguments:
        document_id = graphene.ID(
            required=True, description="ID of the document this note is for"
        )
        corpus_id = graphene.ID(
            required=False,
            description="Optional ID of the corpus this note is associated with",
        )
        title = graphene.String(required=True, description="Title of the note")
        content = graphene.String(
            required=True, description="Markdown content of the note"
        )
        parent_id = graphene.ID(
            required=False,
            description="Optional ID of parent note for hierarchical notes",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(NoteType)

    @login_required
    def mutate(
        root, info, document_id, title, content, corpus_id=None, parent_id=None
    ) -> "CreateNote":
        from opencontractserver.annotations.models import Note
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        try:
            user = info.context.user
            document_pk = from_global_id(document_id)[1]

            # Get the document with visibility filter to prevent IDOR
            document = Document.objects.visible_to_user(user).get(pk=document_pk)

            # Prepare note data
            note_data = {
                "document": document,
                "title": title,
                "content": content,
                "creator": user,
            }

            # Handle optional corpus with visibility filter
            if corpus_id:
                corpus_pk = from_global_id(corpus_id)[1]
                corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
                note_data["corpus"] = corpus

            # Handle optional parent note with visibility filter
            if parent_id:
                parent_pk = from_global_id(parent_id)[1]
                parent_note = Note.objects.visible_to_user(user).get(pk=parent_pk)
                note_data["parent"] = parent_note

            # Create the note
            note = Note.objects.create(**note_data)

            # Set permissions
            set_permissions_for_obj_to_user(user, note, [PermissionTypes.CRUD])

            return CreateNote(ok=True, message="Note created successfully!", obj=note)

        except Document.DoesNotExist:
            return CreateNote(ok=False, message="Document not found.", obj=None)
        except Corpus.DoesNotExist:
            return CreateNote(ok=False, message="Corpus not found.", obj=None)
        except Note.DoesNotExist:
            return CreateNote(ok=False, message="Parent note not found.", obj=None)
        except Exception as e:
            logger.error(f"Error creating note: {e}")
            return CreateNote(
                ok=False, message=f"Failed to create note: {str(e)}", obj=None
            )
