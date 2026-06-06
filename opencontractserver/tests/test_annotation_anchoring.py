from django.test import SimpleTestCase

from opencontractserver.utils.annotation_anchoring import (
    anchor_annotations,
    legacy_annotation_to_dumb_anchor,
)


def _tok(x, text, y=10, w=None, h=12):
    return {
        "x": x,
        "y": y,
        "width": w if w is not None else len(text) * 8,
        "height": h,
        "text": text,
    }


def _page(tokens, index=0):
    return {"page": {"width": 600, "height": 800, "index": index}, "tokens": tokens}


class AnchorPdfTests(SimpleTestCase):
    def setUp(self):
        self.pawls = [
            _page([_tok(10, "CHAPTER"), _tok(90, "1"), _tok(10, "Body", y=40)])
        ]

    def test_bbox_anchors_to_tokens(self):
        anns = [
            {
                "id": "a1",
                "label": "OC_SECTION",
                "rawText": "CHAPTER 1",
                "page": 0,
                "bbox": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                "parent_id": None,
            }
        ]
        out, report = anchor_annotations(
            anns, is_pdf=True, pawls=self.pawls, content=""
        )
        self.assertEqual(len(out), 1)
        a = out[0]
        self.assertEqual(a["annotation_type"], "TOKEN_LABEL")
        self.assertEqual(a["annotationLabel"], "OC_SECTION")
        idxs = [t["tokenIndex"] for t in a["annotation_json"]["0"]["tokensJsons"]]
        self.assertEqual(idxs, [0, 1])
        self.assertFalse(any(r["dropped"] for r in report))

    def test_bbox_miss_falls_back_to_text(self):
        anns = [
            {
                "id": "a1",
                "label": "OC_SECTION",
                "rawText": "CHAPTER 1",
                "page": 0,
                "bbox": {"left": 500, "top": 500, "right": 510, "bottom": 510},
                "parent_id": None,
            }
        ]
        out, report = anchor_annotations(
            anns, is_pdf=True, pawls=self.pawls, content=""
        )
        idxs = [t["tokenIndex"] for t in out[0]["annotation_json"]["0"]["tokensJsons"]]
        self.assertEqual(idxs, [0, 1])

    def test_unanchorable_pdf_is_dropped_and_reported(self):
        anns = [
            {
                "id": "z",
                "label": "OC_SECTION",
                "rawText": "NOTHING HERE",
                "page": 0,
                "bbox": {"left": 500, "top": 500, "right": 510, "bottom": 510},
                "parent_id": None,
            }
        ]
        out, report = anchor_annotations(
            anns, is_pdf=True, pawls=self.pawls, content=""
        )
        self.assertEqual(out, [])
        self.assertTrue(report[0]["dropped"])

    def test_parent_id_passes_through(self):
        anns = [
            {
                "id": "root",
                "label": "OC_SECTION",
                "rawText": "CHAPTER 1",
                "page": 0,
                "bbox": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                "parent_id": None,
            },
            {
                "id": "child",
                "label": "OC_SECTION",
                "rawText": "Body",
                "page": 0,
                "bbox": {"left": 8, "top": 38, "right": 60, "bottom": 54},
                "parent_id": "root",
            },
        ]
        out, _ = anchor_annotations(anns, is_pdf=True, pawls=self.pawls, content="")
        child = [a for a in out if a["id"] == "child"][0]
        self.assertEqual(child["parent_id"], "root")


