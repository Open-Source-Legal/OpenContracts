from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import IntegrityError
from django.db.models import Manager, Model, Prefetch, Q, QuerySet

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
from opencontractserver.vector_search.hooks import enqueue_embedding_index_sync

# Subset of permission codes Annotation / Relationship recognise for
# row-creator shortcuts. PUBLISH/PERMISSION are intentionally excluded so they
# still fall through to the terminal ``return False`` below (these models don't
# support those codes; creators aren't exempt from that fact). Module-level so
# the tuple isn't reallocated on every ``user_can`` call.
_ROW_CREATOR_SHORT_CIRCUIT_PERMS = frozenset(
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

_RELATIONSHIP_CREATOR_SHORT_CIRCUIT_PERMS = _ROW_CREATOR_SHORT_CIRCUIT_PERMS
_ANNOTATION_CREATOR_SOURCE_PRIVACY_EXEMPT_PERMS = _ROW_CREATOR_SHORT_CIRCUIT_PERMS

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document
    from opencontractserver.users.models import User as UserModel

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
    (see ``shared/prefetch_attrs.py``); consumed by ``user_can`` and
    ``resolve_my_permissions``. ``with_doc_label_annotations`` opts in to a
    focused prefetch of ``DOC_TYPE_LABEL`` annotations for list-view badges
    (only honoured in lightweight mode).
    """
    queryset = queryset.select_related("creator", "user_lock", "parent")

    if user and not user.is_anonymous:
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
    1. For anonymous users: only public objects
    2. For authenticated users (superusers included — scoped admin access,
       2026-05, no blanket bypass): public objects, objects they created, or
       objects explicitly shared with them

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
        - Superusers are computed like any other user (no blanket bypass —
          scoped admin access, 2026-05)
        - Anonymous users see only public objects
        - Authenticated users see: public objects, objects they created, or
          objects with an explicit guardian READ grant (user- or group-level)

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

        # NOTE (scoped admin access, 2026-05): superusers are NO LONGER given a
        # blanket bypass here — an admin's data visibility is computed exactly
        # like a normal user (creator / is_public / explicit guardian grant).
        # The only retained admin data privilege is the structural-write
        # break-glass in ``AnnotationManager``/``RelationshipManager.user_can``.
        # Audit/repair of arbitrary data is done through the Django admin site.
        #
        # PERF TRADE-OFF: before this change superusers returned early here
        # (no guardian JOINs, no ``distinct()``). Admin queries now traverse
        # the same prefetch + ``distinct()`` path as a normal user, so bulk
        # admin queries (moderation dashboards, admin scripts) lose the old
        # fast path. This is intentional — correctness (no data leakage)
        # over admin-query speed; reach for the Django admin site / raw ORM
        # for genuine omniscient bulk operations.

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
            # By this point ``user`` is guaranteed to be authenticated — None
            # and anonymous returned early at the top of the method. Superusers
            # are no longer special-cased (scoped admin access, 2026-05); they
            # flow through the same guardian / creator / is_public logic, which
            # means an admin with no grants sees only public + own objects.
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
            except LookupError:
                logger.warning(
                    f"Permission model {app_label}.{permission_model_name}"
                    " not found. Falling back to creator/public check."
                )
                # Fallback if the user-level permission model doesn't exist
                # (might happen for simpler models).
                permitted_ids = []

            # Group object-permissions: ``user_can`` resolves group grants
            # (``_default_user_can`` runs with
            # ``include_group_permissions=True``), so the filter must OR
            # them in too — otherwise a user whose only READ grant is via a
            # group passes ``user_can`` yet never appears in
            # ``visible_to_user``. This is the same drift #1714 closed in
            # the ``shared/QuerySets.py`` bodies; issue #1731 aligns this
            # manager body with that fix. The lazy ``values_list`` keeps the
            # group lookup a SQL subquery (no extra round-trip). Resolved in
            # its own ``try`` so a missing group table never discards the
            # already-resolved user-level grants.
            group_permission_model_name = f"{model_name}groupobjectpermission"
            try:
                user_group_ids = user.groups.values_list("id", flat=True)
                group_permission_model_type = apps.get_model(
                    app_label, group_permission_model_name
                )
                group_permitted_ids = group_permission_model_type.objects.filter(
                    permission__codename=f"read_{model_name}",
                    group_id__in=user_group_ids,
                ).values_list("content_object_id", flat=True)
            except LookupError:
                logger.warning(
                    f"Group permission model {app_label}."
                    f"{group_permission_model_name} not found. Falling back "
                    "to creator/public check."
                )
                # Fallback if the group-level permission model doesn't exist
                # (might happen for simpler models).
                group_permitted_ids = []

            # Build the optimized query: creator OR public OR an explicit
            # user-level guardian READ grant OR a group-level one.
            queryset = model_cls.objects.filter(
                Q(creator_id=user.id)
                | Q(is_public=True)
                | Q(id__in=permitted_ids)
                | Q(id__in=group_permitted_ids)
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
            # The permission logic with __in might introduce duplicates for
            # authenticated users (superusers included — they now traverse the
            # same permission JOINs, scoped admin access 2026-05).
            if user and not user.is_anonymous:
                # Apply distinct for authenticated users where permission JOINs occur
                queryset = queryset.distinct()

            return queryset

        except (ImportError, LookupError) as e:
            # Narrow, intentional fallback (issue #1986 item 4): degrade to
            # creator/public filtering ONLY when the guardian permission tables
            # are genuinely absent for this model — ``ImportError`` (guardian /
            # an app not installed) or ``LookupError`` (``apps.get_model`` cannot
            # resolve the permission model). The previous ``(ImportError,
            # Exception)`` envelope was equivalent to a bare ``except Exception``
            # (``ImportError`` ⊂ ``Exception``): ANY error — a programming bug, a
            # database error, a malformed grant row — was swallowed and the
            # queryset silently dropped every guardian-granted row, UNDER-
            # disclosing (a fail-open-to-less-data security smell) while hiding
            # the defect. Such errors now propagate so they surface in tests and
            # monitoring instead of quietly narrowing a user's visible set.
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

        Note: this override returns before reaching ``super().visible_to_user``;
        ``PermissionQuerySet.visible_to_user`` encodes the full filter
        (superusers are computed like any other user — scoped admin access,
        2026-05).
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
        user: int | str | UserModel | AnonymousUser | None,
        instance: Model,
        permission: _PermissionTypes,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
    ) -> bool:
        """Single-object authorization check for ``UserFeedback``.

        Feedback inherits READ visibility from the annotation it
        comments on: ``user`` can READ a feedback row when they can
        READ the commented annotation (per
        ``Annotation.objects.visible_to_user``), in addition to the
        default creator / ``is_public`` / guardian branches on the
        feedback row itself. Non-READ permissions do NOT inherit from
        the annotation — write access is creator or explicit guardian
        grant on the feedback row only.

        Mirrors ``UserFeedbackQuerySet.visible_to_user``
        (``shared/QuerySets.py``) so the Phase A invariant holds:
        a row included by ``visible_to_user(u)`` always answers True
        for ``user_can(u, READ)``.

        Performance note: the inherited-visibility gate uses a targeted
        ``Annotation.objects.visible_to_user(user).filter(pk=commented_annotation_id).exists()``
        lookup keyed on the FK id rather than dereferencing
        ``instance.commented_annotation`` (the descriptor would trigger
        a DB round-trip per call when not prefetched).
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.types.enums import PermissionTypes

        if permission == PermissionTypes.READ:
            commented_id = getattr(instance, "commented_annotation_id", None)
            if (
                commented_id
                and Annotation.objects.visible_to_user(user)
                .filter(pk=commented_id)
                .exists()
            ):
                return True
        return super().user_can(
            user,
            instance,
            permission,
            include_group_permissions=include_group_permissions,
            request=request,
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
    """Visibility manager for the Document model.

    Returns a DocumentQuerySet that supports vector searching via the
    mixin.

    Documents use the default ``user_can`` rules from
    ``BaseVisibilityManager``: public-corpus visibility is encoded at
    creation time via ``is_public`` auto-propagation
    (``Corpus.add_document`` / ``Corpus._propagate_public_status_to_documents``),
    so the public-corpus auto-inheritance is handled by
    ``_default_user_can``'s public-READ branch without needing
    additional joins. Mirrors ``DocumentQuerySet.visible_to_user``
    (``shared/QuerySets.py``).
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
def _source_privacy_recursion_passes(
    user: UserModel | AnonymousUser,
    instance: Model,
    permission: _PermissionTypes,
    include_group_permissions: bool,
    *,
    request: Any = None,
) -> bool:
    """Return whether the ``created_by_*`` privacy-recursion gate passes.

    Shared by ``AnnotationManager.user_can`` and
    ``RelationshipManager.user_can`` — both models carry
    ``created_by_analysis`` / ``created_by_extract`` FKs and enforce the
    same source-permission rule (relationships gained the recursion in the
    2026-06 permissioning audit, closing the Phase-C deferral from issue
    #1655).

    Three outcomes:
    - ``True`` for the structural-READ short-circuit (structural rows are
      always READable when the parent doc is).
    - ``True`` when the row has neither ``created_by_analysis`` nor
      ``created_by_extract`` set (privacy recursion is a no-op).
    - For analysis/extract-rooted rows, the requested permission must hold
      on the source object as well as doc+corpus. Delegates to
      ``Analysis.objects.user_can`` / ``Extract.objects.user_can`` so
      creator status on the source is honored.

    Callers have already denied non-READ structural requests (the
    structural-write break-glass runs first), so ``structural and READ`` is
    the only structural state we can still be in — but we keep the explicit
    ``and permission == READ`` for readability rather than relying on the
    flow-sensitive equivalence.

    Deleted-source posture: both FKs are ``on_delete=SET_NULL``, so deleting
    the source Analysis/Extract NULLs the FK and the row becomes a normal
    (non-private) row — deletion does NOT permanently lock rows. The
    ``source is None`` branches below fire only in the race window where the
    id column is read before the SET_NULL lands; they fail closed for that
    window, by design.

    Performance note: the FK descriptors (``instance.created_by_analysis``
    / ``created_by_extract``) hit the database once each per call when the
    relations aren't prefetched. Callers that invoke ``user_can`` in a loop
    MUST ``select_related("created_by_analysis", "created_by_extract")`` on
    their root queryset (single-object call sites are unaffected).
    """
    from opencontractserver.types.enums import PermissionTypes

    # Structural-READ short-circuit. The list-side counterpart is the
    # ``Q(structural=True)`` disjunct in the privacy gates
    # (``AnnotationQuerySet.visible_to_user``'s positive filter and
    # ``apply_source_privacy_gate``'s ``structural=False`` conjuncts) —
    # removing either side without the other breaks filter/check parity
    # for structural rows rooted in an invisible source.
    is_structural_read = (
        getattr(instance, "structural", False) and permission == PermissionTypes.READ
    )
    if is_structural_read:
        return True

    analysis_id = getattr(instance, "created_by_analysis_id", None)
    if analysis_id is not None:
        # ``instance`` is statically ``Model`` but this branch only runs for
        # Annotation/Relationship rows, which declare this FK.
        source_analysis = instance.created_by_analysis  # type: ignore[attr-defined]
        if source_analysis is None:
            return False
        from opencontractserver.analyzer.models import Analysis

        return Analysis.objects.user_can(
            user,
            source_analysis,
            permission,
            include_group_permissions=include_group_permissions,
            request=request,
        )

    extract_id = getattr(instance, "created_by_extract_id", None)
    if extract_id is not None:
        # ``instance`` is statically ``Model`` but this branch only runs for
        # Annotation/Relationship rows, which declare this FK.
        source_extract = instance.created_by_extract  # type: ignore[attr-defined]
        if source_extract is None:
            return False
        from opencontractserver.extracts.models import Extract

        return Extract.objects.user_can(
            user,
            source_extract,
            permission,
            include_group_permissions=include_group_permissions,
            request=request,
        )

    return True


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
        user: int | str | UserModel | AnonymousUser | None,
        instance: Model,
        permission: _PermissionTypes,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
    ) -> bool:
        """Single-object authorization check for ``Annotation``.

        Branch order is **LOAD-BEARING** — do not reorder:

        1. ``None`` user → False (matches ``_default_user_can``).
        2. Resolve user (str/int id → ``User`` instance, ``AnonymousUser``
           passes through).
        3. **Anonymous route**: READ via ``visible_to_user(...).exists()``,
           non-READ denied.
        4. **Structural-write break-glass** → for any non-READ permission on
           a ``structural=True`` annotation: True for superusers, False for
           everyone else. This is NOT a blanket superuser bypass — outside
           this single branch superusers are computed exactly like a normal
           user (scoped admin access, 2026-05).
        5. **Row-creator source-privacy exemption** for supported annotation
           permissions (mirrors ``AnnotationQuerySet.visible_to_user``'s
           ``Q(creator=user)`` branch). This bypasses only the source privacy
           recursion; document/corpus permissions are still computed below.
        6. **Privacy recursion** (only when not structural-READ and the row
           creator exemption does not apply): see
           ``_source_privacy_recursion_passes`` (module-level, shared with
           ``RelationshipManager``).
        7. ``document_id is None`` → READ via ``visible_to_user(...).exists()``
           (covers the structural_set route), non-READ denied.
        8. **MIN(doc, corpus)** → see
           ``_compute_annotation_effective_permission``.

        Phase B (issue #1655): the privacy recursion delegates to
        ``Analysis.objects.user_can`` / ``Extract.objects.user_can`` per
        call. Without a request-scoped cache wrapped by
        ``permission_cache_scope``, a GraphQL resolver fanning out
        ``user_can`` over a list of analysis-/extract-created annotations
        re-derefs and re-checks the source Analysis/Extract per row.
        Activate the cache at request scope before this becomes a
        scaling issue.

        Performance note: the privacy-recursion branch dereferences
        ``instance.created_by_analysis`` / ``instance.created_by_extract``
        when their FK ids are set — those descriptors hit the database
        once each per call when the relations aren't prefetched. Bulk
        callers (e.g. GraphQL list resolvers iterating annotations)
        SHOULD ``select_related("created_by_analysis",
        "created_by_extract")`` on their root queryset to avoid one
        extra query per row. The ``AnnotationService`` already
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
            return self._read_only_via_visible_to_user(user, instance, permission)

        # Structural-write break-glass (scoped admin access, 2026-05): structural
        # annotations are read-only for everyone EXCEPT superusers, who retain
        # the one admin data privilege of repairing structural data through the
        # app. Non-superusers can only READ structural annotations; for every
        # other (non-structural) request a superuser is computed exactly like a
        # normal user by falling through to the inheritance logic below.
        if (
            getattr(instance, "structural", False)
            and permission != PermissionTypes.READ
        ):
            return bool(getattr(user, "is_superuser", False))

        # Row-creator source-privacy exemption — mirrors ``Q(creator=user)``
        # in ``AnnotationQuerySet.visible_to_user``'s privacy gate. This must
        # skip only the source-recursion check, then still fall through to the
        # normal doc/corpus MIN computation below; the queryset does not let an
        # annotation creator bypass document/corpus visibility.
        row_creator_exempt_from_source_privacy = (
            getattr(instance, "creator_id", None) is not None
            and instance.creator_id == user.id  # type: ignore[attr-defined]
            and permission in _ANNOTATION_CREATOR_SOURCE_PRIVACY_EXEMPT_PERMS
        )

        if (
            not row_creator_exempt_from_source_privacy
            and not _source_privacy_recursion_passes(
                user, instance, permission, include_group_permissions, request=request
            )
        ):
            return False

        if getattr(instance, "document_id", None) is None:
            # No parent document — no inheritable scope. The QuerySet
            # ``visible_to_user`` covers the structural_set route
            # (annotations linked via ``structural_set__documents`` with
            # document_id NULL) for READ; non-READ is denied.
            return self._read_only_via_visible_to_user(user, instance, permission)

        return self._compute_annotation_effective_permission(
            user, instance, permission, request=request
        )

    def _read_only_via_visible_to_user(
        self,
        user: UserModel | AnonymousUser,
        instance: Model,
        permission: _PermissionTypes,
    ) -> bool:
        """READ via ``visible_to_user(...).exists()``; deny non-READ.

        Shared by two callers in ``user_can``:
        - the anonymous branch, where the QuerySet's anonymous
          predicate encodes structural+public-doc+public-corpus
          rules;
        - the ``document_id is None`` branch for authenticated
          non-superusers, where the QuerySet covers the
          structural_set route (annotations linked via
          ``structural_set__documents`` with ``document_id NULL``).

        Hence the name change from the anonymous-implying original:
        this helper is read-only by design but its caller set is not
        anonymous-only.
        """
        from opencontractserver.types.enums import PermissionTypes

        if permission != PermissionTypes.READ:
            return False
        return self.get_queryset().visible_to_user(user).filter(pk=instance.pk).exists()

    def _compute_annotation_effective_permission(
        self,
        user: UserModel | AnonymousUser,
        instance: Model,
        permission: _PermissionTypes,
        *,
        request: Any = None,
    ) -> bool:
        """Resolve ``permission`` against the MIN(doc, corpus) tuple.

        Delegates to ``AnnotationService._compute_effective_permissions``
        which encodes the MIN logic and BACON MODE
        (``corpus.allow_comments → COMMENT = READ``), then dispatches
        on ``PermissionTypes`` to return the relevant boolean. ALL maps
        to READ+CRUD+COMMENT for annotations (no PUBLISH/PERMISSION).
        """
        from opencontractserver.annotations.services import AnnotationService
        from opencontractserver.types.enums import PermissionTypes

        # Forward ``request`` as ``context`` so the optimizer's request-scoped
        # caches (effective-perms cache + Tier 2 PermissionQueryOptimizer
        # wired into the underlying Document/Corpus user_can calls) are shared
        # across distinct annotation checks in this request.
        # ``instance`` is statically ``Model``; ``document_id`` / ``corpus_id``
        # are Annotation FKs declared on the concrete subclass.
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationService._compute_effective_permissions(
                user=user,
                document_id=instance.document_id,  # type: ignore[attr-defined]
                corpus_id=instance.corpus_id,  # type: ignore[attr-defined]
                context=request,
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
            # Annotations don't support PUBLISH or PERMISSION — ALL here
            # matches the legacy semantic (READ+CRUD+COMMENT).
            return can_read and can_create and can_update and can_delete and can_comment
        # PUBLISH and PERMISSION are not defined for annotations — any
        # caller asking for those on an annotation gets a deny rather
        # than a model-level error so the API surface stays uniform.
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
        user: int | str | UserModel | AnonymousUser | None,
        instance: Model,
        permission: _PermissionTypes,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
    ) -> bool:
        """Single-object authorization check for ``Note``.

        Mirrors ``NoteQuerySet.visible_to_user``
        (``shared/QuerySets.py:486-514``): a note is visible when the
        user created it OR the document AND the corpus (or null corpus)
        are visible. Composes ``Document.objects.user_can`` and
        ``Corpus.objects.user_can`` rather than reusing
        ``AnnotationService`` (notes don't have BACON MODE).

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

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — no blanket bypass. Notes have no structural concept, so
        # there is no admin exception here; the creator short-circuit and
        # MIN(doc, corpus) logic below apply to admins too.

        # Creator short-circuit (matches the QuerySet's ``Q(creator=user)``).
        if (
            getattr(instance, "creator_id", None) is not None
            and instance.creator_id == user.id  # type: ignore[attr-defined]
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
            request=request,
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
            request=request,
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

        Structural-set relationships whose ``document_id`` is NULL are
        intentionally outside this manager-wide non-creator surface: without a
        request document there is no safe way to map ``structural_set_id`` back
        to one specific readable document. Document views use
        ``RelationshipService.get_document_relationships``, which adds the
        structural-set disjunct after checking that document. ``user_can`` also
        returns ``False`` for ``document_id is None``, so filter/check parity
        is preserved here.
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.shared.QuerySets import (
            _exclude_soft_deleted_doc_orphans,
        )

        # Normalise None → AnonymousUser up front. Superusers are NO LONGER
        # short-circuited (scoped admin access, 2026-05) — they flow through
        # the same MIN(doc, corpus) visibility below, so an admin sees a
        # relationship only when it can see the relationship's document and
        # corpus like any other user.
        if user is None:
            user = AnonymousUser()

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

        # Privacy gate for analysis-/extract-rooted relationships (2026-06
        # permissioning audit; closes the Phase-C deferral from issue #1655).
        # Mirrors the AnnotationQuerySet gate: a row clears it when it is
        # structural, the user's own, has no privacy source, or its source is
        # one the user can see (incl. group grants via the shared builders).
        # Must stay aligned with the ``_source_privacy_recursion_passes``
        # branch in ``user_can`` — the parity invariant pins the two.
        from opencontractserver.utils.source_visibility import (
            visible_analyses_for,
            visible_extracts_for,
        )

        privacy_gate = (
            Q(structural=True)
            | (Q(created_by_analysis__isnull=True) & Q(created_by_extract__isnull=True))
            | Q(created_by_analysis__in=visible_analyses_for(user))
            | Q(created_by_extract__in=visible_extracts_for(user))
        )

        # Anonymous users have no ``id`` field — gate the creator OR to
        # authenticated users only. Doc/corpus visibility already encodes
        # the public-anonymous path via ``Document.objects.visible_to_user``.
        if user.is_anonymous:
            qs = self.get_queryset().filter(doc_corpus_visible & privacy_gate)
        else:
            # ``Q(creator=user)`` in the gate matches the creator
            # short-circuit in ``user_can`` so a relationship's creator keeps
            # READ access to their own privacy-rooted rows on both surfaces.
            privacy_gate = privacy_gate | Q(creator=user)
            qs = self.get_queryset().filter(
                (Q(creator=user) | doc_corpus_visible) & privacy_gate
            )
        return _exclude_soft_deleted_doc_orphans(qs)

    def user_can(
        self,
        user: int | str | UserModel | AnonymousUser | None,
        instance: Model,
        permission: _PermissionTypes,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
    ) -> bool:
        """Single-object authorization check for ``Relationship``.

        Order: anonymous READ-only → structural-write break-glass
        (superuser-only) → creator short-circuit → privacy recursion
        (``created_by_analysis`` / ``created_by_extract``, via the shared
        ``_source_privacy_recursion_passes``) → (``document_id is None`` →
        False) → MIN(doc, corpus) via ``AnnotationService``. Superusers
        are otherwise computed like any other user (scoped admin access,
        2026-05).

        The privacy recursion (2026-06 permissioning audit; closes the
        Phase-C deferral from issue #1655) runs AFTER the creator
        short-circuit on purpose: the queryset's privacy gate carries a
        matching ``Q(creator=user)`` disjunct, so a relationship's creator
        keeps access to their own analysis-/extract-rooted rows on both
        surfaces (filter/check parity, pinned by
        ``test_authorization_invariants``). Non-creators must hold the
        requested permission on the source Analysis/Extract as well as
        doc+corpus.
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

        # Structural-write break-glass (scoped admin access, 2026-05): structural
        # relationships are read-only for everyone EXCEPT superusers (the one
        # retained admin data privilege). Run before the creator short-circuit
        # so even the creator cannot write a structural relationship; a
        # superuser's non-structural requests fall through to the normal
        # MIN(doc, corpus) computation below.
        if (
            getattr(instance, "structural", False)
            and permission != PermissionTypes.READ
        ):
            return bool(getattr(user, "is_superuser", False))

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
            and instance.creator_id == user.id  # type: ignore[attr-defined]
            and permission in _RELATIONSHIP_CREATOR_SHORT_CIRCUIT_PERMS
        ):
            return True

        # Privacy recursion for analysis-/extract-rooted relationships —
        # shared with ``AnnotationManager.user_can``. Runs after the creator
        # short-circuit (see docstring) and before the doc/corpus MIN so a
        # non-creator without source access is denied regardless of their
        # doc+corpus grants.
        # PERF: dereferences the created_by_* FKs when set — bulk callers
        # looping ``user_can`` per row SHOULD select_related(
        # "created_by_analysis", "created_by_extract") on their root
        # queryset (see ``_source_privacy_recursion_passes``).
        if not _source_privacy_recursion_passes(
            user, instance, permission, include_group_permissions, request=request
        ):
            return False

        if getattr(instance, "document_id", None) is None:
            return False

        from opencontractserver.annotations.services import AnnotationService

        # Forward ``request`` as ``context`` so the optimizer's request-scoped
        # caches (effective-perms cache + Tier 2 PermissionQueryOptimizer
        # wired into the underlying Document/Corpus user_can calls) are shared
        # across distinct relationship checks in this request.
        # ``instance`` is statically ``Model``; ``document_id`` / ``corpus_id``
        # are Relationship FKs declared on the concrete subclass.
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationService._compute_effective_permissions(
                user=user,
                document_id=instance.document_id,  # type: ignore[attr-defined]
                corpus_id=instance.corpus_id,  # type: ignore[attr-defined]
                context=request,
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

    NOTE for future deletion paths: the object-storage vector index (see
    ``docs/architecture/object_storage_vector_search.md``) only hears about
    writes (via ``enqueue_embedding_index_sync`` below). Deleting a parent
    object is safe — the query-time ORM re-filter drops its id — but any
    code path that deletes/replaces an ``Embedding`` row *independent of its
    parent* (e.g. a stale-embedder cleanup command) must also tombstone the
    corresponding namespace entry (``ObjectStorageVectorEngine.delete``) or
    run ``rebuild_object_vector_index``, or the stale vector keeps matching
    its still-alive parent indefinitely.
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
        relationship_id: int | None = None,
    ) -> Any:
        """
        Create or update an Embedding, referencing exactly one of:
        Document, Annotation, Note, Conversation, ChatMessage, or Relationship.
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
        # Exactly one parent FK must be set — Embedding has a partial
        # unique constraint per (embedder_path, parent) pair and accepting
        # multiple here would silently write a row violating that intent.
        provided = [
            x
            for x in (
                document_id,
                annotation_id,
                note_id,
                conversation_id,
                message_id,
                relationship_id,
            )
            if x
        ]
        if len(provided) != 1:
            raise ValueError(
                "Must provide exactly one of document_id, annotation_id, "
                "note_id, conversation_id, message_id, or relationship_id."
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
            "relationship_id": relationship_id,
        }

        # Check for existing embedding without permission filtering.
        # The unique constraint applies regardless of who created the embedding.
        embedding = self.filter(**lookup).first()

        if embedding:
            setattr(embedding, field_name, vector)
            embedding.save(update_fields=[field_name, "modified"])
            enqueue_embedding_index_sync(embedding, dimension)
            return embedding

        # Try to create a new embedding. If a race condition causes a constraint
        # violation (another worker created the same embedding between our check
        # and create), catch the IntegrityError and update the existing record.
        try:
            embedding = self.create(
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
        enqueue_embedding_index_sync(embedding, dimension)
        return embedding
