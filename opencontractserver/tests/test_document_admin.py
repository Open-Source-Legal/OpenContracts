import logging
import random

from django.test import Client, TestCase
from django.urls import reverse

from opencontractserver.annotations.models import Embedding
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


def random_vector(dimension: int = 384, seed: int = 42):
    """
    Generates a random vector of the specified dimension. Fixed seed for consistency.
    """
    rng = random.Random(seed)
    return [rng.random() for _ in range(dimension)]


class TestDocumentAdmin(TestCase):
    """
    Tests for the Document admin configuration, focusing on:
      - Inline Embeddings
      - total_embeddings annotation
      - Displaying dimension info
    """

    superuser: User
    corpus: Corpus
    document: Document
    document2: Document
    embedding_384: Embedding
    embedding2_384: Embedding
    embedding2_768: Embedding

    @classmethod
    def setUpTestData(cls):
        # Create a superuser so we can access the admin
        cls.superuser = User.objects.create_superuser(
            username="test_admin",
            email="test_admin@example.com",
            password="adminpass",
        )

        # Create a corpus
        cls.corpus = Corpus.objects.create(title="Test Corpus", creator=cls.superuser)

        # Create a document with one embedding
        original_doc = Document.objects.create(
            title="Test Document",
            creator=cls.superuser,
            is_public=True,
        )
        cls.document, _, _ = cls.corpus.add_document(
            document=original_doc, user=cls.superuser
        )
        # Create the Embedding
        cls.embedding_384 = Embedding.objects.create(
            document=cls.document,
            annotation=None,
            note=None,
            embedder_path="doc-embedder",
            creator=cls.superuser,
            vector_384=random_vector(),
        )

        # Create a second document that has multiple embeddings of different dimensions
        original_doc2 = Document.objects.create(
            title="Document with Multiple Embeddings",
            creator=cls.superuser,
            is_public=True,
        )
        cls.document2, _, _ = cls.corpus.add_document(
            document=original_doc2, user=cls.superuser
        )
        # 2 embeddings for document2 with different dimensions
        cls.embedding2_384 = Embedding.objects.create(
            document=cls.document2,
            embedder_path="doc-embedder-384",
            creator=cls.superuser,
            vector_384=random_vector(dimension=384, seed=123),
        )
        cls.embedding2_768 = Embedding.objects.create(
            document=cls.document2,
            embedder_path="doc-embedder-768",
            creator=cls.superuser,
            vector_768=random_vector(dimension=768, seed=999),
        )

    def setUp(self) -> None:
        self.client = Client()
        self.client.login(username="test_admin", password="adminpass")

    def test_document_list_display_and_inline_count(self):
        """
        Check that list_display fields appear, including 'total_embeddings',
        and that inline embeddings are properly visible on the change page.
        """
        url = reverse("admin:documents_document_changelist")
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, 200, "Could not access Document changelist."
        )

        self.assertContains(response, "Test Document")
        self.assertContains(response, "Document with Multiple Embeddings")
        self.assertContains(
            response, ">1</td>", msg_prefix="Should display total_embeddings=1"
        )
        self.assertContains(
            response, ">2</td>", msg_prefix="Should display total_embeddings=2"
        )

        document_change_url = reverse(
            "admin:documents_document_change", args=[self.document2.pk]
        )
        resp_change = self.client.get(document_change_url)
        self.assertEqual(
            resp_change.status_code,
            200,
            f"Could not access Document change page: {document_change_url}",
        )

        # Check that both embedder paths appear in the inline
        content_text = resp_change.content.decode("utf-8")
        self.assertIn(
            "doc-embedder-384", content_text, "First embedder path should be visible"
        )
        self.assertIn(
            "doc-embedder-768", content_text, "Second embedder path should be visible"
        )

    def test_embedding_dimension_display(self):
        """
        Ensure the dimension column is properly computed in the inline (TabularInline)
        by verifying that dimensions are recognized in the dimension() method.
        """
        # Go to the Document change view for the second document with multiple embeddings
        url = reverse("admin:documents_document_change", args=[self.document2.pk])
        response = self.client.get(url)
        self.assertEqual(
            response.status_code,
            200,
            f"Could not access document change page for the document ID={self.document2.pk}.",
        )

        # We expect to see both "384" and "768" if the dimension method recognized both vectors
        self.assertContains(
            response,
            "384",
            msg_prefix="Should display 384 as one of the recognized embedding dimensions",
        )
        self.assertContains(
            response,
            "768",
            msg_prefix="Should display 768 as one of the recognized embedding dimensions",
        )

    def test_embedding_admin_document_reference_type(self):
        """
        Test the EmbeddingAdmin to ensure that:
          - reference_type shows "Document #<id>" for document embeddings
          - dimension_info shows the correct dimension(s) that are populated
        """
        # Go to the Embedding changelist
        emb_changelist_url = reverse("admin:annotations_embedding_changelist")
        response = self.client.get(emb_changelist_url)
        self.assertEqual(
            response.status_code, 200, "Could not access Embedding changelist."
        )

        # Each embedding should appear with reference_type
        # document 1 => "Document #<pk>"
        # document 2 => "Document #<pk>" (appears twice for two embeddings)
        self.assertContains(response, f"Document #{self.document.pk}")
        self.assertContains(response, f"Document #{self.document2.pk}")

        # Check dimension_info
        self.assertContains(response, "384")
        self.assertContains(response, "768")

    def test_document_admin_permissions(self):
        """
        Ensures the superuser can access, add, change, and delete documents.
        This confirms that the GuardedModelAdmin setup doesn't block superuser.
        """
        add_url = reverse("admin:documents_document_add")
        response = self.client.get(add_url)
        self.assertEqual(
            response.status_code,
            200,
            "Could not access document add page as superuser.",
        )

        # Create a document directly using model API
        from django.db import transaction

        try:
            with transaction.atomic():
                original_doc = Document.objects.create(
                    title="Created from admin test",
                    creator=self.superuser,
                    is_public=True,
                )
                document, _, _ = self.corpus.add_document(
                    document=original_doc, user=self.superuser
                )
                document_id = document.id

                # Now verify that the document exists via admin
                detail_url = reverse(
                    "admin:documents_document_change", args=[document_id]
                )
                get_resp = self.client.get(detail_url)

                # Check we can view the document
                self.assertEqual(
                    get_resp.status_code, 200, "Could not view created document."
                )
                self.assertContains(get_resp, "Created from admin test")
        except Exception as e:
            self.fail(f"Failed to create document: {e}")

        # Confirm that the object actually got created in the DB
        self.assertTrue(
            Document.objects.filter(title="Created from admin test").exists(),
            "Document was not actually created in the database.",
        )

    def test_document_with_multiple_dimension_embeddings(self):
        """
        Test that a document with embeddings of different dimensions
        correctly displays all dimensions in the admin.
        """
        # Create a document with embeddings of different dimensions
        original_multi_dim_doc = Document.objects.create(
            title="Document with Multiple Dimension Embeddings",
            creator=self.superuser,
            is_public=True,
        )
        multi_dim_doc, _, _ = self.corpus.add_document(
            document=original_multi_dim_doc, user=self.superuser
        )

        # Create embeddings with different dimensions
        Embedding.objects.create(
            document=multi_dim_doc,
            embedder_path="doc-embedder-384",
            creator=self.superuser,
            vector_384=random_vector(dimension=384),
        )
        Embedding.objects.create(
            document=multi_dim_doc,
            embedder_path="doc-embedder-768",
            creator=self.superuser,
            vector_768=random_vector(dimension=768),
        )
        Embedding.objects.create(
            document=multi_dim_doc,
            embedder_path="doc-embedder-1536",
            creator=self.superuser,
            vector_1536=random_vector(dimension=1536),
        )

        # Go to the document change page
        url = reverse("admin:documents_document_change", args=[multi_dim_doc.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Check that all dimensions are displayed
        self.assertContains(response, "384")
        self.assertContains(response, "768")
        self.assertContains(response, "1536")

        # Check the total embeddings count
        changelist_url = reverse("admin:documents_document_changelist")
        list_response = self.client.get(changelist_url)
        self.assertEqual(list_response.status_code, 200)

        # The document should have 3 embeddings
        content = list_response.content.decode("utf-8")
        doc_row = content.split(f">{multi_dim_doc.title}<")[1].split("</tr>")[0]
        self.assertIn(">3<", doc_row, "Should display total_embeddings=3")