class AnchorTextTests(SimpleTestCase):
    CONTENT = "Intro. “Person” means any individual. Tail."

    def test_rawtext_refind_produces_span(self):
        anns = [
            {
                "id": "d1",
                "label": "DEFINITION",
                "rawText": "“Person” means any individual.",
                "start": 0,
                "end": 5,
                "parent_id": None,
            }
        ]
        out, report = anchor_annotations(
            anns, is_pdf=False, pawls=[], content=self.CONTENT
        )
        a = out[0]
        self.assertEqual(a["annotation_type"], "SPAN_LABEL")
        s, e = a["annotation_json"]["start"], a["annotation_json"]["end"]
        self.assertEqual(self.CONTENT[s:e], "“Person” means any individual.")
        self.assertEqual(a["annotation_json"]["text"], self.CONTENT[s:e])

    def test_repeated_text_disambiguated_by_hint(self):
        content = "term here. ... term here."
        anns = [
            {
                "id": "d",
                "label": "X",
                "rawText": "term here.",
                "start": 15,
                "end": 25,
                "parent_id": None,
            }
        ]
        out, _ = anchor_annotations(anns, is_pdf=False, pawls=[], content=content)
        s = out[0]["annotation_json"]["start"]
        self.assertEqual(s, content.rindex("term here."))

    def test_text_not_found_dropped(self):
        anns = [
            {
                "id": "d",
                "label": "X",
                "rawText": "absent",
                "start": 0,
                "end": 1,
                "parent_id": None,
            }
        ]
        out, report = anchor_annotations(
            anns, is_pdf=False, pawls=[], content=self.CONTENT
        )
        self.assertEqual(out, [])
        self.assertTrue(report[0]["dropped"])

    def test_null_rawtext_does_not_abort_batch(self):
        # A malformed annotation with rawText=None must be dropped+reported,
        # NOT raise and abort the whole batch (the report line used to do
        # ``None[:80]``). A valid annotation after it must still be anchored.
        anns: list[dict] = [
            {
                "id": "bad",
                "label": "X",
                "rawText": None,
                "start": 0,
                "end": 1,
                "parent_id": None,
            },
            {
                "id": "ok",
                "label": "X",
                "rawText": "Tail.",
                "start": 0,
                "end": 1,
                "parent_id": None,
            },
        ]
        out, report = anchor_annotations(
            anns, is_pdf=False, pawls=[], content=self.CONTENT
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "ok")
        self.assertTrue(report[0]["dropped"])
        self.assertFalse(report[1]["dropped"])


class LegacyFormatAdapterTests(SimpleTestCase):
    """The deferred pipeline accepts OLD-format annotations (baked
    ``annotation_json`` / ``tokensJsons``): the adapter drops the indices and
    ``anchor_annotations`` re-derives them from bbox + rawText."""

    def setUp(self):
        # Page 0: "CHAPTER 1", page 1: "SECTION 2".
        self.pawls = [
            _page([_tok(10, "CHAPTER"), _tok(90, "1")], index=0),
            _page([_tok(10, "SECTION"), _tok(90, "2")], index=1),
        ]

    def test_legacy_pdf_reanchors_ignoring_stale_tokensjsons(self):
        legacy = [
            {
                "id": 7,
                "annotationLabel": "OC_SECTION",
                "rawText": "CHAPTER 1",
                "page": 0,
                "parent_id": None,
                "annotation_json": {
                    "0": {
                        "bounds": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                        # Deliberately WRONG indices — must be ignored.
                        "tokensJsons": [{"pageIndex": 0, "tokenIndex": 99}],
                        "rawText": "CHAPTER 1",
                    }
                },
            }
        ]
        out, report = anchor_annotations(
            legacy, is_pdf=True, pawls=self.pawls, content=""
        )
        self.assertEqual(len(out), 1)
        a = out[0]
        self.assertEqual(a["annotationLabel"], "OC_SECTION")
        idxs = [t["tokenIndex"] for t in a["annotation_json"]["0"]["tokensJsons"]]
        self.assertEqual(idxs, [0, 1])  # re-derived, not the stale [99]
        self.assertFalse(any(r["dropped"] for r in report))

    def test_legacy_multipage_pdf_anchors_each_page(self):
        legacy = [
            {
                "id": 1,
                "annotationLabel": "OC_SECTION",
                "rawText": "CHAPTER 1 SECTION 2",
                "page": 0,
                "parent_id": None,
                "annotation_json": {
                    "0": {
                        "bounds": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                        "tokensJsons": [],
                        "rawText": "CHAPTER 1",
                    },
                    "1": {
                        "bounds": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                        "tokensJsons": [],
                        "rawText": "SECTION 2",
                    },
                },
            }
        ]
        out, _ = anchor_annotations(legacy, is_pdf=True, pawls=self.pawls, content="")
        self.assertEqual(len(out), 1)
        aj = out[0]["annotation_json"]
        self.assertIn("0", aj)
        self.assertIn("1", aj)
        self.assertEqual([t["tokenIndex"] for t in aj["1"]["tokensJsons"]], [0, 1])

    def test_legacy_span_reanchors(self):
        content = "Intro. “Person” means any individual. Tail."
        legacy = [
            {
                "id": "d1",
                "annotationLabel": "DEFINITION",
                "rawText": "“Person” means any individual.",
                "page": 0,
                "parent_id": None,
                "annotation_json": {
                    "start": 0,
                    "end": 5,
                    "text": "“Person” means any individual.",
                },
            }
        ]
        out, report = anchor_annotations(
            legacy, is_pdf=False, pawls=[], content=content
        )
        self.assertEqual(len(out), 1)
        s, e = out[0]["annotation_json"]["start"], out[0]["annotation_json"]["end"]
        self.assertEqual(content[s:e], "“Person” means any individual.")
        self.assertFalse(any(r["dropped"] for r in report))

    def test_legacy_structural_is_skipped_and_reported(self):
        legacy = [
            {
                "id": 1,
                "annotationLabel": "OC_SECTION",
                "rawText": "CHAPTER 1",
                "page": 0,
                "structural": True,
                "parent_id": None,
                "annotation_json": {
                    "0": {
                        "bounds": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                        "tokensJsons": [],
                        "rawText": "CHAPTER 1",
                    }
                },
            }
        ]
        out, report = anchor_annotations(
            legacy, is_pdf=True, pawls=self.pawls, content=""
        )
        self.assertEqual(out, [])
        self.assertTrue(report[0]["dropped"])
        # Direct adapter call also returns None for structural.
        self.assertIsNone(legacy_annotation_to_dumb_anchor(legacy[0], is_pdf=True))


