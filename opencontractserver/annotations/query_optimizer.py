"""
Simplified Query Optimizers for OpenContracts
Direct database queries with smart prefetching and permission filtering.
No caching layer - just optimized queries.
"""

from typing import TYPE_CHECKING, Any, Optional, cast

if TYPE_CHECKING:
    from opencontractserver.analyzer.models import Analysis
    from opencontractserver.extracts.models import Extract

from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Value,
    When,
)


class AnnotationQueryOptimizer:
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
        ``user_has_permission_for_obj`` round-trips and the
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

        # Superusers have all permissions
        if user.is_superuser:
            return _store((True, True, True, True, True))

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
        # (instead of the deprecated ``user_has_permission_for_obj``) so creator
        # status is honored. This is the Phase A bug-fix posture: the legacy
        # function ignored creator, producing False-denials when the same
        # user owned both the annotation and its parent document/corpus.
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
        use_cache: bool = True,  # Kept for backward compatibility, ignored
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

        # Apply privacy filtering for created_by_* fields
        if not user.is_superuser:
            # Get analyses user can access
            from opencontractserver.analyzer.models import (
                Analysis,
                AnalysisUserObjectPermission,
            )
            from opencontractserver.extracts.models import Extract

            # Anonymous users can only see public analyses/extracts
            if user.is_anonymous:
                visible_analyses = Analysis.objects.filter(Q(is_public=True))
                visible_extracts = Extract.objects.none()  # No extracts for anonymous
            else:
                # Base query for visible analyses
                visible_analyses = Analysis.objects.filter(
                    Q(is_public=True) | Q(creator=user)
                )

                # Add analyses with explicit permissions
                analyses_with_permission = AnalysisUserObjectPermission.objects.filter(
                    user=user
                ).values_list("content_object_id", flat=True)

                visible_analyses = visible_analyses | Analysis.objects.filter(
                    id__in=analyses_with_permission
                )

                # Get extracts user can access
                from opencontractserver.extracts.models import (
                    ExtractUserObjectPermission,
                )

                visible_extracts = Extract.objects.filter(Q(creator=user))

                # Add extracts with explicit permissions
                extracts_with_permission = ExtractUserObjectPermission.objects.filter(
                    user=user
                ).values_list("content_object_id", flat=True)

                visible_extracts = visible_extracts | Extract.objects.filter(
                    id__in=extracts_with_permission
                )

            # Filter annotations: exclude private ones unless user has access
            # BUT always include structural annotations (they're always visible)
            qs = qs.exclude(
                # Exclude non-structural analysis-created annotations user can't see
                Q(created_by_analysis__isnull=False)
                & Q(structural=False)  # Only apply privacy to non-structural
                & ~Q(created_by_analysis__in=visible_analyses)
            ).exclude(
                # Exclude non-structural extract-created annotations user can't see
                Q(created_by_extract__isnull=False)
                & Q(structural=False)  # Only apply privacy to non-structural
                & ~Q(created_by_extract__in=visible_extracts)
            )

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
                # Structural annotations are read-only for non-superusers.
                # ``can_update``/``can_delete`` here came from doc+corpus
                # perms; mask them off per-row for structural annotations
                # so the annotation matches ``AnnotationManager.user_can``'s
                # structural-write-deny rule. Superusers were already
                # handled upstream in ``_compute_effective_permissions``
                # (superuser → all True), so this Case fires only for
                # non-superusers and only on structural rows.
                _can_update=Case(
                    When(structural=True, then=Value(False)),
                    default=Value(can_update),
                    output_field=BooleanField(),
                ),
                _can_delete=Case(
                    When(structural=True, then=Value(False)),
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
            **kwargs
        )

    @classmethod
    def get_extract_annotation_summary(
        cls, document_id: int, extract_id: int, user, use_cache: bool = True  # Ignored
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
    def _check_document_permission(cls, user, document_id) -> bool:
        """Check if user has permission to access document.
        DEPRECATED: Use _compute_effective_permissions instead.
        Kept for backwards compatibility.
        """
        can_read, _, _, _, _ = cls._compute_effective_permissions(
            user, document_id, None
        )
        return can_read

    @classmethod
    def _apply_permission_filter(cls, qs, user, corpus_id):
        """Apply permission-based filtering.
        DEPRECATED: Permissions are now checked at document+corpus level.
        This method now just filters by corpus_id.
        """
        # Simply filter by corpus since permissions are already checked
        return qs.filter(corpus_id=corpus_id)

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
        from opencontractserver.analyzer.models import (
            Analysis,
            AnalysisUserObjectPermission,
        )
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import (
            Extract,
            ExtractUserObjectPermission,
        )
        from opencontractserver.types.enums import PermissionTypes

        # Superusers see everything
        if user.is_superuser:
            qs = Annotation.objects.filter(corpus_id=corpus_id)

            # For structural annotations, include those linked via structural_set
            # to documents in this corpus
            visible_doc_ids = Document.objects.filter(
                path_records__corpus_id=corpus_id,
                path_records__is_current=True,
                path_records__is_deleted=False,
            ).values_list("id", flat=True)

            structural_set_ids = Document.objects.filter(
                id__in=visible_doc_ids,
                structural_annotation_set_id__isnull=False,
            ).values_list("structural_annotation_set_id", flat=True)

            # Combine: corpus annotations OR structural annotations from visible docs
            qs = Annotation.objects.filter(
                Q(corpus_id=corpus_id)
                | Q(structural_set_id__in=structural_set_ids, structural=True)
            )

            if structural is not None:
                qs = qs.filter(structural=structural)
            if analysis_isnull is not None:
                qs = qs.filter(analysis__isnull=analysis_isnull)

            return qs.distinct()

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

        # Apply privacy filtering for created_by_* fields (non-superuser, non-anonymous)
        if not user.is_anonymous:
            # Get analyses user can access
            visible_analyses = Analysis.objects.filter(
                Q(is_public=True) | Q(creator=user)
            )
            analyses_with_permission = AnalysisUserObjectPermission.objects.filter(
                user=user
            ).values_list("content_object_id", flat=True)
            visible_analyses = visible_analyses | Analysis.objects.filter(
                id__in=analyses_with_permission
            )

            # Get extracts user can access
            visible_extracts = Extract.objects.filter(Q(creator=user))
            extracts_with_permission = ExtractUserObjectPermission.objects.filter(
                user=user
            ).values_list("content_object_id", flat=True)
            visible_extracts = visible_extracts | Extract.objects.filter(
                id__in=extracts_with_permission
            )

            # Filter: exclude private annotations user can't see
            # BUT always include structural annotations (bypass privacy)
            qs = qs.exclude(
                Q(created_by_analysis__isnull=False)
                & Q(structural=False)
                & ~Q(created_by_analysis__in=visible_analyses)
            ).exclude(
                Q(created_by_extract__isnull=False)
                & Q(structural=False)
                & ~Q(created_by_extract__in=visible_extracts)
            )

        # Apply optional filters
        if structural is not None:
            qs = qs.filter(structural=structural)
        if analysis_isnull is not None:
            qs = qs.filter(analysis__isnull=analysis_isnull)

        return qs.distinct()


class RelationshipQueryOptimizer:
    """
    Optimized relationship queries without caching.

    Permission model:
    - Uses same document+corpus permission model as annotations
    - Document permissions are primary (most restrictive)
    - Corpus permissions are secondary
    - Effective permission = MIN(document_permission, corpus_permission)
    """

    @classmethod
    def get_document_relationships(
        cls,
        document_id: int,
        user,
        corpus_id: Optional[int] = None,
        analysis_id: Optional[int] = None,
        pages: Optional[list[int]] = None,
        structural: Optional[bool] = None,
        extract_id: Optional[int] = None,
        strict_extract_mode: bool = False,
        use_cache: bool = True,  # Ignored
        context=None,
    ) -> QuerySet:
        """
        Get relationships with optimized prefetching.
        Permissions are computed at document+corpus level.

        IMPORTANT: Returns relationships from BOTH:
        1. Direct document relationships (document FK) - corpus-specific relationships
        2. Structural relationships via document's structural_annotation_set (structural_set FK) - shared relationships

        ``context`` allows the request-level caches in
        ``AnnotationQueryOptimizer._compute_effective_permissions`` /
        ``_get_document_for_request`` to be shared with the annotation resolver
        in the same GraphQL operation.
        """
        from opencontractserver.annotations.models import Relationship

        # Use unified permission check from AnnotationQueryOptimizer.
        # Pass context so the result is cached for the rest of the request.
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                user, document_id, corpus_id, context=context
            )
        )

        if not can_read:
            return Relationship.objects.none()

        # Fetch document via the request cache (same instance as the annotation
        # resolver uses, when both run in the same GraphQL request).
        document = AnnotationQueryOptimizer._get_document_for_request(
            document_id, context
        )
        if document is None:
            return Relationship.objects.none()

        # Build base filter for relationships from BOTH sources:
        # 1. Direct document relationships (corpus-specific, user-created)
        # 2. Structural relationships via document's structural_annotation_set (shared)
        doc_filters = Q(document_id=document_id)

        if document.structural_annotation_set_id:
            # Include structural relationships from the shared set
            # These relationships have document_id=NULL but structural_set_id=X
            doc_filters |= Q(
                structural_set_id=document.structural_annotation_set_id,
                structural=True,  # Safety check - structural_set relationships must be structural
            )

        # Build query with combined document filters
        qs = Relationship.objects.filter(doc_filters)

        # Apply privacy filtering for created_by_* fields (same pattern as Annotations)
        if not user.is_superuser:
            # Get analyses user can access
            from opencontractserver.analyzer.models import (
                Analysis,
                AnalysisUserObjectPermission,
            )
            from opencontractserver.extracts.models import Extract

            # Anonymous users can only see public analyses/extracts
            if user.is_anonymous:
                visible_analyses = Analysis.objects.filter(Q(is_public=True))
                visible_extracts = Extract.objects.none()  # No extracts for anonymous
            else:
                # Base query for visible analyses
                visible_analyses = Analysis.objects.filter(
                    Q(is_public=True) | Q(creator=user)
                )

                # Add analyses with explicit permissions
                analyses_with_permission = AnalysisUserObjectPermission.objects.filter(
                    user=user
                ).values_list("content_object_id", flat=True)

                visible_analyses = visible_analyses | Analysis.objects.filter(
                    id__in=analyses_with_permission
                )

                # Get extracts user can access
                from opencontractserver.extracts.models import (
                    ExtractUserObjectPermission,
                )

                visible_extracts = Extract.objects.filter(Q(creator=user))

                # Add extracts with explicit permissions
                extracts_with_permission = ExtractUserObjectPermission.objects.filter(
                    user=user
                ).values_list("content_object_id", flat=True)

                visible_extracts = visible_extracts | Extract.objects.filter(
                    id__in=extracts_with_permission
                )

            # Filter relationships: exclude private ones unless user has access
            # BUT always include structural relationships (they're always visible)
            qs = qs.exclude(
                # Exclude non-structural analysis-created relationships user can't see
                Q(created_by_analysis__isnull=False)
                & Q(structural=False)  # Only apply privacy to non-structural
                & ~Q(created_by_analysis__in=visible_analyses)
            ).exclude(
                # Exclude non-structural extract-created relationships user can't see
                Q(created_by_extract__isnull=False)
                & Q(structural=False)  # Only apply privacy to non-structural
                & ~Q(created_by_extract__in=visible_extracts)
            )

        if corpus_id:
            # Filter by corpus (permissions already checked)
            # IMPORTANT: Structural_set relationships have corpus_id=NULL (they're shared across corpuses)
            # So we need to keep BOTH:
            # 1. Corpus-specific relationships where corpus_id matches
            # 2. Structural_set relationships (which have corpus_id=NULL but structural_set_id set)
            corpus_filter = Q(corpus_id=corpus_id)

            if document.structural_annotation_set_id:
                # Also keep structural relationships from this document's set
                # (already filtered in base query, but corpus_id=NULL so we must explicitly allow them)
                corpus_filter |= Q(
                    structural_set_id=document.structural_annotation_set_id,
                    structural=True,
                )

            qs = qs.filter(corpus_filter)
        else:
            # No corpus = structural only (always readable if doc is readable)
            qs = qs.filter(structural=True)

        if analysis_id is not None:
            if analysis_id == 0:  # Special case for user relationships
                qs = qs.filter(analysis__isnull=True)
            else:
                # Check analysis visibility as additional restriction
                from opencontractserver.analyzer.models import Analysis
                from opencontractserver.types.enums import PermissionTypes

                try:
                    analysis = Analysis.objects.get(id=analysis_id)
                    # User can see relationships if: analysis is public, user is creator,
                    # OR has explicit READ permission
                    has_permission = (
                        analysis.is_public
                        or analysis.creator_id == user.id
                        or analysis.user_can(
                            user, PermissionTypes.READ, request=context
                        )
                    )
                    if not has_permission:
                        return Relationship.objects.none()
                except Analysis.DoesNotExist:
                    return Relationship.objects.none()
                qs = qs.filter(analysis_id=analysis_id)
        else:
            # When analysis_id is not provided (None), exclude analysis relationships
            # We only want user/manual relationships in this case
            qs = qs.filter(analysis__isnull=True)

        if structural is not None:
            qs = qs.filter(structural=structural)

        if pages:
            # Filter relationships where source or target annotations are on specified pages
            qs = qs.filter(
                Q(source_annotations__page__in=pages)
                | Q(target_annotations__page__in=pages)
            ).distinct()

        if extract_id:
            # Filter to relationships connected to annotations used in extract
            from opencontractserver.extracts.models import Datacell

            datacell_annotation_ids = Datacell.objects.filter(
                extract_id=extract_id, document_id=document_id
            ).values_list("sources__id", flat=True)

            if strict_extract_mode:
                # Both source and target must be in extract
                qs = qs.filter(
                    source_annotations__id__in=datacell_annotation_ids,
                    target_annotations__id__in=datacell_annotation_ids,
                )
            else:
                # Either source or target in extract
                qs = qs.filter(
                    Q(source_annotations__id__in=datacell_annotation_ids)
                    | Q(target_annotations__id__in=datacell_annotation_ids)
                )

        # Optimize with prefetches and annotate with computed permissions
        qs = (
            qs.select_related("relationship_label", "creator")
            .prefetch_related(
                "source_annotations__annotation_label",
                "target_annotations__annotation_label",
            )
            .annotate(
                # Store computed permissions for backwards compatibility
                _can_read=Value(can_read),
                _can_create=Value(can_create),
                _can_update=Value(can_update),
                _can_delete=Value(can_delete),
                _can_comment=Value(can_comment),
            )
            .distinct()
        )

        return qs

    @classmethod
    def get_relationship_summary(cls, document_id: int, corpus_id: int, user) -> dict:
        """
        Get relationship counts by type.
        """
        from opencontractserver.annotations.models import Relationship

        # Use unified permission check
        can_read, _, _, _, _ = AnnotationQueryOptimizer._compute_effective_permissions(
            user, document_id, corpus_id
        )

        if not can_read:
            return {"total": 0, "by_type": {}}

        summary = (
            Relationship.objects.filter(document_id=document_id, corpus_id=corpus_id)
            .values("relationship_label__text")
            .annotate(count=Count("id"))
        )

        result = {
            "total": sum(item["count"] for item in summary),
            "by_type": {
                item["relationship_label__text"]: item["count"]
                for item in summary
                if item["relationship_label__text"]
            },
        }

        return result

    @classmethod
    def _apply_permission_filter(cls, qs, user, corpus_id):
        """Apply permission-based filtering.
        DEPRECATED: Permissions are now checked at document+corpus level.
        This method now just filters by corpus_id.
        """
        # Simply filter by corpus since permissions are already checked
        return qs.filter(corpus_id=corpus_id)


