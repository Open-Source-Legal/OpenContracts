"""Local document loading: plain text, markdown, and (optionally) PDF.

Everything is processed locally — the only network call in the whole
pipeline is the LLM request made by the engine. PDFs require the ``pdf``
extra (``pip install oc-extract[pdf]``).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".text"}


@dataclass
class LoadedDocument:
    """A parsed document ready for ingestion."""

    title: str
    text: str
    #: Char offset where each page starts (PDF only); enables page-numbered
    #: citations. ``None`` for single-stream text documents.
    page_offsets: list[int] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def load_pdf_bytes(data: bytes, title: str) -> LoadedDocument:
    """Extract text (with page offsets) from PDF bytes via pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "PDF support requires the 'pdf' extra: pip install oc-extract[pdf]"
        ) from exc

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    page_offsets: list[int] = []
    cursor = 0
    for page in reader.pages:
        page_offsets.append(cursor)
        page_text = page.extract_text() or ""
        parts.append(page_text)
        cursor += len(page_text) + 2  # account for the "\n\n" join below
    return LoadedDocument(
        title=title,
        text="\n\n".join(parts),
        page_offsets=page_offsets,
        meta={"pages": len(reader.pages), "format": "pdf"},
    )


def load_bytes(
    data: bytes, filename: str, content_type: str | None = None
) -> LoadedDocument:
    """Load a document from raw bytes, dispatching on type/extension."""
    suffix = Path(filename).suffix.lower()
    title = Path(filename).stem or filename
    if suffix == ".pdf" or (content_type or "").lower() == "application/pdf":
        return load_pdf_bytes(data, title)
    if (
        suffix in TEXT_SUFFIXES
        or (content_type or "").startswith("text/")
        or not suffix
    ):
        return LoadedDocument(
            title=title,
            text=data.decode("utf-8", errors="replace"),
            meta={"format": suffix.lstrip(".") or "text"},
        )
    raise ValueError(
        f"unsupported document type {suffix or content_type!r}; "
        "supported: PDF and plain-text formats"
    )


def load_path(path: str | Path) -> LoadedDocument:
    """Load a document from a filesystem path."""
    p = Path(path)
    return load_bytes(p.read_bytes(), p.name)
