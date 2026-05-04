"""
Dual-Tree Document Versioning Operations

This module implements the core operations for the dual-tree versioning architecture.
It provides functions for import, move, delete, restore, and query operations on documents
within the corpus filesystem.

Architecture Rules Implemented:
- Content Tree (Document model):
  - C1: New Document only when hash first seen in THIS corpus
  - C2: Updates create child nodes of previous version
  - C3: Only one current Document per version tree

- Path Tree (DocumentPath model):
  - P1: Every lifecycle event creates new node
  - P2: New nodes are children of previous state
  - P3: Only current filesystem state is is_current=True
  - P4: One active path per (corpus, path) tuple
  - P5: Version number increments only on content changes
  - P6: Folder deletion sets folder=NULL

- Interaction Rules (Updated for Corpus Isolation):
  - I1: Corpuses have completely isolated Documents with independent version trees
  - I2: Provenance tracked via source_document field
  - I3: File storage can be deduplicated by hash (blob sharing, not Document sharing)
  - Q1: Content "truly deleted" when no active paths point to it
"""

import hashlib
import logging
import mimetypes
import uuid
from typing import TYPE_CHECKING, Literal, Optional

from django.core.files.base import ContentFile
from django.db import transaction

from opencontractserver.constants.document_processing import TEXT_MIMETYPES
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath

if TYPE_CHECKING:
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


# Map MIME types to file extensions for creating filenames
MIME_TO_EXTENSION = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}


def _create_content_file(
    content: bytes,
    content_hash: str,
    path: str,
    file_type: str = "application/pdf",
) -> ContentFile:
    """
    Create a Django ContentFile from raw content bytes.

    Used when importing content that doesn't have an associated file object.
    The filename is derived from the path or hash, with the appropriate extension.

    Args:
        content: Raw file content bytes
        content_hash: SHA-256 hash of the content (used for filename if path not available)
        path: The document path (used to derive filename)
        file_type: MIME type to determine file extension

    Returns:
        ContentFile ready for assignment to a FileField
    """
    # Handle None file_type - default to binary
    if not file_type:
        file_type = "application/octet-stream"

    # Get extension from MIME type
    extension = MIME_TO_EXTENSION.get(file_type)
    if not extension:
        # Fallback to mimetypes library
        extension = mimetypes.guess_extension(file_type) or ".bin"

    # Derive filename from path or use hash
    if path:
        # Extract filename from path, e.g., "/documents/my_file.pdf" -> "my_file"
        base_name = path.split("/")[-1]
        # Remove existing extension if present
        if "." in base_name:
            base_name = base_name.rsplit(".", 1)[0]
    else:
        # Use hash prefix as filename
        base_name = f"doc_{content_hash[:12]}"

    filename = f"{base_name}{extension}"
    return ContentFile(content, name=filename)


def _is_text_file(file_type: str | None) -> bool:
    """Check if the file type should be stored as txt_extract_file."""
    if not file_type:
        return False
    return file_type in TEXT_MIMETYPES


def compute_sha256(content: bytes) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content).hexdigest()


def calculate_content_version(document: Document) -> int:
    """
    Calculate the version number of a document by counting
    ancestors in the content tree.

    Implements: Rule C2 traversal
    """
    count = 1
    current = document
    while current.parent_id:
        count += 1
        current = current.parent
    return count


