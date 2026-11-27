"""Convert a LiteParse service response into an ``OpenContractDocExport``.

The response is the fixed projection served by ``compose/liteparse``
(``liteparse_service/projection.py``): per page, its size in PDF points, text
items with word boxes, and LiteParse's layout blocks (headings with levels,
paragraphs, tables, page headers/footers, ...) in reading order.

- Every word becomes a PAWLs token; a text item without word boxes becomes a
  single token so no text is lost. Pages are placed by ``page_num``: pages
  without text, and pages LiteParse skipped with a page error, keep an empty
  PAWLs page so page indices stay aligned with the PDF.
- Each block becomes one structural annotation. Its tokens come from the text
  items it lists. Tables list none and take the words whose centre lies inside
  their box. Other blocks that list none are fragments LiteParse split off a
  longer line; they take only words no listing block on the page owns, and are
  dropped when none remain (otherwise each would duplicate its neighbour).
- Heading levels build the ``parent_id`` hierarchy, which carries across pages.
"""

import logging
from collections.abc import Iterable
from typing import Any, Optional, Union, cast

from opencontractserver.annotations.models import TOKEN_LABEL
from opencontractserver.constants.document_processing import (
    LITEPARSE_BLOCK_LABELS,
    LITEPARSE_FALLBACK_LABEL,
    LITEPARSE_HEADING_KIND,
    LITEPARSE_PAGE_CHROME_KINDS,
    LITEPARSE_RESPONSE_SCHEMA_VERSION,
    LITEPARSE_SKIPPED_BLOCK_KINDS,
    LITEPARSE_TABLE_BLOCK_KINDS,
)
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.types.dicts import (
    BoundingBoxPythonType,
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsSinglePageAnnotationType,
    PawlsPagePythonType,
    PawlsTokenPythonType,
    TokenIdPythonType,
)

logger = logging.getLogger(__name__)

# A heading with no level is treated as top-level.
_DEFAULT_HEADING_LEVEL = 1


def _token(text: str, box: dict) -> PawlsTokenPythonType:
    return cast(
        PawlsTokenPythonType,
        {
            "x": box["x"],
            "y": box["y"],
            "width": box["width"],
            "height": box["height"],
            "text": text,
        },
    )


def _page_tokens(
    page: dict,
) -> tuple[list[PawlsTokenPythonType], list[list[int]]]:
    """Return the page's tokens and, per text item, the indices of its tokens."""
    tokens: list[PawlsTokenPythonType] = []
    item_tokens: list[list[int]] = []
    for item in page["text_items"]:
        indices: list[int] = []
        words = item["words"] or [{**item, "text": item["text"]}]
        for word in words:
            if not word["text"].strip():
                continue
            indices.append(len(tokens))
            tokens.append(_token(word["text"], word))
        item_tokens.append(indices)
    return tokens, item_tokens


def _contains_centre(box: dict, token: PawlsTokenPythonType) -> bool:
    cx = token["x"] + token["width"] / 2
    cy = token["y"] + token["height"] / 2
    return (
        box["x"] <= cx <= box["x"] + box["width"]
        and box["y"] <= cy <= box["y"] + box["height"]
    )


def _block_boxes(block: dict) -> list[dict]:
    if block["bbox"] is not None:
        return [block["bbox"]]
    cells = list(block["header"] or []) + [
        cell for row in (block["rows"] or []) for cell in row
    ]
    return [cell["bbox"] for cell in cells if cell["bbox"] is not None]


def _words_in_boxes(block: dict, tokens: list[PawlsTokenPythonType]) -> list[int]:
    boxes = _block_boxes(block)
    return [
        i
        for i, token in enumerate(tokens)
        if any(_contains_centre(box, token) for box in boxes)
    ]


def _listed_tokens(
    block: dict, item_tokens: list[list[int]], page_num: int
) -> list[int]:
    result: list[int] = []
    for item_index in block["text_item_indices"]:
        if 0 <= item_index < len(item_tokens):
            result.extend(item_tokens[item_index])
        else:
            logger.warning(
                "LiteParse block on page %d references missing text item %d",
                page_num,
                item_index,
            )
    return result


def _page_block_tokens(
    blocks: list[dict],
    tokens: list[PawlsTokenPythonType],
    item_tokens: list[list[int]],
    page_num: int,
) -> list[list[int]]:
    """Token indices for each block on a page, in block order."""
    listed = [_listed_tokens(b, item_tokens, page_num) for b in blocks]
    claimed = {i for indices in listed for i in indices}
    result: list[list[int]] = []
    for block, own in zip(blocks, listed):
        if block["kind"] in LITEPARSE_TABLE_BLOCK_KINDS:
            result.append(_words_in_boxes(block, tokens))
        elif block["text_item_indices"]:
            result.append(own)
        else:
            orphans = [i for i in _words_in_boxes(block, tokens) if i not in claimed]
            claimed.update(orphans)
            result.append(orphans)
    return result


def _bounds(
    block: dict, tokens: list[PawlsTokenPythonType], token_indices: Iterable[int]
) -> BoundingBoxPythonType:
    if block["bbox"] is not None:
        box = block["bbox"]
        return {
            "left": box["x"],
            "top": box["y"],
            "right": box["x"] + box["width"],
            "bottom": box["y"] + box["height"],
        }
    chosen = [tokens[i] for i in token_indices]
    return {
        "left": min(t["x"] for t in chosen),
        "top": min(t["y"] for t in chosen),
        "right": max(t["x"] + t["width"] for t in chosen),
        "bottom": max(t["y"] + t["height"] for t in chosen),
    }


