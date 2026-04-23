# Copyright (C) 2024 - John Scrudato
import logging

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from django.test.utils import override_settings

from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.documents.models import Document
from opencontractserver.tasks.doc_tasks import ingest_doc
from opencontractserver.tests.fixtures import SAMPLE_TXT_FILE_ONE_PATH

User = get_user_model()

logger = logging.getLogger(__name__)


class TxtIngestorTestCase(TestCase):
    def setUp(self):
        # Setup a test user
        with transaction.atomic():
            self.user = User.objects.create_user(username="bob", password="12345678")

        # Create a test document with a text file
        with SAMPLE_TXT_FILE_ONE_PATH.open("rb") as f:
            txt_content = f.read()

        txt_file = ContentFile(txt_content, name="test.txt")

        with transaction.atomic():
            self.doc = Document.objects.create(
                creator=self.user,
                title="Test Doc",
                description="Sample Text File",
                custom_meta={},
                txt_extract_file=txt_file,
                file_type="text/plain",
                backend_lock=True,
            )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_ingest_txt(self):
        # Run ingest pipeline synchronously
        ingest_doc.si(user_id=self.user.id, doc_id=self.doc.id).apply()

        # Check if the SENTENCE label was created
        sentence_label = AnnotationLabel.objects.filter(
            text="SENTENCE", creator=self.user, label_type="SPAN_LABEL", read_only=True
        ).first()
        self.assertIsNotNone(sentence_label)

        # Refresh the document from the database to get the structural_annotation_set
        self.doc.refresh_from_db()

        # Check that a structural annotation set was created
        self.assertIsNotNone(
            self.doc.structural_annotation_set,
            "Document should have a structural_annotation_set after ingestion",
        )

        # Check if annotations were created in the structural annotation set
        # (structural annotations are no longer linked directly to the document)
        annotations = self.doc.structural_annotation_set.structural_annotations.all()
        self.assertGreater(
            annotations.count(),
            0,
            "Should have structural annotations in the set",
        )

        # Check properties of the first annotation
        first_annotation = annotations.first()
        self.assertEqual(first_annotation.annotation_label, sentence_label)
        self.assertEqual(first_annotation.annotation_type, "SPAN_LABEL")
        self.assertTrue(first_annotation.structural)
        self.assertEqual(first_annotation.creator, self.user)

        # Check if the annotation JSON contains start and end
        self.assertIn("start", first_annotation.json)
        self.assertIn("end", first_annotation.json)

        # Verify that all annotations have non-empty raw_text
        for annotation in annotations:
            self.assertTrue(annotation.raw_text.strip())

        logger.info(f"Created {annotations.count()} sentence annotations")

    def test_parser_supports_paragraph_chunker_via_kwargs(self):
        """Benchmark-style override: swap sentence → paragraph chunking.

        Exercises the flexible chunking plumbing introduced for issue #1348:
        the TxtParser accepts a ``chunkers=[...]`` kwarg that overrides the
        default sentence-level strategy for a single parse invocation, so
        benchmark runners can compare retrieval granularities without
        mutating PipelineSettings.
        """
        from opencontractserver.pipeline.parsers.oc_text_parser import TxtParser
        from opencontractserver.pipeline.parsers.text_chunkers import (
            PARAGRAPH_CHUNK_LABEL,
        )

        parser = TxtParser()
        parsed = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            chunkers=[{"name": "paragraph"}],
        )

        self.assertIsNotNone(parsed)
        labelled = parsed["labelled_text"]
        self.assertGreater(len(labelled), 0, "Paragraph chunker produced no chunks")
        self.assertTrue(
            all(ann["annotationLabel"] == PARAGRAPH_CHUNK_LABEL for ann in labelled),
            "All override-produced annotations should carry the PARAGRAPH label",
        )

    def test_parser_supports_stacked_chunkers(self):
        """Stacking two chunkers produces annotations under both labels."""
        from opencontractserver.pipeline.parsers.oc_text_parser import TxtParser
        from opencontractserver.pipeline.parsers.text_chunkers import (
            PARAGRAPH_CHUNK_LABEL,
            SLIDING_WINDOW_CHUNK_LABEL,
        )

        parser = TxtParser()
        parsed = parser.parse_document(
            user_id=self.user.id,
            doc_id=self.doc.id,
            chunkers=[
                {"name": "paragraph"},
                {"name": "sliding_window", "window_size": 800, "overlap": 100},
            ],
        )

        self.assertIsNotNone(parsed)
        labels = {ann["annotationLabel"] for ann in parsed["labelled_text"]}
        self.assertIn(PARAGRAPH_CHUNK_LABEL, labels)
        self.assertIn(SLIDING_WINDOW_CHUNK_LABEL, labels)
