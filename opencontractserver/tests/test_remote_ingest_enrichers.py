"""
Unit tests for the remote-ingest pre-processing / enrichment stage
(``scripts/remote_ingest/enrichers.py`` + ``example_enrichers.py``).

These are pure-Python tests over synthetic PAWLs exports — no Django DB, no
docling, no network. They lock in the correctness of the annotation-building
helpers (token anchoring, annotation_json shape), the enrichment merge, and the
validation guard that stops a buggy enricher from shipping a broken annotation.
"""

import os
import sys

# The enrichment modules live under scripts/remote_ingest (they run inside the
# worker image, not the Django app), so add that dir to the path for import.
_REMOTE_INGEST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "remote_ingest",
)
if _REMOTE_INGEST not in sys.path:
    sys.path.insert(0, _REMOTE_INGEST)

import enrichers as E  # noqa: E402
import example_enrichers as EX  # noqa: E402
from django.test import SimpleTestCase  # noqa: E402


def _page(tokens, width=612.0, height=792.0, index=0):
    return {
        "page": {"width": width, "height": height, "index": index},
        "tokens": tokens,
    }


def _tok(x, y, w, h, text):
    return {"x": x, "y": y, "width": w, "height": h, "text": text}


def _export(pages):
    return {
        "pawls_file_content": pages,
        "page_count": len(pages),
        "labelled_text": [],
        "relationships": [],
        "doc_labels": [],
        "content": "",
    }


def _ctx(export, *, rel_path="dir/doc.pdf", content="some content"):
    return E.EnricherContext(
        rel_path=rel_path, abs_path="/data/" + rel_path, export=export, content=content
    )


class TokenAnchoringTests(SimpleTestCase):
    def setUp(self):
        self.tokens = [
            _tok(10, 100, 40, 12, "Effective"),
            _tok(55, 100, 30, 12, "Date:"),
            _tok(90, 100, 50, 12, "January"),
            _tok(145, 100, 15, 12, "1,"),
            _tok(165, 100, 35, 12, "2025"),
        ]
        self.ctx = _ctx(_export([_page(self.tokens)]))

    def test_find_token_matches_maps_indices(self):
        matches = self.ctx.find_token_matches(r"January 1, 2025")
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m.page, 0)
        self.assertEqual(m.token_indices, [2, 3, 4])
        self.assertEqual(m.text, "January 1, 2025")

    def test_find_token_matches_single_token(self):
        matches = self.ctx.find_token_matches(r"\bEffective\b")
        self.assertEqual([m.token_indices for m in matches], [[0]])

    def test_token_annotation_shape(self):
        match = self.ctx.find_token_matches(r"January 1, 2025")[0]
        ann = self.ctx.token_annotation("DATE", match)
        self.assertEqual(ann["annotationLabel"], "DATE")
        self.assertEqual(ann["annotation_type"], "TOKEN_LABEL")
        self.assertFalse(ann["structural"])
        self.assertEqual(ann["page"], 0)
        self.assertEqual(ann["rawText"], "January 1, 2025")

        page = ann["annotation_json"]["0"]
        # bounds = union of tokens 2,3,4
        self.assertEqual(page["bounds"]["left"], 90)
        self.assertEqual(page["bounds"]["top"], 100)
        self.assertEqual(page["bounds"]["right"], 200)  # 165 + 35
        self.assertEqual(page["bounds"]["bottom"], 112)  # 100 + 12
        self.assertEqual(
            page["tokensJsons"],
            [
                {"pageIndex": 0, "tokenIndex": 2},
                {"pageIndex": 0, "tokenIndex": 3},
                {"pageIndex": 0, "tokenIndex": 4},
            ],
        )


class EnrichmentMergeTests(SimpleTestCase):
    def test_apply_assigns_unique_ids_and_merges(self):
        export = _export([_page([_tok(0, 0, 10, 10, "X")])])
        # one pre-existing parser annotation id, to prove no collision
        export["labelled_text"].append({"id": "c0_#/texts/0", "annotationLabel": "p"})
        enr = E.Enrichment(
            annotations=[
                {"annotationLabel": "L", "rawText": "x", "annotation_json": {}},
                {"annotationLabel": "L", "rawText": "y", "annotation_json": {}},
            ],
            annotation_labels={"L": E.label_def("L")},
            doc_labels=["dt"],
            doc_label_defs={"dt": E.label_def("dt", E.DOC_TYPE_LABEL)},
            custom_meta={"k": "v"},
        )
        overlay = E.apply_enrichment(export, enr)
        ids = [a["id"] for a in export["labelled_text"]]
        self.assertIn("enr-0", ids)
        self.assertIn("enr-1", ids)
        self.assertEqual(len(set(ids)), len(ids))  # unique
        self.assertEqual(export["doc_labels"], ["dt"])
        self.assertEqual(overlay.custom_meta, {"k": "v"})
        self.assertIn("L", overlay.text_label_defs)
        self.assertIn("dt", overlay.doc_label_defs)

    def test_merge_combines_parts(self):
        a = E.Enrichment(custom_meta={"a": 1}, doc_labels=["x"])
        b = E.Enrichment(custom_meta={"b": 2}, doc_labels=["x", "y"], title="T")
        merged = E.Enrichment.merge([a, None, b])
        self.assertEqual(merged.custom_meta, {"a": 1, "b": 2})
        self.assertEqual(merged.doc_labels, ["x", "y"])
        self.assertEqual(merged.title, "T")


