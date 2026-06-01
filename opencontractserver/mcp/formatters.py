"""Response formatters for MCP resources and tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opencontractserver.annotations.models import Annotation, Relationship
    from opencontractserver.conversations.models import ChatMessage, Conversation
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document
    from opencontractserver.llms.vector_stores.core_relationship_vector_store import (
        RelationshipVectorSearchResult,
    )


def _truncate(text: str, max_chars: int) -> str:
    """Bound a string for AI-facing payloads, marking elision."""
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " …[truncated]"


def format_corpus_summary(corpus: Corpus) -> dict:
    """Format a corpus for list display."""
    return {
        "slug": corpus.slug,
        "title": corpus.title,
        "description": corpus.description or "",
        "document_count": (
            corpus.document_count() if hasattr(corpus, "document_count") else 0
        ),
        "created": corpus.created.isoformat() if corpus.created else None,
    }


def format_document_summary(document: Document) -> dict:
    """Format a document for list display."""
    return {
        "slug": document.slug,
        "title": document.title or "",
        "description": document.description or "",
        "page_count": document.page_count or 0,
        "file_type": document.file_type or "unknown",
        "created": document.created.isoformat() if document.created else None,
    }


def format_annotation(annotation: Annotation) -> dict:
    """Format an annotation for API response (lean, AI-facing shape).

    Drops ``color`` and ``created`` (low signal, high token cost for an AI
    consumer). The ``structural`` flag is retained so callers can always
    delineate layout-derived chunks from human/analysis annotations.
    """
    label_data = None
    if annotation.annotation_label:
        label_data = {
            "text": annotation.annotation_label.text,
            "label_type": annotation.annotation_label.label_type,
        }

    return {
        "id": str(annotation.id),
        "page": annotation.page,
        "raw_text": annotation.raw_text or "",
        "annotation_label": label_data,
        "structural": annotation.structural,
    }


def format_search_passage(
    annotation: Annotation,
    similarity_score: float | None = None,
    struct_doc_lookup: dict[int, tuple[str | None, str]] | None = None,
) -> dict:
    """Format an annotation as a passage-level search hit.

    Document-attached annotations resolve their document via the ``document``
    FK. Structural annotations carry ``document_id=NULL`` and reach their
    document only through ``structural_set`` (mirrored by the document's
    ``structural_annotation_set``); for those, callers must pass a
    ``struct_doc_lookup`` mapping ``structural_set_id -> (slug, title)``.
    The lookup is supplied (rather than resolved lazily) because a structural
    set can be shared across documents/corpuses, so the slug must be picked
    within the caller's corpus scope — an unscoped lookup could mislabel the
    hit with a document from another corpus. Without the lookup a structural
    hit reports ``document_slug=None`` (prior behaviour, preserved).
    """
    from opencontractserver.constants.mcp import MCP_SEARCH_SNIPPET_MAX_CHARS

    structural_set_id: int | None = getattr(annotation, "structural_set_id", None)
    if annotation.document_id:
        doc = annotation.document
        doc_slug = doc.slug if doc else None
        doc_title = (doc.title or "") if doc else ""
    elif struct_doc_lookup and structural_set_id is not None:
        doc_slug, doc_title = struct_doc_lookup.get(structural_set_id, (None, ""))
    else:
        doc_slug, doc_title = None, ""

    return {
        "type": "passage",
        # ``annotation_id`` bridges a search hit back to the underlying
        # annotation: callers can read it via the ``annotation://`` resource or
        # cross-reference ``list_annotations``. It is also the stable identity
        # ``search_corpus`` dedupes on (the annotation→embedding join can
        # surface the same annotation once per stored vector). Matches the
        # ``annotation_id`` key used by ``format_relationship`` nodes.
        "annotation_id": str(annotation.id),
        "document_slug": doc_slug,
        "document_title": doc_title,
        "page": annotation.page,
        "text": _truncate(annotation.raw_text or "", MCP_SEARCH_SNIPPET_MAX_CHARS),
        "structural": annotation.structural,
        "similarity_score": (
            float(similarity_score) if similarity_score is not None else None
        ),
    }


def format_search_block(
    result: RelationshipVectorSearchResult,
    doc_lookup: dict[int, tuple[str | None, str]] | None = None,
) -> dict:
    """Format a ``RelationshipVectorSearchResult`` as a block-level search hit.

    ``result`` already carries ``block_text``, ``label_text``, ``document_id``
    and member ids, so only a light document slug/title lookup is needed.

    Callers formatting many blocks (e.g. ``search_corpus``) should pass a
    pre-fetched ``doc_lookup`` mapping ``document_id -> (slug, title)`` to avoid
    a per-block ``Document`` query (N+1). When omitted, the slug/title is looked
    up lazily so single-block callers stay correct.
    """
    from opencontractserver.constants.mcp import MCP_BLOCK_SNIPPET_MAX_CHARS
    from opencontractserver.documents.models import Document

    doc_slug, doc_title = None, ""
    if result.document_id:
        if doc_lookup is not None:
            doc_slug, doc_title = doc_lookup.get(result.document_id, (None, ""))
        else:
            doc = (
                Document.objects.filter(pk=result.document_id)
                .only("slug", "title")
                .first()
            )
            if doc:
                doc_slug, doc_title = doc.slug, (doc.title or "")

    member_count = (1 if result.source_annotation_id else 0) + len(
        result.target_annotation_ids
    )
    return {
        "type": "block",
        "document_slug": doc_slug,
        "document_title": doc_title,
        "page": None,
        "label": result.label_text,
        "text": _truncate(result.block_text or "", MCP_BLOCK_SNIPPET_MAX_CHARS),
        "member_count": member_count,
        "similarity_score": float(result.similarity_score),
    }


def format_relationship(rel: Relationship) -> dict:
    """Format a ``Relationship`` as labeled source->target edges."""
    from opencontractserver.constants.mcp import MCP_REL_ANNOTATION_TEXT_MAX_CHARS

    def _node(a: Annotation) -> dict:
        return {
            "annotation_id": str(a.id),
            "page": a.page,
            "text": _truncate(a.raw_text or "", MCP_REL_ANNOTATION_TEXT_MAX_CHARS),
        }

    label = rel.relationship_label if rel.relationship_label_id else None
    return {
        "id": str(rel.id),
        "label": label.text if label else None,
        "structural": rel.structural,
        "source": [_node(a) for a in rel.source_annotations.all()],
        "target": [_node(a) for a in rel.target_annotations.all()],
    }


def format_thread_summary(thread: Conversation) -> dict:
    """Format a thread for list display."""
    return {
        "id": str(thread.id),
        "title": thread.title or "",
        "description": thread.description or "",
        "message_count": getattr(thread, "message_count", 0),
        "is_pinned": thread.is_pinned,
        "is_locked": thread.is_locked,
        "created_at": thread.created.isoformat() if thread.created else None,
        "last_activity": thread.modified.isoformat() if thread.modified else None,
    }


def format_message(message: ChatMessage) -> dict:
    """Format a single message without replies."""
    return {
        "id": str(message.id),
        "content": message.content,
        "msg_type": message.msg_type,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "upvote_count": message.upvote_count,
        "downvote_count": message.downvote_count,
    }


def format_message_with_replies(
    message: ChatMessage, user, max_depth: int = 3, current_depth: int = 0
) -> dict:
    """
    Format a message with its replies recursively.

    Uses prefetched replies to avoid N+1 queries.
    Limits recursion depth to prevent deeply nested structures.
    """
    formatted = format_message(message)

    if current_depth >= max_depth:
        formatted["replies"] = []
        formatted["has_more_replies"] = (
            message.replies.exists() if hasattr(message, "replies") else False
        )
        return formatted

    # Access prefetched replies (no additional queries if prefetched)
    replies = list(message.replies.all()) if hasattr(message, "replies") else []

    formatted["replies"] = [
        format_message_with_replies(reply, user, max_depth, current_depth + 1)
        for reply in replies
    ]

    return formatted
