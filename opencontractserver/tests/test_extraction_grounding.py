"""
Tests for the extraction grounding pipeline.

Tests extract_groundable_strings (unit) and the full grounding pipeline
(integration with Django models).
"""

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase

from opencontractserver.utils.extraction_grounding import extract_groundable_strings


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
