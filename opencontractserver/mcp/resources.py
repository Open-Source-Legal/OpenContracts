"""MCP Resource handlers for OpenContracts.

Resources provide static content for context windows, representing specific entities.
"""

from __future__ import annotations

import json

from django.contrib.auth.models import AnonymousUser


def get_corpus_resource(corpus_slug: str) -> str:
    """
    Get corpus resource content.

    URI: corpus://{corpus_slug}
    Returns: JSON with corpus metadata and summary statistics
    """
    from opencontractserver.corpuses.models import Corpus

    anonymous = AnonymousUser()
    corpus = Corpus.objects.visible_to_user(anonymous).get(slug=corpus_slug)

    # Get label set info if available
    label_set_data = None
    if corpus.label_set:
        labels = []
        for label in corpus.label_set.annotation_labels.all()[:20]:  # Limit labels
            labels.append(
                {
                    "text": label.text,
                    "color": label.color or "#000000",
                    "label_type": label.label_type,
                }
            )
        label_set_data = {
            "title": corpus.label_set.title or "",
            "labels": labels,
        }

    return json.dumps(
        {
            "slug": corpus.slug,
            "title": corpus.title,
            "description": corpus.description or "",
            "document_count": corpus.document_count(),
            "created": corpus.created.isoformat() if corpus.created else None,
            "modified": corpus.modified.isoformat() if corpus.modified else None,
            "label_set": label_set_data,
        }
    )


def get_document_resource(corpus_slug: str, document_slug: str) -> str:
    """
    Get document resource content.

    URI: document://{corpus_slug}/{document_slug}
    Returns: JSON with document metadata and extracted text

    Note: Documents are accessible if they're in a public corpus, even if the
    document itself isn't marked public. The corpus visibility acts as the
    permission gate.
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    anonymous = AnonymousUser()

    # Get corpus context - this validates corpus is visible to anonymous
    corpus = Corpus.objects.visible_to_user(anonymous).get(slug=corpus_slug)

    # Get document in corpus via DocumentPath (source of truth)
    # Since corpus is visible to anonymous, documents in it are accessible
    # through the corpus relationship (corpus acts as permission gate)
    document = corpus.get_documents().filter(slug=document_slug).first()

    if not document:
        raise Document.DoesNotExist(
            f"Document '{document_slug}' not found in corpus '{corpus_slug}'"
        )

    # Read extracted text
    full_text = ""
    if document.txt_extract_file:
        try:
            with document.txt_extract_file.open("r") as f:
                full_text = f.read()
        except Exception:
            full_text = ""

    return json.dumps(
        {
            "slug": document.slug,
            "title": document.title or "",
            "description": document.description or "",
            "file_type": document.file_type or "application/pdf",
            "page_count": document.page_count or 0,
            "text_preview": full_text[:500] if full_text else "",
            "full_text": full_text,
            "created": document.created.isoformat() if document.created else None,
            "corpus": corpus_slug,
        }
    )


def get_annotation_resource(
    corpus_slug: str, document_slug: str, annotation_id: int
) -> str:
    """
    Get annotation resource content.

    URI: annotation://{corpus_slug}/{document_slug}/{annotation_id}
    Returns: JSON with annotation details including label and bounding box

    Note: Annotations are accessible if they're in a document within a public
    corpus. The corpus visibility acts as the permission gate.
    """
    from opencontractserver.annotations.query_optimizer import AnnotationQueryOptimizer
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    anonymous = AnonymousUser()

    # Get corpus context - this validates corpus is visible to anonymous
    corpus = Corpus.objects.visible_to_user(anonymous).get(slug=corpus_slug)

    # Get document in corpus via DocumentPath (source of truth)
    # Since corpus is visible to anonymous, documents in it are accessible
    document = corpus.get_documents().filter(slug=document_slug).first()

    if not document:
        raise Document.DoesNotExist(
            f"Document '{document_slug}' not found in corpus '{corpus_slug}'"
        )

    # Use query optimizer for efficient permission checking
    annotations = AnnotationQueryOptimizer.get_document_annotations(
        document_id=document.id, user=anonymous, corpus_id=corpus.id
    )

    annotation = annotations.get(id=annotation_id)

    # Format label data
    label_data = None
    if annotation.annotation_label:
        label_data = {
            "text": annotation.annotation_label.text,
            "color": annotation.annotation_label.color or "#000000",
            "label_type": annotation.annotation_label.label_type,
        }

    return json.dumps(
        {
            "id": str(annotation.id),
            "page": annotation.page,
            "raw_text": annotation.raw_text or "",
            "annotation_label": label_data,
            "json": annotation.json,
            "structural": annotation.structural,
            "created": annotation.created.isoformat() if annotation.created else None,
        }
    )


def get_thread_resource(
    corpus_slug: str, thread_id: int, include_messages: bool = True
) -> str:
    """
    Get thread resource content.

    URI: thread://{corpus_slug}/threads/{thread_id}
    Returns: JSON with thread metadata and optionally messages
    """
    from opencontractserver.conversations.models import (
        ChatMessage,
        Conversation,
        ConversationTypeChoices,
    )
    from opencontractserver.corpuses.models import Corpus

    from .formatters import format_message_with_replies

    anonymous = AnonymousUser()
    corpus = Corpus.objects.visible_to_user(anonymous).get(slug=corpus_slug)

    # Get public thread in this corpus
    thread = (
        Conversation.objects.visible_to_user(anonymous)
        .filter(
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=corpus,
            id=thread_id,
        )
        .first()
    )

    if not thread:
        raise Conversation.DoesNotExist(
            f"Thread '{thread_id}' not found in corpus '{corpus_slug}'"
        )

    data = {
        "id": str(thread.id),
        "title": thread.title or "",
        "description": thread.description or "",
        "is_locked": thread.is_locked,
        "is_pinned": thread.is_pinned,
        "created_at": thread.created.isoformat() if thread.created else None,
    }

    if include_messages:
        # Build hierarchical message structure with prefetch
        messages = list(
            ChatMessage.objects.visible_to_user(anonymous)
            .filter(conversation=thread, parent_message__isnull=True)
            .prefetch_related("replies__replies")
            .order_by("created_at")
        )
        data["messages"] = [
            format_message_with_replies(msg, anonymous) for msg in messages
        ]

    return json.dumps(data)
