"""
Tests for the extraction grounding pipeline.

Tests extract_groundable_strings (unit) and the full grounding pipeline
(integration with Django models).
"""

import json

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase

from opencontractserver.utils.extraction_grounding import extract_groundable_strings


def _build_pawls_for_text(
    pages_text: list[str], page_width: float = 612.0, page_height: float = 792.0
) -> str:
    """Build a v1 PAWLS JSON payload that embeds ``pages_text`` as tokens.

    Each page's text is split on whitespace and laid out as a single row
    of tokens with simple monotonically increasing x-coordinates.  The
    resulting JSON is suitable for ``build_translation_layer`` and lets
    integration tests exercise the PDF grounding path without a real PDF.
    """
    pages: list[dict] = []
    for page_index, text in enumerate(pages_text):
        tokens: list[dict] = []
        x_pos = 10.0
        for word in text.split():
            tokens.append(
                {
                    "x": x_pos,
                    "y": 100.0,
                    "width": float(len(word)) * 6.0,
                    "height": 12.0,
                    "text": word,
                }
            )
            x_pos += float(len(word)) * 6.0 + 4.0
        pages.append(
            {
                "page": {
                    "width": page_width,
                    "height": page_height,
                    "index": page_index,
                },
                "tokens": tokens,
            }
        )
    return json.dumps(pages)


class TestExtractGroundableStrings(SimpleTestCase):
    """Unit tests for extract_groundable_strings() — no Django DB needed."""

    def test_simple_string(self):
        data = "Acme Corporation"
        result = extract_groundable_strings(data)
        self.assertEqual(result, ["Acme Corporation"])

    def test_dict_with_string_values(self):
        data = {
            "party_name": "Acme Holdings, Inc.",
            "jurisdiction": "Delaware",
            "amount": 50000000,
        }
        result = extract_groundable_strings(data)
        self.assertIn("Acme Holdings, Inc.", result)
        self.assertIn("Delaware", result)
        # Numeric values are excluded
        self.assertTrue(all(not r.isdigit() for r in result))

    def test_nested_dict(self):
        data = {
            "parties": {
                "seller": {"name": "Acme Holdings, Inc.", "state": "Delaware"},
                "buyer": {"name": "Global Acquisitions LLC", "state": "New York"},
            }
        }
        result = extract_groundable_strings(data)
        self.assertIn("Acme Holdings, Inc.", result)
        self.assertIn("Global Acquisitions LLC", result)

    def test_list_of_strings(self):
        data = [
            "Section 2.1 Purchase and Sale",
            "Section 3.1 Representations",
            "Section 4.1 Indemnification",
        ]
        result = extract_groundable_strings(data)
        self.assertEqual(len(result), 3)

    def test_list_of_dicts(self):
        data = [
            {"name": "Acme Holdings, Inc.", "role": "Seller"},
            {"name": "Global Acquisitions LLC", "role": "Buyer"},
        ]
        result = extract_groundable_strings(data)
        self.assertIn("Acme Holdings, Inc.", result)
        self.assertIn("Global Acquisitions LLC", result)
        self.assertIn("Seller", result)
        self.assertIn("Buyer", result)

    def test_filters_short_strings(self):
        data = {"a": "Hi", "b": "Yes", "c": "This is a longer string"}
        result = extract_groundable_strings(data)
        self.assertEqual(result, ["This is a longer string"])

    def test_filters_boolean_like(self):
        data = ["true", "false", "yes", "no", "None", "null", "n/a"]
        result = extract_groundable_strings(data)
        self.assertEqual(result, [])

    def test_filters_pure_numeric(self):
        data = ["42", "3.14", "1,000,000", "Actually a sentence with numbers 42"]
        result = extract_groundable_strings(data)
        self.assertEqual(result, ["Actually a sentence with numbers 42"])

    def test_deduplication(self):
        data = ["Acme Corp", "Acme Corp", "Acme Corp"]
        result = extract_groundable_strings(data)
        self.assertEqual(result, ["Acme Corp"])

    def test_max_limit(self):
        data = [f"String number {i} is quite long enough" for i in range(100)]
        result = extract_groundable_strings(data)
        self.assertLessEqual(len(result), 50)

    def test_none_and_empty(self):
        self.assertEqual(extract_groundable_strings(None), [])
        self.assertEqual(extract_groundable_strings(""), [])
        self.assertEqual(extract_groundable_strings({}), [])
        self.assertEqual(extract_groundable_strings([]), [])

    def test_realistic_extraction_output(self):
        """Simulate what a real Datacell.data["data"] looks like."""
        data = {
            "data": {
                "agreement_type": "Asset Purchase Agreement",
                "effective_date": "March 15, 2024",
                "parties": [
                    {"name": "Acme Holdings, Inc.", "role": "Seller"},
                    {"name": "Global Acquisitions LLC", "role": "Buyer"},
                ],
                "purchase_price": "$50,000,000.00",
                "governing_law": "State of Delaware",
            }
        }
        result = extract_groundable_strings(data["data"])
        self.assertIn("Asset Purchase Agreement", result)
        self.assertIn("March 15, 2024", result)
        self.assertIn("Acme Holdings, Inc.", result)
        self.assertIn("Global Acquisitions LLC", result)
        self.assertIn("State of Delaware", result)