def import_document(
    corpus: Corpus,
    path: str,
    content: bytes,
    user: "User",
    folder: Optional[CorpusFolder] = None,
    pdf_file=None,
    txt_file=None,
    **doc_kwargs,
) -> tuple[Document, str, DocumentPath]:
    """
    Import or update a document with dual-tree versioning logic.

    This implements corpus-isolated document management. Documents are isolated
    within each corpus with independent version trees. Provenance is tracked
    via source_document field for traceability.

    Supports all file types with unified versioning:
    - Binary formats (PDF, DOCX, etc.): Stored in pdf_file field
    - Text files: Stored in txt_extract_file field

    Args:
        corpus: The corpus to import into
        path: The filesystem path within the corpus
        content: The file content as bytes
        user: The user performing the import
        folder: Optional folder to place the document in
        pdf_file: Optional Django file object for binary files
        txt_file: Optional Django file object for text files
        **doc_kwargs: Additional keyword arguments for Document creation
            - file_type (str): MIME type (determines storage field)
            - ingestion_source (IngestionSource | None): Source that produced
              this document (stored on DocumentPath)
            - external_id (str | None): External system identifier (stored on
              DocumentPath)
            - ingestion_metadata (dict | None): Arbitrary source metadata such
              as URL, crawl job ID, etc. (stored on DocumentPath)

    Returns:
        Tuple of (document, status, path_record) where status is one of:
        - 'created': New document at new path
        - 'updated': New version at existing path

    Note: No content-based deduplication is performed. Each upload creates
    a new document regardless of content hash.
    """
    # Extract path-level lineage kwargs before they hit Document.objects.create()
    path_kwargs = {}
    for key in ("ingestion_source", "external_id", "ingestion_metadata"):
        if key in doc_kwargs:
            path_kwargs[key] = doc_kwargs.pop(key)

    content_hash = compute_sha256(content)
    # Handle file_type - use default if None or missing
    file_type = doc_kwargs.get("file_type") or "application/pdf"
    is_text = _is_text_file(file_type)

    with transaction.atomic():
        # Step 1: Check if this path already exists in THIS corpus
        current_path = (
            DocumentPath.objects.filter(
                corpus=corpus, path=path, is_current=True, is_deleted=False
            )
            .select_for_update()
            .first()
        )

        if current_path:
            # Path exists - always create new version (no content-based deduplication)
            old_doc = current_path.document

            logger.info(
                f"Creating new version of doc {old_doc.id} for {path} "
                f"in corpus {corpus.id}"
            )

            # Mark old as not current in this version tree
            Document.objects.filter(version_tree_id=old_doc.version_tree_id).update(
                is_current=False
            )

            # Determine file storage based on file type
            # Text files go to txt_extract_file, everything else to pdf_file
            if is_text:
                effective_txt_file = txt_file or old_doc.txt_extract_file
                if not effective_txt_file:
                    effective_txt_file = _create_content_file(
                        content=content,
                        content_hash=content_hash,
                        path=path,
                        file_type=file_type,
                    )
                effective_pdf_file = None
            else:
                effective_pdf_file = pdf_file or old_doc.pdf_file
                if not effective_pdf_file:
                    effective_pdf_file = _create_content_file(
                        content=content,
                        content_hash=content_hash,
                        path=path,
                        file_type=file_type,
                    )
                effective_txt_file = None

            # Inherit structural annotation set only when content is unchanged.
            # When content changes (different hash), the parser will create a
            # fresh StructuralAnnotationSet for the new content during ingestion.
            old_set = old_doc.structural_annotation_set
            if old_set and old_doc.pdf_file_hash == content_hash:
                inherited_set = old_set
            else:
                inherited_set = None

            # Create new document version (isolated within corpus)
            # Documents in public corpora inherit is_public=True so that
            # the permissioning guide rule (both flags must be True) is
            # naturally satisfied without queryset-level overrides.
            new_doc = Document.objects.create(
                title=doc_kwargs.get("title", old_doc.title),
                description=doc_kwargs.get("description", old_doc.description),
                file_type=file_type,
                pdf_file=effective_pdf_file,
                txt_extract_file=effective_txt_file,
                pdf_file_hash=content_hash,
                version_tree_id=old_doc.version_tree_id,  # Same tree
                parent=old_doc,
                is_current=True,
                is_public=corpus.is_public
                or old_doc.is_public
                or doc_kwargs.get("is_public", False),
                structural_annotation_set=inherited_set,
                creator=user,
                **{
                    k: v
                    for k, v in doc_kwargs.items()
                    if k not in ["title", "description", "file_type", "is_public"]
                },
            )

            # Apply Rules P1, P2, P3
            current_path.is_current = False
            current_path.save(update_fields=["is_current"])

            new_path = DocumentPath.objects.create(
                document=new_doc,
                corpus=corpus,
                folder=folder or current_path.folder,
                path=path,
                version_number=current_path.version_number + 1,  # Rule P5
                parent=current_path,  # Rule P2
                is_current=True,  # Rule P3
                is_deleted=False,
                creator=user,
                **path_kwargs,
            )

            logger.info(
                f"Updated {path} in corpus {corpus.id}: "
                f"doc {old_doc.id} v{current_path.version_number} → "
                f"doc {new_doc.id} v{new_path.version_number}"
            )

            # Trigger corpus actions if document is ready (not still processing)
            # If backend_lock=True, actions will be triggered by
            # set_doc_lock_state in doc_tasks.py when processing completes.
            if not new_doc.backend_lock:
                from opencontractserver.corpuses.models import CorpusActionTrigger
                from opencontractserver.tasks.corpus_tasks import process_corpus_action

                logger.info(
                    f"[import_document] Doc {new_doc.id} is ready, "
                    f"triggering corpus actions for corpus {corpus.id}"
                )
                transaction.on_commit(
                    lambda: process_corpus_action.delay(
                        corpus_id=corpus.id,
                        document_ids=[new_doc.id],
                        user_id=user.id,
                        trigger=CorpusActionTrigger.ADD_DOCUMENT,
                    )
                )

            return new_doc, "updated", new_path

        else:
            # New path in this corpus - create fresh document (no content-based deduplication)
            # Each upload is processed independently regardless of content hash
            tree_id = uuid.uuid4()

            # Determine file storage based on file type
            # Text files go to txt_extract_file, everything else to pdf_file
            if is_text:
                effective_txt_file = txt_file
                if not effective_txt_file:
                    effective_txt_file = _create_content_file(
                        content=content,
                        content_hash=content_hash,
                        path=path,
                        file_type=file_type,
                    )
                effective_pdf_file = None
            else:
                effective_pdf_file = pdf_file
                if not effective_pdf_file:
                    effective_pdf_file = _create_content_file(
                        content=content,
                        content_hash=content_hash,
                        path=path,
                        file_type=file_type,
                    )
                effective_txt_file = None

            # Documents in public corpora inherit is_public=True so that
            # the permissioning guide rule (both flags must be True) is
            # naturally satisfied without queryset-level overrides.
            doc = Document.objects.create(
                title=doc_kwargs.get("title", f"Document at {path}"),
                description=doc_kwargs.get("description", ""),
                file_type=file_type,
                pdf_file=effective_pdf_file,
                txt_extract_file=effective_txt_file,
                pdf_file_hash=content_hash,
                version_tree_id=tree_id,
                is_current=True,
                is_public=corpus.is_public or doc_kwargs.get("is_public", False),
                parent=None,  # Root of content tree
                source_document=None,  # Set via add_document() when dragging existing docs
                creator=user,
                **{
                    k: v
                    for k, v in doc_kwargs.items()
                    if k not in ["title", "description", "file_type", "is_public"]
                },
            )
            version = 1
            status = "created"
            logger.info(
                "Created new doc %s at %s in corpus %s", doc.id, path, corpus.id
            )

            # Create root of path tree (Rule P1)
            new_path = DocumentPath.objects.create(
                document=doc,
                corpus=corpus,
                folder=folder,
                path=path,
                version_number=version,
                parent=None,  # Root of path tree
                is_current=True,
                is_deleted=False,
                creator=user,
                **path_kwargs,
            )

            # Trigger corpus actions if document is ready (not still processing)
            # If backend_lock=True, actions will be triggered by
            # set_doc_lock_state in doc_tasks.py when processing completes.
            if not doc.backend_lock:
                from opencontractserver.corpuses.models import CorpusActionTrigger
                from opencontractserver.tasks.corpus_tasks import process_corpus_action

                logger.info(
                    f"[import_document] Doc {doc.id} is ready, "
                    f"triggering corpus actions for corpus {corpus.id}"
                )
                transaction.on_commit(
                    lambda: process_corpus_action.delay(
                        corpus_id=corpus.id,
                        document_ids=[doc.id],
                        user_id=user.id,
                        trigger=CorpusActionTrigger.ADD_DOCUMENT,
                    )
                )

            return doc, status, new_path


