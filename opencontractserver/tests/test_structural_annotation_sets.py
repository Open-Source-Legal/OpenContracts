"""
Tests for the StructuralAnnotationSet model and related functionality.

This file tests:
1. Model creation and uniqueness constraints
2. Annotation/Relationship XOR constraints (document vs structural_set)
3. Shared structural annotations across documents
4. Properties and counts
"""

import hashlib

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

User = get_user_model()


class StructuralAnnotationSetModelTests(TestCase):
    """Tests for the StructuralAnnotationSet model."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.content_hash = hashlib.sha256(b"test content").hexdigest()

    def test_create_structural_annotation_set(self):
        """Test basic creation of StructuralAnnotationSet."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
            page_count=10,
            token_count=1000,
        )

        self.assertEqual(sas.content_hash, self.content_hash)
        self.assertEqual(sas.creator, self.user)
        self.assertEqual(sas.parser_name, "TestParser")
        self.assertEqual(sas.parser_version, "1.0")
        self.assertEqual(sas.page_count, 10)
        self.assertEqual(sas.token_count, 1000)
        self.assertTrue(sas.is_public)  # Default

    def test_content_hash_uniqueness(self):
        """Test that content_hash must be unique."""
        StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )

        # Attempt to create another with the same hash should fail
        with self.assertRaises(IntegrityError):
            StructuralAnnotationSet.objects.create(
                content_hash=self.content_hash, creator=self.user
            )

    def test_string_representation(self):
        """Test __str__ method."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )
        str_repr = str(sas)
        # Should contain first 12 chars of hash
        self.assertIn(self.content_hash[:12], str_repr)
        self.assertIn("StructuralAnnotationSet", str_repr)

    def test_annotation_count_property(self):
        """Test annotation_count property."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )

        # Initially should be 0
        self.assertEqual(sas.annotation_count, 0)

        # Create some structural annotations
        label = AnnotationLabel.objects.create(text="Header", creator=self.user)
        for i in range(3):
            Annotation.objects.create(
                structural_set=sas,
                annotation_label=label,
                creator=self.user,
                raw_text=f"Structural annotation {i}",
                structural=True,
            )

        self.assertEqual(sas.annotation_count, 3)

    def test_relationship_count_property(self):
        """Test relationship_count property."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )

        # Initially should be 0
        self.assertEqual(sas.relationship_count, 0)

        # Create some structural relationships
        label = AnnotationLabel.objects.create(
            text="ParentChild", creator=self.user, label_type="RELATIONSHIP_LABEL"
        )
        for i in range(2):
            Relationship.objects.create(
                structural_set=sas,
                relationship_label=label,
                creator=self.user,
                structural=True,
            )

        self.assertEqual(sas.relationship_count, 2)


class AnnotationStructuralSetConstraintTests(TestCase):
    """Tests for the XOR constraint on Annotation (document vs structural_set)."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.user, is_public=True
        )
        self.document = Document.objects.create(
            title="Test Doc", creator=self.user, is_public=True
        )
        self.label = AnnotationLabel.objects.create(text="Test", creator=self.user)
        self.content_hash = hashlib.sha256(b"test content").hexdigest()
        self.structural_set = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )

    def test_annotation_with_document_only(self):
        """Annotation with document but no structural_set should be valid."""
        annotation = Annotation.objects.create(
            document=self.document,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Test annotation",
        )
        self.assertIsNotNone(annotation.id)
        self.assertEqual(annotation.document, self.document)
        self.assertIsNone(annotation.structural_set)

    def test_annotation_with_structural_set_only(self):
        """Annotation with structural_set but no document should be valid."""
        annotation = Annotation.objects.create(
            structural_set=self.structural_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Structural annotation",
            structural=True,
        )
        self.assertIsNotNone(annotation.id)
        self.assertIsNone(annotation.document)
        self.assertEqual(annotation.structural_set, self.structural_set)

    def test_annotation_with_both_fails_validation(self):
        """Annotation with both document and structural_set should fail validation."""
        annotation = Annotation(
            document=self.document,
            structural_set=self.structural_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Invalid annotation",
        )
        with self.assertRaises(ValidationError) as context:
            annotation.full_clean()

        # Check the error contains the constraint violation message
        error_str = str(context.exception)
        self.assertTrue(
            "cannot belong to both" in error_str
            or "must belong to either" in error_str
            or "__all__" in error_str
        )

    def test_annotation_with_neither_fails_validation(self):
        """Annotation with neither document nor structural_set should fail validation."""
        annotation = Annotation(
            annotation_label=self.label,
            creator=self.user,
            raw_text="Invalid annotation",
        )
        with self.assertRaises(ValidationError) as context:
            annotation.full_clean()

        # Check the error contains the constraint violation message
        error_str = str(context.exception)
        self.assertTrue("must belong to either" in error_str or "__all__" in error_str)


