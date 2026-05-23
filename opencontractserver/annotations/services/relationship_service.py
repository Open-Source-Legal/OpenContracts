"""Relationship read-service — permission-filtered relationship queries.

Relocated verbatim from the former ``annotations/query_optimizer.py``
``RelationshipQueryOptimizer`` monolith as Phase 3 of the service-layer
centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.

Behaviour is preserved exactly — this is a relocation, not a rewrite.
"""

from typing import Optional

from django.db.models import Count, Q, QuerySet, Value

from opencontractserver.annotations.services.annotation_service import (
    AnnotationService,
)
from opencontractserver.shared.services import BaseService


class RelationshipService(BaseService):
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
        context=None,
    ) -> QuerySet:
        """
        Get relationships with optimized prefetching.
        Permissions are computed at document+corpus level.

        IMPORTANT: Returns relationships from BOTH:
        1. Direct document relationships (document FK) - corpus-specific relationships
        2. Structural relationships via document's structural_annotation_set (structural_set FK) - shared relationships

        ``context`` allows the request-level caches in
        ``AnnotationService._compute_effective_permissions`` /
        ``_get_document_for_request`` to be shared with the annotation resolver
        in the same GraphQL operation.
        """
        from opencontractserver.annotations.models import Relationship

        # Use unified permission check from AnnotationService.
        # Pass context so the result is cached for the rest of the request.
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationService._compute_effective_permissions(
                user, document_id, corpus_id, context=context
            )
        )

        if not can_read:
            return Relationship.objects.none()

        # Fetch document via the request cache (same instance as the annotation
        # resolver uses, when both run in the same GraphQL request).
        document = AnnotationService._get_document_for_request(document_id, context)
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
        can_read, _, _, _, _ = AnnotationService._compute_effective_permissions(
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