def move_document(
    corpus: Corpus,
    old_path: str,
    new_path: str,
    user: "User",
    new_folder: "Optional[CorpusFolder] | Literal['UNSET']" = "UNSET",
) -> DocumentPath:
    """
    Move document - creates new DocumentPath, Document unchanged.

    Implements: Rules P1, P2, P3, P5 (no version increment on move)

    Note: new_folder defaults to 'UNSET' to distinguish between "keep current folder"
    and "explicitly set to None". Pass None explicitly to remove folder.
    """
    with transaction.atomic():
        current = DocumentPath.objects.select_for_update().get(
            corpus=corpus, path=old_path, is_current=True, is_deleted=False
        )

        # Apply Rule P3
        current.is_current = False
        current.save(update_fields=["is_current"])

        folder_to_use: Optional[CorpusFolder]
        if new_folder == "UNSET":
            # Not specified, keep current folder
            folder_to_use = current.folder
        elif isinstance(new_folder, str):
            # Defensive: assert is stripped under python -O so use a real raise
            raise TypeError(
                f"new_folder must be a CorpusFolder, None, or 'UNSET'; "
                f"got {new_folder!r}"
            )
        else:
            # Explicitly set (could be None or a folder)
            folder_to_use = new_folder

        # Apply Rules P1, P2
        new_path_record = DocumentPath.objects.create(
            document=current.document,  # Same content
            corpus=corpus,
            folder=folder_to_use,
            path=new_path,
            version_number=current.version_number,  # Rule P5 - no increment
            parent=current,  # Rule P2
            is_current=True,
            is_deleted=False,
            creator=user,
            ingestion_source=current.ingestion_source,
            external_id=current.external_id,
            ingestion_metadata=current.ingestion_metadata,
        )

        logger.info(
            f"Moved doc {current.document_id} in corpus {corpus.id}: "
            f"{old_path} → {new_path}"
        )

        return new_path_record


