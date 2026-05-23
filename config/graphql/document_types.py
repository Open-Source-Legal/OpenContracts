"""GraphQL type definitions for document-related types."""

import logging
from typing import Any, Optional

import graphene
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from graphql_relay import from_global_id

from config.graphql.annotation_types import (
    AnnotationType,
    NoteType,
    RelationshipType,
)
from config.graphql.base import CountableConnection
from config.graphql.base_types import (
    CorpusVersionInfoType,
    DocumentProcessingStatusEnum,
    PathActionEnum,
    PathHistoryType,
    VersionHistoryType,
)
from config.graphql.custom_resolvers import resolve_doc_annotations_optimized
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.constants import MAX_PROCESSING_ERROR_DISPLAY_LENGTH
from opencontractserver.documents.models import (
    Document,
    DocumentAnalysisRow,
    DocumentPath,
    DocumentProcessingStatus,
    DocumentRelationship,
    DocumentSummaryRevision,
    IngestionSource,
    IngestionSourceCategory,
)

User = get_user_model()
logger = logging.getLogger(__name__)


# -------------------- Ingestion Source Types -------------------- #

INGESTION_SOURCE_GLOBAL_ID_TYPE = "IngestionSourceType"

IngestionSourceTypeEnum = graphene.Enum.from_enum(
    IngestionSourceCategory, name="IngestionSourceTypeEnum"
)


class IngestionSourceType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for IngestionSource - a named integration that produces documents."""

    config = GenericScalar(
        description=(
            "Source configuration (connection details, etc.). "
            "WARNING: This field is returned to the owning user verbatim. "
            "Store secret-manager key paths or references here, never raw "
            "credentials (API keys, tokens, passwords)."
        )
    )

    class Meta:
        model = IngestionSource
        interfaces = [relay.Node]
        connection_class = CountableConnection
        # Explicit allowlist: do NOT expose ``user_lock`` (leaks username of
        # the user holding the lock), ``backend_lock``, or ``is_public`` from
        # the BaseOCModel parent.  Keep the API surface limited to the
        # source's descriptive + lifecycle fields.
        fields = (
            "id",
            "name",
            "source_type",
            "config",
            "active",
            "created",
            "modified",
        )

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        """Only show sources owned by the current user, shared, or public."""
        return IngestionSource.objects.visible_to_user(info.context.user)


# -------------------- Document Path Types -------------------- #


class DocumentPathType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for DocumentPath model - represents filesystem lifecycle events."""

    action = graphene.Field(PathActionEnum, description="Inferred action type")
    ingestion_metadata = GenericScalar(
        description="Arbitrary source-specific metadata (URL, crawl job ID, etc.)"
    )

    def resolve_action(self, info) -> Any:
        """Infer action type from path state."""
        if self.is_deleted:
            return "DELETED"
        elif self.parent is None:
            return "IMPORTED"
        else:
            # Check if this is an update vs move
            if hasattr(self, "parent") and self.parent:
                if self.parent.path != self.path:
                    return "MOVED"
                elif self.parent.version_number != self.version_number:
                    return "UPDATED"
            return "UPDATED"

    class Meta:
        model = DocumentPath
        interfaces = [relay.Node]
        connection_class = CountableConnection

    _VISIBLE_CORPUS_IDS_CACHE_KEY = "_docpath_visible_corpus_ids"

    @classmethod
    def _get_visible_corpus_ids(cls, info) -> Any:
        """Get visible corpus IDs with request-level caching to prevent N+1 queries."""
        from opencontractserver.corpuses.models import Corpus

        user = info.context.user
        user_id = getattr(user, "id", "anonymous")
        cache_key = f"{cls._VISIBLE_CORPUS_IDS_CACHE_KEY}_{user_id}"

        if hasattr(info.context, cache_key):
            return getattr(info.context, cache_key)

        visible_ids = set(
            Corpus.objects.visible_to_user(user).values_list("id", flat=True)
        )
        setattr(info.context, cache_key, visible_ids)
        return visible_ids

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        """Filter paths to current, non-deleted paths in visible corpuses."""
        visible_corpus_ids = cls._get_visible_corpus_ids(info)

        if issubclass(type(queryset), QuerySet):
            return queryset.filter(
                corpus_id__in=visible_corpus_ids,
                is_current=True,
                is_deleted=False,
            )
        elif "RelatedManager" in str(type(queryset)):
            return queryset.all().filter(
                corpus_id__in=visible_corpus_ids,
                is_current=True,
                is_deleted=False,
            )
        else:
            return queryset


