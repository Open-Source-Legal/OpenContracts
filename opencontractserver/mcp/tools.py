"""MCP Tool implementations for OpenContracts.

Tools provide dynamic operations - they execute queries and return results.
Supports both global mode (all public corpuses) and corpus-scoped mode
(single corpus, for shareable MCP links).
"""

from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING, Any, Callable, Literal

from django.contrib.auth.models import AnonymousUser
from django.db.models import Count, Q

from opencontractserver.constants.mcp import MAX_THREAD_MESSAGE_LENGTH
from opencontractserver.utils.files import read_field_file_text

from .formatters import (
    format_annotation,
    format_corpus_summary,
    format_document_summary,
    format_message,
    format_message_with_replies,
    format_thread_summary,
)

if TYPE_CHECKING:
    from opencontractserver.users.types import UserOrAnonymous

logger = logging.getLogger(__name__)


def _candidate_fetch_size(limit: int) -> int:
    """Candidate count to fetch per search half before de-duplication.

    Over-fetches ``limit * MCP_SEARCH_CANDIDATE_MULTIPLIER`` (bounded by
    ``MCP_SEARCH_CANDIDATE_MAX``) so duplicate hits removed by
    ``_dedupe_search_hits`` don't starve the final feed below ``limit``.
    """
    from opencontractserver.constants.mcp import (
        MCP_SEARCH_CANDIDATE_MAX,
        MCP_SEARCH_CANDIDATE_MULTIPLIER,
    )

    return min(
        max(limit, 1) * MCP_SEARCH_CANDIDATE_MULTIPLIER, MCP_SEARCH_CANDIDATE_MAX
    )


def _dedupe_search_hits(hits: list[dict]) -> list[dict]:
    """Collapse search hits that resolve to the same annotation or block.

    Passages are keyed by ``annotation_id`` — the annotation->embedding join
    can return one row per stored vector, so the same annotation otherwise
    appears multiple times with an identical score, wasting the caller's
    ``limit`` budget. Blocks (which carry no stable id in the formatted shape)
    are keyed by their content tuple. The first occurrence wins, so callers
    should de-duplicate *after* sorting by score to keep the highest-scoring
    instance. Hits missing an identity fall back to a per-position key so a
    ``None`` id never collapses distinct passages into one.
    """
    seen: set = set()
    deduped: list[dict] = []
    for index, hit in enumerate(hits):
        key: tuple
        if hit.get("type") == "passage":
            annotation_id = hit.get("annotation_id")
            key = ("passage", annotation_id) if annotation_id else ("passage", index)
        else:
            key = (
                "block",
                hit.get("document_slug"),
                hit.get("label"),
                hit.get("text"),
            )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped


