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
from opencontractserver.shared.user_can_mixin import UserCanMixin
from opencontractserver.types.enums import PermissionTypes as _PermissionTypes

# Re-exported so callers receiving "a permissioned manager" can annotate
# against ``PermissionedQueryManagerProtocol`` instead of any concrete
# manager class.  Every visibility manager defined below satisfies the
# ``visible_to_user(user) -> QuerySet`` contract.
from opencontractserver.types.protocols import (  # noqa: F401
    PermissionedQueryManagerProtocol,
)

# Subset of permission codes Relationship recognises and that creators
# are exempt from. PUBLISH/PERMISSION are intentionally excluded so they
# still fall through to the terminal ``return False`` below
# (Relationship doesn't model those codes; creators aren't exempt from
# that fact). Module-level so the tuple isn't reallocated on every
# ``RelationshipManager.user_can`` call.
_RELATIONSHIP_CREATOR_SHORT_CIRCUIT_PERMS = frozenset(
    {
        _PermissionTypes.READ,
        _PermissionTypes.CREATE,
        _PermissionTypes.UPDATE,
        _PermissionTypes.EDIT,
        _PermissionTypes.DELETE,
        _PermissionTypes.COMMENT,
        _PermissionTypes.CRUD,
        _PermissionTypes.ALL,
    }
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


class BaseVisibilityManager(UserCanMixin, Manager):
    """
    Base manager that implements the standard visibility logic for non-annotations and non-relationships .

    This manager provides a secure default implementation of visible_to_user that:
    1. Allows superusers to see everything
    2. For anonymous users: only public objects
    3. For authenticated users: public objects, objects they created, or objects explicitly shared with them

    This is the SECURE fallback logic that should be used by all models that don't have
    more specific permission requirements.

    ``user_can(user, instance, permission)`` is provided by ``UserCanMixin``
    and mirrors ``visible_to_user`` semantics: for READ, it returns the same
    boolean as ``self.visible_to_user(user).filter(pk=instance.pk).exists()``.
    Per-model subclasses SHOULD override and add model-specific rules (e.g.
    structural read-only, annotation privacy) before delegating back to
    ``_default_user_can`` for the default branch.
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

    def user_can(
        self,
        user: Any,
        instance: Any,
        permission: Any,
        *,
        include_group_permissions: bool = True,
    ) -> bool:
        """Single-object authorization check for ``UserFeedback``.

        Mirrors ``UserFeedbackQuerySet.visible_to_user``
        (``shared/QuerySets.py:169-190``): adds a READ grant when the
        feedback's commented annotation is public, then delegates to the
        default branch for creator/public/guardian. Non-READ permissions
        do NOT get the commented-annotation grant — write permission is
        creator/guardian only.

        Performance note: the public-annotation gate uses a targeted
        ``Annotation.objects.filter(pk=commented_annotation_id,
        is_public=True).exists()`` lookup instead of dereferencing
        ``instance.commented_annotation`` — that descriptor triggers a
        DB hit per call when not prefetched, so bulk callers iterating
        feedback rows would otherwise generate one extra query each.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.types.enums import PermissionTypes

        if permission == PermissionTypes.READ:
            commented_id = getattr(instance, "commented_annotation_id", None)
            if (
                commented_id
                and Annotation.objects.filter(pk=commented_id, is_public=True).exists()
            ):
                return True
        return super().user_can(
            user,
            instance,
            permission,
            include_group_permissions=include_group_permissions,
        )

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

    def user_can(
        self,
        user: Any,
        instance: Any,
        permission: Any,
        *,
        include_group_permissions: bool = True,
    ) -> bool:
        """Single-object authorization check for ``Document``.

        Documents in public corpora have ``is_public=True`` auto-propagated
        at creation time (see ``Corpus.add_document`` and
        ``Corpus._propagate_public_status_to_documents``), so the
        public-corpus auto-inheritance is encoded in the instance's own
        ``is_public`` flag and ``_default_user_can``'s public-READ branch
        handles it without additional joins.

        Default rules suffice: creator OR is_public (READ only) OR
        guardian codename. Mirrors ``DocumentQuerySet.visible_to_user``
        (``shared/QuerySets.py:256-299``).
        """
        return super().user_can(
            user,
            instance,
            permission,
            include_group_permissions=include_group_permissions,
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

    def user_can(
        self,
        user: Any,
        instance: Any,
        permission: Any,
        *,
        include_group_permissions: bool = True,
    ) -> bool:
        """Single-object authorization check for ``Annotation``.

        Branch order is **LOAD-BEARING** — do not reorder:

        1. ``None`` user → False (matches ``_default_user_can``).
        2. Resolve user (str/int id → ``User`` instance, ``AnonymousUser``
           passes through).
        3. **Superuser bypass** → True. Must precede structural-write-deny
           so superusers retain write access to structural items.
        4. **Structural write deny** → for non-superusers, any non-READ
           permission on a ``structural=True`` annotation returns False.
        5. **Privacy recursion** (only when not structural-READ):
           ``created_by_analysis``/``created_by_extract`` private rows
           require the *same* permission on the source Analysis/Extract.
           This delegates to ``Analysis.objects.user_can`` /
           ``Extract.objects.user_can`` — those manager paths honor
           creator status, fixing the legacy bug where the recursion
           used the creator-blind ``user_has_permission_for_obj``.
        6. ``document_id is None`` → False for non-superusers. Mirrors
           the legacy denial at ``permissioning.py:640``. Structural-set-
           linked annotations (which the QuerySet does cover via
           ``structural_set__documents``) get their READ answered by the
           ``visible_to_user(...).exists()`` fallback below.
        7. **MIN(doc, corpus)** — delegate to
           ``AnnotationQueryOptimizer._compute_effective_permissions``
           which encodes the MIN logic and BACON MODE
           (``corpus.allow_comments → COMMENT = READ``).

        Performance note: the privacy-recursion branch dereferences
        ``instance.created_by_analysis`` / ``instance.created_by_extract``
        when their FK ids are set — those descriptors hit the database
        once each per call when the relations aren't prefetched. Bulk
        callers (e.g. GraphQL list resolvers iterating annotations)
        SHOULD ``select_related("created_by_analysis",
        "created_by_extract")`` on their root queryset to avoid one
        extra query per row. The ``AnnotationQueryOptimizer`` already
        batches the MIN(doc, corpus) computation; only the privacy
        recursion path is unbatched today.

        Anonymous-path note: the ``visible_to_user(...).filter(pk=).exists()``
        query for anonymous READ is also a per-call DB round-trip with
        no batched alternative — bulk anonymous filtering should call
        ``visible_to_user(anon).filter(pk__in=[...])`` directly rather
        than looping ``user_can`` per row.
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.shared.user_can_mixin import resolve_user_for_user_can
        from opencontractserver.types.enums import PermissionTypes

        # Single shared int/str → User resolver (PR #1663 DRY cleanup).
        # ``None`` covers both an explicit ``None`` argument AND an
        # unresolvable id; both deny under the legacy contract.
        user = resolve_user_for_user_can(user)
        if user is None:
            return False

        if isinstance(user, AnonymousUser) or not getattr(
            user, "is_authenticated", False
        ):
            # Anonymous: route READ through visible_to_user (which
            # encodes the structural+public-doc+public-corpus rules)
            # and deny non-READ outright.
            if permission != PermissionTypes.READ:
                return False
            return (
                self.get_queryset()
                .visible_to_user(user)
                .filter(pk=instance.pk)
                .exists()
            )

        # Superuser bypass — MUST precede structural-write-deny so that
        # admin tooling retains write access to structural annotations.
        if user.is_superuser:
            return True

        # Structural write deny: non-superusers can only READ structural
        # annotations.
        if (
            getattr(instance, "structural", False)
            and permission != PermissionTypes.READ
        ):
            return False

        # Privacy recursion: when an annotation was generated by an
        # Analysis or Extract, gate the requested permission on that
        # source object (in addition to doc+corpus). Skip for the
        # structural-READ case (structural rows are always READable when
        # the parent doc is). At this point step 5 above has already
        # denied non-READ structural calls, so ``structural and READ``
        # is the only structural state we can still be in — but we keep
        # the explicit ``and permission == READ`` for readability rather
        # than relying on the flow-sensitive equivalence.
        is_structural_read = (
            getattr(instance, "structural", False)
            and permission == PermissionTypes.READ
        )
        if not is_structural_read:
            analysis_id = getattr(instance, "created_by_analysis_id", None)
            extract_id = getattr(instance, "created_by_extract_id", None)
            if analysis_id:
                source_analysis = instance.created_by_analysis
                if source_analysis is None:
                    return False
                from opencontractserver.analyzer.models import Analysis

                if not Analysis.objects.user_can(
                    user,
                    source_analysis,
                    permission,
                    include_group_permissions=include_group_permissions,
                ):
                    return False
            elif extract_id:
                source_extract = instance.created_by_extract
                if source_extract is None:
                    return False
                from opencontractserver.extracts.models import Extract

                if not Extract.objects.user_can(
                    user,
                    source_extract,
                    permission,
                    include_group_permissions=include_group_permissions,
                ):
                    return False

        # MIN(doc, corpus): defer to the optimizer which encodes BACON
        # MODE and the corpus.allow_comments → COMMENT = READ flip.
        if getattr(instance, "document_id", None) is None:
            # No parent document — no inheritable scope.
            # Fall back to visible_to_user for the structural_set route
            # (Annotation.objects.visible_to_user handles structural rows
            # linked via ``structural_set__documents`` even when the FK
            # is NULL) for READ only; non-READ is denied.
            if permission != PermissionTypes.READ:
                return False
            return (
                self.get_queryset()
                .visible_to_user(user)
                .filter(pk=instance.pk)
                .exists()
            )

        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                user=user,
                document_id=instance.document_id,
                corpus_id=instance.corpus_id,
            )
        )

        if permission == PermissionTypes.READ:
            return can_read
        if permission == PermissionTypes.CREATE:
            return can_create
        if permission in (PermissionTypes.UPDATE, PermissionTypes.EDIT):
            return can_update
        if permission == PermissionTypes.DELETE:
            return can_delete
        if permission == PermissionTypes.COMMENT:
            return can_comment
        if permission == PermissionTypes.CRUD:
            return can_read and can_create and can_update and can_delete
        if permission == PermissionTypes.ALL:
            # Annotations don't support PUBLISH or PERMISSION — ALL
            # here matches the legacy semantic (READ+CRUD+COMMENT).
            return can_read and can_create and can_update and can_delete and can_comment
        # PUBLISH and PERMISSION are not defined for annotations.
        return False


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

    def user_can(
        self,
        user: Any,
        instance: Any,
        permission: Any,
        *,
        include_group_permissions: bool = True,
    ) -> bool:
        """Single-object authorization check for ``Note``.

        Mirrors ``NoteQuerySet.visible_to_user``
        (``shared/QuerySets.py:486-514``): a note is visible when the
        user created it OR the document AND the corpus (or null corpus)
        are visible. Composes ``Document.objects.user_can`` and
        ``Corpus.objects.user_can`` rather than reusing
        ``AnnotationQueryOptimizer`` (notes don't have BACON MODE).

        Performance note: both the anonymous and authenticated branches
        dereference ``instance.document`` / ``instance.corpus`` — these
        descriptors hit the database when the relations aren't
        prefetched. Bulk callers (list resolvers iterating notes)
        SHOULD ``select_related("document", "corpus")`` on the root
        queryset to keep the per-note check at O(1) DB ops.
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.shared.user_can_mixin import resolve_user_for_user_can
        from opencontractserver.types.enums import PermissionTypes

        user = resolve_user_for_user_can(user)
        if user is None:
            return False

        if isinstance(user, AnonymousUser) or not getattr(
            user, "is_authenticated", False
        ):
            # Anonymous: only public notes on public docs/corpuses
            # (matches NoteQuerySet anonymous branch at QuerySets.py:501-506).
            if permission != PermissionTypes.READ:
                return False
            if not getattr(instance, "is_public", False):
                return False
            doc = getattr(instance, "document", None)
            if doc is None or not getattr(doc, "is_public", False):
                return False
            corpus = getattr(instance, "corpus", None)
            if corpus is not None and not getattr(corpus, "is_public", False):
                return False
            return True

        if user.is_superuser:
            return True

        # Creator short-circuit (matches the QuerySet's ``Q(creator=user)``).
        if (
            getattr(instance, "creator_id", None) is not None
            and instance.creator_id == user.id
        ):
            return True

        # MIN(doc, corpus): the user must be able to perform ``permission``
        # on both the parent document and the corpus (if any).
        doc = getattr(instance, "document", None)
        if doc is None:
            return False

        from opencontractserver.documents.models import Document

        if not Document.objects.user_can(
            user,
            doc,
            permission,
            include_group_permissions=include_group_permissions,
        ):
            return False

        corpus = getattr(instance, "corpus", None)
        if corpus is None:
            return True

        from opencontractserver.corpuses.models import Corpus

        return Corpus.objects.user_can(
            user,
            corpus,
            permission,
            include_group_permissions=include_group_permissions,
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
        """Filter relationships to those visible to ``user``.

        Aligned with ``RelationshipManager.user_can`` (Phase A invariant):
        relationships inherit visibility from their parent document AND
        parent corpus (MIN logic). ``BaseVisibilityManager.visible_to_user``
        would fall back to a creator/public check for this model (no
        ``relationshipuserobjectpermission`` table exists), which is
        narrower than ``user_can``'s MIN(doc, corpus) and produced the
        Phase A invariant-test mismatch. We compose doc + corpus
        visibility directly here so the two surfaces agree.
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
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

        # MIN(doc, corpus): user must be able to see both the parent doc
        # and the parent corpus. Use the manager-level ``visible_to_user``
        # so doc/corpus creator/public/guardian rules all participate.
        visible_doc_ids = Document.objects.visible_to_user(user).values_list(
            "pk", flat=True
        )
        visible_corpus_ids = Corpus.objects.visible_to_user(user).values_list(
            "pk", flat=True
        )

        doc_corpus_visible = Q(document_id__in=visible_doc_ids) & (
            Q(corpus__isnull=True) | Q(corpus_id__in=visible_corpus_ids)
        )

        # Anonymous users have no ``id`` field — gate the creator OR to
        # authenticated users only. Doc/corpus visibility already encodes
        # the public-anonymous path via ``Document.objects.visible_to_user``.
        if user.is_anonymous:
            qs = self.get_queryset().filter(doc_corpus_visible)
        else:
            qs = self.get_queryset().filter(Q(creator=user) | doc_corpus_visible)
        return _exclude_soft_deleted_doc_orphans(qs)

    def user_can(
        self,
        user: Any,
        instance: Any,
        permission: Any,
        *,
        include_group_permissions: bool = True,
    ) -> bool:
        """Single-object authorization check for ``Relationship``.

        Order: superuser bypass → structural-write-deny →
        (``document_id is None`` → False) → MIN(doc, corpus) via
        ``AnnotationQueryOptimizer``.

        **NOTE: deliberately does NOT check ``created_by_analysis``/
        ``created_by_extract``**. Although these fields exist on
        ``Relationship``, the legacy ``user_has_permission_for_obj``
        relationship branch (``permissioning.py:680-740``) never
        consulted them. Adding a privacy check here would be a
        behavior widening beyond the scope of Phase A. If/when that
        widening is desired, mirror the annotation branch and pin a
        new invariant test.

        TODO(Phase-C, issue #1655 follow-up): mirror the privacy
        recursion already wired into ``AnnotationManager.user_can`` so
        analysis-/extract-rooted relationships honour their source's
        creator/grant semantics rather than only the doc+corpus MIN.
        Until then this omission is intentional, not an oversight.
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.shared.user_can_mixin import resolve_user_for_user_can
        from opencontractserver.types.enums import PermissionTypes

        user = resolve_user_for_user_can(user)
        if user is None:
            return False

        if isinstance(user, AnonymousUser) or not getattr(
            user, "is_authenticated", False
        ):
            if permission != PermissionTypes.READ:
                return False
            # ``self.get_queryset()`` is statically a plain ``QuerySet`` in
            # the Django stubs; at runtime ``RelationshipManager`` runs against
            # ``BaseVisibilityManager`` whose ``visible_to_user`` is defined
            # both on the manager and via the QuerySet contract.
            return self.visible_to_user(user).filter(pk=instance.pk).exists()

        if user.is_superuser:
            return True

        # Structural relationships are ALWAYS read-only for non-superusers.
        # Run before the creator short-circuit so even the creator cannot
        # write to a structural relationship.
        if (
            getattr(instance, "structural", False)
            and permission != PermissionTypes.READ
        ):
            return False

        # Creator short-circuit — mirrors ``Q(creator=user)`` in
        # ``visible_to_user``. Without this, granting User A CREATE on a
        # doc/corpus, letting A author a Relationship, then revoking A's
        # READ grant would keep the relationship in A's ``visible_to_user``
        # queryset (creator OR doc-corpus visible) while ``user_can(READ)``
        # would return ``False`` (doc/corpus READ denied) — a latent
        # invariant violation surfaced by the Claude review on PR #1663.
        # See ``_RELATIONSHIP_CREATOR_SHORT_CIRCUIT_PERMS`` (module-level)
        # for the permission codes this short-circuit covers.
        if (
            getattr(instance, "creator_id", None) is not None
            and instance.creator_id == user.id
            and permission in _RELATIONSHIP_CREATOR_SHORT_CIRCUIT_PERMS
        ):
            return True

        if getattr(instance, "document_id", None) is None:
            return False

        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )

        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                user=user,
                document_id=instance.document_id,
                corpus_id=instance.corpus_id,
            )
        )

        if permission == PermissionTypes.READ:
            return can_read
        if permission == PermissionTypes.CREATE:
            return can_create
        if permission in (PermissionTypes.UPDATE, PermissionTypes.EDIT):
            return can_update
        if permission == PermissionTypes.DELETE:
            return can_delete
        if permission == PermissionTypes.COMMENT:
            return can_comment
        if permission == PermissionTypes.CRUD:
            return can_read and can_create and can_update and can_delete
        if permission == PermissionTypes.ALL:
            return can_read and can_create and can_update and can_delete and can_comment
        # PUBLISH and PERMISSION are not defined for relationships.
        return False


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