def _label(kind: str, page_num: int) -> str:
    label = LITEPARSE_BLOCK_LABELS.get(kind)
    if label is None:
        logger.warning(
            "Unknown LiteParse block kind %r on page %d; labelling it %r",
            kind,
            page_num,
            LITEPARSE_FALLBACK_LABEL,
        )
        return LITEPARSE_FALLBACK_LABEL
    return label


def _build_annotation(
    *,
    annotation_id: str,
    label: str,
    page_index: int,
    bounds: BoundingBoxPythonType,
    token_indices: list[int],
    tokens: list[PawlsTokenPythonType],
    parent_id: Optional[str],
) -> OpenContractsAnnotationPythonType:
    raw_text = " ".join(tokens[i]["text"] for i in token_indices)
    refs: list[TokenIdPythonType] = [
        {"pageIndex": page_index, "tokenIndex": i} for i in token_indices
    ]
    page_annotation: OpenContractsSinglePageAnnotationType = {
        "bounds": bounds,
        "tokensJsons": refs,
        "rawText": raw_text,
    }
    annotation_json: dict[Union[int, str], OpenContractsSinglePageAnnotationType] = {
        str(page_index): page_annotation
    }
    return {
        "id": annotation_id,
        "annotationLabel": label,
        "rawText": raw_text,
        "page": page_index,
        "annotation_json": annotation_json,
        "parent_id": parent_id,
        "annotation_type": TOKEN_LABEL,
        "structural": True,
        "content_modalities": ["TEXT"],
    }


def _validate(payload: Any, doc_id: int) -> dict:
    if not isinstance(payload, dict):
        raise DocumentParsingError(
            f"LiteParse returned a non-object response for document {doc_id}",
            is_transient=False,
        )
    version = payload.get("schema_version")
    if version != LITEPARSE_RESPONSE_SCHEMA_VERSION:
        raise DocumentParsingError(
            f"LiteParse service response schema {version!r} does not match the "
            f"expected {LITEPARSE_RESPONSE_SCHEMA_VERSION} for document {doc_id}; "
            "rebuild the liteparse image from this OpenContracts version",
            is_transient=False,
        )
    page_errors = payload.get("page_errors") or []
    for error in page_errors:
        logger.warning(
            "LiteParse could not parse page %s of document %s: %s",
            error.get("page_num"),
            doc_id,
            error.get("message"),
        )
    if not payload.get("pages") and page_errors:
        raise DocumentParsingError(
            f"LiteParse could not parse any page of document {doc_id}",
            is_transient=False,
        )
    return payload


def liteparse_response_to_export(
    payload: Any, *, title: str, doc_id: int
) -> OpenContractDocExport:
    """Convert one LiteParse service response into an ``OpenContractDocExport``."""
    payload = _validate(payload, doc_id)

    pages = payload["pages"]
    page_count = max([payload.get("total_pages") or 0] + [p["page_num"] for p in pages])
    by_index = {p["page_num"] - 1: p for p in pages}
    pawls_pages: list[PawlsPagePythonType] = []
    annotations: list[OpenContractsAnnotationPythonType] = []
    page_texts: list[str] = []
    # (level, annotation id) of the currently open headings, across pages.
    heading_stack: list[tuple[int, str]] = []
    # Size for pages LiteParse skipped (page errors): the nearest page before
    # it, else the first parsed page.
    size = (pages[0]["width"], pages[0]["height"]) if pages else (0.0, 0.0)

    for page_index in range(page_count):
        page = by_index.get(page_index)
        if page is None:
            pawls_pages.append(
                {
                    "page": {"width": size[0], "height": size[1], "index": page_index},
                    "tokens": [],
                }
            )
            page_texts.append("")
            continue

        page_num = page["page_num"]
        size = (page["width"], page["height"])
        tokens, item_tokens = _page_tokens(page)
        pawls_pages.append(
            {
                "page": {"width": size[0], "height": size[1], "index": page_index},
                "tokens": tokens,
            }
        )
        page_texts.append(" ".join(t["text"] for t in tokens))

        block_tokens = _page_block_tokens(page["blocks"], tokens, item_tokens, page_num)
        for block_index, (block, token_indices) in enumerate(
            zip(page["blocks"], block_tokens)
        ):
            kind = block["kind"]
            if kind in LITEPARSE_SKIPPED_BLOCK_KINDS or not token_indices:
                continue

            annotation_id = f"lp-{page_index}-{block_index}"
            if kind in LITEPARSE_PAGE_CHROME_KINDS:
                parent_id = None
            elif kind == LITEPARSE_HEADING_KIND:
                level = block["level"] or _DEFAULT_HEADING_LEVEL
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                parent_id = heading_stack[-1][1] if heading_stack else None
                heading_stack.append((level, annotation_id))
            else:
                parent_id = heading_stack[-1][1] if heading_stack else None

            annotations.append(
                _build_annotation(
                    annotation_id=annotation_id,
                    label=_label(kind, page_num),
                    page_index=page_index,
                    bounds=_bounds(block, tokens, token_indices),
                    token_indices=token_indices,
                    tokens=tokens,
                    parent_id=parent_id,
                )
            )

    logger.info(
        "Converted LiteParse response for document %s: %d pages, %d annotations",
        doc_id,
        len(pawls_pages),
        len(annotations),
    )
    return {
        "title": title,
        "content": "\n\n".join(page_texts),
        "description": None,
        "pawls_file_content": pawls_pages,
        "page_count": len(pawls_pages),
        "doc_labels": [],
        "labelled_text": annotations,
        "relationships": [],
        "file_type": "application/pdf",
    }
