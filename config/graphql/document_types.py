"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Annotated, Any

import strawberry
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from graphql import GraphQLError
from graphql_relay import from_global_id

from config.graphql import enums
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.relay import (
    Node,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_visible_fk,
)
from config.graphql.core.scalars import GenericScalar, JSONString
from config.graphql.custom_resolvers import resolve_doc_annotations_optimized
from config.graphql.filters import AnnotationFilter
from config.graphql.optimized_file_resolvers import (
    resolve_icon_optimized,
    resolve_md_summary_file_optimized,
    resolve_pawls_parse_file_optimized,
    resolve_pdf_file_optimized,
    resolve_txt_extract_file_optimized,
)
from opencontractserver.agents.models import AgentActionResult
from opencontractserver.constants import MAX_PROCESSING_ERROR_DISPLAY_LENGTH
from opencontractserver.corpuses.models import CorpusActionExecution
from opencontractserver.documents.models import (
    Document,
    DocumentAnalysisRow,
    DocumentPath,
    DocumentProcessingStatus,
    DocumentRelationship,
    DocumentSummaryRevision,
    IngestionSource,
)
from opencontractserver.shared.services.base import BaseService

User = get_user_model()
logger = logging.getLogger(__name__)


def _current_path_for_corpus(document, info, corpus_pk):
    """Return ``document``'s current ``DocumentPath`` in a corpus, request-cached.

    ``version_number`` and ``last_modified`` both read the same current
    ``DocumentPath`` row. Without caching, requesting both on a paginated
    documents connection fired 2N queries. This resolves to one query per
    ``(document, corpus)`` on first access and O(1) thereafter (cached on
    ``info.context`` for the life of the request), collapsing the pair to a
    single shared lookup and deduplicating repeats.

    Defined at module level (not as a ``DocumentType`` method) because
    graphene-django invokes resolvers with the Django **model instance** as
    ``self``; a helper method on the ObjectType would not be reachable via
    ``self`` from inside a resolver.
    """
    cache = getattr(info.context, "_current_doc_path_cache", None)
    if cache is None:
        cache = {}
        info.context._current_doc_path_cache = cache
    key = (document.id, str(corpus_pk))
    if key not in cache:
        cache[key] = (
            DocumentPath.objects.filter(
                document_id=document.id, corpus_id=corpus_pk, is_current=True
            )
            .order_by("-created")
            .first()
        )
    return cache[key]


def _dedupe_doc_type_labels(annotations: Any) -> list[Any]:
    # A document can carry multiple DOC_TYPE_LABEL annotations sharing the same
    # label; the badge UI shows each label once, so dedupe by label pk.
    seen: set[int] = set()
    labels: list[Any] = []
    for ann in annotations:
        label = ann.annotation_label
        if label is None or label.pk in seen:
            continue
        seen.add(label.pk)
        labels.append(label)
    return labels


# -------------------- Ingestion Source Types -------------------- #

INGESTION_SOURCE_GLOBAL_ID_TYPE = "IngestionSourceType"


def _assert_user_can_read(document, info):
    """
    Raise ``GraphQLError`` if the requesting user cannot READ this document.
    Returns the resolved user for caller convenience (so callers don't have
    to re-extract it from ``info.context``).

    Routes through the service layer (``BaseService.filter_visible``) so
    the underlying corpus-inherited and group permission rules are
    honoured. Public documents short-circuit with no DB hit so
    high-traffic public reads are not penalised.
    """
    user = info.context.user if hasattr(info.context, "user") else None
    if document.is_public:
        return user
    # Short-circuit anonymous callers before hitting the DB. For
    # ``AnonymousUser`` the manager collapses to ``is_public=True``, so the
    # ``.exists()`` lookup below would always be False here — skip it to
    # preserve the old ordering and avoid an unnecessary round-trip.
    if not user or not getattr(user, "is_authenticated", False):
        raise GraphQLError(
            "Permission denied: Authentication required to access private documents"
        )
    if (
        BaseService.filter_visible(Document, user, request=info.context)
        .filter(id=document.id)
        .exists()
    ):
        return user
    raise GraphQLError("Permission denied: You do not have access to this document")


_VISIBLE_CORPUS_IDS_CACHE_KEY = "_docpath_visible_corpus_ids"


def _docpath_visible_corpus_ids(info) -> Any:
    """Get visible corpus IDs with request-level caching to prevent N+1 queries."""
    from opencontractserver.corpuses.models import Corpus

    user = info.context.user
    user_id = getattr(user, "id", "anonymous")
    cache_key = f"{_VISIBLE_CORPUS_IDS_CACHE_KEY}_{user_id}"

    if hasattr(info.context, cache_key):
        return getattr(info.context, cache_key)

    visible_ids = set(
        BaseService.filter_visible(Corpus, user, request=info.context).values_list(
            "id", flat=True
        )
    )
    setattr(info.context, cache_key, visible_ids)
    return visible_ids


def _resolve_DocumentType_icon(root, info):
    """Port of DocumentType.resolve_icon (optimized file resolver)."""
    return resolve_icon_optimized(root, info)


def _resolve_DocumentType_pdf_file(root, info):
    """Port of DocumentType.resolve_pdf_file (optimized file resolver)."""
    return resolve_pdf_file_optimized(root, info)


def _resolve_DocumentType_txt_extract_file(root, info):
    """Port of DocumentType.resolve_txt_extract_file (optimized file resolver)."""
    return resolve_txt_extract_file_optimized(root, info)


def _resolve_DocumentType_md_summary_file(root, info):
    """Port of DocumentType.resolve_md_summary_file (optimized file resolver)."""
    return resolve_md_summary_file_optimized(root, info)


def _resolve_DocumentType_pawls_parse_file(root, info):
    """Port of DocumentType.resolve_pawls_parse_file (optimized file resolver)."""
    return resolve_pawls_parse_file_optimized(root, info)


def _resolve_DocumentType_processing_status(root, info):
    """Resolve the processing status enum value."""
    status_value = root.processing_status
    if status_value:
        try:
            return enums.DocumentProcessingStatusEnum(status_value)
        except Exception:
            return None
    return None


def _resolve_DocumentType_processing_error(root, info):
    """Resolve processing error message (truncated for display)."""
    if root.processing_error:
        return root.processing_error[:MAX_PROCESSING_ERROR_DISPLAY_LENGTH]
    return None


def _resolve_DocumentType_summary_revisions(root, info, corpus_id):
    """Returns all revisions for this document's summary in a specific corpus, ordered by version."""
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import DocumentSummaryRevision

    _, corpus_pk = from_global_id(corpus_id)
    # Verify user can access the corpus before returning summary data.
    if (
        not BaseService.filter_visible(Corpus, info.context.user, request=info.context)
        .filter(pk=corpus_pk)
        .exists()
    ):
        return DocumentSummaryRevision.objects.none()
    return DocumentSummaryRevision.objects.filter(
        document_id=root.pk, corpus_id=corpus_pk
    ).order_by("version")


def _resolve_DocumentType_doc_annotations(root, info, **kwargs):
    """Port of DocumentType.resolve_doc_annotations (custom_resolvers)."""
    return resolve_doc_annotations_optimized(root, info, **kwargs)


