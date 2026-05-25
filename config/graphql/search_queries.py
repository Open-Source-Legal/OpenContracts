"""
GraphQL query mixin for search and mention queries.
"""

import logging
from typing import Any

import graphene
from django.contrib.postgres.search import SearchQuery
from django.db.models import Q
from django.db.models.functions import Left
from graphene_django.fields import DjangoConnectionField
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import (
    AgentConfigurationType,
    AnnotationType,
    BlockContextType,
    CorpusType,
    DocumentType,
    NoteType,
    SemanticSearchRelationshipResultType,
    SemanticSearchResultType,
    UserType,
)
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from opencontractserver.annotations.models import Annotation, Note
from opencontractserver.constants.annotations import SEMANTIC_SEARCH_MAX_RESULTS
from opencontractserver.constants.search import FTS_CONFIG
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


class SearchQueryMixin:
    """Query fields and resolvers for search and mention queries."""

    # SEARCH RESOURCES FOR MENTIONS #####################################
    search_corpuses_for_mention = DjangoConnectionField(
        CorpusType,
        text_search=graphene.String(
            description="Search query to find corpuses by title or description"
        ),
    )
    search_documents_for_mention = DjangoConnectionField(
        DocumentType,
        text_search=graphene.String(
            description="Search query to find documents by title or description"
        ),
        corpus_id=graphene.ID(
            description="Optional corpus ID to scope search to documents in specific corpus"
        ),
    )
    search_annotations_for_mention = DjangoConnectionField(
        AnnotationType,
        text_search=graphene.String(
            description="Search query to find annotations by label text or raw content"
        ),
        corpus_id=graphene.ID(
            description="Optional corpus ID to scope search to specific corpus"
        ),
    )
    search_users_for_mention = DjangoConnectionField(
        UserType,
        text_search=graphene.String(
            description="Search query to find users by slug or display handle"
        ),
    )

    search_agents_for_mention = DjangoConnectionField(
        AgentConfigurationType,
        text_search=graphene.String(
            description="Search query to find agents by name, slug, or description"
        ),
        corpus_id=graphene.ID(
            description="Corpus ID to scope agent search (includes global + corpus agents)"
        ),
    )

    search_notes_for_mention = DjangoConnectionField(
        NoteType,
        text_search=graphene.String(
            description="Search query to find notes by title or content"
        ),
        corpus_id=graphene.ID(
            description="Optional corpus ID to scope search to notes in specific corpus"
        ),
        document_id=graphene.ID(
            description="Optional document ID to scope search to notes on a specific document"
        ),
    )

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_corpuses_for_mention(
        self, info, text_search=None, **kwargs
    ) -> Any:
        """
        Search corpuses for @ mention autocomplete.

        SECURITY: Only returns corpuses where user can meaningfully contribute.
        Requires write permission (CREATE/UPDATE/DELETE), creator status, or public corpus.

        Rationale: Mentioning a corpus implies drawing attention to it for collaborative
        purposes. Read-only viewers shouldn't be mentioning corpuses since they can't
        contribute to them.

        See: docs/permissioning/mention_permissioning_spec.md
        """
        from guardian.shortcuts import get_objects_for_user

        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return Corpus.objects.none()

        # Superusers see all corpuses
        if user.is_superuser:
            qs = Corpus.objects.all()
        else:
            # Get corpuses user has write permission to
            writable_corpuses = get_objects_for_user(
                user,
                [
                    "corpuses.create_corpus",
                    "corpuses.update_corpus",
                    "corpuses.remove_corpus",  # Note: PermissionTypes.DELETE maps to "remove"
                ],
                klass=Corpus,
                accept_global_perms=False,
                any_perm=True,  # Has ANY of these permissions
            )

            # Combine: creator OR writable OR public
            qs = Corpus.objects.filter(
                Q(creator=user) | Q(id__in=writable_corpuses) | Q(is_public=True)
            ).distinct()

        if text_search:
            qs = qs.filter(
                Q(title__icontains=text_search) | Q(description__icontains=text_search)
            )

        # Order by most recently modified first
        return qs.order_by("-modified")

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_documents_for_mention(
        self, info, text_search=None, corpus_id=None, **kwargs
    ) -> Any:
        """
        Search documents for @ mention autocomplete.

        SECURITY: Only returns documents where user can meaningfully contribute.
        Requires one of:
        - User is creator
        - User has write permission on document
        - Document is in a corpus where user has write permission
        - Document is public AND (no corpus OR public corpus OR user has corpus access)

        When corpus_id is provided, results are further filtered to only include
        documents that belong to that specific corpus. This prevents cross-corpus
        document references in AI agent contexts (Issue #741).

        Rationale: Similar to corpuses, mentioning a document implies collaborative context.
        However, public documents are included to allow discussion/reference in open forums.

        See: docs/permissioning/mention_permissioning_spec.md
        """
        from guardian.shortcuts import get_objects_for_user

        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return Document.objects.none()

        # Superusers see all documents
        if user.is_superuser:
            qs = Document.objects.all()
        else:
            # Get documents user has write permission to
            writable_documents = get_objects_for_user(
                user,
                [
                    "documents.create_document",
                    "documents.update_document",
                    "documents.remove_document",  # Note: PermissionTypes.DELETE maps to "remove"
                ],
                klass=Document,
                accept_global_perms=False,
                any_perm=True,
            )

            # Get corpuses user has write permission to
            writable_corpuses = get_objects_for_user(
                user,
                [
                    "corpuses.create_corpus",
                    "corpuses.update_corpus",
                    "corpuses.remove_corpus",  # Note: PermissionTypes.DELETE maps to "remove"
                ],
                klass=Corpus,
                accept_global_perms=False,
                any_perm=True,
            )

            # Get corpuses user can at least read (for public document context)
            readable_corpuses = BaseService.filter_visible(
                Corpus, user, request=info.context
            )

            # Get documents in writable corpuses via DocumentPath (corpus isolation)
            from opencontractserver.documents.models import DocumentPath

            docs_in_writable_corpuses = DocumentPath.objects.filter(
                corpus__in=writable_corpuses, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)

            # Get documents in readable corpuses for public document context
            docs_in_readable_corpuses = DocumentPath.objects.filter(
                corpus__in=readable_corpuses, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)

            # Get documents in public corpuses for public document context
            public_corpuses = Corpus.objects.filter(is_public=True)
            docs_in_public_corpuses = DocumentPath.objects.filter(
                corpus__in=public_corpuses, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)

            # Get standalone documents (not in any corpus via DocumentPath)
            docs_with_paths = (
                DocumentPath.objects.filter(is_current=True, is_deleted=False)
                .values_list("document_id", flat=True)
                .distinct()
            )

            # Build complex filter:
            # 1. User is creator
            # 2. User has write permission on document
            # 3. Document is in a writable corpus (via DocumentPath)
            # 4. Document is public AND (not in any corpus OR in public corpus OR user has corpus access)
            qs = Document.objects.filter(
                Q(creator=user)
                | Q(id__in=writable_documents)
                | Q(id__in=docs_in_writable_corpuses)  # Via DocumentPath
                | (
                    Q(is_public=True)
                    & (
                        ~Q(id__in=docs_with_paths)  # Not in any corpus (standalone)
                        | Q(id__in=docs_in_public_corpuses)  # In a public corpus
                        | Q(id__in=docs_in_readable_corpuses)  # In a readable corpus
                    )
                )
            ).distinct()

        if text_search:
            qs = qs.filter(
                Q(title__icontains=text_search) | Q(description__icontains=text_search)
            )

        # Filter by corpus if provided (Issue #741 - prevent cross-corpus references)
        if corpus_id:
            from opencontractserver.documents.models import DocumentPath

            _, corpus_pk = from_global_id(corpus_id)
            docs_in_target_corpus = DocumentPath.objects.filter(
                corpus_id=int(corpus_pk),
                is_current=True,
                is_deleted=False,
            ).values_list("document_id", flat=True)
            qs = qs.filter(id__in=docs_in_target_corpus)

        # Note: corpus field exists in model but not in current DB schema for select_related
        # Documents use Many-to-Many relationship via Corpus.documents instead

        # Order by most recently modified first
        return qs.order_by("-modified")

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_annotations_for_mention(
        self, info, text_search=None, corpus_id=None, **kwargs
    ) -> Any:
        """
        Search annotations for @ mention autocomplete.

        SECURITY: Annotations inherit permissions from document + corpus.
        Uses .visible_to_user() which applies composite permission logic.

        PERFORMANCE NOTES:
        - Prioritizes annotation_label.text matches (indexed, fast)
        - Falls back to raw_text search (full-text, slower)
        - Corpus scoping significantly reduces search space
        - Limits to 10 results to prevent overwhelming UI

        Rationale: Mentioning annotations allows precise reference to specific
        content sections. Useful for discussions, citations, and cross-references.

        @param text_search: Search query for label text or content
        @param corpus_id: Optional corpus to scope search (recommended for performance)
        """
        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return Annotation.objects.none()

        # Route through the service layer; the manager handles the composite
        # document+corpus permission logic underneath.
        qs = BaseService.filter_visible(Annotation, user, request=info.context)

        # Scope to specific corpus if provided (major performance boost)
        # Issue #741: Fix to properly convert GraphQL global ID to database primary key
        if corpus_id:
            _, corpus_pk = from_global_id(corpus_id)
            qs = qs.filter(corpus_id=int(corpus_pk))

        if text_search:
            # Three complementary matchers, OR'd together, so the search box
            # behaves the way users expect as they type:
            #   1. annotation_label.text — case-insensitive substring match.
            #   2. raw_text icontains   — case-insensitive substring match,
            #      backed by a pg_trgm GIN index. Catches prefixes/fragments
            #      (e.g. "indemn") that full-text search misses, because FTS
            #      only matches whole, stemmed lexemes — not substrings.
            #   3. search_vector        — full-text search; keeps stemming and
            #      ranking (e.g. "running" finds "ran"), which raw substring
            #      matching cannot. Populated from raw_text by a DB trigger.
            search_query = SearchQuery(text_search, config=FTS_CONFIG)
            qs = qs.filter(
                Q(annotation_label__text__icontains=text_search)
                | Q(raw_text__icontains=text_search)
                | Q(search_vector=search_query)
            )

        # Select related for efficient queries
        qs = qs.select_related("annotation_label", "document", "corpus")

        # Order by label match first (more relevant), then by created date
        # Annotations matching label text are usually more specific/useful
        from django.db.models import Case, IntegerField, Value, When

        if text_search:
            qs = qs.annotate(
                label_match=Case(
                    When(
                        annotation_label__text__icontains=text_search,
                        then=Value(0),
                    ),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("label_match", "-created")
        else:
            qs = qs.order_by("-created")

        # Note: DjangoConnectionField handles pagination automatically
        # Slicing here would prevent GraphQL from applying filters
        return qs

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_users_for_mention(self, info, text_search=None, **kwargs) -> Any:
        """
        Search users for @ mention autocomplete.

        SECURITY: Respects user profile privacy settings.
        Users are visible if:
        - Profile is public (is_profile_public=True)
        - Requesting user shares corpus membership with > READ permission
        - It's the requesting user's own profile

        Searches only the public ``slug`` and ``handle`` fields so that
        OAuth provider subs and email addresses cannot be used as a
        discovery oracle (even though those fields are self-only gated in
        the response, allowing search-by-email would confirm membership).

        PERFORMANCE NOTES:
        - Uses UserService for efficient visibility filtering
        - Searches slug and handle (both indexed)

        @param text_search: Search query for slug or display handle
        """
        from django.contrib.auth import get_user_model

        from opencontractserver.users.services import UserService

        User = get_user_model()
        user = info.context.user

        # Anonymous users cannot mention (must be authenticated)
        if user.is_anonymous:
            return User.objects.none()

        # Use UserService for visibility filtering
        qs = UserService.get_visible_users(user, request=info.context)

        if text_search:
            # Only search public identifiers — never username (OAuth sub) or email.
            qs = qs.filter(
                Q(slug__icontains=text_search) | Q(handle__icontains=text_search)
            )

        # Order by slug for consistent, publicly-meaningful results
        qs = qs.order_by("slug")

        # Note: DjangoConnectionField handles pagination automatically
        return qs

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_agents_for_mention(
        self, info, text_search=None, corpus_id=None, **kwargs
    ) -> Any:
        """
        Search agents for @ mention autocomplete.

        Returns:
        - All active global agents (GLOBAL scope)
        - Corpus-specific agents for the provided corpus (if user has access)

        SECURITY: Filters by visibility - users only see agents they can mention.
        Anonymous users cannot search agents.
        """
        from opencontractserver.agents.services import AgentConfigurationService

        # IDOR-safe global-id decode: a malformed ``corpus_id`` (bad
        # base64, non-numeric body, or a stray byte string) would
        # otherwise raise inside ``from_global_id`` / ``int()`` and
        # surface as a 500. Treat it as "no corpus scope" so the
        # resolver degrades gracefully — mirrors the IDOR-safe decode
        # pattern in ``resolve_search_notes_for_mention`` above.
        corpus_pk: int | None = None
        if corpus_id:
            try:
                corpus_pk = int(from_global_id(corpus_id)[1])
            except (ValueError, TypeError, UnicodeDecodeError):
                corpus_pk = None

        qs = AgentConfigurationService.search_mentionable_agents(
            info.context.user,
            text_search=text_search,
            corpus_id=corpus_pk,
            request=info.context,
        )

        # Order: Global first, then corpus-specific, then alphabetically by name
        return qs.select_related("creator", "corpus").order_by("scope", "name")

    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("READ_LIGHT"))
    def resolve_search_notes_for_mention(
        self, info, text_search=None, corpus_id=None, document_id=None, **kwargs
    ) -> Any:
        """
        Search notes by title or content.

        SECURITY: Notes inherit visibility from document + corpus via
        `Note.objects.visible_to_user()`. Anonymous users only see notes whose
        document, corpus (if any), and the note itself are public.
        """
        user = info.context.user

        qs = BaseService.filter_visible(Note, user, request=info.context)

        # Reject malformed or wrong-type global IDs by returning an empty
        # queryset rather than silently filtering on a non-existent FK.
        if corpus_id:
            try:
                type_name, corpus_pk = from_global_id(corpus_id)
            except (ValueError, UnicodeDecodeError):
                return Note.objects.none()
            if type_name != "CorpusType":
                return Note.objects.none()
            qs = qs.filter(corpus_id=int(corpus_pk))

        if document_id:
            try:
                type_name, document_pk = from_global_id(document_id)
            except (ValueError, UnicodeDecodeError):
                return Note.objects.none()
            if type_name != "DocumentType":
                return Note.objects.none()
            qs = qs.filter(document_id=int(document_pk))

        if text_search:
            # TODO(perf): Note has no `search_vector` column today (unlike
            # Annotation), so `icontains` is the only available substring
            # matcher. This is `LIKE '%…%'` and cannot use a B-tree or GIN
            # index — it degrades to a sequential scan as note volume grows
            # and returns lower-quality matches than FTS (no stemming/rank).
            # The fix is to add a `SearchVectorField` + GIN index to `Note`,
            # backfill it, and switch this filter to `SearchQuery` /
            # `SearchVector` with `FTS_CONFIG` (mirroring
            # `resolve_search_annotations_for_mention`). Acceptable for the
            # small note corpora this was tested against.
            qs = qs.filter(
                Q(title__icontains=text_search) | Q(content__icontains=text_search)
            )

        # Eager-load the relations the result row needs for deep-linking, and
        # annotate a DB-truncated preview so the wire payload doesn't ship the
        # full markdown body for every result.
        qs = qs.select_related(
            "document", "document__creator", "corpus", "creator"
        ).annotate(content_preview=Left("content", 400))

        # NoteType.get_queryset re-applies `visible_to_user` as a defensive
        # second pass, so callers cannot widen visibility by bypassing this
        # resolver.
        return qs.order_by("-modified")

    # SEMANTIC SEARCH QUERIES #############################################
    semantic_search = graphene.List(
        SemanticSearchResultType,
        query=graphene.String(required=True, description="Search query text"),
        corpus_id=graphene.ID(
            required=False, description="Optional corpus ID to search within"
        ),
        document_id=graphene.ID(
            required=False, description="Optional document ID to search within"
        ),
        modalities=graphene.List(
            graphene.String,
            required=False,
            description="Filter by content modalities (TEXT, IMAGE)",
        ),
        label_text=graphene.String(
            required=False,
            description="Filter by annotation label text (case-insensitive substring match)",
        ),
        raw_text_contains=graphene.String(
            required=False,
            description="Filter by raw_text content (case-insensitive substring match)",
        ),
        limit=graphene.Int(
            default_value=50,
            description=f"Maximum number of results to return (default: 50, max: {SEMANTIC_SEARCH_MAX_RESULTS})",
        ),
        offset=graphene.Int(
            default_value=0,
            description="Number of results to skip for pagination",
        ),
        description=(
            "Hybrid search combining vector similarity with text filters. "
            "Uses the default embedder for global cross-corpus search. "
            "Results are first filtered by text criteria, then ranked by similarity."
        ),
    )

    @login_required
    def resolve_semantic_search(
        self,
        info,
        query,
        corpus_id=None,
        document_id=None,
        modalities=None,
        label_text=None,
        raw_text_contains=None,
        limit=50,
        offset=0,
    ) -> Any:
        """
        Hybrid search combining vector similarity with text filters.

        This query enables semantic (meaning-based) search across all annotations
        the user has access to, using the default embedder embeddings that are
        created for every annotation as part of the dual embedding strategy.

        HYBRID SEARCH:
        - Vector similarity search ranks results by semantic relevance
        - Text filters (label_text, raw_text_contains) narrow down results
        - Filters are applied BEFORE vector search for efficiency

        PERMISSION MODEL (follows consolidated_permissioning_guide.md):
        - Uses Document.objects.visible_to_user() for document access control
        - Structural annotations are always visible if document is accessible
        - Non-structural annotations follow: visible if public OR owned by user
        - Corpus permissions are respected via document visibility

        Args:
            info: GraphQL execution info
            query: Search query text for vector similarity
            corpus_id: Optional corpus ID to limit search to (global ID)
            document_id: Optional document ID to limit search to (global ID)
            modalities: Optional list of modalities to filter by (TEXT, IMAGE)
            label_text: Optional filter by annotation label text (case-insensitive)
            raw_text_contains: Optional filter by raw_text substring (case-insensitive)
            limit: Maximum number of results (capped at 200)
            offset: Pagination offset

        Returns:
            List[SemanticSearchResultType]: List of matching annotations with scores
        """
        from opencontractserver.llms.vector_stores.core_vector_stores import (
            CoreAnnotationVectorStore,
        )

        # Alias for clarity: `query` is the GraphQL argument name (raw user
        # text), while `query_text` is used internally to avoid confusion with
        # Django's SearchQuery or VectorSearchQuery objects created later.
        query_text = query

        # N+1 OPTIMIZATION NOTE: The CoreAnnotationVectorStore already applies
        # select_related("annotation_label", "document", "corpus") to the base
        # queryset (see core_vector_stores.py:200-202 and :639-641). This means
        # all related objects are eagerly loaded and no additional queries are
        # made when accessing annotation.document, annotation.corpus, or
        # annotation.annotation_label in the filter loops or result types below.
        # Cap limit to prevent abuse
        limit = min(limit, SEMANTIC_SEARCH_MAX_RESULTS)

        # Convert global IDs to database IDs
        corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None
        document_pk = int(from_global_id(document_id)[1]) if document_id else None

        user = info.context.user

        # -------------------------------------------------------------------------
        # SECURITY: Verify user has access to requested document/corpus (IDOR prevention)
        # Uses visible_to_user() which returns empty queryset if no access.
        # We return empty results for both "not found" and "no permission" cases
        # to prevent enumeration attacks.
        # -------------------------------------------------------------------------
        if document_pk:
            if (
                not BaseService.filter_visible(Document, user, request=info.context)
                .filter(id=document_pk)
                .exists()
            ):
                # Document doesn't exist or user lacks permission - return empty results
                return []

        if corpus_pk:
            if (
                not BaseService.filter_visible(Corpus, user, request=info.context)
                .filter(id=corpus_pk)
                .exists()
            ):
                # Corpus doesn't exist or user lacks permission - return empty results
                return []

        # Build metadata filters for hybrid search
        metadata_filters = {}
        if label_text:
            metadata_filters["annotation_label"] = label_text
        if raw_text_contains:
            metadata_filters["raw_text"] = raw_text_contains

        # If document_id or corpus_id provided, use the instance-based search
        # which respects corpus-specific embedders
        # Import here to avoid circular imports
        from opencontractserver.pipeline.utils import get_default_embedder_path

        if document_pk or corpus_pk:
            # Issue #437: Use corpus.preferred_embedder for corpus-scoped search
            # instead of the global default embedder. Each corpus has a frozen
            # embedder binding set at creation, and all annotations in the corpus
            # have embeddings for that embedder. This ensures consistent search
            # even if the default embedder changes after the corpus was created.
            # When no corpus_id is provided (document-only search), fall back to
            # the PipelineSettings default embedder.
            scoped_embedder_path = get_default_embedder_path()
            if corpus_pk:
                # Fetch the corpus's frozen embedder directly to avoid a
                # redundant DB lookup inside CoreAnnotationVectorStore.
                corpus_embedder = (
                    Corpus.objects.filter(pk=corpus_pk)
                    .values_list("preferred_embedder", flat=True)
                    .first()
                )
                if corpus_embedder:
                    scoped_embedder_path = corpus_embedder

            # Use instance-based CoreAnnotationVectorStore for scoped search
            # Permission already verified above
            vector_store = CoreAnnotationVectorStore(
                user_id=user.id,
                corpus_id=corpus_pk,
                document_id=document_pk,
                modalities=modalities,
                must_have_text=raw_text_contains,  # Additional text filter
                embedder_path=scoped_embedder_path,
            )

            from opencontractserver.llms.vector_stores.core_vector_stores import (
                VectorSearchQuery,
            )

            search_query = VectorSearchQuery(
                query_text=query_text,
                similarity_top_k=limit + offset,  # Fetch extra for pagination
                filters={"annotation_label": label_text} if label_text else None,
            )

            # Use hybrid search (vector + full-text with RRF fusion)
            # when a text query is provided. Skip the FTS overhead and use
            # vector-only search when query is purely an embedding lookup.
            if query_text and query_text.strip():
                results = vector_store.hybrid_search(search_query)
            else:
                results = vector_store.search(search_query)

            # Apply pagination
            paginated_results = results[offset : offset + limit]
        else:
            # Use global_search for cross-corpus search.
            # TODO: global_search uses vector-only search; it does not benefit
            # from hybrid (vector + FTS) search with RRF fusion. Adding FTS
            # integration here would improve result quality for text queries.
            # Then apply additional filters post-search.
            results = CoreAnnotationVectorStore.global_search(
                user_id=user.id,
                query_text=query_text,
                top_k=(limit + offset) * 3,  # Fetch more for post-filtering
                modalities=modalities,
            )

            # Apply hybrid text filters post-search
            if label_text or raw_text_contains:
                filtered_results = []
                for result in results:
                    annotation = result.annotation
                    # Check label_text filter
                    if label_text:
                        label = getattr(annotation.annotation_label, "text", None)
                        if not label or label_text.lower() not in label.lower():
                            continue
                    # Check raw_text filter
                    if raw_text_contains:
                        raw_text = annotation.raw_text or ""
                        if raw_text_contains.lower() not in raw_text.lower():
                            continue
                    filtered_results.append(result)
                results = filtered_results

            # Apply pagination
            paginated_results = results[offset : offset + limit]

        # Defensive select_related: Re-fetch annotations with explicit prefetching
        # to guard against changes in CoreAnnotationVectorStore implementation
        if paginated_results:
            annotation_ids = [r.annotation.id for r in paginated_results]
            annotations_by_id = {
                a.id: a
                for a in Annotation.objects.filter(
                    id__in=annotation_ids
                ).select_related("annotation_label", "document", "corpus")
            }
            # Update results with explicitly prefetched annotations
            for result in paginated_results:
                if result.annotation.id in annotations_by_id:
                    result.annotation = annotations_by_id[result.annotation.id]

        # Convert to GraphQL result types — surface the block-of-context
        # the core store attached after reranking. ``BlockContextType`` is
        # a plain GraphQL ObjectType (not a DjangoObjectType), so we
        # construct it from the dataclass fields directly. Keeping the
        # mapping inline mirrors ``SemanticSearchResultType``'s pattern
        # for ``annotation``/``similarity_score`` and avoids a helper
        # for a single non-shared call site.
        graphql_results = []
        for result in paginated_results:
            block_ctx = None
            if result.block_context is not None:
                bc = result.block_context
                block_ctx = BlockContextType(
                    relationship_id=bc.relationship_id,
                    source_annotation_id=bc.source_annotation_id,
                    source_text=bc.source_text,
                    target_annotation_ids=list(bc.target_annotation_ids),
                    block_text=bc.block_text,
                )
            graphql_results.append(
                SemanticSearchResultType(
                    annotation=result.annotation,
                    similarity_score=result.similarity_score,
                    block_context=block_ctx,
                )
            )
        return graphql_results

    # ------------------------------------------------------------------ #
    # Relationship-targeted semantic search
    # ------------------------------------------------------------------ #
    semantic_search_relationships = graphene.List(
        SemanticSearchRelationshipResultType,
        query=graphene.String(required=True, description="Search query text"),
        corpus_id=graphene.ID(
            required=False,
            description="Optional corpus ID to scope search within",
        ),
        document_id=graphene.ID(
            required=False,
            description="Optional document ID to scope search within",
        ),
        limit=graphene.Int(
            default_value=50,
            description=(
                f"Maximum number of results to return (default: 50, "
                f"max: {SEMANTIC_SEARCH_MAX_RESULTS})"
            ),
        ),
        offset=graphene.Int(
            default_value=0,
            description="Number of results to skip for pagination",
        ),
        description=(
            "Vector search across embedded Relationship rows — currently "
            "the materialised OC_SUBTREE_GROUP subtrees. Returns each "
            "relationship's source/target annotation IDs so the document "
            "viewer can scroll to and select the whole block in one go."
        ),
    )

    @login_required
    def resolve_semantic_search_relationships(
        self,
        info,
        query,
        corpus_id=None,
        document_id=None,
        limit=50,
        offset=0,
    ) -> Any:
        """Run vector search against the embedded Relationship surface.

        Mirrors ``resolve_semantic_search`` for scoping and permissioning
        but targets ``Relationship`` rows instead of annotations. The
        underlying store applies the same ``visible_to_user`` filters so
        IDOR rules are identical.
        """
        from opencontractserver.llms.vector_stores.core_relationship_vector_store import (  # noqa: E501
            CoreRelationshipVectorStore,
            RelationshipVectorSearchQuery,
        )
        from opencontractserver.pipeline.utils import get_default_embedder_path

        limit = min(limit, SEMANTIC_SEARCH_MAX_RESULTS)

        corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None
        document_pk = int(from_global_id(document_id)[1]) if document_id else None

        user = info.context.user

        # IDOR check: same pattern as ``resolve_semantic_search``. Returning
        # ``[]`` for both "not found" and "no permission" prevents
        # enumeration attacks via differing error messages.
        if document_pk:
            if (
                not BaseService.filter_visible(Document, user, request=info.context)
                .filter(id=document_pk)
                .exists()
            ):
                return []

        if corpus_pk:
            if (
                not BaseService.filter_visible(Corpus, user, request=info.context)
                .filter(id=corpus_pk)
                .exists()
            ):
                return []

        # Resolve embedder: corpus-scoped queries use the corpus's frozen
        # ``preferred_embedder`` so the query vector is in the same space
        # as the corpus's relationship embeddings. Same logic as the
        # annotation-targeted path above; kept inline so the two
        # resolvers can evolve independently if the relationship surface
        # ever picks a different embedder.
        scoped_embedder_path = get_default_embedder_path()
        if corpus_pk:
            corpus_embedder = (
                Corpus.objects.filter(pk=corpus_pk)
                .values_list("preferred_embedder", flat=True)
                .first()
            )
            if corpus_embedder:
                scoped_embedder_path = corpus_embedder

        store = CoreRelationshipVectorStore(
            user_id=user.id,
            corpus_id=corpus_pk,
            document_id=document_pk,
            embedder_path=scoped_embedder_path,
        )
        results = store.search(
            RelationshipVectorSearchQuery(
                query_text=query,
                similarity_top_k=limit + offset,
            )
        )
        paginated_results = results[offset : offset + limit]

        # Construct GraphQL types. ``document_id`` and ``corpus_id`` are
        # raw PKs (matching the type definition) so deep-link URLs can
        # round-trip them through ``to_global_id`` on the client side
        # without needing a second resolver.
        graphql_results: list[SemanticSearchRelationshipResultType] = []
        for r in paginated_results:
            graphql_results.append(
                SemanticSearchRelationshipResultType(
                    relationship_id=r.relationship.pk,
                    similarity_score=r.similarity_score,
                    label=r.label_text,
                    source_annotation_id=r.source_annotation_id,
                    target_annotation_ids=list(r.target_annotation_ids),
                    block_text=r.block_text,
                    document_id=r.document_id,
                    corpus_id=r.corpus_id,
                )
            )
        return graphql_results
