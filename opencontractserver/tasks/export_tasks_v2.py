"""
Export tasks for V2/V3 corpus export format.

Handles comprehensive export including:
- All V1 features (documents, annotations, labels)
- Structural annotation sets
- Corpus folders
- DocumentPath version trees
- Relationships
- Agent configurations
- Conversations and messages (optional)

V3 (current emit, schema 3.0): the corpus description rides in
``annotated_docs`` as the Readme.CAML Document, so the legacy
``md_description`` / ``md_description_revisions`` top-level keys are
dropped (see spec §4.8). The import side still accepts V2 archives via a
back-compat shim that synthesises a Readme.CAML Document from those keys.
"""

from __future__ import annotations

import base64
import json
import logging
import zipfile
from tempfile import SpooledTemporaryFile
from typing import IO, TYPE_CHECKING, cast

from celery import shared_task
from django.contrib.auth import get_user_model

from opencontractserver.annotations.models import StructuralAnnotationSet
from opencontractserver.constants.zip_export import get_export_spool_max_size_bytes
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import DocumentPath
from opencontractserver.tasks.export_tasks import finalize_export
from opencontractserver.types.dicts import (
    ChatMessageExport,
    ConversationExport,
    MessageVoteExport,
    OpenContractCorpusV2Type,
    OpenContractDocExport,
    OpenContractsExportDataJsonPythonTypeV3,
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
    package_metadata_schema,
    package_relationships,
    package_structural_annotation_set,
)
from opencontractserver.utils.packaging import (
    package_corpus_for_export,
    package_label_set_for_export,
)
from opencontractserver.utils.text import only_alphanumeric_chars

if TYPE_CHECKING:
    from opencontractserver.users.models import User as UserModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


