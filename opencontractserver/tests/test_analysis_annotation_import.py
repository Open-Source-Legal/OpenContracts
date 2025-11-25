"""
Test that analysis imports properly set the created_by_analysis field.
"""

import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.utils.analyzer import import_annotations_from_analysis

User = get_user_model()
logger = logging.getLogger(__name__)


class AnalysisAnnotationImportTestCase(TestCase):
    """Test that annotations imported from analysis have created_by_analysis set."""

    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(username="analyst", password="test")

        # Create document
        self.doc = Document.objects.create(
            title="Test Document",
            creator=self.user,
            is_public=False,
            backend_lock=False,
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.user, is_public=False
        )
        self.corpus.add_document(document=self.doc, user=self.user)

        # Create DocumentPath to link document to corpus in dual-tree versioning
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test_document.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Setup analyzer infrastructure
        self.gremlin = GremlinEngine.objects.create(
            url="http://test-gremlin:8000", creator=self.user
        )
        self.analyzer = Analyzer.objects.create(
            id="TEST.ANALYZER",
            host_gremlin=self.gremlin,
            creator=self.user,
            description="Test analyzer",
        )

        # Create analysis
        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.user,
            is_public=False,
        )
        self.analysis.analyzed_documents.add(self.doc)

        # Create a label set and label for testing
        self.label_set = LabelSet.objects.create(
            title="Test Label Set", creator=self.user
        )
        self.label = AnnotationLabel.objects.create(
            text="Test Label", label_type=TOKEN_LABEL, creator=self.user
        )

    @patch("opencontractserver.utils.analyzer.install_labels_for_analyzer")
    @patch("opencontractserver.utils.permissioning.set_permissions_for_obj_to_user")
    def test_import_sets_created_by_analysis(self, mock_set_perms, mock_install_labels):
        """Test that imported annotations have created_by_analysis set."""

        # Mock the label installation to return a simple mapping
        mock_install_labels.return_value = {
            "test_doc_label": self.label.id,
            "test_span_label": self.label.id,
        }

        # Prepare analysis results
        analysis_results = {
            "doc_labels": {
                "label1": {"id": "test_doc_label", "name": "Test Doc Label"}
            },
            "text_labels": {
                "label2": {"id": "test_span_label", "name": "Test Span Label"}
            },
            "label_set": {"id": "test_set", "name": "Test Set"},
            "annotated_docs": {
                str(self.doc.id): {
                    "doc_labels": ["test_doc_label"],
                    "labelled_text": [
                        {
                            "annotationLabel": "test_span_label",
                            "rawText": "Test text",
                            "page": 1,
                            "annotation_json": {"test": "data"},
                        }
                    ],
                }
            },
        }

        # Import annotations
        result = import_annotations_from_analysis(
            analysis_id=self.analysis.id,
            creator_id=self.user.id,
            analysis_results=analysis_results,
        )

        # Verify import succeeded
        self.assertTrue(result)

        # Check that annotations were created with created_by_analysis set
        annotations = Annotation.objects.filter(analysis=self.analysis)
        self.assertEqual(annotations.count(), 2)  # One doc label, one span label

        for annotation in annotations:
            # Verify the created_by_analysis field is set
            self.assertEqual(annotation.created_by_analysis_id, self.analysis.id)
            # Verify the annotation is linked to the analysis
            self.assertEqual(annotation.analysis_id, self.analysis.id)

    def test_created_by_analysis_makes_annotations_private(self):
        """Test that annotations with created_by_analysis are private."""
        # Create another user who shouldn't see the annotations
        other_user = User.objects.create_user(username="other", password="test")

        # Create an annotation with created_by_analysis
        # analysis=None so it appears in manual mode queries, but with privacy via created_by_analysis
        private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            # analysis=None (implicit) - allows visibility in manual mode
            created_by_analysis=self.analysis,  # Privacy field
            creator=self.user,
            page=1,
            raw_text="Private annotation",
        )

        # Import the query optimizer to test visibility
        from opencontractserver.annotations.query_optimizer import (
            AnnotationQueryOptimizer,
        )
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        # Give other_user permission to doc and corpus but NOT analysis
        set_permissions_for_obj_to_user(other_user, self.doc, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(other_user, self.corpus, [PermissionTypes.READ])

        # Other user should NOT see the annotation
        visible_annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=other_user, corpus_id=self.corpus.id
        )
        self.assertNotIn(private_annotation, visible_annotations)

        # Original user (with analysis access) should see it
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.READ])

        owner_annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=self.user, corpus_id=self.corpus.id
        )
        self.assertIn(private_annotation, owner_annotations)
