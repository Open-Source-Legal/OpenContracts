"""Tests for converting LiteParse service responses into OpenContracts exports.

``needs_ocr.json`` and ``sample.json`` are real responses recorded from the
``compose/liteparse`` service (OCRia-nano 1.0.0, LiteParse 2.21.3) for
``needs_ocr.pdf`` (a scanned page) and ``sample.pdf`` (text layer + tables).
The synthetic cases cover shapes the fixtures don't contain.
"""

import copy
import json
from pathlib import Path

from django.test import SimpleTestCase

from opencontractserver.annotations.models import TOKEN_LABEL
from opencontractserver.constants.document_processing import (
    LITEPARSE_FALLBACK_LABEL,
    LITEPARSE_RESPONSE_SCHEMA_VERSION,
)
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.parsers.liteparse_conversion import (
    liteparse_response_to_export,
)

FIXTURES = Path(__file__).parent / "fixtures" / "liteparse"


def _fixture(name: str) -> dict:
    with open(FIXTURES / f"{name}.json") as f:
        return json.load(f)


def _word(text, x, y, w=10.0, h=10.0):
    return {"text": text, "x": x, "y": y, "width": w, "height": h}


def _item(words, *, text=None, x=None, y=None, w=50.0, h=10.0):
    """A text item; position defaults to its first word's (pass x/y if no words)."""
    if x is None or y is None:
        x, y = words[0]["x"], words[0]["y"]
    return {
        "text": text if text is not None else " ".join(wd["text"] for wd in words),
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "confidence": None,
        "words": words,
    }


def _block(kind, indices, *, level=None, bbox=None, text=None):
    return {
        "kind": kind,
        "level": level,
        "text": text,
        "bbox": bbox,
        "text_item_indices": list(indices),
        "header": None,
        "rows": None,
    }


def _payload(pages, *, page_errors=()):
    return {
        "schema_version": LITEPARSE_RESPONSE_SCHEMA_VERSION,
        "liteparse_version": "2.21.3",
        "model_version": "1.0.0",
        "total_pages": len(pages),
        "page_errors": list(page_errors),
        "pages": [
            {
                "page_num": i + 1,
                "width": 612.0,
                "height": 792.0,
                "text_items": items,
                "blocks": blocks,
            }
            for i, (items, blocks) in enumerate(pages)
        ],
    }


def _convert(payload):
    return liteparse_response_to_export(payload, title="Doc", doc_id=1)


def _by_text(export, raw_text):
    return [a for a in export["labelled_text"] if a["rawText"] == raw_text]


