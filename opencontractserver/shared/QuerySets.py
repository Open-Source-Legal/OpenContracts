import hashlib
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional, TypeVar

from django.db import models
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from tree_queries.query import TreeQuerySet

from opencontractserver.constants.annotations import (
    ANNOTATION_COUNT_CACHE_PREFIX,
    ANNOTATION_COUNT_CACHE_TTL_SECONDS,
)
from opencontractserver.shared.mixins import VectorSearchViaEmbeddingMixin
from opencontractserver.shared.user_can_mixin import UserCanMixin

# At runtime this is a bare mixin (no QuerySet base) so it can be combined
# ahead of a concrete ``models.QuerySet`` subclass without MRO/metaclass
# clashes. For type-checking we declare ``models.QuerySet`` as the base so
# mypy resolves the inherited ``_result_cache``/``query`` attributes and the
# ``super().count()`` call against the real QuerySet API.
if TYPE_CHECKING:
    _CachedCountBase = models.QuerySet
else:
    _CachedCountBase = object


class CachedCountQuerySetMixin(_CachedCountBase):
    """Mixin that caches a queryset's ``COUNT(*)`` keyed by its compiled SQL.

    Motivation (issue #1908): graphene-django 3.2.3 calls ``.count()``
    *eagerly* inside ``DjangoConnectionField.resolve_connection`` — regardless
    of whether the client selected ``totalCount`` — and ``CountableConnection``
    then resolves ``total_count`` with a second ``.count()``. For the un-scoped
    annotation browse that COUNT runs over the full permission-filtered set, so
    it dominates page latency and fires again on every infinite-scroll page.

    Retained after issue #1906 (justified, not a leftover band-aid): Tier 3
    de-joined ``AnnotationQuerySet.visible_to_user`` (correlated ``EXISTS``
    instead of the ``structural_set__documents`` join) and dropped the trailing
    ``.distinct()``, so the COUNT no longer pays for a fan-out + dedup. But a
    ``COUNT(*)`` over the permission predicate is an OR across several
    dimensions (creator / public / structural / analysis / extract / doc /
    corpus); no single index satisfies that OR, so the count stays an O(n)
    scan that graphene re-fires on every page. Caching the exact value still
    earns its keep on hundreds of thousands of rows. Issue #1906's removal was
    explicitly conditioned on the count becoming "index-cheap"; it does not, so
    the cache stays.

    Casting a queryset to a subclass that mixes this in turns BOTH counts into
    a single cache lookup. The key is the compiled SQL string, which inlines
    the per-user visibility predicate and every active filter — so it is
    naturally user- and filter-scoped and two different users (or two
    different filter combinations) never share a cached value. The value is
    exact when fresh and stale by at most ``_count_cache_ttl`` after a
    create/delete, which is acceptable for a headline tile.

    Clone-safety: Django's ``_clone()``/``_chain()`` reconstruct via
    ``self.__class__(...)``, so the cached-count behaviour survives the
    pagination slicing graphene performs before it reads ``total_count``.

    Concrete subclasses set ``_count_cache_ttl`` and ``_count_cache_prefix``.
    """

    # Concrete subclasses MUST override ``_count_cache_ttl`` with a positive
    # number of seconds. The ``0`` sentinel means "not configured" and bypasses
    # the cache entirely (count runs live) — we deliberately avoid passing it to
    # ``cache.set``, whose meaning for ``0`` is backend-dependent: LocMemCache
    # treats it as "never expire", other backends as "expire immediately".
    _count_cache_ttl: int = 0
    _count_cache_prefix: str = "oc:qs_count"

    def count(self) -> int:
        # If the rows are already in memory (e.g. a parent resolver prefetched
        # this queryset), behave exactly like a plain QuerySet and avoid both
        # the SQL hash and the cache round-trip.
        if self._result_cache is not None:
            return len(self._result_cache)

        # Unconfigured TTL → behave like a plain QuerySet (no caching). Prevents
        # a subclass that forgets to set ``_count_cache_ttl`` from silently
        # caching forever under LocMemCache (see the attribute comment above).
        if self._count_cache_ttl <= 0:
            return super().count()

        from django.core.cache import cache

        sql = str(self.query)
        # ``str(self.query)`` compiles the full SQL (several OR'd visibility
        # subqueries + EXISTS clauses for the annotation browse). That cost is
        # intentionally inside the miss path — do NOT hoist it above the cache
        # lookup; the whole point is to pay it at most once per TTL per filter.
        #
        # Cache-key determinism assumption: the compiled SQL (with parameters
        # interpolated) must be stable for a given user+filter combination.
        # That holds today because the visibility predicate and any label/type
        # filters compile to fixed subqueries. A future filter that bakes a
        # volatile value into the SQL — ``now()``, an unordered ``IN`` list
        # built from a ``set``, or a locale-sensitive comparison — would make
        # the digest unstable and turn every call into a miss. Keep filters on
        # this path order-stable and value-free.
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        cache_key = f"{self._count_cache_prefix}:{digest}"

        # Degrade gracefully on a cache-backend outage (e.g. a transient Redis
        # blip): the eager graphene-django count path means an unhandled cache
        # error would otherwise break the entire annotations browse page rather
        # than just losing the optimisation. Fall back to a live COUNT.
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            value = super().count()
            cache.set(cache_key, value, self._count_cache_ttl)
            return value
        except Exception:  # noqa: BLE001 — cache must never break the page
            return super().count()


