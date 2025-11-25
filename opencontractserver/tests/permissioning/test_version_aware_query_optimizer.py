"""
Tests for version-aware query optimizer functionality.
These tests verify that the query optimizer properly handles document versioning
and deletion status in the dual-tree architecture.
"""

import logging

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.annotations.query_optimizer import AnnotationQueryOptimizer
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.versioning import (
    delete_document,
    import_document,
    move_document,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class TestVersionAwareAnnotationQueryOptimizer(TestCase):
    """Test version-aware annotation query functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", email="test@test.com")
        self.other_user = User.objects.create_user(
            username="other", email="other@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.user, is_public=False
        )
        self.label = AnnotationLabel.objects.create(text="Important", creator=self.user)

        # Give user permissions on corpus
        set_permissions_for_obj_to_user(
            self.user, self.corpus, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

    def test_default_queries_only_current_versions(self):
        """Test that queries default to current versions only."""
        # Import v1
        doc_v1, status, _ = import_document(
            corpus=self.corpus,
            path="/test.pdf",
            content=b"Version 1 content",
            user=self.user,
            title="Test Doc V1",
        )
        self.assertEqual(status, "created")
        # Grant user permissions on the document
        set_permissions_for_obj_to_user(
            self.user, doc_v1, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Create annotation on v1
        Annotation.objects.create(
            document=doc_v1,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Version 1 annotation",
            creator=self.user,
            page=1,
            structural=False,
        )

        # Import v2 (becomes current)
        doc_v2, status, _ = import_document(
            corpus=self.corpus,
            path="/test.pdf",
            content=b"Version 2 content",
            user=self.user,
            title="Test Doc V2",
        )
        self.assertEqual(status, "updated")
        # Grant user permissions on the new document version
        set_permissions_for_obj_to_user(
            self.user, doc_v2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Create annotation on v2
        anno_v2 = Annotation.objects.create(
            document=doc_v2,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Version 2 annotation",
            creator=self.user,
            page=1,
            structural=False,
        )

        # Verify version states
        doc_v1.refresh_from_db()
        doc_v2.refresh_from_db()
        self.assertFalse(doc_v1.is_current)
        self.assertTrue(doc_v2.is_current)

        # Query v1 directly - should return empty by default
        result = AnnotationQueryOptimizer.get_document_annotations(
            document_id=doc_v1.id,
            user=self.user,
            corpus_id=self.corpus.id,
            # check_current_version=True by default
        )
        self.assertEqual(
            result.count(),
            0,
            "Should not return annotations for old version by default",
        )

        # Query v2 (current) - should return annotations
        result = AnnotationQueryOptimizer.get_document_annotations(
            document_id=doc_v2.id, user=self.user, corpus_id=self.corpus.id
        )
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().id, anno_v2.id)

        logger.info("✓ Default queries filter to current versions only")

    def test_can_explicitly_query_old_versions(self):
        """Test that old versions can be queried when explicitly requested."""
        # Import v1
        doc_v1, _, _ = import_document(
            corpus=self.corpus, path="/test.pdf", content=b"Version 1", user=self.user
        )
        set_permissions_for_obj_to_user(
            self.user, doc_v1, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        anno_v1 = Annotation.objects.create(
            document=doc_v1,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="V1 annotation",
            creator=self.user,
        )

        # Import v2
        doc_v2, _, _ = import_document(
            corpus=self.corpus, path="/test.pdf", content=b"Version 2", user=self.user
        )
        set_permissions_for_obj_to_user(
            self.user, doc_v2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Explicitly query old version with check disabled
        result = AnnotationQueryOptimizer.get_document_annotations(
            document_id=doc_v1.id,
            user=self.user,
            corpus_id=self.corpus.id,
            check_current_version=False,  # Explicitly disable version check
        )
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().id, anno_v1.id)

        logger.info("✓ Can query old versions when explicitly requested")

    def test_path_based_queries_return_current_by_default(self):
        """Test that path-based queries return current version by default."""
        # Create version history
        doc_v1, _, _ = import_document(
            corpus=self.corpus,
            path="/contract.pdf",
            content=b"Version 1",
            user=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, doc_v1, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        Annotation.objects.create(
            document=doc_v1,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="V1 clause",
            creator=self.user,
        )

        doc_v2, _, _ = import_document(
            corpus=self.corpus,
            path="/contract.pdf",
            content=b"Version 2",
            user=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, doc_v2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        anno_v2 = Annotation.objects.create(
            document=doc_v2,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="V2 clause",
            creator=self.user,
        )

        # Path-based query should return current version
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id, path="/contract.pdf", user=self.user
        )

        anno_ids = list(result.values_list("id", flat=True))
        self.assertEqual(len(anno_ids), 1)
        self.assertEqual(anno_ids[0], anno_v2.id)

        logger.info("✓ Path-based queries return current version by default")

    def test_path_queries_can_request_specific_version(self):
        """Test that path queries can request specific version numbers."""
        # Create multiple versions
        doc_v1, _, _ = import_document(
            corpus=self.corpus,
            path="/evolving.pdf",
            content=b"Version 1",
            user=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, doc_v1, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        anno_v1 = Annotation.objects.create(
            document=doc_v1,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Version 1 content",
            creator=self.user,
        )

        doc_v2, _, _ = import_document(
            corpus=self.corpus,
            path="/evolving.pdf",
            content=b"Version 2",
            user=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, doc_v2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        anno_v2 = Annotation.objects.create(
            document=doc_v2,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Version 2 content",
            creator=self.user,
        )

        # Request specific version 1
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id,
            path="/evolving.pdf",
            user=self.user,
            version=1,  # Request version 1 explicitly
        )

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().id, anno_v1.id)

        # Request specific version 2
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id,
            path="/evolving.pdf",
            user=self.user,
            version=2,  # Request version 2 explicitly
        )

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().id, anno_v2.id)

        logger.info("✓ Can request specific versions via path queries")

    def test_deleted_documents_are_excluded(self):
        """Test that deleted documents are properly excluded from queries."""
        # Import document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/deleteme.pdf",
            content=b"Content to delete",
            user=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, doc, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Annotation on deleted doc",
            creator=self.user,
        )

        # Query before delete - should find annotation
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id, path="/deleteme.pdf", user=self.user
        )
        self.assertEqual(result.count(), 1)

        # Delete document
        delete_document(self.corpus, "/deleteme.pdf", self.user)

        # Query after delete - should return empty
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id, path="/deleteme.pdf", user=self.user
        )
        self.assertEqual(
            result.count(), 0, "Deleted document should not return annotations"
        )

        # Direct query with version checking should also return empty
        result = AnnotationQueryOptimizer.get_document_annotations(
            document_id=doc.id,
            user=self.user,
            corpus_id=self.corpus.id,
            check_current_version=True,  # Should check deletion status
        )
        self.assertEqual(
            result.count(), 0, "Direct query should respect deletion status"
        )

        # Can still access if we bypass version checking (for recovery scenarios)
        result = AnnotationQueryOptimizer.get_document_annotations(
            document_id=doc.id,
            user=self.user,
            corpus_id=self.corpus.id,
            check_current_version=False,  # Bypass deletion check
        )
        self.assertEqual(
            result.count(), 1, "Can access deleted doc when check disabled"
        )

        logger.info("✓ Deleted documents are properly excluded")

    def test_moved_documents_maintain_annotations(self):
        """Test that moving documents doesn't affect annotation visibility."""
        # Import document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/original/location.pdf",
            content=b"Document content",
            user=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, doc, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        anno = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Annotation on moved doc",
            creator=self.user,
        )

        # Move document
        move_document(
            corpus=self.corpus,
            old_path="/original/location.pdf",
            new_path="/new/location.pdf",
            user=self.user,
        )

        # Query at new path - should find annotation
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id, path="/new/location.pdf", user=self.user
        )
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().id, anno.id)

        # Query at old path - should return empty
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id, path="/original/location.pdf", user=self.user
        )
        self.assertEqual(result.count(), 0, "Old path should not return annotations")

        logger.info("✓ Moved documents maintain annotations at new path")

    def test_structural_annotations_follow_document_versions(self):
        """Test that structural annotations are version-specific."""
        # Import v1
        doc_v1, _, _ = import_document(
            corpus=self.corpus,
            path="/structural.pdf",
            content=b"Version 1 with headers",
            user=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, doc_v1, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Create structural annotation on v1
        Annotation.objects.create(
            document=doc_v1,
            corpus=None,  # Structural annotations don't have corpus
            raw_text="Page 1 Header",
            creator=self.user,
            page=1,
            structural=True,
        )

        # Import v2
        doc_v2, _, _ = import_document(
            corpus=self.corpus,
            path="/structural.pdf",
            content=b"Version 2 with different headers",
            user=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, doc_v2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Create structural annotation on v2
        structural_v2 = Annotation.objects.create(
            document=doc_v2,
            corpus=None,
            raw_text="Page 1 New Header",
            creator=self.user,
            page=1,
            structural=True,
        )

        # Query for current version should only return v2 structural
        # Note: Structural annotations have corpus=None, so we query without corpus_id
        # The version-awareness is based on the document version itself
        result = AnnotationQueryOptimizer.get_document_annotations(
            document_id=doc_v2.id,
            user=self.user,
            corpus_id=None,  # Structural annotations don't have corpus
            structural=True,
        )

        # Should only get v2 structural annotation
        anno_ids = list(result.values_list("id", flat=True))
        self.assertEqual(len(anno_ids), 1)
        self.assertEqual(anno_ids[0], structural_v2.id)

        # Verify that querying v1 (old version) returns v1's structural annotation
        result_v1 = AnnotationQueryOptimizer.get_document_annotations(
            document_id=doc_v1.id,
            user=self.user,
            corpus_id=None,
            structural=True,
        )
        # Should get v1 structural annotation (version-specific)
        self.assertEqual(result_v1.count(), 1)
        self.assertNotEqual(result_v1.first().id, structural_v2.id)

        logger.info("✓ Structural annotations are version-specific")

    def test_cross_corpus_document_with_different_states(self):
        """Test document that exists in multiple corpuses with different states."""
        # Create second corpus
        corpus2 = Corpus.objects.create(
            title="Corpus 2", creator=self.user, is_public=False
        )
        # Grant user permissions on the second corpus
        set_permissions_for_obj_to_user(
            self.user, corpus2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Import document to corpus 1
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/shared.pdf",
            content=b"Shared content",
            user=self.user,
        )
        # Grant user permissions on the document
        set_permissions_for_obj_to_user(
            self.user, doc, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Add annotation in corpus 1
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Corpus 1 annotation",
            creator=self.user,
        )

        # Import same content to corpus 2 (corpus-isolated copy with provenance)
        doc2, status, _ = import_document(
            corpus=corpus2,
            path="/shared.pdf",
            content=b"Shared content",  # Same content
            user=self.user,
        )
        self.assertEqual(status, "created_from_existing")
        self.assertNotEqual(doc.id, doc2.id)  # Corpus-isolated copy
        # Grant user permissions on the corpus-isolated copy
        set_permissions_for_obj_to_user(
            self.user, doc2, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # Add annotation in corpus 2
        anno2 = Annotation.objects.create(
            document=doc2,
            corpus=corpus2,
            annotation_label=self.label,
            raw_text="Corpus 2 annotation",
            creator=self.user,
        )

        # Delete from corpus 1 but not corpus 2
        delete_document(self.corpus, "/shared.pdf", self.user)

        # Document is still current globally
        doc.refresh_from_db()
        self.assertTrue(doc.is_current)

        # Query in corpus 1 - should return empty (deleted)
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id, path="/shared.pdf", user=self.user
        )
        self.assertEqual(result.count(), 0)

        # Query in corpus 2 - should return annotations (not deleted)
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=corpus2.id, path="/shared.pdf", user=self.user
        )
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().id, anno2.id)

        logger.info("✓ Cross-corpus documents maintain independent states")

    def test_nonexistent_path_returns_empty(self):
        """Test that querying nonexistent paths returns empty queryset."""
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id, path="/nonexistent.pdf", user=self.user
        )
        self.assertEqual(result.count(), 0)
        self.assertIsNotNone(result)  # Should be empty queryset, not None

        logger.info("✓ Nonexistent paths return empty queryset")

    def test_version_aware_performance(self):
        """Test that version-aware queries maintain good performance."""
        import time

        # Create 20 versions of a document with annotations
        doc = None
        for i in range(20):
            doc, _, _ = import_document(
                corpus=self.corpus,
                path="/perf_test.pdf",
                content=f"Version {i+1}".encode(),
                user=self.user,
            )
            # Grant user permissions on each document version
            set_permissions_for_obj_to_user(
                self.user, doc, [PermissionTypes.READ, PermissionTypes.UPDATE]
            )

            # Add 5 annotations per version
            for j in range(5):
                Annotation.objects.create(
                    document=doc,
                    corpus=self.corpus,
                    annotation_label=self.label,
                    raw_text=f"V{i+1} Anno {j+1}",
                    creator=self.user,
                )

        # Time the query for current version
        start = time.time()
        result = AnnotationQueryOptimizer.get_annotations_for_path(
            corpus_id=self.corpus.id, path="/perf_test.pdf", user=self.user
        )
        count = result.count()
        duration = time.time() - start

        # Should only return annotations for current version (5 annotations)
        self.assertEqual(count, 5)
        # Should be fast (< 100ms)
        self.assertLess(duration, 0.1, f"Query took {duration:.3f}s, expected < 0.1s")

        logger.info(
            f"✓ Version-aware query performance: {duration:.3f}s for {count} results"
        )
