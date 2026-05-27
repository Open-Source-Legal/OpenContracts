"""Agentic tool to create or version-up a text-based document in a corpus.

This tool is intentionally scoped to text-based formats only
(``TEXT_MIMETYPES`` — text/plain, text/markdown, application/txt). Binary
formats (PDF, DOCX, etc.) require the parsing pipeline and are out of scope.

The tool delegates to ``Corpus.import_content`` which uses
``opencontractserver.documents.versioning.import_document`` — the single
source of truth for the dual-tree versioning architecture. If a document
already exists at the derived path in the corpus a new version is created;
otherwise a fresh document is added at that path.
"""

from typing import Any

from opencontractserver.constants.document_processing import (
    DEFAULT_DOCUMENT_PATH_PREFIX,
    MAX_FILENAME_LENGTH,
    TEXT_MIMETYPES,
)
from opencontractserver.corpuses.models import Corpus

from ._helpers import _db_sync_to_async


def _derive_path_from_title(title: str) -> str:
    """Generate a corpus filesystem path from a document title.

    Mirrors the sanitisation used by ``Corpus.add_document`` so that
    callers that pass the same title repeatedly hit the same path and
    therefore the same version tree.
    """
    safe_title = "".join(
        c if c.isalnum() or c in "-_." else "_" for c in title[:MAX_FILENAME_LENGTH]
    )
    if not safe_title:
        # Fall back to a stable placeholder so the path is still valid.
        safe_title = "untitled"
    return f"{DEFAULT_DOCUMENT_PATH_PREFIX}/{safe_title}"


def create_or_update_text_document(
    corpus_id: int,
    title: str,
    content: str,
    # author_id is always injected from agent context (never LLM-provided),
    # so it is required (int) rather than the int | None = None convention
    # used by tools where the parameter may be absent.
    author_id: int,
    description: str = "",
    folder_id: int | None = None,
    file_type: str = "text/plain",
) -> dict[str, Any]:
    """Create a text document in the target corpus, or version-up an existing one.

    If a document already exists at the path derived from ``title`` in this
    corpus, a new version is created (versioning is handled automatically by
    the dual-tree versioning architecture). Otherwise a new document is
    added to the corpus at that path.

    Only text-based formats are supported: ``text/plain`` (default),
    ``text/markdown``, and ``application/txt``. Binary formats (PDF, DOCX,
    etc.) require the parsing pipeline and are not handled here.

    Args:
        corpus_id: ID of the target corpus.
        title: Title of the document. Used as the document title and to
            derive the corpus filesystem path (so calling the tool twice
            with the same title and corpus version-ups the existing doc).
        content: Full text content of the document (UTF-8).
        author_id: ID of the user performing the operation.
        description: Optional description applied to the new (or new
            version of the) document.
        folder_id: Optional CorpusFolder ID inside the same corpus. When
            omitted the document lives at the corpus root.
        file_type: MIME type. Must be one of ``TEXT_MIMETYPES``.

    Returns:
        Dict with keys: ``status`` (``"created"`` or ``"updated"``),
        ``document_id``, ``corpus_id``, ``path``, ``version_number``,
        ``file_type``, ``byte_count``, ``message``.

    Raises:
        ValueError: If any referenced object does not exist or is not
            accessible, the file_type is unsupported, the content is empty,
            or the upload quota is exceeded.
        PermissionError: If the user lacks UPDATE permission on the corpus.
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.corpuses.services import FolderCRUDService
    from opencontractserver.documents.document_service import DocumentService
    from opencontractserver.types.enums import PermissionTypes
    from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

    User = get_user_model()

    # Validate inputs up front so we don't burn DB lookups on a bad request.
    if not title or not title.strip():
        raise ValueError("title must be a non-empty string.")

    if content is None:
        raise ValueError("content must be a string (got None).")

    if file_type not in TEXT_MIMETYPES:
        raise ValueError(
            f"Unsupported file_type {file_type!r}. "
            f"Only text-based formats are supported: {sorted(TEXT_MIMETYPES)}."
        )

    # Resolve user first so subsequent lookups can be scoped to objects
    # visible to that user (IDOR prevention per CLAUDE.md).
    try:
        user = User.objects.get(pk=author_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={author_id} does not exist.")

    try:
        corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
    except Corpus.DoesNotExist:
        raise ValueError(
            f"Corpus with id={corpus_id} does not exist or is not accessible."
        )

    if not corpus.user_can(user, PermissionTypes.UPDATE):
        raise PermissionError(
            "Permission denied: you do not have write access to this corpus."
        )

    folder = None
    if folder_id is not None:
        folder = FolderCRUDService.get_folder_by_id(user, folder_id)
        # Early cross-corpus check — same generic error as not-found/inaccessible
        # so a readable-but-wrong-corpus folder doesn't leak information
        # through a distinguishable message (IDOR prevention).
        if folder is None or folder.corpus_id != corpus.id:
            raise ValueError(
                f"Folder with id={folder_id} does not exist or is not accessible."
            )

    path = _derive_path_from_title(title)

    # Apply the same quota check that DocumentService.create_document enforces.
    # Every version-up creates a new Document row (sharing the version tree),
    # so capped users hit the limit on either path; we charge both.
    can_upload, quota_error = DocumentService.check_user_upload_quota(user)
    if not can_upload:
        raise ValueError(quota_error)

    content_bytes = content.encode("utf-8")

    document, status, _path_record = corpus.import_content(
        content=content_bytes,
        user=user,
        path=path,
        folder=folder,
        file_type=file_type,
        title=title,
        description=description,
    )

    # Grant CRUD permissions on the new (or new-version) document so the
    # caller can interact with it from user-facing surfaces. Mirrors
    # CorpusDocumentService.add_document_to_corpus.
    set_permissions_for_obj_to_user(
        user,
        document,
        [PermissionTypes.CRUD],
    )

    return {
        "status": status,
        "document_id": document.id,
        "corpus_id": corpus.id,
        "path": path,
        "version_number": _path_record.version_number,
        "file_type": file_type,
        "byte_count": len(content_bytes),
        "message": (
            f"Document {document.id} {status} at {path} "
            f"(v{_path_record.version_number}) in corpus {corpus.id}."
        ),
    }


async def acreate_or_update_text_document(
    corpus_id: int,
    title: str,
    content: str,
    # See create_or_update_text_document() for why author_id is int.
    author_id: int,
    description: str = "",
    folder_id: int | None = None,
    file_type: str = "text/plain",
) -> dict[str, Any]:
    """Async wrapper around :func:`create_or_update_text_document`."""
    return await _db_sync_to_async(create_or_update_text_document)(
        corpus_id=corpus_id,
        title=title,
        content=content,
        author_id=author_id,
        description=description,
        folder_id=folder_id,
        file_type=file_type,
    )


# Aliases for callers that prefer the more agentic verb-first name.
upload_text_document = create_or_update_text_document
aupload_text_document = acreate_or_update_text_document
