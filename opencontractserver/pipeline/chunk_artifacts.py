"""Storage helpers for transient PDF-chunk parsing artifacts.

The chunked-parse Celery fan-out writes each chunk's input PDF and output
``OpenContractDocExport`` JSON to ``default_storage`` under a per-document
scratch namespace, so worker tasks exchange small storage keys instead of
large payloads over the broker. ``cleanup_chunk_artifacts`` removes the whole
namespace after reassembly.
"""

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from opencontractserver.constants.document_processing import CHUNK_SCRATCH_PREFIX

if TYPE_CHECKING:
    from opencontractserver.types.dicts import OpenContractDocExport


def _doc_dir(doc_id: int) -> str:
    return f"{CHUNK_SCRATCH_PREFIX}/doc_{doc_id}"


def _delete_quietly(key: str) -> None:
    """Delete a storage key, ignoring a missing target.

    Avoids the exists()-then-delete() TOCTOU race: ``Storage.delete`` is a
    no-op for an absent key on the backends we use, but we still guard against
    backends that raise so callers stay idempotent.
    """
    try:
        default_storage.delete(key)
    except (FileNotFoundError, OSError):
        pass


def chunk_input_key(doc_id: int, chunk_index: int) -> str:
    """Storage key for a chunk's input PDF bytes."""
    return f"{_doc_dir(doc_id)}/in_{chunk_index}.pdf"


def chunk_output_key(doc_id: int, chunk_index: int) -> str:
    """Storage key for a chunk's output OpenContractDocExport JSON."""
    return f"{_doc_dir(doc_id)}/out_{chunk_index}.json"


def write_chunk_pdf(doc_id: int, chunk_index: int, pdf_bytes: bytes) -> str:
    """Write a chunk's input PDF to storage; return the actual storage key.

    ``Storage.save`` may return a key that differs from the requested one
    (e.g. S3 unique-key mode, or a FileSystemStorage collision), so the saved
    key — not the pre-computed one — is what downstream readers must use.
    """
    key = chunk_input_key(doc_id, chunk_index)
    _delete_quietly(key)  # overwrite any stale artifact from a prior attempt
    return default_storage.save(key, ContentFile(pdf_bytes))


def read_chunk_pdf(key: str) -> bytes:
    """Read chunk input PDF bytes from storage."""
    with default_storage.open(key, "rb") as fh:
        return fh.read()


def write_chunk_result(doc_id: int, chunk_index: int, result: Mapping[str, Any]) -> str:
    """Write a chunk's OpenContractDocExport result JSON to storage; return key.

    Accepts any JSON-serializable mapping (``OpenContractDocExport`` is one);
    typed as ``Mapping`` so both the TypedDict and plain dicts satisfy mypy.

    Returns the *actual* storage key, which may differ from the requested key
    (see :func:`write_chunk_pdf`).
    """
    key = chunk_output_key(doc_id, chunk_index)
    _delete_quietly(key)  # overwrite any stale artifact from a prior attempt
    return default_storage.save(key, ContentFile(json.dumps(result).encode("utf-8")))


def read_chunk_result(key: str) -> "OpenContractDocExport":
    """Read a chunk's OpenContractDocExport result JSON from storage."""
    with default_storage.open(key, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def cleanup_chunk_artifacts(doc_id: int) -> None:
    """Delete all chunk scratch artifacts for a document. Idempotent."""
    doc_dir = _doc_dir(doc_id)
    try:
        dirs, files = default_storage.listdir(doc_dir)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return
    for name in files:
        _delete_quietly(f"{doc_dir}/{name}")