class MetadataPassthroughTests(SimpleTestCase):
    """``link_url`` (OC_URL target) and ``data`` (e.g. geocoded payload) are
    not part of the anchor geometry, so the re-anchor must carry them verbatim
    onto the anchored dict — otherwise bulk import silently strips them."""

    def setUp(self):
        self.pawls = [_page([_tok(10, "CHAPTER"), _tok(90, "1")])]

    def test_pdf_carries_link_url_and_data(self):
        geo = {"canonical_name": "France", "lat": 46.0, "lng": 2.0, "geocoded": True}
        anns = [
            {
                "id": "u1",
                "label": "OC_URL",
                "rawText": "CHAPTER 1",
                "page": 0,
                "bbox": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                "link_url": "https://example.com/ref",
                "data": geo,
                "parent_id": None,
            }
        ]
        out, _ = anchor_annotations(anns, is_pdf=True, pawls=self.pawls, content="")
        self.assertEqual(out[0]["link_url"], "https://example.com/ref")
        self.assertEqual(out[0]["data"], geo)

    def test_text_carries_link_url_and_data(self):
        content = "Intro. PARIS is here. Tail."
        geo = {"canonical_name": "Paris", "lat": 48.85, "lng": 2.35, "geocoded": True}
        anns = [
            {
                "id": "c1",
                "label": "OC_CITY",
                "rawText": "PARIS",
                "start": 0,
                "end": 5,
                "data": geo,
                "parent_id": None,
            }
        ]
        out, _ = anchor_annotations(anns, is_pdf=False, pawls=[], content=content)
        self.assertEqual(out[0]["data"], geo)
        # No link_url supplied -> key is absent (column stays NULL), not None.
        self.assertNotIn("link_url", out[0])

    def test_absent_metadata_keys_stay_absent(self):
        anns = [
            {
                "id": "a1",
                "label": "OC_SECTION",
                "rawText": "CHAPTER 1",
                "page": 0,
                "bbox": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                "parent_id": None,
            }
        ]
        out, _ = anchor_annotations(anns, is_pdf=True, pawls=self.pawls, content="")
        self.assertNotIn("link_url", out[0])
        self.assertNotIn("data", out[0])

    def test_legacy_adapter_carries_link_url(self):
        legacy = [
            {
                "id": 7,
                "annotationLabel": "OC_URL",
                "rawText": "CHAPTER 1",
                "page": 0,
                "parent_id": None,
                "link_url": "https://example.com/legacy",
                "annotation_json": {
                    "0": {
                        "bounds": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                        "tokensJsons": [{"pageIndex": 0, "tokenIndex": 99}],
                        "rawText": "CHAPTER 1",
                    }
                },
            }
        ]
        out, _ = anchor_annotations(legacy, is_pdf=True, pawls=self.pawls, content="")
        self.assertEqual(out[0]["link_url"], "https://example.com/legacy")
