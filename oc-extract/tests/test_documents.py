from __future__ import annotations

import io

import pytest
from oc_extract.documents import load_bytes


def test_load_plain_text():
    doc = load_bytes(b"hello world", "note.txt", "text/plain")
    assert doc.text == "hello world"
    assert doc.title == "note"
    assert doc.page_offsets is None


def test_extensionless_upload_is_treated_as_text():
    # Deliberate permissive-by-default behavior (documented in load_bytes).
    doc = load_bytes(b"raw piped content", "README", None)
    assert doc.text == "raw piped content"


def test_unsupported_type_raises():
    with pytest.raises(ValueError):
        load_bytes(b"\x89PNG", "img.png", "image/png")


def test_load_pdf_bytes_pages_and_offsets():
    pypdf = pytest.importorskip("pypdf")

    buffer = io.BytesIO()
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)

    doc = load_bytes(buffer.getvalue(), "contract.pdf", "application/pdf")
    assert doc.meta == {"pages": 2, "format": "pdf"}
    assert doc.page_offsets is not None
    assert len(doc.page_offsets) == 2
    assert doc.page_offsets[0] == 0
    assert doc.title == "contract"
