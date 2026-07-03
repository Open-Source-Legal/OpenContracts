"""oc-extract: standalone structured data extraction with citations.

A lightweight, SQLite-backed port of the OpenContracts extract pipeline:
define a field set (prompt + output schema per field), point it at locally
processed documents, and get typed answers with character-offset citations.

Library quickstart::

    from oc_extract import ExtractionEngine, FieldSet, FieldSpec, Store
    from oc_extract.documents import load_path
    from oc_extract.runner import run_extract_sync

    store = Store("contracts.db")
    doc = load_path("msa.pdf")
    doc_id = store.add_document(doc.title, doc.text, page_offsets=doc.page_offsets)
    fs_id = store.create_fieldset(FieldSet(
        name="Key terms",
        fields=[
            FieldSpec(name="parties", query="Who are the contracting parties?",
                      output_type="str", extract_is_list=True),
            FieldSpec(name="effective_date", query="What is the effective date?"),
        ],
    ))
    extract_id = store.create_extract("MSA review", fs_id, [doc_id])
    result = run_extract_sync(store, extract_id)

Or run the microservice: ``oc-extract serve --db contracts.db``.
"""

from .engine import CellOutcome, ExtractionEngine
from .schema import FieldSet, FieldSpec, parse_output_type, resolve_target_type
from .store import Store

__all__ = [
    "CellOutcome",
    "ExtractionEngine",
    "FieldSet",
    "FieldSpec",
    "Store",
    "parse_output_type",
    "resolve_target_type",
]

__version__ = "0.1.0"
