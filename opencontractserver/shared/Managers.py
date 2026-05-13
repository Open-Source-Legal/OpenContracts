from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import IntegrityError
from django.db.models import Manager, Prefetch, Q, QuerySet

from opencontractserver.shared.prefetch_attrs import (
    user_group_perm_attr,
    user_perm_attr,
)
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
    from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


def _apply_document_prefetches(
    queryset: QuerySet,
    user: Any,
    lightweight: bool = False,
    with_doc_label_annotations: bool = False,
) -> QuerySet:
    """Apply Document-specific select_related/prefetch_related optimizations.

    Shared by ``BaseVisibilityManager`` and ``DocumentManager``. ``lightweight``
    skips heavy fan-outs (full doc_annotations, rows, relationships, notes) but
    keeps cheap JOINs and user-scoped guardian permission prefetches — fields
    like ``myPermissions`` are commonly requested even on list views.
    Permission prefetches land on each instance under user-id-suffixed attrs
    (see ``shared/prefetch_attrs.py``); consumed by ``user_has_permission_for_obj``
    and ``resolve_my_permissions``. ``with_doc_label_annotations`` opts in to a
    focused prefetch of ``DOC_TYPE_LABEL`` annotations for list-view badges
    (only honoured in lightweight mode).
    """
    queryset = queryset.select_related("creator", "user_lock", "parent")

    if user and not user.is_anonymous and not user.is_superuser:
        from opencontractserver.documents.models import (
            DocumentGroupObjectPermission,
            DocumentUserObjectPermission,
        )

        # Pass the queryset (not ``list(...)``) so Django emits a SQL subquery
        # — async-safe; ``list(...)`` would raise SynchronousOnlyOperation.
        user_group_ids = user.groups.values_list("id", flat=True)

        queryset = queryset.prefetch_related(
            Prefetch(
                "documentuserobjectpermission_set",
                queryset=DocumentUserObjectPermission.objects.filter(
                    user_id=user.id
                ).select_related("permission"),
                to_attr=user_perm_attr(user.id),
            ),
            Prefetch(
                "documentgroupobjectpermission_set",
                queryset=DocumentGroupObjectPermission.objects.filter(
                    group_id__in=user_group_ids
                ).select_related("permission"),
                to_attr=user_group_perm_attr(user.id),
            ),
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
        user: Any = None,
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

        # ``self.model`` is typed as ``type[_T]`` (a TypeVar bound on
        # ``Manager``), so mypy doesn't know it has ``.objects`` /
        # ``.DoesNotExist``.  Concrete subclasses always do at runtime,
        # so the cast just informs mypy of what we already know.
        # Switching to ``self.model._default_manager`` would change call
        # semantics for models that override ``objects``.
        model_cls: Any = cast(Any, self.model)

        # ``Options.model_name`` is Optional only for abstract models.
        # Raise *outside* the broad except below so the abstract-model bug
        # surfaces instead of silently degrading into a creator/public
        # fallback. Use an explicit raise (not ``assert``) so the guard
        # survives ``python -O`` and never lets None propagate.
        model_name = self.model._meta.model_name
        if model_name is None:
            raise RuntimeError(
                f"Concrete manager invoked on abstract model {self.model}"
            )
        app_label = self.model._meta.app_label

        try:

            # Fallback to legacy logic with security warning
            logger.debug(
                f"Using unoptimized visible_to_user permission logic for {model_name} "
                f"(app: {app_label}, model: {model_name})"
            )

            logger.debug(
                f"Consider implementing tuned visible_to_user method on {model_name} manager"
            )

            # === TOP_LEVEL PERMISSION LOGIC ===
            # By this point ``user`` is guaranteed to be authenticated and
            # non-superuser — None / superuser / anonymous all returned early
            # at the top of the method, so the only path that lands here is
            # the authenticated-non-superuser case.
            # Initialize an empty queryset so the outer ``except`` handler
            # below has a defined fallback if the inner permission lookup
            # raises something other than ``LookupError``.
            queryset = model_cls.objects.none()

            permission_model_name = f"{model_name}userobjectpermission"
            try:
                permission_model_type = apps.get_model(app_label, permission_model_name)
                # Optimize: Get IDs with permissions first, then use IN clause
                permitted_ids = permission_model_type.objects.filter(
                    permission__codename=f"read_{model_name}", user_id=user.id
                ).values_list("content_object_id", flat=True)

                # Build the optimized query using simpler conditions
                queryset = model_cls.objects.filter(
                    Q(creator_id=user.id) | Q(is_public=True) | Q(id__in=permitted_ids)
                )
            except LookupError:
                logger.warning(
                    f"Permission model {app_label}.{permission_model_name}"
                    " not found. Falling back to creator/public check."
                )
                # Fallback if permission model doesn't exist (might happen for simpler models)
                queryset = model_cls.objects.filter(
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

    def visible_to_user(
        self,
        user: Any = None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ) -> PermissionQuerySet:
        """
        Returns queryset filtered by user permission via PermissionQuerySet.
        This overrides BaseVisibilityManager's implementation to use
        PermissionQuerySet's simpler visible_to_user logic.

        ``lightweight`` and ``with_doc_label_annotations`` are accepted for
        signature parity with ``BaseVisibilityManager`` but have no effect
        here — ``PermissionQuerySet`` only filters on creator / public.

        Note: this override returns before reaching ``super().visible_to_user``,
        so the base class superuser shortcut is NOT used. Superuser visibility
        is granted by ``PermissionQuerySet.visible_to_user`` itself.
        """
        if user is None:
            user = AnonymousUser()
        return self.get_queryset().visible_to_user(user)


class UserFeedbackManager(BaseVisibilityManager):
    def get_queryset(self) -> UserFeedbackQuerySet:
        return UserFeedbackQuerySet(self.model, using=self._db)

    def visible_to_user(
        self,
        user: Any = None,
        lightweight: bool = False,
        with_doc_label_annotations: bool = False,
    ) -> QuerySet:
        """
        Delegate to the queryset's visible_to_user method.

        ``lightweight`` and ``with_doc_label_annotations`` are accepted for
        signature parity with ``BaseVisibilityManager`` but have no effect
        on UserFeedback (no heavy prefetches involved).
        """
        if user is None:
            user = AnonymousUser()
        return self.get_queryset().visible_to_user(user)

    def get_or_none(self, *args: Any, **kwargs: Any) -> Any | None:
        model_cls: Any = cast(Any, self.model)
        try:
            return self.get(*args, **kwargs)
        except model_cls.DoesNotExist:
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

    def by_creator(self, creator: AbstractBaseUser) -> UserFeedbackQuerySet:
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
        unique: set[str] = set()
        for field_name in type(doc).blob_field_names():
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

    def unique_blob_paths_for_many(
        self, queryset_or_pks: QuerySet | Iterable[Any]
    ) -> set[str]:
        """Batched complement to ``unique_blob_paths`` for bulk deletion.

        Returns the set of blob paths referenced by any Document in the
        input set that are NOT referenced by any Document outside the
        input set. These are the blobs that would be orphaned in storage
        if every Document in the input were deleted.

        Where ``unique_blob_paths`` runs N queries per Document (one per
        FileField), this runs at most ``2 * len(FileFields)`` queries
        regardless of the input size — suitable for queryset-style
        deletes where the per-row form would be N+1.

        Args:
            queryset_or_pks: A Document queryset, or an iterable of
                Document primary keys.

        Returns:
            Set of blob names safe to schedule for deletion if every
            input Document is deleted. Empty/unset fields are omitted.
        """
        if isinstance(queryset_or_pks, QuerySet):
            target_pks: list[Any] = list(queryset_or_pks.values_list("pk", flat=True))
        else:
            target_pks = [pk for pk in queryset_or_pks if pk is not None]

        if not target_pks:
            return set()

        from opencontractserver.documents.models import Document

        unique: set[str] = set()
        for field_name in cast(type[Document], self.model).blob_field_names():
            # Single round-trip per field: collect every distinct,
            # non-empty path used by the targets.
            target_paths: set[str] = {
                path
                for path in self.filter(pk__in=target_pks)
                .exclude(**{field_name: ""})
                .exclude(**{f"{field_name}__isnull": True})
                .values_list(field_name, flat=True)
                .distinct()
                if path
            }
            if not target_paths:
                continue

            # Single round-trip per field: of those, which are still
            # referenced OUTSIDE the target set?
            shared_paths: set[str] = set(
                self.exclude(pk__in=target_pks)
                .filter(**{f"{field_name}__in": list(target_paths)})
                .values_list(field_name, flat=True)
            )

            unique.update(target_paths - shared_paths)
        return unique


# ``Manager.from_queryset(...)`` returns a class object computed at runtime;
# mypy can't trace its members, so the dynamic-base-class warning is silenced
# at the point of declaration.  The resulting manager still gets the
# ``PermissionManager`` API plus everything declared on the queryset.
class AnnotationManager(PermissionManager.from_queryset(AnnotationQuerySet)):  # type: ignore[misc]
    """
    Custom Manager for the Annotation model that uses:
      - PermissionManager (from_queryset)
      - AnnotationQuerySet (with permission checks, CTE support, vector search)
    """

    def get_queryset(self) -> AnnotationQuerySet:
        return AnnotationQuerySet(self.model, using=self._db)

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


# Same ``from_queryset`` dynamic-base-class rationale as ``AnnotationManager``
# above — the runtime-synthesised base class isn't visible to mypy.
class NoteManager(PermissionManager.from_queryset(NoteQuerySet)):  # type: ignore[misc]
    """
    Custom Manager for the Note model that uses:
      - PermissionManager (from_queryset)
      - NoteQuerySet (with permission checks, CTE support, vector search)
    """

    def get_queryset(self) -> NoteQuerySet:
        return NoteQuerySet(self.model, using=self._db)

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


class RelationshipManager(BaseVisibilityManager):
    """Visibility manager for the ``Relationship`` model.

    Relationships don't have their own permission model — they inherit
    visibility from their linked document and corpus. ``BaseVisibilityManager``
    already handles the creator/public/explicit-permission base case; we
    layer on the same DocumentPath-aware filter used for annotations so
    that relationships pointing at a doc currently in the trash for a
    corpus stop appearing in user-facing queries. The data is preserved
    so that "Restore from trash" still works.
    """

    def visible_to_user(
        self,
        user: Any = None,
        lightweight: bool = False,
        # ``with_doc_label_annotations`` is part of ``BaseVisibilityManager``'s
        # signature and is meaningless for Relationship (it only affects
        # annotation-label prefetches). Accepted purely for compatibility with
        # the parent manager so callers can use a uniform call shape.
        with_doc_label_annotations: bool = False,
    ) -> QuerySet:
        from opencontractserver.shared.QuerySets import (
            _exclude_soft_deleted_doc_orphans,
        )

        # Normalise None → AnonymousUser up front and short-circuit on
        # superuser before super() runs, matching AnnotationQuerySet's
        # pattern so the two soft-delete-aware visibility paths read the
        # same.
        if user is None:
            user = AnonymousUser()
        if user.is_superuser:
            return super().visible_to_user(
                user=user,
                lightweight=lightweight,
                with_doc_label_annotations=with_doc_label_annotations,
            )

        qs = super().visible_to_user(
            user=user,
            lightweight=lightweight,
            with_doc_label_annotations=with_doc_label_annotations,
        )
        return _exclude_soft_deleted_doc_orphans(qs)


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
        creator: AbstractBaseUser,
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
