"""
Test that relationship mutations properly respect the privacy and permission model.

NOTE: Relationships do NOT have individual permissions. Like annotations, they inherit
permissions from their parent document and corpus. The effective permission is:
  MIN(document_permission, corpus_permission)

This means to UPDATE a relationship, you need UPDATE permission on BOTH the document
AND the corpus.
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


class RelationshipMutationPermissionTestCase(TestCase):
    """Test that relationship mutations respect the permission model."""

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

        # Create labels
        self.token_label = AnnotationLabel.objects.create(
            text="Test Token Label", label_type=TOKEN_LABEL, creator=self.owner
        )
        self.relationship_label = AnnotationLabel.objects.create(
            text="Test Relationship Label",
            label_type=RELATIONSHIP_LABEL,
            creator=self.owner,
        )

        # Create annotations
        self.source_annotation = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Source annotation",
        )
        self.target_annotation = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            page=1,
            raw_text="Target annotation",
        )
        self.extra_annotation = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            page=2,
            raw_text="Extra annotation",
        )

        # Create relationship
        self.relationship = Relationship.objects.create(
            relationship_label=self.relationship_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
        )
        self.relationship.source_annotations.add(self.source_annotation)
        self.relationship.target_annotations.add(self.target_annotation)

        # Set permissions on DOCUMENTS and CORPUSES (not relationships!)
        # Owner gets full permissions
        set_permissions_for_obj_to_user(self.owner, self.doc, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Collaborator gets READ on doc+corpus (not UPDATE)
        set_permissions_for_obj_to_user(
            self.collaborator, self.doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.READ]
        )

        # Outsider gets nothing

    def test_owner_can_add_source_annotations(self):
        """Test that owner with UPDATE on doc+corpus can add source annotations."""
        # Owner has UPDATE permission on both doc and corpus
        initial_count = self.relationship.source_annotations.count()
        self.relationship.source_annotations.add(self.extra_annotation)
        self.assertEqual(
            self.relationship.source_annotations.count(), initial_count + 1
        )
        self.assertIn(self.extra_annotation, self.relationship.source_annotations.all())

    def test_owner_can_add_target_annotations(self):
        """Test that owner with UPDATE on doc+corpus can add target annotations."""
        initial_count = self.relationship.target_annotations.count()
        self.relationship.target_annotations.add(self.extra_annotation)
        self.assertEqual(
            self.relationship.target_annotations.count(), initial_count + 1
        )
        self.assertIn(self.extra_annotation, self.relationship.target_annotations.all())

    def test_owner_can_remove_annotations(self):
        """Test that owner with UPDATE on doc+corpus can remove annotations."""
        # Remove source annotation
        self.relationship.source_annotations.remove(self.source_annotation)
        self.assertNotIn(
            self.source_annotation, self.relationship.source_annotations.all()
        )

        # Remove target annotation
        self.relationship.target_annotations.remove(self.target_annotation)
        self.assertNotIn(
            self.target_annotation, self.relationship.target_annotations.all()
        )

    def test_collaborator_with_only_read_cannot_update(self):
        """
        Test that collaborator with only READ permission cannot update relationship.

        Since relationships inherit permissions from document+corpus, collaborator
        needs UPDATE on both to modify the relationship.
        """
        # Collaborator only has READ on doc and corpus
        # This means effective permission for relationship is also READ-ONLY

        # Collaborator should be able to READ
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.READ,
                include_group_permissions=True,
            )
        )

        # But NOT UPDATE or DELETE
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_granting_update_permission_allows_modification(self):
        """Test that granting UPDATE permission on doc+corpus allows modification."""
        # Initially collaborator can't update (only has READ)
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )

        # Grant UPDATE permission on both doc and corpus
        set_permissions_for_obj_to_user(
            self.collaborator, self.doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.CRUD]
        )

        # Now collaborator should be able to modify relationship
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.READ,
                include_group_permissions=True,
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_structural_relationship_is_read_only(self):
        """Test that structural relationships are read-only for all users."""
        # Create structural relationship
        structural_rel = Relationship.objects.create(
            relationship_label=self.relationship_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            structural=True,
        )

        # Owner (with full permissions on doc+corpus) can READ
        self.assertTrue(
            user_has_permission_for_obj(
                self.owner,
                structural_rel,
                PermissionTypes.READ,
                include_group_permissions=True,
            )
        )

        # But NOT UPDATE or DELETE (structural is read-only)
        self.assertFalse(
            user_has_permission_for_obj(
                self.owner,
                structural_rel,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.owner,
                structural_rel,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_superuser_always_has_permissions(self):
        """Test that superusers bypass all permission checks."""
        superuser = User.objects.create_superuser(username="super", password="test")

        # Superuser should have all permissions even without explicit grants
        self.assertTrue(
            user_has_permission_for_obj(
                superuser,
                self.relationship,
                PermissionTypes.READ,
                include_group_permissions=True,
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                superuser,
                self.relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(
                superuser,
                self.relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_relationship_with_no_annotations(self):
        """Test that relationships can exist with no source or target annotations."""
        empty_rel = Relationship.objects.create(
            relationship_label=self.relationship_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
        )

        self.assertEqual(empty_rel.source_annotations.count(), 0)
        self.assertEqual(empty_rel.target_annotations.count(), 0)

        # Owner can still add annotations to it (has UPDATE on doc+corpus)
        empty_rel.source_annotations.add(self.source_annotation)
        self.assertEqual(empty_rel.source_annotations.count(), 1)

    def test_adding_same_annotation_multiple_times_has_no_effect(self):
        """Test that adding the same annotation multiple times has no effect (set behavior)."""
        initial_count = self.relationship.source_annotations.count()

        # Try adding the same annotation twice
        self.relationship.source_annotations.add(self.extra_annotation)
        self.relationship.source_annotations.add(self.extra_annotation)

        # Count should only increase by 1
        self.assertEqual(
            self.relationship.source_annotations.count(), initial_count + 1
        )

    def test_can_add_annotation_as_both_source_and_target(self):
        """Test that an annotation can be both source and target of same relationship."""
        self.relationship.source_annotations.add(self.extra_annotation)
        self.relationship.target_annotations.add(self.extra_annotation)

        self.assertIn(self.extra_annotation, self.relationship.source_annotations.all())
        self.assertIn(self.extra_annotation, self.relationship.target_annotations.all())

    def test_removing_nonexistent_annotation_has_no_effect(self):
        """Test that removing an annotation not in the set has no effect."""
        # Create annotation not in relationship
        other_annotation = Annotation.objects.create(
            annotation_label=self.token_label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            page=4,
            raw_text="Other annotation",
        )

        initial_source_count = self.relationship.source_annotations.count()
        initial_target_count = self.relationship.target_annotations.count()

        # Try removing annotation that's not in the relationship
        self.relationship.source_annotations.remove(other_annotation)
        self.relationship.target_annotations.remove(other_annotation)

        # Counts should remain unchanged
        self.assertEqual(
            self.relationship.source_annotations.count(), initial_source_count
        )
        self.assertEqual(
            self.relationship.target_annotations.count(), initial_target_count
        )

    def test_bulk_add_and_remove_operations(self):
        """Test that bulk add/remove operations work correctly."""
        # Create multiple annotations
        bulk_annotations = [
            Annotation.objects.create(
                annotation_label=self.token_label,
                document=self.doc,
                corpus=self.corpus,
                creator=self.owner,
                page=i,
                raw_text=f"Bulk annotation {i}",
            )
            for i in range(5, 10)
        ]

        # Bulk add
        self.relationship.source_annotations.add(*bulk_annotations)
        self.assertEqual(
            self.relationship.source_annotations.filter(
                id__in=[a.id for a in bulk_annotations]
            ).count(),
            len(bulk_annotations),
        )

        # Bulk remove
        self.relationship.source_annotations.remove(*bulk_annotations)
        self.assertEqual(
            self.relationship.source_annotations.filter(
                id__in=[a.id for a in bulk_annotations]
            ).count(),
            0,
        )

    def test_document_permission_is_primary(self):
        """
        Test that document permissions take priority (most restrictive wins).

        If doc has READ and corpus has UPDATE, effective permission is READ.
        """
        # Set up: doc has READ only, corpus has UPDATE
        set_permissions_for_obj_to_user(
            self.collaborator, self.doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.CRUD]
        )

        # Effective permission should be READ (most restrictive)
        # Collaborator can READ
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.READ,
                include_group_permissions=True,
            )
        )

        # But NOT UPDATE or DELETE (doc only has READ)
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

    def test_missing_corpus_permission_blocks_update(self):
        """
        Test that missing corpus permission blocks updates even with doc permission.
        """
        # Set up: doc has UPDATE, corpus has READ only
        set_permissions_for_obj_to_user(
            self.collaborator, self.doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.READ]
        )

        # Effective permission should be READ (most restrictive)
        # Collaborator can READ
        self.assertTrue(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.READ,
                include_group_permissions=True,
            )
        )

        # But NOT UPDATE or DELETE (corpus only has READ)
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.collaborator,
                self.relationship,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )
