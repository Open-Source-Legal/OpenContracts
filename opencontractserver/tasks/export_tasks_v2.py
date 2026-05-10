"""
Export tasks for V2 corpus export format.

Handles comprehensive export including:
- All V1 features (documents, annotations, labels)
- Structural annotation sets
- Corpus folders
- DocumentPath version trees
- Relationships
- Agent configurations
- Markdown descriptions with revisions
- Conversations and messages (optional)
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from typing import cast

from celery import shared_task
from django.contrib.auth import get_user_model

from opencontractserver.annotations.models import StructuralAnnotationSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import DocumentPath
from opencontractserver.tasks.export_tasks import finalize_export
from opencontractserver.types.dicts import (
    ChatMessageExport,
    ConversationExport,
    MessageVoteExport,
    OpenContractCorpusV2Type,
    OpenContractDocExport,
    OpenContractsExportDataJsonV2Type,
    StructuralAnnotationSetExport,
)
from opencontractserver.types.enums import AnnotationFilterMode
from opencontractserver.users.models import UserExport
from opencontractserver.utils.etl import build_document_export, build_label_lookups
from opencontractserver.utils.export_v2 import (
    package_action_trail,
    package_agent_config,
    package_conversations,
    package_corpus_folders,
    package_document_paths,
    package_ingestion_sources,
    package_md_description_revisions,
    package_relationships,
    package_structural_annotation_set,
)
from opencontractserver.utils.packaging import (
    package_corpus_for_export,
    package_label_set_for_export,
)
from opencontractserver.utils.text import only_alphanumeric_chars

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@shared_task
def package_corpus_export_v2(
    export_id: int,
    corpus_pk: int,
    include_conversations: bool = False,
    include_action_trail: bool = False,
    action_trail_limit: int = 1000,
    analysis_pk_list: list[int] | None = None,
    annotation_filter_mode: AnnotationFilterMode = AnnotationFilterMode.CORPUS_LABELSET_ONLY,
) -> None:
    """
    Package a complete V2 corpus export.

    Args:
        export_id: UserExport ID to store result
        corpus_pk: Corpus ID to export
        include_conversations: Whether to include conversations/messages
        include_action_trail: Whether to include action execution history
        action_trail_limit: Max number of executions to include (default 1000)
        analysis_pk_list: Optional list of analysis IDs to filter annotations
        annotation_filter_mode: How to filter annotations
    """
    try:
        logger.info("Starting V2 export for corpus %s", corpus_pk)

        corpus = Corpus.objects.get(pk=corpus_pk)
        export = UserExport.objects.get(pk=export_id)

        # Build label lookups (V1 compatibility)
        label_lookups = build_label_lookups(
            corpus_id=corpus_pk,
            analysis_ids=analysis_pk_list,
            annotation_filter_mode=annotation_filter_mode,
        )

        # Get all active documents in corpus via DocumentPath
        active_doc_paths = DocumentPath.objects.filter(
            corpus=corpus, is_current=True, is_deleted=False
        ).select_related("document")

        document_ids = [dp.document_id for dp in active_doc_paths]
        documents = [dp.document for dp in active_doc_paths]

        # Create output ZIP
        output_bytes = io.BytesIO()
        zip_file = zipfile.ZipFile(
            output_bytes, mode="w", compression=zipfile.ZIP_DEFLATED
        )

        # ===== PART 1: Export Documents (V1 compatible) =====
        annotated_docs: dict[str, OpenContractDocExport] = {}
        structural_sets_seen: set[StructuralAnnotationSet] = set()

        for doc in documents:
            logger.info("Exporting document %s", doc.id)

            # Build document export (V1 style)
            (
                doc_filename,
                pdf_base64,
                doc_export_data,
                _,
                _,
            ) = build_document_export(
                label_lookups=label_lookups,
                doc_id=doc.id,
                corpus_id=corpus_pk,
                analysis_ids=analysis_pk_list,
                annotation_filter_mode=annotation_filter_mode,
            )

            if not doc_filename or not doc_export_data:
                logger.warning("Skipping document %s - export failed", doc.id)
                continue

            # Add structural set reference if present
            if doc.structural_annotation_set:
                doc_export_data["structural_set_hash"] = (
                    doc.structural_annotation_set.content_hash
                )
                structural_sets_seen.add(doc.structural_annotation_set)

            # Add PDF to ZIP
            if pdf_base64:
                base64_img_bytes = pdf_base64.encode("utf-8")
                import base64

                decoded_file_data = base64.decodebytes(base64_img_bytes)
                zip_file.writestr(doc_filename, decoded_file_data)

            annotated_docs[doc_filename] = doc_export_data

        # ===== PART 2: Export Structural Annotation Sets =====
        structural_annotation_sets: dict[str, StructuralAnnotationSetExport] = {}

        for struct_set in structural_sets_seen:
            logger.info("Exporting structural set %s", struct_set.content_hash)
            struct_export = package_structural_annotation_set(struct_set)
            if struct_export:
                structural_annotation_sets[struct_set.content_hash] = struct_export

        # ===== PART 3: Export Corpus Metadata (V2 enhanced) =====
        # ``v2_format=True`` guarantees a V2 dict at runtime; check first,
        # then cast so mypy can narrow the type.
        _corpus_export = package_corpus_for_export(corpus, v2_format=True)
        label_set_export = package_label_set_for_export(corpus.label_set)
        if _corpus_export is None or label_set_export is None:
            raise RuntimeError(
                f"Failed to package corpus or label set for V2 export of corpus "
                f"{corpus_pk}"
            )
        corpus_export = cast(OpenContractCorpusV2Type, _corpus_export)

        # ===== PART 4: Export Folders =====
        folders_export = package_corpus_folders(corpus)

        # ===== PART 5: Export DocumentPath Trees & Ingestion Sources =====
        document_paths_export = package_document_paths(corpus)
        ingestion_sources_export = package_ingestion_sources(corpus)

        # ===== PART 6: Export Relationships =====
        relationships_export = package_relationships(corpus, document_ids)

        # ===== PART 7: Export Agent Config =====
        agent_config_export = package_agent_config(corpus)

        # ===== PART 8: Export Markdown Description & Revisions =====
        md_description, md_revisions = package_md_description_revisions(corpus)

        # ===== PART 9: Export Conversations (Optional) =====
        conversations_export: list[ConversationExport] = []
        messages_export: list[ChatMessageExport] = []
        votes_export: list[MessageVoteExport] = []

        if include_conversations:
            logger.info("Including conversations in export")
            conversations_export, messages_export, votes_export = package_conversations(
                corpus,
                document_ids=document_ids,
                user=export.creator,
            )

        # ===== PART 10: Export Action Trail (Optional) =====
        action_trail_export = None

        if include_action_trail:
            logger.info("Including action trail in export")
            action_trail_export = package_action_trail(
                corpus=corpus,
                include_executions=True,
                execution_limit=action_trail_limit,
            )

        # ===== PART 11: Assemble Final V2 Export =====
        export_data: OpenContractsExportDataJsonV2Type = {
            "version": "2.0",
            # V1 fields
            "annotated_docs": annotated_docs,
            "doc_labels": label_lookups["doc_labels"],
            "text_labels": label_lookups["text_labels"],
            "corpus": corpus_export,
            "label_set": label_set_export,
            # V2 fields
            "structural_annotation_sets": structural_annotation_sets,
            "folders": folders_export,
            "document_paths": document_paths_export,
            "relationships": relationships_export,
            "agent_config": agent_config_export,
            "md_description": md_description,
            "md_description_revisions": md_revisions,
            "post_processors": corpus.post_processors or [],
            "ingestion_sources": ingestion_sources_export,
        }

        # Add conversations if requested
        if include_conversations:
            export_data["conversations"] = conversations_export
            export_data["messages"] = messages_export
            export_data["message_votes"] = votes_export

        # Add action trail if requested
        if include_action_trail and action_trail_export:
            export_data["action_trail"] = action_trail_export

        # Write data.json to ZIP
        json_str = json.dumps(export_data, indent=2) + "\n"
        json_bytes = json_str.encode("utf-8")
        zip_file.writestr("data.json", json_bytes)
        zip_file.close()

        # Save ZIP to export
        finalize_export(
            export_id,
            f"{only_alphanumeric_chars(corpus.title)}_EXPORT_V2.zip",
            output_bytes,
            corpus.title,
        )
        logger.info("V2 export %s completed successfully", export_id)

    except Exception as e:
        logger.error("Error in V2 export for corpus %s: %s", corpus_pk, e)
        # Mark export as failed
        try:
            export = UserExport.objects.get(pk=export_id)
            export.errors = str(e)
            export.backend_lock = False
            export.save()
        except Exception:
            pass
        raise
