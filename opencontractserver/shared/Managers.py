from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.db.models import FileField, Manager, Prefetch, Q, QuerySet

from opencontractserver.shared.QuerySets import (
    AnnotationQuerySet,
    DocumentQuerySet,
    NoteQuerySet,
    PermissionQuerySet,
    UserFeedbackQuerySet,
)

# Re-exported so callers receiving "a permissioned manager" can annotate
# against ``PermissionedQueryManagerProtocol`` instead of any concrete
# manager class.  Every visibility manager defined below satisfies the
# ``visible_to_user(user) -> QuerySet`` contract.
from opencontractserver.types.protocols import (  # noqa: F401
    PermissionedQueryManagerProtocol,
)

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    from opencontractserver.documents.models import Document

    User = get_user_model()
else:
    from django.contrib.auth.models import AbstractUser as User

logger = logging.getLogger(__name__)


def _apply_document_prefetches(
    queryset: QuerySet,
    user: User | None,
    lightweight: bool = False,
    with_doc_label_annotations: bool = False,
) -> QuerySet:
    """
    Apply Document-specific select_related and prefetch_related optimizations.

    Shared by BaseVisibilityManager (for generic model dispatch) and
    DocumentManager (for custom permission filtering) to avoid duplication.

    ``lightweight`` skips ONLY the heavy per-document fan-outs (full
    doc_annotations, rows, source/target relationships, notes). Cheap JOINs
    (creator, parent, user_lock) and user-scoped guardian permission prefetches
    are applied unconditionally because the corresponding GraphQL fields
    (``creator``, ``myPermissions``, version metadata) are commonly requested
    even on list views — leaving them unprefetched produces an N+1 storm where
    every list row issues 2-3 extra round trips. See
    ``resolve_my_permissions`` in
    ``config/graphql/permissioning/permission_annotator/mixins.py`` for the
    consumer of ``_prefetched_user_perms``.

    ``with_doc_label_annotations`` opts in to a focused prefetch of the
    document's ``DOC_TYPE_LABEL`` annotations into
    ``_prefetched_doc_annotations``. ``resolve_doc_annotations_optimized``
    (config/graphql/custom_resolvers.py) prefers that attribute when present,
    so this short-circuits the per-document
    ``AnnotationQueryOptimizer.get_document_annotations`` call that the
    list-view badge query (``GET_DOCUMENTS`` with ``annotateDocLabels: true``)
    otherwise triggers per row. The flag is only consulted in lightweight
    mode — the full prefetch path already loads every doc_annotation, so a
    focused prefetch on top would be redundant work.
    """
    queryset = queryset.select_related("creator", "user_lock", "parent")

    if user and not user.is_anonymous and not user.is_superuser:
        from opencontractserver.documents.models import DocumentUserObjectPermission

        queryset = queryset.prefetch_related(
            Prefetch(
                "documentuserobjectpermission_set",
                queryset=DocumentUserObjectPermission.objects.filter(
                    user_id=user.id
                ).select_related("permission"),
                to_attr="_prefetched_user_perms",
            ),
            "documentgroupobjectpermission_set__permission",
            "documentgroupobjectpermission_set__group",
        )

    if not lightweight:
        from opencontractserver.annotations.models import Annotation

        queryset = queryset.prefetch_related(
            Prefetch(
                "doc_annotations",
                queryset=Annotation.objects.select_related(
                    "annotation_label", "corpus", "analysis", "creator"
                ),
                to_attr="_prefetched_doc_annotations",
            ),
            "rows",
            "source_relationships",
            "target_relationships",
            "notes",
        )
    elif with_doc_label_annotations:
        from opencontractserver.annotations.models import DOC_TYPE_LABEL, Annotation

        queryset = queryset.prefetch_related(
            Prefetch(
                "doc_annotations",
                queryset=Annotation.objects.filter(
                    annotation_label__label_type=DOC_TYPE_LABEL
                ).select_related("annotation_label", "corpus"),
                to_attr="_prefetched_doc_annotations",
            )
        )

    return queryset


