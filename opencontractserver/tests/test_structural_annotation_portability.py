"""
Integration tests for structural annotation portability across corpuses.

These tests verify that structural annotations are properly SHARED across corpuses
when documents are added. The same StructuralAnnotationSet is reused across all
corpus copies of the same document content, which:
- Saves storage (no duplicate annotation data)
- Enables consistent embeddings across corpuses
- Reduces processing time when adding documents to multiple corpuses

CURRENT BEHAVIOR (shared structural sets):
- When a document is added to a corpus, it SHARES the same structural annotation set
- Structural annotation sets are NOT duplicated per corpus
- Total structural annotation count does NOT increase when adding to multiple corpuses
- Corpus-specific (non-structural) annotations remain isolated per corpus
"""

import hashlib

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

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
    """Tests for structural annotations being SHARED across corpuses."""

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
        """When adding a document to corpus, the corpus copy SHARES the same structural set."""
        corpus_doc, status, path = self.corpus_a.add_document(
            document=self.original_doc, user=self.user
        )

        # Status should be 'added' for new copy
        self.assertEqual(status, "added")

        # Corpus doc should be a different document object (corpus isolation)
        self.assertNotEqual(corpus_doc.id, self.original_doc.id)

        # Corpus doc should have the SAME structural annotation set (shared)
        self.assertIsNotNone(corpus_doc.structural_annotation_set)
        self.assertEqual(
            corpus_doc.structural_annotation_set_id,
            self.original_doc.structural_annotation_set_id,
        )

        # Same set metadata
        shared_set = corpus_doc.structural_annotation_set
        self.assertEqual(shared_set.parser_name, self.structural_set.parser_name)
        self.assertEqual(shared_set.parser_version, self.structural_set.parser_version)
        self.assertEqual(shared_set.page_count, self.structural_set.page_count)
        self.assertEqual(shared_set.token_count, self.structural_set.token_count)

        # Content hash is unchanged (no corpus suffix for shared sets)
        self.assertEqual(shared_set.content_hash, self.content_hash)

    def test_structural_annotations_shared_across_corpuses(self):
        """All corpus copies share the SAME structural annotation set and annotations."""
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

        # All should have the SAME structural set (shared)
        self.assertEqual(
            corpus_a_doc.structural_annotation_set_id,
            corpus_b_doc.structural_annotation_set_id,
        )
        self.assertEqual(
            corpus_b_doc.structural_annotation_set_id,
            corpus_c_doc.structural_annotation_set_id,
        )
        self.assertEqual(
            corpus_a_doc.structural_annotation_set_id,
            self.original_doc.structural_annotation_set_id,
        )

        # Each should access the same annotations (shared)
        annots_a = set(
            corpus_a_doc.structural_annotation_set.structural_annotations.values_list(
                "id", flat=True
            )
        )
        annots_b = set(
            corpus_b_doc.structural_annotation_set.structural_annotations.values_list(
                "id", flat=True
            )
        )
        annots_c = set(
            corpus_c_doc.structural_annotation_set.structural_annotations.values_list(
                "id", flat=True
            )
        )

        # All sets should have the same annotation IDs
        self.assertEqual(annots_a, annots_b)
        self.assertEqual(annots_b, annots_c)
        self.assertEqual(len(annots_a), 2)  # header and paragraph

    def test_structural_relationships_shared(self):
        """Structural relationships are also shared via the shared structural set."""
        corpus_a_doc, _, _ = self.corpus_a.add_document(
            document=self.original_doc, user=self.user
        )
        corpus_b_doc, _, _ = self.corpus_b.add_document(
            document=self.original_doc, user=self.user
        )

        # Relationships are shared (same set)
        rels_a = list(
            corpus_a_doc.structural_annotation_set.structural_relationships.all()
        )
        rels_b = list(
            corpus_b_doc.structural_annotation_set.structural_relationships.all()
        )

        # Same relationships in both (shared)
        self.assertEqual(len(rels_a), 1)
        self.assertEqual(len(rels_b), 1)
        self.assertEqual(rels_a[0].id, rels_b[0].id)

        # Same as original
        self.assertEqual(
            self.original_doc.structural_annotation_set.structural_relationships.count(),
            1,
        )

    def test_structural_annotations_count_unchanged_across_corpuses(self):
        """Total structural annotation count does NOT increase when adding to multiple corpuses."""
        # Initially we have 2 structural annotations (in the shared set)
        initial_count = Annotation.objects.filter(structural=True).count()
        self.assertEqual(initial_count, 2)

        # Add document to multiple corpuses
        self.corpus_a.add_document(document=self.original_doc, user=self.user)
        self.corpus_b.add_document(document=self.original_doc, user=self.user)
        self.corpus_c.add_document(document=self.original_doc, user=self.user)

        # Count should NOT increase (same annotations shared)
        final_count = Annotation.objects.filter(structural=True).count()
        self.assertEqual(final_count, initial_count)  # Still 2

    def test_structural_set_count_unchanged_across_corpuses(self):
        """StructuralAnnotationSet count does NOT increase when adding to multiple corpuses."""
        # Initially we have 1 structural set
        initial_set_count = StructuralAnnotationSet.objects.count()
        self.assertEqual(initial_set_count, 1)

        # Add document to multiple corpuses
        self.corpus_a.add_document(document=self.original_doc, user=self.user)
        self.corpus_b.add_document(document=self.original_doc, user=self.user)
        self.corpus_c.add_document(document=self.original_doc, user=self.user)

        # Should still have 1 set (shared)
        final_set_count = StructuralAnnotationSet.objects.count()
        self.assertEqual(final_set_count, 1)

    def test_corpus_specific_annotations_remain_isolated(self):
        """Corpus-specific (non-structural) annotations remain isolated per corpus."""
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

        # Both should have access to the SAME structural annotations via shared set
        self.assertEqual(
            corpus_a_doc.structural_annotation_set.structural_annotations.count(), 2
        )
        self.assertEqual(
            corpus_b_doc.structural_annotation_set.structural_annotations.count(), 2
        )

        # These ARE the same annotation objects (shared set)
        self.assertEqual(
            corpus_a_doc.structural_annotation_set_id,
            corpus_b_doc.structural_annotation_set_id,
        )

    def test_structural_set_shared_even_with_no_annotations(self):
        """Document with structural set but no annotations still shares that set."""
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

        # Should share the same set
        self.assertIsNotNone(corpus_doc.structural_annotation_set)
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

    def test_import_creates_new_document_not_linked_to_global(self):
        """When import_document creates a document, it's a new corpus-isolated document."""
        from opencontractserver.documents.versioning import import_document

        content = b"test pdf content"
        content_hash = hashlib.sha256(content).hexdigest()

        # Create a structural set for this content
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=content_hash, creator=self.user
        )

        # Create a global document with this content and structural set.
        # processing_started bypasses the post_save signal which would
        # otherwise trigger eager celery ingestion for the (file-less) doc
        # under TransactionTestCase.
        _global_doc = Document.objects.create(  # noqa: F841
            title="Global Doc",
            creator=self.user,
            pdf_file_hash=content_hash,
            structural_annotation_set=structural_set,
            processing_started=timezone.now(),
        )

        # Now import the same content into a corpus
        doc, status, path = import_document(
            corpus=self.corpus_a,
            path="/documents/test.pdf",
            content=content,
            user=self.user,
        )

        # Status should be 'created' (new document created)
        self.assertEqual(status, "created")

        # Document should NOT have a structural set yet (parser will create it)
        # import_document doesn't copy structural sets from existing docs
        self.assertIsNone(doc.structural_annotation_set)

    def test_version_update_with_changed_content_gets_no_structural_set(self):
        """When content changes, the new version gets NO structural set (parser creates fresh one)."""
        from opencontractserver.documents.versioning import import_document

        content_v1 = b"test pdf content v1"
        content_v2 = b"test pdf content v2"
        hash_v1 = hashlib.sha256(content_v1).hexdigest()

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

        # Import v2 at same path with DIFFERENT content (version update)
        doc_v2, status_v2, path_v2 = import_document(
            corpus=self.corpus_a,
            path="/documents/test.pdf",
            content=content_v2,
            user=self.user,
        )
        self.assertEqual(status_v2, "updated")

        # v2 should NOT inherit v1's structural set because content changed.
        # The parser will create a fresh StructuralAnnotationSet during ingestion.
        self.assertIsNone(doc_v2.structural_annotation_set)

    def test_version_update_with_same_content_inherits_structural_set(self):
        """When content hash is unchanged, the new version reuses the existing structural set."""
        from opencontractserver.documents.versioning import import_document

        content = b"test pdf content unchanged"
        content_hash = hashlib.sha256(content).hexdigest()

        # Create structural set for this content
        structural_set = StructuralAnnotationSet.objects.create(
            content_hash=content_hash, creator=self.user
        )

        # Import v1
        doc_v1, status_v1, path_v1 = import_document(
            corpus=self.corpus_a,
            path="/documents/test.pdf",
            content=content,
            user=self.user,
        )
        self.assertEqual(status_v1, "created")

        # Manually set the structural set (simulating parser creating it)
        doc_v1.structural_annotation_set = structural_set
        doc_v1.save()

        # Import same content again at same path (re-upload, same hash)
        doc_v2, status_v2, path_v2 = import_document(
            corpus=self.corpus_a,
            path="/documents/test.pdf",
            content=content,
            user=self.user,
        )
        self.assertEqual(status_v2, "updated")

        # v2 should inherit the structural set because content hash is identical
        self.assertEqual(doc_v2.structural_annotation_set, structural_set)

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
