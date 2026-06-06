from __future__ import annotations

import base64
import json
import logging
import pathlib
import uuid
import zipfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opencontractserver.annotations.models import AnnotationLabel

    # Aliased to avoid colliding with the runtime ``User = get_user_model()``
    # below; matches the pattern in ``import_tasks_v2.py``.
    from opencontractserver.users.models import User as UserModel
    from opencontractserver.utils.metadata_file_parser import DocumentMetadata

import filetype
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction

from config import celery_app
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    TOKEN_LABEL,
    LabelSet,
)
from opencontractserver.constants.document_processing import (
    DEFAULT_DOCUMENT_PATH_PREFIX,
    MAX_FILENAME_LENGTH,
)
from opencontractserver.constants.zip_import import get_zip_max_sidecar_size_bytes
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import (
    Document,
    PendingDocumentAnnotations,
)
from opencontractserver.pipeline.registry import get_allowed_mime_types
from opencontractserver.types.dicts import (
    OpenContractsAnnotatedDocumentImportType,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.compact_pawls import compact_pawls_pages
from opencontractserver.utils.files import is_plaintext_content
from opencontractserver.utils.importing import (
    import_doc_annotations,
    load_or_create_labels,
    prepare_import_labels,
    validate_labels_data,
)
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
from opencontractserver.utils.validate_export import validate_dumb_anchor_sidecar

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task()
def import_corpus(
    temporary_file_handle_id: str | int,
    user_id: int,
    seed_corpus_id: int | None,
    reingest_and_remap: bool = False,
) -> int | None:
    """
    Import a corpus from a V1-format export ZIP.

    Delegates to import_corpus_v2 which handles both V1 and V2 formats
    using shared helpers for label loading, document creation, and
    annotation import.

    ``reingest_and_remap`` re-parses each document through the current pipeline
    and re-anchors its non-structural annotations instead of trusting the
    export's baked PAWLs / structural layer. This low-level task defaults it
    **off** (explicit opt-in for direct/programmatic callers and fork); the
    user-facing entry point ``import_corpus_export_for_user`` defaults it **on**
    (opt-out) and passes it through here. See
    ``docs/development/2026-06-06-v2-import-reingest-remap.md``.
    """
    from opencontractserver.tasks.import_tasks_v2 import import_corpus_v2

    return import_corpus_v2(
        temporary_file_handle_id,
        user_id,
        seed_corpus_id,
        reingest_and_remap=reingest_and_remap,
    )


@celery_app.task()
def import_document_to_corpus(
    target_corpus_id: int,
    user_id: int,
    document_import_data: OpenContractsAnnotatedDocumentImportType,
) -> str | None:
    """
    Import a single annotated document into an existing corpus.

    Uses shared helpers for label loading, document creation, and annotation
    import. Creates a standalone document then adds it to the corpus via
    corpus.add_document() for proper corpus isolation.
    """
    try:
        logger.info(f"import_document_to_corpus() - for user_id: {user_id}")

        corpus_obj = Corpus.objects.get(id=target_corpus_id)
        user_obj = User.objects.get(id=user_id)
        labelset_obj = corpus_obj.label_set

        # Load existing labels from labelset, then create any new ones
        existing_text_labels = {
            label.text: label
            for label in labelset_obj.annotation_labels.filter(label_type=TOKEN_LABEL)
        }
        existing_doc_labels = {
            label.text: label
            for label in labelset_obj.annotation_labels.filter(
                label_type=DOC_TYPE_LABEL
            )
        }

        existing_text_labels = load_or_create_labels(
            user_id,
            labelset_obj,
            document_import_data.get("text_labels", {}),
            existing_text_labels,
        )
        existing_doc_labels = load_or_create_labels(
            user_id,
            labelset_obj,
            document_import_data.get("doc_labels", {}),
            existing_doc_labels,
        )

        label_lookup = {**existing_text_labels, **existing_doc_labels}
        doc_label_lookup = {label.text: label for label in existing_doc_labels.values()}

        # Decode and create document
        pdf_data = base64.b64decode(document_import_data["pdf_base64"])
        pdf_file = ContentFile(pdf_data, name=f"{document_import_data['pdf_name']}.pdf")

        doc_data = document_import_data["doc_data"]
        pawls_parse_file = ContentFile(
            json.dumps(compact_pawls_pages(doc_data["pawls_file_content"])).encode(
                "utf-8"
            ),
            name="pawls_tokens.json",
        )

        doc_obj = Document.objects.create(
            title=doc_data["title"],
            description=doc_data.get("description", ""),
            pdf_file=pdf_file,
            pawls_parse_file=pawls_parse_file,
            creator=user_obj,
            backend_lock=True,
            page_count=doc_data.get("page_count", 0),
        )
        set_permissions_for_obj_to_user(user_obj, doc_obj, [PermissionTypes.ALL])

        # Add to corpus - creates corpus-isolated copy
        corpus_doc, _status, _doc_path = corpus_obj.add_document(
            document=doc_obj, user=user_obj
        )

        # Import all annotations onto the corpus copy using shared helper
        _annot_id_map, _doc_labels_count = import_doc_annotations(
            doc_data=doc_data,
            corpus_doc=corpus_doc,
            corpus_obj=corpus_obj,
            user_id=user_id,
            label_lookup=label_lookup,
            doc_label_lookup=doc_label_lookup,
        )

        # Unlock original document
        doc_obj.backend_lock = False
        doc_obj.save(update_fields=["backend_lock"])

        logger.info("Document import completed successfully")
        return corpus_doc.id

    except Exception as e:
        logger.error(f"Exception encountered in document import: {e}")
        return None


@celery_app.task()
def process_documents_zip(
    temporary_file_handle_id: str | int,
    user_id: int,
    job_id: str,
    title_prefix: str | None = None,
    description: str | None = None,
    custom_meta: dict[str, Any] | None = None,
    make_public: bool = False,
    corpus_id: int | None = None,
) -> dict[str, Any]:
    """
    Process a zip file containing documents, extract each file, and create Document objects
    for files with allowed MIME types.

    Args:
        temporary_file_handle_id: ID of the temporary file containing the zip
        user_id: ID of the user who uploaded the zip
        job_id: Unique ID for the job
        title_prefix: Optional prefix for document titles
        description: Optional description to apply to all documents
        custom_meta: Optional metadata to apply to all documents
        make_public: Whether the documents should be public
        corpus_id: Optional ID of corpus to link documents to

    Returns:
        Dictionary with summary of processing results
    """
    results: dict[str, Any] = {
        "job_id": job_id,
        "success": False,
        "completed": False,  # Will be set to True on successful completion
        "total_files": 0,
        "processed_files": 0,
        "skipped_files": 0,
        "error_files": 0,
        "document_ids": [],
        "errors": [],
    }

    try:
        logger.info(f"process_documents_zip() - Processing started for job: {job_id}")

        # Get the temporary file and user objects
        temporary_file_handle = TemporaryFileHandle.objects.get(
            id=temporary_file_handle_id
        )
        user_obj = User.objects.get(id=user_id)

        # Check for corpus if needed
        corpus_obj = None
        if corpus_id:
            corpus_obj = Corpus.objects.get(id=corpus_id)

        # Calculate user doc limit if capped
        if user_obj.is_usage_capped:
            current_doc_count = user_obj.document_set.count()
            remaining_quota = (
                settings.USAGE_CAPPED_USER_DOC_CAP_COUNT - current_doc_count
            )
            if remaining_quota <= 0:
                results["success"] = False
                results["completed"] = True  # Task completed but failed
                results["errors"].append(
                    f"User has reached maximum document limit of {settings.USAGE_CAPPED_USER_DOC_CAP_COUNT}"
                )
                return results

        # Process the zip file
        with temporary_file_handle.file.open("rb") as import_file, zipfile.ZipFile(
            import_file, mode="r"
        ) as import_zip:
            logger.info(f"process_documents_zip() - Opened zip file for job: {job_id}")

            # Get list of files in the zip
            files = import_zip.namelist()
            logger.info(f"process_documents_zip() - Found {len(files)} files in zip")
            results["total_files"] = len(files)

            # Process each file in the zip
            for filename in files:
                # Skip directories and hidden files
                if (
                    filename.endswith("/")
                    or filename.startswith(".")
                    or "/__MACOSX/" in filename
                ):
                    results["skipped_files"] += 1
                    continue

                try:
                    # Check if we've hit the user cap
                    if user_obj.is_usage_capped:
                        current_doc_count = user_obj.document_set.count()
                        if (
                            current_doc_count
                            >= settings.USAGE_CAPPED_USER_DOC_CAP_COUNT
                        ):
                            results["errors"].append(
                                "User document limit reached during processing"
                            )
                            break

                    # Extract the file from the zip
                    with import_zip.open(filename) as file_handle:
                        file_bytes = file_handle.read()

                        # Check file type
                        kind = filetype.guess(file_bytes)
                        if kind is None:
                            # Try to detect plaintext using the improved utility
                            if is_plaintext_content(file_bytes):
                                kind = "text/plain"
                            else:  # Truly unknown/binary
                                logger.info(
                                    f"process_documents_zip() - Skipping file with unknown type: {filename}"
                                )
                                results["skipped_files"] += 1
                                continue
                        else:
                            kind = kind.mime

                        # Skip files with unsupported types
                        if kind not in get_allowed_mime_types():
                            results["skipped_files"] += 1
                            continue

                        # Prepare document attributes
                        # Use only the filename part, discarding the path within the zip
                        base_filename = pathlib.Path(filename).name
                        doc_title = base_filename
                        if title_prefix:
                            doc_title = f"{title_prefix} - {base_filename}"

                        doc_description = (
                            description
                            or f"Uploaded as part of batch upload (job: {job_id})"
                        )

                        # Generate path for corpus document
                        safe_filename = "".join(
                            c if c.isalnum() or c in "-_." else "_"
                            for c in base_filename[:MAX_FILENAME_LENGTH]
                        )
                        doc_path = f"{DEFAULT_DOCUMENT_PATH_PREFIX}/{safe_filename}"

                        # Create the document based on file type
                        document = None

                        if kind in [
                            "application/pdf",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        ]:
                            # Use corpus_obj if provided, otherwise use personal corpus
                            target_corpus = corpus_obj
                            if target_corpus is None:
                                # Get or create user's personal corpus
                                target_corpus = Corpus.get_or_create_personal_corpus(
                                    user_obj
                                )
                                logger.info(
                                    f"process_documents_zip() - Using personal corpus "
                                    f"{target_corpus.id} for user {user_obj.id}"
                                )

                            # Use import_content to create document directly in corpus
                            # This avoids creating orphan standalone documents
                            # backend_lock=True ensures document shows as processing
                            document, status, path_record = (
                                target_corpus.import_content(
                                    content=file_bytes,
                                    path=doc_path,
                                    user=user_obj,
                                    title=doc_title,
                                    description=doc_description,
                                    custom_meta=custom_meta,
                                    is_public=make_public,
                                    file_type=kind,
                                    backend_lock=True,
                                )
                            )
                            logger.info(
                                f"process_documents_zip() - Created document {document.id} "
                                f"in corpus {target_corpus.id} (status: {status})"
                            )
                        elif kind in ["text/plain", "application/txt"]:
                            # Use corpus_obj if provided, otherwise use personal corpus
                            target_corpus = corpus_obj
                            if target_corpus is None:
                                target_corpus = Corpus.get_or_create_personal_corpus(
                                    user_obj
                                )
                                logger.info(
                                    f"process_documents_zip() - Using personal corpus "
                                    f"{target_corpus.id} for text upload by user {user_obj.id}"
                                )

                            # Use import_content() which routes based on file_type
                            document, status, path_record = (
                                target_corpus.import_content(
                                    content=file_bytes,
                                    user=user_obj,
                                    path=doc_path,
                                    filename=filename,
                                    file_type=kind,
                                    title=doc_title,
                                    description=doc_description,
                                    custom_meta=custom_meta,
                                    backend_lock=True,
                                    is_public=make_public,
                                )
                            )
                            logger.info(
                                f"process_documents_zip() - Created text document {document.id} "
                                f"in corpus {target_corpus.id} (status: {status})"
                            )

                        if document:
                            # Set permissions for the document
                            set_permissions_for_obj_to_user(
                                user_obj, document, [PermissionTypes.CRUD]
                            )

                            # Update results
                            results["processed_files"] += 1
                            results["document_ids"].append(str(document.id))
                            logger.info(
                                f"process_documents_zip() - Created document: {document.id} for file: {filename}"
                            )

                except Exception as e:
                    logger.error(
                        f"process_documents_zip() - Error processing file {filename}: {str(e)}"
                    )
                    results["error_files"] += 1
                    results["errors"].append(f"Error processing {filename}: {str(e)}")

        # Check if processing was stopped early due to user cap
        user_cap_reached_mid_processing = any(
            "User document limit reached during processing" in error
            for error in results["errors"]
        )

        # Clean up the temporary file
        temporary_file_handle.delete()

        # success=True must reflect both the user-cap state and any per-file
        # processing errors recorded above.  Previously success only tracked
        # the user cap, so callers got success=True even when individual files
        # failed and were appended to results["errors"].
        results["success"] = (
            not user_cap_reached_mid_processing and results["error_files"] == 0
        )
        results["completed"] = True  # Task completed, success depends on errors/cap
        logger.info(
            f"process_documents_zip() - Completed job: {job_id}, processed: {results['processed_files']}"
        )

    except Exception as e:
        logger.error(f"process_documents_zip() - Job failed with error: {str(e)}")
        results["success"] = False
        results["completed"] = True  # Task completed but failed
        results["errors"].append(f"Job failed: {str(e)}")

    return results


def create_relationships_from_parsed(
    corpus: Corpus,
    user: UserModel,
    document_path_map: dict[str, Document],
    parsed_relationships: list[Any],
    logger: logging.Logger,
) -> dict[str, Any]:
    """
    Create DocumentRelationship objects from parsed relationship data.

    This function is called after all documents are imported and the
    document_path_map has been built. It creates relationships between
    documents based on the paths specified in the relationships CSV.

    Args:
        corpus: The Corpus object to create relationships in
        user: The User creating the relationships
        document_path_map: Mapping of normalized paths to Document objects. May
            include documents already in the corpus (not just this import's), so
            endpoints can resolve across separately-imported batches.
        parsed_relationships: List of ParsedRelationship objects from the parser
        logger: Logger instance for logging

    Returns:
        Dictionary with relationship creation statistics:
        - relationships_created: Number of relationships successfully created
        - relationships_skipped: Number skipped due to missing documents
        - relationship_errors: List of error messages
    """
    from opencontractserver.annotations.models import AnnotationLabel
    from opencontractserver.documents.models import DocumentRelationship
    from opencontractserver.types.enums import LabelType

    results: dict[str, Any] = {
        "relationships_created": 0,
        "relationships_skipped": 0,
        "relationship_errors": [],
    }

    # Cache for labels to avoid repeated lookups
    label_cache: dict[str, AnnotationLabel] = {}

    for rel in parsed_relationships:
        try:
            # Look up source and target documents by path
            source_doc = document_path_map.get(rel.source_path)
            target_doc = document_path_map.get(rel.target_path)

            if source_doc is None:
                results["relationships_skipped"] += 1
                results["relationship_errors"].append(
                    f"Source document not found: {rel.source_path}"
                )
                continue

            if target_doc is None:
                results["relationships_skipped"] += 1
                results["relationship_errors"].append(
                    f"Target document not found: {rel.target_path}"
                )
                continue

            # Get or create the label for this relationship
            if rel.label not in label_cache:
                annotation_label = corpus.ensure_label_and_labelset(
                    label_text=rel.label,
                    creator_id=user.id,
                    label_type=LabelType.RELATIONSHIP_LABEL,
                )
                label_cache[rel.label] = annotation_label
            else:
                annotation_label = label_cache[rel.label]

            # Build relationship data
            relationship_data = {}
            if rel.notes:
                relationship_data["note"] = rel.notes

            # Create the relationship
            DocumentRelationship.objects.create(
                source_document=source_doc,
                target_document=target_doc,
                corpus=corpus,
                annotation_label=annotation_label,
                relationship_type=rel.relationship_type,
                data=relationship_data if relationship_data else None,
                creator=user,
            )

            results["relationships_created"] += 1
            logger.debug(
                f"Created relationship: {rel.source_path} --[{rel.label}]--> "
                f"{rel.target_path} (type: {rel.relationship_type})"
            )

        except Exception as e:
            results["relationship_errors"].append(
                f"Error creating relationship {rel.source_path} -> {rel.target_path}: {str(e)}"
            )
            logger.error(
                f"Error creating relationship {rel.source_path} -> {rel.target_path}: {e}"
            )

    logger.info(
        f"Relationship creation complete: {results['relationships_created']} created, "
        f"{results['relationships_skipped']} skipped"
    )

    return results


def build_existing_corpus_path_map(
    user: UserModel,
    corpus: Corpus,
) -> dict[str, Document]:
    """Map current corpus document paths -> Document for cross-batch relationships.

    A ``relationships.csv`` endpoint that does not match a file in *this* ZIP is
    resolved against documents already in the corpus, so a relationship can span
    separately-imported batches (the cross-batch edges a single ZIP otherwise
    can't express). Only current, non-deleted paths whose document the importing
    user can access — via ``CorpusDocumentService.get_corpus_documents``, the
    canonical corpus-scoped accessor — are included, so the map can never resolve
    an endpoint to a document the user could not already see in the corpus.

    Keys are the document's path within the corpus (``DocumentPath.path``, e.g.
    ``/contracts/master.pdf``), which equals the ZIP-relative path when no target
    folder is used, so the common case "Just Works".
    """
    from opencontractserver.corpuses.services import CorpusDocumentService
    from opencontractserver.documents.models import DocumentPath

    accessible_doc_ids = set(
        CorpusDocumentService.get_corpus_documents(user, corpus).values_list(
            "id", flat=True
        )
    )
    if not accessible_doc_ids:
        return {}

    path_map: dict[str, Document] = {}
    for doc_path in DocumentPath.objects.filter(
        corpus=corpus,
        is_current=True,
        is_deleted=False,
        document_id__in=accessible_doc_ids,
    ).select_related("document"):
        path_map[doc_path.path] = doc_path.document
    return path_map


def _read_sidecar(
    import_zip: zipfile.ZipFile,
    sidecar_path: str,
) -> dict[str, Any]:
    """
    Read and parse a sidecar JSON from the zip file.

    Args:
        import_zip: The open zip file handle.
        sidecar_path: Path within the zip to the sidecar JSON file.

    Returns:
        Parsed sidecar data dict.

    Raises:
        json.JSONDecodeError: If the sidecar is not valid JSON.
        KeyError: If the sidecar path is not found in the zip.
        ValueError: If the sidecar exceeds ZIP_MAX_SIDECAR_SIZE_BYTES.
    """
    # sidecar_path is the *original* (unsanitized) zip entry name stored in
    # manifest.annotation_sidecars.  This is safe: ZipFile.open() performs a
    # name lookup against the zip's central directory — it does NOT touch the
    # filesystem and cannot be used for path-traversal.

    # Read the configurable limit at call time (never frozen at import — see
    # opencontractserver/constants/zip_import.py).
    max_sidecar_size_bytes = get_zip_max_sidecar_size_bytes()

    # Pre-read size check using the central directory's declared size.
    # This avoids allocating memory for oversized sidecars.  A malicious zip
    # could forge this value, so we keep a post-read assertion as well.
    info = import_zip.getinfo(sidecar_path)
    if info.file_size > max_sidecar_size_bytes:
        raise ValueError(
            f"Sidecar {sidecar_path} declares {info.file_size} bytes, "
            f"exceeds limit of {max_sidecar_size_bytes} bytes"
        )

    with import_zip.open(sidecar_path) as sidecar_handle:
        raw = sidecar_handle.read()
        if len(raw) > max_sidecar_size_bytes:
            raise ValueError(
                f"Sidecar {sidecar_path} is {len(raw)} bytes, "
                f"exceeds limit of {max_sidecar_size_bytes} bytes"
            )
        return json.loads(raw.decode("UTF-8"))


@celery_app.task()
def import_zip_with_folder_structure(
    temporary_file_handle_id: str | int,
    user_id: int,
    job_id: str,
    corpus_id: int,
    target_folder_id: int | None = None,
    title_prefix: str | None = None,
    description: str | None = None,
    custom_meta: dict[str, Any] | None = None,
    make_public: bool = False,
) -> dict[str, Any]:
    """
    Process a zip file and import documents preserving folder structure.

    This task:
    1. Validates the zip file for security (path traversal, zip bombs, etc.)
    2. Creates the folder structure from the zip in the corpus
    3. If labels.json is present, loads annotation label definitions
    4. Extracts and creates documents with proper folder assignments.
       If a document has a co-located .json sidecar in the dumb-anchor format
       (a top-level ``"annotations"`` list of label/rawText anchors), the
       document is created normally (no ``processing_started`` suppression) and
       the sidecar's producer annotations are persisted in a
       ``PendingDocumentAnnotations`` row stamped with this import's run id.
       The standard document post_save ingest chain
       (``extract_thumbnail -> ingest_doc -> remap_pending_annotations ->
       set_doc_lock_state``) then anchors them **after** PAWLs / text exist —
       the importer no longer owns a bespoke chain. Documents without a sidecar
       go through the parser pipeline unchanged.
    5. If a relationships.csv file is present at the zip root, creates
       document relationships based on its contents

    The relationships.csv file should have the format:
        source_path,relationship_label,target_path,notes
        /contracts/master.pdf,Parent,/contracts/amendments/a1.pdf,
        /contracts/master.pdf,References,/exhibits/exhibit_a.pdf,See section 3

    Args:
        temporary_file_handle_id: ID of the temporary file containing the zip
        user_id: ID of the user who uploaded the zip
        job_id: Unique ID for the job
        corpus_id: ID of the corpus to import into
        target_folder_id: Optional folder ID to place zip contents under
        title_prefix: Optional prefix for document titles
        description: Optional description to apply to all documents
        custom_meta: Optional metadata to apply to all documents
        make_public: Whether the documents should be public

    Returns:
        Dictionary with comprehensive results including:
        - job_id, success, completed flags
        - File statistics (processed, skipped by type/size/path, errored)
        - Folder statistics (created, reused)
        - Relationship statistics (created, skipped, errors)
        - Document IDs and error messages
    """
    from opencontractserver.constants.zip_import import get_zip_document_batch_size
    from opencontractserver.corpuses.models import Corpus, CorpusFolder
    from opencontractserver.corpuses.services import FolderCRUDService
    from opencontractserver.utils.zip_security import validate_zip_for_import

    # Read the configurable batch size once for this run (never frozen at
    # import — see opencontractserver/constants/zip_import.py).
    zip_document_batch_size = get_zip_document_batch_size()

    results: dict[str, Any] = {
        "job_id": job_id,
        "success": False,
        "completed": False,
        # Validation
        "validation_passed": False,
        "validation_errors": [],
        # File statistics
        "total_files_in_zip": 0,
        "files_processed": 0,
        "files_skipped_type": 0,
        "files_skipped_size": 0,
        "files_skipped_hidden": 0,
        "files_skipped_path": 0,
        "files_errored": 0,
        "files_upversioned": 0,  # Count of documents that replaced existing versions
        # Folder statistics
        "folders_created": 0,
        "folders_reused": 0,
        # Metadata statistics
        "metadata_file_found": False,
        "metadata_applied": 0,
        # Annotation sidecar statistics
        "labels_file_found": False,
        "labels_loaded": False,
        "annotation_sidecars_found": 0,
        "annotation_sidecars_errored": 0,
        "annotations_imported": 0,
        "pipeline_skipped": 0,
        "pending_annotation_docs": 0,
        # Count of intra-document annotation-to-annotation relationships found
        # across all sidecars and persisted for deferred wiring. The relationships
        # themselves are created later by ``remap_pending_annotations`` (once the
        # annotation id_map exists), so this is a "captured", not "created", count.
        "sidecar_relationships_found": 0,
        # Relationship statistics
        "relationships_file_found": False,
        "relationships_created": 0,
        "relationships_skipped": 0,
        "relationship_errors": [],
        # Output
        "document_ids": [],
        "errors": [],
        "skipped_oversized": [],
        "upversioned_paths": [],  # Paths where new versions replaced old ones
    }

    # One ingestion-run token for every deferred annotation set this import
    # produces, so the rows can be grouped / gated / reported on later.
    # NOTE (review finding #4): this is minted per task *execution*, so a Celery
    # retry of a partially-completed import gives documents from the retry a
    # different ``import_run_id`` than those created on the first attempt. Any
    # caller using ``run_id`` to gate/aggregate must treat a single logical
    # import as potentially spanning multiple run ids; ``run_id=None`` (apply
    # every PENDING row for the document) is unaffected.
    import_run_id = uuid.uuid4()

    try:
        logger.info(
            f"import_zip_with_folder_structure() - Processing started for job: {job_id}"
        )

        # Get required objects
        temporary_file_handle = TemporaryFileHandle.objects.get(
            id=temporary_file_handle_id
        )
        user_obj = User.objects.get(id=user_id)
        corpus_obj = Corpus.objects.get(id=corpus_id)

        # Get target folder if specified
        target_folder = None
        if target_folder_id:
            target_folder = CorpusFolder.objects.get(
                id=target_folder_id, corpus=corpus_obj
            )

        # Check user quota
        if user_obj.is_usage_capped:
            current_doc_count = user_obj.document_set.count()
            remaining_quota = (
                settings.USAGE_CAPPED_USER_DOC_CAP_COUNT - current_doc_count
            )
            if remaining_quota <= 0:
                results["completed"] = True
                results["errors"].append(
                    f"User has reached maximum document limit of "
                    f"{settings.USAGE_CAPPED_USER_DOC_CAP_COUNT}"
                )
                return results

        # Open and validate the zip file
        with temporary_file_handle.file.open("rb") as import_file, zipfile.ZipFile(
            import_file, mode="r"
        ) as import_zip:
            logger.info(
                f"import_zip_with_folder_structure() - Opened zip file for job: {job_id}"
            )

            # Phase 1: Validate the zip file
            manifest = validate_zip_for_import(import_zip)
            results["total_files_in_zip"] = manifest.total_files_in_zip

            if not manifest.is_valid:
                results["completed"] = True
                results["validation_errors"].append(manifest.error_message)
                results["errors"].append(f"Validation failed: {manifest.error_message}")
                logger.warning(
                    f"import_zip_with_folder_structure() - Validation failed: "
                    f"{manifest.error_message}"
                )
                return results

            results["validation_passed"] = True

            # Count skipped files by reason
            for skipped in manifest.skipped_files:
                if skipped.is_oversized:
                    results["files_skipped_size"] += 1
                    results["skipped_oversized"].append(skipped.original_path)
                elif "hidden" in skipped.skip_reason.lower():
                    results["files_skipped_hidden"] += 1
                elif "path" in skipped.skip_reason.lower():
                    results["files_skipped_path"] += 1
                else:
                    # Generic skip
                    results["files_skipped_path"] += 1

            logger.info(
                f"import_zip_with_folder_structure() - Validation passed: "
                f"{len(manifest.valid_files)} valid files, "
                f"{len(manifest.skipped_files)} skipped, "
                f"{len(manifest.folder_paths)} folders to create"
            )

            # Phase 2: Create folder structure
            if manifest.folder_paths:
                folder_map, created, reused, folder_error = (
                    FolderCRUDService.create_folder_structure_from_paths(
                        user=user_obj,
                        corpus=corpus_obj,
                        folder_paths=manifest.folder_paths,
                        target_folder=target_folder,
                    )
                )

                if folder_error:
                    results["completed"] = True
                    results["errors"].append(f"Folder creation failed: {folder_error}")
                    logger.error(
                        f"import_zip_with_folder_structure() - Folder creation failed: "
                        f"{folder_error}"
                    )
                    return results

                results["folders_created"] = created
                results["folders_reused"] = reused
            else:
                folder_map = {}

            logger.info(
                f"import_zip_with_folder_structure() - Folder structure ready: "
                f"{results['folders_created']} created, {results['folders_reused']} reused"
            )

            # Track if relationships file was found for Phase 4
            if manifest.relationship_file:
                results["relationships_file_found"] = True
                logger.info(
                    f"import_zip_with_folder_structure() - Relationships file found: "
                    f"{manifest.relationship_file}"
                )

            # Parse metadata file if present (used in Phase 3)
            metadata_lookup: dict[str, DocumentMetadata] = {}
            if manifest.metadata_file:
                from opencontractserver.utils.metadata_file_parser import (
                    parse_metadata_file,
                )

                results["metadata_file_found"] = True
                logger.info(
                    f"import_zip_with_folder_structure() - Metadata file found: "
                    f"{manifest.metadata_file}"
                )

                meta_result = parse_metadata_file(import_zip, manifest.metadata_file)
                if meta_result.is_valid:
                    metadata_lookup = meta_result.metadata
                    logger.info(
                        f"import_zip_with_folder_structure() - Parsed metadata for "
                        f"{len(metadata_lookup)} documents"
                    )
                    for warning in meta_result.warnings:
                        logger.warning(
                            f"import_zip_with_folder_structure() - "
                            f"Metadata warning: {warning}"
                        )
                else:
                    for error in meta_result.errors:
                        logger.warning(
                            f"import_zip_with_folder_structure() - "
                            f"Metadata parsing error: {error}"
                        )
                        results["errors"].append(f"Metadata file error: {error}")

            # Phase 3: Load annotation labels if labels.json is present
            # These are needed when importing annotation sidecars
            label_lookup: dict[str, AnnotationLabel] = {}
            doc_label_lookup: dict[str, AnnotationLabel] = {}
            # Retained at function scope so the Phase-4 dumb-anchor sidecar
            # pre-flight (validate_dumb_anchor_sidecar) can check producer
            # annotations against the same labels.json. ``None`` when no
            # labels file was loaded.
            labels_data: dict | None = None
            if manifest.labels_file:
                results["labels_file_found"] = True
            if manifest.labels_file and manifest.annotation_sidecars:
                try:
                    with import_zip.open(manifest.labels_file) as labels_handle:
                        labels_data = json.loads(labels_handle.read().decode("UTF-8"))

                    # Validate labels.json schema before processing
                    validation_errors = validate_labels_data(labels_data)
                    if validation_errors:
                        for err in validation_errors:
                            logger.warning(
                                f"import_zip_with_folder_structure() - "
                                f"Labels validation error: {err}"
                            )
                            results["errors"].append(f"Labels file error: {err}")
                    else:
                        # Ensure corpus has a label set
                        if not corpus_obj.label_set:
                            labelset_obj = LabelSet.objects.create(
                                title=f"Labels for {corpus_obj.title}",
                                description="Auto-created during annotated import",
                                creator=user_obj,
                            )
                            set_permissions_for_obj_to_user(
                                user_obj, labelset_obj, [PermissionTypes.ALL]
                            )
                            corpus_obj.label_set = labelset_obj
                            corpus_obj.save(update_fields=["label_set"])
                        else:
                            labelset_obj = corpus_obj.label_set

                        label_lookup, doc_label_lookup = prepare_import_labels(
                            labels_data, user_obj.id, labelset_obj
                        )
                        results["labels_loaded"] = True
                        logger.info(
                            f"import_zip_with_folder_structure() - Loaded "
                            f"{len(label_lookup)} labels from {manifest.labels_file}"
                        )
                except Exception as e:
                    logger.error(
                        f"import_zip_with_folder_structure() - "
                        f"Error parsing labels file: {e}"
                    )
                    results["errors"].append(f"Labels file error: {e}")

            results["annotation_sidecars_found"] = len(manifest.annotation_sidecars)

            # Phase 4: Process documents in batches
            # Build document_path_map as documents are created for use in Phase 4
            document_path_map: dict[str, Document] = {}
            batch_count = 0
            for entry in manifest.valid_files:
                try:
                    # Check user quota during processing
                    if user_obj.is_usage_capped:
                        current_doc_count = user_obj.document_set.count()
                        if (
                            current_doc_count
                            >= settings.USAGE_CAPPED_USER_DOC_CAP_COUNT
                        ):
                            results["errors"].append(
                                "User document limit reached during processing"
                            )
                            break

                    # Extract file from zip
                    with import_zip.open(entry.original_path) as file_handle:
                        file_bytes = file_handle.read()

                    # Validate MIME type
                    kind = filetype.guess(file_bytes)
                    if kind is None:
                        if is_plaintext_content(file_bytes):
                            mime_type = "text/plain"
                        else:
                            results["files_skipped_type"] += 1
                            continue
                    else:
                        mime_type = kind.mime

                    if mime_type not in get_allowed_mime_types():
                        results["files_skipped_type"] += 1
                        continue

                    # Prepare document attributes
                    doc_title = entry.filename
                    if title_prefix:
                        doc_title = f"{title_prefix} - {entry.filename}"

                    doc_description = (
                        description or f"Imported from zip (job: {job_id})"
                    )

                    # Apply metadata from meta.csv if available
                    # Lookup key is normalized path with leading slash
                    metadata_path = f"/{entry.sanitized_path}"
                    doc_metadata = metadata_lookup.get(metadata_path)
                    if doc_metadata:
                        if doc_metadata.title:
                            doc_title = doc_metadata.title
                            if title_prefix:
                                doc_title = f"{title_prefix} - {doc_metadata.title}"
                        if doc_metadata.description:
                            doc_description = doc_metadata.description
                        results["metadata_applied"] += 1

                    # Determine target folder for this document
                    doc_folder = None
                    if entry.folder_path:
                        doc_folder = folder_map.get(entry.folder_path)
                        if doc_folder is None and target_folder:
                            # Fallback to target folder if path mapping failed
                            doc_folder = target_folder
                    elif target_folder:
                        # File at zip root goes to target folder
                        doc_folder = target_folder

                    # Build the document path for versioning
                    # This enables collision detection and upversioning
                    if target_folder:
                        # Prepend target folder's path to the zip path
                        target_path = target_folder.get_path()
                        doc_path_str = f"{target_path}/{entry.sanitized_path}"
                    else:
                        # Use the sanitized path directly from the zip
                        doc_path_str = f"/{entry.sanitized_path}"

                    # Determine document creation strategy:
                    # - If a co-located sidecar in the dumb-anchor format
                    #   (top-level ``"annotations"`` list) exists, create the
                    #   document via the normal parser pipeline, persist the
                    #   producer annotations in a PendingDocumentAnnotations
                    #   row, and dispatch an explicit
                    #   ingest -> remap -> unlock chain so the remap runs after
                    #   PAWLs / text exist.
                    # - Otherwise, use the normal pipeline path (the document's
                    #   post_save signal owns the ingest/unlock chain).
                    added_doc = None
                    doc_path = None
                    sidecar_path = manifest.annotation_sidecars.get(
                        entry.sanitized_path
                    )

                    # Pre-read sidecar if present (to detect the dumb-anchor
                    # format and to avoid reading twice).
                    sidecar_data: dict | None = None
                    has_pending_annotations = False
                    pending_annotations_list: list | None = None
                    # Intra-document annotation-to-annotation relationships
                    # (source/target annotation ids referencing the sidecar's
                    # own annotations). Carried verbatim into the pending row so
                    # the deferred remap can wire them once the annotation
                    # id_map exists.
                    pending_relationships_list: list | None = None
                    # True only for the dumb-anchor format (top-level
                    # ``"annotations"``); the legacy ``"labelled_text"`` format
                    # has no pre-flight schema and is re-anchored leniently.
                    sidecar_is_dumb_anchor = False
                    if sidecar_path:
                        try:
                            sidecar_data = _read_sidecar(import_zip, sidecar_path)
                            # Accept BOTH producer formats and route either into
                            # the deferred remap pipeline:
                            #   * dumb-anchor: a top-level ``"annotations"`` list
                            #     of page+bbox / start anchors;
                            #   * legacy export / ``skip_pipeline`` scrape: a
                            #     ``"labelled_text"`` list of baked
                            #     ``annotation_json`` annotations.
                            # The remap step strips any token indices and
                            # re-anchors onto the freshly-parsed PAWLs, so the
                            # embedded ``content`` / ``pawls_file_content`` and
                            # the ``skip_pipeline`` flag are ignored — the
                            # document is force-ingested through the normal
                            # parser (giving it a real text layer + structural
                            # annotations), then its producer annotations are
                            # re-anchored.
                            if isinstance(sidecar_data.get("annotations"), list):
                                pending_annotations_list = sidecar_data["annotations"]
                                # Only PURE dumb-anchor entries (``label`` +
                                # ``page``/``bbox`` or ``start``/``end``) are
                                # understood by validate_dumb_anchor_sidecar.
                                # Legacy export entries (``annotationLabel`` +
                                # baked ``annotation_json``) can also live in an
                                # "annotations" list; those are normalised by
                                # anchor_annotations' legacy adapter at remap
                                # time and must NOT be pre-flighted (they would
                                # false-fail the dumb-anchor schema).
                                sidecar_is_dumb_anchor = not any(
                                    isinstance(a, dict) and "annotation_json" in a
                                    for a in pending_annotations_list
                                )
                            elif isinstance(sidecar_data.get("labelled_text"), list):
                                pending_annotations_list = sidecar_data["labelled_text"]
                            has_pending_annotations = (
                                pending_annotations_list is not None
                            )
                            # Intra-document annotation-to-annotation
                            # relationships ride alongside the annotations in a
                            # top-level ``"relationships"`` list. They reference
                            # the sidecar's own annotation ids, so they cannot be
                            # wired until those annotations have been anchored and
                            # assigned real pks. We capture them here and persist
                            # them on the pending row; ``remap_pending_annotations``
                            # wires them after ``import_annotations`` builds the
                            # export-id -> new-pk map.
                            sidecar_rels = sidecar_data.get("relationships")
                            if isinstance(sidecar_rels, list) and sidecar_rels:
                                pending_relationships_list = sidecar_rels
                                results["sidecar_relationships_found"] += len(
                                    sidecar_rels
                                )
                        except Exception as e:
                            logger.error(
                                f"import_zip_with_folder_structure() - "
                                f"Error reading sidecar {sidecar_path}: {e}",
                                exc_info=True,
                            )
                            results["annotation_sidecars_errored"] += 1
                            results["errors"].append(
                                f"Sidecar read error for {sidecar_path}: {e}"
                            )
                            # Fall through to pipeline creation without sidecar
                            sidecar_data = None

                    try:
                        # No processing_started suppression and no bespoke
                        # Celery chain here: the standard Document post_save
                        # chain (extract_thumbnail -> ingest_doc ->
                        # remap_pending_annotations -> set_doc_lock_state) now
                        # owns dispatch and applies the deferred annotations.
                        # Create the document AND its pending-annotation row in
                        # one atomic block. The Document post_save chain
                        # (extract_thumbnail -> ingest_doc ->
                        # remap_pending_annotations -> set_doc_lock_state) is
                        # dispatched via transaction.on_commit, which Django runs
                        # at the OUTERMOST atomic commit. Wrapping both writes
                        # together guarantees the PendingDocumentAnnotations row
                        # is committed before remap runs — otherwise the chain
                        # would fire at import_content's inner commit (before the
                        # row exists) and the remap would no-op.
                        with transaction.atomic():
                            added_doc, _status, doc_path = corpus_obj.import_content(
                                content=file_bytes,
                                path=doc_path_str,
                                user=user_obj,
                                folder=doc_folder,
                                filename=entry.filename,
                                title=doc_title,
                                description=doc_description,
                                custom_meta=custom_meta,
                                is_public=make_public,
                                file_type=mime_type,
                                backend_lock=True,
                            )
                            logger.info(
                                f"import_zip_with_folder_structure() - "
                                f"Created document {added_doc.id} in corpus "
                                f"{corpus_obj.id} via pipeline"
                            )

                            if added_doc:
                                # Set permissions for the document
                                set_permissions_for_obj_to_user(
                                    user_obj, added_doc, [PermissionTypes.CRUD]
                                )

                                # Persist dumb-anchor annotations for the
                                # standard ingest chain's remap step to consume.
                                # Stamped with this import's run id so the set
                                # can be grouped / gated / reported on later.
                                if has_pending_annotations and sidecar_data:
                                    # Pre-flight validate the dumb-anchor payload
                                    # against labels.json BEFORE persisting. A
                                    # malformed sidecar (entry missing label /
                                    # rawText / anchor, or a label that doesn't
                                    # resolve in labels.json) otherwise drains
                                    # through the Celery queue and only surfaces
                                    # as a remap failure after ingest; validating
                                    # here co-locates the error with the import
                                    # and gives faster feedback. Invalid rows are
                                    # still persisted (never silently dropped) but
                                    # marked FAILED so remap skips them.
                                    #
                                    # Gated on BOTH conditions:
                                    #   * dumb-anchor format only — the validator
                                    #     does not understand the legacy
                                    #     "labelled_text" shape, which stays
                                    #     PENDING and is re-anchored leniently;
                                    #   * a labels.json was actually loaded — the
                                    #     validator's label-resolution check is
                                    #     defined against labels.json, but in the
                                    #     import flow labels legitimately resolve
                                    #     from the corpus labelset when no
                                    #     labels.json ships. Running it without
                                    #     labels.json would false-fail every label
                                    #     as "does not resolve".
                                    pending_status = (
                                        PendingDocumentAnnotations.Status.PENDING
                                    )
                                    pending_report: list = []
                                    if (
                                        sidecar_is_dumb_anchor
                                        and labels_data is not None
                                    ):
                                        vres = validate_dumb_anchor_sidecar(
                                            sidecar_data, labels_data
                                        )
                                        if not vres.ok:
                                            pending_status = (
                                                PendingDocumentAnnotations.Status.FAILED
                                            )
                                            pending_report = [
                                                {"error": e} for e in vres.errors
                                            ]
                                            results["annotation_sidecars_errored"] += 1
                                            results["errors"].append(
                                                f"Sidecar {sidecar_path} failed "
                                                f"validation ({len(vres.errors)} "
                                                "error(s)); annotations not "
                                                "imported."
                                            )
                                    PendingDocumentAnnotations.objects.create(
                                        document=added_doc,
                                        corpus=corpus_obj,
                                        creator=user_obj,
                                        ingestion_run_id=import_run_id,
                                        payload={
                                            "annotations": pending_annotations_list
                                            or [],
                                            "doc_labels": sidecar_data.get(
                                                "doc_labels", []
                                            ),
                                            "relationships": (
                                                pending_relationships_list or []
                                            ),
                                        },
                                        status=pending_status,
                                        report=pending_report,
                                    )
                                    results["pending_annotation_docs"] += 1
                                    logger.info(
                                        f"import_zip_with_folder_structure() - "
                                        f"Persisted pending annotations (run "
                                        f"{import_run_id}) for document "
                                        f"{added_doc.id}; standard chain will remap"
                                    )

                    except PermissionError as e:
                        logger.warning(
                            f"Permission error adding document at {doc_path_str}: {e}"
                        )
                        results["files_errored"] += 1
                        results["errors"].append(
                            f"Permission error for {entry.sanitized_path}: {str(e)}"
                        )
                        continue

                    if added_doc:
                        results["files_processed"] += 1
                        results["document_ids"].append(str(added_doc.id))

                        # Add to document_path_map for relationship processing
                        # Key is normalized path with leading slash to match CSV format
                        normalized_zip_path = f"/{entry.sanitized_path}"
                        document_path_map[normalized_zip_path] = added_doc

                        # Track upversioned documents
                        if doc_path and doc_path.version_number > 1:
                            results["files_upversioned"] += 1
                            results["upversioned_paths"].append(doc_path_str)

                        batch_count += 1
                        if batch_count % zip_document_batch_size == 0:
                            logger.info(
                                f"import_zip_with_folder_structure() - "
                                f"Processed {batch_count} documents..."
                            )

                except Exception as e:
                    logger.error(
                        f"import_zip_with_folder_structure() - Error processing file "
                        f"{entry.sanitized_path}: {str(e)}"
                    )
                    results["files_errored"] += 1
                    results["errors"].append(
                        f"Error processing {entry.sanitized_path}: {str(e)}"
                    )

            # Phase 5: Process relationships file if present.
            # The gate no longer requires ``document_path_map`` to be non-empty:
            # a relationship-only ZIP (just a relationships.csv wiring documents
            # already in the corpus) is a valid cross-batch use case.
            if manifest.relationship_file:
                from opencontractserver.utils.relationship_file_parser import (
                    parse_relationship_file,
                )

                logger.info(
                    f"import_zip_with_folder_structure() - Processing relationships "
                    f"file: {manifest.relationship_file}"
                )

                # Resolve endpoints against documents imported in THIS ZIP first,
                # falling back to documents already in the corpus so a
                # relationship can span separately-imported batches. The
                # in-import map is layered on TOP so a path imported now wins over
                # the same path's prior version.
                resolution_path_map = {
                    **build_existing_corpus_path_map(user_obj, corpus_obj),
                    **document_path_map,
                }

                # Parse the relationships file
                parse_result = parse_relationship_file(
                    import_zip, manifest.relationship_file
                )

                if not parse_result.is_valid:
                    for error in parse_result.errors:
                        results["relationship_errors"].append(error)
                    logger.warning(
                        f"import_zip_with_folder_structure() - Relationships file "
                        f"parsing failed: {parse_result.errors}"
                    )
                else:
                    # Log any warnings
                    for warning in parse_result.warnings:
                        logger.warning(
                            f"import_zip_with_folder_structure() - "
                            f"Relationship warning: {warning}"
                        )

                    # Create relationships if there are any
                    if parse_result.relationships:
                        rel_results = create_relationships_from_parsed(
                            corpus=corpus_obj,
                            user=user_obj,
                            document_path_map=resolution_path_map,
                            parsed_relationships=parse_result.relationships,
                            logger=logger,
                        )

                        results["relationships_created"] = rel_results[
                            "relationships_created"
                        ]
                        results["relationships_skipped"] = rel_results[
                            "relationships_skipped"
                        ]
                        results["relationship_errors"].extend(
                            rel_results["relationship_errors"]
                        )

                        logger.info(
                            f"import_zip_with_folder_structure() - "
                            f"Relationships created: {results['relationships_created']}, "
                            f"skipped: {results['relationships_skipped']}"
                        )

        # Cleanup temporary file
        temporary_file_handle.delete()

        # Determine success.  success=True must reflect that the documents
        # AND their annotations were imported as the caller asked.  Sidecar
        # failures (e.g. ZIP_MAX_SIDECAR_SIZE_BYTES exceeded, malformed JSON,
        # missing labels for sidecar-declared annotations) were previously
        # ignored here, so callers got success=True even when annotations
        # were silently dropped.  Per-file failures and the user-cap check
        # are unchanged.  Relationship_errors are *not* folded in: the
        # documents themselves are imported and individual relationship rows
        # already surface via relationships_skipped + relationship_errors,
        # which is the contract existing callers depend on.
        user_cap_reached = any(
            "User document limit reached" in error for error in results["errors"]
        )
        results["success"] = (
            not user_cap_reached
            and results["files_errored"] == 0
            and results["annotation_sidecars_errored"] == 0
        )
        results["completed"] = True

        logger.info(
            f"import_zip_with_folder_structure() - Completed job: {job_id}, "
            f"processed: {results['files_processed']}, "
            f"upversioned: {results['files_upversioned']}, "
            f"folders created: {results['folders_created']}, "
            f"metadata applied: {results['metadata_applied']}, "
            f"pending annotation docs: {results['pending_annotation_docs']}, "
            f"pipeline skipped: {results['pipeline_skipped']}, "
            f"annotations imported: {results['annotations_imported']}, "
            f"sidecar relationships captured: "
            f"{results['sidecar_relationships_found']}, "
            f"relationships created: {results['relationships_created']}"
        )

    except Corpus.DoesNotExist:
        logger.error(
            f"import_zip_with_folder_structure() - Corpus {corpus_id} not found"
        )
        results["completed"] = True
        results["errors"].append(f"Corpus not found: {corpus_id}")
    except CorpusFolder.DoesNotExist:
        logger.error(
            f"import_zip_with_folder_structure() - Target folder {target_folder_id} not found"
        )
        results["completed"] = True
        results["errors"].append(f"Target folder not found: {target_folder_id}")
    except Exception as e:
        logger.error(
            f"import_zip_with_folder_structure() - Job failed with error: {str(e)}"
        )
        results["completed"] = True
        results["errors"].append(f"Job failed: {str(e)}")

    return results
