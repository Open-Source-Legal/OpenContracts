from django.test import SimpleTestCase

from opencontractserver.utils.annotation_anchoring import anchor_annotations


def _tok(x, text, y=10, w=None, h=12):
    return {"x": x, "y": y, "width": w if w is not None else len(text) * 8,
            "height": h, "text": text}


def _page(tokens, index=0):
    return {"page": {"width": 600, "height": 800, "index": index}, "tokens": tokens}


class AnchorPdfTests(SimpleTestCase):
    def setUp(self):
        self.pawls = [_page([_tok(10, "CHAPTER"), _tok(90, "1"), _tok(10, "Body", y=40)])]

    def test_bbox_anchors_to_tokens(self):
        anns = [{"id": "a1", "label": "OC_SECTION", "rawText": "CHAPTER 1",
                 "page": 0, "bbox": {"left": 8, "top": 8, "right": 130, "bottom": 24},
                 "parent_id": None}]
        out, report = anchor_annotations(anns, is_pdf=True, pawls=self.pawls, content="")
        self.assertEqual(len(out), 1)
        a = out[0]
        self.assertEqual(a["annotation_type"], "TOKEN_LABEL")
        self.assertEqual(a["annotationLabel"], "OC_SECTION")
        idxs = [t["tokenIndex"] for t in a["annotation_json"]["0"]["tokensJsons"]]
        self.assertEqual(idxs, [0, 1])
        self.assertFalse(any(r["dropped"] for r in report))

    def test_bbox_miss_falls_back_to_text(self):
        anns = [{"id": "a1", "label": "OC_SECTION", "rawText": "CHAPTER 1",
                 "page": 0, "bbox": {"left": 500, "top": 500, "right": 510, "bottom": 510},
                 "parent_id": None}]
        out, report = anchor_annotations(anns, is_pdf=True, pawls=self.pawls, content="")
        idxs = [t["tokenIndex"] for t in out[0]["annotation_json"]["0"]["tokensJsons"]]
        self.assertEqual(idxs, [0, 1])

    def test_unanchorable_pdf_is_dropped_and_reported(self):
        anns = [{"id": "z", "label": "OC_SECTION", "rawText": "NOTHING HERE",
                 "page": 0, "bbox": {"left": 500, "top": 500, "right": 510, "bottom": 510},
                 "parent_id": None}]
        out, report = anchor_annotations(anns, is_pdf=True, pawls=self.pawls, content="")
        self.assertEqual(out, [])
        self.assertTrue(report[0]["dropped"])

    def test_parent_id_passes_through(self):
        anns = [
            {"id": "root", "label": "OC_SECTION", "rawText": "CHAPTER 1", "page": 0,
             "bbox": {"left": 8, "top": 8, "right": 130, "bottom": 24}, "parent_id": None},
            {"id": "child", "label": "OC_SECTION", "rawText": "Body", "page": 0,
             "bbox": {"left": 8, "top": 38, "right": 60, "bottom": 54}, "parent_id": "root"},
        ]
        out, _ = anchor_annotations(anns, is_pdf=True, pawls=self.pawls, content="")
        child = [a for a in out if a["id"] == "child"][0]
        self.assertEqual(child["parent_id"], "root")


class AnchorTextTests(SimpleTestCase):
    CONTENT = "Intro. “Person” means any individual. Tail."

    def test_rawtext_refind_produces_span(self):
        anns = [{"id": "d1", "label": "DEFINITION",
                 "rawText": "“Person” means any individual.",
                 "start": 0, "end": 5, "parent_id": None}]
        out, report = anchor_annotations(anns, is_pdf=False, pawls=[], content=self.CONTENT)
        a = out[0]
        self.assertEqual(a["annotation_type"], "SPAN_LABEL")
        s, e = a["annotation_json"]["start"], a["annotation_json"]["end"]
        self.assertEqual(self.CONTENT[s:e], "“Person” means any individual.")
        self.assertEqual(a["annotation_json"]["text"], self.CONTENT[s:e])

    def test_repeated_text_disambiguated_by_hint(self):
        content = "term here. ... term here."
        anns = [{"id": "d", "label": "X", "rawText": "term here.",
                 "start": 15, "end": 25, "parent_id": None}]
        out, _ = anchor_annotations(anns, is_pdf=False, pawls=[], content=content)
        s = out[0]["annotation_json"]["start"]
        self.assertEqual(s, content.rindex("term here."))

    def test_text_not_found_dropped(self):
        anns = [{"id": "d", "label": "X", "rawText": "absent", "start": 0, "end": 1,
                 "parent_id": None}]
        out, report = anchor_annotations(anns, is_pdf=False, pawls=[], content=self.CONTENT)
        self.assertEqual(out, [])
        self.assertTrue(report[0]["dropped"])