class RelationshipStructuralSetConstraintTests(TestCase):
    """Tests for the XOR constraint on Relationship (document vs structural_set)."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.document = Document.objects.create(
            title="Test Doc", creator=self.user, is_public=True
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="ParentOf", creator=self.user, label_type="RELATIONSHIP_LABEL"
        )
        self.content_hash = hashlib.sha256(b"test content").hexdigest()
        self.structural_set = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )

    def test_relationship_with_document_only(self):
        """Relationship with document but no structural_set should be valid."""
        rel = Relationship.objects.create(
            document=self.document, relationship_label=self.rel_label, creator=self.user
        )
        self.assertIsNotNone(rel.id)
        self.assertEqual(rel.document, self.document)
        self.assertIsNone(rel.structural_set)

    def test_relationship_with_structural_set_only(self):
        """Relationship with structural_set but no document should be valid."""
        rel = Relationship.objects.create(
            structural_set=self.structural_set,
            relationship_label=self.rel_label,
            creator=self.user,
            structural=True,
        )
        self.assertIsNotNone(rel.id)
        self.assertIsNone(rel.document)
        self.assertEqual(rel.structural_set, self.structural_set)

    def test_relationship_with_both_fails_validation(self):
        """Relationship with both document and structural_set should fail validation."""
        rel = Relationship(
            document=self.document,
            structural_set=self.structural_set,
            relationship_label=self.rel_label,
            creator=self.user,
        )
        with self.assertRaises(ValidationError) as context:
            rel.full_clean()

        self.assertIn("document", str(context.exception))
        self.assertIn("structural_set", str(context.exception))

    def test_relationship_with_neither_fails_validation(self):
        """Relationship with neither document nor structural_set should fail validation."""
        rel = Relationship(relationship_label=self.rel_label, creator=self.user)
        with self.assertRaises(ValidationError) as context:
            rel.full_clean()

        self.assertIn("document", str(context.exception))
        self.assertIn("structural_set", str(context.exception))


class DocumentStructuralAnnotationSetTests(TestCase):
    """Tests for Document referencing StructuralAnnotationSet."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.content_hash = hashlib.sha256(b"test pdf content").hexdigest()

    def test_document_can_reference_structural_set(self):
        """Document should be able to reference a StructuralAnnotationSet."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
            parser_name="DoclingParser",
            page_count=5,
        )

        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=sas,
        )

        self.assertEqual(doc.structural_annotation_set, sas)
        self.assertIn(doc, sas.documents.all())

    def test_multiple_documents_share_structural_set(self):
        """Multiple documents should be able to share the same structural set."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )

        # Create multiple documents with same content (corpus isolation scenario)
        doc1 = Document.objects.create(
            title="Doc in Corpus A",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=sas,
        )
        doc2 = Document.objects.create(
            title="Doc in Corpus B",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=sas,
        )
        doc3 = Document.objects.create(
            title="Doc in Corpus C",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=sas,
        )

        # All documents should reference the same set
        self.assertEqual(doc1.structural_annotation_set, sas)
        self.assertEqual(doc2.structural_annotation_set, sas)
        self.assertEqual(doc3.structural_annotation_set, sas)

        # The set should have all documents
        self.assertEqual(sas.documents.count(), 3)

    def test_document_without_structural_set(self):
        """Document can exist without a structural_annotation_set."""
        doc = Document.objects.create(
            title="Doc without structural set", creator=self.user
        )
        self.assertIsNone(doc.structural_annotation_set)

    def test_shared_annotations_across_documents(self):
        """Structural annotations should be accessible via multiple documents."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )

        # Create structural annotations in the set
        label = AnnotationLabel.objects.create(text="Section", creator=self.user)
        struct_annot1 = Annotation.objects.create(
            structural_set=sas,
            annotation_label=label,
            creator=self.user,
            raw_text="Introduction",
            structural=True,
        )
        struct_annot2 = Annotation.objects.create(
            structural_set=sas,
            annotation_label=label,
            creator=self.user,
            raw_text="Conclusion",
            structural=True,
        )

        # Create two documents sharing the set
        doc1 = Document.objects.create(
            title="Doc 1",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=sas,
        )
        doc2 = Document.objects.create(
            title="Doc 2",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=sas,
        )

        # Both documents should see the same structural annotations
        doc1_struct_annots = list(
            doc1.structural_annotation_set.structural_annotations.all()
        )
        doc2_struct_annots = list(
            doc2.structural_annotation_set.structural_annotations.all()
        )

        self.assertEqual(len(doc1_struct_annots), 2)
        self.assertEqual(len(doc2_struct_annots), 2)
        self.assertEqual(set(doc1_struct_annots), set(doc2_struct_annots))
        self.assertIn(struct_annot1, doc1_struct_annots)
        self.assertIn(struct_annot2, doc1_struct_annots)


class StructuralAnnotationSetProtectionTests(TestCase):
    """Tests for protection of StructuralAnnotationSet from deletion."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.content_hash = hashlib.sha256(b"test content").hexdigest()

    def test_cannot_delete_structural_set_with_documents(self):
        """Deleting a structural set referenced by documents should fail."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )
        Document.objects.create(
            title="Test Doc",
            creator=self.user,
            structural_annotation_set=sas,
        )

        # Attempting to delete the structural set should raise an error
        # (due to PROTECT on delete)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            sas.delete()

    def test_can_delete_structural_set_without_documents(self):
        """Deleting an unreferenced structural set should succeed."""
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )
        sas_id = sas.id

        # Should be able to delete
        sas.delete()

        # Verify it's gone
        self.assertFalse(StructuralAnnotationSet.objects.filter(id=sas_id).exists())

    def test_deleting_document_preserves_set_when_other_documents_reference_it(self):
        """Deleting a document leaves the SAS intact if another doc still
        references it. The orphan-GC signal added in PR #1380 only deletes
        sets with zero remaining references; see
        ``test_orphan_structural_set_gc.py`` for the orphan path.
        """
        sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )
        sas_id = sas.id

        doc1 = Document.objects.create(
            title="Test Doc 1",
            creator=self.user,
            structural_annotation_set=sas,
        )
        Document.objects.create(
            title="Test Doc 2",
            creator=self.user,
            structural_annotation_set=sas,
        )

        # Delete one document; the other still references the set.
        doc1.delete()

        self.assertTrue(StructuralAnnotationSet.objects.filter(id=sas_id).exists())


class StructuralAnnotationImmutabilityTests(TestCase):
    """Tests for immutability of structural annotations in shared sets."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.content_hash = hashlib.sha256(b"test content").hexdigest()
        self.sas = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )
        self.label = AnnotationLabel.objects.create(text="Header", creator=self.user)

    def test_structural_annotation_belongs_to_set_not_document(self):
        """Structural annotations in a set should not belong to any specific document."""
        annotation = Annotation.objects.create(
            structural_set=self.sas,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Shared header",
            structural=True,
        )

        self.assertIsNone(annotation.document)
        self.assertIsNone(annotation.corpus)
        self.assertEqual(annotation.structural_set, self.sas)

    def test_structural_relationship_belongs_to_set_not_document(self):
        """Structural relationships in a set should not belong to any specific document."""
        rel_label = AnnotationLabel.objects.create(
            text="Contains", creator=self.user, label_type="RELATIONSHIP_LABEL"
        )
        relationship = Relationship.objects.create(
            structural_set=self.sas,
            relationship_label=rel_label,
            creator=self.user,
            structural=True,
        )

        self.assertIsNone(relationship.document)
        self.assertIsNone(relationship.corpus)
        self.assertEqual(relationship.structural_set, self.sas)


