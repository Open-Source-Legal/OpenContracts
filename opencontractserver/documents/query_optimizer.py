"""
Document Query Optimizer for OpenContracts.

Provides optimized queries for document-related actions (extracts, analysis rows, corpus actions).
Follows the least-privilege permission model.
"""

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

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

if TYPE_CHECKING:
    from opencontractserver.documents.models import DocumentRelationship


class DocumentActionsQueryOptimizer:
    """
    Optimized queries for document-related actions (extracts, analysis rows, corpus actions).

    Follows the least-privilege model from AnnotationQueryOptimizer:
    - Document permissions are primary
    - Corpus permissions are secondary
    - Effective permission = MIN(document_permission, corpus_permission)

    This optimizer centralizes permission logic so developers don't need to
    understand the permissioning system when retrieving document-related objects.
    """

    @classmethod
    def get_document_actions(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
    ) -> dict:
        """
        Get all actions/extracts/analyses for a document with proper permission filtering.

        This method follows the least-privilege model:
        1. First checks document permission
        2. If corpus_id provided, also checks corpus permission
        3. Returns only objects the user has access to

        Args:
            user: The requesting user
            document_id: The document ID to get actions for
            corpus_id: Optional corpus ID to filter by

        Returns:
            dict with:
            - corpus_actions: list of CorpusAction objects
            - extracts: list of Extract objects
            - analysis_rows: list of DocumentAnalysisRow objects
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
            ExtractQueryOptimizer,
        )
        from opencontractserver.corpuses.models import Corpus, CorpusAction
        from opencontractserver.documents.models import Document

        result: dict[str, list[Any]] = {
            "corpus_actions": [],
            "extracts": [],
            "analysis_rows": [],
        }

        # Get document first
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return result

        # Check document permission
        if not cls._check_document_permission(user, document):
            return result

        # Get corpus if provided and check permission
        corpus = None
        if corpus_id:
            try:
                corpus = Corpus.objects.get(id=corpus_id)
                if not cls._check_corpus_permission(user, corpus):
                    return result
            except Corpus.DoesNotExist:
                # No corpus found, but document permission passed
                # Return document-only results (no corpus actions)
                pass

        # Get corpus actions (only if corpus is provided and accessible)
        if corpus:
            result["corpus_actions"] = list(
                CorpusAction.objects.visible_to_user(user).filter(corpus=corpus)
            )

        # Get extracts using ExtractQueryOptimizer
        visible_extracts = ExtractQueryOptimizer.get_visible_extracts(
            user, corpus_id=corpus_id
        )
        # Filter to extracts that include this document
        result["extracts"] = list(visible_extracts.filter(documents=document))

        # Get analysis rows
        # Filter to analyses user can see, then get their rows for this document
        visible_analyses = AnalysisQueryOptimizer.get_visible_analyses(
            user, corpus_id=corpus_id
        )
        result["analysis_rows"] = list(
            document.rows.filter(analysis__in=visible_analyses).select_related(
                "analysis", "analysis__analyzer"
            )
        )

        return result

    @classmethod
    def _check_document_permission(cls, user, document) -> bool:
        """
        Check if user has READ permission on document.

        Users can read a document if:
        - They are superuser
        - Document is public
        - They are the creator
        - They have explicit READ permission

        Args:
            user: The requesting user
            document: The Document object

        Returns:
            True if user can read the document, False otherwise
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Superusers can access everything
        if hasattr(user, "is_superuser") and user.is_superuser:
            return True

        # Anonymous users can only access public documents
        if user is None or (hasattr(user, "is_anonymous") and user.is_anonymous):
            return document.is_public

        # Public documents are accessible to all authenticated users
        if document.is_public:
            return True

        # Creators can always access their own documents
        if hasattr(document, "creator_id") and document.creator_id == user.id:
            return True

        # Check explicit READ permission
        return user_has_permission_for_obj(
            user, document, PermissionTypes.READ, include_group_permissions=True
        )

    @classmethod
    def _check_corpus_permission(cls, user, corpus) -> bool:
        """
        Check if user has READ permission on corpus.

        Users can read a corpus if:
        - They are superuser
        - Corpus is public
        - They are the creator
        - They have explicit READ permission

        Args:
            user: The requesting user
            corpus: The Corpus object

        Returns:
            True if user can read the corpus, False otherwise
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Superusers can access everything
        if hasattr(user, "is_superuser") and user.is_superuser:
            return True

        # Anonymous users can only access public corpuses
        if user is None or (hasattr(user, "is_anonymous") and user.is_anonymous):
            return corpus.is_public

        # Public corpuses are accessible to all authenticated users
        if corpus.is_public:
            return True

        # Creators can always access their own corpuses
        if hasattr(corpus, "creator_id") and corpus.creator_id == user.id:
            return True

        # Check explicit READ permission
        return user_has_permission_for_obj(
            user, corpus, PermissionTypes.READ, include_group_permissions=True
        )

    @classmethod
    def get_corpus_actions_for_corpus(
        cls,
        user,
        corpus_id: int,
    ) -> QuerySet:
        """
        Get all corpus actions for a corpus with permission filtering.

        Args:
            user: The requesting user
            corpus_id: The corpus ID

        Returns:
            QuerySet of CorpusAction objects
        """
        from opencontractserver.corpuses.models import Corpus, CorpusAction

        # Check corpus permission first
        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            return CorpusAction.objects.none()

        if not cls._check_corpus_permission(user, corpus):
            return CorpusAction.objects.none()

        # Use visible_to_user manager method
        return CorpusAction.objects.visible_to_user(user).filter(corpus=corpus)

    @classmethod
    def get_extracts_for_document(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
    ) -> QuerySet:
        """
        Get extracts that include a specific document.

        Args:
            user: The requesting user
            document_id: The document ID
            corpus_id: Optional corpus to filter by

        Returns:
            QuerySet of Extract objects
        """
        from opencontractserver.annotations.query_optimizer import (
            ExtractQueryOptimizer,
        )
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import Extract

        # Check document permission
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return Extract.objects.none()

        if not cls._check_document_permission(user, document):
            return Extract.objects.none()

        # Get visible extracts
        visible_extracts = ExtractQueryOptimizer.get_visible_extracts(
            user, corpus_id=corpus_id
        )

        # Filter to those that include this document
        return visible_extracts.filter(documents=document)

    @classmethod
    def get_analysis_rows_for_document(
        cls,
        user,
        document_id: int,
        corpus_id: Optional[int] = None,
    ) -> QuerySet:
        """
        Get analysis rows for a specific document.

        Args:
            user: The requesting user
            document_id: The document ID
            corpus_id: Optional corpus to filter by

        Returns:
            QuerySet of DocumentAnalysisRow objects
        """
        from opencontractserver.annotations.query_optimizer import (
            AnalysisQueryOptimizer,
        )
        from opencontractserver.documents.models import Document, DocumentAnalysisRow

        # Check document permission
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return DocumentAnalysisRow.objects.none()

        if not cls._check_document_permission(user, document):
            return DocumentAnalysisRow.objects.none()

        # Get visible analyses
        visible_analyses = AnalysisQueryOptimizer.get_visible_analyses(
            user, corpus_id=corpus_id
        )

        # Get rows for this document from visible analyses
        return document.rows.filter(analysis__in=visible_analyses).select_related(
            "analysis", "analysis__analyzer"
        )


class DocumentRelationshipQueryOptimizer:
    """
    Optimized queries for DocumentRelationship objects.

    DocumentRelationship inherits permissions from source_document + target_document
    + corpus (same model as annotation Relationships). This optimizer provides
    centralized, permission-aware queries with proper eager loading.

    Permission Model:
    - READ: Can read BOTH source and target documents (and corpus if set)
    - CREATE: Can create on BOTH source and target documents (and corpus if set)
    - UPDATE: Can update on BOTH source and target documents (and corpus if set)
    - DELETE: Can delete on BOTH source and target documents (and corpus if set)

    Formula: Effective Permission = MIN(source_doc_perm, target_doc_perm, corpus_perm)

    Performance Note:
    The _get_visible_document_ids and _get_visible_corpus_ids methods support
    request-level caching via the info.context parameter to prevent N+1 queries
    when resolving relationship counts for multiple documents in a single request.
    """

    # Cache key prefixes for request-level caching
    _VISIBLE_DOC_IDS_CACHE_KEY = "_doc_rel_visible_doc_ids"
    _VISIBLE_CORPUS_IDS_CACHE_KEY = "_doc_rel_visible_corpus_ids"
    _RELATIONSHIP_COUNTS_CACHE_KEY = "_doc_rel_counts"

    @classmethod
    def get_relationship_counts_by_document(
        cls,
        user,
        corpus_id: Optional[int] = None,
        context=None,
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
            context: Optional GraphQL context for request-level caching. When
                provided, the result is cached on the context keyed by
                (user, corpus_id) so repeated resolvers share the work.
        """
        # DocumentRelationship is imported lazily to avoid circular imports
        # between this module and ``opencontractserver.documents.models``.
        from opencontractserver.documents.models import DocumentRelationship

        cache_obj_key = (
            f"{cls._RELATIONSHIP_COUNTS_CACHE_KEY}_"
            f"{getattr(user, 'id', None)}_{corpus_id if corpus_id else 'all'}"
        )
        if context is not None and hasattr(context, cache_obj_key):
            return getattr(context, cache_obj_key)

        is_superuser = bool(getattr(user, "is_superuser", False))
        if is_superuser:
            qs = DocumentRelationship.objects.all()
        else:
            visible_doc_ids = cls._get_visible_document_ids(user, context=context)
            visible_corpus_ids = cls._get_visible_corpus_ids(user, context=context)
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
        if context is not None:
            setattr(context, cache_obj_key, result)
        return result

    @classmethod
    def _get_visible_document_ids(cls, user, context=None) -> QuerySet:
        """
        Get a queryset of document IDs visible to user, suitable for use as
        a SQL subquery via ``__in``.

        Args:
            user: The requesting user
            context: Optional GraphQL context for request-level caching.
                     When provided, the queryset is cached on the context to
                     avoid rebuilding it multiple times in the same request.

        Returns:
            QuerySet of visible document IDs (values queryset)
        """
        from opencontractserver.documents.models import Document

        # Try to use cached value from context
        if context is not None:
            cache_key = f"{cls._VISIBLE_DOC_IDS_CACHE_KEY}_{user.id}"
            if hasattr(context, cache_key):
                return getattr(context, cache_key)

        # Return a lazy values queryset — Django will embed this as a SQL
        # subquery when used with ``__in``, avoiding materialisation into
        # Python memory.
        visible_qs = Document.objects.visible_to_user(user).values("id")

        # Cache on context if available
        if context is not None:
            cache_key = f"{cls._VISIBLE_DOC_IDS_CACHE_KEY}_{user.id}"
            setattr(context, cache_key, visible_qs)

        return visible_qs

    @classmethod
    def _get_visible_corpus_ids(cls, user, context=None) -> QuerySet:
        """
        Get a queryset of corpus IDs visible to user, suitable for use as
        a SQL subquery via ``__in``.

        Args:
            user: The requesting user
            context: Optional GraphQL context for request-level caching.
                     When provided, the queryset is cached on the context to
                     avoid rebuilding it multiple times in the same request.

        Returns:
            QuerySet of visible corpus IDs (values queryset)
        """
        from opencontractserver.corpuses.models import Corpus

        # Try to use cached value from context
        if context is not None:
            cache_key = f"{cls._VISIBLE_CORPUS_IDS_CACHE_KEY}_{user.id}"
            if hasattr(context, cache_key):
                return getattr(context, cache_key)

        # Return a lazy values queryset for SQL subquery usage
        visible_qs = Corpus.objects.visible_to_user(user).values("id")

        # Cache on context if available
        if context is not None:
            cache_key = f"{cls._VISIBLE_CORPUS_IDS_CACHE_KEY}_{user.id}"
            setattr(context, cache_key, visible_qs)

        return visible_qs

    @classmethod
    def _check_corpus_permission(cls, user, corpus) -> bool:
        """Check if user can read the corpus."""
        # Anonymous users can only access public corpuses
        if user is None or (hasattr(user, "is_anonymous") and user.is_anonymous):
            return corpus.is_public

        if user.is_superuser:
            return True
        if corpus.is_public:
            return True
        if corpus.creator_id == user.id:
            return True

        from guardian.shortcuts import get_perms

        perms = get_perms(user, corpus)
        return "read_corpus" in perms

    @classmethod
    def get_visible_relationships(
        cls,
        user,
        source_document_id: Optional[int] = None,
        target_document_id: Optional[int] = None,
        corpus_id: Optional[int] = None,
        relationship_type: Optional[str] = None,
        context=None,
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
            context: Optional GraphQL context for request-level caching

        Returns:
            QuerySet of DocumentRelationship objects with eager loading
        """
        from django.db.models import Q

        from opencontractserver.documents.models import DocumentRelationship

        # Superusers see everything
        is_superuser = user.is_superuser
        if is_superuser:
            queryset = DocumentRelationship.objects.all()
        else:
            # Get subqueries for documents and corpuses user can see
            # Pass context for request-level caching to prevent N+1 queries
            visible_doc_ids = cls._get_visible_document_ids(user, context=context)
            visible_corpus_ids = cls._get_visible_corpus_ids(user, context=context)

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
        # Superusers get all perms; creators get CRUD; others get read only.
        if is_superuser:
            queryset = queryset.annotate(
                _can_read=Value(True, output_field=BooleanField()),
                _can_create=Value(True, output_field=BooleanField()),
                _can_update=Value(True, output_field=BooleanField()),
                _can_delete=Value(True, output_field=BooleanField()),
                _can_publish=Value(True, output_field=BooleanField()),
            )
        else:
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
        context=None,
    ) -> QuerySet:
        """
        Get all DocumentRelationship objects where a document is source or target.

        Args:
            user: The requesting user
            document_id: The document ID
            corpus_id: Optional corpus filter
            include_as_source: Include relationships where doc is source
            include_as_target: Include relationships where doc is target
            context: Optional GraphQL context for request-level caching

        Returns:
            QuerySet of DocumentRelationship objects
        """
        from django.db.models import Q

        from opencontractserver.documents.models import Document, DocumentRelationship

        # Check document exists and user can access it
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            return DocumentRelationship.objects.none()

        if not DocumentActionsQueryOptimizer._check_document_permission(user, document):
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
        # Pass context for request-level caching to prevent N+1 queries
        queryset = cls.get_visible_relationships(
            user, corpus_id=corpus_id, context=context
        ).filter(q_filter)

        return queryset

    @classmethod
    def get_relationship_by_id(
        cls,
        user,
        relationship_id: int,
    ) -> Optional["DocumentRelationship"]:
        """
        Get a single DocumentRelationship by ID with permission check.

        Args:
            user: The requesting user
            relationship_id: The relationship ID

        Returns:
            DocumentRelationship object or None if not found/not accessible
        """
        from django.core.exceptions import ObjectDoesNotExist

        try:
            return cls.get_visible_relationships(user).get(id=relationship_id)
        except ObjectDoesNotExist:
            return None

    @classmethod
    def user_has_permission(
        cls,
        user,
        doc_relationship: "DocumentRelationship",
        permission_type: str,
    ) -> bool:
        """
        Check if user has a specific permission on a DocumentRelationship.

        Permission is inherited from source_document + target_document + corpus.
        User must have the permission on BOTH documents AND corpus (if set).

        Args:
            user: The requesting user
            doc_relationship: The DocumentRelationship object
            permission_type: One of 'READ', 'CREATE', 'UPDATE', 'DELETE'

        Returns:
            True if user has permission, False otherwise
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import user_has_permission_for_obj

        # Superusers have all permissions
        if user.is_superuser:
            return True

        # Map permission type string to enum
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
        if not user_has_permission_for_obj(
            user,
            doc_relationship.source_document,
            perm_enum,
            include_group_permissions=True,
        ):
            return False

        # Check permission on target document
        if not user_has_permission_for_obj(
            user,
            doc_relationship.target_document,
            perm_enum,
            include_group_permissions=True,
        ):
            return False

        # Check permission on corpus (if set)
        if doc_relationship.corpus:
            if not user_has_permission_for_obj(
                user,
                doc_relationship.corpus,
                perm_enum,
                include_group_permissions=True,
            ):
                return False

        return True


class DocumentVersionQueryOptimizer:
    """
    Optimized queries for document version metadata.

    Documents in the same ``version_tree_id`` represent successive content
    versions of the same logical document (Rule C1). The
    ``DocumentType.versionCount`` GraphQL field surfaces the size of that
    tree to the UI, so any list view that selects it would otherwise issue
    one ``COUNT(*)`` per row — the classic N+1 storm.

    This optimizer batches that work into a single aggregated query per
    request, scoped to documents the user is allowed to read so the badge
    cannot be used to enumerate hidden versions.
    """

    _VERSION_COUNTS_CACHE_KEY = "_doc_version_counts_by_tree"

    @classmethod
    def get_version_counts_by_tree(
        cls,
        user,
        context=None,
    ) -> dict[UUID, int]:
        """
        Return a mapping ``{version_tree_id: count}`` of visible documents per
        version tree, computed in a single aggregated SQL query.

        Replaces the per-document ``.count()`` pattern in
        ``resolve_version_count`` (config/graphql/document_types.py), which
        produced N+1 query storms when ``versionCount`` was selected on a
        paginated documents connection.

        The aggregation is scoped to ``Document.objects.visible_to_user(user)``
        so the badge cannot leak the existence of versions the user is not
        allowed to see.

        Args:
            user: The requesting user.
            context: Optional GraphQL context for request-level caching. When
                provided, the result is cached on the context keyed by user
                so repeated resolvers in the same request share the work.

        Returns:
            A plain ``dict`` keyed by ``version_tree_id`` (UUID) with visible
            document counts as values. Trees with no visible documents are
            absent from the dict; resolvers should fall back to a sensible
            default (typically 1, since the resolver is only called on a
            document the user can already see).
        """
        from opencontractserver.documents.models import Document

        cache_obj_key = f"{cls._VERSION_COUNTS_CACHE_KEY}_{getattr(user, 'id', None)}"
        if context is not None and hasattr(context, cache_obj_key):
            return getattr(context, cache_obj_key)

        rows = (
            Document.objects.visible_to_user(user)
            .values("version_tree_id")
            .annotate(c=Count("id"))
        )
        result: dict[UUID, int] = {r["version_tree_id"]: r["c"] for r in rows}

        if context is not None:
            setattr(context, cache_obj_key, result)
        return result
