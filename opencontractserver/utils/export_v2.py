"""
Export utilities for V2 corpus export format.

Handles export of new features added since original export design:
- Structural annotation sets
- Corpus folders hierarchy
- DocumentPath version trees
- Relationships
- Agent configurations
- Markdown descriptions with revisions
- Conversations and messages (optional)
"""

from __future__ import annotations

import json
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
    StructuralAnnotationSetExport,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


def package_structural_annotation_set(
    structural_set,
) -> StructuralAnnotationSetExport | None:
    """
    Package a StructuralAnnotationSet for export.

    Args:
        structural_set: StructuralAnnotationSet instance

    Returns:
        StructuralAnnotationSetExport dict or None if error
    """
    try:
        # Read PAWLS file content
        pawls_content = []
        if structural_set.pawls_parse_file:
            with structural_set.pawls_parse_file.open("r") as f:
                pawls_content = json.load(f)

        # Read text extract
        txt_content = ""
        if structural_set.txt_extract_file:
            with structural_set.txt_extract_file.open("r") as f:
                txt_content = f.read()

        # Get structural annotations
        structural_annotations = []
        for annot in structural_set.structural_annotations.all():
            structural_annotations.append(
                {
                    "id": str(annot.id),
                    "annotationLabel": (
                        annot.annotation_label.text if annot.annotation_label else ""
                    ),
                    "rawText": annot.raw_text or "",
                    "page": annot.page or 0,
                    "annotation_json": annot.json or {},
                    "parent_id": str(annot.parent_id) if annot.parent_id else None,
                    "annotation_type": annot.annotation_type or "",
                    "structural": True,
                }
            )

        # Get structural relationships
        structural_relationships = []
        for rel in structural_set.structural_relationships.all():
            structural_relationships.append(
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
                    "structural": True,
                }
            )

        return {
            "content_hash": structural_set.content_hash,
            "parser_name": structural_set.parser_name,
            "parser_version": structural_set.parser_version,
            "page_count": structural_set.page_count,
            "token_count": structural_set.token_count,
            "pawls_file_content": pawls_content,
            "txt_content": txt_content,
            "structural_annotations": structural_annotations,
            "structural_relationships": structural_relationships,
        }

    except Exception as e:
        logger.error(
            f"Error packaging structural annotation set {structural_set.id}: {e}"
        )
        return None


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