class StructuralSetRequiresStructuralFlagTests(TestCase):
    """
    Tests for the database constraint that ensures annotations and relationships
    in a structural_set must have structural=True.

    This constraint prevents data integrity issues where an annotation/relationship
    is assigned to a structural_set but has structural=False, which would break
    assumptions in the query optimizer (see query_optimizer.py:207-209).
    """

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.content_hash = hashlib.sha256(b"test constraint content").hexdigest()
        self.structural_set = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash, creator=self.user
        )
        self.label = AnnotationLabel.objects.create(text="TestLabel", creator=self.user)
        self.rel_label = AnnotationLabel.objects.create(
            text="TestRelLabel", creator=self.user, label_type="RELATIONSHIP_LABEL"
        )

    def test_annotation_in_structural_set_with_structural_true_succeeds(self):
        """Annotation in structural_set with structural=True should succeed."""
        annotation = Annotation.objects.create(
            structural_set=self.structural_set,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Valid structural annotation",
            structural=True,
        )
        self.assertIsNotNone(annotation.id)
        self.assertTrue(annotation.structural)
        self.assertEqual(annotation.structural_set, self.structural_set)

    def test_annotation_in_structural_set_with_structural_false_fails(self):
        """Annotation in structural_set with structural=False should fail at database level."""
        # This tests the CheckConstraint 'structural_set_requires_structural_flag'
        with self.assertRaises(IntegrityError):
            # Bypass model validation by using SQL insert or raw create
            # We need to test the DB-level constraint, so we use a lower-level approach
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO annotations_annotation
                    (created, modified, page, raw_text, structural, is_public,
                     creator_id, structural_set_id, annotation_label_id, annotation_type,
                     json)
                    VALUES (NOW(), NOW(), 1, 'Invalid annotation', FALSE, FALSE,
                            %s, %s, %s, 'TOKEN_LABEL', '{}')
                    """,
                    [self.user.id, self.structural_set.id, self.label.id],
                )

    def test_relationship_in_structural_set_with_structural_true_succeeds(self):
        """Relationship in structural_set with structural=True should succeed."""
        relationship = Relationship.objects.create(
            structural_set=self.structural_set,
            relationship_label=self.rel_label,
            creator=self.user,
            structural=True,
        )
        self.assertIsNotNone(relationship.id)
        self.assertTrue(relationship.structural)
        self.assertEqual(relationship.structural_set, self.structural_set)

    def test_relationship_in_structural_set_with_structural_false_fails(self):
        """Relationship in structural_set with structural=False should fail at database level."""
        # This tests the CheckConstraint 'rel_structural_set_requires_structural_flag'
        with self.assertRaises(IntegrityError):
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO annotations_relationship
                    (created, modified, structural, is_public,
                     creator_id, structural_set_id, relationship_label_id)
                    VALUES (NOW(), NOW(), FALSE, FALSE,
                            %s, %s, %s)
                    """,
                    [self.user.id, self.structural_set.id, self.rel_label.id],
                )

    def test_annotation_without_structural_set_can_have_structural_false(self):
        """Annotation without structural_set can have structural=False (normal case)."""
        document = Document.objects.create(
            title="Test Doc", creator=self.user, is_public=True
        )
        annotation = Annotation.objects.create(
            document=document,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Normal non-structural annotation",
            structural=False,
        )
        self.assertIsNotNone(annotation.id)
        self.assertFalse(annotation.structural)
        self.assertIsNone(annotation.structural_set)

    def test_relationship_without_structural_set_can_have_structural_false(self):
        """Relationship without structural_set can have structural=False (normal case)."""
        document = Document.objects.create(
            title="Test Doc", creator=self.user, is_public=True
        )
        relationship = Relationship.objects.create(
            document=document,
            relationship_label=self.rel_label,
            creator=self.user,
            structural=False,
        )
        self.assertIsNotNone(relationship.id)
        self.assertFalse(relationship.structural)
        self.assertIsNone(relationship.structural_set)


class StructuralAnnotationSetDuplicateTests(TestCase):
    """Tests for the StructuralAnnotationSet.duplicate() method."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.content_hash = hashlib.sha256(b"test duplicate content").hexdigest()
        self.label = AnnotationLabel.objects.create(text="Section", creator=self.user)

    def test_duplicate_creates_new_set_with_corpus_suffix(self):
        """Test that duplicate() creates a new set with corpus_id and UUID suffix."""
        original = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
            page_count=5,
            token_count=500,
        )

        copy = original.duplicate(corpus_id=123)

        self.assertNotEqual(original.id, copy.id)
        # Content hash format: {original_hash}_{corpus_id}_{uuid8}
        self.assertTrue(
            copy.content_hash.startswith(f"{self.content_hash}_123_"),
            f"Expected hash to start with '{self.content_hash}_123_', "
            f"got '{copy.content_hash}'",
        )
        # Verify UUID suffix is 8 hex chars
        suffix = copy.content_hash.split("_")[-1]
        self.assertEqual(len(suffix), 8, "UUID suffix should be 8 characters")
        self.assertEqual(copy.parser_name, "TestParser")
        self.assertEqual(copy.parser_version, "1.0")
        self.assertEqual(copy.page_count, 5)
        self.assertEqual(copy.token_count, 500)
        self.assertEqual(copy.creator, self.user)

    def test_duplicate_creates_new_set_with_uuid_suffix(self):
        """Test that duplicate() creates a new set with UUID suffix when no corpus_id."""
        original = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
        )

        copy = original.duplicate()

        self.assertNotEqual(original.id, copy.id)
        self.assertTrue(copy.content_hash.startswith(self.content_hash))
        self.assertNotEqual(copy.content_hash, self.content_hash)
        # UUID suffix is 8 chars after underscore
        suffix = copy.content_hash[len(self.content_hash) + 1 :]
        self.assertEqual(len(suffix), 8)

    def test_duplicate_copies_annotations(self):
        """Test that duplicate() copies structural annotations."""
        original = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
        )

        # Create some annotations
        for i in range(3):
            Annotation.objects.create(
                structural_set=original,
                annotation_label=self.label,
                creator=self.user,
                raw_text=f"Section {i}",
                page=i,
                structural=True,
            )

        copy = original.duplicate(corpus_id=456)

        # Check annotations were copied
        self.assertEqual(original.annotation_count, 3)
        self.assertEqual(copy.annotation_count, 3)

        # Annotations should be different objects
        original_annot_ids = set(
            original.structural_annotations.values_list("id", flat=True)
        )
        copy_annot_ids = set(copy.structural_annotations.values_list("id", flat=True))
        self.assertEqual(len(original_annot_ids & copy_annot_ids), 0)

        # But content should match
        original_texts = set(
            original.structural_annotations.values_list("raw_text", flat=True)
        )
        copy_texts = set(copy.structural_annotations.values_list("raw_text", flat=True))
        self.assertEqual(original_texts, copy_texts)

    def test_duplicate_preserves_annotation_content_modalities(self):
        """Test that duplicate() preserves content_modalities field."""
        from opencontractserver.types.enums import ContentModality

        original = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
        )

        # Create annotation with image modality
        Annotation.objects.create(
            structural_set=original,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Figure caption",
            structural=True,
            content_modalities=[
                ContentModality.TEXT.value,
                ContentModality.IMAGE.value,
            ],
        )

        copy = original.duplicate(corpus_id=789)

        copy_annot = copy.structural_annotations.first()
        self.assertIn(ContentModality.TEXT.value, copy_annot.content_modalities)
        self.assertIn(ContentModality.IMAGE.value, copy_annot.content_modalities)