def _resolve_DocumentType_doc_type_labels(root, info):
    from opencontractserver.annotations.models import DOC_TYPE_LABEL
    from opencontractserver.annotations.services import AnnotationService

    prefetched = getattr(root, "_prefetched_doc_annotations", None)
    if prefetched is not None:
        # ``_apply_document_prefetches`` already filtered to DOC_TYPE_LABEL
        # and ``select_related``-cached ``annotation_label``.
        return _dedupe_doc_type_labels(prefetched)

    # Fallback path: ``DocumentType`` accessed outside the corpus-list
    # batch (e.g. ``node(id:)``). Push ``label_type == DOC_TYPE_LABEL``
    # into SQL via the service queryset — ``structural=True`` is not
    # usable because imported DOC_TYPE_LABEL annotations are created with
    # ``Annotation.structural`` defaulting to False.
    fallback_qs = (
        AnnotationService.get_document_annotations(
            document_id=root.id,
            user=getattr(info.context, "user", None),
            context=info.context,
        )
        .filter(annotation_label__label_type=DOC_TYPE_LABEL)
        .select_related("annotation_label")
    )
    return _dedupe_doc_type_labels(fallback_qs)


def _resolve_DocumentType_all_structural_annotations(root, info, annotation_ids=None):
    from opencontractserver.annotations.services import AnnotationService

    qs = AnnotationService.get_document_annotations(
        document_id=root.id,
        user=getattr(info.context, "user", None),
        structural=True,
    )
    if annotation_ids:
        django_pks = [from_global_id(gid)[1] for gid in annotation_ids]
        qs = qs.filter(pk__in=django_pks)
    return qs


def _resolve_DocumentType_all_annotations(
    root, info, corpus_id=None, analysis_id=None, is_structural=None
):
    from opencontractserver.annotations.services import AnnotationService

    user = getattr(info.context, "user", None)
    corpus_pk: int | None = int(from_global_id(corpus_id)[1]) if corpus_id else None
    analysis_pk: int | None = None
    if analysis_id:
        analysis_pk = (
            0 if analysis_id == "__none__" else int(from_global_id(analysis_id)[1])
        )
    return AnnotationService.get_document_annotations(
        document_id=root.id,
        user=user,
        corpus_id=corpus_pk,
        analysis_id=analysis_pk,
        structural=is_structural,
        context=info.context,
    )


def _resolve_DocumentType_all_relationships(
    root, info, corpus_id=None, analysis_id=None, is_structural=None
):
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
            document_id=root.id,
            user=user,
            corpus_id=corpus_pk,
            analysis_id=analysis_pk,
            structural=is_structural,
            context=info.context,
        )
    except Exception as e:
        logger.warning(
            f"Failed resolving relationships query for document {root.id} with input: corpus_id={corpus_id}, "
            f"analysis_id={analysis_id}. Error: {e}"
        )
        return []


def _resolve_DocumentType_all_structural_relationships(
    root, info, relationship_ids=None
):
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
            document_id=root.id,
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
            f"document {root.id}. Error: {e}"
        )
        return []


def _resolve_DocumentType_all_doc_relationships(root, info, corpus_id=None):
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
            document_id=root.id,
            corpus_id=int(corpus_pk) if corpus_pk else None,
            request=info.context,
        )
    except Exception as e:
        logger.warning(
            "Failed resolving document relationships query for "
            f"document {root.id} with input: corpus_id={corpus_id}. "
            f"Error: {e}"
        )
        return []


def _resolve_DocumentType_doc_relationship_count(root, info, corpus_id=None):
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
        return counts.get(root.id, 0)
    except Exception as e:
        logger.warning(
            f"Failed resolving doc_relationship_count for document {root.id}. "
            f"Error: {e}"
        )
        return 0


def _resolve_DocumentType_all_notes(root, info, corpus_id: str | None = None):
    """
    Return the set of Note objects related to this Document instance that the user can see,
    filtered by corpus_id.
    """
    from opencontractserver.annotations.models import Note

    user = info.context.user

    # Start with a base queryset of all Notes the user can see (service layer).
    base_qs = BaseService.filter_visible(Note, user, request=info.context)

    if corpus_id is None:
        corpus_pk = None
        return base_qs.filter(document=root)

    else:
        corpus_pk = from_global_id(corpus_id)[1]
        # Then intersect with this Document's related notes, filtering by the given corpus_id
        # This ensures we only query notes that are both visible to the user and belong to
        # this specific Document (through the related manager self.notes).
        return base_qs.filter(document=root, corpus_id=corpus_pk)


def _resolve_DocumentType_current_summary_version(root, info, corpus_id):
    """Returns the current summary version number for a specific corpus."""
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import DocumentSummaryRevision

    _, corpus_pk = from_global_id(corpus_id)
    # Verify user can access the corpus before returning version data.
    if (
        not BaseService.filter_visible(Corpus, info.context.user, request=info.context)
        .filter(pk=corpus_pk)
        .exists()
    ):
        return 0
    latest_revision = (
        DocumentSummaryRevision.objects.filter(document_id=root.pk, corpus_id=corpus_pk)
        .order_by("-version")
        .first()
    )

    return latest_revision.version if latest_revision else 0


def _resolve_DocumentType_summary_content(root, info, corpus_id):
    """Returns the current summary content for a specific corpus."""
    from opencontractserver.corpuses.models import Corpus

    _, corpus_pk = from_global_id(corpus_id)
    try:
        # IDOR-safe corpus fetch via service layer.
        corpus = BaseService.get_or_none(
            Corpus, corpus_pk, info.context.user, request=info.context
        )
        if corpus is None:
            raise Corpus.DoesNotExist
        return root.get_summary_for_corpus(corpus)
    except Corpus.DoesNotExist:
        return ""


def _resolve_DocumentType_version_number(root, info, corpus_id):
    """Get version number from DocumentPath for this corpus."""
    _, corpus_pk = from_global_id(corpus_id)
    try:
        path_record = _current_path_for_corpus(root, info, corpus_pk)
        return path_record.version_number if path_record else 1
    except Exception:
        return 1


def _resolve_DocumentType_has_version_history(root, info):
    """Check if document has a parent (i.e., multiple versions exist).

    Uses ``parent_id`` rather than ``parent`` so the check costs zero
    queries — reading ``self.parent`` would fetch the entire parent
    ``Document`` row per document (an N+1 on list views).
    """
    return root.parent_id is not None


def _resolve_DocumentType_version_count(root, info):
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
        return counts.get(root.version_tree_id, 1)
    except Exception as e:
        logger.warning(
            f"Failed resolving version_count for document {root.id}. Error: {e}"
        )
        return 1


def _resolve_DocumentType_is_latest_version(root, info):
    """Check if this is the current version."""
    return root.is_current


def _resolve_DocumentType_last_modified(root, info, corpus_id):
    """Get last modification time from DocumentPath."""
    _, corpus_pk = from_global_id(corpus_id)
    try:
        path_record = _current_path_for_corpus(root, info, corpus_pk)
        return path_record.created if path_record else root.modified
    except Exception:
        return root.modified