def delete_document(corpus: Corpus, path: str, user: "User") -> DocumentPath:
    """
    Soft delete - creates deleted DocumentPath.

    Implements: Rules P1, P2, P3, P5 (no version increment on delete)
    """
    with transaction.atomic():
        current = DocumentPath.objects.select_for_update().get(
            corpus=corpus, path=path, is_current=True, is_deleted=False
        )

        current.is_current = False
        current.save(update_fields=["is_current"])

        deleted_path = DocumentPath.objects.create(
            document=current.document,
            corpus=corpus,
            folder=current.folder,
            path=current.path,
            version_number=current.version_number,  # Rule P5
            parent=current,  # Rule P2
            is_deleted=True,  # Soft delete
            is_current=True,
            creator=user,
            ingestion_source=current.ingestion_source,
            external_id=current.external_id,
            ingestion_metadata=current.ingestion_metadata,
        )

        logger.info(
            f"Soft deleted doc {current.document_id} at {path} "
            f"in corpus {corpus.id}"
        )

        return deleted_path


def restore_document(corpus: Corpus, path: str, user: "User") -> DocumentPath:
    """
    Restore deleted document.

    Implements: Rules P1, P2, P3
    """
    with transaction.atomic():
        deleted = DocumentPath.objects.select_for_update().get(
            corpus=corpus, path=path, is_current=True, is_deleted=True
        )

        deleted.is_current = False
        deleted.save(update_fields=["is_current"])

        restored_path = DocumentPath.objects.create(
            document=deleted.document,
            corpus=corpus,
            folder=deleted.folder,
            path=deleted.path,
            version_number=deleted.version_number,
            parent=deleted,
            is_deleted=False,  # Not deleted
            is_current=True,
            creator=user,
            ingestion_source=deleted.ingestion_source,
            external_id=deleted.external_id,
            ingestion_metadata=deleted.ingestion_metadata,
        )

        logger.info(
            f"Restored doc {deleted.document_id} at {path} " f"in corpus {corpus.id}"
        )

        return restored_path


# ========== Query Functions ==========


def get_current_filesystem(corpus: Corpus):
    """
    Get current filesystem state for a corpus.

    Returns: QuerySet of active DocumentPath records

    Implements: Rule P3
    """
    return DocumentPath.objects.filter(
        corpus=corpus, is_current=True, is_deleted=False
    ).select_related("document", "folder")