class ValidationTests(SimpleTestCase):
    def setUp(self):
        self.export = _export(
            [_page([_tok(0, 0, 10, 10, "A"), _tok(10, 0, 10, 10, "B")])]
        )

    def _valid_token_ann(self):
        return {
            "id": "e1",
            "annotationLabel": "L",
            "rawText": "A",
            "page": 0,
            "annotation_type": "TOKEN_LABEL",
            "annotation_json": {
                "0": {
                    "bounds": {"top": 0, "bottom": 10, "left": 0, "right": 10},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                    "rawText": "A",
                }
            },
        }

    def test_valid_passes(self):
        enr = E.Enrichment(
            annotations=[self._valid_token_ann()],
            annotation_labels={"L": E.label_def("L")},
        )
        self.assertEqual(E.validate_enrichment(self.export, enr), [])

    def test_token_index_out_of_range(self):
        ann = self._valid_token_ann()
        ann["annotation_json"]["0"]["tokensJsons"][0]["tokenIndex"] = 99
        enr = E.Enrichment(annotations=[ann], annotation_labels={"L": E.label_def("L")})
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(any("tokenIndex" in e for e in errs))

    def test_missing_label_def(self):
        enr = E.Enrichment(annotations=[self._valid_token_ann()])  # no label def
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(any("no definition" in e for e in errs))

    def test_empty_raw_text(self):
        ann = self._valid_token_ann()
        ann["rawText"] = "  "
        enr = E.Enrichment(annotations=[ann], annotation_labels={"L": E.label_def("L")})
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(any("rawText is empty" in e for e in errs))

    def test_relationship_unknown_id(self):
        ann = self._valid_token_ann()
        enr = E.Enrichment(
            annotations=[ann],
            annotation_labels={
                "L": E.label_def("L"),
                "R": E.label_def("R", E.RELATIONSHIP_LABEL),
            },
            relationships=[
                {
                    "relationshipLabel": "R",
                    "source_annotation_ids": ["e1"],
                    "target_annotation_ids": ["does-not-exist"],
                }
            ],
        )
        # validate runs BEFORE apply (as the driver calls it). The injected
        # annotation's explicit id "e1" resolves; "does-not-exist" does not.
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(
            any("unknown annotation id 'does-not-exist'" in e for e in errs)
        )
        self.assertFalse(any("'e1'" in e for e in errs))

    def test_relationship_to_injected_id_valid_without_apply(self):
        a1 = self._valid_token_ann()  # id "e1"
        a2 = dict(self._valid_token_ann(), id="e2")
        enr = E.Enrichment(
            annotations=[a1, a2],
            annotation_labels={
                "L": E.label_def("L"),
                "R": E.label_def("R", E.RELATIONSHIP_LABEL),
            },
            relationships=[
                {
                    "relationshipLabel": "R",
                    "source_annotation_ids": ["e1"],
                    "target_annotation_ids": ["e2"],
                }
            ],
        )
        self.assertEqual(E.validate_enrichment(self.export, enr), [])

    def test_structural_injection_rejected(self):
        ann = dict(self._valid_token_ann(), structural=True)
        enr = E.Enrichment(annotations=[ann], annotation_labels={"L": E.label_def("L")})
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(any("non-structural" in e for e in errs))

    def test_unresolvable_parent_id_rejected(self):
        ann = dict(self._valid_token_ann(), parent_id="ghost")
        enr = E.Enrichment(annotations=[ann], annotation_labels={"L": E.label_def("L")})
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(any("parent_id 'ghost'" in e for e in errs))

    def test_explicit_id_collision_with_parser_rejected(self):
        # a parser annotation with id "c0_x" already on the export
        self.export["labelled_text"].append({"id": "c0_x", "annotationLabel": "p"})
        ann = dict(self._valid_token_ann(), id="c0_x")
        enr = E.Enrichment(annotations=[ann], annotation_labels={"L": E.label_def("L")})
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(any("collides with a parser annotation id" in e for e in errs))

    def test_duplicate_injected_id_rejected(self):
        a1 = self._valid_token_ann()
        a2 = self._valid_token_ann()  # same id "e1"
        enr = E.Enrichment(
            annotations=[a1, a2], annotation_labels={"L": E.label_def("L")}
        )
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(any("duplicate injected annotation id" in e for e in errs))

    def test_doc_type_label_in_annotations_rejected(self):
        ann = dict(self._valid_token_ann(), annotation_type="DOC_TYPE_LABEL")
        enr = E.Enrichment(annotations=[ann], annotation_labels={"L": E.label_def("L")})
        errs = E.validate_enrichment(self.export, enr)
        self.assertTrue(any("DOC_TYPE_LABEL belongs in" in e for e in errs))


