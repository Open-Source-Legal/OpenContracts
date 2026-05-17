"""MCP Tool implementations for OpenContracts.

Tools provide dynamic operations - they execute queries and return results.
Supports both global mode (all public corpuses) and corpus-scoped mode
(single corpus, for shareable MCP links).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from django.contrib.auth.models import AnonymousUser
from django.db.models import Count, Q

from opencontractserver.constants.mcp import MAX_THREAD_MESSAGE_LENGTH

from .formatters import (
    format_annotation,
    format_corpus_summary,
    format_document_summary,
    format_message,
    format_message_with_replies,
    format_thread_summary,
)

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.users.types import UserOrAnonymous

logger = logging.getLogger(__name__)


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
    from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
    from opencontractserver.corpuses.models import Corpus

    limit = min(limit, 100)
    user = user or AnonymousUser()

    # Get corpus (raises Corpus.DoesNotExist if not found or not public)
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    # Use CorpusObjsService for optimized single-query document retrieval
    # This handles corpus membership and visibility in one query
    qs = CorpusObjsService.get_corpus_documents(
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
    corpus_slug: str, document_slug: str, user: UserOrAnonymous | None = None
) -> dict:
    """
    Retrieve full extracted text from a document.

    Args:
        corpus_slug: Corpus identifier
        document_slug: Document identifier

    Returns:
        Dict with document slug, page count, and full text
    """
    from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
    from opencontractserver.corpuses.models import Corpus

    user = user or AnonymousUser()

    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
    # Route document lookup through CorpusObjsService so tools.py uses
    # the same permission chain as resources.py (corpus READ gate +
    # corpus membership) and IDOR-safely raises Document.DoesNotExist
    # for slug-misses, hidden corpora, and cross-corpus lookups alike.
    document = CorpusObjsService.get_corpus_document_by_slug(
        user=user, corpus=corpus, slug=document_slug
    )

    full_text = ""
    if document.txt_extract_file:
        try:
            with document.txt_extract_file.open("r") as f:
                full_text = f.read()
        except Exception:
            full_text = ""

    return {
        "document_slug": document.slug,
        "page_count": document.page_count or 0,
        "text": full_text,
    }


def list_annotations(
    corpus_slug: str,
    document_slug: str,
    page: int | None = None,
    label_text: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user: UserOrAnonymous | None = None,
) -> dict:
    """
    List annotations on a document with optional filtering.

    Args:
        corpus_slug: Corpus identifier
        document_slug: Document identifier
        page: Optional page number filter
        label_text: Optional label text filter
        limit: Number of results (max 100)
        offset: Pagination offset

    Returns:
        Dict with total_count and list of annotations
    """
    from opencontractserver.annotations.query_optimizer import AnnotationQueryOptimizer
    from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
    from opencontractserver.corpuses.models import Corpus

    limit = min(limit, 100)
    user = user or AnonymousUser()

    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
    document = CorpusObjsService.get_corpus_document_by_slug(
        user=user, corpus=corpus, slug=document_slug
    )

    # Use query optimizer - eliminates N+1 permission queries
    qs = AnnotationQueryOptimizer.get_document_annotations(
        document_id=document.id, user=user, corpus_id=corpus.id
    )

    # Apply filters
    if page is not None:
        qs = qs.filter(page=page)

    if label_text:
        qs = qs.filter(annotation_label__text=label_text)

    total_count = qs.count()
    annotations = list(qs.select_related("annotation_label")[offset : offset + limit])

    return {
        "total_count": total_count,
        "annotations": [format_annotation(a) for a in annotations],
    }


def search_corpus(
    corpus_slug: str, query: str, limit: int = 10, user: UserOrAnonymous | None = None
) -> dict:
    """
    Semantic search within a corpus using vector embeddings.

    Falls back to text search if embeddings are unavailable.

    Args:
        corpus_slug: Corpus identifier
        query: Search query text
        limit: Number of results (max 50)

    Returns:
        Dict with query and ranked results
    """
    from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
    from opencontractserver.corpuses.models import Corpus

    limit = min(limit, 50)
    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    # Try to use vector search
    try:
        # embed_text() returns (embedder_path, query_vector) tuple
        embedder_path, query_vector = corpus.embed_text(query)

        if query_vector:
            # Single canonical entry point: corpus-as-gate doc set for this user.
            doc_results = list(
                CorpusObjsService.get_corpus_documents(
                    user=user, corpus=corpus
                ).search_by_embedding(  # type: ignore[attr-defined]
                    query_vector, embedder_path, top_k=limit
                )
            )

            results = []
            for doc in doc_results:
                results.append(
                    {
                        "type": "document",
                        "slug": doc.slug,
                        "title": doc.title or "",
                        "similarity_score": float(getattr(doc, "similarity_score", 0)),
                    }
                )

            return {"query": query, "results": results}
    except (ValueError, TypeError, AttributeError):
        # Expected when embeddings are not configured or embed_text returns invalid data
        pass
    except RuntimeError as e:
        # Embedding service or model loading errors
        import logging

        logging.getLogger(__name__).debug(f"Vector search unavailable: {e}")

    # Fallback to text search
    return _text_search_fallback(corpus, query, limit, user)


def _text_search_fallback(
    corpus: Corpus, query: str, limit: int, user: UserOrAnonymous
) -> dict:
    """Fallback to text search when embeddings are unavailable."""
    from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService

    # Single canonical entry point: corpus-as-gate doc set for this user.
    documents = list(
        CorpusObjsService.get_corpus_documents(user=user, corpus=corpus).filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )[:limit]
    )

    results = []
    for doc in documents:
        results.append(
            {
                "type": "document",
                "slug": doc.slug,
                "title": doc.title or "",
                "similarity_score": None,
            }
        )

    return {"query": query, "results": results}


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
    from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
    from opencontractserver.corpuses.models import Corpus

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
        document = CorpusObjsService.get_corpus_document_by_slug(
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

    # Get label set info if available
    label_set_data = None
    if corpus.label_set:
        labels = []
        # annotation_labels is already prefetched, slicing in Python to avoid new query
        for label in list(corpus.label_set.annotation_labels.all())[:50]:
            labels.append(
                {
                    "text": label.text,
                    "color": label.color or "#000000",
                    "label_type": label.label_type,
                    "description": label.description or "",
                }
            )
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

    def wrapper(**kwargs: Any) -> Any:
        # Always inject the scoped corpus_slug, ignoring any provided value
        kwargs[corpus_slug_param] = corpus_slug
        return tool_func(**kwargs)

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
