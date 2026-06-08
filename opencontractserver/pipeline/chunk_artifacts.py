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

if TYPE_CHECKING:
    from opencontractserver.types.dicts import OpenContractDocExport

_SCRATCH_PREFIX = "chunk_scratch"


def _doc_dir(doc_id: int) -> str:
    return f"{_SCRATCH_PREFIX}/doc_{doc_id}"


def chunk_input_key(doc_id: int, chunk_index: int) -> str:
    """Storage key for a chunk's input PDF bytes."""
    return f"{_doc_dir(doc_id)}/in_{chunk_index}.pdf"


def chunk_output_key(doc_id: int, chunk_index: int) -> str:
    """Storage key for a chunk's output OpenContractDocExport JSON."""
    return f"{_doc_dir(doc_id)}/out_{chunk_index}.json"


def write_chunk_pdf(doc_id: int, chunk_index: int, pdf_bytes: bytes) -> str:
    """Write a chunk's input PDF to storage; return its key."""
    key = chunk_input_key(doc_id, chunk_index)
    if default_storage.exists(key):
        default_storage.delete(key)
    default_storage.save(key, ContentFile(pdf_bytes))
    return key


def read_chunk_pdf(key: str) -> bytes:
    """Read chunk input PDF bytes from storage."""
    with default_storage.open(key, "rb") as fh:
        return fh.read()


def write_chunk_result(doc_id: int, chunk_index: int, result: Mapping[str, Any]) -> str:
    """Write a chunk's OpenContractDocExport result JSON to storage; return key.

    Accepts any JSON-serializable mapping (``OpenContractDocExport`` is one);
    typed as ``Mapping`` so both the TypedDict and plain dicts satisfy mypy.
    """
    key = chunk_output_key(doc_id, chunk_index)
    if default_storage.exists(key):
        default_storage.delete(key)
    default_storage.save(key, ContentFile(json.dumps(result).encode("utf-8")))
    return key


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
        key = f"{doc_dir}/{name}"
        if default_storage.exists(key):
            default_storage.delete(key)