# Preserves the concrete QuerySet subclass (e.g. AnnotationQuerySet) across
# ``_exclude_soft_deleted_doc_orphans`` so callers don't lose their typed
# chain when applying the filter.
_QS = TypeVar("_QS", bound=models.QuerySet)


def _exclude_soft_deleted_doc_orphans(qs: _QS) -> _QS:
    """Hide rows whose ``(document, corpus)`` pair has been soft-deleted.

    Used by Annotation and Relationship visibility logic. A row is treated as
    orphaned (and excluded) when:
      - it has both ``document_id`` and ``corpus_id`` set, AND
      - at least one ``DocumentPath`` exists for that pair (so the doc was
        ever pathed into this corpus), AND
      - NO ``DocumentPath`` row for that pair has
        ``is_current=True, is_deleted=False``.

    Rows on standalone documents (never pathed) and structural rows
    (``document_id IS NULL``) are kept — the predicate intentionally does
    nothing for them so that test fixtures and pre-corpus-isolation data
    keep working.

    Mirrors the same predicate as ``Corpus._get_active_documents()`` and
    ``AnnotationService.get_corpus_annotations()`` so visibility
    is consistent across the codebase.
    """
    from opencontractserver.documents.models import DocumentPath

    any_path_for_pair = DocumentPath.objects.filter(
        document_id=OuterRef("document_id"),
        corpus_id=OuterRef("corpus_id"),
    )
    active_path_for_pair = DocumentPath.objects.filter(
        document_id=OuterRef("document_id"),
        corpus_id=OuterRef("corpus_id"),
        is_current=True,
        is_deleted=False,
    )

    return qs.exclude(
        Q(document_id__isnull=False)
        & Q(corpus_id__isnull=False)
        & Exists(any_path_for_pair)
        & ~Exists(active_path_for_pair)
    )