def get_content_history(document: Document):
    """
    Traverse content tree upward to get version history.

    Returns: List of Documents from oldest to newest

    Implements: Rule C2 traversal
    """
    history = []
    current = document
    while current:
        history.append(current)
        current = current.parent
    return list(reversed(history))  # Oldest to newest


def get_path_history(document_path: DocumentPath):
    """
    Traverse path tree upward to get lifecycle history.

    Returns: List of dicts with path lifecycle events from oldest to newest

    Implements: Rule P2 traversal
    """

    def determine_action(current, previous):
        """Determine what action this path record represents."""
        if not previous:
            return "CREATED"
        if current.is_deleted and not previous.is_deleted:
            return "DELETED"
        if not current.is_deleted and previous.is_deleted:
            return "RESTORED"
        # MOVED takes priority over UPDATED: a document replacement that also
        # changes the path is primarily a move (the path change is the visible
        # user action), and callers can inspect document_id to detect the
        # replacement separately.
        # folder_id can differ while path stays the same if a folder was
        # deleted and recreated with the same name — treat that as a move.
        if current.path != previous.path or current.folder_id != previous.folder_id:
            return "MOVED"
        if current.document_id != previous.document_id:
            return "UPDATED"
        return "UNKNOWN"

    history = []
    current = document_path
    while current:
        history.append(
            {
                "id": current.id,
                "timestamp": current.created,
                "path": current.path,
                "folder_id": current.folder_id,
                "version": current.version_number,
                "deleted": current.is_deleted,
                "document_id": current.document_id,
                "action": determine_action(current, current.parent),
            }
        )
        current = current.parent

    return list(reversed(history))  # Oldest to newest


def get_filesystem_at_time(corpus: Corpus, timestamp):
    """
    Reconstruct filesystem at specific time (time-travel query).

    Returns: QuerySet of DocumentPath records representing filesystem state

    Implements: Time-travel capability using Rule P1 (temporal tree)
    """
    from django.db.models import OuterRef, Subquery

    # For each unique path, find the most recent DocumentPath before timestamp
    newest_before_time = (
        DocumentPath.objects.filter(
            corpus=corpus, created__lte=timestamp, path=OuterRef("path")
        )
        .order_by("-created")
        .values("id")[:1]
    )

    return (
        DocumentPath.objects.filter(id__in=Subquery(newest_before_time))
        .exclude(is_deleted=True)
        .select_related("document", "folder")
    )


def is_content_truly_deleted(document: Document, corpus: Corpus) -> bool:
    """
    Check if content is "truly deleted" (no active paths point to it).

    Implements: Rule Q1
    """
    return not DocumentPath.objects.filter(
        document=document, corpus=corpus, is_current=True, is_deleted=False
    ).exists()


def has_references_in_other_corpuses(
    document: Document, exclude_corpus: Corpus
) -> bool:
    """
    Check if document has any DocumentPath references in other corpuses.

    Used to determine if Document can be deleted when permanently removing
    from a corpus (Rule Q1 extended).
    """
    return (
        DocumentPath.objects.filter(document=document)
        .exclude(corpus=exclude_corpus)
        .exists()
    )


