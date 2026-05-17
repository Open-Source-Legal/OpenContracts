"""MCP Resource handlers for OpenContracts.

Resources provide static content for context windows, representing specific entities.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from django.contrib.auth.models import AnonymousUser

if TYPE_CHECKING:
    from opencontractserver.users.types import UserOrAnonymous


def get_corpus_resource(corpus_slug: str, user: UserOrAnonymous | None = None) -> str:
    """
    Get corpus resource content.

    URI: corpus://{corpus_slug}
    Returns: JSON with corpus metadata and summary statistics
    """
    from opencontractserver.corpuses.models import Corpus

    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

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


def get_document_resource(
    corpus_slug: str, document_slug: str, user: UserOrAnonymous | None = None
) -> str:
    """
    Get document resource content.

    URI: document://{corpus_slug}/{document_slug}
    Returns: JSON with document metadata and extracted text

    Note: Document membership is resolved through DocumentFolderService so
    corpus read access and current DocumentPath state are enforced consistently
    with list_documents.
    """
    from opencontractserver.corpuses.folder_service import DocumentFolderService
    from opencontractserver.corpuses.models import Corpus

    user = user or AnonymousUser()

    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    # Get document in corpus via DocumentPath (source of truth)
    document = DocumentFolderService.get_corpus_documents(
        user=user, corpus=corpus, include_deleted=False
    ).get(slug=document_slug)

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
    corpus_slug: str,
    document_slug: str,
    annotation_id: int,
    user: UserOrAnonymous | None = None,
) -> str:
    """
    Get annotation resource content.

    URI: annotation://{corpus_slug}/{document_slug}/{annotation_id}
    Returns: JSON with annotation details including label and bounding box

    Note: Document membership is resolved through DocumentFolderService, then
    annotations are filtered through AnnotationQueryOptimizer's effective
    permission checks.
    """
    from opencontractserver.annotations.query_optimizer import AnnotationQueryOptimizer
    from opencontractserver.corpuses.folder_service import DocumentFolderService
    from opencontractserver.corpuses.models import Corpus

    user = user or AnonymousUser()

    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    # Get document in corpus via DocumentPath (source of truth)
    document = DocumentFolderService.get_corpus_documents(
        user=user, corpus=corpus, include_deleted=False
    ).get(slug=document_slug)

    # Use query optimizer for efficient permission checking
    annotations = AnnotationQueryOptimizer.get_document_annotations(
        document_id=document.id, user=user, corpus_id=corpus.id
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
    corpus_slug: str,
    thread_id: int,
    include_messages: bool = True,
    user: UserOrAnonymous | None = None,
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
            ChatMessage.objects.visible_to_user(user)
            .filter(conversation=thread, parent_message__isnull=True)
            .prefetch_related("replies__replies")
            .order_by("created_at")
        )
        data["messages"] = [format_message_with_replies(msg, user) for msg in messages]

    return json.dumps(data)