def _resolve_DocumentType_version_history(root, info):
    """
    Lazy-load complete version history.
    Returns all versions in the document's version tree.

    graphene returned bare dicts here; strawberry's default resolver is
    attribute-based, so the same data is packed into the plain
    ``DocumentVersionType`` / ``VersionHistoryType`` value types instead.
    """
    from graphql_relay import to_global_id

    from config.graphql.base_types import DocumentVersionType, VersionHistoryType

    # Get all documents in the version tree the user may see, ordered by
    # creation. Scoped to ``visible_to_user`` so this resolver cannot leak
    # version metadata (creator, hash, size) for documents hidden from the
    # caller — matching the security posture of ``resolve_corpus_versions``
    # (the two used to disagree). ``select_related("creator")`` avoids an
    # N+1 on ``created_by`` below.
    versions = (
        BaseService.filter_visible(Document, info.context.user, request=info.context)
        .filter(version_tree_id=root.version_tree_id)
        .select_related("creator")
        .order_by("created")
    )

    version_list = []
    for idx, doc in enumerate(versions, start=1):
        # Determine change type. Use ``parent_id`` (not ``parent``) so we
        # don't fetch the entire parent row per version (N+1).
        if doc.parent_id is None:
            change_type = "INITIAL"
        else:
            # Could be enhanced to detect minor vs major changes
            change_type = "CONTENT_UPDATE"

        # NOTE: ``pdf_file.size`` issues a storage stat (a remote HEAD under
        # S3) per version. Version trees are typically shallow so this is
        # bounded, but it is the one remaining per-version storage call here.
        version_data = DocumentVersionType(
            id=to_global_id("DocumentType", doc.id),
            version_number=idx,
            hash=doc.pdf_file_hash or "",
            created_at=doc.created,
            created_by=doc.creator,
            size_bytes=doc.pdf_file.size if doc.pdf_file else None,
            change_type=coerce_enum(enums.VersionChangeTypeEnum, change_type),
            parent_version=None,  # Could be resolved if needed
        )
        version_list.append(version_data)

    # Find current version
    current = next(
        (v for v in version_list if v.id == to_global_id("DocumentType", root.id)),
        version_list[-1] if version_list else None,
    )

    return VersionHistoryType(
        versions=version_list,
        current_version=current,
        version_tree=None,  # Could build tree structure if needed
    )


def _resolve_DocumentType_path_history(root, info, corpus_id):
    """
    Lazy-load path history for this document in a corpus.
    Returns all lifecycle events (import, move, delete, restore).

    graphene returned bare dicts here; strawberry's default resolver is
    attribute-based, so the same data is packed into the plain
    ``PathEventType`` / ``PathHistoryType`` value types instead.
    """
    from graphql_relay import to_global_id

    from config.graphql.base_types import PathEventType, PathHistoryType

    _, corpus_pk = from_global_id(corpus_id)

    # Get all path records for this document in this corpus. Materialise
    # once and index by pk so each node's predecessor (``parent_id``) is
    # resolved from memory — avoids the per-node ``.parent`` query that
    # produced an N+1 over the history depth.
    path_records = list(
        DocumentPath.objects.filter(
            document__version_tree_id=root.version_tree_id, corpus_id=corpus_pk
        ).order_by("created")
    )
    records_by_id = {pr.id: pr for pr in path_records}

    events = []
    original_path = None
    current_path = None
    move_count = 0

    for path_record in path_records:
        # Resolve predecessor from the in-memory index (None for roots).
        # Fall back to the ``.parent`` FK only for the rare legacy chain
        # whose parent points at a record outside this version-tree slice
        # (pre-isolation add_document replacements) — preserves exact action
        # inference without reintroducing the per-node N+1 on normal data.
        previous = None
        if path_record.parent_id:
            previous = records_by_id.get(path_record.parent_id)
            if previous is None:
                previous = path_record.parent
        # Single source of truth for action inference (shared with
        # ``versioning.get_path_history`` and ``DocumentPathType``).
        action = path_record.infer_action(previous)
        if action == DocumentPath.ACTION_IMPORTED:
            original_path = path_record.path
        elif action == DocumentPath.ACTION_MOVED:
            move_count += 1

        if path_record.is_current and not path_record.is_deleted:
            current_path = path_record.path

        event = PathEventType(
            id=to_global_id("DocumentPathType", path_record.id),
            action=coerce_enum(enums.PathActionEnum, action),
            path=path_record.path,
            folder=path_record.folder,
            timestamp=path_record.created,
            user=path_record.creator,
            version_number=path_record.version_number,
        )
        events.append(event)

    return PathHistoryType(
        events=events,
        current_path=current_path or original_path or "",
        original_path=original_path or "",
        move_count=move_count,
    )


def _resolve_DocumentType_corpus_versions(root, info, corpus_id):
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

    from config.graphql.base_types import CorpusVersionInfoType

    type_name, corpus_pk = from_global_id(corpus_id)
    if not type_name or type_name != "CorpusType":
        return []

    # Request-level cache keyed on (version_tree_id, corpus_pk).
    cache_key = (root.version_tree_id, corpus_pk)
    cache = getattr(info.context, "_corpus_versions_cache", None)
    if cache is None:
        cache = {}
        info.context._corpus_versions_cache = cache
    if cache_key in cache:
        return cache[cache_key]

    # Subquery: only documents in this version tree the user can see.
    visible_version_docs = (
        BaseService.filter_visible(Document, info.context.user, request=info.context)
        .filter(version_tree_id=root.version_tree_id)
        .only("pk")
    )

    # delete_document() creates a tombstone (is_current=True, is_deleted=True)
    # but leaves the previous path record with is_deleted=False.
    # Exclude version_numbers that have a deleted current path.
    deleted_version_numbers = DocumentPath.objects.filter(
        corpus_id=corpus_pk,
        document__version_tree_id=root.version_tree_id,
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
            CorpusVersionInfoType(
                version_number=path_record.version_number,
                document_id=to_global_id("DocumentType", path_record.document_id),
                document_slug=path_record.document.slug,
                created=path_record.created,
                is_current=path_record.is_current,
            )
        )

    cache[cache_key] = results
    return results


def _resolve_DocumentType_can_restore(root, info, corpus_id):
    """Check if user has UPDATE permission for restore operations."""
    from django.contrib.auth.models import AnonymousUser

    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.types.enums import PermissionTypes

    user = info.context.user
    if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
        return False

    # Check document permission (boolean via service layer).
    has_doc_update = BaseService.user_has(
        root, user, PermissionTypes.UPDATE, request=info.context
    )
    if not has_doc_update:
        return False

    # Check corpus permission via an IDOR-safe service fetch:
    # ``get_or_none`` returns the corpus only when the user holds UPDATE
    # on it, and ``None`` for both not-found and denied — collapsing the
    # prior raw ``.objects.get`` fetch-then-check into one service-layer
    # call (no behaviour change: ``corpus is not None`` ⟺ has UPDATE).
    _, corpus_pk = from_global_id(corpus_id)
    corpus = BaseService.get_or_none(
        Corpus, corpus_pk, user, PermissionTypes.UPDATE, request=info.context
    )
    return corpus is not None


def _resolve_DocumentType_can_view_history(root, info):
    """Check if user has READ permission for viewing history."""
    from django.contrib.auth.models import AnonymousUser

    from opencontractserver.types.enums import PermissionTypes

    user = info.context.user

    # Public documents can be viewed by anyone
    if root.is_public:
        return True

    if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
        return False

    return BaseService.user_has(root, user, PermissionTypes.READ, request=info.context)


def _resolve_DocumentType_can_retry(root, info):
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
    if root.processing_status != DocumentProcessingStatus.FAILED:
        return False

    user = info.context.user
    if isinstance(user, AnonymousUser) or not user or not user.is_authenticated:
        return False

    # Creator can always retry their own documents. Superusers are computed
    # like a normal user (scoped admin access, 2026-05) — no blanket retry;
    # they fall through to the normal UPDATE-permission check below.
    if root.creator == user:
        return True

    # Others (incl. superusers) need UPDATE permission (via service layer).
    return BaseService.user_has(
        root, user, PermissionTypes.UPDATE, request=info.context
    )


