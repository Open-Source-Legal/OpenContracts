"""Tests for the LiteParse service's response projection (pure Python, runs in CI).

The fakes mirror liteparse 2.21.3's result dataclasses (ParseResult, ParsedPage,
TextItem, WordBox, LayoutBlock, LayoutCell, AnnotationRect) attribute-for-
attribute, so the projection never needs the real package to be tested.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).parents[1]))

from liteparse_service.projection import (  # noqa: E402
    SCHEMA_VERSION,
    is_truncated,
    project_result,
)


def _rect(x, y, w, h):
    return NS(x=x, y=y, width=w, height=h)


def _word(text, x, y, w, h):
    return NS(text=text, x=x, y=y, width=w, height=h)


def _item(text, x, y, w, h, *, words, confidence=None):
    return NS(
        text=text,
        x=x,
        y=y,
        width=w,
        height=h,
        confidence=confidence,
        words=words,
        font_name="OCR",
    )


def _block(
    kind, *, level=None, text=None, bbox=None, indices=(), header=None, rows=None
):
    return NS(
        kind=kind,
        level=level,
        text=text,
        bbox=bbox,
        text_item_indices=list(indices),
        header=header,
        rows=rows,
        bold=False,
    )


def _page(num, *, items=(), blocks=None, width=612.0, height=792.0):
    return NS(
        page_num=num,
        width=width,
        height=height,
        text_items=list(items),
        blocks=blocks,
        text="",
        markdown="",
    )


def _result(pages, *, total_pages=None, page_errors=()):
    return NS(
        pages=list(pages),
        total_pages=len(pages) if total_pages is None else total_pages,
        page_errors=list(page_errors),
        text="",
    )


def test_project_result_shapes_words_and_blocks():
    item = _item(
        "Hello world",
        10.0,
        20.0,
        80.0,
        12.0,
        confidence=0.93,
        words=[
            _word("Hello", 10.0, 20.0, 35.0, 12.0),
            _word("world", 50.0, 20.0, 40.0, 12.0),
        ],
    )
    heading = _block(
        "heading",
        level=2,
        text="Hello world",
        bbox=_rect(10.0, 20.0, 80.0, 12.0),
        indices=[0],
    )
    result = _result([_page(1, items=[item], blocks=[heading])])

    out = project_result(result, liteparse_version="2.21.3", model_version="1.0.0")

    assert out == {
        "schema_version": SCHEMA_VERSION,
        "liteparse_version": "2.21.3",
        "model_version": "1.0.0",
        "total_pages": 1,
        "page_errors": [],
        "pages": [
            {
                "page_num": 1,
                "width": 612.0,
                "height": 792.0,
                "text_items": [
                    {
                        "text": "Hello world",
                        "x": 10.0,
                        "y": 20.0,
                        "width": 80.0,
                        "height": 12.0,
                        "confidence": 0.93,
                        "words": [
                            {
                                "text": "Hello",
                                "x": 10.0,
                                "y": 20.0,
                                "width": 35.0,
                                "height": 12.0,
                            },
                            {
                                "text": "world",
                                "x": 50.0,
                                "y": 20.0,
                                "width": 40.0,
                                "height": 12.0,
                            },
                        ],
                    }
                ],
                "blocks": [
                    {
                        "kind": "heading",
                        "level": 2,
                        "text": "Hello world",
                        "bbox": {"x": 10.0, "y": 20.0, "width": 80.0, "height": 12.0},
                        "text_item_indices": [0],
                        "header": None,
                        "rows": None,
                    }
                ],
            }
        ],
    }
    assert SCHEMA_VERSION == 1


def test_project_result_none_blocks_and_none_bbox():
    cell = NS(text="30a", bbox=_rect(66.0, 65.8, 17.0, 13.0), text_item_indices=[])
    empty_cell = NS(text="", bbox=None, text_item_indices=[])
    table = _block(
        "table", text="", bbox=None, rows=[[cell, empty_cell]], header=[cell]
    )
    pages = [_page(1, blocks=None), _page(2, blocks=[table])]

    out = project_result(_result(pages), liteparse_version="v", model_version="m")

    assert out["pages"][0]["blocks"] == []
    block = out["pages"][1]["blocks"][0]
    assert block["bbox"] is None
    assert block["rows"] == [
        [
            {
                "text": "30a",
                "bbox": {"x": 66.0, "y": 65.8, "width": 17.0, "height": 13.0},
                "text_item_indices": [],
            },
            {"text": "", "bbox": None, "text_item_indices": []},
        ]
    ]
    assert block["header"] == [
        {
            "text": "30a",
            "bbox": {"x": 66.0, "y": 65.8, "width": 17.0, "height": 13.0},
            "text_item_indices": [],
        }
    ]


def test_project_result_page_errors():
    result = _result([_page(1)], page_errors=[NS(page_num=3, message="bad xref")])

    out = project_result(result, liteparse_version="v", model_version="m")

    assert out["page_errors"] == [{"page_num": 3, "message": "bad xref"}]


def test_is_truncated_true_when_total_exceeds_pages():
    assert is_truncated(_result([_page(1), _page(2)], total_pages=9)) is True


def test_is_truncated_false_when_equal():
    assert is_truncated(_result([_page(1), _page(2)])) is False


def test_is_truncated_false_when_errored_pages_account_for_gap():
    result = _result(
        [_page(1), _page(3)], total_pages=3, page_errors=[NS(page_num=2, message="x")]
    )
    assert is_truncated(result) is False


def test_is_truncated_true_when_gap_not_explained_by_errors():
    result = _result(
        [_page(1), _page(2)], total_pages=4, page_errors=[NS(page_num=2, message="x")]
    )
    assert is_truncated(result) is True
