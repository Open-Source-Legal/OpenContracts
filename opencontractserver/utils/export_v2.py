"""
Export utilities for V2 corpus export format.

Handles export of new features added since original export design:
- Corpus folders hierarchy
- DocumentPath version trees
- Relationships (including structural)
- Agent configurations
- Markdown descriptions with revisions
- Conversations and messages (optional)

Note: StructuralAnnotationSet was removed in favor of direct structural annotations
on documents (identified by structural=True flag).
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db.models import Q

from opencontractserver.annotations.models import Relationship
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusDescriptionRevision,
)
from opencontractserver.documents.models import DocumentPath
from opencontractserver.types.dicts import (
    AgentConfigExport,
    CorpusFolderExport,
    DescriptionRevisionExport,
    DocumentPathExport,
    OpenContractsRelationshipPythonType,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


def package_corpus_folders(corpus: Corpus) -> list[CorpusFolderExport]:
    """
    Package corpus folder hierarchy for export.

    Exports folders in depth-first order with full paths for easy reconstruction.

    Args:
        corpus: Corpus instance

    Returns:
        List of CorpusFolderExport dicts
    """
    folders_export = []

    try:
        # Get all folders for this corpus, ordered by ID (parents before children)
        folders = corpus.folders.all().order_by("id")

        # Build export ID mapping (db_id -> export_id)
        folder_id_map = {}

        for folder in folders:
            # Use DB ID as export ID (simpler than generating new IDs)
            export_id = str(folder.id)
            folder_id_map[folder.id] = export_id

            # Get full path
            path = folder.get_path()

            # Get parent export ID
            parent_export_id = None
            if folder.parent_id:
                parent_export_id = folder_id_map.get(folder.parent_id)

            folders_export.append(
                {
                    "id": export_id,
                    "name": folder.name,
                    "description": folder.description,
                    "color": folder.color,
                    "icon": folder.icon,
                    "tags": folder.tags,
                    "is_public": folder.is_public,
                    "parent_id": parent_export_id,
                    "path": path,
                }
            )

    except Exception as e:
        logger.error(f"Error packaging corpus folders for corpus {corpus.id}: {e}")

    return folders_export


def package_document_paths(corpus: Corpus) -> list[DocumentPathExport]:
    """
    Package DocumentPath version trees for export.

    Exports complete version history including deleted versions.

    Args:
        corpus: Corpus instance

    Returns:
        List of DocumentPathExport dicts
    """
    paths_export = []

    try:
        # Get all DocumentPath records for this corpus (including non-current)
        all_paths = DocumentPath.objects.filter(corpus=corpus).order_by(
            "path", "version_number"
        )

        for doc_path in all_paths:
            # Get folder path if assigned
            folder_path = None
            if doc_path.folder:
                folder_path = doc_path.folder.get_path()

            # Get parent version number
            parent_version_number = None
            if doc_path.parent:
                parent_version_number = doc_path.parent.version_number

            # Use document hash as reference (more stable than ID)
            document_ref = (
                doc_path.document.pdf_file_hash
                if doc_path.document.pdf_file_hash
                else str(doc_path.document.id)
            )

            paths_export.append(
                {
                    "document_ref": document_ref,
                    "folder_path": folder_path,
                    "path": doc_path.path,
                    "version_number": doc_path.version_number,
                    "parent_version_number": parent_version_number,
                    "is_current": doc_path.is_current,
                    "is_deleted": doc_path.is_deleted,
                    "created": doc_path.created.isoformat(),
                }
            )

    except Exception as e:
        logger.error(f"Error packaging document paths for corpus {corpus.id}: {e}")

    return paths_export


def package_relationships(
    corpus: Corpus, document_ids: list[int]
) -> list[OpenContractsRelationshipPythonType]:
    """
    Package relationships for export.

    Exports both document-level and corpus-level relationships.

    Args:
        corpus: Corpus instance
        document_ids: List of document IDs being exported

    Returns:
        List of relationship dicts
    """
    relationships_export = []

    try:
        # Get relationships for documents in this corpus
        # Include both document-linked and corpus-linked relationships
        relationships = Relationship.objects.filter(
            Q(document_id__in=document_ids) | Q(corpus=corpus)
        ).distinct()

        for rel in relationships:
            relationships_export.append(
                {
                    "id": str(rel.id),
                    "relationshipLabel": (
                        rel.relationship_label.text if rel.relationship_label else ""
                    ),
                    "source_annotation_ids": [
                        str(a.id) for a in rel.source_annotations.all()
                    ],
                    "target_annotation_ids": [
                        str(a.id) for a in rel.target_annotations.all()
                    ],
                    "structural": rel.structural,
                }
            )

    except Exception as e:
        logger.error(f"Error packaging relationships for corpus {corpus.id}: {e}")

    return relationships_export


def package_agent_config(corpus: Corpus) -> AgentConfigExport:
    """
    Package agent configuration for export.

    Args:
        corpus: Corpus instance

    Returns:
        AgentConfigExport dict
    """
    return {
        "corpus_agent_instructions": corpus.corpus_agent_instructions,
        "document_agent_instructions": corpus.document_agent_instructions,
    }


def package_md_description_revisions(
    corpus: Corpus,
) -> tuple[str | None, list[DescriptionRevisionExport]]:
    """
    Package markdown description and revision history for export.

    Args:
        corpus: Corpus instance

    Returns:
        Tuple of (current_md_description, list of revisions)
    """
    current_description = None
    revisions_export = []

    try:
        # Get current markdown description
        if corpus.md_description and corpus.md_description.name:
            with corpus.md_description.open("r") as f:
                current_description = f.read()

        # Get revision history
        revisions = CorpusDescriptionRevision.objects.filter(corpus=corpus).order_by(
            "version"
        )

        for revision in revisions:
            revisions_export.append(
                {
                    "version": revision.version,
                    "diff": revision.diff,
                    "snapshot": revision.snapshot,
                    "checksum_base": revision.checksum_base,
                    "checksum_full": revision.checksum_full,
                    "created": revision.created.isoformat(),
                    "author_email": revision.author.email if revision.author else "",
                }
            )

    except Exception as e:
        logger.error(
            f"Error packaging markdown description for corpus {corpus.id}: {e}"
        )

    return current_description, revisions_export


def package_conversations(
    corpus: Corpus,
) -> tuple[list, list, list]:
    """
    Package conversations, messages, and votes for export (optional).

    Args:
        corpus: Corpus instance

    Returns:
        Tuple of (conversations, messages, message_votes)
    """
    from opencontractserver.conversations.models import (
        ChatMessage,
        Conversation,
        MessageVote,
    )

    conversations_export = []
    messages_export = []
    votes_export = []

    try:
        # Get all conversations for this corpus
        conversations = Conversation.objects.filter(chat_with_corpus=corpus)

        # Build conversation ID mapping
        conv_id_map = {}

        for conv in conversations:
            conv_export_id = str(conv.id)
            conv_id_map[conv.id] = conv_export_id

            conversations_export.append(
                {
                    "id": conv_export_id,
                    "title": conv.title or "",
                    "conversation_type": conv.conversation_type or "chat",
                    "is_public": conv.is_public,
                    "creator_email": conv.creator.email if conv.creator else "",
                    "created": conv.created_at.isoformat(),
                    "modified": conv.updated_at.isoformat(),
                }
            )

        # Get all messages for these conversations
        messages = ChatMessage.objects.filter(conversation__in=conversations)

        # Build message ID mapping
        msg_id_map = {}

        for msg in messages:
            msg_export_id = str(msg.id)
            msg_id_map[msg.id] = msg_export_id

            messages_export.append(
                {
                    "id": msg_export_id,
                    "conversation_id": conv_id_map.get(msg.conversation_id, ""),
                    "content": msg.content or "",
                    "msg_type": msg.msg_type,
                    "state": msg.state,
                    "agent_type": msg.agent_type or None,
                    "creator_email": msg.creator.email if msg.creator else "",
                    "created": msg.created_at.isoformat(),
                }
            )

        # Get all votes for these messages
        votes = MessageVote.objects.filter(message__in=messages)

        for vote in votes:
            votes_export.append(
                {
                    "message_id": msg_id_map.get(vote.message_id, ""),
                    "vote_type": vote.vote_type or "upvote",
                    "creator_email": vote.creator.email if vote.creator else "",
                    "created": vote.created_at.isoformat(),
                }
            )

    except Exception as e:
        logger.error(f"Error packaging conversations for corpus {corpus.id}: {e}")

    return conversations_export, messages_export, votes_export


def package_action_trail(
    corpus: Corpus,
    include_executions: bool = True,
    execution_limit: int | None = 1000,
    since=None,
):
    """
    Package corpus action trail for export.

    Args:
        corpus: Corpus to export actions for
        include_executions: Whether to include execution history
        execution_limit: Max executions to include (None = unlimited)
        since: Only include executions after this datetime

    Returns:
        ActionTrailExport dict with actions, executions, and stats
    """
    from django.db.models import Count, Q

    from opencontractserver.corpuses.models import CorpusActionExecution

    # Export action configurations
    actions = []
    for action in corpus.actions.all():
        # Determine action type - use 'is not None' to handle CharField PKs
        if action.fieldset_id is not None:
            action_type = "fieldset"
        elif action.analyzer_id is not None:
            action_type = "analyzer"
        else:
            action_type = "agent"

        actions.append(
            {
                "id": str(action.id),
                "name": action.name,
                "action_type": action_type,
                "trigger": action.trigger,
                "disabled": action.disabled,
                "fieldset_id": (
                    str(action.fieldset_id) if action.fieldset_id is not None else None
                ),
                "analyzer_id": (
                    str(action.analyzer_id) if action.analyzer_id is not None else None
                ),
                "agent_config_id": (
                    str(action.agent_config_id)
                    if action.agent_config_id is not None
                    else None
                ),
                "agent_prompt": action.agent_prompt or "",
                "pre_authorized_tools": action.pre_authorized_tools or [],
            }
        )

    # Export executions if requested
    executions = []
    if include_executions:
        qs = CorpusActionExecution.objects.filter(corpus=corpus)

        if since:
            qs = qs.filter(queued_at__gte=since)

        qs = qs.select_related("corpus_action", "document").order_by("-queued_at")

        if execution_limit:
            qs = qs[:execution_limit]

        for exec_record in qs:
            executions.append(
                {
                    "id": str(exec_record.id),
                    "action_name": exec_record.corpus_action.name,
                    "action_type": exec_record.action_type,
                    "document_id": str(exec_record.document_id),
                    "status": exec_record.status,
                    "trigger": exec_record.trigger,
                    "queued_at": (
                        exec_record.queued_at.isoformat()
                        if exec_record.queued_at
                        else None
                    ),
                    "started_at": (
                        exec_record.started_at.isoformat()
                        if exec_record.started_at
                        else None
                    ),
                    "completed_at": (
                        exec_record.completed_at.isoformat()
                        if exec_record.completed_at
                        else None
                    ),
                    "duration_seconds": exec_record.duration_seconds,
                    "affected_objects": exec_record.affected_objects or [],
                    "error_message": exec_record.error_message or "",
                    "execution_metadata": exec_record.execution_metadata or {},
                }
            )

    # Calculate stats
    stats = CorpusActionExecution.objects.filter(corpus=corpus).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status="completed")),
        failed=Count("id", filter=Q(status="failed")),
    )

    return {
        "actions": actions,
        "executions": executions,
        "stats": {
            "total_executions": stats["total"] or 0,
            "completed": stats["completed"] or 0,
            "failed": stats["failed"] or 0,
            "exported_count": len(executions),
        },
    }
