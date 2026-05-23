"""
Integration tests for AnnotationService and RelationshipService
with StructuralAnnotationSet support.

These tests verify that the query optimizers correctly return:
1. Annotations/relationships from both document FK and structural_set FK
2. Proper corpus filtering (structural_set items have corpus_id=NULL)
3. Corpus copies SHARE the same structural annotation set (for efficiency)
   - Embeddings are added incrementally per-corpus via ensure_embeddings_for_corpus task
"""

import hashlib

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.annotations.services import (
    AnnotationService,
    RelationshipService,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class QueryOptimizerStructuralSetTests(TestCase):
    """Tests for query optimizers returning structural_set annotations/relationships."""

    def setUp(self):
        """
        Set up test data with structural annotation sets.

        NOTE: When adding a document to a corpus, the structural annotation set is
        SHARED (not duplicated). This is intentional for efficiency - annotations
        and parsing artifacts are reused across corpus copies. Per-corpus embeddings
        are handled incrementally via the ensure_embeddings_for_corpus task, which
        adds embeddings for the corpus's preferred_embedder if they don't exist.

        The test creates:
        - An original document with a structural_annotation_set
        - A corpus-isolated copy via corpus.add_document() which SHARES the same
          structural_annotation_set
        - Structural annotations are created on the shared set
        """
        self.user = User.objects.create_user(
            username="query_optimizer_struct_sets_tester",
            password="test",
            email="query_optimizer_struct_sets@test.com",
        )
        self.content_hash = hashlib.sha256(b"test content").hexdigest()

        # Create corpuses
        self.corpus_a = Corpus.objects.create(
            title="Corpus A", creator=self.user, is_public=True
        )
        self.corpus_b = Corpus.objects.create(
            title="Corpus B", creator=self.user, is_public=True
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

        # Create a structural annotation set for the source document
        # This will be duplicated when added to corpus
        self.source_structural_set = StructuralAnnotationSet.objects.create(
            content_hash=self.content_hash,
            creator=self.user,
            parser_name="TestParser",
            parser_version="1.0",
        )

        # Create document with structural set
        self.doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file_hash=self.content_hash,
            structural_annotation_set=self.source_structural_set,
        )

        # Add document to corpus A (creates corpus-isolated copy that SHARES structural set)
        self.corpus_a_doc, _, _ = self.corpus_a.add_document(
            document=self.doc, user=self.user
        )

        # Get the SHARED structural set (same as source document)
        self.corpus_a_structural_set = self.corpus_a_doc.structural_annotation_set

        # Create structural annotations in the shared set
        self.structural_annot1 = Annotation.objects.create(
            structural_set=self.corpus_a_structural_set,
            annotation_label=self.header_label,
            creator=self.user,
            raw_text="Structural Header",
            structural=True,
            page=1,
        )
        self.structural_annot2 = Annotation.objects.create(
            structural_set=self.corpus_a_structural_set,
            annotation_label=self.para_label,
            creator=self.user,
            raw_text="Structural Paragraph",
            structural=True,
            page=1,
        )

        # Create a structural relationship in the shared set
        self.structural_rel = Relationship.objects.create(
            structural_set=self.corpus_a_structural_set,
            relationship_label=self.rel_label,
            creator=self.user,
            structural=True,
        )
        self.structural_rel.source_annotations.add(self.structural_annot1)
        self.structural_rel.target_annotations.add(self.structural_annot2)

        # Create a corpus-specific annotation on the corpus copy
        self.corpus_specific_annot = Annotation.objects.create(
            document=self.corpus_a_doc,
            corpus=self.corpus_a,
            annotation_label=self.para_label,
            creator=self.user,
            raw_text="Corpus-specific annotation",
            structural=False,
            page=1,
        )

        # Grant user permissions
        set_permissions_for_obj_to_user(
            self.user, self.corpus_a_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus_a, [PermissionTypes.READ]
        )

    def test_query_optimizer_returns_structural_set_annotations(self):
        """
        CRITICAL TEST: Verify AnnotationService returns structural annotations
        from structural sets (not just from document FK).
        """
        annotations = list(
            AnnotationService.get_document_annotations(
                document_id=self.corpus_a_doc.id,
                user=self.user,
                corpus_id=self.corpus_a.id,
            )
        )

        # Should include BOTH structural_set annotations AND corpus-specific annotation
        annotation_texts = [a.raw_text for a in annotations]

        # Structural annotations from set
        self.assertIn("Structural Header", annotation_texts)
        self.assertIn("Structural Paragraph", annotation_texts)

        # Corpus-specific annotation
        self.assertIn("Corpus-specific annotation", annotation_texts)

        # Total: 2 structural + 1 corpus-specific = 3
        self.assertEqual(len(annotations), 3)

    def test_query_optimizer_returns_structural_set_relationships(self):
        """
        CRITICAL TEST: Verify RelationshipService returns structural relationships
        from structural sets (not just from document FK).
        """
        relationships = list(
            RelationshipService.get_document_relationships(
                document_id=self.corpus_a_doc.id,
                user=self.user,
                corpus_id=self.corpus_a.id,
            )
        )

        # Should include structural relationship from set
        self.assertEqual(len(relationships), 1)
        self.assertEqual(relationships[0].id, self.structural_rel.id)
        self.assertTrue(relationships[0].structural)

    def test_structural_filter_includes_structural_set_annotations(self):
        """
        Verify structural=True filter includes structural_set annotations.
        """
        structural_only = list(
            AnnotationService.get_document_annotations(
                document_id=self.corpus_a_doc.id,
                user=self.user,
                corpus_id=self.corpus_a.id,
                structural=True,
            )
        )

        # Should include only structural annotations (2 from set)
        self.assertEqual(len(structural_only), 2)
        annotation_texts = [a.raw_text for a in structural_only]
        self.assertIn("Structural Header", annotation_texts)
        self.assertIn("Structural Paragraph", annotation_texts)

    def test_non_structural_filter_excludes_structural_set_annotations(self):
        """
        Verify structural=False filter excludes structural_set annotations.
        """
        non_structural_only = list(
            AnnotationService.get_document_annotations(
                document_id=self.corpus_a_doc.id,
                user=self.user,
                corpus_id=self.corpus_a.id,
                structural=False,
            )
        )

        # Should include only corpus-specific annotation
        self.assertEqual(len(non_structural_only), 1)
        self.assertEqual(non_structural_only[0].raw_text, "Corpus-specific annotation")

    def test_multiple_corpus_copies_share_structural_sets(self):
        """
        Verify multiple corpus-isolated documents SHARE the same structural annotation set.

        This is intentional for efficiency - structural annotations and parsing artifacts
        are reused across corpus copies. Per-corpus embeddings are handled incrementally
        via the ensure_embeddings_for_corpus task (tested separately in corpus tasks tests).
        """
        # Add same document to corpus B (will SHARE the same structural set)
        corpus_b_doc, _, _ = self.corpus_b.add_document(
            document=self.doc, user=self.user
        )

        # Grant permissions
        set_permissions_for_obj_to_user(self.user, corpus_b_doc, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            self.user, self.corpus_b, [PermissionTypes.READ]
        )

        # Both corpus copies should SHARE the same structural set
        # This is the new design - structural sets are reused for efficiency
        self.assertEqual(
            self.corpus_a_doc.structural_annotation_set_id,
            corpus_b_doc.structural_annotation_set_id,
        )

        # Query annotations for corpus B copy
        corpus_b_annotations = list(
            AnnotationService.get_document_annotations(
                document_id=corpus_b_doc.id,
                user=self.user,
                corpus_id=self.corpus_b.id,
            )
        )

        # Should include the SHARED structural annotations (same as corpus A)
        annotation_texts = [a.raw_text for a in corpus_b_annotations]
        self.assertIn("Structural Header", annotation_texts)
        self.assertIn("Structural Paragraph", annotation_texts)

        # Should NOT include corpus A's corpus-specific annotation
        # (corpus-specific annotations are tied to a specific corpus, not shared)
        self.assertNotIn("Corpus-specific annotation", annotation_texts)

    def test_document_without_structural_set_works(self):
        """
        Verify query optimizer works for documents without structural_annotation_set.
        """
        # Create document without structural set
        doc_no_set = Document.objects.create(
            title="Doc No Set", creator=self.user, pdf_file_hash="differenthash"
        )
        corpus_doc, _, _ = self.corpus_a.add_document(
            document=doc_no_set, user=self.user
        )

        # Create annotation directly on document
        Annotation.objects.create(
            document=corpus_doc,
            corpus=self.corpus_a,
            annotation_label=self.para_label,
            creator=self.user,
            raw_text="Direct annotation",
            structural=False,
        )

        # Grant permissions
        set_permissions_for_obj_to_user(self.user, corpus_doc, [PermissionTypes.READ])

        # Query should work and return only direct annotation
        annotations = list(
            AnnotationService.get_document_annotations(
                document_id=corpus_doc.id,
                user=self.user,
                corpus_id=self.corpus_a.id,
            )
        )

        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0].raw_text, "Direct annotation")

    def test_no_corpus_mode_returns_only_structural(self):
        """
        Verify that querying without corpus_id returns only structural annotations.
        """
        annotations = list(
            AnnotationService.get_document_annotations(
                document_id=self.corpus_a_doc.id,
                user=self.user,
                corpus_id=None,  # No corpus
            )
        )

        # Should include only structural annotations (2 from set)
        self.assertEqual(len(annotations), 2)
        for annot in annotations:
            self.assertTrue(annot.structural)

    def test_permissions_computed_once(self):
        """
        Verify permissions are computed at document+corpus level and applied to all.
        All annotations should have the same permission flags.
        """
        annotations = AnnotationService.get_document_annotations(
            document_id=self.corpus_a_doc.id,
            user=self.user,
            corpus_id=self.corpus_a.id,
        )

        # All annotations should have permission flags annotated
        for annot in annotations:
            self.assertTrue(hasattr(annot, "_can_read"))
            self.assertTrue(annot._can_read)  # User has READ permission

            # Structural annotations should NOT be editable
            if annot.structural:
                self.assertFalse(annot._can_update)
                self.assertFalse(annot._can_delete)

    def test_pages_filter_works_with_structural_set_annotations(self):
        """
        Verify page filtering works for structural_set annotations.
        """
        # Create structural annotation on page 2 (in the corpus's structural set)
        _page2_annot = Annotation.objects.create(  # noqa: F841
            structural_set=self.corpus_a_structural_set,
            annotation_label=self.header_label,
            creator=self.user,
            raw_text="Page 2 Header",
            structural=True,
            page=2,
        )

        # Query only page 1
        page1_annotations = list(
            AnnotationService.get_document_annotations(
                document_id=self.corpus_a_doc.id,
                user=self.user,
                corpus_id=self.corpus_a.id,
                pages=[1],
            )
        )

        annotation_texts = [a.raw_text for a in page1_annotations]

        # Should include page 1 annotations but not page 2
        self.assertIn("Structural Header", annotation_texts)  # Page 1
        self.assertNotIn("Page 2 Header", annotation_texts)  # Page 2

    def test_structural_annotations_included_in_results(self):
        """
        Verify structural annotations from structural_set are included when querying.

        NOTE: Structural protection (read-only enforcement) happens at mutation time via
        the ``user_can`` permission checks, not at query time.
        The query optimizer computes permissions at document+corpus level.
        """
        # Grant full CRUD permissions to user
        set_permissions_for_obj_to_user(
            self.user, self.corpus_a_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus_a, [PermissionTypes.CRUD]
        )

        # Query all annotations
        annotations = list(
            AnnotationService.get_document_annotations(
                document_id=self.corpus_a_doc.id,
                user=self.user,
                corpus_id=self.corpus_a.id,
            )
        )

        # Should include both structural (from set) and non-structural annotations
        structural_count = sum(1 for a in annotations if a.structural)
        non_structural_count = sum(1 for a in annotations if not a.structural)

        self.assertEqual(structural_count, 2)  # 2 structural from set
        self.assertEqual(non_structural_count, 1)  # 1 corpus-specific

        # All should have permission flags annotated
        for annot in annotations:
            self.assertTrue(hasattr(annot, "_can_read"))
            self.assertTrue(annot._can_read)  # User has READ permission