class TestFixtureConversion(SimpleTestCase):
    def test_ocr_fixture_tokens_and_dims(self):
        payload = _fixture("needs_ocr")
        export = _convert(payload)

        self.assertEqual(export["page_count"], 1)
        page = export["pawls_file_content"][0]
        self.assertAlmostEqual(page["page"]["width"], 595.44, places=2)
        self.assertAlmostEqual(page["page"]["height"], 842.16, places=2)
        self.assertEqual(page["page"]["index"], 0)
        self.assertEqual(
            [t["text"] for t in page["tokens"][:3]], ["KVK", "14", "Wijziging"]
        )
        expected = sum(
            1
            for item in payload["pages"][0]["text_items"]
            for word in item["words"]
            if word["text"].strip()
        )
        self.assertEqual(len(page["tokens"]), expected)

    def test_ocr_fixture_heading_hierarchy(self):
        export = _convert(_fixture("needs_ocr"))

        (title,) = _by_text(export, "KVK 14 Wijziging")
        self.assertEqual(title["annotationLabel"], "Section Header")
        self.assertIsNone(title["parent_id"])
        (sub,) = _by_text(export, "Ondernemings- en vestigingsgegevens")
        self.assertEqual(sub["parent_id"], title["id"])
        footers = [
            a for a in export["labelled_text"] if a["annotationLabel"] == "Page Footer"
        ]
        self.assertTrue(footers)
        self.assertTrue(all(a["parent_id"] is None for a in footers))

    def test_annotation_shape(self):
        export = _convert(_fixture("needs_ocr"))
        (title,) = _by_text(export, "KVK 14 Wijziging")

        self.assertEqual(title["annotation_type"], TOKEN_LABEL)
        self.assertTrue(title["structural"])
        self.assertEqual(title["content_modalities"], ["TEXT"])
        self.assertEqual(title["page"], 0)
        page_json = title["annotation_json"]["0"]
        self.assertEqual(page_json["rawText"], "KVK 14 Wijziging")
        self.assertEqual(
            page_json["tokensJsons"],
            [{"pageIndex": 0, "tokenIndex": i} for i in range(3)],
        )
        bounds = page_json["bounds"]
        self.assertLess(bounds["left"], bounds["right"])
        self.assertLess(bounds["top"], bounds["bottom"])

    def test_all_token_refs_in_range(self):
        for name in ("needs_ocr", "sample"):
            export = _convert(_fixture(name))
            pages = export["pawls_file_content"]
            for annotation in export["labelled_text"]:
                for page_key, page_json in annotation["annotation_json"].items():
                    self.assertTrue(page_json["tokensJsons"], annotation["id"])
                    for ref in page_json["tokensJsons"]:
                        self.assertEqual(ref["pageIndex"], int(page_key))
                        self.assertLess(
                            ref["tokenIndex"], len(pages[ref["pageIndex"]]["tokens"])
                        )

    def test_sample_fixture_tables_have_tokens(self):
        payload = _fixture("sample")
        self.assertTrue(
            any(
                b["kind"] == "table" and not b["text_item_indices"]
                for p in payload["pages"]
                for b in p["blocks"]
            )
        )
        export = _convert(payload)
        tables = [a for a in export["labelled_text"] if a["annotationLabel"] == "Table"]
        self.assertTrue(tables)
        self.assertTrue(
            all(a["annotation_json"][str(a["page"])]["tokensJsons"] for a in tables)
        )

    def test_sample_fixture_hierarchy_crosses_pages(self):
        export = _convert(_fixture("sample"))
        by_id = {a["id"]: a for a in export["labelled_text"]}
        self.assertTrue(
            any(
                a["page"] >= 1
                and a["parent_id"] is not None
                and by_id[a["parent_id"]]["page"] < a["page"]
                for a in export["labelled_text"]
            )
        )

    def test_sample_fixture_page_count_and_content(self):
        export = _convert(_fixture("sample"))
        self.assertEqual(export["page_count"], 9)
        self.assertEqual(len(export["pawls_file_content"]), 9)
        self.assertEqual(export["content"].count("\n\n"), 8)
        self.assertEqual(export["file_type"], "application/pdf")
        self.assertEqual(export["title"], "Doc")


class TestSyntheticConversion(SimpleTestCase):
    def test_unknown_kind_uses_fallback_and_warns(self):
        payload = _payload(
            [([_item([_word("Aside", 10, 10)])], [_block("sidebar", [0])])]
        )
        with self.assertLogs(
            "opencontractserver.pipeline.parsers.liteparse_conversion", "WARNING"
        ) as logs:
            export = _convert(payload)
        self.assertEqual(
            export["labelled_text"][0]["annotationLabel"], LITEPARSE_FALLBACK_LABEL
        )
        self.assertIn("sidebar", "\n".join(logs.output))

    def test_rule_blocks_skipped(self):
        payload = _payload(
            [
                (
                    [_item([_word("Body", 10, 10)])],
                    [_block("rule", [0]), _block("paragraph", [0])],
                )
            ]
        )
        export = _convert(payload)
        self.assertEqual(
            [a["annotationLabel"] for a in export["labelled_text"]], ["Paragraph"]
        )

    def test_item_without_words_becomes_single_token(self):
        item = _item([], text="Signed", x=100.0, y=200.0, w=40.0, h=12.0)
        export = _convert(_payload([([item], [_block("paragraph", [0])])]))
        tokens = export["pawls_file_content"][0]["tokens"]
        self.assertEqual(
            tokens,
            [{"x": 100.0, "y": 200.0, "width": 40.0, "height": 12.0, "text": "Signed"}],
        )
        self.assertEqual(export["labelled_text"][0]["rawText"], "Signed")

    def test_blank_words_skipped(self):
        item = _item([_word("A", 10, 10), _word("  ", 25, 10), _word("B", 40, 10)])
        export = _convert(_payload([([item], [_block("paragraph", [0])])]))
        self.assertEqual(
            [t["text"] for t in export["pawls_file_content"][0]["tokens"]], ["A", "B"]
        )

    def test_blank_page_keeps_page_alignment(self):
        page = ([_item([_word("x", 10, 10)])], [_block("paragraph", [0])])
        export = _convert(_payload([page, ([], []), page]))
        pawls = export["pawls_file_content"]
        self.assertEqual([p["page"]["index"] for p in pawls], [0, 1, 2])
        self.assertEqual(pawls[1]["tokens"], [])
        self.assertEqual(export["page_count"], 3)
        self.assertEqual(sorted(a["page"] for a in export["labelled_text"]), [0, 2])

    def test_heading_level_skip_nests(self):
        items = [_item([_word(t, 10, 10 + 20 * i)]) for i, t in enumerate("ABCD")]
        blocks = [
            _block("heading", [0], level=1),
            _block("heading", [1], level=3),
            _block("heading", [2], level=2),
            _block("paragraph", [3]),
        ]
        export = _convert(_payload([(items, blocks)]))
        a, b, c, d = export["labelled_text"]
        self.assertIsNone(a["parent_id"])
        self.assertEqual(b["parent_id"], a["id"])
        self.assertEqual(c["parent_id"], a["id"])
        self.assertEqual(d["parent_id"], c["id"])

    def test_heading_without_level_is_top_level(self):
        items = [_item([_word(t, 10, 10 + 20 * i)]) for i, t in enumerate("AB")]
        blocks = [_block("heading", [0], level=2), _block("heading", [1], level=None)]
        a, b = _convert(_payload([(items, blocks)]))["labelled_text"]
        self.assertIsNone(b["parent_id"])

    def test_page_chrome_never_parent(self):
        items = [_item([_word(t, 10, 10 + 20 * i)]) for i, t in enumerate("HFP")]
        blocks = [
            _block("heading", [0], level=1),
            _block("page_footer", [1]),
            _block("paragraph", [2]),
        ]
        heading, footer, para = _convert(_payload([(items, blocks)]))["labelled_text"]
        self.assertIsNone(footer["parent_id"])
        self.assertEqual(para["parent_id"], heading["id"])

    def test_block_without_indices_uses_word_boxes(self):
        item = _item([_word("left", 10, 10), _word("right", 300, 10)])
        bbox = {"x": 290.0, "y": 5.0, "width": 60.0, "height": 20.0}
        export = _convert(_payload([([item], [_block("paragraph", [], bbox=bbox)])]))
        self.assertEqual(export["labelled_text"][0]["rawText"], "right")

    def test_table_without_bbox_uses_cell_boxes(self):
        item = _item([_word("cell", 100, 100)])
        table = _block("table", [], bbox=None)
        table["rows"] = [
            [
                {
                    "text": "cell",
                    "bbox": {"x": 95.0, "y": 95.0, "width": 30.0, "height": 20.0},
                    "text_item_indices": [],
                }
            ]
        ]
        export = _convert(_payload([([item], [table])]))
        self.assertEqual(export["labelled_text"][0]["rawText"], "cell")

    def test_block_without_tokens_skipped(self):
        bbox = {"x": 500.0, "y": 500.0, "width": 10.0, "height": 10.0}
        payload = _payload(
            [([_item([_word("x", 10, 10)])], [_block("figure", [], bbox=bbox)])]
        )
        self.assertEqual(_convert(payload)["labelled_text"], [])

    def test_out_of_range_index_warns(self):
        payload = _payload(
            [([_item([_word("x", 10, 10)])], [_block("paragraph", [0, 7])])]
        )
        with self.assertLogs(
            "opencontractserver.pipeline.parsers.liteparse_conversion", "WARNING"
        ):
            export = _convert(payload)
        self.assertEqual(export["labelled_text"][0]["rawText"], "x")

    def test_schema_version_mismatch_is_permanent(self):
        payload = copy.deepcopy(_fixture("needs_ocr"))
        payload["schema_version"] = LITEPARSE_RESPONSE_SCHEMA_VERSION + 1
        with self.assertRaises(DocumentParsingError) as ctx:
            _convert(payload)
        self.assertFalse(ctx.exception.is_transient)
        self.assertIn("rebuild", str(ctx.exception))

    def test_non_dict_payload_is_permanent(self):
        with self.assertRaises(DocumentParsingError) as ctx:
            _convert(["not", "a", "dict"])
        self.assertFalse(ctx.exception.is_transient)

    def test_all_pages_failed_is_permanent(self):
        payload = _payload([], page_errors=[{"page_num": 1, "message": "boom"}])
        with self.assertRaises(DocumentParsingError) as ctx:
            _convert(payload)
        self.assertFalse(ctx.exception.is_transient)

    def test_partial_page_errors_warn_and_convert(self):
        payload = _payload(
            [([_item([_word("ok", 10, 10)])], [_block("paragraph", [0])])],
            page_errors=[{"page_num": 2, "message": "bad page"}],
        )
        with self.assertLogs(
            "opencontractserver.pipeline.parsers.liteparse_conversion", "WARNING"
        ) as logs:
            export = _convert(payload)
        self.assertIn("bad page", "\n".join(logs.output))
        self.assertEqual(len(export["labelled_text"]), 1)
