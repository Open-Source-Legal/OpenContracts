from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.files import base_64_encode_bytes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class DocumentMutationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.client = Client(schema, context_value=TestContext(self.user))

    def test_upload_document_mutation(self):
        mutation = """
            mutation UploadDocument(
                $file: String!,
                $filename: String!,
                $title: String!,
                $description: String!,
                $customMeta: GenericScalar!,
                $addToCorpusId: ID,
                $makePublic: Boolean!
            ) {
                uploadDocument(
                    base64FileString: $file,
                    filename: $filename,
                    title: $title,
                    description: $description,
                    customMeta: $customMeta,
                    makePublic: $makePublic,
                    addToCorpusId: $addToCorpusId
                ) {
                    ok
                    message
                    document {
                        id
                        title
                        description
                    }
                }
            }
        """  # noqa

        # Create a mock PDF content
        pdf_content = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
        pdf_base64 = base_64_encode_bytes(pdf_content)

        variables = {
            "file": pdf_base64,
            "filename": "test.pdf",
            "title": "Test PDF",
            "description": "A test PDF file",
            "makePublic": False,
            "customMeta": {"key": "value"},
        }

        with patch(
            "opencontractserver.documents.models.Document.objects.create"
        ) as mock_create:
            mock_create.return_value = Document(
                id=1, title="Test PDF", description="A test PDF file"
            )
            result = self.client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["uploadDocument"]["ok"])
        self.assertEqual(result["data"]["uploadDocument"]["message"], "Success")
        self.assertEqual(
            result["data"]["uploadDocument"]["document"]["title"], "Test PDF"
        )

    def test_upload_txt_document(self):
        mutation = """
            mutation UploadDocument(
                $file: String!,
                $filename: String!,
                $title: String!,
                $description: String!,
                $customMeta: GenericScalar!,
                $addToCorpusId: ID,
                $makePublic: Boolean!
            ) {
                uploadDocument(
                    base64FileString: $file,
                    filename: $filename,
                    title: $title,
                    description: $description,
                    customMeta: $customMeta,
                    addToCorpusId: $addToCorpusId,
                    makePublic: $makePublic
                ) {
                    ok
                    message
                    document {
                        id
                        title
                    }
                }
            }
        """  # noqa

        # Create a mock text file content
        txt_content = b"This is a text file."
        txt_base64 = base_64_encode_bytes(txt_content)

        variables = {
            "file": txt_base64,
            "filename": "test.txt",
            "title": "Test TXT",
            "description": "A test TXT file",
            "makePublic": False,
            "customMeta": {},
        }

        result = self.client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["uploadDocument"]["ok"])

    def test_upload_zip_document(self):
        mutation = """
            mutation UploadDocument(
                $file: String!,
                $filename: String!,
                $title: String!,
                $description: String!,
                $customMeta: GenericScalar!,
                $addToCorpusId: ID,
                $makePublic: Boolean!
            ) {
                uploadDocument(
                    base64FileString: $file,
                    filename: $filename,
                    title: $title,
                    description: $description,
                    customMeta: $customMeta,
                    addToCorpusId: $addToCorpusId,
                    makePublic: $makePublic
                ) {
                    ok
                    message
                    document {
                        id
                        title
                    }
                }
            }
        """  # noqa

        # Create a mock ZIP file content
        zip_content = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"  # Minimal ZIP file header
        zip_base64 = base_64_encode_bytes(zip_content)

        variables = {
            "file": zip_base64,
            "filename": "test.zip",
            "title": "Test ZIP",
            "description": "A test ZIP file",
            "makePublic": False,
            "customMeta": {},
        }

        result = self.client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["uploadDocument"]["ok"])
        self.assertEqual(
            result["data"]["uploadDocument"]["message"],
            "Unallowed filetype: application/zip",
        )

    def test_update_document_mutation(self):
        # First, create a document
        document = Document(
            creator=self.user,
            title="Original Title",
            description="Original Description",
            pdf_file="path/to/original.pdf",
        )
        document.save()
        set_permissions_for_obj_to_user(self.user, document, [PermissionTypes.CRUD])
        doc_id = to_global_id("DocumentType", document.id)

        mutation = """
            mutation UpdateDocument($id: String!, $title: String, $description: String, $pdfFile: String) {
                updateDocument(
                    id: $id,
                    title: $title,
                    description: $description,
                    pdfFile: $pdfFile
                ) {
                    ok
                    message
                }
            }
        """

        # Update title and description
        variables = {
            "id": str(doc_id),
            "title": "Updated Title",
            "description": "Updated Description",
        }

        result = self.client.execute(mutation, variables=variables)

        document.refresh_from_db()

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateDocument"]["ok"])
        self.assertEqual(document.title, "Updated Title")
        self.assertEqual(document.description, "Updated Description")

        # Update PDF file
        pdf_content = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
        new_pdf_base64 = base_64_encode_bytes(pdf_content)

        variables = {
            "id": str(doc_id),
            "pdfFile": new_pdf_base64,
        }
        result = self.client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateDocument"]["ok"])
        # You might want to add more assertions here to check if the PDF file was actually updated

    def test_delete_document_mutation(self):
        # First, create a document
        document = Document(
            creator=self.user,
            title="Document to Delete",
            description="This document will be deleted",
            pdf_file="path/to/delete.pdf",
        )
        document.save()
        set_permissions_for_obj_to_user(self.user, document, [PermissionTypes.CRUD])
        doc_id = to_global_id("DocumentType", document.id)

        mutation = """
            mutation DeleteDocument($id: String!) {
                deleteDocument(id: $id) {
                    ok
                    message
                }
            }
        """

        variables = {
            "id": str(doc_id),
        }

        result = self.client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteDocument"]["ok"])
        self.assertEqual(result["data"]["deleteDocument"]["message"], "Success!")

        # Verify that the document was actually deleted
        with self.assertRaises(Document.DoesNotExist):
            Document.objects.get(id=document.id)

    def test_document_summary_creation_and_editing(self):
        """Create a new markdown summary for a document and then update it, validating version increments."""

        # Create corpus and link a document to it
        from opencontractserver.corpuses.models import Corpus

        corpus = Corpus.objects.create(title="Summary Corpus", creator=self.user)
        document = Document.objects.create(
            creator=self.user,
            title="Summary Test Doc",
            description="Testing summary mutation",
        )
        corpus.add_document(document=document, user=self.user)

        doc_gid = to_global_id("DocumentType", document.id)
        corpus_gid = to_global_id("CorpusType", corpus.id)

        mutation = """
            mutation UpdateDocumentSummary($documentId: ID!, $corpusId: ID!, $newContent: String!) {
              updateDocumentSummary(
                documentId: $documentId,
                corpusId: $corpusId,
                newContent: $newContent
              ) {
                ok
                message
                version
                obj {
                  id
                  summaryContent(corpusId: $corpusId)
                  currentSummaryVersion(corpusId: $corpusId)
                }
              }
            }
        """

        # --- Create initial summary ---
        variables = {
            "documentId": doc_gid,
            "corpusId": corpus_gid,
            "newContent": "Initial summary content.",
        }
        result = self.client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        res_data = result["data"]["updateDocumentSummary"]
        self.assertTrue(res_data["ok"])
        self.assertEqual(res_data["version"], 1)
        self.assertEqual(res_data["obj"]["summaryContent"], "Initial summary content.")
        self.assertEqual(res_data["obj"]["currentSummaryVersion"], 1)

        # --- Update existing summary ---
        variables["newContent"] = "Updated summary content."
        result = self.client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        res_data = result["data"]["updateDocumentSummary"]
        self.assertTrue(res_data["ok"])
        self.assertEqual(res_data["version"], 2)
        self.assertEqual(res_data["obj"]["summaryContent"], "Updated summary content.")
        self.assertEqual(res_data["obj"]["currentSummaryVersion"], 2)

        # --- No-change update should not create a new version ---
        result = self.client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        res_data = result["data"]["updateDocumentSummary"]
        self.assertTrue(res_data["ok"])
        # Version should stay at 2 since content did not change
        self.assertEqual(res_data["version"], 2)
