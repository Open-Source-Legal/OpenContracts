"""
Utility functions for bulk ingestion operations.

Provides bulk versions of expensive per-document operations:
- Permission assignment (bypassing guardian's per-object overhead)
- Staging file I/O (reading from S3/GCS/local staging areas)
- Thumbnail handling
"""

import base64
import json
import logging
from io import BytesIO

from django.apps import apps
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from opencontractserver.bulk_ingestion.constants import (
    BULK_INGESTION_PERMISSION_BATCH_SIZE,
    BULK_INGESTION_STAGING_PREFIX,
)

logger = logging.getLogger(__name__)


def bulk_create_document_permissions(documents, user) -> int:
    """
    Create object-level permissions for multiple documents in bulk.

    This replaces the per-document set_permissions_for_obj_to_user() call,
    which does 7 remove_perm queries + multiple assign_perm queries per document.
    Instead, this does a single bulk_create with ignore_conflicts=True.

    Args:
        documents: Iterable of Document instances (must have pk set)
        user: The User to grant permissions to

    Returns:
        Number of permission rows created
    """
    Document = apps.get_model("documents", "Document")
    DocumentUserObjectPermission = apps.get_model(
        "documents", "DocumentUserObjectPermission"
    )

    doc_ct = ContentType.objects.get_for_model(Document)
    perm_codenames = [
        "create_document",
        "read_document",
        "update_document",
        "remove_document",
    ]

    perms = list(
        Permission.objects.filter(
            content_type=doc_ct,
            codename__in=perm_codenames,
        )
    )

    if not perms:
        logger.warning("No document permissions found in database")
        return 0

    perm_objects = []
    for doc in documents:
        for perm in perms:
            perm_objects.append(
                DocumentUserObjectPermission(
                    content_object=doc,
                    permission=perm,
                    user=user,
                )
            )

    created = DocumentUserObjectPermission.objects.bulk_create(
        perm_objects,
        batch_size=BULK_INGESTION_PERMISSION_BATCH_SIZE,
        ignore_conflicts=True,
    )

    count = len(created)
    logger.info(f"Bulk-created {count} permission rows for {len(list(documents))} documents")
    return count


def bulk_create_document_path_permissions(document_paths, user) -> int:
    """
    Create object-level permissions for multiple DocumentPaths in bulk.

    Args:
        document_paths: Iterable of DocumentPath instances (must have pk set)
        user: The User to grant permissions to

    Returns:
        Number of permission rows created
    """
    DocumentPath = apps.get_model("documents", "DocumentPath")
    DocumentPathUserObjectPermission = apps.get_model(
        "documents", "DocumentPathUserObjectPermission"
    )

    dp_ct = ContentType.objects.get_for_model(DocumentPath)
    perm_codenames = [
        "create_documentpath",
        "read_documentpath",
        "update_documentpath",
        "remove_documentpath",
    ]

    perms = list(
        Permission.objects.filter(
            content_type=dp_ct,
            codename__in=perm_codenames,
        )
    )

    if not perms:
        logger.warning("No DocumentPath permissions found in database")
        return 0

    perm_objects = []
    for dp in document_paths:
        for perm in perms:
            perm_objects.append(
                DocumentPathUserObjectPermission(
                    content_object=dp,
                    permission=perm,
                    user=user,
                )
            )

    created = DocumentPathUserObjectPermission.objects.bulk_create(
        perm_objects,
        batch_size=BULK_INGESTION_PERMISSION_BATCH_SIZE,
        ignore_conflicts=True,
    )

    count = len(created)
    logger.info(
        f"Bulk-created {count} permission rows for "
        f"{len(list(document_paths))} document paths"
    )
    return count


def read_staged_file(staged_path: str) -> bytes:
    """
    Read a file from the staging area.

    Supports the project's configured storage backend (S3, GCS, local)
    via Django's default_storage.

    Args:
        staged_path: Path relative to the storage root, or absolute path
            for local storage.

    Returns:
        File content as bytes.

    Raises:
        FileNotFoundError: If the staged file doesn't exist.
    """
    try:
        with default_storage.open(staged_path, "rb") as f:
            return f.read()
    except Exception as e:
        raise FileNotFoundError(
            f"Could not read staged file at {staged_path}: {e}"
        ) from e


def read_jsonl_batch(batch_path: str) -> list[dict]:
    """
    Read a JSONL batch file from staging storage.

    Each line is a JSON object representing a PreParsedDocumentBundle.
    Lines with parse errors are logged and skipped.

    Args:
        batch_path: Path to the JSONL file in storage.

    Returns:
        List of parsed dictionaries.
    """
    raw = read_staged_file(batch_path)
    records = []
    for line_num, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            logger.error(
                f"Skipping malformed JSON at line {line_num} in {batch_path}: {e}"
            )
    return records


def read_batch_manifest(manifest_path: str) -> dict:
    """
    Read and parse a BatchManifest JSON file from staging storage.

    Args:
        manifest_path: Path to the manifest.json file.

    Returns:
        Parsed manifest dictionary.
    """
    raw = read_staged_file(manifest_path)
    return json.loads(raw.decode("utf-8"))


def save_thumbnail_from_base64(document, thumbnail_base64: str, fmt: str = "png"):
    """
    Save a pre-generated thumbnail to a document's icon field.

    Args:
        document: Document instance to save thumbnail to.
        thumbnail_base64: Base64-encoded image data.
        fmt: Image format extension (default: "png").
    """
    image_bytes = base64.b64decode(thumbnail_base64)
    filename = f"doc_{document.pk}_thumb.{fmt}"
    document.icon.save(filename, ContentFile(image_bytes), save=True)


def staging_path_for_job(job_id: int, filename: str = "") -> str:
    """
    Generate a staging storage path for a bulk ingestion job.

    Args:
        job_id: The BulkIngestionJob ID.
        filename: Optional filename within the job staging directory.

    Returns:
        Storage path string.
    """
    base = f"{BULK_INGESTION_STAGING_PREFIX}/job_{job_id}"
    if filename:
        return f"{base}/{filename}"
    return base


def write_to_staging(path: str, content: bytes) -> str:
    """
    Write content to staging storage.

    Args:
        path: Storage path to write to.
        content: Bytes to write.

    Returns:
        The actual path where the file was saved.
    """
    return default_storage.save(path, BytesIO(content))