def list_public_corpuses(
    limit: int = 20,
    offset: int = 0,
    search: str = "",
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    List corpuses visible to the caller.

    For anonymous callers this is the set of public, published corpuses.
    Authenticated callers additionally see private corpuses they own or
    have been granted access to via the standard visibility rules.

    Args:
        limit: Number of results (default 20, max 100)
        offset: Pagination offset
        search: Optional search filter for title/description

    Returns:
        Dict with total_count and list of corpus summaries
    """
    from opencontractserver.corpuses.models import Corpus

    # Enforce max limit
    limit = min(limit, 100)

    user = user or AnonymousUser()
    qs = Corpus.objects.visible_to_user(user)

    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

    total_count = qs.count()
    corpuses = list(qs[offset : offset + limit])

    return {
        "total_count": total_count,
        "corpuses": [format_corpus_summary(c) for c in corpuses],
    }


def list_documents(
    corpus_slug: str,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    List documents in a public corpus.

    Args:
        corpus_slug: Corpus identifier
        limit: Number of results (default 50, max 100)
        offset: Pagination offset
        search: Optional search filter

    Returns:
        Dict with total_count and list of document summaries
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    limit = min(limit, 100)
    user = user or AnonymousUser()

    # Get corpus (raises Corpus.DoesNotExist if not found or not public)
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    # Use CorpusDocumentService for optimized single-query document retrieval
    # This handles corpus membership and visibility in one query
    qs = CorpusDocumentService.get_corpus_documents(
        user=user, corpus=corpus, include_deleted=False
    )

    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search))

    total_count = qs.count()
    documents = list(qs[offset : offset + limit])

    return {
        "total_count": total_count,
        "documents": [format_document_summary(d) for d in documents],
    }


def get_document_text(
    corpus_slug: str,
    document_slug: str,
    char_offset: int = 0,
    max_chars: int | None = None,
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    Retrieve extracted document text in bounded slices.

    Returns a window of the flat extracted text starting at ``char_offset``.
    Use ``next_offset`` from the response to page through a long document
    rather than pulling the whole thing in one (token-blowing) call. For
    page-targeted reads, use ``search_corpus`` (returns ``page``) and
    ``list_annotations(page=N)`` instead.

    Args:
        corpus_slug: Corpus identifier
        document_slug: Document identifier
        char_offset: Start offset into the extracted text (default 0)
        max_chars: Window size in characters (default
            ``MCP_DOCUMENT_TEXT_DEFAULT_CHARS``, hard-capped at
            ``MCP_DOCUMENT_TEXT_MAX_CHARS``)

    Returns:
        Dict with slug, page_count, total_chars, char_offset, text,
        next_offset (None when the window reaches the end) and truncated.
    """
    from opencontractserver.constants.mcp import (
        MCP_DOCUMENT_TEXT_DEFAULT_CHARS,
        MCP_DOCUMENT_TEXT_MAX_CHARS,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    user = user or AnonymousUser()

    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
    # Route document lookup through CorpusDocumentService so tools.py uses
    # the same permission chain as resources.py (corpus READ gate +
    # corpus membership) and IDOR-safely raises Document.DoesNotExist
    # for slug-misses, hidden corpora, and cross-corpus lookups alike.
    document = CorpusDocumentService.get_corpus_document_by_slug(
        user=user, corpus=corpus, slug=document_slug
    )

    full_text = ""
    if document.txt_extract_file:
        try:
            # errors="replace" so a few undecodable bytes substitute U+FFFD
            # rather than raising UnicodeDecodeError and silently yielding an
            # empty document to the client.
            full_text = read_field_file_text(
                document.txt_extract_file, errors="replace"
            )
        except Exception:
            full_text = ""

    total = len(full_text)
    char_offset = max(0, int(char_offset))
    window = MCP_DOCUMENT_TEXT_DEFAULT_CHARS if max_chars is None else int(max_chars)
    window = max(0, min(window, MCP_DOCUMENT_TEXT_MAX_CHARS))
    end = char_offset + window
    text = full_text[char_offset:end]
    next_offset = end if end < total else None

    return {
        "document_slug": document.slug,
        "page_count": document.page_count or 0,
        "total_chars": total,
        "char_offset": char_offset,
        "text": text,
        "next_offset": next_offset,
        "truncated": next_offset is not None,
    }


def list_annotations(
    corpus_slug: str,
    document_slug: str,
    page: int | None = None,
    label_text: str | None = None,
    text_contains: str | None = None,
    structural: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    List / search annotations on a document with optional filtering.

    Args:
        corpus_slug: Corpus identifier
        document_slug: Document identifier
        page: Optional page number filter
        label_text: Optional exact label-text filter
        text_contains: Optional case-insensitive substring filter on annotation text
        structural: Optional kind filter — None=both, True=structural only,
            False=human/analysis only
        limit: Number of results (max 100)
        offset: Pagination offset

    Returns:
        Dict with total_count and list of annotations (ordered by page)
    """
    from opencontractserver.annotations.services import AnnotationService
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    limit = min(limit, 100)
    user = user or AnonymousUser()

    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
    document = CorpusDocumentService.get_corpus_document_by_slug(
        user=user, corpus=corpus, slug=document_slug
    )

    # Use query optimizer - eliminates N+1 permission queries
    qs = AnnotationService.get_document_annotations(
        document_id=document.id, user=user, corpus_id=corpus.id
    )

    # Apply filters
    if page is not None:
        qs = qs.filter(page=page)

    if label_text:
        qs = qs.filter(annotation_label__text=label_text)

    if text_contains:
        qs = qs.filter(raw_text__icontains=text_contains)

    if structural is not None:
        qs = qs.filter(structural=structural)

    # Stable reading order so an AI can reassemble document flow.
    qs = qs.order_by("page", "id")

    total_count = qs.count()
    annotations = list(qs.select_related("annotation_label")[offset : offset + limit])

    return {
        "total_count": total_count,
        "annotations": [format_annotation(a) for a in annotations],
    }


def list_relationships(
    corpus_slug: str,
    document_slug: str | None = None,
    structural: bool | None = None,
    label_text: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    List labeled source->target relationships in the corpus (or one document).

    Relationships connect annotations (e.g. parent/child, cross-references,
    human- or analysis-drawn edges) and are used to aggregate related content.

    Args:
        corpus_slug: Corpus identifier
        document_slug: Optional document filter (corpus-wide when omitted)
        structural: Optional kind filter — None=both, True=structural only,
            False=human/analysis only
        label_text: Optional exact relationship-label filter
        limit: Number of results (max 100)
        offset: Pagination offset

    Returns:
        Dict with total_count and list of relationships (source/target edges)
    """
    from opencontractserver.annotations.services.relationship_service import (
        RelationshipService,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    from .formatters import format_relationship

    limit = min(limit, 100)
    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    if document_slug:
        document = CorpusDocumentService.get_corpus_document_by_slug(
            user=user, corpus=corpus, slug=document_slug
        )
        qs = RelationshipService.get_document_relationships(
            document_id=document.id,
            user=user,
            corpus_id=corpus.id,
            structural=structural,
        )
    else:
        qs = RelationshipService.get_corpus_relationships(
            corpus_id=corpus.id, user=user, structural=structural
        )

    if label_text:
        qs = qs.filter(relationship_label__text=label_text)

    qs = (
        qs.select_related("relationship_label")
        .prefetch_related("source_annotations", "target_annotations")
        .order_by("id")
    )

    total_count = qs.count()
    relationships = list(qs[offset : offset + limit])

    return {
        "total_count": total_count,
        "relationships": [format_relationship(r) for r in relationships],
    }


def search_corpus(
    corpus_slug: str,
    query: str,
    limit: int = 10,
    granularity: Literal["passage", "block", "both"] = "both",
    structural: bool | None = None,
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    Search a corpus and return a single ranked feed of passages and blocks.

    - ``passage`` hits are annotations (semantic via embeddings, with a text
      fallback when the vector path is empty/absent/errors).
    - ``block`` hits are ``OC_SUBTREE_GROUP`` relationships (an ancestor plus
      its full descendant subtree) — the embedded aggregation unit — via
      ``CoreRelationshipVectorStore``. Blocks are vector-only (no text fallback).

    Args:
        corpus_slug: Corpus identifier
        query: Search query text
        limit: Number of results (max 50)
        granularity: "passage" | "block" | "both" (default "both")
        structural: Passage filter — None=both, True=structural only,
            False=human/analysis only

    Returns:
        Dict with query and a ranked ``results`` list, each tagged ``type``.
    """
    from opencontractserver.annotations.services import AnnotationService
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    from .formatters import format_search_block, format_search_passage

    limit = min(limit, 50)
    # Over-fetch candidates per half so duplicates removed below don't starve
    # the feed below ``limit`` distinct hits.
    candidate_k = _candidate_fetch_size(limit)
    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    embedder_path: str | None = None
    query_vector: list[float] | None = None
    try:
        # embed_text() returns (embedder_path, query_vector) tuple.
        embedder_path, query_vector = corpus.embed_text(query)
    except (ValueError, TypeError, AttributeError, RuntimeError):
        embedder_path, query_vector = None, None

    formatted: list[dict] = []

    # --- passage half (annotations) ---
    if granularity in ("passage", "both"):
        ann_qs = AnnotationService.get_corpus_annotations(
            corpus.id, user, structural=structural
        ).select_related("document", "annotation_label")
        passages: list = []
        if query_vector:
            try:
                passages = list(
                    ann_qs.search_by_embedding(  # type: ignore[attr-defined]
                        query_vector, embedder_path, top_k=candidate_k
                    )
                )
            except (ValueError, TypeError, AttributeError, RuntimeError):
                passages = []
        if not passages:
            # Fall through to text search whenever the vector path yields
            # nothing — fixing the prior "return on empty vector" dead-fallback.
            passages = list(ann_qs.filter(raw_text__icontains=query)[:candidate_k])

        # Structural passages carry document_id=NULL and reach their document
        # only through structural_set; build a corpus-scoped
        # structural_set_id -> (slug, title) lookup so those hits still resolve
        # a navigable document instead of emitting document_slug=None.
        struct_set_ids = {
            a.structural_set_id
            for a in passages
            if a.document_id is None and a.structural_set_id
        }
        struct_doc_lookup: dict[int, tuple[str | None, str]] = {}
        if struct_set_ids:
            for set_id, slug, title in (
                Document.objects.filter(
                    structural_annotation_set_id__in=struct_set_ids,
                    path_records__corpus_id=corpus.id,
                    path_records__is_current=True,
                    path_records__is_deleted=False,
                )
                .values_list("structural_annotation_set_id", "slug", "title")
                .order_by("structural_annotation_set_id", "slug")
                .distinct()
            ):
                # If a structural set maps to multiple corpus documents, pick
                # the first alphabetically by slug — deterministic (guaranteed
                # by the order_by above); the edge case is rare in practice.
                struct_doc_lookup.setdefault(set_id, (slug, title or ""))

        formatted.extend(
            format_search_passage(
                a, getattr(a, "similarity_score", None), struct_doc_lookup
            )
            for a in passages
        )

    # --- block half (subtree-group relationships, vector-only) ---
    if granularity in ("block", "both") and query_vector:
        from opencontractserver.llms.vector_stores.core_relationship_vector_store import (  # noqa: E501
            CoreRelationshipVectorStore,
            RelationshipVectorSearchQuery,
        )

        try:
            store = CoreRelationshipVectorStore(
                user_id=getattr(user, "pk", None),
                corpus_id=corpus.id,
                embedder_path=embedder_path,
                embed_dim=len(query_vector),
            )
            blocks = store.search(
                RelationshipVectorSearchQuery(
                    query_embedding=query_vector, similarity_top_k=candidate_k
                )
            )
            # Bulk-fetch block document slugs/titles in one query to avoid a
            # per-block Document lookup (N+1) inside the formatter.
            block_doc_ids = {b.document_id for b in blocks if b.document_id}
            doc_lookup = {
                pk: (slug, title or "")
                for pk, slug, title in Document.objects.filter(
                    pk__in=block_doc_ids
                ).values_list("id", "slug", "title")
            }
            formatted.extend(format_search_block(b, doc_lookup) for b in blocks)
        except (ValueError, TypeError, AttributeError, RuntimeError):
            pass

    # Merge by score; text-fallback passages (score None) sort last. De-dupe
    # *after* sorting so the highest-scoring instance of each annotation/block
    # survives, then cap at limit.
    formatted.sort(
        key=lambda r: (
            r["similarity_score"] is not None,
            r["similarity_score"] if r["similarity_score"] is not None else 0.0,
        ),
        reverse=True,
    )
    deduped = _dedupe_search_hits(formatted)
    return {"query": query, "results": deduped[:limit]}


def list_threads(
    corpus_slug: str,
    document_slug: str | None = None,
    limit: int = 20,
    offset: int = 0,
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    List discussion threads in a corpus or document.

    Args:
        corpus_slug: Corpus identifier
        document_slug: Optional document filter
        limit: Number of results (max 100)
        offset: Pagination offset

    Returns:
        Dict with total_count and list of thread summaries
    """
    from opencontractserver.conversations.models import (
        Conversation,
        ConversationTypeChoices,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    limit = min(limit, 100)
    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    qs = (
        Conversation.objects.visible_to_user(user)
        .filter(
            conversation_type=ConversationTypeChoices.THREAD, chat_with_corpus=corpus
        )
        .annotate(message_count=Count("chat_messages"))
    )

    if document_slug:
        document = CorpusDocumentService.get_corpus_document_by_slug(
            user=user, corpus=corpus, slug=document_slug
        )
        qs = qs.filter(chat_with_document=document)

    # Order by pinned first, then recent activity
    qs = qs.order_by("-is_pinned", "-modified")

    total_count = qs.count()
    threads = list(qs[offset : offset + limit])

    return {
        "total_count": total_count,
        "threads": [format_thread_summary(t) for t in threads],
    }


def get_thread_messages(
    corpus_slug: str,
    thread_id: int,
    flatten: bool = False,
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    Retrieve all messages in a thread with hierarchical structure.

    Args:
        corpus_slug: Corpus identifier
        thread_id: Thread identifier
        flatten: If True, return flat list instead of tree

    Returns:
        Dict with thread_id, title, and messages
    """
    from django.core.exceptions import ObjectDoesNotExist

    from opencontractserver.conversations.models import (
        ChatMessage,
        Conversation,
        ConversationTypeChoices,
    )
    from opencontractserver.corpuses.models import Corpus

    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    thread = (
        Conversation.objects.visible_to_user(user)
        .filter(
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=corpus,
            id=thread_id,
        )
        .first()
    )

    if not thread:
        raise ObjectDoesNotExist(f"Thread {thread_id} not found")

    if flatten:
        messages = list(
            ChatMessage.objects.visible_to_user(user)
            .filter(conversation=thread)
            .order_by("created_at")
        )
        return {
            "thread_id": str(thread.id),
            "title": thread.title or "",
            "messages": [format_message(m) for m in messages],
        }

    # Build hierarchical structure with prefetch
    root_messages = list(
        ChatMessage.objects.visible_to_user(user)
        .filter(conversation=thread, parent_message__isnull=True)
        .prefetch_related("replies__replies")
        .order_by("created_at")
    )

    return {
        "thread_id": str(thread.id),
        "title": thread.title or "",
        "messages": [format_message_with_replies(m, user) for m in root_messages],
    }


def create_thread_message(
    corpus_slug: str,
    thread_id: int,
    content: str,
    parent_message_id: int | None = None,
    user: UserOrAnonymous | None = None,
) -> dict:
    """Create a message in an existing thread (authenticated users only).

    Permission model: write access intentionally piggybacks on read
    visibility — any user who can ``visible_to_user`` the corpus and thread
    may post into it. This mirrors the existing GraphQL ``ChatMessage``
    contract: thread visibility (public corpus / public thread / shared
    thread / owner) implies the right to contribute. Callers that need
    stricter gating (e.g. read-only spectators) should use a private
    corpus / thread or a separate role layer; this tool deliberately does
    not introduce a write-only permission check.

    Raises:
        PermissionDenied: caller is anonymous.
        ValidationError: content is blank or exceeds
            ``MAX_THREAD_MESSAGE_LENGTH``.
        Conversation.DoesNotExist / Corpus.DoesNotExist / ChatMessage.DoesNotExist:
            the corpus, thread, or parent is not visible to the caller.
    """
    from django.core.exceptions import PermissionDenied, ValidationError

    from opencontractserver.conversations.models import (
        ChatMessage,
        Conversation,
        ConversationTypeChoices,
        MessageTypeChoices,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.tasks.agent_tasks import trigger_agent_responses_for_message
    from opencontractserver.types.enums import PermissionTypes
    from opencontractserver.utils.mention_parser import (
        link_message_to_resources,
        parse_mentions_from_content,
    )
    from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

    if user is None or isinstance(user, AnonymousUser):
        raise PermissionDenied("Authentication required for write tools")

    # Validate and persist on the *stripped* value so the validation
    # boundary and the stored row agree. Previously a "   hello   " input
    # passed the strip-only emptiness check but was saved with the original
    # leading/trailing whitespace, which created subtle UI drift and a hard
    # diff between what the tool validated and what other readers later saw.
    normalized = content.strip() if content else ""
    if not normalized:
        raise ValidationError("Message content must not be empty")
    if len(normalized) > MAX_THREAD_MESSAGE_LENGTH:
        raise ValidationError(
            f"Message content exceeds maximum length of "
            f"{MAX_THREAD_MESSAGE_LENGTH} characters"
        )

    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
    thread = Conversation.objects.visible_to_user(user).get(
        id=thread_id,
        conversation_type=ConversationTypeChoices.THREAD,
        chat_with_corpus=corpus,
    )
    if thread.is_locked:
        raise PermissionDenied("This thread is locked")

    parent = None
    if parent_message_id is not None:
        # visible_to_user + ``conversation=thread`` together protect against
        # IDOR: a parent id from another (even visible) thread, or a parent
        # the caller cannot see, surfaces as ChatMessage.DoesNotExist rather
        # than being silently accepted.
        parent = ChatMessage.objects.visible_to_user(user).get(
            id=parent_message_id, conversation=thread
        )

    message = ChatMessage.objects.create(
        conversation=thread,
        msg_type=MessageTypeChoices.HUMAN,
        content=normalized,
        creator=user,
        parent_message=parent,
    )
    set_permissions_for_obj_to_user(user, message, [PermissionTypes.CRUD])

    try:
        mentioned_ids = parse_mentions_from_content(normalized)
        link_result = link_message_to_resources(message, mentioned_ids)
        if link_result.get("agents_linked", 0) > 0:
            trigger_agent_responses_for_message.delay(
                message_id=message.pk,
                user_id=user.pk,
            )
    except Exception as e:
        # Fire-and-forget: the message row is already saved, so a broker
        # hiccup or mention-parser hiccup must not fail the write. Log at
        # ``warning`` rather than ``error`` so a temporarily-unavailable
        # broker doesn't pollute error dashboards on every send.
        logger.warning("Error parsing mentions in MCP message: %s", e)

    return {
        "id": str(message.id),
        "thread_id": str(thread.id),
        "content": message.content,
        "parent_message_id": (
            str(message.parent_message_id) if message.parent_message_id else None
        ),
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


# =============================================================================
# CORPUS-SCOPED TOOL SUPPORT
# =============================================================================
# These functions support corpus-scoped MCP endpoints where a corpus_slug is
# pre-defined in the URL (e.g., /mcp/corpus/{corpus_slug}/) and automatically
# injected into tool calls.


def get_corpus_info(corpus_slug: str, user: UserOrAnonymous | None = None) -> dict:
    """
    Get detailed information about the scoped corpus.

    This is the scoped equivalent of list_public_corpuses - instead of listing
    all corpuses, it returns detailed information about the single scoped corpus.

    Args:
        corpus_slug: Corpus identifier (injected from scoped endpoint)
        user: Optional authenticated user; defaults to AnonymousUser.

    Returns:
        Dict with detailed corpus information including label set
    """
    from opencontractserver.annotations.services import AnnotationService
    from opencontractserver.corpuses.models import Corpus

    user = user or AnonymousUser()
    # Use select_related for label_set and prefetch_related for annotation_labels
    # to avoid N+1 queries when accessing label data
    corpus = (
        Corpus.objects.visible_to_user(user)
        .select_related("label_set")
        .prefetch_related("label_set__annotation_labels")
        .get(slug=corpus_slug)
    )

    # Get label set info if available. Only surface labels that are ACTUALLY
    # used on this corpus's annotations — the seeded "Default Labels" set
    # otherwise advertises dozens of irrelevant labels and misleads an AI
    # about what the `label_text` filter can match.
    label_set_data = None
    if corpus.label_set:
        used_label_ids = set(
            AnnotationService.get_corpus_annotations(corpus.id, user)
            .exclude(annotation_label__isnull=True)
            .values_list("annotation_label_id", flat=True)
            .distinct()
        )
        labels = []
        # Iterate the label set's labels, keeping only those actually in use
        # (filtered against ``used_label_ids`` above). Capped at 50.
        for label in corpus.label_set.annotation_labels.all():
            if label.id not in used_label_ids:
                continue
            labels.append(
                {
                    "text": label.text,
                    "color": label.color or "#000000",
                    "label_type": label.label_type,
                    "description": label.description or "",
                }
            )
            if len(labels) >= 50:
                break
        label_set_data = {
            "title": corpus.label_set.title or "",
            "description": corpus.label_set.description or "",
            "labels": labels,
        }

    return {
        "slug": corpus.slug,
        "title": corpus.title,
        "description": corpus.description or "",
        "document_count": corpus.document_count(),
        "created": corpus.created.isoformat() if corpus.created else None,
        "modified": corpus.modified.isoformat() if corpus.modified else None,
        "label_set": label_set_data,
        "allow_comments": corpus.allow_comments,
    }


def create_scoped_tool_wrapper(
    tool_func: Callable[..., Any],
    corpus_slug: str,
    corpus_slug_param: str = "corpus_slug",
) -> Callable[..., Any]:
    """
    Create a wrapper function that auto-injects corpus_slug into tool calls.

    This allows scoped MCP endpoints to use the same tool implementations
    while automatically providing the corpus context.

    Args:
        tool_func: The original tool function
        corpus_slug: The corpus slug to inject
        corpus_slug_param: The parameter name for corpus_slug (default: "corpus_slug")

    Returns:
        Wrapped function that auto-injects corpus_slug
    """

    @functools.wraps(tool_func)
    def wrapper(**kwargs: Any) -> Any:
        # Always inject the scoped corpus_slug, ignoring any provided value
        kwargs[corpus_slug_param] = corpus_slug
        return tool_func(**kwargs)

    # ``functools.wraps`` sets ``__wrapped__`` to ``tool_func`` so
    # ``inspect.signature(wrapper)`` resolves to the real tool signature (not
    # ``(**kwargs)``). The dispatcher's argument validation relies on this to
    # reject unknown arguments for scoped tools as well as global ones.
    return wrapper


def get_scoped_tool_handlers(corpus_slug: str) -> dict[str, Callable[..., Any]]:
    """
    Get tool handlers for a corpus-scoped MCP endpoint.

    Returns a mapping of tool names to handler functions where corpus_slug
    is automatically injected.

    Args:
        corpus_slug: The corpus slug to scope all tools to

    Returns:
        Dict mapping tool names to scoped handler functions
    """
    return {
        # Scoped version: returns info about this specific corpus
        "get_corpus_info": create_scoped_tool_wrapper(get_corpus_info, corpus_slug),
        # These tools have corpus_slug auto-injected
        "list_documents": create_scoped_tool_wrapper(list_documents, corpus_slug),
        "get_document_text": create_scoped_tool_wrapper(get_document_text, corpus_slug),
        "list_annotations": create_scoped_tool_wrapper(list_annotations, corpus_slug),
        "list_relationships": create_scoped_tool_wrapper(
            list_relationships, corpus_slug
        ),
        "search_corpus": create_scoped_tool_wrapper(search_corpus, corpus_slug),
        "list_threads": create_scoped_tool_wrapper(list_threads, corpus_slug),
        "get_thread_messages": create_scoped_tool_wrapper(
            get_thread_messages, corpus_slug
        ),
        # Write tool: corpus_slug is pre-validated by the scoped endpoint and
        # injected automatically. Authentication is still enforced inside the
        # tool (anonymous callers raise PermissionDenied).
        "create_thread_message": create_scoped_tool_wrapper(
            create_thread_message, corpus_slug
        ),
    }
