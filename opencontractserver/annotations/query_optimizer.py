"""
Simplified Query Optimizers for OpenContracts
Direct database queries with smart prefetching and permission filtering.
No caching layer - just optimized queries.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from opencontractserver.analyzer.models import Analysis
    from opencontractserver.extracts.models import Extract

from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Value


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
        cls, user, document_id: int, corpus_id: Optional[int] = None
    ) -> tuple[bool, bool, bool, bool, bool]:
        """
        Compute effective permissions based on document and corpus.

        Special handling for COMMENT permission:
        - If corpus.allow_comments is True, any readable annotation is commentable
        - Otherwise, standard MIN(doc_comment, corpus_comment) logic applies

        Returns: (can_read, can_create, can_update, can_delete, can_comment)
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Superusers have all permissions
        if user.is_superuser:
            return True, True, True, True, True

        # Anonymous users only have read access to public documents/corpuses
        if user.is_anonymous:
            try:
                document = Document.objects.get(id=document_id)
                doc_read = document.is_public
            except Document.DoesNotExist:
                return False, False, False, False, False

            if not doc_read:
                return False, False, False, False, False

            if corpus_id:
                try:
                    corpus = Corpus.objects.get(id=corpus_id)
                    corpus_read = corpus.is_public
                except Corpus.DoesNotExist:
                    return False, False, False, False, False

                if not corpus_read:
                    return False, False, False, False, False

            # Anonymous users only get read permission
            return True, False, False, False, False

        # First check document permissions (primary)
        try:
            document = Document.objects.get(id=document_id)
            doc_read = user_has_permission_for_obj(user, document, PermissionTypes.READ)
            doc_create = user_has_permission_for_obj(
                user, document, PermissionTypes.CREATE
            )
            doc_update = user_has_permission_for_obj(
                user, document, PermissionTypes.UPDATE
            )
            doc_delete = user_has_permission_for_obj(
                user, document, PermissionTypes.DELETE
            )
            doc_comment = user_has_permission_for_obj(
                user, document, PermissionTypes.COMMENT
            )
        except Document.DoesNotExist:
            return False, False, False, False, False

        # If no document read permission, no access at all
        if not doc_read:
            return False, False, False, False, False

        # If no corpus, use document permissions only
        if not corpus_id:
            return doc_read, doc_create, doc_update, doc_delete, doc_comment

        # Check corpus permissions and apply most restrictive
        try:
            corpus = Corpus.objects.get(id=corpus_id)
            corpus_read = user_has_permission_for_obj(
                user, corpus, PermissionTypes.READ
            )
            corpus_create = user_has_permission_for_obj(
                user, corpus, PermissionTypes.CREATE
            )
            corpus_update = user_has_permission_for_obj(
                user, corpus, PermissionTypes.UPDATE
            )
            corpus_delete = user_has_permission_for_obj(
                user, corpus, PermissionTypes.DELETE
            )
            corpus_comment = user_has_permission_for_obj(
                user, corpus, PermissionTypes.COMMENT
            )

            # Compute final read permission
            final_read = doc_read and corpus_read

            # BACON MODE: If corpus allows comments, readable = commentable
            if corpus.allow_comments:
                final_comment = final_read  # Can see it? Can comment on it.
            else:
                # Standard restrictive model
                final_comment = doc_comment and corpus_comment

            # Return computed permissions
            return (
                final_read,
                doc_create and corpus_create,
                doc_update and corpus_update,
                doc_delete and corpus_delete,
                final_comment,
            )
        except Corpus.DoesNotExist:
            # Corpus doesn't exist, use document permissions
            return doc_read, doc_create, doc_update, doc_delete, doc_comment

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
    ) -> QuerySet:
        """
        Get annotations with permission filtering and optimized queries.
        Permissions are computed at document+corpus level and applied to all annotations.

        IMPORTANT: Returns annotations from BOTH:
        1. Direct document annotations (document FK) - corpus-specific annotations
        2. Structural annotations via document's structural_annotation_set (structural_set FK) - shared annotations
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import Document

        # Compute effective permissions once
        can_read, can_create, can_update, can_delete, can_comment = (
            cls._compute_effective_permissions(user, document_id, corpus_id)
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

        # Fetch document to check for structural_annotation_set
        # Use select_related for efficiency to avoid N+1 queries
        try:
            document = Document.objects.select_related("structural_annotation_set").get(
                pk=document_id
            )
        except Document.DoesNotExist:
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
            from opencontractserver.utils.permissioning import (
                user_has_permission_for_obj,
            )

            try:
                analysis = Analysis.objects.get(id=analysis_id)
                # Check analysis visibility as additional restriction
                # User can see annotations if: analysis is public, user is creator, OR has explicit READ permission
                has_permission = (
                    analysis.is_public
                    or analysis.creator_id == user.id
                    or user_has_permission_for_obj(
                        user,
                        analysis,
                        PermissionTypes.READ,
                        include_group_permissions=True,
                    )
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

        # Optimize query with prefetches and annotate feedback count
        # Also annotate with computed permissions for backwards compatibility
        qs = (
            qs.select_related("annotation_label", "creator", "analysis")
            .annotate(
                feedback_count=Count("user_feedback"),
                # Store computed permissions for GraphQL myPermissions field
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
        except DocumentPath.MultipleObjectsReturned:
            # Shouldn't happen with constraints, but handle safely
            document_path = path_query.first()

        # Use existing method with resolved document_id
        return cls.get_document_annotations(
            document_id=document_path.document_id,
            user=user,
            corpus_id=corpus_id,
            check_current_version=False,  # Already checked via path
            **kwargs
        )

    # TODO - in-use?
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
    ) -> QuerySet:
        """
        Get relationships with optimized prefetching.
        Permissions are computed at document+corpus level.

        IMPORTANT: Returns relationships from BOTH:
        1. Direct document relationships (document FK) - corpus-specific relationships
        2. Structural relationships via document's structural_annotation_set (structural_set FK) - shared relationships
        """
        from opencontractserver.annotations.models import Relationship
        from opencontractserver.documents.models import Document

        # Use unified permission check from AnnotationQueryOptimizer
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                user, document_id, corpus_id
            )
        )

        if not can_read:
            return Relationship.objects.none()

        # Fetch document to check for structural_annotation_set
        # Use select_related for efficiency
        try:
            document = Document.objects.select_related("structural_annotation_set").get(
                pk=document_id
            )
        except Document.DoesNotExist:
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
                from opencontractserver.utils.permissioning import (
                    user_has_permission_for_obj,
                )

                try:
                    analysis = Analysis.objects.get(id=analysis_id)
                    # User can see relationships if: analysis is public, user is creator,
                    # OR has explicit READ permission
                    has_permission = (
                        analysis.is_public
                        or analysis.creator_id == user.id
                        or user_has_permission_for_obj(
                            user,
                            analysis,
                            PermissionTypes.READ,
                            include_group_permissions=True,
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
        cls, user, analysis_id: int
    ) -> tuple[bool, Optional["Analysis"]]:
        """
        Check if user can access an analysis.
        Returns (has_permission, analysis_object)

        Permission model:
        1. User must have permission on the analysis object itself
        2. AND user must have permission on the corpus
        """
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

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
                or user_has_permission_for_obj(
                    user, analysis, PermissionTypes.READ, include_group_permissions=True
                )
            )

            if not has_analysis_perm:
                return False, None

            # Check corpus permission if analysis has a corpus
            if analysis.analyzed_corpus:
                has_corpus_perm = (
                    analysis.analyzed_corpus.is_public
                    or analysis.analyzed_corpus.creator_id == user.id
                    or user_has_permission_for_obj(
                        user,
                        analysis.analyzed_corpus,
                        PermissionTypes.READ,
                        include_group_permissions=True,
                    )
                )
                if not has_corpus_perm:
                    return False, None

            return True, analysis

        except Analysis.DoesNotExist:
            return False, None

    @classmethod
    def get_visible_analyses(cls, user, corpus_id: Optional[int] = None) -> QuerySet:
        """
        Get analyses visible to user based on:
        1. User has permission on analysis object
        2. User has READ permission on corpus
        """
        from opencontractserver.analyzer.models import Analysis
        from opencontractserver.corpuses.models import (
            Corpus,
            CorpusUserObjectPermission,
        )
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

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
                elif not user.is_superuser and not user_has_permission_for_obj(
                    user, corpus, PermissionTypes.READ, include_group_permissions=True
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
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Start with all annotations in the analysis
        qs = Annotation.objects.filter(analysis=analysis)

        if document_id:
            # Filter to specific document if requested
            qs = qs.filter(document_id=document_id)

            # Check document permission
            if not user.is_superuser:
                try:
                    doc = Document.objects.get(id=document_id)
                    if not user_has_permission_for_obj(
                        user, doc, PermissionTypes.READ, include_group_permissions=True
                    ):
                        return Annotation.objects.none()
                except Document.DoesNotExist:
                    return Annotation.objects.none()
        else:
            # Filter to only documents user can read
            if not user.is_superuser:
                # Get IDs of documents user can read
                readable_doc_ids = []
                for doc in analysis.analyzed_documents.all():
                    if user_has_permission_for_obj(
                        user, doc, PermissionTypes.READ, include_group_permissions=True
                    ):
                        readable_doc_ids.append(doc.id)

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
        cls, user, extract_id: int
    ) -> tuple[bool, Optional["Extract"]]:
        """
        Check if user can access an extract.
        Returns (has_permission, extract_object)
        """
        from opencontractserver.extracts.models import Extract
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

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
            has_extract_perm = (
                extract.creator_id == user.id
                or user_has_permission_for_obj(
                    user, extract, PermissionTypes.READ, include_group_permissions=True
                )
            )

            if not has_extract_perm:
                return False, None

            # Check corpus permission if extract has a corpus
            if extract.corpus:
                has_corpus_perm = (
                    extract.corpus.is_public
                    or extract.corpus.creator_id == user.id
                    or user_has_permission_for_obj(
                        user,
                        extract.corpus,
                        PermissionTypes.READ,
                        include_group_permissions=True,
                    )
                )
                if not has_corpus_perm:
                    return False, None

            return True, extract

        except Extract.DoesNotExist:
            return False, None

    @classmethod
    def get_visible_extracts(cls, user, corpus_id: Optional[int] = None) -> QuerySet:
        """
        Get extracts visible to user based on:
        1. User has permission on extract object
        2. User has READ permission on corpus
        """
        from opencontractserver.corpuses.models import (
            Corpus,
            CorpusUserObjectPermission,
        )
        from opencontractserver.extracts.models import Extract
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        if user.is_superuser:
            qs = Extract.objects.all()
        elif user.is_anonymous:
            # Anonymous users can only see public extracts in public corpuses
            qs = Extract.objects.filter(
                Q(corpus__isnull=True) | Q(corpus__is_public=True)
            )
        else:
            # Import permission model
            from opencontractserver.extracts.models import ExtractUserObjectPermission

            # Get extracts where:
            # 1. User has permission on the extract AND
            # 2. User has permission on the corpus
            qs = Extract.objects.filter(
                # User must have extract permission
                Q(creator=user)
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
                elif not user.is_superuser and not user_has_permission_for_obj(
                    user, corpus, PermissionTypes.READ, include_group_permissions=True
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
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Start with all datacells in the extract
        qs = Datacell.objects.filter(extract=extract)

        if document_id:
            # Filter to specific document if requested
            qs = qs.filter(document_id=document_id)

            # Check document permission
            if not user.is_superuser:
                try:
                    doc = Document.objects.get(id=document_id)
                    if not user_has_permission_for_obj(
                        user, doc, PermissionTypes.READ, include_group_permissions=True
                    ):
                        return Datacell.objects.none()
                except Document.DoesNotExist:
                    return Datacell.objects.none()
        else:
            # Filter to only documents user can read
            if not user.is_superuser:
                # Get IDs of documents user can read
                readable_doc_ids = []
                for doc in extract.documents.all():
                    if user_has_permission_for_obj(
                        user, doc, PermissionTypes.READ, include_group_permissions=True
                    ):
                        readable_doc_ids.append(doc.id)

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