class BaseVisibilityManager(Manager):
    """
    Base manager that implements the standard visibility logic for non-annotations and non-relationships .

    This manager provides a secure default implementation of visible_to_user that:
    1. Allows superusers to see everything
    2. For anonymous users: only public objects
    3. For authenticated users: public objects, objects they created, or objects explicitly shared with them

    This is the SECURE fallback logic that should be used by all models that don't have
    more specific permission requirements.
    """

    def visible_to_user(
        self,
        user=None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ) -> QuerySet:
        """
        Returns queryset filtered to only objects visible to the user.

        Visibility rules:
        - Superusers see everything
        - Anonymous users see only public objects
        - Authenticated users see: public objects, objects they created, or objects with explicit permissions

        Args:
            user: The requesting user (None treated as anonymous).
            lightweight: If True, skip heavy prefetch_related lookups for
                Document queries (doc_annotations, rows, relationships,
                notes). Useful for queries that only need basic fields
                like id, title, slug, icon, fileType, creator.
        """

        from django.apps import apps

        queryset = self.get_queryset()

        # Handle None user as anonymous
        if user is None:
            user = AnonymousUser()

        # Superusers see everything (ordered by created for consistency)
        if hasattr(user, "is_superuser") and user.is_superuser:
            return queryset.order_by("created")

        # Anonymous users only see public items
        if user.is_anonymous:
            return queryset.filter(is_public=True)

        try:
            # Get objects the user has read permission for via Guardian
            model_name = self.model._meta.model_name
            app_label = self.model._meta.app_label

            # Fallback to legacy logic with security warning
            logger.debug(
                f"Using unoptimized visible_to_user permission logic for {model_name} "
                f"(app: {app_label}, model: {model_name})"
            )

            logger.debug(
                f"Consider implementing tuned visible_to_user method on {model_name} manager"
            )

            # === TOP_LEVEL PERMISSION LOGIC ===
            # This logic is for objs that don't follow some parent permissions logic

            # Get the base queryset first (only stuff given user CAN see)
            queryset = self.model.objects.none()  # Start with an empty queryset

            # Handle the case where user resolution failed explicitly
            if user is None:
                queryset = self.model.objects.filter(is_public=True)
            elif user.is_superuser:
                # Superusers see everything, no filtering needed
                queryset = self.model.objects.all().order_by("created")
            elif user.is_anonymous:
                # Anonymous users only see public items
                queryset = self.model.objects.filter(is_public=True)
            else:  # Authenticated, non-superuser
                permission_model_name = f"{model_name}userobjectpermission"
                try:
                    permission_model_type = apps.get_model(
                        app_label, permission_model_name
                    )
                    # Optimize: Get IDs with permissions first, then use IN clause
                    permitted_ids = permission_model_type.objects.filter(
                        permission__codename=f"read_{model_name}", user_id=user.id
                    ).values_list("content_object_id", flat=True)

                    # Build the optimized query using simpler conditions
                    queryset = self.model.objects.filter(
                        Q(creator_id=user.id)
                        | Q(is_public=True)
                        | Q(id__in=permitted_ids)
                    )
                except LookupError:
                    logger.warning(
                        f"Permission model {app_label}.{permission_model_name}"
                        " not found. Falling back to creator/public check."
                    )
                    # Fallback if permission model doesn't exist (might happen for simpler models)
                    queryset = self.model.objects.filter(
                        Q(creator_id=user.id) | Q(is_public=True)
                    )

            # --- Apply Performance Optimizations Based on Model Type ---
            if model_name.upper() == "CORPUS":
                logger.debug("Applying Corpus specific optimizations")
                queryset = queryset.select_related(
                    "creator",
                    "label_set",
                    "user_lock",  # If user_lock info is displayed
                )
                # NOTE: documents M2M was removed in favor of DocumentPath
                # Document counts are now computed via DocumentPath subqueries
            elif model_name.upper() == "DOCUMENT":
                logger.debug("Applying Document specific optimizations")
                queryset = _apply_document_prefetches(
                    queryset,
                    user,
                    lightweight,
                    with_doc_label_annotations=with_doc_label_annotations,
                )
            # Add elif blocks here for other models needing specific optimizations

            # Apply distinct *after* optimizations only when necessary.
            # The permission logic with __in might introduce duplicates for authenticated users.
            # Skip distinct for public/superuser queries where it's not needed.
            if user and not user.is_anonymous and not user.is_superuser:
                # Only apply distinct for authenticated non-superuser users where permission JOINs occur
                queryset = queryset.distinct()

            return queryset

        except (ImportError, Exception) as e:
            # Fall back to creator/public check only if Guardian not available or error
            logger.debug(
                f"Could not use Guardian permissions for {self.model.__name__}: {e}. "
                f"Using creator/public filtering only."
            )
            queryset = queryset.filter(Q(creator_id=user.id) | Q(is_public=True))

        return queryset.distinct()


class PermissionManager(BaseVisibilityManager):
    """
    Manager that uses PermissionQuerySet which has its own visible_to_user implementation.
    Inherits from BaseVisibilityManager but overrides to use PermissionQuerySet's version.
    """

    def get_queryset(self) -> PermissionQuerySet:
        return PermissionQuerySet(self.model, using=self._db)

    def for_user(
        self, user: User, perm: str, extra_conditions: Q | None = None
    ) -> PermissionQuerySet:
        return self.get_queryset().for_user(user, perm, extra_conditions)

    def visible_to_user(self, user: Any) -> PermissionQuerySet:
        """
        Returns queryset filtered by user permission via PermissionQuerySet.
        This overrides BaseVisibilityManager's implementation to use
        PermissionQuerySet's simpler visible_to_user logic.
        """
        return self.get_queryset().visible_to_user(user)


