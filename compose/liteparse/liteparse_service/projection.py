"""Project a LiteParse ``ParseResult`` onto the service's fixed JSON contract.

The contract (``SCHEMA_VERSION``) is what OpenContracts'
``opencontractserver/pipeline/parsers/liteparse_conversion.py`` consumes; bump
the version on any shape change so a stale client fails loudly instead of
misreading fields. Coordinates are PDF points, top-left origin, exactly as
LiteParse reports them.

Duck-typed on purpose: only attributes are read, so this module never imports
``liteparse`` and its tests run with plain fakes.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1


def _rect(rect: Any) -> dict | None:
    if rect is None:
        return None
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def _cell(cell: Any) -> dict:
    return {
        "text": cell.text,
        "bbox": _rect(cell.bbox),
        "text_item_indices": list(cell.text_item_indices),
    }


def _cells(cells: Any) -> list | None:
    return None if cells is None else [_cell(c) for c in cells]


def _block(block: Any) -> dict:
    return {
        "kind": block.kind,
        "level": block.level,
        "text": block.text,
        "bbox": _rect(block.bbox),
        "text_item_indices": list(block.text_item_indices),
        "header": _cells(block.header),
        "rows": None if block.rows is None else [_cells(row) for row in block.rows],
    }


def _text_item(item: Any) -> dict:
    return {
        "text": item.text,
        "x": item.x,
        "y": item.y,
        "width": item.width,
        "height": item.height,
        "confidence": item.confidence,
        "words": [
            {"text": w.text, "x": w.x, "y": w.y, "width": w.width, "height": w.height}
            for w in item.words
        ],
    }


def _page(page: Any) -> dict:
    return {
        "page_num": page.page_num,
        "width": page.width,
        "height": page.height,
        "text_items": [_text_item(i) for i in page.text_items],
        "blocks": [_block(b) for b in (page.blocks or [])],
    }


def project_result(result: Any, *, liteparse_version: str, model_version: str) -> dict:
    """Return the JSON-serializable wire payload for one parsed document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "liteparse_version": liteparse_version,
        "model_version": model_version,
        "total_pages": result.total_pages,
        "page_errors": [
            {"page_num": e.page_num, "message": e.message} for e in result.page_errors
        ],
        "pages": [_page(p) for p in result.pages],
    }


def is_truncated(result: Any) -> bool:
    """True when LiteParse stopped at ``max_pages`` (it truncates silently).

    Pages skipped with a page error (``continue_on_page_error``) are accounted
    for, so only pages that are neither parsed nor reported count as missing.
    """
    covered = {p.page_num for p in result.pages} | {
        e.page_num for e in result.page_errors
    }
    return result.total_pages > len(covered)
