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

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import DocumentPath
from opencontractserver.types.dicts import OpenContractsExportDataJsonV2Type
from opencontractserver.types.enums import AnnotationFilterMode
from opencontractserver.users.models import UserExport
from opencontractserver.utils.etl import build_document_export, build_label_lookups
from opencontractserver.utils.export_v2 import (
    package_agent_config,
    package_conversations,
    package_corpus_folders,
    package_document_paths,
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
    analysis_pk_list: list[int] | None = None,
    annotation_filter_mode: AnnotationFilterMode = AnnotationFilterMode.CORPUS_LABELSET_ONLY,
):
    """
    Package a complete V2 corpus export.

    Args:
        export_id: UserExport ID to store result
        corpus_pk: Corpus ID to export
        include_conversations: Whether to include conversations/messages
        analysis_pk_list: Optional list of analysis IDs to filter annotations
        annotation_filter_mode: How to filter annotations
    """
    try:
        logger.info(f"Starting V2 export for corpus {corpus_pk}")

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
        annotated_docs = {}
        structural_sets_seen = set()

        for doc in documents:
            logger.info(f"Exporting document {doc.id}")

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
                logger.warning(f"Skipping document {doc.id} - export failed")
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
        structural_annotation_sets = {}

        for struct_set in structural_sets_seen:
            logger.info(f"Exporting structural set {struct_set.content_hash}")
            struct_export = package_structural_annotation_set(struct_set)
            if struct_export:
                structural_annotation_sets[struct_set.content_hash] = struct_export

        # ===== PART 3: Export Corpus Metadata (V2 enhanced) =====
        corpus_export = package_corpus_for_export(corpus, v2_format=True)
        label_set_export = package_label_set_for_export(corpus.label_set)

        # ===== PART 4: Export Folders =====
        folders_export = package_corpus_folders(corpus)

        # ===== PART 5: Export DocumentPath Trees =====
        document_paths_export = package_document_paths(corpus)

        # ===== PART 6: Export Relationships =====
        relationships_export = package_relationships(corpus, document_ids)

        # ===== PART 7: Export Agent Config =====
        agent_config_export = package_agent_config(corpus)

        # ===== PART 8: Export Markdown Description & Revisions =====
        md_description, md_revisions = package_md_description_revisions(corpus)

        # ===== PART 9: Export Conversations (Optional) =====
        conversations_export = []
        messages_export = []
        votes_export = []

        if include_conversations:
            logger.info("Including conversations in export")
            conversations_export, messages_export, votes_export = package_conversations(
                corpus
            )

        # ===== PART 10: Assemble Final V2 Export =====
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
        }

        # Add conversations if requested
        if include_conversations:
            export_data["conversations"] = conversations_export
            export_data["messages"] = messages_export
            export_data["message_votes"] = votes_export

        # Write data.json to ZIP
        json_str = json.dumps(export_data, indent=2) + "\n"
        json_bytes = json_str.encode("utf-8")
        zip_file.writestr("data.json", json_bytes)
        zip_file.close()

        # Save ZIP to export
        output_bytes.seek(io.SEEK_SET)
        export.file.save(
            f"{only_alphanumeric_chars(corpus.title)}_EXPORT_V2.zip", output_bytes
        )
        export.finished = timezone.now()
        export.backend_lock = False
        export.save()

        logger.info(f"V2 export {export_id} completed successfully")

    except Exception as e:
        logger.error(f"Error in V2 export for corpus {corpus_pk}: {str(e)}")
        # Mark export as failed
        try:
            export = UserExport.objects.get(pk=export_id)
            export.error = True
            export.backend_lock = False
            export.save()
        except Exception:
            pass
        raise
