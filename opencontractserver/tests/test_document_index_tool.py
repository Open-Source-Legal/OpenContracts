from __future__ import annotations

import json
import logging

from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from config.graphql.serializers import AnnotationSerializer
from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL, Annotation
from opencontractserver.constants.annotations import OC_SECTION_LABEL
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools import (
    IndexEntryItem,
    create_document_index,
)
from opencontractserver.tests.fixtures import (
    SAMPLE_PAWLS_FILE_ONE_PATH,
    SAMPLE_TXT_FILE_ONE_PATH,
)
from opencontractserver.types.dicts import OpenContractsAnnotationPythonType
from opencontractserver.users.models import User
from opencontractserver.utils.importing import import_annotations

logger = logging.getLogger(__name__)


class TestCreateDocumentIndexPDF(TestCase):
    """Tests for create_document_index with PDF documents."""

    user: User
    corpus: Corpus
    doc: Document

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user("idx_user", password="pass")
        cls.corpus = Corpus.objects.create(title="Index Corpus", creator=cls.user)

        pawls_json = SAMPLE_PAWLS_FILE_ONE_PATH.read_text()
        pawls_tokens = json.loads(pawls_json)

        cls.doc = Document.objects.create(
            creator=cls.user,
            title="PDF Doc",
            file_type="application/pdf",
            page_count=len(pawls_tokens),
            processing_started=timezone.now(),
        )
        cls.doc.pawls_parse_file.save(
            SAMPLE_PAWLS_FILE_ONE_PATH.name, ContentFile(pawls_json.encode())
        )
        cls.doc.save()
        cls.doc, _, _ = cls.corpus.add_document(document=cls.doc, user=cls.user)

    def setUp(self):
        self.doc.refresh_from_db()
        storage = self.doc.pawls_parse_file.storage
        name = self.doc.pawls_parse_file.name
        assert name is not None
        if not storage.exists(name):
            self.doc.pawls_parse_file.save(
                name,
                ContentFile(SAMPLE_PAWLS_FILE_ONE_PATH.read_bytes()),
            )

    def test_create_flat_index(self):
        """Root-level entries produce TOKEN_LABEL annotations with OC_SECTION label."""
        entries: list[IndexEntryItem] = [
            {
                "title": "License Agreement",
                "exact_string": "EXCLUSIVE LICENSE AND PRODUCT DEVELOPMENT AGREEMENT",
                "long_description": "The main agreement heading.",
                "parent_index": -1,
            },
            {
                "title": "Execution Date",
                "exact_string": "Execution Date",
                "parent_index": -1,
            },
        ]
        pks = create_document_index(
            entries,
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )
        self.assertEqual(len(pks), 2)

        annotations = Annotation.objects.filter(id__in=pks)
        for ann in annotations:
            self.assertEqual(ann.annotation_label.text, OC_SECTION_LABEL)
            self.assertEqual(ann.annotation_type, TOKEN_LABEL)
            self.assertEqual(ann.document_id, self.doc.id)
            self.assertFalse(ann.structural)

        # First entry should have long_description set
        first = Annotation.objects.get(pk=pks[0])
        self.assertEqual(first.raw_text, "License Agreement")
        self.assertEqual(first.long_description, "The main agreement heading.")
        self.assertIsNone(first.parent)

        # Second entry should have None long_description (not provided)
        second = Annotation.objects.get(pk=pks[1])
        self.assertEqual(second.raw_text, "Execution Date")
        self.assertIsNone(second.long_description)
        self.assertIsNone(second.parent)

    def test_create_hierarchical_index(self):
        """Parent wiring produces correct parent FK relationships."""
        entries: list[IndexEntryItem] = [
            {
                "title": "Agreement",
                "exact_string": "EXCLUSIVE LICENSE AND PRODUCT DEVELOPMENT AGREEMENT",
                "parent_index": -1,
            },
            {
                "title": "Definitions",
                "exact_string": "Execution Date",
                "parent_index": 0,
            },
        ]
        pks = create_document_index(
            entries,
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )
        self.assertEqual(len(pks), 2)

        parent = Annotation.objects.get(pk=pks[0])
        child = Annotation.objects.get(pk=pks[1])
        self.assertIsNone(parent.parent)
        self.assertEqual(child.parent_id, parent.id)

    def test_string_not_found_raises(self):
        """ValueError raised when exact_string is not in document text."""
        entries: list[IndexEntryItem] = [
            {
                "title": "Ghost Section",
                "exact_string": "THIS_STRING_DEFINITELY_DOES_NOT_EXIST_IN_THE_DOC_xyz789",
                "parent_index": -1,
            },
        ]
        with self.assertRaises(ValueError, msg="Exact string not found"):
            create_document_index(
                entries,
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

    def test_parent_index_out_of_range_raises(self):
        """ValueError raised when parent_index exceeds entries length."""
        entries: list[IndexEntryItem] = [
            {
                "title": "Section A",
                "exact_string": "Agreement",
                "parent_index": 5,  # Out of range
            },
        ]
        with self.assertRaises(ValueError, msg="out of range"):
            create_document_index(
                entries,
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

    def test_self_referential_parent_raises(self):
        """ValueError raised when entry references itself as parent."""
        entries: list[IndexEntryItem] = [
            {
                "title": "Self Parent",
                "exact_string": "Agreement",
                "parent_index": 0,
            },
        ]
        with self.assertRaises(ValueError, msg="references itself"):
            create_document_index(
                entries,
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

    def test_multi_node_cycle_raises(self):
        """ValueError raised when entries form a cycle (A->B, B->A)."""
        entries: list[IndexEntryItem] = [
            {
                "title": "Section A",
                "exact_string": "Agreement",
                "parent_index": 1,
            },
            {
                "title": "Section B",
                "exact_string": "Execution Date",
                "parent_index": 0,
            },
        ]
        with self.assertRaises(ValueError, msg="Cycle detected"):
            create_document_index(
                entries,
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

    def test_nonexistent_document_raises(self):
        """ValueError raised for a document ID that doesn't exist."""
        with self.assertRaises(ValueError, msg="does not exist"):
            create_document_index(
                [{"title": "X", "exact_string": "Y", "parent_index": -1}],
                document_id=999999,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

    def test_document_not_in_corpus_raises(self):
        """ValueError raised when document exists but is not in the corpus."""
        other_corpus = Corpus.objects.create(title="Other Corpus", creator=self.user)
        with self.assertRaises(ValueError, msg="not linked to corpus"):
            create_document_index(
                [{"title": "X", "exact_string": "Y", "parent_index": -1}],
                document_id=self.doc.id,
                corpus_id=other_corpus.id,
                creator_id=self.user.id,
            )

    def test_unsupported_file_type_raises(self):
        """ValueError raised for unsupported file types."""
        doc = Document.objects.create(
            creator=self.user,
            title="Image Doc",
            file_type="image/png",
            processing_started=timezone.now(),
        )
        doc, _, _ = self.corpus.add_document(document=doc, user=self.user)
        with self.assertRaises(ValueError, msg="Unsupported file_type"):
            create_document_index(
                [{"title": "X", "exact_string": "Y", "parent_index": -1}],
                document_id=doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

    def test_empty_file_type_raises(self):
        """ValueError raised when file_type is empty string."""
        doc = Document.objects.create(
            creator=self.user,
            title="No Type Doc",
            file_type="",
            processing_started=timezone.now(),
        )
        doc, _, _ = self.corpus.add_document(document=doc, user=self.user)
        with self.assertRaises(ValueError, msg="no file_type"):
            create_document_index(
                [{"title": "X", "exact_string": "Y", "parent_index": -1}],
                document_id=doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

    def test_transaction_rollback_on_failure(self):
        """All annotations rolled back if one entry fails."""
        entries: list[IndexEntryItem] = [
            {
                "title": "Good Entry",
                "exact_string": "Agreement",
                "parent_index": -1,
            },
            {
                "title": "Bad Entry",
                "exact_string": "NONEXISTENT_STRING_abc123",
                "parent_index": -1,
            },
        ]
        before_count = Annotation.objects.count()
        with self.assertRaises(ValueError):
            create_document_index(
                entries,
                document_id=self.doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )
        # No annotations should have been created
        self.assertEqual(Annotation.objects.count(), before_count)


class TestCreateDocumentIndexText(TestCase):
    """Tests for create_document_index with text documents."""

    user: User
    corpus: Corpus
    doc: Document

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user("idx_txt_user", password="pass")
        cls.corpus = Corpus.objects.create(title="Text Index Corpus", creator=cls.user)

        text_content = SAMPLE_TXT_FILE_ONE_PATH.read_text()
        cls.doc = Document.objects.create(
            creator=cls.user,
            title="Text Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        cls.doc.txt_extract_file.save(
            SAMPLE_TXT_FILE_ONE_PATH.name, ContentFile(text_content.encode())
        )
        cls.doc.save()
        cls.doc, _, _ = cls.corpus.add_document(document=cls.doc, user=cls.user)

    def setUp(self):
        self.doc.refresh_from_db()
        storage = self.doc.txt_extract_file.storage
        name = self.doc.txt_extract_file.name
        assert name is not None
        if not storage.exists(name):
            self.doc.txt_extract_file.save(
                name,
                ContentFile(SAMPLE_TXT_FILE_ONE_PATH.read_bytes()),
            )

    def test_create_text_index(self):
        """Text document index creates SPAN_LABEL annotations."""
        entries: list[IndexEntryItem] = [
            {
                "title": "License Section",
                "exact_string": "EXCLUSIVE LICENSE AND PRODUCT DEVELOPMENT AGREEMENT",
                "long_description": "Opening section of the agreement.",
                "parent_index": -1,
            },
        ]
        pks = create_document_index(
            entries,
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )
        self.assertEqual(len(pks), 1)

        ann = Annotation.objects.get(pk=pks[0])
        self.assertEqual(ann.annotation_type, SPAN_LABEL)
        self.assertEqual(ann.annotation_label.text, OC_SECTION_LABEL)
        self.assertEqual(ann.raw_text, "License Section")
        self.assertEqual(ann.long_description, "Opening section of the agreement.")
        self.assertEqual(ann.page, 1)
        self.assertFalse(ann.structural)

        # JSON should contain start/end offsets
        self.assertIn("start", ann.json)
        self.assertIn("end", ann.json)
        self.assertGreater(ann.json["end"], ann.json["start"])

    def test_text_hierarchy(self):
        """Text document hierarchy uses parent FK correctly."""
        entries: list[IndexEntryItem] = [
            {
                "title": "Root",
                "exact_string": "EXCLUSIVE LICENSE",
                "parent_index": -1,
            },
            {
                "title": "Child",
                "exact_string": "Execution Date",
                "parent_index": 0,
            },
        ]
        pks = create_document_index(
            entries,
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )
        child = Annotation.objects.get(pk=pks[1])
        self.assertEqual(child.parent_id, pks[0])


class TestUpdateAnnotationLongDescription(TestCase):
    """Test that long_description can be updated via AnnotationSerializer (UpdateAnnotation path)."""

    user: User
    corpus: Corpus
    doc: Document

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user("idx_update_user", password="pass")
        cls.corpus = Corpus.objects.create(title="Update Test Corpus", creator=cls.user)

        pawls_json = SAMPLE_PAWLS_FILE_ONE_PATH.read_text()

        cls.doc = Document.objects.create(
            creator=cls.user,
            title="Update Test Doc",
            file_type="application/pdf",
            page_count=len(json.loads(pawls_json)),
            processing_started=timezone.now(),
        )
        cls.doc.pawls_parse_file.save(
            SAMPLE_PAWLS_FILE_ONE_PATH.name, ContentFile(pawls_json.encode())
        )
        cls.doc.save()
        cls.doc, _, _ = cls.corpus.add_document(document=cls.doc, user=cls.user)

    def setUp(self):
        self.doc.refresh_from_db()
        storage = self.doc.pawls_parse_file.storage
        name = self.doc.pawls_parse_file.name
        assert name is not None
        if not storage.exists(name):
            self.doc.pawls_parse_file.save(
                name,
                ContentFile(SAMPLE_PAWLS_FILE_ONE_PATH.read_bytes()),
            )

    def test_update_long_description_via_serializer(self):
        """Partial update via AnnotationSerializer persists long_description."""
        pks = create_document_index(
            [
                {
                    "title": "Original",
                    "exact_string": "Agreement",
                    "long_description": "Initial description.",
                    "parent_index": -1,
                }
            ],
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )
        ann = Annotation.objects.get(pk=pks[0])
        self.assertEqual(ann.long_description, "Initial description.")

        # Partial update — mirrors what UpdateAnnotation (DRFMutation) does
        serializer = AnnotationSerializer(
            ann, data={"long_description": "Updated description."}, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        ann.refresh_from_db()
        self.assertEqual(ann.long_description, "Updated description.")

    def test_clear_long_description_via_serializer(self):
        """Setting long_description to empty string clears it."""
        pks = create_document_index(
            [
                {
                    "title": "Clearable",
                    "exact_string": "Execution Date",
                    "long_description": "Will be cleared.",
                    "parent_index": -1,
                }
            ],
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )
        ann = Annotation.objects.get(pk=pks[0])
        serializer = AnnotationSerializer(
            ann, data={"long_description": ""}, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        ann.refresh_from_db()
        self.assertEqual(ann.long_description, "")


class TestLongDescriptionExportImportRoundTrip(TestCase):
    """Test that long_description survives an export→import cycle."""

    user: User
    corpus: Corpus
    doc: Document

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user("idx_rt_user", password="pass")
        cls.corpus = Corpus.objects.create(title="Round-trip Corpus", creator=cls.user)

        text_content = SAMPLE_TXT_FILE_ONE_PATH.read_text()
        cls.doc = Document.objects.create(
            creator=cls.user,
            title="RT Text Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        cls.doc.txt_extract_file.save(
            SAMPLE_TXT_FILE_ONE_PATH.name, ContentFile(text_content.encode())
        )
        cls.doc.save()
        cls.doc, _, _ = cls.corpus.add_document(document=cls.doc, user=cls.user)

    def setUp(self):
        self.doc.refresh_from_db()
        storage = self.doc.txt_extract_file.storage
        name = self.doc.txt_extract_file.name
        assert name is not None
        if not storage.exists(name):
            self.doc.txt_extract_file.save(
                name,
                ContentFile(SAMPLE_TXT_FILE_ONE_PATH.read_bytes()),
            )

    def test_round_trip_preserves_long_description(self):
        """Export an annotation with long_description, import it, verify field is preserved."""
        from opencontractserver.annotations.models import AnnotationLabel

        pks = create_document_index(
            [
                {
                    "title": "Section One",
                    "exact_string": "EXCLUSIVE LICENSE",
                    "long_description": "Markdown **summary** of the section.",
                    "parent_index": -1,
                }
            ],
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )
        original = Annotation.objects.get(pk=pks[0])

        # Simulate export format (mirrors export_v2.py)
        exported: OpenContractsAnnotationPythonType = {
            "id": str(original.id),
            "annotationLabel": original.annotation_label.text,
            "rawText": original.raw_text or "",
            "page": original.page or 0,
            "annotation_json": original.json or {},
            "parent_id": None,
            "annotation_type": original.annotation_type or "",
            "structural": False,
            "long_description": original.long_description,
        }

        # Delete the original so the import creates a fresh one
        original.delete()

        # Build label lookup as import_annotations expects
        label_lookup = {
            original.annotation_label.text: AnnotationLabel.objects.get(
                pk=original.annotation_label_id
            )
        }

        # Import
        old_to_new = import_annotations(
            annotations_data=[exported],
            doc_obj=self.doc,
            corpus_obj=self.corpus,
            label_lookup=label_lookup,
            label_type=SPAN_LABEL,
            user_id=self.user.id,
        )

        # Verify round-tripped annotation
        new_pk = list(old_to_new.values())[0]
        reimported = Annotation.objects.get(pk=new_pk)
        self.assertEqual(
            reimported.long_description, "Markdown **summary** of the section."
        )
        self.assertEqual(reimported.raw_text, "Section One")

    def test_round_trip_without_long_description(self):
        """Annotations without long_description import with None (backward compat)."""
        from opencontractserver.annotations.models import AnnotationLabel

        pks = create_document_index(
            [
                {
                    "title": "No Desc",
                    "exact_string": "Execution Date",
                    "parent_index": -1,
                }
            ],
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )
        original = Annotation.objects.get(pk=pks[0])
        self.assertIsNone(original.long_description)

        # Export without long_description key (old format)
        exported: OpenContractsAnnotationPythonType = {
            "id": str(original.id),
            "annotationLabel": original.annotation_label.text,
            "rawText": original.raw_text or "",
            "page": original.page or 0,
            "annotation_json": original.json or {},
            "parent_id": None,
            "annotation_type": original.annotation_type or "",
            "structural": False,
            # No long_description key — simulates pre-feature export
        }

        original.delete()

        label_lookup = {
            original.annotation_label.text: AnnotationLabel.objects.get(
                pk=original.annotation_label_id
            )
        }

        old_to_new = import_annotations(
            annotations_data=[exported],
            doc_obj=self.doc,
            corpus_obj=self.corpus,
            label_lookup=label_lookup,
            label_type=SPAN_LABEL,
            user_id=self.user.id,
        )

        new_pk = list(old_to_new.values())[0]
        reimported = Annotation.objects.get(pk=new_pk)
        self.assertIsNone(reimported.long_description)
