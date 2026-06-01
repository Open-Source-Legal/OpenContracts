"""Analysis read-service — visibility and permission queries for ``Analysis``.

Relocated from the former ``annotations/query_optimizer.py`` (where the
``AnalysisQueryOptimizer`` class was misfiled — ``Analysis`` is an
``analyzer`` concern, not an ``annotations`` one) into its correct app as
Phase 3 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.

Behaviour is preserved exactly — this is a relocation, not a rewrite.
"""

from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Count, Exists, OuterRef, Q, QuerySet

from opencontractserver.shared.services import BaseService

if TYPE_CHECKING:
    from opencontractserver.analyzer.models import Analysis


class AnalysisService(BaseService):
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

        # scoped admin access, 2026-05: admins computed like a normal user
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

        # scoped admin access, 2026-05: admins computed like a normal user
        if user.is_anonymous:
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
                # scoped admin access, 2026-05: admins computed like a normal user
                elif not corpus.user_can(user, PermissionTypes.READ, request=context):
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
            # scoped admin access, 2026-05: admins computed like a normal user
            try:
                doc = Document.objects.get(id=document_id)
                if not doc.user_can(user, PermissionTypes.READ):
                    return Annotation.objects.none()
            except Document.DoesNotExist:
                return Annotation.objects.none()
        else:
            # Filter to only documents user can read
            # scoped admin access, 2026-05: admins computed like a normal user
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