class PermissionedTreeQuerySet(UserCanMixin, TreeQuerySet):
    """Tree-aware queryset that exposes the standard ``user_can`` surface.

    ``user_can`` is inherited from ``UserCanMixin`` (delegates to
    ``_default_user_can``). See ``BaseVisibilityManager.user_can`` for the
    contract — both surfaces converge on the same logic so that filter
    (``visible_to_user``) and check (``user_can``) decisions stay aligned.
    """

    def approved(self) -> "PermissionedTreeQuerySet":
        return self.filter(approved=True)

    def rejected(self) -> "PermissionedTreeQuerySet":
        return self.filter(rejected=True)

    def pending(self) -> "PermissionedTreeQuerySet":
        return self.filter(approved=False, rejected=False)

    def recent(self, days: int = 30) -> "PermissionedTreeQuerySet":
        recent_date = timezone.now() - timedelta(days=days)
        return self.filter(created__gte=recent_date)

    def with_comments(self) -> "PermissionedTreeQuerySet":
        return self.exclude(comment="")

    def by_creator(self, creator: Any) -> "PermissionedTreeQuerySet":
        return self.filter(creator=creator)

    def visible_to_user(self, user: Any) -> "PermissionedTreeQuerySet":
        """
        Gets queryset with_tree_fields that is visible to user. At moment, we're JUST filtering
        on creator and is_public, BUT this will filter on per-obj permissions later.
        """
        # Handle None user as anonymous
        if user is None:
            from django.contrib.auth.models import AnonymousUser

            user = AnonymousUser()

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — no blanket bypass.
        if user.is_anonymous or not hasattr(user, "is_authenticated"):
            queryset = self.filter(Q(is_public=True)).distinct()
        else:
            # Try to use Guardian's permission system for authenticated users
            from guardian.shortcuts import get_objects_for_user

            try:
                # Get objects the user has read permission for via Guardian
                model_name = self.model._meta.model_name
                app_label = self.model._meta.app_label
                perm = f"{app_label}.read_{model_name}"

                # Get objects user has permission for
                permitted_objects = get_objects_for_user(
                    user,
                    perm,
                    klass=self.model,
                    accept_global_perms=False,
                    with_superuser=False,
                )

                # Get the IDs of permitted objects
                permitted_ids = list(permitted_objects.values_list("id", flat=True))

                # Combine: creator OR public OR has explicit permission
                queryset = self.filter(
                    Q(creator=user) | Q(is_public=True) | Q(id__in=permitted_ids)
                ).distinct()

            except (ImportError, Exception):
                # Fall back to creator/public check only if Guardian not available
                queryset = self.filter(Q(creator=user) | Q(is_public=True)).distinct()

        # Apply model-specific optimizations
        model_name = self.model._meta.model_name
        if model_name == "corpus":
            queryset = queryset.select_related(
                "creator",
                "label_set",
                "user_lock",
            )

        return queryset.with_tree_fields()

    def with_tree_fields(self) -> "PermissionedTreeQuerySet":
        return super().with_tree_fields()


class UserFeedbackQuerySet(models.QuerySet):
    def approved(self) -> "UserFeedbackQuerySet":
        return self.filter(approved=True)

    def rejected(self) -> "UserFeedbackQuerySet":
        return self.filter(rejected=True)

    def pending(self) -> "UserFeedbackQuerySet":
        return self.filter(approved=False, rejected=False)

    def recent(self, days: int = 30) -> "UserFeedbackQuerySet":
        recent_date = timezone.now() - timedelta(days=days)
        return self.filter(created__gte=recent_date)

    def with_comments(self) -> "UserFeedbackQuerySet":
        return self.exclude(comment="")

    def by_creator(self, creator: Any) -> "UserFeedbackQuerySet":
        return self.filter(creator=creator)

    def visible_to_user(self, user: Any) -> "UserFeedbackQuerySet":
        """Filter feedback rows to those ``user`` may READ.

        Aligned with ``UserFeedbackManager.user_can`` (Phase A invariant):
        a feedback row inherits READ visibility from the annotation it
        comments on — if ``user`` can see the commented annotation via
        ``Annotation.objects.visible_to_user``, they can read feedback
        on it. The inherited grant is symmetric across the anonymous
        and authenticated branches. Authenticated users additionally
        get creator short-circuit, ``is_public=True`` on the feedback
        row itself, and explicit guardian READ grants on the feedback.
        """
        from django.apps import apps

        from opencontractserver.annotations.models import Annotation

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — feedback visibility follows the commented annotation's
        # visibility for everyone, admins included.
        # Both anonymous and authenticated users may READ a feedback row
        # whose commented annotation is visible to them — mirrors the
        # ``Annotation.objects.visible_to_user(user)``-based gate in
        # ``UserFeedbackManager.user_can`` so the manager check and the
        # queryset filter answer the same question for the same user.
        #
        # ``visible_to_user`` produces a compound subquery here —
        # acceptable for Phase A correctness, but see issue #1655 for
        # the Phase B request-scoped permission cache that should wrap
        # this path before it hits scale.
        visible_annotation_ids = Annotation.objects.visible_to_user(user).values("pk")
        inherited_visibility = Q(commented_annotation_id__in=visible_annotation_ids)

        if user.is_anonymous:
            return self.filter(Q(is_public=True) | inherited_visibility).distinct()

        # Authenticated: creator OR is_public OR commented-annotation-visible
        # OR an explicit guardian READ grant on the feedback row itself
        # (matches ``_default_user_can``'s guardian branch).
        guardian_q = Q()
        try:
            permission_model = apps.get_model(
                "feedback", "userfeedbackuserobjectpermission"
            )
            permitted_ids = permission_model.objects.filter(
                permission__codename="read_userfeedback", user_id=user.id
            ).values_list("content_object_id", flat=True)
            guardian_q = Q(id__in=permitted_ids)
        except LookupError:
            pass

        return self.filter(
            Q(creator=user) | Q(is_public=True) | inherited_visibility | guardian_q
        ).distinct()