class DocumentRelationshipType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for DocumentRelationship model."""

    data = GenericScalar()

    class Meta:
        model = DocumentRelationship
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        # Check if permissions were already handled by the relationship service.
        # The service adds _can_read, _can_create, etc. annotations.
        if hasattr(queryset, "query") and queryset.query.annotations:
            if any(key.startswith("_can_") for key in queryset.query.annotations):
                return queryset

        # Fall back to service-based permission filtering.
        # DocumentRelationship uses inherited permissions (not PermissionManager),
        # so we delegate to DocumentRelationshipService which checks
        # visibility on source_document + target_document + corpus.
        from opencontractserver.documents.services import DocumentRelationshipService

        user = info.context.user
        return DocumentRelationshipService.get_visible_relationships(
            user, request=info.context
        )


class DocumentType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    # Import optimized resolvers for file fields
    from config.graphql.optimized_file_resolvers import (
        resolve_icon_optimized,
        resolve_md_summary_file_optimized,
        resolve_pawls_parse_file_optimized,
        resolve_pdf_file_optimized,
        resolve_txt_extract_file_optimized,
    )

    # Use optimized resolvers that minimize storage backend overhead
    resolve_pdf_file = resolve_pdf_file_optimized
    resolve_icon = resolve_icon_optimized
    resolve_txt_extract_file = resolve_txt_extract_file_optimized
    resolve_md_summary_file = resolve_md_summary_file_optimized
    resolve_pawls_parse_file = resolve_pawls_parse_file_optimized
    resolve_doc_annotations = resolve_doc_annotations_optimized

    def _assert_user_can_read(self, info):
        """
        Raise ``GraphQLError`` if the requesting user cannot READ this document.
        Returns the resolved user for caller convenience (so callers don't have
        to re-extract it from ``info.context``).

        Uses the canonical ``Document.objects.visible_to_user(user)`` manager
        method so corpus-inherited and group permissions are honoured. Public
        documents short-circuit with no DB hit so high-traffic public reads are
        not penalised.
        """
        user = info.context.user if hasattr(info.context, "user") else None
        if self.is_public:
            return user
        # Short-circuit anonymous callers before hitting the DB. For
        # ``AnonymousUser`` the manager collapses to ``is_public=True``, so the
        # ``.exists()`` lookup below would always be False here — skip it to
        # preserve the old ordering and avoid an unnecessary round-trip.
        if not user or not getattr(user, "is_authenticated", False):
            raise GraphQLError(
                "Permission denied: Authentication required to access private documents"
            )
        if Document.objects.visible_to_user(user).filter(id=self.id).exists():
            return user
        raise GraphQLError("Permission denied: You do not have access to this document")

    all_structural_annotations = graphene.List(
        AnnotationType,
        annotation_ids=graphene.List(graphene.NonNull(graphene.ID)),
    )

    def resolve_all_structural_annotations(self, info, annotation_ids=None) -> Any:
        from opencontractserver.annotations.services import AnnotationService

        qs = AnnotationService.get_document_annotations(
            document_id=self.id,
            user=getattr(info.context, "user", None),
            structural=True,
        )
        if annotation_ids:
            django_pks = [from_global_id(gid)[1] for gid in annotation_ids]
            qs = qs.filter(pk__in=django_pks)
        return qs

    # Updated field and resolver for all annotations with enhanced filtering
    all_annotations = graphene.List(
        AnnotationType,
        corpus_id=graphene.ID(),
        analysis_id=graphene.ID(),
        is_structural=graphene.Boolean(),
    )

    def resolve_all_annotations(
        self, info, corpus_id=None, analysis_id=None, is_structural=None
    ) -> Any:
        from opencontractserver.annotations.services import AnnotationService

        user = getattr(info.context, "user", None)
        corpus_pk: int | None = int(from_global_id(corpus_id)[1]) if corpus_id else None
        analysis_pk: int | None = None
        if analysis_id:
            analysis_pk = (
                0 if analysis_id == "__none__" else int(from_global_id(analysis_id)[1])
            )
        return AnnotationService.get_document_annotations(
            document_id=self.id,
            user=user,
            corpus_id=corpus_pk,
            analysis_id=analysis_pk,
            structural=is_structural,
            context=info.context,
        )

    # New field and resolver for all relationships
    all_relationships = graphene.List(
        RelationshipType,
        corpus_id=graphene.ID(),
        analysis_id=graphene.ID(),
        is_structural=graphene.Boolean(),
    )

    def resolve_all_relationships(
        self, info, corpus_id=None, analysis_id=None, is_structural=None
    ) -> Any:
        """Resolve all relationships using the optimizer."""
        from opencontractserver.annotations.services import RelationshipService

        try:
            corpus_pk: int | None = None
            analysis_pk: int | None = None

            if corpus_id:
                corpus_pk = int(from_global_id(corpus_id)[1])
            if analysis_id and analysis_id != "__none__":
                analysis_pk = int(from_global_id(analysis_id)[1])
            elif analysis_id == "__none__":
                analysis_pk = 0  # Special case for user relationships

            # Get user from context
            user = info.context.user if hasattr(info.context, "user") else None

            return RelationshipService.get_document_relationships(
                document_id=self.id,
                user=user,
                corpus_id=corpus_pk,
                analysis_id=analysis_pk,
                structural=is_structural,
                context=info.context,
            )
        except Exception as e:
            logger.warning(
                f"Failed resolving relationships query for document {self.id} with input: corpus_id={corpus_id}, "
                f"analysis_id={analysis_id}. Error: {e}"
            )
            return []

    all_structural_relationships = graphene.List(
        RelationshipType,
        relationship_ids=graphene.List(graphene.NonNull(graphene.ID)),
    )

    def resolve_all_structural_relationships(self, info, relationship_ids=None) -> Any:
        """
        Resolve structural relationships for this document.

        Mirrors ``all_structural_annotations``: returns the document's
        shared structural relationships (corpus-independent), so the
        frontend can lazy-load them alongside structural annotations
        instead of hauling them down on every initial document open.
        """
        from opencontractserver.annotations.services import RelationshipService

        try:
            user = getattr(info.context, "user", None)
            # Bulk structural-toggle fetches reuse the per-request cache;
            # targeted deep-link fetches (relationship_ids supplied) bypass
            # it because the cached queryset is shaped for the bulk path
            # and would mask the id-filter we apply below.
            qs = RelationshipService.get_document_relationships(
                document_id=self.id,
                user=user,
                structural=True,
                context=info.context,
            )
            if relationship_ids:
                django_pks = [from_global_id(gid)[1] for gid in relationship_ids]
                qs = qs.filter(pk__in=django_pks)
            return qs
        except Exception as e:
            logger.warning(
                "Failed resolving structural relationships query for "
                f"document {self.id}. Error: {e}"
            )
            return []

    # New field for document relationships
    all_doc_relationships = graphene.List(
        DocumentRelationshipType,
        corpus_id=graphene.String(),
    )

    # Relationship count field for efficient badge display
    doc_relationship_count = graphene.Int(
        corpus_id=graphene.String(),
        description="Count of document relationships for this document in the given corpus",
    )

    def resolve_doc_relationship_count(self, info, corpus_id=None) -> Any:
        """
        Return the count of document relationships for this document.

        Performance: uses ``get_relationship_counts_by_document`` so the first
        call computes counts for every document the user can see (optionally
        scoped to ``corpus_id``) in two aggregated SQL queries, caching the
        result on ``info.context``. Subsequent resolvers in the same GraphQL
        request resolve in O(1) — eliminating the N+1 ``.count()`` storm that
        occurred when this field was requested for hundreds of documents.

        Note: the document was already filtered through ``visible_to_user`` by
        the parent resolver, so per-document permission re-checks aren't
        required here — visibility is enforced at the relationship level by
        the optimizer's source/target/corpus filters.
        """
        from opencontractserver.documents.services import DocumentRelationshipService

        try:
            user = info.context.user
            corpus_pk = int(from_global_id(corpus_id)[1]) if corpus_id else None

            counts = DocumentRelationshipService.get_relationship_counts_by_document(
                user=user,
                corpus_id=corpus_pk,
                request=info.context,
            )
            return counts.get(self.id, 0)
        except Exception as e:
            logger.warning(
                f"Failed resolving doc_relationship_count for document {self.id}. "
                f"Error: {e}"
            )
            return 0

    def resolve_all_doc_relationships(self, info, corpus_id=None) -> Any:
        """
        Resolve DocumentRelationship objects for this document.

        Uses DocumentRelationshipService for proper permission filtering.
        DocumentRelationship inherits visibility from source_document,
        target_document, and corpus — its own guardian tables were dropped in
        migration ``documents/0029``. The service enforces the AND-of-all-three
        rule (see ``DocumentRelationshipService.get_visible_relationships``).

        Performance: Passes info.context to the service for request-level
        caching of visible document/corpus IDs.
        """
        from opencontractserver.documents.services import DocumentRelationshipService

        try:
            user = info.context.user
            corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None

            # Use the relationship service for proper permission filtering
            # Pass info.context for request-level caching
            return DocumentRelationshipService.get_relationships_for_document(
                user=user,
                document_id=self.id,
                corpus_id=int(corpus_pk) if corpus_pk else None,
                request=info.context,
            )
        except Exception as e:
            logger.warning(
                "Failed resolving document relationships query for "
                f"document {self.id} with input: corpus_id={corpus_id}. "
                f"Error: {e}"
            )
            return []

    all_notes = graphene.List(
        NoteType,
        corpus_id=graphene.ID(),
    )

    def resolve_all_notes(self, info, corpus_id: Optional[str] = None) -> Any:
        """
        Return the set of Note objects related to this Document instance that the user can see,
        filtered by corpus_id.
        """
        from opencontractserver.annotations.models import Note

        user = info.context.user

        # Start with a base queryset of all Notes the user can see
        base_qs = Note.objects.visible_to_user(user=user)

        if corpus_id is None:
            corpus_pk = None
            return base_qs.filter(document=self)

        else:
            corpus_pk = from_global_id(corpus_id)[1]
            # Then intersect with this Document's related notes, filtering by the given corpus_id
            # This ensures we only query notes that are both visible to the user and belong to
            # this specific Document (through the related manager self.notes).
            return base_qs.filter(document=self, corpus_id=corpus_pk)

    # Summary version history (corpus-specific)
    summary_revisions = graphene.List(
        lambda: DocumentSummaryRevisionType,
        corpus_id=graphene.ID(required=True),
        description="List of all summary revisions/versions for a specific corpus, ordered by version.",
    )
    current_summary_version = graphene.Int(
        corpus_id=graphene.ID(required=True),
        description="Current version number of the summary for a specific corpus",
    )
    summary_content = graphene.String(
        corpus_id=graphene.ID(required=True),
        description="Current summary content for a specific corpus",
    )

    def resolve_summary_revisions(self, info, corpus_id) -> Any:
        """Returns all revisions for this document's summary in a specific corpus, ordered by version."""
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import DocumentSummaryRevision

        _, corpus_pk = from_global_id(corpus_id)
        # Verify user can access the corpus before returning summary data
        if (
            not Corpus.objects.visible_to_user(info.context.user)
            .filter(pk=corpus_pk)
            .exists()
        ):
            return DocumentSummaryRevision.objects.none()
        return DocumentSummaryRevision.objects.filter(
            document_id=self.pk, corpus_id=corpus_pk
        ).order_by("version")

    def resolve_current_summary_version(self, info, corpus_id) -> Any:
        """Returns the current summary version number for a specific corpus."""
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import DocumentSummaryRevision

        _, corpus_pk = from_global_id(corpus_id)
        # Verify user can access the corpus before returning version data
        if (
            not Corpus.objects.visible_to_user(info.context.user)
            .filter(pk=corpus_pk)
            .exists()
        ):
            return 0
        latest_revision = (
            DocumentSummaryRevision.objects.filter(
                document_id=self.pk, corpus_id=corpus_pk
            )
            .order_by("-version")
            .first()
        )

        return latest_revision.version if latest_revision else 0

    def resolve_summary_content(self, info, corpus_id) -> Any:
        """Returns the current summary content for a specific corpus."""
        from opencontractserver.corpuses.models import Corpus

        _, corpus_pk = from_global_id(corpus_id)
        try:
            # Use visible_to_user() to prevent cross-corpus data leakage
            corpus = Corpus.objects.visible_to_user(info.context.user).get(pk=corpus_pk)
            return self.get_summary_for_corpus(corpus)
        except Corpus.DoesNotExist:
            return ""

    # -------------------- Version Metadata Fields (Phase 1.1) -------------------- #
    # These are lightweight fields that are always loaded with documents

    version_number = graphene.Int(
        corpus_id=graphene.ID(required=True),
        description="Content version number in this corpus (from DocumentPath)",
    )
    has_version_history = graphene.Boolean(
        description="True if this document has multiple versions (parent exists)"
    )
    version_count = graphene.Int(
        description="Total number of versions in this document's version tree"
    )
    is_latest_version = graphene.Boolean(
        description="True if this is the current version (Document.is_current)"
    )
    last_modified = graphene.DateTime(
        corpus_id=graphene.ID(required=True),
        description="When the document was last modified in this corpus",
    )

    # Lazy-loaded version history fields
    version_history = graphene.Field(
        VersionHistoryType,
        description="Complete version history (lazy-loaded on request)",
    )
    path_history = graphene.Field(
        PathHistoryType,
        corpus_id=graphene.ID(required=True),
        description="Path/location history in corpus (lazy-loaded on request)",
    )

    # Corpus-specific version list for version selector UI
    corpus_versions = graphene.List(
        graphene.NonNull(CorpusVersionInfoType),
        corpus_id=graphene.ID(required=True),
        description=(
            "All versions of this document in a specific corpus. "
            "Used by the version selector UI to show available versions."
        ),
    )

    # Permission helpers for versioning features
    can_restore = graphene.Boolean(
        corpus_id=graphene.ID(required=True),
        description="Whether user can restore this document (requires UPDATE permission)",
    )
    can_view_history = graphene.Boolean(
        description="Whether user can view version history (requires READ permission)"
    )

    def resolve_version_number(self, info, corpus_id) -> Any:
        """Get version number from DocumentPath for this corpus."""
        _, corpus_pk = from_global_id(corpus_id)
        try:
            path_record = DocumentPath.objects.filter(
                document_id=self.id, corpus_id=corpus_pk, is_current=True
            ).first()
            return path_record.version_number if path_record else 1
        except Exception:
            return 1

    def resolve_has_version_history(self, info) -> Any:
        """Check if document has parent (i.e., multiple versions exist)."""
        return self.parent is not None

    def resolve_version_count(self, info) -> Any:
        """
        Return the count of visible documents sharing this version tree.

        Performance: uses ``DocumentVersionService.get_version_counts_by_tree``
        so the first call computes counts for every version tree the user can
        see in a single aggregated SQL query, caching the result on
        ``info.context``. Subsequent resolvers in the same GraphQL request
        resolve in O(1) — eliminating the N+1 ``.count()`` storm that occurred
        when this field was requested for a paginated documents connection.

        Security: the aggregation is scoped to ``visible_to_user`` so the
        badge cannot leak the existence of versions hidden from this user.
        Falls back to 1 because the resolver is only reachable on a document
        the user can already see (the parent resolver applies the same
        visibility filter).
        """
        from opencontractserver.documents.services import DocumentVersionService

        try:
            counts = DocumentVersionService.get_version_counts_by_tree(
                user=info.context.user,
                request=info.context,
            )
            return counts.get(self.version_tree_id, 1)
        except Exception as e:
            logger.warning(
                f"Failed resolving version_count for document {self.id}. Error: {e}"
            )
            return 1

    def resolve_is_latest_version(self, info) -> Any:
        """Check if this is the current version."""
        return self.is_current

    def resolve_last_modified(self, info, corpus_id) -> Any:
        """Get last modification time from DocumentPath."""
        _, corpus_pk = from_global_id(corpus_id)
        try:
            path_record = DocumentPath.objects.filter(
                document_id=self.id, corpus_id=corpus_pk, is_current=True
            ).first()
            return path_record.created if path_record else self.modified
        except Exception:
            return self.modified

    def resolve_version_history(self, info) -> Any:
        """
        Lazy-load complete version history.
        Returns all versions in the document's version tree.
        """
        from graphql_relay import to_global_id

        # Get all documents in the version tree, ordered by creation
        versions = Document.objects.filter(
            version_tree_id=self.version_tree_id
        ).order_by("created")

        version_list = []
        for idx, doc in enumerate(versions, start=1):
            # Determine change type
            if doc.parent is None:
                change_type = "INITIAL"
            else:
                # Could be enhanced to detect minor vs major changes
                change_type = "CONTENT_UPDATE"

            version_data = {
                "id": to_global_id("DocumentType", doc.id),
                "version_number": idx,
                "hash": doc.pdf_file_hash or "",
                "created_at": doc.created,
                "created_by": doc.creator,
                "size_bytes": doc.pdf_file.size if doc.pdf_file else None,
                "change_type": change_type,
                "parent_version": None,  # Could be resolved if needed
            }
            version_list.append(version_data)

        # Find current version
        current = next(
            (
                v
                for v in version_list
                if v["id"] == to_global_id("DocumentType", self.id)
            ),
            version_list[-1] if version_list else None,
        )

        return {
            "versions": version_list,
            "current_version": current,
            "version_tree": None,  # Could build tree structure if needed
        }

    def resolve_path_history(self, info, corpus_id) -> Any:
        """
        Lazy-load path history for this document in a corpus.
        Returns all lifecycle events (import, move, delete, restore).
        """
        from graphql_relay import to_global_id

        _, corpus_pk = from_global_id(corpus_id)

        # Get all path records for this document in this corpus
        path_records = DocumentPath.objects.filter(
            document__version_tree_id=self.version_tree_id, corpus_id=corpus_pk
        ).order_by("created")

        events = []
        original_path = None
        current_path = None
        move_count = 0

        for path_record in path_records:
            # Infer action type
            if path_record.is_deleted:
                action = "DELETED"
            elif path_record.parent is None:
                action = "IMPORTED"
                original_path = path_record.path
            else:
                # Check if path changed vs version changed
                if hasattr(path_record, "parent") and path_record.parent:
                    if path_record.parent.path != path_record.path:
                        action = "MOVED"
                        move_count += 1
                    elif (
                        path_record.parent.version_number != path_record.version_number
                    ):
                        action = "UPDATED"
                    else:
                        action = "RESTORED"
                else:
                    action = "UPDATED"

            if path_record.is_current and not path_record.is_deleted:
                current_path = path_record.path

            event = {
                "id": to_global_id("DocumentPathType", path_record.id),
                "action": action,
                "path": path_record.path,
                "folder": path_record.folder,
                "timestamp": path_record.created,
                "user": path_record.creator,
                "version_number": path_record.version_number,
            }
            events.append(event)

        return {
            "events": events,
            "current_path": current_path or original_path or "",
            "original_path": original_path or "",
            "move_count": move_count,
        }

    def resolve_corpus_versions(self, info, corpus_id) -> Any:
        """Return all versions of this document in a specific corpus.

        Uses DocumentPath records to find all versions, ordered by version_number.
        Each entry maps to a specific Document record, enabling the frontend
        to navigate to historical versions via the ?v=N URL parameter.

        Only returns versions whose underlying Document the requesting user
        has permission to see (via visible_to_user), preventing information
        disclosure of historical version metadata the user shouldn't access.

        Performance: Uses a DB-level subquery (document__in) to push
        permission filtering into a single query instead of materializing
        visible IDs in Python then filtering. Results are cached on the
        request context so that listing N documents with corpusVersions
        in one query reuses the same result for documents sharing a
        version_tree_id + corpus_id pair (avoids N+1).
        """
        from graphql_relay import to_global_id

        type_name, corpus_pk = from_global_id(corpus_id)
        if not type_name or type_name != "CorpusType":
            return []

        # Request-level cache keyed on (version_tree_id, corpus_pk).
        cache_key = (self.version_tree_id, corpus_pk)
        cache = getattr(info.context, "_corpus_versions_cache", None)
        if cache is None:
            cache = {}
            info.context._corpus_versions_cache = cache
        if cache_key in cache:
            return cache[cache_key]

        # Subquery: only documents in this version tree the user can see.
        visible_version_docs = (
            Document.objects.visible_to_user(info.context.user)
            .filter(version_tree_id=self.version_tree_id)
            .only("pk")
        )

        # delete_document() creates a tombstone (is_current=True, is_deleted=True)
        # but leaves the previous path record with is_deleted=False.
        # Exclude version_numbers that have a deleted current path.
        deleted_version_numbers = DocumentPath.objects.filter(
            corpus_id=corpus_pk,
            document__version_tree_id=self.version_tree_id,
            is_current=True,
            is_deleted=True,
        ).values("version_number")

        # Non-deleted paths whose document passes visibility,
        # excluding versions that are soft-deleted via tombstone.
        # select_related("document") is needed only for slug access.
        path_records = (
            DocumentPath.objects.filter(
                document__in=visible_version_docs,
                corpus_id=corpus_pk,
                is_deleted=False,
            )
            .exclude(version_number__in=deleted_version_numbers)
            .select_related("document")
            .order_by("version_number", "-created")
        )

        # Deduplicate by version_number (keep first = most recent due to -created).
        seen_versions = set()
        results = []
        for path_record in path_records:
            if path_record.version_number in seen_versions:
                continue
            seen_versions.add(path_record.version_number)
            results.append(
                {
                    "version_number": path_record.version_number,
                    "document_id": to_global_id(
                        "DocumentType", path_record.document_id
                    ),
                    "document_slug": path_record.document.slug,
                    "created": path_record.created,
                    "is_current": path_record.is_current,
                }
            )

        cache[cache_key] = results
        return results

    def resolve_can_restore(self, info, corpus_id) -> Any:
        """Check if user has UPDATE permission for restore operations."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes

        user = info.context.user
        if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
            return False

        # Check document permission
        has_doc_update = self.user_can(
            user, PermissionTypes.UPDATE, request=info.context
        )
        if not has_doc_update:
            return False

        # Check corpus permission
        _, corpus_pk = from_global_id(corpus_id)
        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
            return corpus.user_can(user, PermissionTypes.UPDATE, request=info.context)
        except Corpus.DoesNotExist:
            return False

    def resolve_can_view_history(self, info) -> Any:
        """Check if user has READ permission for viewing history."""
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.types.enums import PermissionTypes

        user = info.context.user

        # Public documents can be viewed by anyone
        if self.is_public:
            return True

        if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
            return False

        return self.user_can(user, PermissionTypes.READ, request=info.context)

    # -------------------- Processing Status Fields (Pipeline Hardening) -------------------- #
    processing_status = graphene.Field(
        DocumentProcessingStatusEnum,
        description="Current processing status of the document in the parsing pipeline",
    )
    processing_error = graphene.String(
        description="Error message if processing failed (truncated for display)",
    )
    can_retry = graphene.Boolean(
        description="Whether the user can retry processing for this document (True if FAILED and user has permission)",
    )

    def resolve_processing_status(self, info) -> Any:
        """Resolve the processing status enum value."""
        status_value = self.processing_status
        if status_value:
            try:
                return DocumentProcessingStatusEnum.get(status_value)
            except Exception:
                return None
        return None

    def resolve_processing_error(self, info) -> Any:
        """Resolve processing error message (truncated for display)."""
        if self.processing_error:
            return self.processing_error[:MAX_PROCESSING_ERROR_DISPLAY_LENGTH]
        return None

    def resolve_can_retry(self, info) -> Any:
        """
        Check if user can retry processing for this document.

        Returns True only if:
        1. Document is in FAILED state
        2. User has UPDATE permission (or is creator/superuser)

        Note: This logic must stay aligned with RetryDocumentProcessing mutation.
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.types.enums import PermissionTypes

        # Must be in failed state to retry
        if self.processing_status != DocumentProcessingStatus.FAILED:
            return False

        user = info.context.user
        if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
            return False

        # Creator and superuser can always retry their documents
        if self.creator == user or user.is_superuser:
            return True

        # Others need UPDATE permission
        return self.user_can(user, PermissionTypes.UPDATE, request=info.context)

    page_annotations = graphene.List(
        AnnotationType,
        corpus_id=graphene.ID(required=True),
        page=graphene.Int(),  # Now optional for backwards compatibility
        pages=graphene.List(graphene.Int),  # NEW: Accept multiple pages
        structural=graphene.Boolean(),
        analysis_id=graphene.ID(),
        description="Get annots for spec. page(s) using opt. queries. Either 'page' (single) or 'pages' (multiple).",
    )

    page_relationships = graphene.List(
        RelationshipType,
        corpus_id=graphene.ID(required=True),
        pages=graphene.List(graphene.Int, required=True),
        structural=graphene.Boolean(),
        analysis_id=graphene.ID(),
        description="Get relationships where source or target annotations are on the specified page(s).",
    )

    def resolve_page_annotations(
        self,
        info,
        corpus_id,
        page=None,
        pages=None,
        structural=None,
        analysis_id=None,
        extract_id=None,
    ) -> Any:
        """Resolve annotations for specific page(s) using optimized queries."""
        from opencontractserver.annotations.services import AnnotationService

        corpus_pk = int(from_global_id(corpus_id)[1])
        analysis_pk: int | None = None
        if analysis_id:
            analysis_pk = int(from_global_id(analysis_id)[1])
        extract_pk: int | None = None
        if extract_id:
            extract_pk = int(from_global_id(extract_id)[1])

        user = self._assert_user_can_read(info)

        # Handle both single page and multiple pages
        # Priority: if 'pages' is provided, use it; otherwise fall back to 'page'
        page_list = None
        if pages is not None and len(pages) > 0:
            page_list = pages
        elif page is not None:
            page_list = [page]

        # If neither is provided, return empty list (maintain backwards compatibility)
        if page_list is None:
            return []

        return AnnotationService.get_document_annotations(
            document_id=self.id,
            user=user,
            corpus_id=corpus_pk,
            pages=page_list,  # Pass list of pages
            structural=structural,
            analysis_id=analysis_pk,
            extract_id=extract_pk,
        )

    def resolve_page_relationships(
        self,
        info,
        corpus_id,
        pages,
        structural=None,
        analysis_id=None,
        extract_id=None,
        strict_extract_mode=False,
    ) -> Any:
        """Resolve relationships for specific page(s) using the optimizer."""
        from opencontractserver.annotations.services import RelationshipService

        corpus_pk = int(from_global_id(corpus_id)[1])
        analysis_pk: int | None = None
        if analysis_id:
            if analysis_id == "__none__":
                analysis_pk = 0  # Special case for user annotations
            else:
                analysis_pk = int(from_global_id(analysis_id)[1])
        extract_pk: int | None = None
        if extract_id:
            extract_pk = int(from_global_id(extract_id)[1])

        user = self._assert_user_can_read(info)

        return RelationshipService.get_document_relationships(
            document_id=self.id,
            user=user,
            corpus_id=corpus_pk,
            pages=pages if pages else None,
            structural=structural,
            analysis_id=analysis_pk,
            extract_id=extract_pk,
            strict_extract_mode=strict_extract_mode,
        )

    relationship_summary = graphene.Field(
        GenericScalar,
        corpus_id=graphene.ID(required=True),
        description="Get relationship summary statistics for this document and corpus (MV-backed).",
    )

    # Extract-specific summary
    extract_annotation_summary = graphene.Field(
        GenericScalar,
        extract_id=graphene.ID(required=True),
        description="Get summary of annotations used in specific extract.",
    )

    def resolve_relationship_summary(self, info, corpus_id) -> Any:
        from opencontractserver.annotations.services import RelationshipService

        user = self._assert_user_can_read(info)

        corpus_pk = int(from_global_id(corpus_id)[1])
        summary = RelationshipService.get_relationship_summary(
            document_id=self.id, corpus_id=corpus_pk, user=user
        )
        return summary

    def resolve_extract_annotation_summary(self, info, extract_id) -> Any:
        """Get summary of annotations in extract."""
        from opencontractserver.annotations.services import AnnotationService

        user = self._assert_user_can_read(info)
        extract_pk = int(from_global_id(extract_id)[1])

        return AnnotationService.get_extract_annotation_summary(
            document_id=self.id, extract_id=extract_pk, user=user
        )

    # Folder assignment within a corpus
    folder_in_corpus = graphene.Field(
        lambda: _get_corpus_folder_type(),
        corpus_id=graphene.ID(required=True),
        description="Get the folder this document is in within a specific corpus (null = root)",
    )

    def resolve_folder_in_corpus(self, info, corpus_id) -> Any:
        """
        Get folder assignment for this document in a specific corpus.

        Delegates to FolderDocumentService.get_document_folder() for
        permission checking and dual-system consistency.
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.corpuses.services import FolderDocumentService

        _, corpus_pk = from_global_id(corpus_id)
        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
            return FolderDocumentService.get_document_folder(
                user=info.context.user,
                document=self,
                corpus=corpus,
                request=info.context,
            )
        except Corpus.DoesNotExist:
            return None

    class Meta:
        model = Document
        interfaces = [relay.Node]
        exclude = ("embedding",)
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        if issubclass(type(queryset), QuerySet):
            return queryset.visible_to_user(info.context.user)
        elif "RelatedManager" in str(type(queryset)):
            # https://stackoverflow.com/questions/11320702/import-relatedmanager-from-django-db-models-fields-related
            return queryset.all().visible_to_user(info.context.user)
        else:
            return queryset


# Explicit Connection class for DocumentType to use in relay.ConnectionField
class DocumentTypeConnection(CountableConnection):
    """Connection class for DocumentType used in Corpus.documents field."""

    class Meta:
        node = DocumentType


class DocumentStatsType(graphene.ObjectType):
    """Permission-scoped aggregate counts for the Documents view tile counters."""

    total_docs = graphene.Int(required=True)
    total_pages = graphene.Int(required=True)
    processed_count = graphene.Int(required=True)
    processing_count = graphene.Int(required=True)


class DocumentAnalysisRowType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    class Meta:
        model = DocumentAnalysisRow
        interfaces = [relay.Node]
        connection_class = CountableConnection


class DocumentCorpusActionsType(graphene.ObjectType):
    corpus_actions = graphene.List(lambda: _get_corpus_action_type())
    extracts = graphene.List(lambda: _get_extract_type())
    analysis_rows = graphene.List(DocumentAnalysisRowType)


class DocumentSummaryRevisionType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """GraphQL type for document summary revisions."""

    class Meta:
        model = DocumentSummaryRevision
        interfaces = [relay.Node]
        connection_class = CountableConnection


def _get_corpus_folder_type() -> Any:
    from config.graphql.corpus_types import CorpusFolderType

    return CorpusFolderType


def _get_corpus_action_type() -> Any:
    from config.graphql.agent_types import CorpusActionType

    return CorpusActionType


def _get_extract_type() -> Any:
    from config.graphql.extract_types import ExtractType

    return ExtractType