class TestIsNonGroundable(SimpleTestCase):
    """Direct tests for _is_non_groundable() edge cases."""

    def setUp(self):
        from opencontractserver.utils.extraction_grounding import _is_non_groundable

        self.is_non_groundable = _is_non_groundable

    def test_boolean_strings(self):
        for val in ("true", "false", "yes", "no", "None", "null", "n/a"):
            self.assertTrue(self.is_non_groundable(val), f"{val!r} should be excluded")

    def test_pure_integer_string(self):
        self.assertTrue(self.is_non_groundable("42"))

    def test_pure_float_string(self):
        self.assertTrue(self.is_non_groundable("3.14"))

    def test_comma_separated_number(self):
        # "50,000,000" parses as float after comma removal -> excluded
        self.assertTrue(self.is_non_groundable("50,000,000"))

    def test_dollar_amount_is_groundable(self):
        # "$50,000,000.00" has a dollar sign so float() fails -> groundable
        self.assertFalse(self.is_non_groundable("$50,000,000.00"))

    def test_normal_text_is_groundable(self):
        self.assertFalse(self.is_non_groundable("Acme Holdings, Inc."))

    def test_sentence_with_numbers_is_groundable(self):
        self.assertFalse(self.is_non_groundable("Section 4.2 of the Agreement"))