def _resolve_DocumentType_page_annotations(
    root,
    info,
    corpus_id,
    page=None,
    pages=None,
    structural=None,
    analysis_id=None,
    extract_id=None,
):
    """Resolve annotations for specific page(s) using optimized queries."""
    from opencontractserver.annotations.services import AnnotationService

    corpus_pk = int(from_global_id(corpus_id)[1])
    analysis_pk: int | None = None
    if analysis_id:
        analysis_pk = int(from_global_id(analysis_id)[1])
    extract_pk: int | None = None
    if extract_id:
        extract_pk = int(from_global_id(extract_id)[1])

    user = _assert_user_can_read(root, info)

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
        document_id=root.id,
        user=user,
        corpus_id=corpus_pk,
        pages=page_list,  # Pass list of pages
        structural=structural,
        analysis_id=analysis_pk,
        extract_id=extract_pk,
    )


def _resolve_DocumentType_page_relationships(
    root,
    info,
    corpus_id,
    pages,
    structural=None,
    analysis_id=None,
    extract_id=None,
    strict_extract_mode=False,
):
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

    user = _assert_user_can_read(root, info)

    return RelationshipService.get_document_relationships(
        document_id=root.id,
        user=user,
        corpus_id=corpus_pk,
        pages=pages if pages else None,
        structural=structural,
        analysis_id=analysis_pk,
        extract_id=extract_pk,
        strict_extract_mode=strict_extract_mode,
    )


def _resolve_DocumentType_relationship_summary(root, info, corpus_id):
    from opencontractserver.annotations.services import RelationshipService

    user = _assert_user_can_read(root, info)

    corpus_pk = int(from_global_id(corpus_id)[1])
    summary = RelationshipService.get_relationship_summary(
        document_id=root.id, corpus_id=corpus_pk, user=user
    )
    return summary


def _resolve_DocumentType_extract_annotation_summary(root, info, extract_id):
    """Get summary of annotations in extract."""
    from opencontractserver.annotations.services import AnnotationService

    user = _assert_user_can_read(root, info)
    extract_pk = int(from_global_id(extract_id)[1])

    return AnnotationService.get_extract_annotation_summary(
        document_id=root.id, extract_id=extract_pk, user=user
    )


def _resolve_DocumentType_folder_in_corpus(root, info, corpus_id):
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
            document=root,
            corpus=corpus,
            request=info.context,
        )
    except Corpus.DoesNotExist:
        return None


@strawberry.type(name="DocumentType")
class DocumentType(Node):
    @strawberry.field(name="parent")
    def parent(self, info: strawberry.Info) -> DocumentType | None:
        return resolve_visible_fk(self, info, "parent_id", "DocumentType")

    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    _assert_user_can_read = staticmethod(_assert_user_can_read)

    @strawberry.field(name="title")
    def title(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "title", None))

    @strawberry.field(name="description")
    def description(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "description", None))

    @strawberry.field(
        name="slug",
        description="Case-sensitive slug unique per creator. Allowed: A-Z, a-z, 0-9, hyphen (-).",
    )
    def slug(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "slug", None))

    custom_meta: JSONString | None = strawberry.field(name="customMeta", default=None)

    @strawberry.field(name="fileType")
    def file_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "file_type", None))

    @strawberry.field(name="icon")
    def icon(self, info: strawberry.Info) -> str:
        kwargs = strip_unset({})
        return _resolve_DocumentType_icon(self, info, **kwargs)

    @strawberry.field(name="pdfFile")
    def pdf_file(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_pdf_file(self, info, **kwargs)

    @strawberry.field(name="txtExtractFile")
    def txt_extract_file(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_txt_extract_file(self, info, **kwargs)

    @strawberry.field(name="mdSummaryFile")
    def md_summary_file(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_md_summary_file(self, info, **kwargs)

    page_count: int = strawberry.field(name="pageCount", default=None)

    @strawberry.field(name="pawlsParseFile")
    def pawls_parse_file(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_pawls_parse_file(self, info, **kwargs)

    @strawberry.field(
        name="originalFileType",
        description="MIME type of the original upload before PDF conversion",
    )
    def original_file_type(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "original_file_type", None))

    @strawberry.field(
        name="pdfFileHash",
        description="SHA-256 hash of the PDF file content for caching and integrity checks",
    )
    def pdf_file_hash(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "pdf_file_hash", None))

    version_tree_id: uuid.UUID = strawberry.field(
        name="versionTreeId",
        description="Groups all content versions of same logical document. Implements Rule C1.",
        default=None,
    )
    is_current: bool = strawberry.field(
        name="isCurrent",
        description="True for newest content in this version tree. Implements Rule C3.",
        default=None,
    )

    @strawberry.field(
        name="sourceDocument",
        description="Original document this was copied from (cross-corpus provenance). Implements Rule I2.",
    )
    def source_document(self, info: strawberry.Info) -> DocumentType | None:
        # Cross-corpus provenance: a copied document must not leak its private
        # origin document to a caller who lacks READ on the source.
        return resolve_visible_fk(self, info, "source_document_id", "DocumentType")

    processing_started: datetime.datetime | None = strawberry.field(
        name="processingStarted", default=None
    )
    processing_finished: datetime.datetime | None = strawberry.field(
        name="processingFinished", default=None
    )

    @strawberry.field(
        name="processingStatus",
        description="Current processing status of the document in the parsing pipeline",
    )
    def processing_status(
        self, info: strawberry.Info
    ) -> enums.DocumentProcessingStatusEnum | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_processing_status(self, info, **kwargs)

    @strawberry.field(
        name="processingError",
        description="Error message if processing failed (truncated for display)",
    )
    def processing_error(self, info: strawberry.Info) -> str | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_processing_error(self, info, **kwargs)

    @strawberry.field(
        name="processingErrorTraceback",
        description="Full traceback if processing failed",
    )
    def processing_error_traceback(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "processing_error_traceback", None))

    @strawberry.field(name="assignmentSet")
    def assignment_set(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AssignmentTypeConnection, strawberry.lazy("config.graphql.user_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "assignment_set", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AssignmentType",
        )

    @strawberry.field(
        name="corpusCopies",
        description="Original document this was copied from (cross-corpus provenance). Implements Rule I2.",
    )
    def corpus_copies(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> DocumentTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "corpus_copies", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentType",
        )

    @strawberry.field(name="children")
    def children(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> DocumentTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "children", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentType",
        )

    @strawberry.field(name="rows")
    def rows(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> DocumentAnalysisRowTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "rows", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentAnalysisRowType",
        )

    @strawberry.field(name="sourceRelationships")
    def source_relationships(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> DocumentRelationshipTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "source_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentRelationshipType",
        )

    @strawberry.field(name="targetRelationships")
    def target_relationships(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> DocumentRelationshipTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "target_relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentRelationshipType",
        )

    @strawberry.field(
        name="pathRecords", description="Specific content version this path points to"
    )
    def path_records(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> DocumentPathTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "path_records", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentPathType",
        )

    @strawberry.field(
        name="summaryRevisions",
        description="List of all summary revisions/versions for a specific corpus, ordered by version.",
    )
    def summary_revisions(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> list[DocumentSummaryRevisionType | None] | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_summary_revisions(self, info, **kwargs)

    memory_for_corpus: None | (
        Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="memoryForCorpus", default=None)

    @strawberry.field(
        name="corpusActionExecutions",
        description="The document this action was executed on (null for thread-based actions)",
    )
    def corpus_action_executions(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpus_Id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.CorpusesCorpusActionExecutionStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        action_type: Annotated[
            enums.CorpusesCorpusActionExecutionActionTypeChoices | None,
            strawberry.argument(name="actionType"),
        ] = strawberry.UNSET,
        trigger: Annotated[
            enums.CorpusesCorpusActionExecutionTriggerChoices | None,
            strawberry.argument(name="trigger"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusActionExecutionTypeConnection,
        strawberry.lazy("config.graphql.agent_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus__id": corpus__id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "action_type": action_type,
                "trigger": trigger,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "corpus_action_executions", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusActionExecutionType",
            filterset_class=filterset_factory(
                CorpusActionExecution,
                fields={
                    "id": ["exact"],
                    "corpus__id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "action_type": ["exact"],
                    "trigger": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus__id": "corpus__id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "action_type": "action_type",
                "trigger": "trigger",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(name="relationships")
    def relationships(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        RelationshipTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "relationships", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="RelationshipType",
        )

    @strawberry.field(name="docAnnotations")
    def doc_annotations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = _resolve_DocumentType_doc_annotations(self, info, **kwargs)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(name="notes")
    def notes(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        NoteTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "notes", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="NoteType",
        )

    @strawberry.field(name="inboundReferences")
    def inbound_references(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        CorpusReferenceTypeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "inbound_references", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="CorpusReferenceType",
        )

    @strawberry.field(name="frontierEntries")
    def frontier_entries(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AuthorityFrontierNodeConnection,
        strawberry.lazy("config.graphql.annotation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "frontier_entries", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AuthorityFrontierNode",
        )

    @strawberry.field(name="includedInAnalyses")
    def included_in_analyses(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnalysisTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "included_in_analyses", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnalysisType",
        )

    @strawberry.field(name="extracts")
    def extracts(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ExtractTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "extracts", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ExtractType",
        )

    @strawberry.field(name="extractedDatacells")
    def extracted_datacells(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DatacellTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "extracted_datacells", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    @strawberry.field(
        name="conversations",
        description="The document to which this conversation belongs",
    )
    def conversations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ConversationTypeConnection,
        strawberry.lazy("config.graphql.conversation_types"),
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "conversations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ConversationType",
        )

    @strawberry.field(
        name="chatMessages", description="A document that this chat message is based on"
    )
    def chat_messages(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        MessageTypeConnection, strawberry.lazy("config.graphql.conversation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "chat_messages", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="MessageType",
        )

    @strawberry.field(
        name="agentActionResults",
        description="The document this action was run on (null for thread-based actions)",
    )
    def agent_action_results(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        id: Annotated[
            strawberry.ID | None, strawberry.argument(name="id")
        ] = strawberry.UNSET,
        corpus_action__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusAction_Id")
        ] = strawberry.UNSET,
        document__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="document_Id")
        ] = strawberry.UNSET,
        status: Annotated[
            enums.AgentsAgentActionResultStatusChoices | None,
            strawberry.argument(name="status"),
        ] = strawberry.UNSET,
        creator__id: Annotated[
            strawberry.ID | None, strawberry.argument(name="creator_Id")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AgentActionResultTypeConnection, strawberry.lazy("config.graphql.agent_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "id": id,
                "corpus_action__id": corpus_action__id,
                "document__id": document__id,
                "status": status,
                "creator__id": creator__id,
            }
        )
        resolved = getattr(self, "agent_action_results", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AgentActionResultType",
            filterset_class=filterset_factory(
                AgentActionResult,
                fields={
                    "id": ["exact"],
                    "corpus_action__id": ["exact"],
                    "document__id": ["exact"],
                    "status": ["exact"],
                    "creator__id": ["exact"],
                },
            ),
            filter_args={
                "id": "id",
                "corpus_action__id": "corpus_action__id",
                "document__id": "document__id",
                "status": "status",
                "creator__id": "creator__id",
            },
        )

    @strawberry.field(
        name="citedInResearchReports",
        description="Documents touched (vector-search hits, summaries loaded, etc.)",
    )
    def cited_in_research_reports(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        ResearchReportTypeConnection, strawberry.lazy("config.graphql.research_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "cited_in_research_reports", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="ResearchReportType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(
        name="docTypeLabels",
        description="Flat list of distinct ``DOC_TYPE_LABEL`` annotation labels for this document — the corpus list view's per-card badges. Resolved from a single batched prefetch when the parent ``documents`` resolver opts in via ``requests_doc_type_labels``; falls back to one targeted SELECT per document otherwise. Skipping the Relay connection wrapper avoids the per-document COUNT + SELECT + FK descriptor storm the old ``docAnnotations`` shape forced.",
    )
    def doc_type_labels(self, info: strawberry.Info) -> None | (
        list[
            Annotated[
                AnnotationLabelType,
                strawberry.lazy("config.graphql.annotation_types"),
            ]
        ]
    ):
        kwargs = strip_unset({})
        return _resolve_DocumentType_doc_type_labels(self, info, **kwargs)

    @strawberry.field(name="allStructuralAnnotations")
    def all_structural_annotations(
        self,
        info: strawberry.Info,
        annotation_ids: Annotated[
            list[strawberry.ID] | None, strawberry.argument(name="annotationIds")
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    AnnotationType, strawberry.lazy("config.graphql.annotation_types")
                ]
            )
        ]
    ):
        kwargs = strip_unset({"annotation_ids": annotation_ids})
        return _resolve_DocumentType_all_structural_annotations(self, info, **kwargs)

    @strawberry.field(name="allAnnotations")
    def all_annotations(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        analysis_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analysisId")
        ] = strawberry.UNSET,
        is_structural: Annotated[
            bool | None, strawberry.argument(name="isStructural")
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    AnnotationType, strawberry.lazy("config.graphql.annotation_types")
                ]
            )
        ]
    ):
        kwargs = strip_unset(
            {
                "corpus_id": corpus_id,
                "analysis_id": analysis_id,
                "is_structural": is_structural,
            }
        )
        return _resolve_DocumentType_all_annotations(self, info, **kwargs)

    @strawberry.field(name="allRelationships")
    def all_relationships(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        analysis_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analysisId")
        ] = strawberry.UNSET,
        is_structural: Annotated[
            bool | None, strawberry.argument(name="isStructural")
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    RelationshipType,
                    strawberry.lazy("config.graphql.annotation_types"),
                ]
            )
        ]
    ):
        kwargs = strip_unset(
            {
                "corpus_id": corpus_id,
                "analysis_id": analysis_id,
                "is_structural": is_structural,
            }
        )
        return _resolve_DocumentType_all_relationships(self, info, **kwargs)

    @strawberry.field(name="allStructuralRelationships")
    def all_structural_relationships(
        self,
        info: strawberry.Info,
        relationship_ids: Annotated[
            list[strawberry.ID] | None, strawberry.argument(name="relationshipIds")
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    RelationshipType,
                    strawberry.lazy("config.graphql.annotation_types"),
                ]
            )
        ]
    ):
        kwargs = strip_unset({"relationship_ids": relationship_ids})
        return _resolve_DocumentType_all_structural_relationships(self, info, **kwargs)

    @strawberry.field(name="allDocRelationships")
    def all_doc_relationships(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            str | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> list[DocumentRelationshipType | None] | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_all_doc_relationships(self, info, **kwargs)

    @strawberry.field(
        name="docRelationshipCount",
        description="Count of document relationships for this document in the given corpus",
    )
    def doc_relationship_count(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            str | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> int | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_doc_relationship_count(self, info, **kwargs)

    @strawberry.field(name="allNotes")
    def all_notes(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            None
            | (Annotated[NoteType, strawberry.lazy("config.graphql.annotation_types")])
        ]
    ):
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_all_notes(self, info, **kwargs)

    @strawberry.field(
        name="currentSummaryVersion",
        description="Current version number of the summary for a specific corpus",
    )
    def current_summary_version(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> int | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_current_summary_version(self, info, **kwargs)

    @strawberry.field(
        name="summaryContent",
        description="Current summary content for a specific corpus",
    )
    def summary_content(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> str | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_summary_content(self, info, **kwargs)

    @strawberry.field(
        name="versionNumber",
        description="Content version number in this corpus (from DocumentPath)",
    )
    def version_number(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> int | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_version_number(self, info, **kwargs)

    @strawberry.field(
        name="hasVersionHistory",
        description="True if this document has multiple versions (parent exists)",
    )
    def has_version_history(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_has_version_history(self, info, **kwargs)

    @strawberry.field(
        name="versionCount",
        description="Total number of versions in this document's version tree",
    )
    def version_count(self, info: strawberry.Info) -> int | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_version_count(self, info, **kwargs)

    @strawberry.field(
        name="isLatestVersion",
        description="True if this is the current version (Document.is_current)",
    )
    def is_latest_version(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_is_latest_version(self, info, **kwargs)

    @strawberry.field(
        name="lastModified",
        description="When the document was last modified in this corpus",
    )
    def last_modified(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> datetime.datetime | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_last_modified(self, info, **kwargs)

    @strawberry.field(
        name="versionHistory",
        description="Complete version history (lazy-loaded on request)",
    )
    def version_history(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[VersionHistoryType, strawberry.lazy("config.graphql.base_types")]
    ):
        kwargs = strip_unset({})
        return _resolve_DocumentType_version_history(self, info, **kwargs)

    @strawberry.field(
        name="pathHistory",
        description="Path/location history in corpus (lazy-loaded on request)",
    )
    def path_history(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> None | (
        Annotated[PathHistoryType, strawberry.lazy("config.graphql.base_types")]
    ):
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_path_history(self, info, **kwargs)

    @strawberry.field(
        name="corpusVersions",
        description="All versions of this document in a specific corpus. Used by the version selector UI to show available versions.",
    )
    def corpus_versions(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            Annotated[
                CorpusVersionInfoType, strawberry.lazy("config.graphql.base_types")
            ]
        ]
    ):
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_corpus_versions(self, info, **kwargs)

    @strawberry.field(
        name="canRestore",
        description="Whether user can restore this document (requires UPDATE permission)",
    )
    def can_restore(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> bool | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_can_restore(self, info, **kwargs)

    @strawberry.field(
        name="canViewHistory",
        description="Whether user can view version history (requires READ permission)",
    )
    def can_view_history(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_can_view_history(self, info, **kwargs)

    @strawberry.field(
        name="canRetry",
        description="Whether the user can retry processing for this document (True if FAILED and user has permission)",
    )
    def can_retry(self, info: strawberry.Info) -> bool | None:
        kwargs = strip_unset({})
        return _resolve_DocumentType_can_retry(self, info, **kwargs)

    @strawberry.field(
        name="pageAnnotations",
        description="Get annots for spec. page(s) using opt. queries. Either 'page' (single) or 'pages' (multiple).",
    )
    def page_annotations(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        page: Annotated[
            int | None, strawberry.argument(name="page")
        ] = strawberry.UNSET,
        pages: Annotated[
            list[int | None] | None, strawberry.argument(name="pages")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        analysis_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analysisId")
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    AnnotationType, strawberry.lazy("config.graphql.annotation_types")
                ]
            )
        ]
    ):
        kwargs = strip_unset(
            {
                "corpus_id": corpus_id,
                "page": page,
                "pages": pages,
                "structural": structural,
                "analysis_id": analysis_id,
            }
        )
        return _resolve_DocumentType_page_annotations(self, info, **kwargs)

    @strawberry.field(
        name="pageRelationships",
        description="Get relationships where source or target annotations are on the specified page(s).",
    )
    def page_relationships(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        pages: Annotated[
            list[int | None], strawberry.argument(name="pages")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        analysis_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="analysisId")
        ] = strawberry.UNSET,
    ) -> None | (
        list[
            None
            | (
                Annotated[
                    RelationshipType,
                    strawberry.lazy("config.graphql.annotation_types"),
                ]
            )
        ]
    ):
        kwargs = strip_unset(
            {
                "corpus_id": corpus_id,
                "pages": pages,
                "structural": structural,
                "analysis_id": analysis_id,
            }
        )
        return _resolve_DocumentType_page_relationships(self, info, **kwargs)

    @strawberry.field(
        name="relationshipSummary",
        description="Get relationship summary statistics for this document and corpus (MV-backed).",
    )
    def relationship_summary(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> GenericScalar | None:
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_relationship_summary(self, info, **kwargs)

    @strawberry.field(
        name="extractAnnotationSummary",
        description="Get summary of annotations used in specific extract.",
    )
    def extract_annotation_summary(
        self,
        info: strawberry.Info,
        extract_id: Annotated[
            strawberry.ID, strawberry.argument(name="extractId")
        ] = strawberry.UNSET,
    ) -> GenericScalar | None:
        kwargs = strip_unset({"extract_id": extract_id})
        return _resolve_DocumentType_extract_annotation_summary(self, info, **kwargs)

    @strawberry.field(
        name="folderInCorpus",
        description="Get the folder this document is in within a specific corpus (null = root)",
    )
    def folder_in_corpus(
        self,
        info: strawberry.Info,
        corpus_id: Annotated[
            strawberry.ID, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
    ) -> None | (
        Annotated[CorpusFolderType, strawberry.lazy("config.graphql.corpus_types")]
    ):
        kwargs = strip_unset({"corpus_id": corpus_id})
        return _resolve_DocumentType_folder_in_corpus(self, info, **kwargs)


def _get_queryset_DocumentType(queryset, info):
    """Port of DocumentType.get_queryset."""
    # Chain the queryset's own ``visible_to_user`` through the service
    # layer so the visibility filter stays a single ``WHERE`` expression
    # tree (no correlated ``pk__in`` subquery over the full table).
    return BaseService.filter_visible_qs(
        queryset, info.context.user, request=info.context
    )


register_type(
    "DocumentType",
    DocumentType,
    model=Document,
    get_queryset=_get_queryset_DocumentType,
)


DocumentTypeConnection = make_connection_types(
    DocumentType,
    type_name="DocumentTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(name="DocumentAnalysisRowType")
class DocumentAnalysisRowType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    document: DocumentType = strawberry.field(name="document", default=None)

    @strawberry.field(name="annotations")
    def annotations(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
        raw_text__contains: Annotated[
            str | None, strawberry.argument(name="rawText_Contains")
        ] = strawberry.UNSET,
        annotation_label_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="annotationLabelId")
        ] = strawberry.UNSET,
        annotation_label__text: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text")
        ] = strawberry.UNSET,
        annotation_label__text__contains: Annotated[
            str | None, strawberry.argument(name="annotationLabel_Text_Contains")
        ] = strawberry.UNSET,
        annotation_label__description__contains: Annotated[
            str | None,
            strawberry.argument(name="annotationLabel_Description_Contains"),
        ] = strawberry.UNSET,
        annotation_label__label_type: Annotated[
            enums.AnnotationsAnnotationLabelLabelTypeChoices | None,
            strawberry.argument(name="annotationLabel_LabelType"),
        ] = strawberry.UNSET,
        analysis__isnull: Annotated[
            bool | None, strawberry.argument(name="analysis_Isnull")
        ] = strawberry.UNSET,
        document_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="documentId")
        ] = strawberry.UNSET,
        corpus_id: Annotated[
            strawberry.ID | None, strawberry.argument(name="corpusId")
        ] = strawberry.UNSET,
        structural: Annotated[
            bool | None, strawberry.argument(name="structural")
        ] = strawberry.UNSET,
        uses_label_from_labelset_id: Annotated[
            str | None, strawberry.argument(name="usesLabelFromLabelsetId")
        ] = strawberry.UNSET,
        created_by_analysis_ids: Annotated[
            str | None, strawberry.argument(name="createdByAnalysisIds")
        ] = strawberry.UNSET,
        created_with_analyzer_id: Annotated[
            str | None, strawberry.argument(name="createdWithAnalyzerId")
        ] = strawberry.UNSET,
        order_by: Annotated[
            str | None, strawberry.argument(name="orderBy", description="Ordering")
        ] = strawberry.UNSET,
    ) -> Annotated[
        AnnotationTypeConnection, strawberry.lazy("config.graphql.annotation_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
                "raw_text__contains": raw_text__contains,
                "annotation_label_id": annotation_label_id,
                "annotation_label__text": annotation_label__text,
                "annotation_label__text__contains": annotation_label__text__contains,
                "annotation_label__description__contains": annotation_label__description__contains,
                "annotation_label__label_type": annotation_label__label_type,
                "analysis__isnull": analysis__isnull,
                "document_id": document_id,
                "corpus_id": corpus_id,
                "structural": structural,
                "uses_label_from_labelset_id": uses_label_from_labelset_id,
                "created_by_analysis_ids": created_by_analysis_ids,
                "created_with_analyzer_id": created_with_analyzer_id,
                "order_by": order_by,
            }
        )
        resolved = getattr(self, "annotations", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="AnnotationType",
            filterset_class=setup_filterset(AnnotationFilter),
            filter_args={
                "raw_text__contains": "raw_text__contains",
                "annotation_label_id": "annotation_label_id",
                "annotation_label__text": "annotation_label__text",
                "annotation_label__text__contains": "annotation_label__text__contains",
                "annotation_label__description__contains": "annotation_label__description__contains",
                "annotation_label__label_type": "annotation_label__label_type",
                "analysis__isnull": "analysis__isnull",
                "document_id": "document_id",
                "corpus_id": "corpus_id",
                "structural": "structural",
                "uses_label_from_labelset_id": "uses_label_from_labelset_id",
                "created_by_analysis_ids": "created_by_analysis_ids",
                "created_with_analyzer_id": "created_with_analyzer_id",
                "order_by": "order_by",
            },
        )

    @strawberry.field(name="data")
    def data(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> Annotated[
        DatacellTypeConnection, strawberry.lazy("config.graphql.extract_types")
    ]:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "data", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DatacellType",
        )

    analysis: None | (
        Annotated[AnalysisType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="analysis", default=None)
    extract: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="extract", default=None)

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


register_type(
    "DocumentAnalysisRowType", DocumentAnalysisRowType, model=DocumentAnalysisRow
)


DocumentAnalysisRowTypeConnection = make_connection_types(
    DocumentAnalysisRowType,
    type_name="DocumentAnalysisRowTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(
    name="DocumentRelationshipType",
    description="GraphQL type for DocumentRelationship model.",
)
class DocumentRelationshipType(Node):
    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    source_document: DocumentType = strawberry.field(
        name="sourceDocument", default=None
    )
    target_document: DocumentType = strawberry.field(
        name="targetDocument", default=None
    )

    @strawberry.field(name="relationshipType")
    def relationship_type(
        self, info: strawberry.Info
    ) -> enums.DocumentsDocumentRelationshipRelationshipTypeChoices:
        return coerce_enum(
            enums.DocumentsDocumentRelationshipRelationshipTypeChoices,
            getattr(self, "relationship_type", None),
        )

    annotation_label: None | (
        Annotated[
            AnnotationLabelType, strawberry.lazy("config.graphql.annotation_types")
        ]
    ) = strawberry.field(name="annotationLabel", default=None)
    corpus: None | (
        Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="corpus", default=None)
    data: GenericScalar | None = strawberry.field(name="data", default=None)

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_queryset_DocumentRelationshipType(queryset, info):
    """Port of DocumentRelationshipType.get_queryset."""
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


register_type(
    "DocumentRelationshipType",
    DocumentRelationshipType,
    model=DocumentRelationship,
    get_queryset=_get_queryset_DocumentRelationshipType,
)


DocumentRelationshipTypeConnection = make_connection_types(
    DocumentRelationshipType,
    type_name="DocumentRelationshipTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


def _resolve_DocumentPathType_action(root, info):
    """Infer action type from path state.

    Delegates to ``DocumentPath.infer_action`` — the single source of
    truth shared with ``versioning.get_path_history`` and
    ``DocumentType.resolve_path_history`` — so all three surfaces agree
    on MOVED/RESTORED/DELETED/UPDATED.
    """
    return coerce_enum(enums.PathActionEnum, root.infer_action())


@strawberry.type(
    name="DocumentPathType",
    description="GraphQL type for DocumentPath model - represents filesystem lifecycle events.",
)
class DocumentPathType(Node):
    @strawberry.field(name="parent")
    def parent(self, info: strawberry.Info) -> DocumentPathType | None:
        return resolve_visible_fk(self, info, "parent_id", "DocumentPathType")

    user_lock: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userLock", default=None)
    backend_lock: bool = strawberry.field(name="backendLock", default=None)
    is_public: bool = strawberry.field(name="isPublic", default=None)
    creator: Annotated[UserType, strawberry.lazy("config.graphql.user_types")] = (
        strawberry.field(name="creator", default=None)
    )
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)
    document: DocumentType = strawberry.field(
        name="document",
        description="Specific content version this path points to",
        default=None,
    )
    corpus: Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")] = (
        strawberry.field(
            name="corpus", description="Corpus owning this path", default=None
        )
    )

    @strawberry.field(
        name="folder",
        description="Current folder (null if folder deleted or at root)",
    )
    def folder(
        self, info: strawberry.Info
    ) -> None | (
        Annotated[CorpusFolderType, strawberry.lazy("config.graphql.corpus_types")]
    ):
        return resolve_visible_fk(self, info, "folder_id", "CorpusFolderType")

    @strawberry.field(name="path", description="Full path in corpus filesystem")
    def path(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "path", None))

    version_number: int = strawberry.field(
        name="versionNumber",
        description="Content version number (Rule P5: increments only on content changes)",
        default=None,
    )
    is_deleted: bool = strawberry.field(
        name="isDeleted", description="Soft delete flag", default=None
    )
    is_current: bool = strawberry.field(
        name="isCurrent",
        description="True for current filesystem state (Rule P3)",
        default=None,
    )

    @strawberry.field(
        name="ingestionSource",
        description="Source integration that produced this version (null = manual upload)",
    )
    def ingestion_source(self, info: strawberry.Info) -> IngestionSourceType | None:
        return resolve_visible_fk(
            self, info, "ingestion_source_id", "IngestionSourceType"
        )

    @strawberry.field(
        name="externalId",
        description="Identifier in the external system (e.g. 'alpha:contract-123')",
    )
    def external_id(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "external_id", None))

    ingestion_metadata: GenericScalar | None = strawberry.field(
        name="ingestionMetadata",
        description="Arbitrary source-specific metadata (URL, crawl job ID, etc.)",
        default=None,
    )

    @strawberry.field(name="children")
    def children(
        self,
        info: strawberry.Info,
        offset: Annotated[
            int | None, strawberry.argument(name="offset")
        ] = strawberry.UNSET,
        before: Annotated[
            str | None, strawberry.argument(name="before")
        ] = strawberry.UNSET,
        after: Annotated[
            str | None, strawberry.argument(name="after")
        ] = strawberry.UNSET,
        first: Annotated[
            int | None, strawberry.argument(name="first")
        ] = strawberry.UNSET,
        last: Annotated[
            int | None, strawberry.argument(name="last")
        ] = strawberry.UNSET,
    ) -> DocumentPathTypeConnection:
        kwargs = strip_unset(
            {
                "offset": offset,
                "before": before,
                "after": after,
                "first": first,
                "last": last,
            }
        )
        resolved = getattr(self, "children", None)
        return resolve_django_connection(
            resolved=resolved,
            info=info,
            args=kwargs,
            node_type_name="DocumentPathType",
        )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)

    @strawberry.field(name="action", description="Inferred action type")
    def action(self, info: strawberry.Info) -> enums.PathActionEnum | None:
        kwargs = strip_unset({})
        return _resolve_DocumentPathType_action(self, info, **kwargs)


def _get_queryset_DocumentPathType(queryset, info):
    """Filter paths to current, non-deleted paths in visible corpuses whose
    target document is also visible to the user.

    The ``document_id`` filter enforces MIN(document, corpus) and closes a
    cross-document leak: DocumentPath membership is corpus-gated, so a public
    (or merely shared) corpus lists paths for its *private* documents too.
    graphene filtered the **non-null** ``document`` FK through
    ``DocumentType.get_queryset`` per row (an invisible target surfaced as a
    non-null-violation error, never real data); strawberry's plain field
    cannot resolve non-null to null, so the exclusion moves up to the list
    level — the same MIN semantic ``CorpusType.documents`` already uses
    (issue #1682).
    """
    from opencontractserver.documents.models import Document

    visible_corpus_ids = _docpath_visible_corpus_ids(info)
    visible_document_ids = BaseService.filter_visible(
        Document, info.context.user, request=info.context
    ).values("id")

    if issubclass(type(queryset), QuerySet):
        return queryset.filter(
            corpus_id__in=visible_corpus_ids,
            document_id__in=visible_document_ids,
            is_current=True,
            is_deleted=False,
        )
    elif "RelatedManager" in str(type(queryset)):
        return queryset.all().filter(
            corpus_id__in=visible_corpus_ids,
            document_id__in=visible_document_ids,
            is_current=True,
            is_deleted=False,
        )
    else:
        return queryset


register_type(
    "DocumentPathType",
    DocumentPathType,
    model=DocumentPath,
    get_queryset=_get_queryset_DocumentPathType,
)


DocumentPathTypeConnection = make_connection_types(
    DocumentPathType,
    type_name="DocumentPathTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(
    name="IngestionSourceType",
    description="GraphQL type for IngestionSource - a named integration that produces documents.",
)
class IngestionSourceType(Node):
    created: datetime.datetime = strawberry.field(name="created", default=None)
    modified: datetime.datetime = strawberry.field(name="modified", default=None)

    @strawberry.field(
        name="name",
        description="Human-readable name for this source (e.g. 'alpha_site_crawler')",
    )
    def name(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "name", None))

    @strawberry.field(name="sourceType", description="Category of ingestion source")
    def source_type(
        self, info: strawberry.Info
    ) -> enums.DocumentsIngestionSourceSourceTypeChoices:
        return coerce_enum(
            enums.DocumentsIngestionSourceSourceTypeChoices,
            getattr(self, "source_type", None),
        )

    config: GenericScalar | None = strawberry.field(
        name="config",
        description="Source configuration (connection details, etc.). WARNING: This field is returned to the owning user verbatim. Store secret-manager key paths or references here, never raw credentials (API keys, tokens, passwords).",
        default=None,
    )
    active: bool = strawberry.field(
        name="active",
        description="Whether this source is actively ingesting documents",
        default=None,
    )

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