def _md_by_name(enr):
    return {m["column_name"]: m for m in enr.metadata}


class MetadataFieldTests(SimpleTestCase):
    def test_metadata_field_infers_type(self):
        self.assertEqual(E.metadata_field("c", "x")["data_type"], "STRING")
        self.assertEqual(E.metadata_field("c", 3)["data_type"], "INTEGER")
        self.assertEqual(E.metadata_field("c", True)["data_type"], "BOOLEAN")
        self.assertEqual(E.metadata_field("c", 1.5)["data_type"], "FLOAT")
        self.assertEqual(E.metadata_field("c", {"a": 1})["data_type"], "JSON")
        self.assertEqual(
            E.metadata_field("c", "x", data_type="DATE")["data_type"], "DATE"
        )

    def test_metadata_validation_value_type(self):
        export = _export([_page([_tok(0, 0, 10, 10, "x")])])
        bad = E.Enrichment(
            metadata=[E.metadata_field("Year", "2025", data_type="INTEGER")]
        )
        errs = E.validate_enrichment(export, bad)
        self.assertTrue(any("must be an integer" in e for e in errs))

    def test_metadata_validation_bad_data_type(self):
        export = _export([_page([_tok(0, 0, 10, 10, "x")])])
        bad = E.Enrichment(
            metadata=[{"column_name": "X", "data_type": "WIDGET", "value": 1}]
        )
        errs = E.validate_enrichment(export, bad)
        self.assertTrue(any("must be one of" in e for e in errs))

    def test_metadata_choice_valid(self):
        export = _export([_page([_tok(0, 0, 10, 10, "x")])])
        ok = E.Enrichment(
            metadata=[
                E.metadata_field(
                    "Type",
                    "A",
                    data_type="CHOICE",
                    validation_config={"choices": ["A", "B"]},
                )
            ]
        )
        self.assertEqual(E.validate_enrichment(export, ok), [])

    def test_apply_carries_metadata_to_overlay(self):
        export = _export([_page([_tok(0, 0, 10, 10, "x")])])
        enr = E.Enrichment(metadata=[E.metadata_field("Number", "058000")])
        overlay = E.apply_enrichment(export, enr)
        self.assertEqual(overlay.metadata[0]["column_name"], "Number")
        self.assertEqual(overlay.metadata[0]["data_type"], "STRING")


class ExampleEnricherTests(SimpleTestCase):
    def test_filename_metadata(self):
        ctx = _ctx(
            _export([_page([_tok(0, 0, 10, 10, "x")])]),
            rel_path="050000's/058000-R3 - General - Contract - Acme.pdf",
        )
        enr = EX.filename_metadata(ctx)
        md = _md_by_name(enr)
        self.assertEqual(md["Contract Number"]["value"], "058000")
        self.assertEqual(md["Revision"]["value"], "R3")
        self.assertEqual(md["Category"]["value"], "General")
        self.assertEqual(enr.custom_meta["source_path"], ctx.rel_path)
        self.assertEqual(E.validate_enrichment(ctx.export, enr), [])

    def test_effective_date_annotations(self):
        tokens = [
            _tok(0, 0, 50, 12, "January"),
            _tok(55, 0, 15, 12, "1,"),
            _tok(75, 0, 35, 12, "2025"),
        ]
        ctx = _ctx(_export([_page(tokens)]))
        enr = EX.effective_date_annotations(ctx)
        self.assertEqual(len(enr.annotations), 1)
        self.assertIn("DETECTED_DATE", enr.annotation_labels)
        md = _md_by_name(enr)
        self.assertEqual(md["Effective Date"]["value"], "2025-01-01")
        self.assertEqual(md["Effective Date"]["data_type"], "DATE")
        # the injected annotation + metadata are valid against the export
        self.assertEqual(E.validate_enrichment(ctx.export, enr), [])

    def test_contract_type_label(self):
        ctx = _ctx(
            _export([_page([_tok(0, 0, 10, 10, "x")])]),
            content="This CONSTRUCTION agreement ...",
        )
        enr = EX.contract_type_label(ctx)
        self.assertEqual(enr.doc_labels, ["contract:Construction-Related"])
        md = _md_by_name(enr)
        self.assertEqual(md["Contract Type"]["value"], "Construction-Related")
        self.assertEqual(md["Contract Type"]["data_type"], "CHOICE")
        self.assertIn("contract:Construction-Related", enr.doc_label_defs)
        self.assertEqual(E.validate_enrichment(ctx.export, enr), [])