class TestGroundingPipelineIntegration(TestCase):
    """Integration tests for the full grounding pipeline with Django models.

    These tests verify that ground_extraction_to_annotations correctly
    creates SPAN_LABEL annotations for text documents.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.files.base import ContentFile

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import (
            Column,
            Datacell,
            Extract,
            Fieldset,
        )
        from opencontractserver.notifications.models import Notification

        User = get_user_model()
        self.user = User.objects.create_user(
            username="grounding_test_user", password="testpass"
        )

        # Clear any auto-created notifications from signal handlers
        Notification.objects.filter(recipient=self.user).delete()

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Grounding Test Corpus", creator=self.user
        )

        # Create a text document with known content
        self.doc_text = (
            "ASSET PURCHASE AGREEMENT\n\n"
            "This Agreement is entered into as of March 15, 2024, "
            'by and between Acme Holdings, Inc. ("Seller") and '
            'Global Acquisitions LLC ("Buyer").\n\n'
            "The Purchase Price shall be Fifty Million Dollars ($50,000,000.00)."
        )
        self.document = Document.objects.create(
            title="Test Contract",
            creator=self.user,
            file_type="text/plain",
        )
        self.document.txt_extract_file.save(
            "test_contract.txt", ContentFile(self.doc_text.encode())
        )
        self.corpus.add_document(document=self.document, user=self.user)

        # Create extraction infrastructure
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            name="Party Names",
            query="Extract all party names",
            output_type="str",
            creator=self.user,
        )
        self.extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.user,
        )
        self.datacell = Datacell.objects.create(
            extract=self.extract,
            column=self.column,
            document=self.document,
            creator=self.user,
            data={"data": ["Acme Holdings, Inc.", "Global Acquisitions LLC"]},
        )

    def test_ground_text_document(self):
        """Test grounding on a text/plain document creates SPAN_LABEL annotations."""
        from opencontractserver.annotations.models import SPAN_LABEL
        from opencontractserver.constants.annotations import OC_EXTRACT_SOURCE_LABEL
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        annotations = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )

        self.assertGreater(len(annotations), 0)

        for annot in annotations:
            self.assertEqual(annot.annotation_type, SPAN_LABEL)
            self.assertEqual(annot.document, self.document)
            self.assertEqual(annot.corpus, self.corpus)
            self.assertFalse(annot.structural)
            self.assertIsNotNone(annot.annotation_label)
            assert annot.annotation_label is not None  # narrow for mypy
            self.assertEqual(annot.annotation_label.text, OC_EXTRACT_SOURCE_LABEL)

            # Verify span data
            self.assertIn("start", annot.json)
            self.assertIn("end", annot.json)
            self.assertEqual(
                self.doc_text[annot.json["start"] : annot.json["end"]],
                annot.raw_text,
            )

        # Verify datacell sources were linked
        self.datacell.refresh_from_db()
        self.assertEqual(self.datacell.sources.count(), len(annotations))

    def test_ground_with_corpus_id(self):
        """Test that passing corpus as int (ID) works."""
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        annotations = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus.id,
            user_id=self.user.id,
            enable_fuzzy=False,
        )

        self.assertGreater(len(annotations), 0)

    def test_ground_no_corpus_returns_empty(self):
        """Without a corpus, grounding should return empty (no label creation)."""
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        annotations = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=None,
            user_id=self.user.id,
        )

        self.assertEqual(len(annotations), 0)

    def test_ground_empty_data_returns_empty(self):
        """Datacell with no data should return empty."""
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        self.datacell.data = {}
        self.datacell.save()

        annotations = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
        )

        self.assertEqual(len(annotations), 0)

    def test_ground_no_matches_returns_empty(self):
        """When extracted values don't appear in document, no annotations created."""
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        self.datacell.data = {"data": ["Totally nonexistent company name XYZ123"]}
        self.datacell.save()

        annotations = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )

        self.assertEqual(len(annotations), 0)

    def test_ground_text_document_is_idempotent(self):
        """Running grounding twice should not create duplicate annotations.

        Simulates a Celery retry after a partial failure.  The second call
        must reuse existing OC_EXTRACT_SOURCE annotations rather than
        bloating ``datacell.sources`` with duplicates.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        first = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )
        self.assertGreater(len(first), 0)
        first_count = Annotation.objects.filter(document=self.document).count()
        first_ids = sorted(a.id for a in first)

        second = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )
        second_count = Annotation.objects.filter(document=self.document).count()
        second_ids = sorted(a.id for a in second)

        self.assertEqual(
            first_count,
            second_count,
            "Re-running grounding created duplicate annotations.",
        )
        self.assertEqual(
            first_ids,
            second_ids,
            "Re-running grounding returned annotations with different IDs.",
        )

        self.datacell.refresh_from_db()
        self.assertEqual(self.datacell.sources.count(), first_count)


class TestGroundingPipelinePDFIntegration(TestCase):
    """Integration tests for grounding against a PDF-shaped document.

    Builds a synthetic multi-page PAWLS payload (no real PDF needed) and
    exercises the TOKEN_LABEL path through PlasmaPDF's translation layer.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.files.base import ContentFile

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import (
            Column,
            Datacell,
            Extract,
            Fieldset,
        )
        from opencontractserver.notifications.models import Notification

        User = get_user_model()
        self.user = User.objects.create_user(
            username="grounding_pdf_user", password="testpass"
        )
        Notification.objects.filter(recipient=self.user).delete()

        self.corpus = Corpus.objects.create(
            title="PDF Grounding Corpus", creator=self.user
        )

        # Two-page synthetic document; "Acme Holdings" is on page 0,
        # "Global Acquisitions" on page 1.
        self.pages_text = [
            "ASSET PURCHASE AGREEMENT between Acme Holdings Inc and others",
            "Global Acquisitions LLC shall serve as the Buyer of record",
        ]
        pawls_json = _build_pawls_for_text(self.pages_text)

        self.document = Document.objects.create(
            title="PDF Grounding Test",
            creator=self.user,
            file_type="application/pdf",
        )
        self.document.pawls_parse_file.save(
            "test.pawls", ContentFile(pawls_json.encode())
        )
        self.corpus.add_document(document=self.document, user=self.user)

        self.fieldset = Fieldset.objects.create(name="PDF Fieldset", creator=self.user)
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            name="Parties",
            query="Extract parties",
            output_type="str",
            creator=self.user,
        )
        self.extract = Extract.objects.create(
            name="PDF Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.user,
        )
        self.datacell = Datacell.objects.create(
            extract=self.extract,
            column=self.column,
            document=self.document,
            creator=self.user,
            data={"data": ["Acme Holdings", "Global Acquisitions"]},
        )

    def test_ground_pdf_creates_token_label_annotations(self):
        """PDF grounding should create TOKEN_LABEL annotations with valid pages."""
        from opencontractserver.annotations.models import TOKEN_LABEL
        from opencontractserver.constants.annotations import OC_EXTRACT_SOURCE_LABEL
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        annotations = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )

        self.assertGreater(len(annotations), 0)
        for annot in annotations:
            self.assertEqual(annot.annotation_type, TOKEN_LABEL)
            self.assertEqual(annot.document, self.document)
            self.assertEqual(annot.corpus, self.corpus)
            self.assertFalse(annot.structural)
            self.assertIsNotNone(annot.annotation_label)
            assert annot.annotation_label is not None  # narrow for mypy
            self.assertEqual(annot.annotation_label.text, OC_EXTRACT_SOURCE_LABEL)
            # PlasmaPDF returns 0-indexed pages; valid range is
            # [0, len(pages) - 1]. The bug we're guarding against is the
            # silent fallback that would have saved everything on a single
            # default page even when the span lives on a different one.
            self.assertIsInstance(annot.page, int)
            self.assertGreaterEqual(annot.page, 0)
            self.assertLess(annot.page, len(self.pages_text))
            self.assertTrue(annot.raw_text)

        # "Acme Holdings" is on page 0 (0-indexed) and "Global Acquisitions"
        # on page 1 — confirm the per-page mapping actually works by
        # checking we got annotations on more than one page.
        pages_seen = {a.page for a in annotations}
        self.assertGreater(
            len(pages_seen),
            1,
            "Expected grounding to span multiple PDF pages.",
        )

        self.datacell.refresh_from_db()
        self.assertEqual(self.datacell.sources.count(), len(annotations))

    def test_ground_pdf_is_idempotent(self):
        """Re-running PDF grounding must not duplicate TOKEN_LABEL annotations."""
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        first = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )
        self.assertGreater(len(first), 0)
        first_count = Annotation.objects.filter(document=self.document).count()
        first_ids = sorted(a.id for a in first)

        second = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )
        second_count = Annotation.objects.filter(document=self.document).count()
        second_ids = sorted(a.id for a in second)

        self.assertEqual(first_count, second_count)
        self.assertEqual(first_ids, second_ids)

        self.datacell.refresh_from_db()
        self.assertEqual(self.datacell.sources.count(), first_count)

    def test_ground_pdf_skips_when_page_is_none(self):
        """If PlasmaPDF returns page=None, the annotation must be skipped.

        Regression for the silent ``page=1`` fallback bug: a missing page
        on a multi-page PDF should result in *no* annotation being saved
        rather than a structurally incorrect one anchored to page 1.
        """
        from unittest.mock import patch

        from opencontractserver.annotations.models import Annotation
        from opencontractserver.constants.annotations import OC_EXTRACT_SOURCE_LABEL
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        def stub_create(self, span_annotation):
            # Mimic PlasmaPDF's payload but force page=None so the grounding
            # pipeline must take the skip-rather-than-fallback path.
            return {"page": None, "rawText": "stub", "annotation_json": {}}

        with patch(
            "plasmapdf.models.PdfDataLayer.PdfDataLayer."
            "create_opencontract_annotation_from_span",
            new=stub_create,
        ):
            annotations = async_to_sync(ground_extraction_to_annotations)(
                datacell=self.datacell,
                document=self.document,
                corpus=self.corpus,
                user_id=self.user.id,
                enable_fuzzy=False,
            )

        self.assertEqual(
            len(annotations),
            0,
            "Annotations with page=None must be skipped, not saved on page 1.",
        )
        # And nothing should have been persisted to the database either.
        self.assertEqual(
            Annotation.objects.filter(
                document=self.document,
                annotation_label__text=OC_EXTRACT_SOURCE_LABEL,
            ).count(),
            0,
        )

    def test_ground_pdf_separate_corpora_create_separate_annotations(self):
        """A document shared across two corpora must NOT collapse its
        grounding annotations into a single shared row.

        Regression for issue raised in PR review: ``corpus`` was previously
        only in ``defaults`` so the second corpus's grounding would silently
        return the first corpus's annotation, producing a ``datacell.sources``
        FK whose ``corpus`` mismatched the extract.  Fixing the lookup key
        to include ``corpus`` means each corpus now owns a distinct row
        with the correct FK.
        """
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.extracts.models import (
            Datacell,
            Extract,
        )
        from opencontractserver.utils.extraction_grounding import (
            ground_extraction_to_annotations,
        )

        # Re-add the document to a SECOND corpus so it lives in both.
        other_corpus = Corpus.objects.create(
            title="Second PDF Grounding Corpus", creator=self.user
        )
        other_corpus.add_document(document=self.document, user=self.user)

        # Build a parallel extract+datacell anchored to the OTHER corpus.
        other_extract = Extract.objects.create(
            name="Second PDF Extract",
            corpus=other_corpus,
            fieldset=self.fieldset,
            creator=self.user,
        )
        other_datacell = Datacell.objects.create(
            extract=other_extract,
            column=self.column,
            document=self.document,
            creator=self.user,
            data={"data": ["Acme Holdings", "Global Acquisitions"]},
        )

        first_corpus_annotations = async_to_sync(ground_extraction_to_annotations)(
            datacell=self.datacell,
            document=self.document,
            corpus=self.corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )
        second_corpus_annotations = async_to_sync(ground_extraction_to_annotations)(
            datacell=other_datacell,
            document=self.document,
            corpus=other_corpus,
            user_id=self.user.id,
            enable_fuzzy=False,
        )

        self.assertGreater(len(first_corpus_annotations), 0)
        self.assertGreater(len(second_corpus_annotations), 0)

        # The two corpora's grounding annotations must be DISJOINT.
        first_ids = {a.id for a in first_corpus_annotations}
        second_ids = {a.id for a in second_corpus_annotations}
        self.assertTrue(
            first_ids.isdisjoint(second_ids),
            "Annotations leaked between corpora — corpus is missing from "
            "the get_or_create lookup key.",
        )

        # Each annotation should point to its own corpus, not the other one.
        for annot in first_corpus_annotations:
            self.assertEqual(annot.corpus_id, self.corpus.id)
        for annot in second_corpus_annotations:
            self.assertEqual(annot.corpus_id, other_corpus.id)