class PermissionQuerySet(models.QuerySet):
    def visible_to_user(
        self, user: Any, perm: Optional[str] = None
    ) -> "PermissionQuerySet":
        """Filter to rows visible to ``user`` honoring django-guardian.

        Mirrors ``BaseVisibilityManager.visible_to_user`` so that
        ``Model.objects.user_can`` (which routes through
        ``_default_user_can`` and consults guardian) stays aligned with
        the queryset filter — this is the invariant pinned by
        ``test_authorization_invariants``.

        Logic:
          - Superuser → all rows (DB-default ordering preserved).
          - Anonymous → ``is_public=True`` only.
          - Authenticated non-superuser → ``creator | is_public |
            guardian read codename (user- and group-level)``.

        Concrete subclasses (``DocumentQuerySet``, ``AnnotationQuerySet``,
        ``NoteQuerySet``) override with model-specific logic; this body
        is the fallback for direct uses of ``PermissionManager``.
        """
        from django.apps import apps
        from django.contrib.auth.models import AnonymousUser

        if user is None:
            user = AnonymousUser()

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — no blanket bypass.
        if user.is_anonymous:
            return self.filter(is_public=True).distinct()

        # Authenticated non-superuser: combine creator, is_public, and
        # the user's explicit guardian READ grants — both user-level and
        # group-level. Mirrors BaseVisibilityManager.visible_to_user.
        model_name = self.model._meta.model_name
        app_label = self.model._meta.app_label

        try:
            permission_model = apps.get_model(
                app_label, f"{model_name}userobjectpermission"
            )
            permitted_ids = permission_model.objects.filter(
                permission__codename=f"read_{model_name}", user_id=user.id
            ).values_list("content_object_id", flat=True)
        except LookupError:
            # No user-level guardian table for this model.
            permitted_ids = []

        # Group object-permissions: ``_default_user_can`` resolves group
        # grants (``include_group_permissions=True``), so the filter must
        # OR them in too — otherwise a user whose only READ grant is via
        # a group passes ``user_can`` yet never appears in
        # ``visible_to_user`` (issue #1714). The lazy ``values_list``
        # keeps this a SQL subquery (no extra round-trip). Resolved in
        # its own ``try`` so a missing group table never discards the
        # already-resolved user-level grants.
        try:
            user_group_ids = user.groups.values_list("id", flat=True)
            group_permission_model = apps.get_model(
                app_label, f"{model_name}groupobjectpermission"
            )
            group_permitted_ids = group_permission_model.objects.filter(
                permission__codename=f"read_{model_name}",
                group_id__in=user_group_ids,
            ).values_list("content_object_id", flat=True)
        except LookupError:
            group_permitted_ids = []

        return self.filter(
            Q(creator=user)
            | Q(is_public=True)
            | Q(id__in=permitted_ids)
            | Q(id__in=group_permitted_ids)
        ).distinct()


