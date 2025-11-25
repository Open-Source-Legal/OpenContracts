"""
Test that structural annotations and relationships are ALWAYS read-only except for superusers.

This is critical for data integrity - structural annotations/relationships are generated
automatically and should never be manually modified.
"""

import logging

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class StructuralProtectionTestCase(TestCase):
    """Test that structural annotations and relationships cannot be modified by non-superusers."""

    def setUp(self):
        """Set up test data."""
        # Create users
        self.owner = User.objects.create_user(username="owner", password="test")
        self.superuser = User.objects.create_superuser(
            username="superuser", password="test"
        )

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

        # Create labels
        self.token_label = AnnotationLabel.objects.create(
            text="Test Token Label", label_type=TOKEN_LABEL, creator=self.owner
        )
        self.relationship_label = AnnotationLabel.objects.create(
            text="Test Relationship Label",
            label_type=RELATIONSHIP_LABEL,
            creator=self.owner,
        )

        # Create structural annotation
        self.structural_annotation = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Structural annotation",
            structural=True,
        )

        # Create structural relationship
        self.structural_relationship = Relationship.objects.create(
            relationship_label=self.relationship_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            structural=True,
        )

        # Grant owner FULL permissions on document and corpus
        set_permissions_for_obj_to_user(self.owner, self.doc, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

    def test_owner_can_read_structural_annotation(self):
        """Owner with full permissions can READ structural annotations."""
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner,
                self.structural_annotation,
                PermissionTypes.READ,
                include_group_permissions=True,
            )
        )

    def test_owner_cannot_update_structural_annotation(self):
        """Owner CANNOT UPDATE structural annotations even with full permissions."""
        self.assertFalse(
            user_has_permission_for_obj(
                self.owner,
                self.structural_annotation,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )

    def test_owner_cannot_delete_structural_annotation(self):
        """Owner CANNOT DELETE structural annotations even with full permissions."""
        self.assertFalse(
            user_has_permission_for_obj(
                self.owner,
                self.structural_annotation,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_owner_can_read_structural_relationship(self):
        """Owner with full permissions can READ structural relationships."""
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner,
                self.structural_relationship,
                PermissionTypes.READ,
                include_group_permissions=True,
            )
        )

    def test_owner_cannot_update_structural_relationship(self):
        """Owner CANNOT UPDATE structural relationships even with full permissions."""
        self.assertFalse(
            user_has_permission_for_obj(
                self.owner,
                self.structural_relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )

    def test_owner_cannot_delete_structural_relationship(self):
        """Owner CANNOT DELETE structural relationships even with full permissions."""
        self.assertFalse(
            user_has_permission_for_obj(
                self.owner,
                self.structural_relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_superuser_can_update_structural_annotation(self):
        """Superuser CAN UPDATE structural annotations."""
        self.assertTrue(
            user_has_permission_for_obj(
                self.superuser,
                self.structural_annotation,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )

    def test_superuser_can_delete_structural_annotation(self):
        """Superuser CAN DELETE structural annotations."""
        self.assertTrue(
            user_has_permission_for_obj(
                self.superuser,
                self.structural_annotation,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_superuser_can_update_structural_relationship(self):
        """Superuser CAN UPDATE structural relationships."""
        self.assertTrue(
            user_has_permission_for_obj(
                self.superuser,
                self.structural_relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )

    def test_superuser_can_delete_structural_relationship(self):
        """Superuser CAN DELETE structural relationships."""
        self.assertTrue(
            user_has_permission_for_obj(
                self.superuser,
                self.structural_relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_non_structural_annotation_can_be_modified(self):
        """Non-structural annotations CAN be modified by owner."""
        normal_annotation = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Normal annotation",
            structural=False,
        )

        # Owner should be able to UPDATE and DELETE normal annotations
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner,
                normal_annotation,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner,
                normal_annotation,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_non_structural_relationship_can_be_modified(self):
        """Non-structural relationships CAN be modified by owner."""
        normal_relationship = Relationship.objects.create(
            relationship_label=self.relationship_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            structural=False,
        )

        # Owner should be able to UPDATE and DELETE normal relationships
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner,
                normal_relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner,
                normal_relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )
