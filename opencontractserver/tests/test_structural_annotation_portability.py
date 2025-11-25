"""
Integration tests for structural annotation portability across corpuses.

These tests verify that structural annotations properly travel with documents
when they are added to multiple corpuses via corpus isolation.
"""

import hashlib

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

User = get_user_model()


class StructuralAnnotationPortabilityTests(TestCase):
    """Tests for structural annotations traveling with documents across corpuses."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.content_hash = hashlib.sha256(b"test pdf content").hexdigest()

        # Create corpuses
        self.corpus_a = Corpus.objects.create(
            title="Corpus A", creator=self.user, is_public=True
        )
        self.corpus_b = Corpus.objects.create(
            title="Corpus B", creator=self.user, is_public=True
        )
        self.corpus_c = Corpus.objects.create(
            title="Corpus C", creator=self.user, is_public=True
        )

        # Create a structural annotation set for the document
        self.structural_set = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
            page_count=5,
            token_count=500,
        )

        # Create labels
        self.header_label = AnnotationLabel.objects.create(
            text="Header", creator=self.user
        )
        self.para_label = AnnotationLabel.objects.create(
            text="Paragraph", creator=self.user
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="Contains", creator=self.user, label_type="RELATIONSHIP_LABEL"
        )

        # Create structural annotations in the set
        self.header_annot = Annotation.objects.create(
            structural_set=self.structural_set,
            annotation_label=self.header_label,
            creator=self.user,
            raw_text="Chapter 1: Introduction",
            structural=True,
        )
        self.para_annot = Annotation.objects.create(
            structural_set=self.structural_set,
            annotation_label=self.para_label,
            creator=self.user,
            raw_text="This document describes the system architecture.",
            structural=True,
        )

        # Create a structural relationship
        self.structural_rel = Relationship.objects.create(
            structural_set=self.structural_set,
            relationship_label=self.rel_label,
            creator=self.user,
            structural=True,
        )
        self.structural_rel.source_annotations.add(self.header_annot)
        self.structural_rel.target_annotations.add(self.para_annot)

        # Create the original document with the structural set
        self.original_doc = Document.objects.create(
            title="Test Document",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=self.structural_set,
        )

    def test_structural_set_shared_when_adding_to_corpus(self):
        """When adding a document to corpus, the corpus copy should share the structural set."""
        corpus_doc, status, path = self.corpus_a.add_document(
            document=self.original_doc, user=self.user
        )

        # Status should be 'added' for new copy
        self.assertEqual(status, "added")

        # Corpus doc should be a different object (corpus isolation)
        self.assertNotEqual(corpus_doc.id, self.original_doc.id)

        # But should share the same structural annotation set
        self.assertEqual(
            corpus_doc.structural_annotation_set_id,
            self.original_doc.structural_annotation_set_id,
        )
        self.assertEqual(corpus_doc.structural_annotation_set, self.structural_set)

    def test_structural_annotations_accessible_via_all_corpus_copies(self):
        """All corpus copies should access the same structural annotations."""
        # Add document to three different corpuses
        corpus_a_doc, _, _ = self.corpus_a.add_document(
            document=self.original_doc, user=self.user
        )
        corpus_b_doc, _, _ = self.corpus_b.add_document(
            document=self.original_doc, user=self.user
        )
        corpus_c_doc, _, _ = self.corpus_c.add_document(
            document=self.original_doc, user=self.user
        )

        # All should share the same structural set
        self.assertEqual(
            corpus_a_doc.structural_annotation_set_id,
            corpus_b_doc.structural_annotation_set_id,
        )
        self.assertEqual(
            corpus_b_doc.structural_annotation_set_id,
            corpus_c_doc.structural_annotation_set_id,
        )

        # All should have access to the same structural annotations
        annots_a = list(
            corpus_a_doc.structural_annotation_set.structural_annotations.all()
        )
        annots_b = list(
            corpus_b_doc.structural_annotation_set.structural_annotations.all()
        )
        annots_c = list(
            corpus_c_doc.structural_annotation_set.structural_annotations.all()
        )

        self.assertEqual(set(annots_a), set(annots_b))
        self.assertEqual(set(annots_b), set(annots_c))
        self.assertEqual(len(annots_a), 2)  # header and paragraph

        # Verify the specific annotations are there
        self.assertIn(self.header_annot, annots_a)
        self.assertIn(self.para_annot, annots_a)

    def test_structural_relationships_accessible_via_all_corpus_copies(self):
        """All corpus copies should access the same structural relationships."""
        corpus_a_doc, _, _ = self.corpus_a.add_document(
            document=self.original_doc, user=self.user
        )
        corpus_b_doc, _, _ = self.corpus_b.add_document(
            document=self.original_doc, user=self.user
        )

        # Both should have access to the same structural relationships
        rels_a = list(
            corpus_a_doc.structural_annotation_set.structural_relationships.all()
        )
        rels_b = list(
            corpus_b_doc.structural_annotation_set.structural_relationships.all()
        )

        self.assertEqual(set(rels_a), set(rels_b))
        self.assertEqual(len(rels_a), 1)
        self.assertIn(self.structural_rel, rels_a)

    def test_structural_annotations_count_not_duplicated(self):
        """Structural annotations should not be duplicated across corpus copies."""
        # Initially we have 2 structural annotations
        initial_count = Annotation.objects.filter(structural=True).count()
        self.assertEqual(initial_count, 2)

        # Add document to multiple corpuses
        self.corpus_a.add_document(document=self.original_doc, user=self.user)
        self.corpus_b.add_document(document=self.original_doc, user=self.user)
        self.corpus_c.add_document(document=self.original_doc, user=self.user)

        # Count should remain the same (no duplication)
        final_count = Annotation.objects.filter(structural=True).count()
        self.assertEqual(final_count, initial_count)

    def test_structural_set_reference_only_once_per_content(self):
        """Documents with same content hash should reuse the same structural set."""
        # Original doc already has the structural set
        self.assertEqual(
            self.original_doc.structural_annotation_set_id, self.structural_set.id
        )

        # Create another document with same content hash
        another_doc = Document.objects.create(
            title="Another Document",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=self.structural_set,
        )

        # Both should reference the same set
        self.assertEqual(
            self.original_doc.structural_annotation_set_id,
            another_doc.structural_annotation_set_id,
        )

        # The set should have both documents
        self.assertIn(self.original_doc, self.structural_set.documents.all())
        self.assertIn(another_doc, self.structural_set.documents.all())

    def test_corpus_specific_annotations_remain_isolated(self):
        """Corpus-specific annotations should not be shared across corpus copies."""
        corpus_a_doc, _, _ = self.corpus_a.add_document(
            document=self.original_doc, user=self.user
        )
        corpus_b_doc, _, _ = self.corpus_b.add_document(
            document=self.original_doc, user=self.user
        )

        # Create corpus-specific annotations
        label = AnnotationLabel.objects.create(text="UserNote", creator=self.user)
        _corpus_a_annot = Annotation.objects.create(  # noqa: F841
            document=corpus_a_doc,
            corpus=self.corpus_a,
            annotation_label=label,
            creator=self.user,
            raw_text="Note for Corpus A",
            structural=False,  # NOT structural
        )

        # This annotation should only be accessible via corpus_a_doc
        self.assertEqual(
            corpus_a_doc.doc_annotations.filter(structural=False).count(), 1
        )
        self.assertEqual(
            corpus_b_doc.doc_annotations.filter(structural=False).count(), 0
        )

        # But both should have access to structural annotations via the set
        self.assertEqual(
            corpus_a_doc.structural_annotation_set.structural_annotations.count(), 2
        )
        self.assertEqual(
            corpus_b_doc.structural_annotation_set.structural_annotations.count(), 2
        )

    def test_structural_set_with_no_annotations(self):
        """Document with structural set but no annotations should still share the set."""
        empty_hash = hashlib.sha256(b"empty content").hexdigest()
        empty_set = StructuralAnnotationSet.objects.create(
            content_hash=empty_hash, creator=self.user
        )

        doc = Document.objects.create(
            title="Empty Doc",
            creator=self.user,
            pdf_file_hash=empty_hash,
            structural_annotation_set=empty_set,
        )

        corpus_doc, _, _ = self.corpus_a.add_document(document=doc, user=self.user)

        # Should share the empty set
        self.assertEqual(corpus_doc.structural_annotation_set, empty_set)
        self.assertEqual(
            corpus_doc.structural_annotation_set.structural_annotations.count(), 0
        )


class ImportContentStructuralSetTests(TransactionTestCase):
    """Tests for structural annotation sets with import_content."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="test")
        self.corpus_a = Corpus.objects.create(
            title="Corpus A", creator=self.user, is_public=True
        )
        self.corpus_b = Corpus.objects.create(
            title="Corpus B", creator=self.user, is_public=True
        )

    def test_created_from_existing_inherits_structural_set(self):
        """When import_content finds existing content, it should inherit structural set."""
        from opencontractserver.documents.versioning import import_document

        content = b"test pdf content"
        content_hash = hashlib.sha256(content).hexdigest()

        # Create a structural set for this content
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=content_hash, creator=self.user
        )

        # Create a global document with this content and structural set
        global_doc = Document.objects.create(
            title="Global Doc",
            creator=self.user,
            pdf_file_hash=content_hash,
            structural_annotation_set=structural_set,
        )

        # Now import the same content into a corpus
        doc, status, path = import_document(
            corpus=self.corpus_a,
            path="/documents/test.pdf",
            content=content,
            user=self.user,
        )

        # Status should be 'created_from_existing'
        self.assertEqual(status, "created_from_existing")

        # Document should inherit the structural set
        self.assertEqual(doc.structural_annotation_set, structural_set)

        # Source document should be the global doc
        self.assertEqual(doc.source_document, global_doc)

    def test_version_update_preserves_structural_set(self):
        """When content is updated, the new version should preserve the structural set."""
        from opencontractserver.documents.versioning import import_document

        content_v1 = b"test pdf content v1"
        content_v2 = b"test pdf content v2"
        hash_v1 = hashlib.sha256(content_v1).hexdigest()
        _hash_v2 = hashlib.sha256(content_v2).hexdigest()  # noqa: F841

        # Create structural set for v1
        structural_set_v1 = StructuralAnnotationSet.objects.create(
            content_hash=hash_v1, creator=self.user
        )

        # Import v1
        doc_v1, status_v1, path_v1 = import_document(
            corpus=self.corpus_a,
            path="/documents/test.pdf",
            content=content_v1,
            user=self.user,
        )
        self.assertEqual(status_v1, "created")

        # Manually set the structural set (simulating parser creating it)
        doc_v1.structural_annotation_set = structural_set_v1
        doc_v1.save()

        # Import v2 at same path (version update)
        doc_v2, status_v2, path_v2 = import_document(
            corpus=self.corpus_a,
            path="/documents/test.pdf",
            content=content_v2,
            user=self.user,
        )
        self.assertEqual(status_v2, "updated")

        # v2 should inherit structural set from v1
        # (In a real scenario, parser would create new set for new content)
        self.assertEqual(doc_v2.structural_annotation_set, structural_set_v1)

    def test_brand_new_content_has_no_structural_set(self):
        """Brand new content should have no structural set (parser will create it later)."""
        from opencontractserver.documents.versioning import import_document

        content = b"brand new content"

        doc, status, path = import_document(
            corpus=self.corpus_a,
            path="/documents/new.pdf",
            content=content,
            user=self.user,
        )

        self.assertEqual(status, "created")
        # No structural set yet (parser will create it)
        self.assertIsNone(doc.structural_annotation_set)