class DocumentQuerySet(PermissionQuerySet, VectorSearchViaEmbeddingMixin):
    """
    Custom QuerySet for Document that includes permission filtering
    with guardian checks and vector-based search.
    """

    def visible_to_user(
        self, user: Any, perm: Optional[str] = None
    ) -> "DocumentQuerySet":
        """
        Override PermissionQuerySet.visible_to_user to include guardian
        permission checks. Without this override, chaining
        .filter().visible_to_user() would skip guardian entirely.

        Both the user-level and group-level guardian object-permission
        tables are consulted so the filter agrees with
        ``DocumentManager.user_can`` for group-shared users (issue #1714).

        Follows the same pattern as BaseVisibilityManager.visible_to_user
        (opencontractserver/shared/Managers.py). Prefetch optimisation is
        handled by DocumentManager.
        """
        from django.contrib.auth.models import AnonymousUser

        if user is None:
            user = AnonymousUser()

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — no blanket bypass.

        # Documents in public corpora have is_public=True auto-propagated
        # at creation time (see Corpus.add_document, import_document, and
        # Corpus._propagate_public_status_to_documents), so the standard
        # is_public filter naturally covers them without subqueries.

        if user.is_anonymous:
            return self.filter(is_public=True).distinct()

        # Query guardian permission tables directly for performance
        from django.apps import apps

        try:
            permission_model = apps.get_model(
                "documents", "documentuserobjectpermission"
            )
            permitted_ids = permission_model.objects.filter(
                permission__codename="read_document", user_id=user.id
            ).values_list("content_object_id", flat=True)
        except LookupError:
            permitted_ids = []

        # Group object-permissions: ``_default_user_can`` honours group
        # READ grants (``include_group_permissions=True``), so the filter
        # must OR them in too — otherwise a group-shared user passes
        # ``user_can`` yet never appears in ``visible_to_user``
        # (issue #1714). Resolved in its own ``try`` so a missing group
        # table never discards the already-resolved user-level grants.
        try:
            user_group_ids = user.groups.values_list("id", flat=True)
            group_permission_model = apps.get_model(
                "documents", "documentgroupobjectpermission"
            )
            group_permitted_ids = group_permission_model.objects.filter(
                permission__codename="read_document",
                group_id__in=user_group_ids,
            ).values_list("content_object_id", flat=True)
        except LookupError:
            group_permitted_ids = []

        return self.filter(
            Q(creator=user)
            | Q(is_public=True)
            | Q(id__in=permitted_ids)
            | Q(id__in=group_permitted_ids)
        ).distinct()


