"""Tests for PdfOutlineEnricher.

These exercise the enricher directly (``enrich_document``) against a
hand-built OpenContractDocExport and a synthesized bookmarked PDF, so they do
not depend on a parser, the embedding pipeline, or document persistence.
"""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import TOKEN_LABEL
from opencontractserver.constants.annotations import OC_SECTION_LABEL
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.enrichers.pdf_outline_enricher import (
    PdfOutlineEnricher,
)
from opencontractserver.tests.fixtures.pdf_generator import create_pdf_with_outline

User = get_user_model()


class PdfOutlineEnricherTests(TestCase):
    """Behavioural tests for PdfOutlineEnricher._enrich_document_impl."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user("enricher_user", password="pw")

    # ---- helpers ----------------------------------------------------------

    def _make_pdf_doc(self, pages: list[dict], outline: list[dict]) -> Document:
        """Create a Document whose pdf_file is a synthesized bookmarked PDF."""
        pdf_bytes = create_pdf_with_outline(pages, outline)
        doc = Document.objects.create(
            creator=self.user,
            title="Outline Doc",
            file_type="application/pdf",
            page_count=len(pages),
            # processing_started suppresses the ingest signal — this doc is a
            # test fixture, not a real upload.
            processing_started=timezone.now(),
        )
        doc.pdf_file.save("outline.pdf", ContentFile(pdf_bytes))
        return doc

    @staticmethod
    def _pawls(pages_words: list[list[str]]) -> list[dict]:
        """Build PAWLs page content; each page is a left-to-right token row."""
        pages = []
        for idx, words in enumerate(pages_words):
            tokens = []
            x = 72.0
            for word in words:
                width = max(6.0 * len(word), 6.0)
                tokens.append(
                    {
                        "x": x,
                        "y": 700.0,
                        "width": width,
                        "height": 12.0,
                        "text": word,
                    }
                )
                x += width + 4.0
            pages.append(
                {
                    "page": {"width": 612.0, "height": 792.0, "index": idx},
                    "tokens": tokens,
                }
            )
        return pages

    def _export(self, pages_words, labelled_text=None) -> dict:
        return {
            "pawls_file_content": self._pawls(pages_words),
            "labelled_text": list(labelled_text or []),
        }

    def _enrich(self, doc: Document, export: dict, **kwargs) -> dict:
        return PdfOutlineEnricher().enrich_document(
            self.user.id, doc.id, export, **kwargs
        )

    @staticmethod
    def _sections(export: dict) -> list[dict]:
        return [
            a
            for a in export["labelled_text"]
            if a["annotationLabel"] == OC_SECTION_LABEL
        ]

    # ---- tests ------------------------------------------------------------

    def test_happy_path_nested_outline(self):
        """A nested outline yields a correctly-anchored OC_SECTION tree."""
        doc = self._make_pdf_doc(
            pages=[
                {"lines": ["Chapter One"]},
                {"lines": ["Section A"]},
                {"lines": ["Section B"]},
            ],
            outline=[
                {"title": "Chapter One", "page": 0, "level": 0},
                {"title": "Section A", "page": 1, "level": 1},
                {"title": "Section B", "page": 2, "level": 1},
            ],
        )
        export = self._export(
            [
                ["Chapter", "One", "intro", "body"],
                ["Section", "A", "details"],
                ["Section", "B", "more"],
            ]
        )
        result = self._enrich(doc, export)
        sections = self._sections(result)
        self.assertEqual(len(sections), 3)

        by_title = {s["rawText"]: s for s in sections}
        self.assertEqual(set(by_title), {"Chapter One", "Section A", "Section B"})
        for section in sections:
            self.assertEqual(section["annotation_type"], TOKEN_LABEL)
            self.assertFalse(section["structural"])

        # Pages are 0-based and correct.
        self.assertEqual(by_title["Chapter One"]["page"], 0)
        self.assertEqual(by_title["Section A"]["page"], 1)
        self.assertEqual(by_title["Section B"]["page"], 2)

        # Hierarchy: children point at the root's export-local id.
        root = by_title["Chapter One"]
        self.assertIsNone(root["parent_id"])
        self.assertEqual(by_title["Section A"]["parent_id"], root["id"])
        self.assertEqual(by_title["Section B"]["parent_id"], root["id"])

        # annotation_json anchors to real tokens on the destination page.
        ajson = by_title["Section A"]["annotation_json"]
        self.assertEqual(set(ajson), {"1"})
        self.assertTrue(ajson["1"]["tokensJsons"])
        self.assertEqual(ajson["1"]["tokensJsons"][0]["pageIndex"], 1)

    def test_no_outline_returns_unchanged(self):
        """A PDF without bookmarks leaves labelled_text untouched."""
        doc = self._make_pdf_doc(pages=[{"lines": ["Plain page"]}], outline=[])
        export = self._export([["Plain", "page", "text"]])
        result = self._enrich(doc, export)
        self.assertEqual(self._sections(result), [])
        self.assertEqual(len(result["labelled_text"]), 0)

    def test_no_pawls_returns_unchanged(self):
        """With no PAWLs token data, the enricher cannot anchor — no-op."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["Heading"]}],
            outline=[{"title": "Heading", "page": 0, "level": 0}],
        )
        export = {"pawls_file_content": [], "labelled_text": []}
        result = self._enrich(doc, export)
        self.assertEqual(result["labelled_text"], [])

    def test_unmatched_parent_dropped_children_reparented(self):
        """An unmatched parent is dropped; its children re-parent upward."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["page0"]}, {"lines": ["Real Child"]}],
            outline=[
                {"title": "Missing Heading", "page": 0, "level": 0},
                {"title": "Real Child", "page": 1, "level": 1},
            ],
        )
        # Page 0 does NOT contain "Missing Heading"; page 1 has "Real Child".
        export = self._export(
            [
                ["completely", "different", "words"],
                ["Real", "Child", "section"],
            ]
        )
        result = self._enrich(doc, export)
        sections = self._sections(result)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["rawText"], "Real Child")
        # Parent was dropped, so the child re-parents to the root (None).
        self.assertIsNone(sections[0]["parent_id"])

    def test_fuzzy_match_within_threshold(self):
        """A bookmark title with a typo still anchors via fuzzy matching."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["General Fund"]}],
            outline=[{"title": "Genral Fund", "page": 0, "level": 0}],
        )
        export = self._export([["General", "Fund", "balance"]])
        result = self._enrich(doc, export)
        sections = self._sections(result)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["rawText"], "Genral Fund")

    def test_unmatched_title_dropped(self):
        """A title with no resemblance to page text is dropped entirely."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["page"]}],
            outline=[{"title": "Totally Unrelated Heading", "page": 0, "level": 0}],
        )
        export = self._export([["xyz", "qrs", "tuv"]])
        result = self._enrich(doc, export)
        self.assertEqual(self._sections(result), [])

    def test_max_depth_prunes_deep_branches(self):
        """Outline branches deeper than max_depth are pruned."""
        doc = self._make_pdf_doc(
            pages=[{"lines": [f"H{i}"]} for i in range(4)],
            outline=[
                {"title": "Level0", "page": 0, "level": 0},
                {"title": "Level1", "page": 1, "level": 1},
                {"title": "Level2", "page": 2, "level": 2},
                {"title": "Level3", "page": 3, "level": 3},
            ],
        )
        export = self._export(
            [
                ["Level0", "body"],
                ["Level1", "body"],
                ["Level2", "body"],
                ["Level3", "body"],
            ]
        )
        result = self._enrich(doc, export, max_depth=2)
        titles = {s["rawText"] for s in self._sections(result)}
        # max_depth=2 keeps depths 0 and 1; depth 2+ is pruned.
        self.assertEqual(titles, {"Level0", "Level1"})

    def test_max_entries_truncates(self):
        """No more than max_entries OC_SECTION annotations are emitted."""
        doc = self._make_pdf_doc(
            pages=[{"lines": [f"Sec{i}"]} for i in range(4)],
            outline=[{"title": f"Sec{i}", "page": i, "level": 0} for i in range(4)],
        )
        export = self._export([[f"Sec{i}", "body"] for i in range(4)])
        result = self._enrich(doc, export, max_entries=2)
        self.assertEqual(len(self._sections(result)), 2)

    def test_existing_annotations_preserved_and_ids_prefixed(self):
        """Parser-emitted annotations survive; enricher ids are prefixed."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["Heading"]}],
            outline=[{"title": "Heading", "page": 0, "level": 0}],
        )
        existing = [
            {
                "id": "parser_0",
                "annotationLabel": "STRUCT",
                "rawText": "x",
                "page": 0,
                "annotation_json": {
                    "0": {
                        "bounds": {
                            "top": 0,
                            "bottom": 1,
                            "left": 0,
                            "right": 1,
                        },
                        "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                        "rawText": "x",
                    }
                },
                "parent_id": None,
                "annotation_type": TOKEN_LABEL,
                "structural": True,
            }
        ]
        export = self._export([["Heading", "body"]], labelled_text=existing)
        result = self._enrich(doc, export)

        self.assertTrue(any(a["id"] == "parser_0" for a in result["labelled_text"]))
        sections = self._sections(result)
        self.assertEqual(len(sections), 1)
        self.assertTrue(sections[0]["id"].startswith("enr_outline_"))

    def test_emitted_annotation_json_shape(self):
        """The emitted token annotation_json matches the documented shape."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["Budget Summary"]}],
            outline=[{"title": "Budget Summary", "page": 0, "level": 0}],
        )
        export = self._export([["Budget", "Summary", "fiscal", "year"]])
        result = self._enrich(doc, export)
        section = self._sections(result)[0]

        page_key = str(section["page"])
        ajson = section["annotation_json"]
        self.assertEqual(set(ajson), {page_key})

        page_data = ajson[page_key]
        self.assertEqual(set(page_data), {"bounds", "tokensJsons", "rawText"})
        self.assertEqual(set(page_data["bounds"]), {"top", "bottom", "left", "right"})
        for value in page_data["bounds"].values():
            self.assertGreaterEqual(value, 0)

        token_count = len(export["pawls_file_content"][section["page"]]["tokens"])
        self.assertTrue(page_data["tokensJsons"])
        for ref in page_data["tokensJsons"]:
            self.assertEqual(set(ref), {"pageIndex", "tokenIndex"})
            self.assertEqual(ref["pageIndex"], section["page"])
            self.assertGreaterEqual(ref["tokenIndex"], 0)
            self.assertLess(ref["tokenIndex"], token_count)