def _get_queryset_IngestionSourceType(queryset, info):
    """Only show sources owned by the current user, shared, or public."""
    return BaseService.filter_visible(
        IngestionSource, info.context.user, request=info.context
    )


register_type(
    "IngestionSourceType",
    IngestionSourceType,
    model=IngestionSource,
    get_queryset=_get_queryset_IngestionSourceType,
)


IngestionSourceTypeConnection = make_connection_types(
    IngestionSourceType,
    type_name="IngestionSourceTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(
    name="DocumentSummaryRevisionType",
    description="GraphQL type for document summary revisions.",
)
class DocumentSummaryRevisionType(Node):
    document: DocumentType = strawberry.field(name="document", default=None)
    corpus: Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")] = (
        strawberry.field(name="corpus", default=None)
    )
    author: None | (
        Annotated[UserType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="author", default=None)
    version: int = strawberry.field(name="version", default=None)

    @strawberry.field(name="diff")
    def diff(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "diff", None))

    @strawberry.field(name="snapshot")
    def snapshot(self, info: strawberry.Info) -> str | None:
        return coerce_str(getattr(self, "snapshot", None))

    @strawberry.field(name="checksumBase")
    def checksum_base(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "checksum_base", None))

    @strawberry.field(name="checksumFull")
    def checksum_full(self, info: strawberry.Info) -> str:
        return coerce_str(getattr(self, "checksum_full", None))

    created: datetime.datetime = strawberry.field(name="created", default=None)

    @strawberry.field(name="myPermissions")
    def my_permissions(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_my_permissions(self, info)

    @strawberry.field(name="isPublished")
    def is_published(self, info: strawberry.Info) -> bool | None:
        return core_permissions.resolve_is_published(self, info)

    @strawberry.field(name="objectSharedWith")
    def object_shared_with(self, info: strawberry.Info) -> GenericScalar | None:
        return core_permissions.resolve_object_shared_with(self, info)


register_type(
    "DocumentSummaryRevisionType",
    DocumentSummaryRevisionType,
    model=DocumentSummaryRevision,
)


DocumentSummaryRevisionTypeConnection = make_connection_types(
    DocumentSummaryRevisionType,
    type_name="DocumentSummaryRevisionTypeConnection",
    countable=True,
    pdf_page_aware=False,
)


@strawberry.type(name="DocumentCorpusActionsType")
class DocumentCorpusActionsType:
    corpus_actions: None | (
        list[
            None
            | (
                Annotated[
                    CorpusActionType, strawberry.lazy("config.graphql.agent_types")
                ]
            )
        ]
    ) = strawberry.field(name="corpusActions", default=None)
    extracts: None | (
        list[
            None
            | (Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")])
        ]
    ) = strawberry.field(name="extracts", default=None)
    analysis_rows: list[DocumentAnalysisRowType | None] | None = strawberry.field(
        name="analysisRows", default=None
    )


register_type("DocumentCorpusActionsType", DocumentCorpusActionsType, model=None)


@strawberry.type(
    name="DocumentStatsType",
    description="Permission-scoped aggregate counts for the Documents view tile counters.",
)
class DocumentStatsType:
    total_docs: int = strawberry.field(name="totalDocs", default=None)
    total_pages: int = strawberry.field(name="totalPages", default=None)
    processed_count: int = strawberry.field(name="processedCount", default=None)
    processing_count: int = strawberry.field(name="processingCount", default=None)


register_type("DocumentStatsType", DocumentStatsType, model=None)