class AnnotationQuerySet(PermissionQuerySet, VectorSearchViaEmbeddingMixin):
    """
    Custom QuerySet for Annotation model, combining:
      - PermissionQuerySet for permission-based filtering
      - VectorSearchViaEmbeddingMixin for vector-based search

    CTE support: django-cte 3.0+ provides the standalone with_cte() function
    that works on any queryset, so CTEQuerySet inheritance is no longer needed.
    """

    def visible_to_user(
        self, user: Any, perm: Optional[str] = None
    ) -> "AnnotationQuerySet":
        """
        Override to properly handle the annotation privacy model, expressed
        with correlated ``EXISTS`` subqueries so the predicate carries **no
        multi-valued join** and the queryset never needs a trailing
        ``.distinct()`` (issue #1906 — Tier 3 of #1908).

        Why EXISTS instead of joins
        ---------------------------
        The previous implementation reached structural-set document
        visibility through the ``structural_set__documents`` reverse-FK
        relation. That join fans a single annotation out to one row per
        document in the set, so the queryset had to end in ``.distinct()``.
        The ``DISTINCT`` in turn knocked the un-scoped "Browse annotations"
        ``COUNT(*)`` and ``ORDER BY -modified`` page off any single index
        (a full scan + dedup). Expressing document- and corpus-visibility
        as correlated ``EXISTS`` subqueries keeps the outer query on the
        ``annotation`` table alone (no joins, no row fan-out), so:

          * the row set is **identical** to the old join+DISTINCT predicate
            — pinned by ``test_authorization_invariants`` (the
            ``visible_to_user ⟺ user_can(READ)`` invariant) and by the
            de-join regression tests in
            ``test_annotation_visibility_exists.py``; and
          * ``COUNT(*)`` and the ``-modified`` page can ride the annotation
            indexes (migration ``0077`` adds the ``(structural, modified)``
            composite that backs the structural-filtered browse).

        Soft-deleted documents stay in the DB so that "Restore from trash"
        can recover their annotations, but they must NOT surface in
        user-facing queries — otherwise global annotation searches show
        rows pointing at documents the user cannot navigate to (issue
        symptom: "annotations linked to unknown document"). The
        ``_exclude_soft_deleted_doc_orphans`` helper applies the same
        ``DocumentPath(is_current=True, is_deleted=False)`` predicate used
        by ``Corpus._get_active_documents()`` and
        ``AnnotationService.get_corpus_annotations()``.
        """
        from django.apps import apps
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.analyzer.models import (
            Analysis,
            AnalysisUserObjectPermission,
        )
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import (
            Extract,
            ExtractUserObjectPermission,
        )

        # Peer querysets (NoteQuerySet, PermissionQuerySet) normalise None
        # to AnonymousUser at the queryset boundary. The Manager wrapper
        # also does this conversion, but direct queryset calls would raise
        # AttributeError on the `user.is_anonymous` access below.
        if user is None:
            user = AnonymousUser()

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — no blanket bypass. Admins therefore do NOT see
        # trashed-doc annotations through the app; audit/repair of trashed
        # data is done via the Django admin site.

        # Start with base queryset, then hide rows whose linked doc is
        # in trash for the relevant corpus.
        qs = _exclude_soft_deleted_doc_orphans(self.all())

        # For anonymous users, only show public structural annotations.
        if user.is_anonymous:
            # Document-attached: the annotation's own (public) document.
            # ``document__isnull`` / ``document__is_public`` are forward-FK
            # column checks / single joins — they never fan rows out.
            doc_attached_public = Q(document__isnull=False) & Q(
                document__is_public=True
            )
            # Structural-set route (document FK NULL): visible when at least
            # one PUBLIC document references the set. Correlated EXISTS
            # replaces the old ``structural_set__documents`` reverse-FK join
            # (the sole reason this branch previously needed ``.distinct()``).
            structural_set_public = (
                Q(document__isnull=True)
                & Q(structural_set__isnull=False)
                & Exists(
                    Document.objects.filter(
                        structural_annotation_set_id=OuterRef("structural_set_id"),
                        is_public=True,
                    )
                )
            )
            return qs.filter(
                Q(structural=True)
                & (doc_attached_public | structural_set_public)
                & (Q(corpus__isnull=True) | Q(corpus__is_public=True))
            )

        # ---- Authenticated users ----

        # Build visibility filters for analyses / extracts. Kept as lazy
        # querysets so they compile to subqueries (no extra round-trips) and
        # keep the cached-count SQL deterministic (see CachedCountQuerySetMixin).
        visible_analyses = Analysis.objects.filter(Q(is_public=True) | Q(creator=user))
        analyses_with_permission = AnalysisUserObjectPermission.objects.filter(
            user=user
        ).values_list("content_object_id", flat=True)
        visible_analyses = visible_analyses | Analysis.objects.filter(
            id__in=analyses_with_permission
        )

        visible_extracts = Extract.objects.filter(Q(creator=user))
        extracts_with_permission = ExtractUserObjectPermission.objects.filter(
            user=user
        ).values_list("content_object_id", flat=True)
        visible_extracts = visible_extracts | Extract.objects.filter(
            id__in=extracts_with_permission
        )

        # Privacy gate. An annotation clears it when it is structural, the
        # user's own, has no analysis/extract privacy source, or its privacy
        # source is one the user can see. All branches are own-column checks
        # or ``__in`` subqueries — no joins.
        visibility_filter = (
            # Structural annotations (always visible if doc is readable)
            Q(structural=True)
            |
            # User's own annotations
            Q(creator=user)
            |
            # Regular annotations (no privacy fields)
            (Q(created_by_analysis__isnull=True) & Q(created_by_extract__isnull=True))
            |
            # Analysis-created annotations user can see
            (Q(created_by_analysis__in=visible_analyses))
            |
            # Extract-created annotations user can see
            (Q(created_by_extract__in=visible_extracts))
        )

        # Guardian READ grants for documents and corpuses — both the
        # user-level and group-level object-permission tables.
        # ``_default_user_can`` resolves group grants
        # (``include_group_permissions=True``), so omitting the group
        # tables here would drift the annotation filter from the
        # Document/Corpus ``user_can`` checks (issue #1714). Lazy
        # ``values_list`` keeps each a SQL subquery.
        user_group_ids = user.groups.values_list("id", flat=True)

        try:
            doc_perm_model = apps.get_model("documents", "documentuserobjectpermission")
            doc_permitted_ids = doc_perm_model.objects.filter(
                permission__codename="read_document", user_id=user.id
            ).values_list("content_object_id", flat=True)
            doc_group_perm_model = apps.get_model(
                "documents", "documentgroupobjectpermission"
            )
            doc_group_permitted_ids = doc_group_perm_model.objects.filter(
                permission__codename="read_document", group_id__in=user_group_ids
            ).values_list("content_object_id", flat=True)
        except LookupError:
            doc_permitted_ids = []
            doc_group_permitted_ids = []

        try:
            corpus_perm_model = apps.get_model("corpuses", "corpususerobjectpermission")
            corpus_permitted_ids = corpus_perm_model.objects.filter(
                permission__codename="read_corpus", user_id=user.id
            ).values_list("content_object_id", flat=True)
            corpus_group_perm_model = apps.get_model(
                "corpuses", "corpusgroupobjectpermission"
            )
            corpus_group_permitted_ids = corpus_group_perm_model.objects.filter(
                permission__codename="read_corpus", group_id__in=user_group_ids
            ).values_list("content_object_id", flat=True)
        except LookupError:
            corpus_permitted_ids = []
            corpus_group_permitted_ids = []

        # A document is visible when it is public, the user's own, or carries
        # an explicit (user- or group-level) guardian READ grant. Reused by
        # both the document-attached and structural-set EXISTS subqueries.
        doc_visible = (
            Q(is_public=True)
            | Q(creator=user)
            | Q(pk__in=doc_permitted_ids)
            | Q(pk__in=doc_group_permitted_ids)
        )
        corpus_visible = (
            Q(is_public=True)
            | Q(creator=user)
            | Q(pk__in=corpus_permitted_ids)
            | Q(pk__in=corpus_group_permitted_ids)
        )

        # Handle TWO types of annotations:
        # 1. Document-attached: the row's own document FK must be visible.
        # 2. Structural via structural_set (document FK NULL): visible if ANY
        #    document referencing that set is visible. Both checks are
        #    correlated EXISTS subqueries — no joins, so no row fan-out and no
        #    ``.distinct()`` (issue #1906).
        doc_attached_filter = Q(document__isnull=False) & Exists(
            Document.objects.filter(pk=OuterRef("document_id")).filter(doc_visible)
        )
        structural_set_filter = (
            Q(document__isnull=True)
            & Q(structural_set__isnull=False)
            & Q(structural=True)
            & Exists(
                Document.objects.filter(
                    structural_annotation_set_id=OuterRef("structural_set_id")
                ).filter(doc_visible)
            )
        )

        doc_visibility_filter = doc_attached_filter | structural_set_filter

        # Corpus visibility: null corpus (structural / standalone) is allowed,
        # otherwise the annotation's corpus must be visible — again via a
        # correlated EXISTS rather than a ``corpus__*`` join.
        corpus_filter = Q(corpus__isnull=True) | Exists(
            Corpus.objects.filter(pk=OuterRef("corpus_id")).filter(corpus_visible)
        )

        return qs.filter(visibility_filter & doc_visibility_filter & corpus_filter)

    def with_cached_count(self) -> "CachedCountAnnotationQuerySet":
        """Return a clone whose ``.count()`` is cached (issue #1908).

        Used only by the un-scoped annotations browse, where the exact
        ``totalCount`` over the full permission-filtered set is the dominant
        cost. Document- and corpus-scoped annotation queries deliberately do
        NOT call this — their counts are bounded and must stay live so a count
        badge updates immediately after an edit.

        The returned clone is an instance of ``CachedCountAnnotationQuerySet``;
        because ``_clone()`` preserves ``self.__class__``, any further
        ``.select_related()`` / ``.filter()`` / pagination slicing keeps the
        cached-count behaviour. See ``CachedCountQuerySetMixin``.
        """
        # Reassigning ``__class__`` on a fresh ``_chain()`` clone is an
        # intentional, well-established Django-internal technique for swapping a
        # queryset to a subclass without re-running the query construction. It
        # is safe here because ``CachedCountAnnotationQuerySet`` only ADDS the
        # cached ``.count()`` and shares ``AnnotationQuerySet``'s state layout.
        clone = self._chain()  # type: ignore[attr-defined]
        clone.__class__ = CachedCountAnnotationQuerySet
        return clone