def permanently_delete_document(
    corpus: Corpus, document: Document, user: "User"
) -> tuple[bool, str]:
    """
    Permanently delete a soft-deleted document from a corpus.

    This is IRREVERSIBLE and performs the following cleanup:
    1. Deletes ALL DocumentPath records for this document in the corpus (entire history)
    2. Deletes corpus-scoped user annotations (non-structural) on this document
    3. Deletes relationships involving those annotations
    4. Deletes DocumentSummaryRevision records for this document+corpus
    5. If no other corpus references the document (Rule Q1), deletes Document itself

    Args:
        corpus: The corpus to permanently delete from
        document: The document to permanently delete
        user: The user performing the deletion (for logging)

    Returns:
        Tuple of (success, error_message)

    Raises:
        Does not raise - returns (False, error_message) on failure
    """
    from opencontractserver.annotations.models import Annotation, Relationship

    with transaction.atomic():
        # Step 1: Verify document is currently soft-deleted in this corpus
        deleted_path = DocumentPath.objects.filter(
            document=document,
            corpus=corpus,
            is_current=True,
            is_deleted=True,
        ).first()

        if not deleted_path:
            return False, "Document is not in trash (not soft-deleted) in this corpus"

        # Step 2: Get all DocumentPath IDs for this document in this corpus
        # (includes entire history, not just current)
        path_ids = list(
            DocumentPath.objects.filter(
                document=document,
                corpus=corpus,
            ).values_list("id", flat=True)
        )

        logger.info(
            f"Permanently deleting document {document.id} from corpus {corpus.id} "
            f"({len(path_ids)} path records) by user {user.id}"
        )

        # Step 3: Delete DocumentSummaryRevision records for this doc+corpus
        from opencontractserver.documents.models import DocumentSummaryRevision

        summary_count = DocumentSummaryRevision.objects.filter(
            document=document,
            corpus=corpus,
        ).delete()[0]
        logger.debug("Deleted %s DocumentSummaryRevision records", summary_count)

        # Step 4: Delete user annotations (non-structural) for this document
        # Structural annotations live in StructuralAnnotationSet and are shared
        user_annotations = Annotation.objects.filter(
            document=document,
            structural_set__isnull=True,  # Only user annotations, not structural
        )

        # Step 5: Delete relationships involving these annotations first (FK constraint)
        # Use Q objects to delete in one operation to avoid counting duplicates
        # (same relationship could have both source and target in annotation_ids)
        from django.db.models import Q

        annotation_ids = list(user_annotations.values_list("id", flat=True))
        relationship_count = Relationship.objects.filter(
            Q(source_annotations__id__in=annotation_ids)
            | Q(target_annotations__id__in=annotation_ids)
        ).delete()[0]
        logger.debug("Deleted %s Relationship records", relationship_count)

        # Step 6: Delete the user annotations
        annotation_count = user_annotations.delete()[0]
        logger.debug("Deleted %s user Annotation records", annotation_count)

        # Step 7: Delete all DocumentPath records for this document in corpus
        DocumentPath.objects.filter(id__in=path_ids).delete()
        logger.debug("Deleted %s DocumentPath records", len(path_ids))

        # Step 8: Check if document should be deleted (Rule Q1 extended)
        # Document can be deleted if no other corpus has any reference to it
        if not has_references_in_other_corpuses(document, corpus):
            doc_id = document.id
            doc_title = document.title
            document.delete()
            logger.info(
                f"Deleted Document {doc_id} ({doc_title}) - no other corpus references"
            )
        else:
            logger.debug(
                f"Document {document.id} preserved - has references in other corpuses"
            )

        return True, ""


def permanently_delete_all_in_trash(
    corpus: Corpus, user: "User"
) -> tuple[int, list[str]]:
    """
    Permanently delete ALL soft-deleted documents in a corpus (empty trash).

    This function processes deletions one-by-one and allows partial success.
    Each document deletion is wrapped in its own atomic transaction via
    `permanently_delete_document`, so if one fails, others may still succeed.

    Design Decision: Partial deletions are intentionally allowed because:
    1. Document-level isolation: Each document's deletion is independent
    2. Better UX: Users get feedback on what succeeded/failed
    3. Recoverability: Failed items remain in trash for retry
    4. Each individual deletion is fully atomic (all-or-nothing at doc level)

    Args:
        corpus: The corpus to empty trash for
        user: The user performing the deletion

    Returns:
        Tuple of (deleted_count, list_of_errors) where:
        - deleted_count: Number of documents successfully deleted
        - list_of_errors: List of error messages for failed deletions
        Note: deleted_count > 0 with non-empty errors indicates partial success.
    """
    # Get all currently soft-deleted documents
    deleted_paths = DocumentPath.objects.filter(
        corpus=corpus,
        is_current=True,
        is_deleted=True,
    ).select_related("document")

    deleted_count = 0
    errors = []

    # Get unique documents (a document might have multiple deleted paths theoretically)
    documents = {path.document for path in deleted_paths}

    for document in documents:
        success, error = permanently_delete_document(corpus, document, user)
        if success:
            deleted_count += 1
        else:
            errors.append(f"Document {document.id}: {error}")

    logger.info(
        f"Empty trash completed for corpus {corpus.id}: "
        f"{deleted_count} deleted, {len(errors)} errors"
    )

    return deleted_count, errors
