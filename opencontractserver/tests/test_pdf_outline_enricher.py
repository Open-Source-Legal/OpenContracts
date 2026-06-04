"""Tests for PdfOutlineEnricher.

These exercise the enricher directly (``enrich_document``) against a
hand-built OpenContractDocExport and a synthesized bookmarked PDF, so they do
not depend on a parser, the embedding pipeline, or document persistence.
"""

from typing import cast

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from opencontractserver.annotations.models import TOKEN_LABEL
from opencontractserver.constants.annotations import OC_SECTION_LABEL
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.enrichers.pdf_outline_enricher import (
    PdfOutlineEnricher,
    _walk_outline,
)
from opencontractserver.tests.fixtures.pdf_generator import create_pdf_with_outline
from opencontractserver.types.dicts import OpenContractDocExport, PawlsPagePythonType
from opencontractserver.users.models import User
from opencontractserver.utils.pdf_token_matching import (
    match_title_to_tokens as _match_title_to_tokens,
)
from opencontractserver.utils.pdf_token_matching import (
    page_text_tokens as _page_text_tokens,
)


class PdfOutlineEnricherTests(TestCase):
    """Behavioural tests for PdfOutlineEnricher._enrich_document_impl."""

    user: User

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username="enricher_user", password="pw")

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
        return cast(
            dict,
            PdfOutlineEnricher().enrich_document(
                self.user.id,
                doc.id,
                cast(OpenContractDocExport, export),
                **kwargs,
            ),
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
        export: dict = {"pawls_file_content": [], "labelled_text": []}
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

    def test_id_prefix_collision_falls_back_to_uuid(self):
        """An existing enr_outline_-prefixed id forces a uuid-suffixed prefix."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["Heading"]}],
            outline=[{"title": "Heading", "page": 0, "level": 0}],
        )
        # Pre-seed an annotation whose id already uses the default prefix.
        existing = [
            {
                "id": "enr_outline_1",
                "annotationLabel": "STRUCT",
                "rawText": "x",
                "page": 0,
                "annotation_json": {},
                "parent_id": None,
                "annotation_type": TOKEN_LABEL,
                "structural": True,
            }
        ]
        export = self._export([["Heading", "body"]], labelled_text=existing)
        result = self._enrich(doc, export)
        sections = self._sections(result)
        self.assertEqual(len(sections), 1)
        # The plain prefix would have collided ("enr_outline_1"); the fallback
        # inserts an 8-hex-char uuid segment so the new ids cannot clash.
        self.assertRegex(sections[0]["id"], r"^enr_outline_[0-9a-f]{8}_\d+$")

    def test_no_pdf_file_returns_unchanged(self):
        """A document with no pdf_file cannot be read — enricher is a no-op."""
        doc = Document.objects.create(
            creator=self.user,
            title="No File Doc",
            file_type="application/pdf",
            page_count=1,
            processing_started=timezone.now(),
        )
        export = self._export([["Heading", "body"]])
        result = self._enrich(doc, export)
        self.assertEqual(self._sections(result), [])

    def test_non_list_labelled_text_is_tolerated(self):
        """A malformed (non-list) labelled_text is replaced with an empty list."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["Heading"]}],
            outline=[{"title": "Heading", "page": 0, "level": 0}],
        )
        export = {
            "pawls_file_content": self._pawls([["Heading", "body"]]),
            "labelled_text": "not-a-list",
        }
        result = self._enrich(doc, cast(dict, export))
        # The garbage value is dropped; only the enricher's section survives.
        self.assertEqual(len(self._sections(result)), 1)

    def test_max_entries_zero_yields_no_sections(self):
        """max_entries=0 makes the outline walk produce no nodes at all."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["Heading"]}],
            outline=[{"title": "Heading", "page": 0, "level": 0}],
        )
        export = self._export([["Heading", "body"]])
        result = self._enrich(doc, export, max_entries=0)
        self.assertEqual(self._sections(result), [])

    def test_destination_page_beyond_pawls_is_skipped(self):
        """A bookmark whose page is beyond the parsed PAWLs layer is dropped."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["Page Zero"]}, {"lines": ["Page One"]}],
            outline=[{"title": "Page One", "page": 1, "level": 0}],
        )
        # PAWLs content has only one page; the bookmark targets page index 1.
        export = self._export([["Page", "Zero", "text"]])
        result = self._enrich(doc, export)
        self.assertEqual(self._sections(result), [])

    def test_image_only_page_cannot_anchor(self):
        """A destination page with only image tokens yields no text to anchor."""
        doc = self._make_pdf_doc(
            pages=[{"lines": ["Heading"]}],
            outline=[{"title": "Heading", "page": 0, "level": 0}],
        )
        export = {
            "pawls_file_content": [
                {
                    "page": {"width": 612.0, "height": 792.0, "index": 0},
                    "tokens": [
                        {
                            "x": 72.0,
                            "y": 700.0,
                            "width": 40.0,
                            "height": 12.0,
                            "text": "Heading",
                            "is_image": True,
                        }
                    ],
                }
            ],
            "labelled_text": [],
        }
        result = self._enrich(doc, cast(dict, export))
        self.assertEqual(self._sections(result), [])

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


