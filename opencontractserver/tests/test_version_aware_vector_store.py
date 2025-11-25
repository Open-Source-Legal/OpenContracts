"""
Tests for version-aware vector store functionality.
These tests verify that vector search properly handles document versioning
and deletion status in the dual-tree architecture.
"""

import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel, Embedding
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.versioning import (
    delete_document,
    import_document,
    move_document,
)
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
)

User = get_user_model()
logger = logging.getLogger(__name__)

# Use the default microservice embedder path for consistency
TEST_EMBEDDER_PATH = "opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder"


def mock_embeddings(dimension: int = 384) -> list[float]:
    """Generate mock embeddings for testing."""
    return [0.1] * dimension


class TestVersionAwareVectorStore(TestCase):
    """Test version-aware vector search functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", email="test@test.com")
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.user, is_public=False
        )
        self.label = AnnotationLabel.objects.create(text="Important", creator=self.user)

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_vector_search_defaults_to_current_versions(self, mock_generate):
        """Test that vector search defaults to current versions only."""
        mock_generate.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

        # Import v1
        doc_v1, _, _ = import_document(
            corpus=self.corpus, path="/test.pdf", content=b"Old content", user=self.user
        )

        # Add public annotation to v1
        annot_v1 = Annotation.objects.create(
            document=doc_v1,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Old searchable content",
            creator=self.user,
            structural=False,
            is_public=True,  # Make searchable
        )
        # Create embedding for annotation
        Embedding.objects.create(
            annotation=annot_v1,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Import v2 (becomes current)
        doc_v2, _, _ = import_document(
            corpus=self.corpus, path="/test.pdf", content=b"New content", user=self.user
        )

        # Add public annotation to v2
        annot_v2 = Annotation.objects.create(
            document=doc_v2,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="New searchable content",
            creator=self.user,
            structural=False,
            is_public=True,
        )
        Embedding.objects.create(
            annotation=annot_v2,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Create vector store (defaults to current only)
        vector_store = CoreAnnotationVectorStore(
            corpus_id=self.corpus.id,
            user_id=None,  # Anonymous search
            embedder_path=TEST_EMBEDDER_PATH,
            # only_current_versions=True by default
        )

        # Search
        query = VectorSearchQuery(query_text="searchable content", similarity_top_k=10)

        results = vector_store.search(query)

        # Should only find v2 annotation (current version)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].annotation.document_id, doc_v2.id)
        self.assertIn("New searchable", results[0].annotation.raw_text)

        logger.info("✓ Vector search defaults to current versions only")

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_vector_search_can_include_old_versions(self, mock_generate):
        """Test that vector search can explicitly include old versions."""
        mock_generate.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

        # Import v1
        doc_v1, _, _ = import_document(
            corpus=self.corpus, path="/test.pdf", content=b"Version 1", user=self.user
        )

        annot_v1 = Annotation.objects.create(
            document=doc_v1,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Historical content",
            creator=self.user,
            structural=False,
            is_public=True,
        )
        Embedding.objects.create(
            annotation=annot_v1,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Import v2
        doc_v2, _, _ = import_document(
            corpus=self.corpus, path="/test.pdf", content=b"Version 2", user=self.user
        )

        annot_v2 = Annotation.objects.create(
            document=doc_v2,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Current content",
            creator=self.user,
            structural=False,
            is_public=True,
        )
        Embedding.objects.create(
            annotation=annot_v2,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Create vector store with old versions included
        vector_store = CoreAnnotationVectorStore(
            corpus_id=self.corpus.id,
            user_id=None,
            only_current_versions=False,  # Include all versions
            # Don't filter by DocumentPath (needed to see old versions)
            check_corpus_deletion=False,
            embedder_path=TEST_EMBEDDER_PATH,
        )

        query = VectorSearchQuery(query_text="content", similarity_top_k=10)

        results = vector_store.search(query)

        # Should find both versions
        self.assertEqual(len(results), 2)
        doc_ids = {r.annotation.document_id for r in results}
        self.assertEqual(doc_ids, {doc_v1.id, doc_v2.id})

        logger.info("✓ Vector search can include old versions when requested")

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_vector_search_excludes_deleted_documents(self, mock_generate):
        """Test that vector search excludes deleted documents."""
        mock_generate.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

        # Import document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/deleteme.pdf",
            content=b"Content to delete",
            user=self.user,
        )

        annot = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Searchable content in deleted doc",
            creator=self.user,
            structural=False,
            is_public=True,
        )
        Embedding.objects.create(
            annotation=annot,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Search before delete
        vector_store = CoreAnnotationVectorStore(
            corpus_id=self.corpus.id, user_id=None, embedder_path=TEST_EMBEDDER_PATH
        )

        query = VectorSearchQuery(query_text="searchable", similarity_top_k=10)

        results = vector_store.search(query)
        self.assertEqual(len(results), 1)

        # Delete document
        delete_document(self.corpus, "/deleteme.pdf", self.user)

        # Search after delete - should find nothing
        vector_store_after = CoreAnnotationVectorStore(
            corpus_id=self.corpus.id,
            user_id=None,
            embedder_path=TEST_EMBEDDER_PATH,
            # check_corpus_deletion=True by default
        )

        results = vector_store_after.search(query)
        self.assertEqual(
            len(results), 0, "Should not find annotations in deleted documents"
        )

        logger.info("✓ Vector search excludes deleted documents")

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_vector_search_without_deletion_check(self, mock_generate):
        """Test that deletion check can be disabled for recovery scenarios."""
        mock_generate.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

        # Import and delete document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/deleted.pdf",
            content=b"Deleted content",
            user=self.user,
        )

        annot = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Content in deleted doc",
            creator=self.user,
            structural=False,
            is_public=True,
        )
        Embedding.objects.create(
            annotation=annot,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        delete_document(self.corpus, "/deleted.pdf", self.user)

        # Search with deletion check disabled
        vector_store = CoreAnnotationVectorStore(
            corpus_id=self.corpus.id,
            user_id=None,
            check_corpus_deletion=False,  # Disable deletion check
            embedder_path=TEST_EMBEDDER_PATH,
        )

        query = VectorSearchQuery(query_text="content", similarity_top_k=10)

        results = vector_store.search(query)
        self.assertEqual(len(results), 1, "Can find deleted docs when check disabled")

        logger.info("✓ Deletion check can be disabled for recovery")

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_vector_search_after_document_move(self, mock_generate):
        """Test that vector search works correctly after document move."""
        mock_generate.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

        # Import document
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/original/path.pdf",
            content=b"Moveable content",
            user=self.user,
        )

        annot = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.label,
            raw_text="Content in moved doc",
            creator=self.user,
            structural=False,
            is_public=True,
        )
        Embedding.objects.create(
            annotation=annot,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Move document
        move_document(
            corpus=self.corpus,
            old_path="/original/path.pdf",
            new_path="/new/path.pdf",
            user=self.user,
        )

        # Search should still find the annotation
        vector_store = CoreAnnotationVectorStore(
            corpus_id=self.corpus.id, user_id=None, embedder_path=TEST_EMBEDDER_PATH
        )

        query = VectorSearchQuery(query_text="moved doc", similarity_top_k=10)

        results = vector_store.search(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].annotation.document_id, doc.id)

        logger.info("✓ Vector search works after document move")

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_structural_annotations_in_vector_search(self, mock_generate):
        """Test that structural annotations follow version filtering."""
        mock_generate.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

        # Import v1
        doc_v1, _, _ = import_document(
            corpus=self.corpus,
            path="/structural.pdf",
            content=b"Version 1",
            user=self.user,
        )

        # Create structural annotation on v1
        annot_v1 = Annotation.objects.create(
            document=doc_v1,
            corpus=None,  # Structural has no corpus
            raw_text="V1 Header",
            creator=self.user,
            structural=True,
        )
        Embedding.objects.create(
            annotation=annot_v1,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Import v2
        doc_v2, _, _ = import_document(
            corpus=self.corpus,
            path="/structural.pdf",
            content=b"Version 2",
            user=self.user,
        )

        # Create structural annotation on v2
        annot_v2 = Annotation.objects.create(
            document=doc_v2,
            corpus=None,
            raw_text="V2 Header",
            creator=self.user,
            structural=True,
        )
        Embedding.objects.create(
            annotation=annot_v2,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Search with document context
        vector_store = CoreAnnotationVectorStore(
            document_id=doc_v2.id,  # Specific document
            user_id=None,
            embedder_path=TEST_EMBEDDER_PATH,
        )

        query = VectorSearchQuery(query_text="header", similarity_top_k=10)

        results = vector_store.search(query)

        # Should only find v2 structural annotation
        self.assertEqual(len(results), 1)
        self.assertIn("V2", results[0].annotation.raw_text)

        logger.info("✓ Structural annotations follow version filtering")

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_empty_corpus_returns_no_results(self, mock_generate):
        """Test that corpus with all deleted documents returns empty results."""
        mock_generate.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

        # Import multiple documents
        for i in range(3):
            doc, _, _ = import_document(
                corpus=self.corpus,
                path=f"/doc{i}.pdf",
                content=f"Content {i}".encode(),
                user=self.user,
            )

            annot = Annotation.objects.create(
                document=doc,
                corpus=self.corpus,
                raw_text=f"Searchable content {i}",
                creator=self.user,
                is_public=True,
            )
            Embedding.objects.create(
                annotation=annot,
                embedder_path=TEST_EMBEDDER_PATH,
                vector_384=mock_embeddings(),
                creator=self.user,
            )

            # Delete all documents
            delete_document(self.corpus, f"/doc{i}.pdf", self.user)

        # Search in corpus with all deleted documents
        vector_store = CoreAnnotationVectorStore(
            corpus_id=self.corpus.id, user_id=None, embedder_path=TEST_EMBEDDER_PATH
        )

        query = VectorSearchQuery(query_text="searchable", similarity_top_k=10)

        results = vector_store.search(query)
        self.assertEqual(
            len(results), 0, "Corpus with all deleted docs should return empty"
        )

        logger.info("✓ Empty corpus returns no results")

    @patch(
        "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
    )
    def test_cross_corpus_search_independence(self, mock_generate):
        """Test that deletion in one corpus doesn't affect search in another."""
        mock_generate.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

        # Create second corpus
        corpus2 = Corpus.objects.create(title="Corpus 2", creator=self.user)

        # Import to corpus 1
        doc, _, _ = import_document(
            corpus=self.corpus,
            path="/shared.pdf",
            content=b"Shared content",
            user=self.user,
        )

        annot1 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            raw_text="Corpus 1 searchable",
            creator=self.user,
            is_public=True,
        )
        Embedding.objects.create(
            annotation=annot1,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Import same content to corpus 2 (corpus-isolated copy with provenance)
        doc2, status, _ = import_document(
            corpus=corpus2,
            path="/shared.pdf",
            content=b"Shared content",
            user=self.user,
        )
        self.assertEqual(status, "created_from_existing")
        self.assertNotEqual(doc.id, doc2.id)  # Isolated document

        annot2 = Annotation.objects.create(
            document=doc2,
            corpus=corpus2,
            raw_text="Corpus 2 searchable",
            creator=self.user,
            is_public=True,
        )
        Embedding.objects.create(
            annotation=annot2,
            embedder_path=TEST_EMBEDDER_PATH,
            vector_384=mock_embeddings(),
            creator=self.user,
        )

        # Delete from corpus 1
        delete_document(self.corpus, "/shared.pdf", self.user)

        # Search in corpus 1 - should find nothing
        vector_store1 = CoreAnnotationVectorStore(
            corpus_id=self.corpus.id, user_id=None, embedder_path=TEST_EMBEDDER_PATH
        )

        query = VectorSearchQuery(query_text="searchable", similarity_top_k=10)
        results1 = vector_store1.search(query)
        self.assertEqual(len(results1), 0)

        # Search in corpus 2 - should still find annotation
        vector_store2 = CoreAnnotationVectorStore(
            corpus_id=corpus2.id, user_id=None, embedder_path=TEST_EMBEDDER_PATH
        )

        results2 = vector_store2.search(query)
        self.assertEqual(len(results2), 1)
        self.assertIn("Corpus 2", results2[0].annotation.raw_text)

        logger.info("✓ Cross-corpus search independence maintained")

    def test_vector_store_performance_with_versions(self):
        """Test that vector search maintains good performance with many versions."""
        import time

        # Create many versions
        doc = None
        for i in range(20):
            doc, _, _ = import_document(
                corpus=self.corpus,
                path="/perf.pdf",
                content=f"Version {i+1}".encode(),
                user=self.user,
            )

            # Add searchable annotations
            for j in range(3):
                annot = Annotation.objects.create(
                    document=doc,
                    corpus=self.corpus,
                    raw_text=f"V{i+1} searchable {j}",
                    creator=self.user,
                    is_public=True,
                )
                Embedding.objects.create(
                    annotation=annot,
                    embedder_path=TEST_EMBEDDER_PATH,
                    vector_384=mock_embeddings(),
                    creator=self.user,
                )

        # Time the search with version filtering
        with patch(
            "opencontractserver.llms.vector_stores.core_vector_stores.generate_embeddings_from_text"
        ) as mock_gen:
            mock_gen.return_value = (TEST_EMBEDDER_PATH, mock_embeddings())

            vector_store = CoreAnnotationVectorStore(
                corpus_id=self.corpus.id, user_id=None, embedder_path=TEST_EMBEDDER_PATH
            )

            query = VectorSearchQuery(query_text="searchable", similarity_top_k=20)

            start = time.time()
            results = vector_store.search(query)
            duration = time.time() - start

            # Should only find current version (3 annotations)
            self.assertEqual(len(results), 3)
            # Should be fast
            self.assertLess(
                duration, 0.2, f"Search took {duration:.3f}s, expected < 0.2s"
            )

            logger.info(
                f"✓ Vector search performance: {duration:.3f}s for {len(results)} results"
            )