class AnalysisQueryOptimizer:
    """
    Optimized queries for Analysis model with hybrid permission model.

    Permission model:
    - Analysis has its own permissions (can be shared independently)
    - BUT visibility requires corpus permissions too
    - Annotations within are filtered by document permissions
    """

    @classmethod
    def check_analysis_permission(
        cls, user, analysis_id: int, context: Optional[Any] = None
    ) -> tuple[bool, Optional["Analysis"]]:
        """
        Check if user can access an analysis.
        Returns (has_permission, analysis_object)

        Permission model:
        1. User must have permission on the analysis object itself
        2. AND user must have permission on the corpus

        Args:
            user: The requesting user
            analysis_id: The analysis ID to check
            context: Optional GraphQL context (``info.context``) threaded into
                ``user_can`` so Tier-2 request-scoped permission caching applies.
        """
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.types.enums import PermissionTypes

        # Superuser can see everything
        if user.is_superuser:
            try:
                analysis = Analysis.objects.get(id=analysis_id)
                return True, analysis
            except Analysis.DoesNotExist:
                return False, None

        try:
            analysis = Analysis.objects.get(id=analysis_id)

            # Check analysis-level permission
            has_analysis_perm = (
                analysis.is_public
                or analysis.creator_id == user.id
                or analysis.user_can(user, PermissionTypes.READ, request=context)
            )

            if not has_analysis_perm:
                return False, None

            # Check corpus permission if analysis has a corpus
            if analysis.analyzed_corpus:
                has_corpus_perm = (
                    analysis.analyzed_corpus.is_public
                    or analysis.analyzed_corpus.creator_id == user.id
                    or analysis.analyzed_corpus.user_can(
                        user, PermissionTypes.READ, request=context
                    )
                )
                if not has_corpus_perm:
                    return False, None

            return True, analysis

        except Analysis.DoesNotExist:
            return False, None

    @classmethod
    def get_visible_analyses(
        cls,
        user,
        corpus_id: Optional[int] = None,
        context: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get analyses visible to user based on:
        1. User has permission on analysis object
        2. User has READ permission on corpus

        Args:
            user: The requesting user
            corpus_id: Optional corpus ID to scope the query
            context: Optional GraphQL context (``info.context``) threaded into
                ``user_can`` so Tier-2 request-scoped permission caching applies.
        """
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.corpuses.models import (
            Corpus,
            CorpusUserObjectPermission,
        )
        from opencontractserver.types.enums import PermissionTypes

        if user.is_superuser:
            qs = Analysis.objects.all()
        elif user.is_anonymous:
            # Anonymous users can only see public analyses in public corpuses
            qs = Analysis.objects.filter(
                Q(is_public=True)
                & (Q(analyzed_corpus__isnull=True) | Q(analyzed_corpus__is_public=True))
            )
        else:
            # Import permission model
            from opencontractserver.analyzer.models import AnalysisUserObjectPermission

            # Get analyses where:
            # 1. User has permission on the analysis AND
            # 2. User has permission on the corpus
            qs = Analysis.objects.filter(
                # User must have analysis permission
                Q(is_public=True)
                | Q(creator=user)
                | Exists(
                    AnalysisUserObjectPermission.objects.filter(
                        user=user, content_object_id=OuterRef("id")
                    )
                )
            ).filter(
                # AND user must have corpus permission
                Q(analyzed_corpus__isnull=True)  # No corpus needed
                | Q(analyzed_corpus__creator=user)
                | Q(analyzed_corpus__is_public=True)
                | Exists(
                    CorpusUserObjectPermission.objects.filter(
                        user=user,
                        content_object_id=OuterRef("analyzed_corpus_id"),
                        permission__codename__contains="read",
                    )
                )
            )

        # Filter by corpus if specified
        if corpus_id:
            # Check corpus permission
            try:
                corpus = Corpus.objects.get(id=corpus_id)
                # Anonymous users can only access public corpuses
                if user.is_anonymous:
                    if not corpus.is_public:
                        return Analysis.objects.none()
                elif not user.is_superuser and not corpus.user_can(
                    user, PermissionTypes.READ, request=context
                ):
                    return Analysis.objects.none()
            except Corpus.DoesNotExist:
                return Analysis.objects.none()

            qs = qs.filter(analyzed_corpus_id=corpus_id)

        # Optimize query
        qs = (
            qs.select_related("analyzer", "analyzed_corpus", "creator")
            .prefetch_related("analyzed_documents")
            .distinct()
        )

        return qs

    @classmethod
    def get_analysis_annotations(
        cls, analysis: "Analysis", user, document_id: Optional[int] = None
    ) -> QuerySet:
        """
        Get annotations from an analysis, filtered by document permissions.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import Document
        from opencontractserver.types.enums import PermissionTypes

        # Start with all annotations in the analysis
        qs = Annotation.objects.filter(analysis=analysis)

        if document_id:
            # Filter to specific document if requested
            qs = qs.filter(document_id=document_id)

            # Check document permission
            if not user.is_superuser:
                try:
                    doc = Document.objects.get(id=document_id)
                    if not doc.user_can(user, PermissionTypes.READ):
                        return Annotation.objects.none()
                except Document.DoesNotExist:
                    return Annotation.objects.none()
        else:
            # Filter to only documents user can read
            if not user.is_superuser:
                readable_doc_ids = list(
                    Document.objects.visible_to_user(user)
                    .filter(id__in=analysis.analyzed_documents.values("id"))
                    .values_list("id", flat=True)
                )

                if not readable_doc_ids:
                    return Annotation.objects.none()

                qs = qs.filter(document_id__in=readable_doc_ids)

        # Optimize query
        qs = (
            qs.select_related("annotation_label", "document", "corpus", "creator")
            .annotate(feedback_count=Count("user_feedback"))
            .distinct()
        )

        return qs


class ExtractQueryOptimizer:
    """
    Optimized queries for Extract model with hybrid permission model.

    Permission model:
    - Extract has its own permissions (can be shared independently)
    - BUT visibility requires corpus permissions too
    - Datacells within are filtered by document permissions
    """

    @classmethod
    def check_extract_permission(
        cls, user, extract_id: int, context: Optional[Any] = None
    ) -> tuple[bool, Optional["Extract"]]:
        """
        Check if user can access an extract.
        Returns (has_permission, extract_object)

        Args:
            user: The requesting user
            extract_id: The extract ID to check
            context: Optional GraphQL context (``info.context``) threaded into
                ``user_can`` so Tier-2 request-scoped permission caching applies.
        """
        from opencontractserver.extracts.models import Extract
        from opencontractserver.types.enums import PermissionTypes

        # Superuser can see everything
        if user.is_superuser:
            try:
                extract = Extract.objects.get(id=extract_id)
                return True, extract
            except Extract.DoesNotExist:
                return False, None

        try:
            extract = Extract.objects.get(id=extract_id)

            # Check extract-level permission
            has_extract_perm = extract.creator_id == user.id or extract.user_can(
                user, PermissionTypes.READ, request=context
            )

            if not has_extract_perm:
                return False, None

            # Check corpus permission if extract has a corpus
            if extract.corpus:
                has_corpus_perm = (
                    extract.corpus.is_public
                    or extract.corpus.creator_id == user.id
                    or extract.corpus.user_can(
                        user, PermissionTypes.READ, request=context
                    )
                )
                if not has_corpus_perm:
                    return False, None

            return True, extract

        except Extract.DoesNotExist:
            return False, None

    @classmethod
    def get_visible_extracts(
        cls,
        user,
        corpus_id: Optional[int] = None,
        context: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get extracts visible to user based on:
        1. User has permission on extract object
        2. User has READ permission on corpus

        Args:
            user: The requesting user
            corpus_id: Optional corpus ID to scope the query
            context: Optional GraphQL context (``info.context``) threaded into
                ``user_can`` so Tier-2 request-scoped permission caching applies.
        """
        from opencontractserver.corpuses.models import (
            Corpus,
            CorpusUserObjectPermission,
        )
        from opencontractserver.extracts.models import Extract
        from opencontractserver.types.enums import PermissionTypes

        if user.is_superuser:
            qs = Extract.objects.all()
        elif user.is_anonymous:
            # Anonymous users can only see public extracts in public corpuses
            qs = Extract.objects.filter(
                Q(is_public=True) & (Q(corpus__isnull=True) | Q(corpus__is_public=True))
            )
        else:
            # Import permission model
            from opencontractserver.extracts.models import ExtractUserObjectPermission

            # Get extracts where:
            # 1. User has permission on the extract (via creator, is_public, or guardian) AND
            # 2. User has permission on the corpus (required for both anonymous and authenticated)
            # Note: is_public=True grants extract-level access, but corpus access is still checked below
            qs = Extract.objects.filter(
                # User must have extract permission (one of: creator, public, or guardian)
                Q(creator=user)
                | Q(is_public=True)
                | Exists(
                    ExtractUserObjectPermission.objects.filter(
                        user=user, content_object_id=OuterRef("id")
                    )
                )
            ).filter(
                # AND user must have corpus permission
                Q(corpus__isnull=True)  # No corpus needed
                | Q(corpus__creator=user)
                | Q(corpus__is_public=True)
                | Exists(
                    CorpusUserObjectPermission.objects.filter(
                        user=user,
                        content_object_id=OuterRef("corpus_id"),
                        permission__codename__contains="read",
                    )
                )
            )

        # Filter by corpus if specified
        if corpus_id:
            # Check corpus permission
            try:
                corpus = Corpus.objects.get(id=corpus_id)
                # Anonymous users can only access public corpuses
                if user.is_anonymous:
                    if not corpus.is_public:
                        return Extract.objects.none()
                elif not user.is_superuser and not corpus.user_can(
                    user, PermissionTypes.READ, request=context
                ):
                    return Extract.objects.none()
            except Corpus.DoesNotExist:
                return Extract.objects.none()

            qs = qs.filter(corpus_id=corpus_id)

        # Optimize query
        qs = (
            qs.select_related("fieldset", "corpus", "creator", "corpus_action")
            .prefetch_related("documents", "fieldset__columns")
            .distinct()
        )

        return qs

    @classmethod
    def get_extract_datacells(
        cls, extract: "Extract", user, document_id: Optional[int] = None
    ) -> QuerySet:
        """
        Get datacells from an extract, filtered by document permissions.
        """
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import Datacell
        from opencontractserver.types.enums import PermissionTypes

        # Start with all datacells in the extract
        qs = Datacell.objects.filter(extract=extract)

        if document_id:
            # Filter to specific document if requested
            qs = qs.filter(document_id=document_id)

            # Check document permission
            if not user.is_superuser:
                try:
                    doc = Document.objects.get(id=document_id)
                    if not doc.user_can(user, PermissionTypes.READ):
                        return Datacell.objects.none()
                except Document.DoesNotExist:
                    return Datacell.objects.none()
        else:
            # Filter to only documents user can read
            if not user.is_superuser:
                readable_doc_ids = list(
                    Document.objects.visible_to_user(user)
                    .filter(id__in=extract.documents.values("id"))
                    .values_list("id", flat=True)
                )

                if not readable_doc_ids:
                    return Datacell.objects.none()

                qs = qs.filter(document_id__in=readable_doc_ids)

        # Optimize query
        qs = (
            qs.select_related(
                "column", "column__fieldset", "document", "approved_by", "rejected_by"
            )
            .prefetch_related("sources")
            .distinct()
        )

        return qs
