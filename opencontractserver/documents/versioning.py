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

from django.core.files.base import ContentFile, File
from django.db import transaction
from django.db.models import Q

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
    content: bytes | None,
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

    Raises:
        ValueError: if ``content`` is ``None``. Callers reach this branch only
            when no file object (``content_file`` / ``pdf_file`` / ``txt_file``)
            was supplied, in which case the ``content`` bytes are mandatory.
            ``import_document``'s hash-source guard rejects the all-``None`` case
            up front; this is the explicit fail-closed backstop so a future
            caller that slips past it gets a clear error instead of a
            ``ContentFile(None, ...)`` ``TypeError``.
    """
    if content is None:
        raise ValueError(
            "_create_content_file requires content bytes when no file object "
            "is provided (got content=None)."
        )

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


def compute_sha256_for_file(file_obj: "File") -> str:
    """
    Stream a Django ``File`` (or bare file-like) and return its SHA-256 hex
    digest.

    This is the streaming counterpart to :func:`compute_sha256`: it reads the
    file in ``File.chunks()`` blocks so peak memory stays O(block) instead of
    the full file size, which is what lets a large single-document import skip
    buffering the whole file in RAM (issue #1843). The cursor is rewound to the
    start afterward so the storage write that follows sees the entire file.

    NOTE: this is two disk passes — once here for the hash, once again for the
    storage write that follows. Peak memory is O(block), not O(file), but on a
    network-backed storage backend (S3/GCS) a multi-GB upload is read end-to-end
    twice; that is the deliberate trade for not holding the whole file in RAM.
    """
    hasher = hashlib.sha256()
    # Django ``File`` exposes ``chunks()`` (which seeks to 0 before iterating);
    # wrap a bare file-like so either kind of object can be passed.
    chunked = file_obj if hasattr(file_obj, "chunks") else File(file_obj)
    for block in chunked.chunks():
        hasher.update(block)
    # ``chunks()`` leaves the cursor at EOF; rewind for the subsequent read.
    try:
        file_obj.seek(0)
    except (AttributeError, ValueError):  # pragma: no cover - non-seekable
        pass
    return hasher.hexdigest()


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
    content: Optional[bytes],
    user: "User",
    folder: Optional[CorpusFolder] = None,
    pdf_file=None,
    txt_file=None,
    content_file: "File | None" = None,
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
        content: The file content as bytes. May be ``None`` when the content
            is supplied as a file object instead (``content_file`` or the
            type-specific ``pdf_file`` / ``txt_file``), in which case the
            SHA-256 hash is computed by streaming the file rather than from a
            ``bytes`` blob — see issue #1843.
        user: The user performing the import
        folder: Optional folder to place the document in
        pdf_file: Optional Django file object for binary files
        txt_file: Optional Django file object for text files
        content_file: Optional Django file object whose content is routed to
            ``pdf_file`` or ``txt_file`` automatically based on the detected
            file type. Lets streaming callers hand over a single on-disk file
            (e.g. a reassembled chunked upload) without knowing the storage
            field up front.
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

    # Handle file_type - use default if None or missing
    file_type = doc_kwargs.get("file_type") or "application/pdf"
    is_text = _is_text_file(file_type)

    # ``content_file`` is a type-agnostic streaming alternative to ``content``
    # bytes: route it to the storage field that matches the file type so the
    # create/update branches below store it directly instead of materialising a
    # ContentFile from in-memory bytes.
    if content_file is not None:
        # Reject — rather than silently drop — a caller that supplies both the
        # type-agnostic ``content_file`` and the matching explicit file object.
        # ``import_content`` enforces the same ``content``/``content_file``
        # mutual-exclusion; do the equivalent here so the two surfaces behave
        # consistently and a future caller can't lose ``content_file`` to a
        # stray ``pdf_file``/``txt_file``.
        if (is_text and txt_file is not None) or (not is_text and pdf_file is not None):
            raise ValueError(
                "import_document accepts either ``content_file`` or the explicit "
                "``pdf_file``/``txt_file`` for the file type, not both"
            )
        if is_text:
            txt_file = content_file
        else:
            pdf_file = content_file

    # Compute the content hash. Prefer the in-memory bytes when present;
    # otherwise stream the stored file so peak memory stays O(block) rather
    # than the full document size (issue #1843).
    if content is not None:
        content_hash = compute_sha256(content)
    else:
        hash_source = txt_file if is_text else pdf_file
        if hash_source is None:
            raise ValueError(
                "import_document requires either ``content`` bytes or a matching "
                "file object (``content_file``, or ``pdf_file`` / ``txt_file`` "
                "for the file type)"
            )
        # NOTE: this streams the file end-to-end once for the hash; the storage
        # write below reads it again (see the double-pass NOTE in
        # ``compute_sha256_for_file``). For a multi-GB file on S3/GCS that is
        # two full reads — intentional, to keep peak memory O(block).
        content_hash = compute_sha256_for_file(hash_source)

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
            # Text files go to txt_extract_file, everything else to pdf_file.
            # Mirror the create-path logic (lines 324-343): if a File object
            # was passed explicitly, use it; otherwise materialise the
            # ``content`` bytes into a fresh ContentFile. Reusing the old
            # doc's stored file here would silently drop the new content on
            # a version-up (it inherits the previous version's bytes).
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
    from opencontractserver.corpuses.services.paths import CorpusPathService

    with transaction.atomic():
        deleted = DocumentPath.objects.select_for_update().get(
            corpus=corpus, path=path, is_current=True, is_deleted=True
        )

        # The original path may have been reused by a new document while this
        # one was in the trash. Restoring onto an occupied path would violate
        # ``unique_active_path_per_corpus``; disambiguate so both survive.
        #
        # TOCTOU: the select_for_update above locks only the deleted row, not
        # the active rows ``disambiguate_path`` reads. A concurrent import
        # landing on ``restore_path`` between this SELECT and the create below
        # loses the unique-active-path race and surfaces as an IntegrityError
        # (loud, not silent — matching the documented race note in
        # ``Corpus.add_document``). The ``lifecycle.restore_document`` wrapper
        # is the catch point for callers that need graceful degradation.
        restore_path = CorpusPathService.disambiguate_path(deleted.path, corpus)

        deleted.is_current = False
        deleted.save(update_fields=["is_current"])

        restored_path = DocumentPath.objects.create(
            document=deleted.document,
            corpus=corpus,
            folder=deleted.folder,
            path=restore_path,
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

    def determine_action(node: DocumentPath, previous: DocumentPath | None) -> str:
        """Map the canonical ``DocumentPath.infer_action`` result onto this
        function's historical label set.

        Action *logic* lives in ``DocumentPath.infer_action`` (the single
        source of truth shared with the GraphQL resolvers); only the legacy
        label vocabulary differs here and is preserved for backward
        compatibility:

        * canonical ``IMPORTED`` -> ``"CREATED"``
        * canonical ``UPDATED`` is split back into ``"UPDATED"`` (the document
          actually changed) vs ``"UNKNOWN"`` (a no-op record whose path,
          folder, AND document all match the parent).
        * ``MOVED`` / ``DELETED`` / ``RESTORED`` pass through unchanged.
        """
        canonical = node.infer_action(previous)
        if canonical == DocumentPath.ACTION_IMPORTED:
            return "CREATED"
        if canonical == DocumentPath.ACTION_UPDATED:
            if previous is not None and node.document_id == previous.document_id:
                return "UNKNOWN"
            return "UPDATED"
        return canonical

    # Walk the parent chain once, caching each node so action inference reuses
    # the already-fetched predecessor instead of issuing a second query per
    # node.
    chain: list[DocumentPath] = []
    current = document_path
    while current:
        chain.append(current)
        current = current.parent

    history = []
    # ``chain`` is newest -> oldest; ``chain[idx + 1]`` is each node's parent.
    for idx, node in enumerate(chain):
        previous = chain[idx + 1] if idx + 1 < len(chain) else None
        history.append(
            {
                "id": node.id,
                "timestamp": node.created,
                "path": node.path,
                "folder_id": node.folder_id,
                "version": node.version_number,
                "deleted": node.is_deleted,
                "document_id": node.document_id,
                "action": determine_action(node, previous),
            }
        )

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

    # Scope the OUTER query to this corpus too. The correlated subquery already
    # constrains results to corpus rows, but without ``corpus=corpus`` here the
    # outer query evaluates the subquery against every DocumentPath row in the
    # whole table (a full-table scan that grows with the global corpus count,
    # not this corpus's size).
    return (
        DocumentPath.objects.filter(corpus=corpus, id__in=Subquery(newest_before_time))
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

    NOTE: Under Phase-2 corpus isolation (Rule I1), each corpus gets its own
    isolated Document copy with a distinct primary key, so in normal operation
    a given ``document`` is referenced by exactly one corpus and this returns
    ``False``. It is retained as a deliberate safety net: it guards against any
    future or out-of-band path that shares a single Document across corpora, so
    ``permanently_delete_document`` never hard-deletes a row another corpus
    still points at. Do not remove without re-checking that isolation invariant.
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

    This is IRREVERSIBLE and performs the following cleanup (the step
    numbers match the inline comments in the implementation below):

    1. Verify the document is currently soft-deleted in this corpus.
    2. Collect every DocumentPath id for the (document, corpus) pair so
       the cascade scope is bounded to this corpus' history.
    3. Delete DocumentSummaryRevision records for the (document, corpus)
       pair.
    4. Delete corpus-scoped user relationships (non-structural) on this
       document.
    5. Delete corpus-scoped user annotations (non-structural) on this
       document.
    6. Delete every DocumentPath record collected in step 2.
    7. If no other corpus references the document (Rule Q1), delete the
       Document itself. Cascade then cleans up notes, datacells, agent
       results, etc. and the ``_gc_orphan_structural_set`` post_delete
       signal drops the ``StructuralAnnotationSet`` (with its structural
       annotations and structural relationships) iff no other Document
       references it.

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

        # Step 4: Delete corpus-scoped (non-structural) user relationships on
        # this document. Two patterns are covered in one query:
        #   a) Relationships explicitly tagged ``document=doc`` (the corpus-
        #      scoped owner).
        #   b) Relationships referencing any non-structural annotation on this
        #      doc as source or target — catches legacy rows that may have
        #      ``document_id`` unset.
        # Structural relationships (``structural_set IS NOT NULL``) are
        # preserved here; they're garbage-collected by the
        # ``_gc_orphan_structural_set`` signal when the Document is deleted
        # below and no other Document references the set.
        # The annotation membership is expressed as a subquery so we don't
        # materialise potentially-large pk lists into Python memory before
        # the DELETE; PostgreSQL handles the IN-via-subquery plan well.
        user_annotations_qs = Annotation.objects.filter(
            document=document,
            structural_set__isnull=True,
        )
        # ``distinct()`` is required because the M2M joins on
        # ``source_annotations`` / ``target_annotations`` can yield the
        # same Relationship row twice. ``.delete()`` itself collapses to
        # ``pk IN (...)`` and won't double-delete, but the returned count
        # would otherwise overstate the number of rows removed.
        relationship_count = (
            Relationship.objects.filter(
                Q(document=document, structural_set__isnull=True)
                | Q(source_annotations__in=user_annotations_qs)
                | Q(target_annotations__in=user_annotations_qs)
            )
            .distinct()
            .delete()[0]
        )
        logger.debug("Deleted %s Relationship records", relationship_count)

        # Step 5: Delete user annotations (non-structural) on this document.
        # Structural annotations live on the shared StructuralAnnotationSet
        # and are GC'd via the post_delete signal below, not here. Reuse the
        # lazy queryset defined above (it isn't materialised, just compiled
        # into the relationship subquery) so the filter stays DRY.
        annotation_count = user_annotations_qs.delete()[0]
        logger.debug("Deleted %s user Annotation records", annotation_count)

        # Step 6: Delete all DocumentPath records for this document in corpus
        DocumentPath.objects.filter(id__in=path_ids).delete()
        logger.debug("Deleted %s DocumentPath records", len(path_ids))

        # Step 7: Check if document should be deleted (Rule Q1 extended).
        # Document can be deleted if no other corpus has any reference to it.
        # The Document.delete() call cascades to remaining corpus-scoped
        # objects (notes, datacells, agent results, embeddings) and fires
        # the structural-set GC signal which drops the shared
        # StructuralAnnotationSet iff no other Document references it.
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
