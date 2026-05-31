"""
Export utilities for V2/V3 corpus export format.

Handles export of features added since the original export design:
- Structural annotation sets
- Corpus folders hierarchy
- DocumentPath version trees
- Relationships
- Agent configurations
- Conversations and messages (optional)

V3 (current emit) drops the legacy top-level ``md_description`` /
``md_description_revisions`` fields; the corpus description rides in
``annotated_docs`` as the Readme.CAML Document. See
``opencontractserver/tasks/export_tasks_v2.py`` for the assembled payload.
"""

from __future__ import annotations

import json
import logging
import os
from typing import cast

from django.contrib.auth import get_user_model
from django.db.models import Q

from opencontractserver.annotations.compact_json import compact_annotation_json
from opencontractserver.annotations.models import Relationship
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import DocumentPath, IngestionSource
from opencontractserver.extracts.models import Datacell
from opencontractserver.types.dicts import (
    AgentConfigExport,
    CompactAnnotationJsonType,
    CorpusFolderExport,
    DocumentPathExport,
    IngestionSourceExport,
    ManualColumnExport,
    ManualDatacellExport,
    MetadataSchemaExport,
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
    PawlsPagePythonType,
    StructuralAnnotationSetExport,
)
from opencontractserver.utils.compact_pawls import expand_pawls_pages
from opencontractserver.utils.files import read_field_file_text

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
        # Read PAWLS file content. ``expand_pawls_pages`` is a permissive
        # normaliser typed as ``list[dict[str, Any]]``; cast so the
        # TypedDict assignment below stays narrow.
        pawls_content: list[PawlsPagePythonType] = []
        if structural_set.pawls_parse_file:
            with structural_set.pawls_parse_file.open("r") as f:
                pawls_content = cast(
                    list[PawlsPagePythonType], expand_pawls_pages(json.load(f))
                )

        # Read text extract
        txt_content = ""
        if structural_set.txt_extract_file:
            txt_content = read_field_file_text(structural_set.txt_extract_file)

        # Get structural annotations
        structural_annotations: list[OpenContractsAnnotationPythonType] = []
        for annot in structural_set.structural_annotations.all():
            # CompactAnnotationJsonType requires both ``v`` and ``p``; an
            # empty dict would be a structural lie. Emit the canonical
            # empty-compact payload instead so downstream consumers that
            # assume the schema cannot trip on missing keys.
            annotation_json: CompactAnnotationJsonType = (
                cast(CompactAnnotationJsonType, compact_annotation_json(annot.json))
                if annot.json
                else {"v": 2, "p": {}}
            )
            annot_data: OpenContractsAnnotationPythonType = {
                "id": str(annot.id),
                "annotationLabel": (
                    annot.annotation_label.text if annot.annotation_label else ""
                ),
                "rawText": annot.raw_text or "",
                "page": annot.page or 0,
                "annotation_json": annotation_json,
                "parent_id": str(annot.parent_id) if annot.parent_id else None,
                "annotation_type": annot.annotation_type or "",
                "structural": True,
            }
            if annot.long_description is not None:
                annot_data["long_description"] = annot.long_description
            # Carry the OC_URL ``link_url`` through round-trip so forked /
            # re-imported corpora keep their clickable targets.
            if annot.link_url:
                annot_data["link_url"] = annot.link_url
            structural_annotations.append(annot_data)

        # Get structural relationships
        structural_relationships: list[OpenContractsRelationshipPythonType] = []
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

        result: StructuralAnnotationSetExport = {
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
        return result

    except Exception as e:
        logger.error(
            "Error packaging structural annotation set %s: %s",
            structural_set.id,
            e,
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
    folders_export: list[CorpusFolderExport] = []

    try:
        # Get all folders for this corpus, ordered by ID (parents before children)
        folders = corpus.folders.all().order_by("id")

        # Build export ID mapping (db_id -> export_id)
        folder_id_map: dict[int, str] = {}

        for folder in folders:
            # Use DB ID as export ID (simpler than generating new IDs)
            export_id = str(folder.id)
            folder_id_map[folder.id] = export_id

            # Get full path
            path = folder.get_path()

            # Get parent export ID
            parent_export_id: str | None = None
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
        logger.error("Error packaging corpus folders for corpus %s: %s", corpus.id, e)

    return folders_export


def package_document_paths(corpus: Corpus) -> list[DocumentPathExport]:
    """
    Package DocumentPath version trees for export.

    Exports complete version history including deleted versions.
    Includes ingestion lineage fields when present.

    Args:
        corpus: Corpus instance

    Returns:
        List of DocumentPathExport dicts
    """
    paths_export = []

    try:
        # Get all DocumentPath records for this corpus (including non-current)
        # select_related on ingestion_source to avoid N+1 queries
        all_paths = (
            DocumentPath.objects.filter(corpus=corpus)
            .select_related("ingestion_source", "document", "folder", "parent")
            .order_by("path", "version_number")
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

            # Use document hash as primary reference (stable across systems).
            # Fall back to the filename (basename of pdf_file), which matches
            # the key used in annotated_docs and is available on both the
            # export and import sides.
            document_ref: str
            if doc_path.document.pdf_file_hash:
                document_ref = doc_path.document.pdf_file_hash
            elif doc_path.document.pdf_file and doc_path.document.pdf_file.name:
                document_ref = os.path.basename(doc_path.document.pdf_file.name)
            else:
                # Mirror ``build_document_export``'s synthesized filename
                # so the import-side map (keyed by hash OR zip filename)
                # finds this entry on the way back.
                document_ref = f"document_{doc_path.document.id}.placeholder"

            entry: DocumentPathExport = {
                "document_ref": document_ref,
                "folder_path": folder_path,
                "path": doc_path.path,
                "version_number": doc_path.version_number,
                "parent_version_number": parent_version_number,
                "is_current": doc_path.is_current,
                "is_deleted": doc_path.is_deleted,
                "created": doc_path.created.isoformat(),
            }

            # Include ingestion lineage fields when present.
            if doc_path.ingestion_source_id and doc_path.ingestion_source is not None:
                entry["ingestion_source_name"] = doc_path.ingestion_source.name
            if doc_path.external_id:
                entry["external_id"] = doc_path.external_id
            if doc_path.ingestion_metadata:
                entry["ingestion_metadata"] = doc_path.ingestion_metadata

            paths_export.append(entry)

    except Exception as e:
        logger.error("Error packaging document paths for corpus %s: %s", corpus.id, e)

    return paths_export


def package_ingestion_sources(corpus: Corpus) -> list[IngestionSourceExport]:
    """
    Package IngestionSource records referenced by this corpus's DocumentPaths.

    Only exports sources that are actually used by at least one DocumentPath
    in this corpus (not all sources owned by the creator).

    Args:
        corpus: Corpus instance

    Returns:
        List of IngestionSourceExport dicts
    """
    try:
        sources = IngestionSource.objects.filter(
            document_paths__corpus=corpus
        ).distinct()
        return [
            {
                "name": source.name,
                "source_type": source.source_type,
                # Config is intentionally omitted from exports because it may
                # contain credentials (API keys, tokens, connection strings).
                # Importers should reconfigure sources after import.
                "config": {},
                "active": source.active,
            }
            for source in sources
        ]

    except Exception as e:
        logger.error(
            "Error packaging ingestion sources for corpus %s: %s", corpus.id, e
        )
        return []


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
    relationships_export: list[OpenContractsRelationshipPythonType] = []

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
        logger.error("Error packaging relationships for corpus %s: %s", corpus.id, e)

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


def package_conversations(
    corpus: Corpus,
    document_ids: list[int] | None = None,
    user=None,
) -> tuple[list, list, list]:
    """
    Package conversations, messages, and votes for export (optional).

    Includes both corpus-level and document-level conversations.
    Applies permission filtering when a user is provided.

    Args:
        corpus: Corpus instance
        document_ids: List of document IDs in the corpus (for doc-level
            conversations). If None, will be computed from active DocumentPaths.
        user: The exporting user for permission filtering. If None, all
            conversations are included (superuser / system export behavior).

    Returns:
        Tuple of (conversations, messages, message_votes)
    """
    from django.db.models import Q

    from opencontractserver.conversations.models import (
        ChatMessage,
        Conversation,
        MessageVote,
    )

    conversations_export = []
    messages_export = []
    votes_export = []

    try:
        # Compute document_ids if not provided
        if document_ids is None:
            from opencontractserver.documents.models import DocumentPath

            document_ids = list(
                DocumentPath.objects.filter(
                    corpus=corpus, is_current=True, is_deleted=False
                ).values_list("document_id", flat=True)
            )

        # Get all conversations for this corpus AND its documents
        corpus_filter = Q(chat_with_corpus=corpus)
        doc_filter = Q(chat_with_document_id__in=document_ids)
        conversations = Conversation.objects.filter(
            corpus_filter | doc_filter
        ).select_related("chat_with_document", "creator")

        # Apply permission filtering if user is provided
        if user is not None:
            visible_ids = Conversation.objects.visible_to_user(user).values_list(
                "id", flat=True
            )
            conversations = conversations.filter(id__in=visible_ids)

        # Build conversation ID mapping
        conv_id_map = {}

        # TODO(PII): `creator_email` on every conv/msg/vote built below leaks
        # collaborator PII into export ZIPs.  Same staged migration plan as
        # `author_email` above:
        #   1. Add `creator_slug` (from the user-slug work in #1612) alongside
        #      the email for one minor version; deprecation-log on the read side.
        #   2. Make import prefer slug; keep email as a fallback for older
        #      archives.
        #   3. Drop `creator_email` on the next export-format version bump.
        for conv in conversations:
            conv_export_id = str(conv.id)
            conv_id_map[conv.id] = conv_export_id

            conversations_export.append(
                {
                    "id": conv_export_id,
                    "title": conv.title or "",
                    "description": conv.description or "",
                    "conversation_type": conv.conversation_type or "chat",
                    "is_public": conv.is_public,
                    "is_locked": conv.is_locked,
                    "is_pinned": conv.is_pinned,
                    "creator_email": conv.creator.email if conv.creator else "",
                    "created": conv.created_at.isoformat(),
                    "modified": conv.updated_at.isoformat(),
                    # Reference to document (if doc-level conversation)
                    "chat_with_document_id": (
                        str(conv.chat_with_document_id)
                        if conv.chat_with_document_id
                        else None
                    ),
                    # Document hash for cross-system re-linking
                    "chat_with_document_hash": (
                        conv.chat_with_document.pdf_file_hash
                        if conv.chat_with_document
                        and conv.chat_with_document.pdf_file_hash
                        else None
                    ),
                    # Reference to corpus (always present for corpus-level)
                    "chat_with_corpus": conv.chat_with_corpus_id == corpus.id,
                }
            )

        # Get all messages for these conversations, ordered chronologically
        messages = ChatMessage.objects.filter(conversation__in=conversations).order_by(
            "created_at"
        )

        # No additional permission filter needed for messages — they are
        # already scoped to permission-filtered conversations above.

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
                    "data": msg.data,
                    "parent_message_id": (
                        str(msg.parent_message_id) if msg.parent_message_id else None
                    ),
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
        logger.error("Error packaging conversations for corpus %s: %s", corpus.id, e)

    return conversations_export, messages_export, votes_export


def package_metadata_schema(corpus: Corpus) -> MetadataSchemaExport | None:
    """
    Package a corpus's manual-metadata schema for export.

    Returns ``None`` when the corpus has no attached ``Fieldset``
    (most corpora don't).  Otherwise returns a
    :class:`opencontractserver.types.dicts.MetadataSchemaExport` dict
    containing the fieldset metadata, the manual-entry subset of its
    columns, and every user-entered datacell (``extract__isnull=True``)
    for those columns on documents currently active in the corpus.

    Document references in the datacells match the ``document_ref`` field
    on :func:`package_document_paths` (document hash when available,
    otherwise zip filename) so the importer can re-link via the same
    lookup map.
    """
    fieldset = getattr(corpus, "metadata_schema", None)
    if not fieldset:
        return None

    columns_qs = list(
        fieldset.columns.filter(is_manual_entry=True).order_by("display_order", "id")
    )
    if not columns_qs:
        # Fieldset with no manual-entry columns — still emit the
        # fieldset so its identity round-trips, but with empty payloads.
        return MetadataSchemaExport(
            fieldset_name=fieldset.name,
            fieldset_description=fieldset.description or "",
            columns=[],
            datacells=[],
        )

    columns_export: list[ManualColumnExport] = [
        {
            "id": str(c.pk),
            "name": c.name,
            "output_type": c.output_type,
            "data_type": c.data_type,
            "validation_config": (
                c.validation_config.copy() if c.validation_config else None
            ),
            "default_value": c.default_value,
            "help_text": c.help_text,
            "display_order": c.display_order,
        }
        for c in columns_qs
    ]

    # Build doc_id -> document_ref the same way package_document_paths does
    # so importers can use one lookup map for both.
    active_doc_paths = DocumentPath.objects.filter(
        corpus=corpus, is_current=True, is_deleted=False
    ).select_related("document")

    doc_ref_by_id: dict[int, str] = {}
    for dp in active_doc_paths:
        doc = dp.document
        if doc.pdf_file_hash:
            doc_ref_by_id[doc.id] = doc.pdf_file_hash
        elif doc.pdf_file and doc.pdf_file.name:
            doc_ref_by_id[doc.id] = os.path.basename(doc.pdf_file.name)
        else:
            # Mirror build_document_export's synthesized filename for
            # docs without files so the import-side doc_hash_to_corpus_doc
            # lookup (keyed by hash OR filename) finds us.
            doc_ref_by_id[doc.id] = f"document_{doc.id}.placeholder"

    column_ids = [c.pk for c in columns_qs]
    datacells_qs = Datacell.objects.filter(
        column_id__in=column_ids,
        document_id__in=doc_ref_by_id.keys(),
        extract__isnull=True,
    ).select_related("column")

    datacells_export: list[ManualDatacellExport] = []
    for dc in datacells_qs:
        doc_ref = doc_ref_by_id.get(dc.document_id)
        if not doc_ref:
            continue
        datacells_export.append(
            {
                "column_id": str(dc.column_id),
                "document_ref": doc_ref,
                "data": dc.data.copy() if dc.data else None,
                "data_definition": dc.data_definition or "",
            }
        )

    return MetadataSchemaExport(
        fieldset_name=fieldset.name,
        fieldset_description=fieldset.description or "",
        columns=columns_export,
        datacells=datacells_export,
    )


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
                "task_instructions": action.task_instructions or "",
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