class _FakeDest:
    """Stand-in for a pypdf ``Destination`` carrying a plain title."""

    def __init__(self, title: str):
        self.title = title


class _BadTitleDest:
    """A ``Destination`` whose ``.title`` access raises (malformed object)."""

    @property
    def title(self) -> str:
        raise RuntimeError("malformed destination title")


class _FakeReader:
    """Resolves destination page numbers from an identity map.

    Items absent from the map raise — mimicking pypdf's behaviour for a
    bookmark whose destination cannot be resolved to a page.
    """

    def __init__(self, page_for: dict[int, int]):
        self._page_for = page_for

    def get_destination_page_number(self, item) -> int:
        if id(item) in self._page_for:
            return self._page_for[id(item)]
        raise ValueError("unresolvable destination")


class PdfOutlineHelperTests(SimpleTestCase):
    """Unit tests for the module-level helper functions."""

    def test_page_text_tokens_skips_image_and_empty_tokens(self):
        """Image tokens and blank-text tokens are excluded; indices preserved."""
        page = {
            "tokens": [
                {"text": "img", "is_image": True},
                {"text": ""},
                {"text": "   "},
                {"text": "real"},
            ]
        }
        texts, indices = _page_text_tokens(cast(PawlsPagePythonType, page))
        self.assertEqual(texts, ["real"])
        # The kept token's index is its position in the ORIGINAL tokens array.
        self.assertEqual(indices, [3])

    def test_match_title_to_tokens_empty_title_returns_none(self):
        """A whitespace-only title normalizes to empty and cannot match."""
        self.assertIsNone(_match_title_to_tokens("   ", ["alpha", "beta"], 0.8))

    def test_match_title_to_tokens_window_stops_at_max_len(self):
        """The fuzzy window stops growing once it exceeds the length cap."""
        # Short title -> small max_len; the second token blows past it, so the
        # window breaks without ever matching.
        result = _match_title_to_tokens(
            "ab", ["abc", "extraordinarilylongtokenword", "tail"], 0.99
        )
        self.assertIsNone(result)

    def test_walk_outline_skips_bare_nested_lists(self):
        """A bare nested list with no preceding Destination is skipped."""
        outline: list = [[] for _ in range(3)]
        nodes = _walk_outline(_FakeReader({}), outline, "enr_", 50, 10)
        self.assertEqual(nodes, [])

    def test_walk_outline_skips_duplicate_entries(self):
        """The same Destination object appearing twice is only emitted once."""
        dest = _FakeDest("Heading")
        outline = [dest, dest]
        reader = _FakeReader({id(dest): 0})
        nodes = _walk_outline(reader, outline, "enr_", 50, 10)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].title, "Heading")

    def test_walk_outline_drops_malformed_title(self):
        """A Destination whose title access raises is dropped, not fatal."""
        bad = _BadTitleDest()
        nodes = _walk_outline(_FakeReader({id(bad): 0}), [bad], "enr_", 50, 10)
        self.assertEqual(nodes, [])

    def test_walk_outline_drops_unresolvable_destination(self):
        """A bookmark whose destination page cannot be resolved is dropped."""
        dest = _FakeDest("Heading")
        # Empty page map -> get_destination_page_number raises.
        nodes = _walk_outline(_FakeReader({}), [dest], "enr_", 50, 10)
        self.assertEqual(nodes, [])

    def test_walk_outline_aborts_on_item_cap(self):
        """A pathological outline is bounded by the processed-item cap."""
        # max_entries=2 -> item_cap = 2 * 4 = 8; 9 non-emitting items trip it.
        outline: list = [[] for _ in range(9)]
        nodes = _walk_outline(_FakeReader({}), outline, "enr_", 2, 10)
        self.assertEqual(nodes, [])