def build_corpus_v2_zip(
    corpus_pk: int,
    user_for_visibility: UserModel | None = None,
    include_conversations: bool = False,
    include_action_trail: bool = False,
    action_trail_limit: int = 1000,
    analysis_pk_list: list[int] | None = None,
    annotation_filter_mode: AnnotationFilterMode = AnnotationFilterMode.CORPUS_LABELSET_ONLY,
) -> IO[bytes]:
    """
    Build a V2 corpus export ZIP and return its bytes via a spooled buffer.

    No ``UserExport`` row is created or modified — callers that want to
    persist the archive should pair this with ``finalize_export``.  Fork
    uses this directly to round-trip a corpus through the import pipeline
    without touching ``UserExport`` at all.

    Memory characteristic: the underlying buffer is a
    :class:`tempfile.SpooledTemporaryFile` that keeps small archives entirely
    in heap memory and transparently rolls over to an on-disk temp file once
    it exceeds :data:`EXPORT_SPOOL_MAX_SIZE_BYTES`. This bounds peak heap
    usage on large corpora (which embed every document's PDF bytes) without
    forcing small exports to touch disk. **Caller owns the returned buffer's
    lifetime** — close it (or use it as a context manager) once the
    downstream consumer is done reading.

    Args:
        corpus_pk: Corpus to export.
        user_for_visibility: Used for ``Conversation.visible_to_user``
            filtering when ``include_conversations=True``.  ``None`` means
            no filtering (export every conversation attached to the corpus
            or its documents).
        include_conversations, include_action_trail, action_trail_limit,
        analysis_pk_list, annotation_filter_mode: same semantics as
            ``package_corpus_export_v2``.

    Returns:
        A seekable binary file-like buffer positioned at offset 0, ready
        to read.

    Raises:
        RuntimeError: if corpus or label set packaging fails.
    """
    corpus = Corpus.objects.get(pk=corpus_pk)

    # Build label lookups (V1 compatibility)
    label_lookups = build_label_lookups(
        corpus_id=corpus_pk,
        analysis_ids=analysis_pk_list,
        annotation_filter_mode=annotation_filter_mode,
    )

    # Active documents via DocumentPath
    active_doc_paths = DocumentPath.objects.filter(
        corpus=corpus, is_current=True, is_deleted=False
    ).select_related("document")

    document_ids = [dp.document_id for dp in active_doc_paths]
    documents = [dp.document for dp in active_doc_paths]

    # Read the spool threshold at call time so ``@override_settings`` in
    # tests (and any runtime settings change) actually takes effect.
    output_bytes: IO[bytes] = SpooledTemporaryFile(
        max_size=get_export_spool_max_size_bytes(), mode="w+b"
    )
    zip_file = zipfile.ZipFile(output_bytes, mode="w", compression=zipfile.ZIP_DEFLATED)

    # ===== PART 1: Documents (V1 compatible) =====
    annotated_docs: dict[str, OpenContractDocExport] = {}
    structural_sets_seen: set[StructuralAnnotationSet] = set()

    for doc in documents:
        logger.info("Exporting document %s", doc.id)

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

        if doc.structural_annotation_set:
            doc_export_data["structural_set_hash"] = (
                doc.structural_annotation_set.content_hash
            )
            structural_sets_seen.add(doc.structural_annotation_set)

        if pdf_base64:
            decoded_file_data = base64.decodebytes(pdf_base64.encode("utf-8"))
            zip_file.writestr(doc_filename, decoded_file_data)

        annotated_docs[doc_filename] = doc_export_data

    # ===== PART 2: Structural annotation sets =====
    structural_annotation_sets: dict[str, StructuralAnnotationSetExport] = {}
    for struct_set in structural_sets_seen:
        logger.info("Exporting structural set %s", struct_set.content_hash)
        struct_export = package_structural_annotation_set(struct_set)
        if struct_export:
            structural_annotation_sets[struct_set.content_hash] = struct_export

    # ===== PART 3: Corpus metadata (V2 enhanced) =====
    _corpus_export = package_corpus_for_export(corpus, v2_format=True)
    if _corpus_export is None:
        raise RuntimeError(
            f"Failed to package corpus for V2 export of corpus {corpus_pk}"
        )
    corpus_export = cast(OpenContractCorpusV2Type, _corpus_export)

    # A corpus may genuinely have no LabelSet (e.g. brand-new, empty
    # corpus).  Emit a minimal placeholder so the importer has something
    # to unpack — it will create an empty LabelSet and attach it.
    #
    # ``id: 0`` is not a sentinel: ``_setup_corpus_and_labels`` pops the
    # ``id`` key off ``label_set_data`` before unpacking, so any int value
    # is equivalent.  Zero is used for readability.
    if corpus.label_set is not None:
        label_set_export = package_label_set_for_export(corpus.label_set)
        if label_set_export is None:
            raise RuntimeError(
                f"Failed to package label set for V2 export of corpus {corpus_pk}"
            )
    else:
        label_set_export = {
            "id": 0,
            "title": f"{corpus.title} LabelSet",
            "description": "",
            "icon_name": "",
            "icon_data": "",
            "creator": corpus.creator.email if corpus.creator else "",
        }

    # ===== PART 4: Folders =====
    folders_export = package_corpus_folders(corpus)

    # ===== PART 5: DocumentPath trees + ingestion sources =====
    document_paths_export = package_document_paths(corpus)
    ingestion_sources_export = package_ingestion_sources(corpus)

    # ===== PART 6: Relationships =====
    relationships_export = package_relationships(corpus, document_ids)

    # ===== PART 7: Agent config =====
    agent_config_export = package_agent_config(corpus)

    # ===== PART 8: Manual metadata schema =====
    #
    # V3 drops the legacy ``md_description`` / ``md_description_revisions``
    # top-level fields: the Readme.CAML Document rides in ``annotated_docs``
    # like every other Document, and revisions are version-tree siblings —
    # see spec §4.8 of the Canonical-CAML refactor.
    metadata_schema_export = package_metadata_schema(corpus)

    # ===== PART 10: Conversations (optional) =====
    conversations_export: list[ConversationExport] = []
    messages_export: list[ChatMessageExport] = []
    votes_export: list[MessageVoteExport] = []

    if include_conversations:
        logger.info("Including conversations in export")
        conversations_export, messages_export, votes_export = package_conversations(
            corpus,
            document_ids=document_ids,
            user=user_for_visibility,
        )

    # ===== PART 11: Action trail (optional) =====
    # NOTE: action-trail import is not yet implemented on the import side
    # (see opencontractserver/tasks/import_tasks_v2.py and docs/architecture/
    # corpus_export_import_v2.md). The exported payload is included for
    # diagnostic/audit purposes but is dropped on re-import.
    action_trail_export = None
    if include_action_trail:
        logger.info("Including action trail in export")
        action_trail_export = package_action_trail(
            corpus=corpus,
            include_executions=True,
            execution_limit=action_trail_limit,
        )

    # ===== PART 12: Assemble =====
    export_data: OpenContractsExportDataJsonPythonTypeV3 = {
        "version": "3.0",
        "annotated_docs": annotated_docs,
        "doc_labels": label_lookups["doc_labels"],
        "text_labels": label_lookups["text_labels"],
        "corpus": corpus_export,
        "label_set": label_set_export,
        "structural_annotation_sets": structural_annotation_sets,
        "folders": folders_export,
        "document_paths": document_paths_export,
        "relationships": relationships_export,
        "agent_config": agent_config_export,
        "post_processors": corpus.post_processors or [],
        "ingestion_sources": ingestion_sources_export,
    }

    if include_conversations:
        export_data["conversations"] = conversations_export
        export_data["messages"] = messages_export
        export_data["message_votes"] = votes_export

    if metadata_schema_export is not None:
        export_data["metadata_schema"] = metadata_schema_export

    if include_action_trail and action_trail_export:
        export_data["action_trail"] = action_trail_export

    json_str = json.dumps(export_data, indent=2) + "\n"
    zip_file.writestr("data.json", json_str.encode("utf-8"))
    zip_file.close()

    output_bytes.seek(0)
    return output_bytes


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
    Package a complete V2 corpus export into a ``UserExport`` row.

    Thin orchestration wrapper around :func:`build_corpus_v2_zip` and
    :func:`finalize_export`; all the actual serialization work lives in
    the helper so fork (and any other in-process caller) can reuse it
    without touching ``UserExport``.

    Args:
        export_id: UserExport ID to store result.
        corpus_pk: Corpus ID to export.
        include_conversations: Whether to include conversations/messages.
        include_action_trail: Whether to include action execution history.
        action_trail_limit: Max number of executions to include.
        analysis_pk_list: Optional list of analysis IDs to filter annotations.
        annotation_filter_mode: How to filter annotations.
    """
    try:
        logger.info("Starting V2 export for corpus %s", corpus_pk)

        corpus = Corpus.objects.get(pk=corpus_pk)
        export = UserExport.objects.get(pk=export_id)

        with build_corpus_v2_zip(
            corpus_pk=corpus_pk,
            user_for_visibility=export.creator,
            include_conversations=include_conversations,
            include_action_trail=include_action_trail,
            action_trail_limit=action_trail_limit,
            analysis_pk_list=analysis_pk_list,
            annotation_filter_mode=annotation_filter_mode,
        ) as output_bytes:
            finalize_export(
                export_id,
                f"{only_alphanumeric_chars(corpus.title)}_EXPORT_V2.zip",
                output_bytes,
                corpus.title,
            )
        logger.info("V2 export %s completed successfully", export_id)

    except Exception as e:
        logger.error("Error in V2 export for corpus %s: %s", corpus_pk, e)
        try:
            export = UserExport.objects.get(pk=export_id)
            export.errors = str(e)
            export.backend_lock = False
            export.save()
        except Exception:
            pass
        raise
