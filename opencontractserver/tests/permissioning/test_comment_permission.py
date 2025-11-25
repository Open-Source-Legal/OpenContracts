"""
Test COMMENT Permission Inheritance for Annotations and Relationships

This test validates that COMMENT permissions follow the same inheritance model
as other permissions (READ, CREATE, UPDATE, DELETE).

Permission Rules for COMMENT:
1. Document COMMENT permission is PRIMARY (most restrictive)
2. Corpus COMMENT permission is SECONDARY
3. Effective COMMENT permission = MIN(doc_comment, corpus_comment)
4. Private annotations (created_by_analysis/extract) require COMMENT on source object
"""

import logging

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.annotations.query_optimizer import AnnotationQueryOptimizer
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class CommentPermissionTestCase(TestCase):
    """
    Tests that COMMENT permissions follow the same inheritance model as other permissions.
    """

    def setUp(self):
        """Set up test users, documents, corpuses, and annotations"""
        # Create test users
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.commenter = User.objects.create_user(
            username="commenter", password="test123"
        )

        # Create document
        with open(SAMPLE_PDF_FILE_ONE_PATH, "rb") as pdf_file:
            pdf_content = pdf_file.read()

        self.document = Document.objects.create(
            title="Test Document",
            description="Test",
            creator=self.owner,
            pdf_file=ContentFile(pdf_content, name="test.pdf"),
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=self.owner,
        )
        self.corpus.add_document(document=self.document, user=self.owner)

        # Create DocumentPath to link document to corpus in dual-tree versioning
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.owner,
        )

        # Create annotation label
        self.label = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL,
            text="Test Label",
            creator=self.owner,
        )

        # Create annotation
        self.annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.document,
            corpus=self.corpus,
            page=1,
            creator=self.owner,
        )

    def test_comment_permission_document_only(self):
        """Test COMMENT permission with only document permissions"""
        # Give commenter COMMENT permission on document only
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        # Check via query optimizer
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                self.commenter,
                self.document.id,
                None,  # No corpus context
            )
        )

        self.assertTrue(can_read, "User should have READ permission")
        self.assertTrue(can_comment, "User should have COMMENT permission")
        self.assertFalse(can_update, "User should NOT have UPDATE permission")

    def test_comment_permission_document_and_corpus(self):
        """Test COMMENT permission with both document and corpus permissions"""
        # Give commenter COMMENT on document
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        # Give commenter COMMENT on corpus
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        # Check via query optimizer with corpus context
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                self.commenter,
                self.document.id,
                self.corpus.id,
            )
        )

        self.assertTrue(can_read, "User should have READ permission")
        self.assertTrue(can_comment, "User should have COMMENT permission on both")

    def test_comment_permission_most_restrictive_wins(self):
        """Test that most restrictive COMMENT permission wins"""
        # Give commenter COMMENT on document but NOT on corpus
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        # Give commenter only READ on corpus (no COMMENT)
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ],  # No COMMENT
        )

        # Check via query optimizer with corpus context
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                self.commenter,
                self.document.id,
                self.corpus.id,
            )
        )

        self.assertTrue(can_read, "User should have READ permission")
        self.assertFalse(
            can_comment,
            "User should NOT have COMMENT permission (corpus restriction applies)",
        )

    def test_comment_permission_via_user_has_permission(self):
        """Test COMMENT permission check via user_has_permission_for_obj"""
        # Give commenter COMMENT on document and corpus
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        # Test via user_has_permission_for_obj
        has_comment = user_has_permission_for_obj(
            self.commenter,
            self.annotation,
            PermissionTypes.COMMENT,
            include_group_permissions=True,
        )

        self.assertTrue(
            has_comment,
            "User should have COMMENT permission on annotation via inheritance",
        )

    def test_comment_permission_annotated_on_queryset(self):
        """Test that _can_comment is properly annotated on queryset"""
        # Give commenter COMMENT permission
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.COMMENT],
        )

        # Get annotations via query optimizer
        annotations = AnnotationQueryOptimizer.get_document_annotations(
            document_id=self.document.id,
            user=self.commenter,
            corpus_id=self.corpus.id,
        )

        # Check that _can_comment is annotated
        annotation = annotations.first()
        self.assertIsNotNone(annotation, "Should have at least one annotation")
        self.assertTrue(
            hasattr(annotation, "_can_comment"),
            "Annotation should have _can_comment attribute",
        )
        self.assertTrue(
            annotation._can_comment,
            "Annotation should have _can_comment=True",
        )

    def test_superuser_has_comment_permission(self):
        """Test that superusers have COMMENT permission"""
        superuser = User.objects.create_superuser(username="super", password="admin")

        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                superuser,
                self.document.id,
                self.corpus.id,
            )
        )

        self.assertTrue(can_comment, "Superuser should have COMMENT permission")

    def test_allow_comments_enables_commenting_for_readers(self):
        """Test that corpus.allow_comments=True gives COMMENT to all readers (BACON MODE)"""
        # Enable allow_comments on corpus
        self.corpus.allow_comments = True
        self.corpus.save()

        # Give commenter only READ on document and corpus (no explicit COMMENT)
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ],  # No COMMENT
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ],  # No COMMENT
        )

        # Check via query optimizer
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                self.commenter,
                self.document.id,
                self.corpus.id,
            )
        )

        self.assertTrue(can_read, "User should have READ permission")
        self.assertTrue(
            can_comment,
            "User should have COMMENT permission via allow_comments (comment mode)",
        )
        self.assertFalse(can_update, "User should NOT have UPDATE permission")

    def test_allow_comments_respects_read_boundaries(self):
        """Test that allow_comments doesn't grant access beyond READ boundaries"""
        # Enable allow_comments
        self.corpus.allow_comments = True
        self.corpus.save()

        # Give commenter CORPUS access but NO document access
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ],
        )
        # Explicitly NO document permissions

        # Check via query optimizer
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                self.commenter,
                self.document.id,
                self.corpus.id,
            )
        )

        self.assertFalse(
            can_read, "User should NOT have READ permission (no doc access)"
        )
        self.assertFalse(
            can_comment,
            "User should NOT have COMMENT permission (can't read = can't comment)",
        )

    def test_allow_comments_off_requires_explicit_permission(self):
        """Test that allow_comments=False requires explicit COMMENT permissions"""
        # Ensure allow_comments is False
        self.corpus.allow_comments = False
        self.corpus.save()

        # Give commenter READ but not COMMENT
        set_permissions_for_obj_to_user(
            self.commenter,
            self.document,
            [PermissionTypes.READ],  # No COMMENT
        )
        set_permissions_for_obj_to_user(
            self.commenter,
            self.corpus,
            [PermissionTypes.READ],  # No COMMENT
        )

        # Check via query optimizer
        can_read, can_create, can_update, can_delete, can_comment = (
            AnnotationQueryOptimizer._compute_effective_permissions(
                self.commenter,
                self.document.id,
                self.corpus.id,
            )
        )

        self.assertTrue(can_read, "User should have READ permission")
        self.assertFalse(
            can_comment,
            "User should NOT have COMMENT permission (explicit COMMENT perm required)",
        )