class UserFeedbackManager(BaseVisibilityManager):
    def get_queryset(self) -> UserFeedbackQuerySet:
        return UserFeedbackQuerySet(self.model, using=self._db)

    def visible_to_user(self, user: User) -> QuerySet:
        """Delegate to the queryset's visible_to_user method"""
        return self.get_queryset().visible_to_user(user)

    def get_or_none(self, *args: Any, **kwargs: Any) -> Any | None:
        try:
            return self.get(*args, **kwargs)
        except self.model.DoesNotExist:
            return None

    def approved(self) -> UserFeedbackQuerySet:
        return self.get_queryset().approved()

    def rejected(self) -> UserFeedbackQuerySet:
        return self.get_queryset().rejected()

    def pending(self) -> UserFeedbackQuerySet:
        return self.get_queryset().pending()

    def recent(self, days: int = 30) -> UserFeedbackQuerySet:
        return self.get_queryset().recent(days)

    def with_comments(self) -> UserFeedbackQuerySet:
        return self.get_queryset().with_comments()

    def by_creator(self, creator: User) -> UserFeedbackQuerySet:
        return self.get_queryset().by_creator(creator)

    def search(self, query: str) -> UserFeedbackQuerySet:
        return self.get_queryset().filter(
            Q(comment__icontains=query) | Q(markdown__icontains=query)
        )


class DocumentManager(BaseVisibilityManager):
    """
    Extends PermissionManager to return a DocumentQuerySet
    that supports vector searching via the mixin.
    """

    def get_queryset(self) -> DocumentQuerySet:
        return DocumentQuerySet(self.model, using=self._db)

    def visible_to_user(
        self,
        user: Any | None = None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ) -> QuerySet:
        """
        Delegate permission filtering to DocumentQuerySet (which includes
        public-corpus logic) then apply the shared prefetch optimisations.

        See ``_apply_document_prefetches`` for the meaning of
        ``with_doc_label_annotations``.
        """
        from django.contrib.auth.models import AnonymousUser

        if user is None:
            user = AnonymousUser()

        queryset = self.get_queryset().visible_to_user(user)
        return _apply_document_prefetches(
            queryset,
            user,
            lightweight,
            with_doc_label_annotations=with_doc_label_annotations,
        )

    def search_by_embedding(
        self, query_vector: list[float], embedder_path: str, top_k: int = 10
    ) -> list[Any]:
        """
        Convenience method so you can do:
            Document.objects.search_by_embedding([...])
        directly.
        """
        return self.get_queryset().search_by_embedding(
            query_vector, embedder_path, top_k
        )

    def unique_blob_paths(self, doc: Document) -> set[str]:
        """Return the subset of file-field blob paths on ``doc`` that
        are NOT referenced by any other Document row.

        Corpus-isolated copies created via ``Corpus.add_document`` share
        blob field values with their source by design (Rule I3). Any
        code that wants to delete a blob from storage MUST consult this
        method first and skip paths that are still in use elsewhere —
        otherwise it silently destroys files that other Documents
        depend on (issue #1464).

        The blob-field list is derived from ``Document._meta`` so adding
        a new ``FileField`` on the model extends coverage automatically.

        Args:
            doc: The Document whose blob paths we're auditing.

        Returns:
            Set of blob names (storage keys) that are referenced
            *only* by ``doc``. Safe to delete from storage. Empty/
            unset fields are omitted.
        """
        blob_fields: list[str] = [
            field.name
            for field in doc._meta.get_fields()
            if isinstance(field, FileField)
        ]

        unique: set[str] = set()
        for field_name in blob_fields:
            file_field = getattr(doc, field_name)
            if not file_field:
                continue
            blob_name = file_field.name
            if not blob_name:
                continue
            shared = self.filter(**{field_name: blob_name}).exclude(pk=doc.pk).exists()
            if not shared:
                unique.add(blob_name)
        return unique


class AnnotationManager(PermissionManager.from_queryset(AnnotationQuerySet)):
    """
    Custom Manager for the Annotation model that uses:
      - PermissionManager (from_queryset)
      - AnnotationQuerySet (with permission checks, CTE support, vector search)
    """

    def get_queryset(self) -> AnnotationQuerySet:
        return AnnotationQuerySet(self.model, using=self._db)

    def for_user(
        self, user: User, perm: str, extra_conditions: Q | None = None
    ) -> AnnotationQuerySet:
        """
        Filters the queryset based on user permissions.
        """
        return self.get_queryset().for_user(user, perm, extra_conditions)

    def search_by_embedding(
        self, query_vector: list[float], embedder_path: str, top_k: int = 10
    ) -> list[Any]:
        """
        If using VectorSearchViaEmbeddingMixin in your AnnotationQuerySet,
        you can call this convenience method just like:
            Annotation.objects.search_by_embedding([0.1, 0.2, ...], "xx-embedder", top_k=10)
        """
        return self.get_queryset().search_by_embedding(
            query_vector, embedder_path, top_k
        )


class NoteManager(PermissionManager.from_queryset(NoteQuerySet)):
    """
    Custom Manager for the Note model that uses:
      - PermissionManager (from_queryset)
      - NoteQuerySet (with permission checks, CTE support, vector search)
    """

    def get_queryset(self) -> NoteQuerySet:
        return NoteQuerySet(self.model, using=self._db)

    def for_user(
        self, user: User, perm: str, extra_conditions: Q | None = None
    ) -> NoteQuerySet:
        """
        Filters the queryset based on user permissions.
        """
        return self.get_queryset().for_user(user, perm, extra_conditions)

    def search_by_embedding(
        self, query_vector: list[float], embedder_path: str, top_k: int = 10
    ) -> list[Any]:
        """
        If using VectorSearchViaEmbeddingMixin in your NoteQuerySet,
        you can call:
            Note.objects.search_by_embedding([0.1, 0.2, ...], "xx-embedder", top_k=10)
        """
        return self.get_queryset().search_by_embedding(
            query_vector, embedder_path, top_k
        )


class EmbeddingManager(BaseVisibilityManager):
    """
    Manager for Embedding that can store or update embeddings
    without creating accidental duplicates for the same dimension,
    embedder_path, and parent references (document/annotation/note).
    """

    def _get_vector_field_name(self, dimension: int) -> str:
        if dimension == 384:
            return "vector_384"
        elif dimension == 768:
            return "vector_768"
        elif dimension == 1024:
            return "vector_1024"
        elif dimension == 1536:
            return "vector_1536"
        elif dimension == 2048:
            return "vector_2048"
        elif dimension == 3072:
            return "vector_3072"
        elif dimension == 4096:
            return "vector_4096"
        raise ValueError(f"Unsupported embedding dimension: {dimension}")

    def store_embedding(
        self,
        *,
        creator: User,
        dimension: int,
        vector: list[float],
        embedder_path: str,
        document_id: int | None = None,
        annotation_id: int | None = None,
        note_id: int | None = None,
        conversation_id: int | None = None,
        message_id: int | None = None,
    ) -> Any:
        """
        Create or update an Embedding, referencing exactly one of:
        Document, Annotation, Note, Conversation, or ChatMessage.
        If an Embedding already exists for (embedder_path + parent_id), update its vector field
        instead of creating a new record.

        This method handles race conditions atomically: if a concurrent worker creates
        the same embedding between our check and create, we catch the IntegrityError
        and update the existing record instead.

        Note: We use filter() instead of visible_to_user() for existence checks because
        unique constraints apply regardless of who created the embedding. Permission
        filtering would cause us to miss embeddings created by other users, leading to
        constraint violations.
        """
        if not any([document_id, annotation_id, note_id, conversation_id, message_id]):
            raise ValueError(
                "Must provide one of document_id, annotation_id, note_id, conversation_id, or message_id."
            )

        field_name = self._get_vector_field_name(dimension)

        # Build lookup kwargs for the unique constraint
        lookup = {
            "embedder_path": embedder_path,
            "document_id": document_id,
            "annotation_id": annotation_id,
            "note_id": note_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
        }

        # Check for existing embedding without permission filtering.
        # The unique constraint applies regardless of who created the embedding.
        embedding = self.filter(**lookup).first()

        if embedding:
            setattr(embedding, field_name, vector)
            embedding.save(update_fields=[field_name, "modified"])
            return embedding

        # Try to create a new embedding. If a race condition causes a constraint
        # violation (another worker created the same embedding between our check
        # and create), catch the IntegrityError and update the existing record.
        try:
            return self.create(
                creator=creator,
                **lookup,
                **{field_name: vector},
            )
        except IntegrityError:
            # Race condition: another worker created the embedding first.
            # Fetch the existing one and update it.
            logger.info(
                f"Race condition in store_embedding: embedding for {lookup} was created "
                f"by another worker. Fetching and updating instead."
            )
            embedding = self.get(**lookup)
            setattr(embedding, field_name, vector)
            embedding.save(update_fields=[field_name, "modified"])
            return embedding
