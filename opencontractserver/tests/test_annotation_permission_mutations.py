"""
Test that annotation mutations properly respect the privacy model.
"""

import logging

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class AnnotationMutationPermissionTestCase(TestCase):
    """Test that annotation mutations respect the privacy model."""

    def setUp(self):
        """Set up test data."""
        # Create users
        self.owner = User.objects.create_user(username="owner", password="test")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test"
        )
        self.outsider = User.objects.create_user(username="outsider", password="test")

        # Create document
        self.doc = Document.objects.create(
            title="Test Document",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.corpus.add_document(document=self.doc, user=self.owner)

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
        self.extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )
        self.extract.documents.add(self.doc)

        # Set permissions
        # Owner gets full permissions
        set_permissions_for_obj_to_user(self.owner, self.doc, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(
            self.owner, self.analysis, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.extract, [PermissionTypes.CRUD]
        )

        # Collaborator gets doc+corpus but NOT analysis/extract
        set_permissions_for_obj_to_user(
            self.collaborator, self.doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.CRUD]
        )

        # Outsider gets nothing

    def test_user_permission_for_regular_annotation(self):
        """Test that regular annotations follow document+corpus permissions."""
        # Create a regular annotation
        annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Regular annotation",
        )

        # Owner should have full permissions
        self.assertTrue(
            user_has_permission_for_obj(self.owner, annotation, PermissionTypes.READ)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.owner, annotation, PermissionTypes.UPDATE)
        )
        self.assertTrue(
            user_has_permission_for_obj(self.owner, annotation, PermissionTypes.DELETE)
        )

        # Collaborator should have full permissions (has doc+corpus)
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator, annotation, PermissionTypes.READ
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator, annotation, PermissionTypes.UPDATE
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator, annotation, PermissionTypes.DELETE
            )
        )

        # Outsider should have no permissions
        self.assertFalse(
            user_has_permission_for_obj(self.outsider, annotation, PermissionTypes.READ)
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, annotation, PermissionTypes.UPDATE
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, annotation, PermissionTypes.DELETE
            )
        )

    def test_user_permission_for_analysis_created_annotation(self):
        """Test that analysis-created annotations require analysis permission."""
        # Create an annotation marked as created by analysis
        private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            analysis=self.analysis,
            created_by_analysis=self.analysis,  # Mark as private to analysis
            creator=self.owner,
            page=1,
            raw_text="Private analysis annotation",
        )

        # Owner should have permissions (has analysis permission)
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner, private_annotation, PermissionTypes.READ
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner, private_annotation, PermissionTypes.UPDATE
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner, private_annotation, PermissionTypes.DELETE
            )
        )

        # Collaborator should have NO permissions (no analysis permission)
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.READ
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.UPDATE
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.DELETE
            )
        )

        # Outsider should have no permissions
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, private_annotation, PermissionTypes.READ
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, private_annotation, PermissionTypes.UPDATE
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, private_annotation, PermissionTypes.DELETE
            )
        )

    def test_user_permission_for_extract_created_annotation(self):
        """Test that extract-created annotations require extract permission."""
        # Create an annotation marked as created by extract
        private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            created_by_extract=self.extract,  # Mark as private to extract
            creator=self.owner,
            page=1,
            raw_text="Private extract annotation",
        )

        # Owner should have permissions (has extract permission)
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner, private_annotation, PermissionTypes.READ
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner, private_annotation, PermissionTypes.UPDATE
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner, private_annotation, PermissionTypes.DELETE
            )
        )

        # Collaborator should have NO permissions (no extract permission)
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.READ
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.UPDATE
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.DELETE
            )
        )

        # Outsider should have no permissions
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, private_annotation, PermissionTypes.READ
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, private_annotation, PermissionTypes.UPDATE
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, private_annotation, PermissionTypes.DELETE
            )
        )

    def test_structural_annotation_is_read_only(self):
        """Test that structural annotations are always read-only."""
        # Create a structural annotation
        structural = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            structural=True,  # Mark as structural
            creator=self.owner,
            page=1,
            raw_text="Structural annotation",
        )

        # Owner should have READ but NOT write permissions
        self.assertTrue(
            user_has_permission_for_obj(self.owner, structural, PermissionTypes.READ)
        )
        self.assertFalse(
            user_has_permission_for_obj(self.owner, structural, PermissionTypes.UPDATE)
        )
        self.assertFalse(
            user_has_permission_for_obj(self.owner, structural, PermissionTypes.DELETE)
        )

        # Collaborator should have READ but NOT write permissions
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator, structural, PermissionTypes.READ
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, structural, PermissionTypes.UPDATE
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, structural, PermissionTypes.DELETE
            )
        )

    def test_structural_annotation_with_privacy_still_visible(self):
        """Test that structural annotations bypass privacy rules for reading."""
        # Create a structural annotation with privacy field
        structural = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            analysis=self.analysis,
            created_by_analysis=self.analysis,  # Private to analysis
            structural=True,  # BUT structural
            creator=self.owner,
            page=1,
            raw_text="Structural private annotation",
        )

        # Collaborator should be able to READ (structural bypasses privacy)
        # but NOT write (structural is always read-only)
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator, structural, PermissionTypes.READ
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, structural, PermissionTypes.UPDATE
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, structural, PermissionTypes.DELETE
            )
        )

    def test_granting_analysis_permission_reveals_annotations(self):
        """Test that granting analysis permission makes its annotations accessible."""
        # Create private annotation
        private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            analysis=self.analysis,
            created_by_analysis=self.analysis,
            creator=self.owner,
            page=1,
            raw_text="Private analysis annotation",
        )

        # Initially collaborator can't access it
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.READ
            )
        )

        # Grant analysis permission to collaborator
        set_permissions_for_obj_to_user(
            self.collaborator, self.analysis, [PermissionTypes.READ]
        )

        # Now collaborator should be able to read it
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.READ
            )
        )
        # But still can't edit (only has READ on analysis)
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.UPDATE
            )
        )

        # Grant full permissions on analysis
        set_permissions_for_obj_to_user(
            self.collaborator, self.analysis, [PermissionTypes.CRUD]
        )

        # Now collaborator should have full permissions
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.UPDATE
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator, private_annotation, PermissionTypes.DELETE
            )
        )

    def test_superuser_always_has_permissions(self):
        """Test that superusers bypass all permission checks."""
        # Create superuser
        superuser = User.objects.create_superuser(username="super", password="test")

        # Create private annotation
        private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            analysis=self.analysis,
            created_by_analysis=self.analysis,
            creator=self.owner,
            page=1,
            raw_text="Private annotation",
        )

        # Superuser should have all permissions even without explicit grants
        self.assertTrue(
            user_has_permission_for_obj(
                superuser, private_annotation, PermissionTypes.READ
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                superuser, private_annotation, PermissionTypes.UPDATE
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                superuser, private_annotation, PermissionTypes.DELETE
            )
        )
