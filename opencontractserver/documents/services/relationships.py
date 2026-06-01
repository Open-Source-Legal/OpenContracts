"""Document relationship service — permission-aware ``DocumentRelationship`` queries.

``DocumentRelationship`` inherits permissions from ``source_document`` +
``target_document`` + ``corpus`` (same model as annotation Relationships).
This service provides centralized, permission-aware queries with proper
eager loading.

Permission Model:
- READ: Can read BOTH source and target documents (and corpus if set)
- CREATE: Can create on BOTH source and target documents (and corpus if set)
- UPDATE: Can update on BOTH source and target documents (and corpus if set)
- DELETE: Can delete on BOTH source and target documents (and corpus if set)

Formula: Effective Permission = MIN(source_doc_perm, target_doc_perm, corpus_perm)

Performance Note:
The ``_get_visible_document_ids`` and ``_get_visible_corpus_ids`` helpers
support request-level caching via the ``request`` parameter to prevent N+1
queries when resolving relationship counts for multiple documents in a
single request.

Migrated from ``documents/query_optimizer.py`` as Phase 4 of the
service-layer centralization roadmap — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional

from django.db.models import (
    BooleanField,
    Case,
    Count,
    F,
    Q,
    QuerySet,
    Value,
    When,
)

from opencontractserver.shared.services import BaseService

if TYPE_CHECKING:
    from opencontractserver.documents.models import DocumentRelationship


class DocumentRelationshipService(BaseService):
    """Permission-aware queries for ``DocumentRelationship`` objects."""

    # Cache key prefixes for request-level caching
    _VISIBLE_DOC_IDS_CACHE_KEY = "_doc_rel_visible_doc_ids"
    _VISIBLE_CORPUS_IDS_CACHE_KEY = "_doc_rel_visible_corpus_ids"
    _RELATIONSHIP_COUNTS_CACHE_KEY = "_doc_rel_counts"

    @classmethod
    def get_relationship_counts_by_document(
        cls,
        user,
        corpus_id: Optional[int] = None,
        *,
        request: Optional[Any] = None,
    ) -> dict[int, int]:
        """
        Return a mapping ``{document_id: count}`` of visible relationships per
        document, computed in a single pair of aggregated SQL queries.

        This replaces the per-document ``.count()`` pattern in
        ``resolve_doc_relationship_count``, which produced N+1 query storms
        when resolving the count field for every document in a list view.

        Each ``DocumentRelationship`` contributes 1 to BOTH its source and
        target document's count.

        Args:
            user: The requesting user.
            corpus_id: Optional corpus filter (matches the resolver argument).
            request: Optional request object for request-level caching. When
                provided, the result is cached on the request keyed by
                (user, corpus_id) so repeated resolvers share the work.
        """
        # DocumentRelationship is imported lazily to avoid circular imports
        # between this module and ``opencontractserver.documents.models``.
        from opencontractserver.documents.models import DocumentRelationship

        cache_obj_key = (
            f"{cls._RELATIONSHIP_COUNTS_CACHE_KEY}_"
            f"{getattr(user, 'id', None)}_{corpus_id if corpus_id else 'all'}"
        )
        if request is not None and hasattr(request, cache_obj_key):
            return getattr(request, cache_obj_key)

        # Superusers are computed like any other user (scoped admin access, 2026-05).
        visible_doc_ids = cls._get_visible_document_ids(user, request=request)
        visible_corpus_ids = cls._get_visible_corpus_ids(user, request=request)
        # Visibility requires BOTH endpoints to be readable (matches
        # ``get_visible_relationships``). This intentionally hides a
        # relationship from the count when the *other* document is
        # invisible to the user — surfacing the count would otherwise leak
        # the existence of a hidden document via the badge number.
        qs = DocumentRelationship.objects.filter(
            source_document_id__in=visible_doc_ids,
            target_document_id__in=visible_doc_ids,
        ).filter(Q(corpus__isnull=True) | Q(corpus_id__in=visible_corpus_ids))

        if corpus_id:
            qs = qs.filter(corpus_id=corpus_id)

        counts: defaultdict[int, int] = defaultdict(int)
        for row in qs.values("source_document_id").annotate(c=Count("id")):
            counts[row["source_document_id"]] += row["c"]
        # Exclude self-referential rows from the target-side aggregation so a
        # relationship where source == target only contributes once. Without
        # this guard, such a row would be counted both as a source and as a
        # target for the same document.
        for row in (
            qs.exclude(source_document_id=F("target_document_id"))
            .values("target_document_id")
            .annotate(c=Count("id"))
        ):
            counts[row["target_document_id"]] += row["c"]

        # Materialise to a plain dict so callers can ``.get(key, 0)`` without
        # accidentally mutating the defaultdict.
        result = dict(counts)
        if request is not None:
            setattr(request, cache_obj_key, result)
        return result

    @classmethod
    def _get_visible_document_ids(
        cls, user, *, request: Optional[Any] = None
    ) -> QuerySet:
        """
        Get a queryset of document IDs visible to user, suitable for use as
        a SQL subquery via ``__in``.

        Args:
            user: The requesting user
            request: Optional request object for request-level caching.
                     When provided, the queryset is cached on the request to
                     avoid rebuilding it multiple times in the same request.

        Returns:
            QuerySet of visible document IDs (values queryset)
        """
        from opencontractserver.documents.models import Document

        # Try to use cached value from request
        if request is not None:
            cache_key = f"{cls._VISIBLE_DOC_IDS_CACHE_KEY}_{user.id}"
            if hasattr(request, cache_key):
                return getattr(request, cache_key)

        # Return a lazy values queryset — Django will embed this as a SQL
        # subquery when used with ``__in``, avoiding materialisation into
        # Python memory.
        visible_qs = Document.objects.visible_to_user(user).values("id")

        # Cache on request if available
        if request is not None:
            cache_key = f"{cls._VISIBLE_DOC_IDS_CACHE_KEY}_{user.id}"
            setattr(request, cache_key, visible_qs)

        return visible_qs

    @classmethod
    def _get_visible_corpus_ids(
        cls, user, *, request: Optional[Any] = None
    ) -> QuerySet:
        """
        Get a queryset of corpus IDs visible to user, suitable for use as
        a SQL subquery via ``__in``.

        Args:
            user: The requesting user
            request: Optional request object for request-level caching.
                     When provided, the queryset is cached on the request to
                     avoid rebuilding it multiple times in the same request.

        Returns:
            QuerySet of visible corpus IDs (values queryset)
        """
        from opencontractserver.corpuses.models import Corpus

        # Try to use cached value from request
        if request is not None:
            cache_key = f"{cls._VISIBLE_CORPUS_IDS_CACHE_KEY}_{user.id}"
            if hasattr(request, cache_key):
                return getattr(request, cache_key)

        # Return a lazy values queryset for SQL subquery usage
        visible_qs = Corpus.objects.visible_to_user(user).values("id")

        # Cache on request if available
        if request is not None:
            cache_key = f"{cls._VISIBLE_CORPUS_IDS_CACHE_KEY}_{user.id}"
            setattr(request, cache_key, visible_qs)

        return visible_qs

    @classmethod
    def get_visible_relationships(
        cls,
        user,
        source_document_id: Optional[int] = None,
        target_document_id: Optional[int] = None,
        corpus_id: Optional[int] = None,
        relationship_type: Optional[str] = None,
        *,
        request: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get DocumentRelationship objects visible to the user.

        Visibility requires READ permission on BOTH source and target documents,
        and on corpus if set.

        Args:
            user: The requesting user
            source_document_id: Optional filter by source document
            target_document_id: Optional filter by target document
            corpus_id: Optional filter by corpus
            relationship_type: Optional filter by type ("RELATIONSHIP" or "NOTES")
            request: Optional request object for request-level caching

        Returns:
            QuerySet of DocumentRelationship objects with eager loading
        """
        from opencontractserver.documents.models import DocumentRelationship

        # Superusers are computed like any other user (scoped admin access, 2026-05).
        # Get subqueries for documents and corpuses user can see
        # Pass request for request-level caching to prevent N+1 queries
        visible_doc_ids = cls._get_visible_document_ids(user, request=request)
        visible_corpus_ids = cls._get_visible_corpus_ids(user, request=request)

        # Filter: user can see BOTH source and target documents
        # AND (no corpus OR user can see corpus)
        queryset = DocumentRelationship.objects.filter(
            source_document_id__in=visible_doc_ids,
            target_document_id__in=visible_doc_ids,
        ).filter(Q(corpus__isnull=True) | Q(corpus_id__in=visible_corpus_ids))

        # Apply additional filters
        if source_document_id:
            queryset = queryset.filter(source_document_id=source_document_id)
        if target_document_id:
            queryset = queryset.filter(target_document_id=target_document_id)
        if corpus_id:
            queryset = queryset.filter(corpus_id=corpus_id)
        if relationship_type:
            queryset = queryset.filter(relationship_type=relationship_type)

        # Pre-compute permission flags so AnnotatePermissionsForReadMixin
        # can use them instead of querying non-existent guardian tables.
        # All returned results passed the visibility filter → _can_read=True.
        # Creators get CRUD; others get read only. Superusers are treated like
        # any other user (scoped admin access, 2026-05).
        #
        # For anonymous users, user.id is None so this becomes
        # Q(creator_id=None). This is safe because every relationship
        # has a non-null creator, so the condition simply won't match.
        is_creator = Q(creator_id=user.id)
        queryset = queryset.annotate(
            _can_read=Value(True, output_field=BooleanField()),
            _can_create=Case(
                When(is_creator, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
            _can_update=Case(
                When(is_creator, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
            _can_delete=Case(
                When(is_creator, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
            _can_publish=Value(False, output_field=BooleanField()),
        )

        # Eager load related objects (including nested creator FKs to avoid N+1)
        return queryset.select_related(
            "source_document__creator",
            "target_document__creator",
            "annotation_label",
            "corpus__creator",
            "creator",
        )

    @classmethod
    def get_relationships_for_document(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
        include_as_source: bool = True,
        include_as_target: bool = True,
        *,
        request: Optional[Any] = None,
    ) -> QuerySet:
        """
        Get all DocumentRelationship objects where a document is source or target.

        Args:
            user: The requesting user
            document_id: The document ID
            corpus_id: Optional corpus filter
            include_as_source: Include relationships where doc is source
            include_as_target: Include relationships where doc is target
            request: Optional request object for request-level caching

        Returns:
            QuerySet of DocumentRelationship objects
        """
        from opencontractserver.documents.models import Document, DocumentRelationship
        from opencontractserver.types.enums import PermissionTypes

        # Check document exists and user can access it
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return DocumentRelationship.objects.none()

        if not document.user_can(user, PermissionTypes.READ, request=request):
            return DocumentRelationship.objects.none()

        # Build filter for source/target
        q_filter = Q()
        if include_as_source:
            q_filter |= Q(source_document_id=document_id)
        if include_as_target:
            q_filter |= Q(target_document_id=document_id)

        if not q_filter:
            return DocumentRelationship.objects.none()

        # Use get_visible_relationships for permission filtering, then apply doc filter
        # Pass request for request-level caching to prevent N+1 queries
        queryset = cls.get_visible_relationships(
            user, corpus_id=corpus_id, request=request
        ).filter(q_filter)

        return queryset

    @classmethod
    def get_relationship_by_id(
        cls,
        user,
        relationship_id: int,
        *,
        request: Optional[Any] = None,
    ) -> Optional["DocumentRelationship"]:
        """
        Get a single DocumentRelationship by ID with permission check.

        Args:
            user: The requesting user
            relationship_id: The relationship ID
            request: Optional request object for request-level caching

        Returns:
            DocumentRelationship object or None if not found/not accessible
        """
        from django.core.exceptions import ObjectDoesNotExist

        try:
            return cls.get_visible_relationships(user, request=request).get(
                id=relationship_id
            )
        except ObjectDoesNotExist:
            return None

    @classmethod
    def user_has_permission(
        cls,
        user,
        doc_relationship: "DocumentRelationship",
        permission_type: str,
        *,
        request: Optional[Any] = None,
    ) -> bool:
        """
        Check if user has a specific permission on a DocumentRelationship.

        Permission is inherited from source_document + target_document + corpus.
        User must have the permission on BOTH documents AND corpus (if set).

        Args:
            user: The requesting user
            doc_relationship: The DocumentRelationship object
            permission_type: One of 'READ', 'CREATE', 'UPDATE', 'DELETE'
            request: Optional request object threaded into ``user_can`` so the
                Tier-2 request-scoped permission cache applies.

        Returns:
            True if user has permission, False otherwise
        """
        from opencontractserver.types.enums import PermissionTypes

        # Map permission type string to enum. ``user_can`` already handles the
        # superuser short-circuit, so we don't need a guard here.
        perm_map = {
            "READ": PermissionTypes.READ,
            "CREATE": PermissionTypes.CREATE,
            "UPDATE": PermissionTypes.UPDATE,
            "DELETE": PermissionTypes.DELETE,
        }
        perm_enum = perm_map.get(permission_type.upper())
        if not perm_enum:
            return False

        # Check permission on source document
        if not doc_relationship.source_document.user_can(
            user, perm_enum, request=request
        ):
            return False

        # Check permission on target document
        if not doc_relationship.target_document.user_can(
            user, perm_enum, request=request
        ):
            return False

        # Check permission on corpus (if set)
        if doc_relationship.corpus:
            if not doc_relationship.corpus.user_can(user, perm_enum, request=request):
                return False

        return True
