"""
Tests for PDF file hash field in GraphQL API.
"""

import hashlib
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from graphene_django.utils.testing import GraphQLTestCase

from opencontractserver.documents.models import Document

User = get_user_model()


class PDFHashGraphQLTestCase(GraphQLTestCase):
    """Test cases for PDF hash field in GraphQL API."""

    GRAPHQL_URL = "http://localhost:8000/graphql/"

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create a simple PDF-like bytes content for testing
        self.pdf_content = b"%PDF-1.4\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>endobj\n"
        self.pdf_hash = hashlib.sha256(self.pdf_content).hexdigest()

        # Create a document with PDF and hash
        pdf_file = SimpleUploadedFile(
            "test.pdf", self.pdf_content, content_type="application/pdf"
        )

        self.document = Document.objects.create(
            title="Test Document",
            creator=self.user,
            pdf_file=pdf_file,
            pdf_file_hash=self.pdf_hash,
            is_public=True,  # Make it public so we can query it
        )

    def test_pdf_file_hash_field_in_document_query(self):
        """Test that pdf_file_hash field is available in DocumentType GraphQL query."""
        query = """
            query GetDocument($id: String!) {
                document(id: $id) {
                    id
                    title
                    pdfFileHash
                    pdfFile
                }
            }
        """

        # Convert Django ID to GraphQL ID
        from graphql_relay import to_global_id

        global_id = to_global_id("DocumentType", self.document.id)

        response = self.query(query, variables={"id": global_id})

        # Check response structure
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)

        # Verify the hash field is present and correct
        self.assertIn("data", content)
        self.assertIn("document", content["data"])
        self.assertEqual(content["data"]["document"]["title"], "Test Document")
        self.assertEqual(content["data"]["document"]["pdfFileHash"], self.pdf_hash)

    def test_documents_query_includes_pdf_file_hash(self):
        """Test that pdf_file_hash is included when querying multiple documents."""
        query = """
            query GetDocuments {
                documents {
                    edges {
                        node {
                            id
                            title
                            pdfFileHash
                        }
                    }
                }
            }
        """

        response = self.query(query)

        # Check response structure
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)

        # Verify at least one document has the hash
        edges = content["data"]["documents"]["edges"]
        self.assertGreater(len(edges), 0)

        # Find our test document
        test_doc = None
        for edge in edges:
            if edge["node"]["title"] == "Test Document":
                test_doc = edge["node"]
                break

        self.assertIsNotNone(test_doc)
        self.assertEqual(test_doc["pdfFileHash"], self.pdf_hash)

    def test_document_without_hash(self):
        """Test that documents without hash return null for pdfFileHash field."""
        # Create document without PDF
        doc_no_pdf = Document.objects.create(
            title="Document without PDF", creator=self.user, is_public=True
        )

        query = """
            query GetDocument($id: String!) {
                document(id: $id) {
                    id
                    title
                    pdfFileHash
                }
            }
        """

        from graphql_relay import to_global_id

        global_id = to_global_id("DocumentType", doc_no_pdf.id)

        response = self.query(query, variables={"id": global_id})

        self.assertResponseNoErrors(response)
        content = json.loads(response.content)

        # Should return null for pdfFileHash
        self.assertIsNone(content["data"]["document"]["pdfFileHash"])
