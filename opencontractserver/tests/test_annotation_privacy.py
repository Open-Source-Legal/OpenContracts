"""
Test annotation privacy model with created_by_analysis and created_by_extract fields.
"""

import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.annotations.query_optimizer import AnnotationQueryOptimizer
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.extracts.models import Column, Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class AnnotationPrivacyTestCase(TestCase):
    """Test that annotations with created_by_* fields respect privacy rules."""

    def setUp(self):
        """Set up test data."""
        # Create users
        self.owner = User.objects.create_user(username="owner", password="test")
        self.viewer = User.objects.create_user(username="viewer", password="test")
        self.outsider = User.objects.create_user(username="outsider", password="test")

        # Create document (without file upload to avoid S3 issues in test)
        self.doc = Document.objects.create(
            title="Test Document",
            creator=self.owner,
            is_public=False,
            backend_lock=False,  # Ensure document is not locked
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.corpus.add_document(document=self.doc, user=self.owner)

        # Create DocumentPath to link document to corpus in dual-tree versioning
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test_document.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.owner,
        )

        # Create label
        self.label = AnnotationLabel.objects.create(
            text="Test Label", label_type=TOKEN_LABEL, creator=self.owner
        )

        # Setup analyzer infrastructure
        self.gremlin = GremlinEngine.objects.create(
            url="http://test-gremlin:8000", creator=self.owner
        )
        self.analyzer = Analyzer.objects.create(
            id="TEST.ANALYZER",
            host_gremlin=self.gremlin,
            creator=self.owner,
            description="Test analyzer",
        )

        # Create analysis
        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            is_public=False,
        )
        self.analysis.analyzed_documents.add(self.doc)

        # Create extract
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset", creator=self.owner
        )
        self.column = Column.objects.create(
            name="Test Column",
            fieldset=self.fieldset,
            creator=self.owner,
            output_type="string",
        )
        self.extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )
        self.extract.documents.add(self.doc)

        # Set permissions
        # Owner gets full permissions to their created objects
        set_permissions_for_obj_to_user(
            self.owner,
            self.doc,
            [
                PermissionTypes.READ,
                PermissionTypes.CREATE,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
            ],
        )
        set_permissions_for_obj_to_user(
            self.owner,
            self.corpus,
            [
                PermissionTypes.READ,
                PermissionTypes.CREATE,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
            ],
        )

        # Viewer can see doc and corpus but NOT analysis/extract
        set_permissions_for_obj_to_user(self.viewer, self.doc, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            self.viewer, self.corpus, [PermissionTypes.READ]
        )

    def test_annotation_without_created_by_is_visible(self):
        """Test that regular annotations without created_by fields are visible."""
        # Create a regular annotation
        annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Regular annotation",
        )

        # Viewer should see it (has doc and corpus permissions)
        visible_annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=self.viewer, corpus_id=self.corpus.id
        )

        self.assertIn(annotation, visible_annotations)

    def test_analysis_created_annotation_is_private(self):
        """Test that annotations created by analysis are private to that analysis."""
        # Create an annotation created by the analysis
        # Note: analysis field is None so it appears in manual mode queries
        # Only created_by_analysis is set for privacy enforcement
        private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            # analysis=None (implicit) - allows visibility in manual mode
            created_by_analysis=self.analysis,  # Mark as created by analysis for privacy
            creator=self.owner,
            page=1,
            raw_text="Private analysis annotation",
        )

        # Viewer should NOT see it (no analysis permission)
        visible_annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=self.viewer, corpus_id=self.corpus.id
        )

        self.assertNotIn(private_annotation, visible_annotations)

        # Owner should see it (has analysis permission as creator)
        owner_annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=self.owner, corpus_id=self.corpus.id
        )

        self.assertIn(private_annotation, owner_annotations)

    def test_extract_created_annotation_is_private(self):
        """Test that annotations created by extract are private to that extract."""
        # Create an annotation created by the extract
        private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            created_by_extract=self.extract,  # Mark as created by extract
            creator=self.owner,
            page=1,
            raw_text="Private extract annotation",
        )

        # Viewer should NOT see it (no extract permission)
        visible_annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=self.viewer, corpus_id=self.corpus.id
        )

        self.assertNotIn(private_annotation, visible_annotations)

        # Owner should see it (has extract permission as creator)
        owner_annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=self.owner, corpus_id=self.corpus.id
        )

        self.assertIn(private_annotation, owner_annotations)

    def test_cannot_set_both_created_by_fields(self):
        """Test that an annotation cannot be created by both analysis and extract."""
        annotation = Annotation(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            created_by_analysis=self.analysis,
            created_by_extract=self.extract,  # Both fields set - should fail!
            creator=self.owner,
            page=1,
            raw_text="Invalid annotation",
        )
        with self.assertRaises(ValidationError):
            annotation.full_clean()  # This should raise ValidationError

    def test_granting_analysis_permission_reveals_annotations(self):
        """Test that granting analysis permission reveals its private annotations."""
        # Create private annotation (analysis=None for manual mode visibility)
        private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            # analysis=None (implicit) - allows visibility in manual mode
            created_by_analysis=self.analysis,  # Privacy field
            creator=self.owner,
            page=1,
            raw_text="Private analysis annotation",
        )

        # Initially viewer can't see it
        visible = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=self.viewer, corpus_id=self.corpus.id
        )
        self.assertNotIn(private_annotation, visible)

        # Grant analysis permission to viewer
        set_permissions_for_obj_to_user(
            self.viewer, self.analysis, [PermissionTypes.READ]
        )

        # Now viewer should see it
        visible = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id, user=self.viewer, corpus_id=self.corpus.id
        )
        self.assertIn(private_annotation, visible)

    def test_structural_annotations_always_visible(self):
        """Test that structural annotations are always visible regardless of created_by."""
        # Create a structural annotation created by analysis
        # analysis=None so it appears in manual mode, but has privacy via created_by_analysis
        structural_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            # analysis=None (implicit) - allows visibility in manual mode
            created_by_analysis=self.analysis,  # Privacy field (but structural trumps this)
            structural=True,  # Mark as structural - makes it visible regardless of privacy
            creator=self.owner,
            page=1,
            raw_text="Structural annotation",
        )

        # Viewer should see it even without analysis permission (structural trumps privacy)
        visible_annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.doc.id,
            user=self.viewer,
            corpus_id=self.corpus.id,
            structural=True,
        )

        self.assertIn(structural_annotation, visible_annotations)
