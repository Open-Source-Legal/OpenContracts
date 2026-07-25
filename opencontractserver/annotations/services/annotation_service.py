"""Annotation read-service — permission-filtered annotation queries.

Relocated verbatim from the former ``annotations/query_optimizer.py``
``AnnotationQueryOptimizer`` monolith as Phase 3 of the service-layer
centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.

Behaviour is preserved exactly: prefetch shapes, the request-scoped
permission / instance caches, and the ``MIN(document, corpus)`` effective-
permission model are byte-for-byte identical to the former optimizer.
"""

from collections.abc import Iterable
from typing import Any, Optional, cast

from django.db.models import (
    BooleanField,
    Case,
    Count,
    Prefetch,
    Q,
    QuerySet,
    Value,
    When,
)

from opencontractserver.shared.services import BaseService

# ``source_visibility`` imports stay inside methods below: importing that module
# at file load time creates Django app-loading cycles through models/managers.


class AnnotationService(BaseService):
    """
    Optimized annotation queries with permission filtering.
    Direct database queries without caching.

    Permission model:
    - Document permissions are primary (most restrictive)
    - Corpus permissions are secondary
    - Effective permission = MIN(document_permission, corpus_permission)
    - Structural annotations always have READ permission if document is readable
    """

    @classmethod
    def _compute_effective_permissions(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
        context=None,
    ) -> tuple[bool, bool, bool, bool, bool]:
        """
        Compute effective permissions based on document and corpus.

        Special handling for COMMENT permission:
        - If corpus.allow_comments is True, any readable annotation is commentable
        - Otherwise, standard MIN(doc_comment, corpus_comment) logic applies

        ``context`` is the GraphQL request context. When provided, results are
        cached on ``context._effective_perms_cache`` keyed by
        ``(user_id, document_id, corpus_id)`` so subsequent resolvers in the
        same request reuse the answer instead of re-running the 10
        ``user_can`` round-trips and the
        ``Document``/``Corpus`` ``.get()`` lookups. The cache is also primed
        with the fetched ORM instances so other resolvers inside this request
        can avoid re-fetching them.

        Returns: (can_read, can_create, can_update, can_delete, can_comment)
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.types.enums import PermissionTypes

        cache_key = (
            getattr(user, "id", None),
            document_id,
            corpus_id,
        )
        perms_cache = None
        if context is not None:
            perms_cache = getattr(context, "_effective_perms_cache", None)
            if perms_cache is None:
                perms_cache = {}
                context._effective_perms_cache = perms_cache
            cached = perms_cache.get(cache_key)
            if cached is not None:
                return cached

        def _store(
            result: tuple[bool, bool, bool, bool, bool],
        ) -> tuple[bool, bool, bool, bool, bool]:
            if perms_cache is not None:
                perms_cache[cache_key] = result
            return result

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — no blanket grant; effective perms come from doc+corpus below.

        document = cls._get_document_for_request(document_id, context)
        if document is None:
            return _store((False, False, False, False, False))

        # Anonymous users only have read access to public documents/corpuses
        if user.is_anonymous:
            if not document.is_public:
                return _store((False, False, False, False, False))

            if corpus_id:
                corpus = cls._get_corpus_for_request(corpus_id, context)
                if corpus is None or not corpus.is_public:
                    return _store((False, False, False, False, False))

            return _store((True, False, False, False, False))

        # Authenticated user — document permissions first.
        # NOTE: Routes through ``Document.objects.user_can`` / ``Corpus.objects.user_can``
        # so creator status is honored — a user who owns both the annotation
        # and its parent document/corpus is not False-denied.
        #
        # Forward ``context`` as ``request`` so the Tier 2
        # ``PermissionQueryOptimizer`` (PR #1665) dedupes the guardian
        # lookups across distinct Document/Corpus instances in this request.
        doc_read = Document.objects.user_can(
            user, document, PermissionTypes.READ, request=context
        )
        if not doc_read:
            return _store((False, False, False, False, False))

        doc_create = Document.objects.user_can(
            user, document, PermissionTypes.CREATE, request=context
        )
        doc_update = Document.objects.user_can(
            user, document, PermissionTypes.UPDATE, request=context
        )
        doc_delete = Document.objects.user_can(
            user, document, PermissionTypes.DELETE, request=context
        )
        doc_comment = Document.objects.user_can(
            user, document, PermissionTypes.COMMENT, request=context
        )

        if not corpus_id:
            return _store((doc_read, doc_create, doc_update, doc_delete, doc_comment))

        corpus = cls._get_corpus_for_request(corpus_id, context)
        if corpus is None:
            # Corpus doesn't exist or isn't visible — fall back to document perms.
            return _store((doc_read, doc_create, doc_update, doc_delete, doc_comment))

        corpus_read = Corpus.objects.user_can(
            user, corpus, PermissionTypes.READ, request=context
        )
        corpus_create = Corpus.objects.user_can(
            user, corpus, PermissionTypes.CREATE, request=context
        )
        corpus_update = Corpus.objects.user_can(
            user, corpus, PermissionTypes.UPDATE, request=context
        )
        corpus_delete = Corpus.objects.user_can(
            user, corpus, PermissionTypes.DELETE, request=context
        )
        corpus_comment = Corpus.objects.user_can(
            user, corpus, PermissionTypes.COMMENT, request=context
        )

        final_read = doc_read and corpus_read

        # BACON MODE: If corpus allows comments, readable = commentable.
        if corpus.allow_comments:
            final_comment = final_read
        else:
            final_comment = doc_comment and corpus_comment

        return _store(
            (
                final_read,
                doc_create and corpus_create,
                doc_update and corpus_update,
                doc_delete and corpus_delete,
                final_comment,
            )
        )

    @staticmethod
    def _get_document_for_request(document_id: int, context):
        """
        Return the ``Document`` for ``document_id``, caching the instance on
        ``context._document_instance_cache`` so the same request never fetches
        the same row twice.

        ``structural_annotation_set`` is ``select_related`` so the FK
        dereference inside ``get_document_annotations`` (which builds a query
        spanning the document's structural set) stays on the original SELECT
        instead of triggering a follow-up round-trip per request.
        """
        from opencontractserver.documents.models import Document

        if context is None:
            try:
                return Document.objects.select_related("structural_annotation_set").get(
                    id=document_id
                )
            except Document.DoesNotExist:
                return None

        cache = getattr(context, "_document_instance_cache", None)
        if cache is None:
            cache = {}
            context._document_instance_cache = cache
        if document_id in cache:
            return cache[document_id]
        try:
            instance = Document.objects.select_related("structural_annotation_set").get(
                id=document_id
            )
        except Document.DoesNotExist:
            instance = None
        cache[document_id] = instance
        return instance

    @staticmethod
    def _get_corpus_for_request(corpus_id: int, context):
        """
        Return the ``Corpus`` for ``corpus_id``, caching the instance on
        ``context._corpus_instance_cache``. Mirror of
        ``_get_document_for_request``.
        """
        from opencontractserver.corpuses.models import Corpus

        if context is None:
            try:
                return Corpus.objects.get(id=corpus_id)
            except Corpus.DoesNotExist:
                return None

        cache = getattr(context, "_corpus_instance_cache", None)
        if cache is None:
            cache = {}
            context._corpus_instance_cache = cache
        if corpus_id in cache:
            return cache[corpus_id]
        try:
            instance = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            instance = None
        cache[corpus_id] = instance
        return instance

    @classmethod
    def get_document_annotations(
        cls,
        document_id: int,
        user,
        corpus_id: Optional[int] = None,
        pages: Optional[list[int]] = None,
        analysis_id: Optional[int] = None,
        extract_id: Optional[int] = None,
        structural: Optional[bool] = None,  # Filter for structural annotations
        check_current_version: bool = True,  # NEW: Check if document is current and has active path
        context=None,
    ) -> QuerySet:
        """
        Get annotations with permission filtering and optimized queries.
        Permissions are computed at document+corpus level and applied to all annotations.

        IMPORTANT: Returns annotations from BOTH:
        1. Direct document annotations (document FK) - corpus-specific annotations
        2. Structural annotations via document's structural_annotation_set (structural_set FK) - shared annotations

        ``context`` is the GraphQL request context. When provided, the
        permission check, the parent ``Document`` fetch, and the
        ``Corpus`` fetch are cached for the lifetime of the request, so
        sibling resolvers (``allAnnotations`` / ``allRelationships`` /
        ``docAnnotations``) don't repeat the work for the same
        ``(user, document, corpus)`` tuple.
        """
        from opencontractserver.annotations.models import Annotation

        # Compute effective permissions once (cached on context if available)
        can_read, can_create, can_update, can_delete, can_comment = (
            cls._compute_effective_permissions(
                user, document_id, corpus_id, context=context
            )
        )
        # No read permission = no annotations
        if not can_read:
            return Annotation.objects.none()

        # Check if document has active path in corpus (version awareness)
        if check_current_version and corpus_id:
            from opencontractserver.documents.models import DocumentPath

            has_active_path = DocumentPath.objects.filter(
                document_id=document_id,
                corpus_id=corpus_id,
                is_current=True,
                is_deleted=False,
            ).exists()

            if not has_active_path:
                # Document is deleted or not current in corpus
                return Annotation.objects.none()

        # Fetch the document (request-cached if ``context`` is provided so we
        # don't re-fetch the row that ``_compute_effective_permissions`` and
        # parent resolvers have already loaded). The cached fetcher
        # ``_get_document_for_request`` uses ``select_related(
        # "structural_annotation_set")`` so the structural-set branch below
        # never triggers a follow-up round-trip on FK dereference.
        document = cls._get_document_for_request(document_id, context)
        if document is None:
            return Annotation.objects.none()

        # Build base filter for annotations from BOTH sources:
        # 1. Direct document annotations (corpus-specific, user-created)
        # 2. Structural annotations via document's structural_annotation_set (shared)
        doc_filters = Q(document_id=document_id)

        if document.structural_annotation_set_id:
            # Include structural annotations from the shared set
            # These annotations have document_id=NULL but structural_set_id=X
            doc_filters |= Q(
                structural_set_id=document.structural_annotation_set_id,
                structural=True,  # Safety check - structural_set annotations must be structural
            )

        # Build optimized query with combined document filters
        qs = Annotation.objects.filter(doc_filters)

        # Apply privacy filtering for created_by_* fields. Applies to ALL
        # users including superusers (scoped admin access, 2026-05): an admin
        # only sees analysis-/extract-private annotations it can actually
        # reach. The shared gate honours user- AND group-level guardian
        # grants (parity with ``user_can``'s privacy recursion) and encodes
        # the anonymous rules (public analyses only; never extracts).
        from opencontractserver.utils.source_visibility import (
            apply_source_privacy_gate,
        )

        qs = apply_source_privacy_gate(qs, user)

        # Add filters
        if corpus_id:
            # Filter by corpus (permissions already checked)
            # IMPORTANT: Structural_set annotations have corpus_id=NULL (they're shared across corpuses)
            # So we need to keep BOTH:
            # 1. Corpus-specific annotations where corpus_id matches
            # 2. Structural_set annotations (which have corpus_id=NULL but structural_set_id set)
            corpus_filter = Q(corpus_id=corpus_id)

            if document.structural_annotation_set_id:
                # Also keep structural annotations from this document's set
                # (already filtered in base query, but corpus_id=NULL so we must explicitly allow them)
                corpus_filter |= Q(
                    structural_set_id=document.structural_annotation_set_id,
                    structural=True,
                )

            qs = qs.filter(corpus_filter)

            # Apply structural filter if specified
            if structural is not None:
                qs = qs.filter(structural=structural)
        else:
            # No corpus = structural only (always readable if doc is readable)
            # Unless explicitly requested otherwise
            if structural is False:
                # Explicitly requesting non-structural without corpus = empty
                return Annotation.objects.none()
            # Default to structural only when no corpus
            qs = qs.filter(structural=True)

        if pages:
            qs = qs.filter(page__in=pages)

        if analysis_id:
            # Additional filter for analysis visibility
            from opencontractserver.analyzer.models import Analysis
            from opencontractserver.types.enums import PermissionTypes

            try:
                analysis = Analysis.objects.get(id=analysis_id)
                # Check analysis visibility as additional restriction
                # User can see annotations if: analysis is public, user is creator, OR has explicit READ permission
                has_permission = (
                    analysis.is_public
                    or analysis.creator_id == user.id
                    or analysis.user_can(user, PermissionTypes.READ, request=context)
                )
                if not has_permission:
                    return Annotation.objects.none()
            except Analysis.DoesNotExist:
                return Annotation.objects.none()
            qs = qs.filter(analysis_id=analysis_id)
        else:
            # When analysis_id is not provided, exclude all analysis annotations
            # We only want user/manual annotations in this case
            qs = qs.filter(analysis__isnull=True)

        if extract_id:
            # Filter to annotations that are sources for datacells in this extract
            from opencontractserver.extracts.models import Datacell

            datacell_annotation_ids = Datacell.objects.filter(
                extract_id=extract_id, document_id=document_id
            ).values_list("sources__id", flat=True)
            qs = qs.filter(id__in=datacell_annotation_ids)

        # Optimize query with prefetches and annotate computed permissions for
        # the GraphQL ``myPermissions`` field. Permission values are constant
        # for the whole queryset (computed once above) so they're cheap.
        #
        # NB: previously this also did ``.annotate(feedback_count=Count(...))``
        # plus ``.distinct()``. Both were per-row costs paid for every
        # annotation in the response, even when no feedback exists:
        #   - the Count forced a LEFT JOIN user_feedback + GROUP BY
        #     annotation.id, which Postgres has to materialise/sort with
        #     ``select_related`` joins also live
        #   - the distinct then ran a sort/hash unique pass on the joined
        #     row set
        # Neither was necessary: the filters above don't introduce
        # duplicates (no M2M JOINs — analysis/extract visibility uses
        # subqueries), and ``feedback_count`` is now computed from the
        # prefetched ``user_feedback`` list in
        # ``AnnotationType.resolve_feedback_count``.
        from opencontractserver.feedback.models import UserFeedback

        # Structural rows are writable ONLY via the superuser break-glass
        # (see ``AnnotationManager.user_can``); reflect that in the
        # pre-computed myPermissions so the UI mirrors what mutations will
        # actually allow. ``_compute_effective_permissions`` has no superuser
        # short-circuit (scoped admin access, 2026-05), so the break-glass
        # must be applied here explicitly.
        user_is_superuser = bool(getattr(user, "is_superuser", False))

        qs = (
            qs.select_related("annotation_label", "creator", "analysis")
            .prefetch_related(
                Prefetch(
                    "user_feedback",
                    queryset=UserFeedback.objects.only(
                        "id",
                        "approved",
                        "rejected",
                        "commented_annotation_id",
                    ),
                )
            )
            .annotate(
                _can_read=Value(can_read),
                _can_create=Value(can_create),
                # ``can_update``/``can_delete`` came from doc+corpus perms;
                # mask them per-row on structural annotations so the
                # annotation matches ``AnnotationManager.user_can``'s
                # structural-write rule: True for superusers (break-glass),
                # False for everyone else.
                _can_update=Case(
                    When(structural=True, then=Value(user_is_superuser)),
                    default=Value(can_update),
                    output_field=BooleanField(),
                ),
                _can_delete=Case(
                    When(structural=True, then=Value(user_is_superuser)),
                    default=Value(can_delete),
                    output_field=BooleanField(),
                ),
                _can_comment=Value(can_comment),
            )
        )

        return qs

    @classmethod
    def get_annotations_for_path(
        cls, corpus_id: int, path: str, user, version: Optional[int] = None, **kwargs
    ) -> QuerySet:
        """
        Get annotations for document at a specific path (defaults to current version).
        This is the recommended method for corpus-scoped annotation queries.

        Args:
            corpus_id: The corpus ID
            path: The document path in the corpus
            user: The requesting user
            version: Optional specific version number (defaults to current)
            **kwargs: Additional arguments passed to get_document_annotations

        Returns:
            QuerySet of annotations for the document at this path
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import DocumentPath

        # Find the document at this path
        path_query = DocumentPath.objects.filter(corpus_id=corpus_id, path=path)

        if version is not None:
            # Specific version requested
            path_query = path_query.filter(version_number=version)
        else:
            # Default to current, non-deleted
            path_query = path_query.filter(is_current=True, is_deleted=False)

        try:
            document_path = path_query.get()
        except DocumentPath.DoesNotExist:
            # Path doesn't exist or is deleted
            return Annotation.objects.none()
        except (
            DocumentPath.MultipleObjectsReturned
        ):  # pragma: no cover -- defensive; uniqueness constraints prevent this
            # Shouldn't happen with constraints. first() is non-None when
            # MultipleObjectsReturned was raised (≥2 rows); cast narrows
            # DocumentPath | None → DocumentPath for mypy.
            document_path = cast("DocumentPath", path_query.first())

        # Use existing method with resolved document_id
        return cls.get_document_annotations(
            document_id=document_path.document_id,
            user=user,
            corpus_id=corpus_id,
            check_current_version=False,  # Already checked via path
            **kwargs,
        )

    @classmethod
    def get_extract_annotation_summary(
        cls, document_id: int, extract_id: int, user
    ) -> dict:
        """
        Get summary of annotations used in specific extract.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.extracts.models import Datacell, Extract

        # Get extract to determine corpus
        try:
            extract = Extract.objects.get(id=extract_id)
            corpus_id = extract.corpus_id if hasattr(extract, "corpus_id") else None
        except Extract.DoesNotExist:
            corpus_id = None

        # Use unified permission check
        can_read, _, _, _, _ = cls._compute_effective_permissions(
            user, document_id, corpus_id
        )

        if not can_read:
            return {
                "total_source_annotations": 0,
                "by_label": {},
                "pages_with_sources": [],
            }

        # Get annotation IDs used as sources in this extract
        source_annotation_ids = (
            Datacell.objects.filter(extract_id=extract_id, document_id=document_id)
            .values_list("sources__id", flat=True)
            .distinct()
        )

        # Get annotation summary
        annotations = Annotation.objects.filter(id__in=source_annotation_ids)

        summary = {
            "total_source_annotations": annotations.count(),
            "by_label": {},
            "pages_with_sources": list(
                annotations.values_list("page", flat=True).distinct().order_by("page")
            ),
        }

        # Count by label
        label_counts = annotations.values("annotation_label__text").annotate(
            count=Count("id")
        )

        summary["by_label"] = {
            item["annotation_label__text"]: item["count"]
            for item in label_counts
            if item["annotation_label__text"]
        }

        return summary

    @classmethod
    def get_label_distribution_for_corpus(
        cls,
        corpus,
        visible_doc_ids,
        top_n: int,
        exclude_label_prefix: Optional[str] = None,
        *,
        user: Any,
    ) -> list[dict]:
        """Top-N annotation-label distribution across a corpus's visible docs.

        Powers the ``corpusIntelligenceAggregates`` resolver's label panel.
        Callers supply ``visible_doc_ids`` (a values queryset from a
        permission-filtered Document queryset) so the visibility decision is
        made once at the call site and the ``__in`` clauses below push
        subqueries to SQL rather than materialising ids into Python.

        ``user`` engages the ``created_by_*`` privacy gate (2026-06 audit):
        without it, label names and counts of analysis-/extract-private
        annotations leaked into the aggregate for viewers who could not see
        the rows themselves. The parameter is REQUIRED and keyword-only —
        omission is a ``TypeError`` at the call site, never a silent
        under-count. Passing an explicit ``None`` (or ``AnonymousUser``)
        yields the most restrictive anonymous shape: public analyses only,
        no extracts. (Current callers: the ``corpusIntelligenceAggregates``
        resolver in ``config/graphql/corpus_queries.py`` and the privacy
        regression tests.)

        ``distinct=True`` on the count is required: structural annotations are
        joined via the ``structural_set__documents`` reverse FK, which fans a
        single annotation out to one row per referencing visible document and
        would otherwise inflate that label's count.

        Args:
            corpus: The (already permission-checked) Corpus instance.
            visible_doc_ids: Queryset of visible document ids in the corpus.
            top_n: Number of labels to return, most frequent first.
            exclude_label_prefix: When set, labels whose text starts with this
                prefix are excluded (e.g. the reserved ``OC_`` namespace).

        Returns:
            List of ``{"annotation_label__text", "annotation_label__color",
            "count"}`` dicts ordered by descending count.
        """
        from opencontractserver.utils.source_visibility import (
            apply_source_privacy_gate,
        )

        qs = corpus.annotations.filter(
            Q(document_id__in=visible_doc_ids)
            | Q(structural_set__documents__in=visible_doc_ids, structural=True)
        ).exclude(annotation_label__isnull=True)
        # Privacy gate (2026-06 audit): exclude analysis-/extract-private
        # rows the user cannot see so their label names/counts don't leak
        # into the aggregate. Structural rows bypass privacy as everywhere.
        qs = apply_source_privacy_gate(qs, user)
        if exclude_label_prefix:
            qs = qs.exclude(annotation_label__text__startswith=exclude_label_prefix)
        return list(
            qs.values("annotation_label__text", "annotation_label__color")
            .annotate(count=Count("id", distinct=True))
            .order_by("-count")[:top_n]
        )

    @classmethod
    def get_corpus_annotations(
        cls,
        corpus_id: int,
        user,
        structural: Optional[bool] = None,
        analysis_isnull: Optional[bool] = None,
        context: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get annotations for a corpus with proper permission filtering.
        Handles BOTH document-attached AND structural annotations correctly.

        This method is for corpus-wide queries where no specific document_id is provided.
        It properly includes structural annotations which have:
        - document_id = NULL (linked via structural_set instead)
        - corpus_id = NULL (shared across corpuses via structural_set)

        Permission model:
        - User must have READ permission on corpus
        - Annotations are filtered to only those on documents user can see
        - Structural annotations are included if their structural_set is linked
          to any visible document in the corpus

        Args:
            corpus_id: The corpus ID to query annotations for
            user: The requesting user
            structural: Optional filter for structural annotations (True/False/None)
            analysis_isnull: Optional filter for analysis field (True=manual only)
            context: Optional GraphQL context (``info.context``) threaded into
                ``user_can`` so Tier-2 request-scoped permission caching applies.

        Returns:
            QuerySet of annotations with permission filtering applied
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.types.enums import PermissionTypes

        # Superusers are computed like any other user (scoped admin access,
        # 2026-05) — the corpus-permission path below applies to admins too.
        # Check corpus permission first
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return Annotation.objects.none()

        # Anonymous users: corpus must be public
        if user.is_anonymous:
            if not corpus.is_public:
                return Annotation.objects.none()
            # Get public documents in this corpus
            visible_doc_ids = Document.objects.filter(
                is_public=True,
                path_records__corpus_id=corpus_id,
                path_records__is_current=True,
                path_records__is_deleted=False,
            ).values_list("id", flat=True)
        else:
            # Check if user has READ permission on corpus
            has_corpus_read = corpus.user_can(
                user, PermissionTypes.READ, request=context
            )
            if not has_corpus_read:
                return Annotation.objects.none()

            # Get documents visible to user in this corpus
            visible_doc_ids = (
                Document.objects.visible_to_user(user)
                .filter(
                    path_records__corpus_id=corpus_id,
                    path_records__is_current=True,
                    path_records__is_deleted=False,
                )
                .values_list("id", flat=True)
            )

        if not visible_doc_ids:
            return Annotation.objects.none()

        # Get structural_annotation_set IDs from visible documents
        structural_set_ids = Document.objects.filter(
            id__in=visible_doc_ids,
            structural_annotation_set_id__isnull=False,
        ).values_list("structural_annotation_set_id", flat=True)

        # Build query for BOTH types of annotations:
        # 1. Document-attached annotations: corpus_id matches AND document is visible
        # 2. Structural annotations: structural_set_id is from a visible document
        base_filter = Q(corpus_id=corpus_id, document_id__in=visible_doc_ids)

        if structural_set_ids:
            base_filter |= Q(structural_set_id__in=structural_set_ids, structural=True)

        qs = Annotation.objects.filter(base_filter)

        # Apply privacy filtering for created_by_* fields. Applies to ALL
        # users including superusers (scoped admin access, 2026-05): an admin
        # only sees analysis-/extract-private annotations it can actually
        # reach. The shared builders honour user- AND group-level guardian
        # grants (parity with ``user_can``'s privacy recursion) and encode
        # the anonymous rules (public analyses only; never extracts).
        #
        # Intentionally UNCONDITIONAL — no ``if not user.is_anonymous``
        # guard. The old guard skipped privacy filtering entirely for
        # anonymous viewers, leaking analysis-/extract-private annotations
        # on public corpora (2026-06 audit). Anonymous handling lives inside
        # the shared gate.
        from opencontractserver.utils.source_visibility import (
            apply_source_privacy_gate,
        )

        qs = apply_source_privacy_gate(qs, user)

        # Apply optional filters
        if structural is not None:
            qs = qs.filter(structural=structural)
        if analysis_isnull is not None:
            qs = qs.filter(analysis__isnull=analysis_isnull)

        # NOTE: intentionally returns an UNANNOTATED queryset — no
        # pre-computed ``_can_*`` values (unlike ``get_document_annotations``,
        # where one (doc, corpus) pair covers every row). A corpus-wide
        # listing spans many documents with differing effective permissions,
        # so per-row ``myPermissions`` falls back to
        # ``AnnotatePermissionsForReadMixin``'s standard resolution.
        return qs.distinct()

    @classmethod
    def structural_document_prefetch(
        cls,
        *,
        user: Any,
        corpus_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> Prefetch:
        """Build the ``structural_set__documents`` prefetch consumed by
        ``AnnotationType.resolve_document``.

        Structural annotations carry ``document_id=NULL`` and reach their
        document only through the shared ``structural_set``. A
        ``StructuralAnnotationSet`` is deduplicated by content hash and is
        therefore shared across documents AND corpuses, so an *unscoped*
        resolution (``structural_set.documents.first()``) returns an
        arbitrary member of the set — typically the standalone import source
        (which has no path in any corpus) or a copy living in a different
        corpus. In the corpus annotation cards that produces a card that
        either names the wrong document or fails to deep-link into the
        corpus being viewed.

        Scoping the prefetch to the current context makes
        ``resolve_document`` return the context-local copy. Mirrors the
        corpus-scoped structural lookup in
        ``opencontractserver/mcp/tools.py::search_corpus``.

        ``document_id`` takes precedence over ``corpus_id`` so the
        document-knowledge-base view (which always passes a document, and
        often a corpus too) resolves to the *exact* document being viewed,
        while the corpus annotation cards (document_id=None) fall back to
        the corpus-local copy.

        The prefetch is ALSO scoped to documents ``user`` may READ
        (``Document.objects.visible_to_user``). A ``StructuralAnnotationSet``
        is content-hash deduplicated and therefore shared across documents
        AND owners, so an unscoped prefetch can surface a private copy owned
        by another user. Filtering here means ``resolve_document`` never has
        to re-gate per row — the visibility check runs once when the prefetch
        is evaluated for the whole page. ``user`` is required (keyword-only)
        so a caller cannot accidentally build an un-gated prefetch.

        Args:
            user: The requesting user; the prefetched documents are
                intersected with ``Document.objects.visible_to_user(user)``.
            corpus_id: When set (and no ``document_id``), restrict the
                prefetched documents to those with a current, non-deleted
                path in this corpus.
            document_id: When set, restrict to exactly this document — the
                document being viewed.

        Returns:
            A ``Prefetch`` for ``structural_set__documents`` whose queryset is
            scoped to the supplied context and ordered deterministically by
            ``slug`` (the tie-break when a structural set maps to more than
            one in-scope document, matching ``search_corpus``).
        """
        from opencontractserver.documents.models import Document

        documents = Document.objects.visible_to_user(user).select_related("creator")
        if document_id is not None:
            documents = documents.filter(id=document_id)
        elif corpus_id is not None:
            documents = documents.filter(
                path_records__corpus_id=corpus_id,
                path_records__is_current=True,
                path_records__is_deleted=False,
            )
        return Prefetch(
            "structural_set__documents",
            queryset=documents.order_by("slug").distinct(),
        )

    @classmethod
    def search_corpus_annotation_text(
        cls,
        *,
        corpus_id: int,
        user,
        phrase: str,
        document_id: Optional[int] = None,
        limit: int = 10,
        exclude_label_texts: Optional[Iterable[str]] = None,
        context: Optional[Any] = None,
    ) -> QuerySet:
        """Find corpus annotations whose text contains ``phrase``, tightest first.

        The permission-filtered, *citeable* counterpart to
        ``search_exact_text_as_sources``: that tool re-derives matches from the
        PAWLS/text layer and returns synthetic negative ids, which cannot be
        cited or linked to anything. This returns the real ``Annotation`` rows
        that contain the phrase, so the caller gets a durable anchor id it can
        attribute with (see the deep-research ``find_citable_passages`` tool,
        issue #2201).

        Visibility is delegated wholesale to ``get_corpus_annotations`` —
        corpus READ plus per-document visibility plus the analysis/extract
        privacy gate — so this adds no permission logic of its own.

        Ordering is by ``raw_text`` length ascending: the shortest annotation
        containing the phrase is the most pinpoint anchor, which is exactly what
        the citation-discipline rules (#2180) ask for. ``id`` breaks ties so
        results are deterministic. The length is ``annotate``d rather than passed
        straight to ``order_by`` because ``get_corpus_annotations`` returns a
        ``.distinct()`` queryset, and Postgres rejects a SELECT DISTINCT ordered
        by an expression that is not in the select list.

        ``limit`` is a positive row count with a floor of 1 — ``limit=0`` still
        yields one row rather than none. Pass an empty ``phrase`` (or just don't
        call this) when the answer you want is "no rows".

        ``exclude_label_texts`` drops annotations carrying any of the given
        ``annotation_label.text`` values, matched case-insensitively. Callers use
        it to keep whole categories of anchor out of the results — the
        deep-research tool passes the section-header labels so a bare
        ``ITEM 1A. RISK FACTORS`` is never offered as a citable passage (#2180).
        Note this is keyed on the LABEL, never on ``Annotation.structural``:
        the parsing pipeline marks its entire layout layer structural, so
        filtering on that flag would drop nearly every body passage while
        keeping the bookmark-derived headers, which are ``structural=False``.

        ``raw_text__icontains`` is index-backed: annotations migration 0074 adds
        a pg_trgm GIN index on ``Annotation.raw_text`` precisely so ILIKE
        substring lookups don't degrade to a sequential scan.
        """
        from django.db.models.functions import Length

        from opencontractserver.annotations.models import Annotation

        phrase = (phrase or "").strip()
        if not phrase:
            return Annotation.objects.none()

        qs = cls.get_corpus_annotations(corpus_id, user, context=context).filter(
            raw_text__icontains=phrase
        )
        if document_id is not None:
            qs = qs.filter(document_id=document_id)
        if exclude_label_texts:
            excluded = Q()
            for label_text in exclude_label_texts:
                excluded |= Q(annotation_label__text__iexact=label_text)
            # ``annotation_label`` is nullable, and a negated lookup across a
            # nullable FK drops the NULL-label rows too (SQL three-valued
            # logic: ``NOT (NULL = 'x')`` is NULL, not TRUE). Re-admit them
            # explicitly so excluding a header label never silently costs us
            # every unlabelled passage. One combined Q rather than a chain of
            # ``exclude()`` calls, so this stays a single condition however
            # many labels the caller passes.
            qs = qs.filter(~excluded | Q(annotation_label__isnull=True))
        return (
            qs.select_related("document", "annotation_label")
            .annotate(_anchor_chars=Length("raw_text"))
            .order_by("_anchor_chars", "id")[: max(1, int(limit))]
        )

    @classmethod
    def resolve_owned_document(cls, *, document_id: int, user: Any) -> Any:
        """Permission-gated fallback fetch of a non-structural annotation's document.

        ``AnnotationType.resolve_document`` returns ``self.document`` directly
        when the FK was ``select_related`` (the normal, hot path — see the
        caller). This method backs the defensive fallback for callers that
        fetched the ``Annotation`` without ``select_related("document")``:
        annotation READ visibility is inherited from the document, so any
        annotation that reached the resolver already implies document READ,
        but the permission-scoped fetch here re-derives that instead of
        trusting an un-checked FK traversal.

        Args:
            document_id: ``Annotation.document_id`` of the owning document.
            user: The requesting user; the result is intersected with
                ``Document.objects.visible_to_user``.

        Returns:
            The ``Document``, or ``None`` if it is not visible to ``user``.
        """
        from opencontractserver.documents.models import Document

        return (
            cls.filter_visible_qs(Document.objects.filter(pk=document_id), user)
            .select_related("creator")
            .first()
        )

    @classmethod
    def resolve_structural_document_fallback(
        cls,
        *,
        structural_set_id: int,
        corpus_id: Optional[int],
        user: Any,
    ) -> Any:
        """Best-effort structural-document resolution when no context-scoped
        prefetch (``structural_document_prefetch``) was applied — or its
        user-scoped prefetch resolved to nothing.

        Scopes to the annotation's own corpus, gates by visibility, and
        orders deterministically so this never returns an arbitrary or
        private member of the content-hash-shared ``StructuralAnnotationSet``.
        Query-context scoping (which corpus/document is being viewed) only
        happens via the prefetch in ``structural_document_prefetch``; without
        a corpus to scope against here, any visible member of the shared set
        is an equally "valid" but potentially unrelated-corpus (or the
        standalone import source) pick, so this returns ``None`` rather than
        guessing.

        Args:
            structural_set_id: ``Annotation.structural_set_id`` of the shared set.
            corpus_id: ``Annotation.corpus_id``. Required — without it there is
                no corpus to scope the shared set's documents against.
            user: The requesting user; the result is intersected with
                ``Document.objects.visible_to_user``.

        Returns:
            The corpus-scoped, visible ``Document``, or ``None`` when there is
            no corpus context or no visible member of the set has a path in it.
        """
        from opencontractserver.documents.models import Document

        if not corpus_id:
            return None

        documents = Document.objects.filter(
            structural_annotation_set_id=structural_set_id,
            path_records__corpus_id=corpus_id,
            path_records__is_current=True,
            path_records__is_deleted=False,
        )
        return cls.filter_visible_qs(documents, user).order_by("slug").first()