class CachedCountAnnotationQuerySet(CachedCountQuerySetMixin, AnnotationQuerySet):
    """``AnnotationQuerySet`` whose ``COUNT(*)`` is cached.

    Reached via ``AnnotationQuerySet.with_cached_count()`` rather than
    instantiated directly. The cache TTL/namespace come from
    ``opencontractserver.constants.annotations`` so the value and the
    documentation of the freshness window live in one place.
    """

    _count_cache_ttl = ANNOTATION_COUNT_CACHE_TTL_SECONDS
    _count_cache_prefix = ANNOTATION_COUNT_CACHE_PREFIX


class NoteQuerySet(PermissionQuerySet, VectorSearchViaEmbeddingMixin):
    """
    Custom QuerySet for Note model, combining:
      - PermissionQuerySet
      - VectorSearchViaEmbeddingMixin

    Notes inherit permissions from their parent document and corpus
    following the MIN(document_permission, corpus_permission) pattern.

    CTE support: django-cte 3.0+ provides the standalone with_cte() function
    that works on any queryset, so CTEQuerySet inheritance is no longer needed.
    """

    def visible_to_user(self, user: Any, perm: Optional[str] = None) -> "NoteQuerySet":
        """Filter notes to those visible to ``user``.

        Aligned with ``NoteManager.user_can`` (Phase A invariant): a note
        is visible when the user created it OR they can see both the
        parent document and the parent corpus (MIN logic). Document and
        corpus visibility are evaluated via the same
        ``Document.objects.visible_to_user`` / ``Corpus.objects.visible_to_user``
        managers that ``user_can`` composes — so authenticated users
        with explicit guardian READ grants on the parent doc + corpus
        see their notes in list views, matching the manager check.
        Group-level guardian grants flow through transparently because
        both delegated managers honour them (issue #1714).
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        if user is None:
            user = AnonymousUser()

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — no blanket bypass; note visibility is MIN(doc, corpus)
        # for everyone, admins included.

        # Doc/corpus visibility delegated to the doc/corpus managers so the
        # full creator/public/guardian rules apply (mirroring user_can's
        # ``Document.objects.user_can`` / ``Corpus.objects.user_can`` composition).
        visible_doc_ids = Document.objects.visible_to_user(user).values_list(
            "pk", flat=True
        )
        visible_corpus_ids = Corpus.objects.visible_to_user(user).values_list(
            "pk", flat=True
        )
        doc_visible = Q(document_id__in=visible_doc_ids)
        corpus_visible = Q(corpus__isnull=True) | Q(corpus_id__in=visible_corpus_ids)

        if user.is_anonymous:
            # Anonymous additionally requires the note itself to be public —
            # NoteManager.user_can's anonymous branch denies non-public notes
            # outright.
            return self.filter(
                Q(is_public=True) & doc_visible & corpus_visible
            ).distinct()

        return self.filter(Q(creator=user) | (doc_visible & corpus_visible)).distinct()
