"""
Test DocumentRelationship CRUD mutations.

This module tests the GraphQL mutations for creating, updating, and deleting
DocumentRelationship objects.
"""

import logging

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentRelationship,
)
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class DocumentRelationshipMutationTestCase(TestCase):
    """Test DocumentRelationship CRUD mutations."""

    def setUp(self):
        """Set up test data."""
        # Create users
        self.owner = User.objects.create_user(username="owner", password="test")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test"
        )
        self.outsider = User.objects.create_user(username="outsider", password="test")

        # Create GraphQL clients for each user
        self.owner_client = Client(schema, context_value=TestContext(self.owner))
        self.collaborator_client = Client(
            schema, context_value=TestContext(self.collaborator)
        )
        self.outsider_client = Client(schema, context_value=TestContext(self.outsider))

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=False,
        )

        # Create test documents
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            description="Source document",
            custom_meta={},
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            description="Target document",
            custom_meta={},
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        # Create test annotation label
        self.annotation_label = AnnotationLabel.objects.create(
            text="Test Relationship Label",
            label_type="RELATIONSHIP_LABEL",
            creator=self.owner,
        )

        # Add documents to corpus (required for DocumentRelationship)
        # Add documents to corpus via DocumentPath
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/source_doc_{self.source_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/target_doc_{self.target_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Set permissions for owner
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Set read-only permissions for collaborator
        set_permissions_for_obj_to_user(
            self.collaborator, self.source_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.target_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.READ]
        )

        # Outsider gets nothing

    def test_create_document_relationship_as_owner(self):
        """Test that owner can create a document relationship."""
        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!,
                $annotationLabelId: String
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId,
                    annotationLabelId: $annotationLabelId
                ) {
                    ok
                    message
                    documentRelationship {
                        id
                        relationshipType
                        sourceDocument {
                            id
                        }
                        targetDocument {
                            id
                        }
                        annotationLabel {
                            id
                        }
                        corpus {
                            id
                        }
                    }
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", self.source_doc.id),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "RELATIONSHIP",
            "annotationLabelId": to_global_id(
                "AnnotationLabelType", self.annotation_label.id
            ),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertTrue(data["ok"])
        self.assertIsNotNone(data["documentRelationship"])
        self.assertEqual(
            data["documentRelationship"]["relationshipType"], "RELATIONSHIP"
        )
        self.assertEqual(
            data["documentRelationship"]["sourceDocument"]["id"],
            to_global_id("DocumentType", self.source_doc.id),
        )
        self.assertEqual(
            data["documentRelationship"]["targetDocument"]["id"],
            to_global_id("DocumentType", self.target_doc.id),
        )

    def test_create_notes_type_without_label(self):
        """Test that NOTES type relationship can be created without annotation_label."""
        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!,
                $data: GenericScalar
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId,
                    data: $data
                ) {
                    ok
                    message
                    documentRelationship {
                        id
                        relationshipType
                        data
                    }
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", self.source_doc.id),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "NOTES",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "data": {"note": "Test note content"},
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertTrue(data["ok"])
        self.assertIsNotNone(data["documentRelationship"])
        self.assertEqual(data["documentRelationship"]["relationshipType"], "NOTES")
        self.assertEqual(
            data["documentRelationship"]["data"], {"note": "Test note content"}
        )

    def test_create_relationship_type_requires_label(self):
        """Test that RELATIONSHIP type requires annotation_label_id."""
        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId
                ) {
                    ok
                    message
                    documentRelationship {
                        id
                    }
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", self.source_doc.id),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "RELATIONSHIP",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("annotation_label_id is required", data["message"])

    def test_create_relationship_without_permission_fails(self):
        """Test that outsider cannot create a document relationship."""
        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId
                ) {
                    ok
                    message
                    documentRelationship {
                        id
                    }
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", self.source_doc.id),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "NOTES",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = self.outsider_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertFalse(data["ok"])
        # IDOR protection: same message for not found or no permission
        self.assertIn("not found", data["message"].lower())

    def test_collaborator_read_only_cannot_create(self):
        """Test that collaborator with only READ permission cannot create."""
        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", self.source_doc.id),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "NOTES",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = self.collaborator_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertFalse(data["ok"])
        # IDOR protection: same message for not found or no permission
        self.assertIn("not found", data["message"].lower())

    def test_create_relationship_docs_not_in_corpus_fails(self):
        """Test that creating a relationship fails if documents aren't in the corpus."""
        # Create a different corpus without the documents
        other_corpus = Corpus.objects.create(
            title="Other Corpus",
            creator=self.owner,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.owner, other_corpus, [PermissionTypes.CRUD]
        )

        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", self.source_doc.id),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "NOTES",
            "corpusId": to_global_id("CorpusType", other_corpus.id),
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("same corpus", data["message"].lower())


class DocumentRelationshipUpdateMutationTestCase(TestCase):
    """Test DocumentRelationship update mutations."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test"
        )

        self.owner_client = Client(schema, context_value=TestContext(self.owner))
        self.collaborator_client = Client(
            schema, context_value=TestContext(self.collaborator)
        )

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=False,
        )

        # Create test documents
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        # Create test annotation label
        self.annotation_label = AnnotationLabel.objects.create(
            text="Test Relationship Label",
            label_type="RELATIONSHIP_LABEL",
            creator=self.owner,
        )

        # Add documents to corpus (required for DocumentRelationship)
        # Add documents to corpus via DocumentPath
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/source_doc_{self.source_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/target_doc_{self.target_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create existing relationship
        # Note: DocumentRelationship inherits permissions from source_doc,
        # target_doc, and corpus - no guardian permissions on relationship itself
        self.relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"note": "Original note"},
            creator=self.owner,
            corpus=self.corpus,
        )

        # Set permissions for owner on documents and corpus
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Collaborator gets read-only on documents and corpus
        # This means they can READ relationships but not UPDATE/DELETE
        set_permissions_for_obj_to_user(
            self.collaborator, self.source_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.target_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.READ]
        )

    def test_update_document_relationship_as_owner(self):
        """Test that owner can update a document relationship."""
        mutation = """
            mutation UpdateDocRel(
                $documentRelationshipId: String!,
                $data: GenericScalar
            ) {
                updateDocumentRelationship(
                    documentRelationshipId: $documentRelationshipId,
                    data: $data
                ) {
                    ok
                    message
                    documentRelationship {
                        id
                        data
                    }
                }
            }
        """

        variables = {
            "documentRelationshipId": to_global_id(
                "DocumentRelationshipType", self.relationship.id
            ),
            "data": {"note": "Updated note"},
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["updateDocumentRelationship"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["documentRelationship"]["data"], {"note": "Updated note"})

    def test_update_relationship_without_permission_fails(self):
        """Test that collaborator with only READ permission cannot update.

        Permission Model: DocumentRelationship inherits permissions from source_doc,
        target_doc, and corpus. Collaborator has READ-only on these, so they can
        see the relationship but cannot UPDATE it. Returns explicit permission denied.
        """
        mutation = """
            mutation UpdateDocRel(
                $documentRelationshipId: String!,
                $data: GenericScalar
            ) {
                updateDocumentRelationship(
                    documentRelationshipId: $documentRelationshipId,
                    data: $data
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "documentRelationshipId": to_global_id(
                "DocumentRelationshipType", self.relationship.id
            ),
            "data": {"note": "Unauthorized update"},
        }

        result = self.collaborator_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["updateDocumentRelationship"]
        self.assertFalse(data["ok"])
        # Collaborator can see relationship but lacks UPDATE permission
        self.assertIn("permission", data["message"].lower())

    def test_update_relationship_type_validates_label(self):
        """Test that changing to RELATIONSHIP type requires annotation_label."""
        mutation = """
            mutation UpdateDocRel(
                $documentRelationshipId: String!,
                $relationshipType: String
            ) {
                updateDocumentRelationship(
                    documentRelationshipId: $documentRelationshipId,
                    relationshipType: $relationshipType
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "documentRelationshipId": to_global_id(
                "DocumentRelationshipType", self.relationship.id
            ),
            "relationshipType": "RELATIONSHIP",
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["updateDocumentRelationship"]
        # Should fail because RELATIONSHIP type requires annotation_label
        self.assertFalse(data["ok"])


class DocumentRelationshipDeleteMutationTestCase(TestCase):
    """Test DocumentRelationship delete mutations."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.outsider = User.objects.create_user(username="outsider", password="test")

        self.owner_client = Client(schema, context_value=TestContext(self.owner))
        self.outsider_client = Client(schema, context_value=TestContext(self.outsider))

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=False,
        )

        # Create test documents
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        # Add documents to corpus (required for DocumentRelationship)
        # Add documents to corpus via DocumentPath
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/source_doc_{self.source_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/target_doc_{self.target_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create existing relationship
        # Note: DocumentRelationship inherits permissions from source_doc,
        # target_doc, and corpus - no guardian permissions on relationship itself
        self.relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"note": "Test note"},
            creator=self.owner,
            corpus=self.corpus,
        )

        # Set permissions on documents and corpus (relationships inherit from these)
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

    def test_delete_document_relationship_as_owner(self):
        """Test that owner can delete a document relationship."""
        relationship_id = self.relationship.id

        mutation = """
            mutation DeleteDocRel($documentRelationshipId: String!) {
                deleteDocumentRelationship(
                    documentRelationshipId: $documentRelationshipId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "documentRelationshipId": to_global_id(
                "DocumentRelationshipType", relationship_id
            ),
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["deleteDocumentRelationship"]
        self.assertTrue(data["ok"])

        # Verify it's deleted
        self.assertFalse(
            DocumentRelationship.objects.filter(pk=relationship_id).exists()
        )

    def test_delete_relationship_without_permission_fails(self):
        """Test that outsider cannot delete a document relationship.

        IDOR Protection: Returns "not found" for both non-existent AND inaccessible
        resources to prevent attackers from discovering what exists.
        """
        mutation = """
            mutation DeleteDocRel($documentRelationshipId: String!) {
                deleteDocumentRelationship(
                    documentRelationshipId: $documentRelationshipId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "documentRelationshipId": to_global_id(
                "DocumentRelationshipType", self.relationship.id
            ),
        }

        result = self.outsider_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["deleteDocumentRelationship"]
        self.assertFalse(data["ok"])
        # IDOR protection: same "not found" message for inaccessible as non-existent
        self.assertIn("not found", data["message"].lower())

        # Verify it still exists
        self.assertTrue(
            DocumentRelationship.objects.filter(pk=self.relationship.id).exists()
        )

    def test_delete_multiple_document_relationships(self):
        """Test bulk delete of document relationships."""
        # Create additional relationship
        # Note: No guardian permissions needed - inherits from source_doc, target_doc, corpus
        relationship2 = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"note": "Second note"},
            creator=self.owner,
            corpus=self.corpus,
        )

        mutation = """
            mutation DeleteDocRels($documentRelationshipIds: [String]!) {
                deleteDocumentRelationships(
                    documentRelationshipIds: $documentRelationshipIds
                ) {
                    ok
                    message
                    deletedCount
                }
            }
        """

        variables = {
            "documentRelationshipIds": [
                to_global_id("DocumentRelationshipType", self.relationship.id),
                to_global_id("DocumentRelationshipType", relationship2.id),
            ],
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["deleteDocumentRelationships"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["deletedCount"], 2)

        # Verify both are deleted
        self.assertFalse(
            DocumentRelationship.objects.filter(
                pk__in=[self.relationship.id, relationship2.id]
            ).exists()
        )


class DocumentRelationshipValidationTestCase(TestCase):
    """Test DocumentRelationship validation scenarios."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.owner_client = Client(schema, context_value=TestContext(self.owner))

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=False,
        )

        # Create test documents
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            pdf_file=pdf_file,
            backend_lock=True,
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            pdf_file=pdf_file,
            backend_lock=True,
        )

        # Create annotation label
        self.annotation_label = AnnotationLabel.objects.create(
            text="Test Label",
            label_type="RELATIONSHIP_LABEL",
            creator=self.owner,
        )

        # Add documents to corpus (required for DocumentRelationship)
        # Add documents to corpus via DocumentPath
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/source_doc_{self.source_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/target_doc_{self.target_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Set permissions
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

    def test_invalid_relationship_type_rejected(self):
        """Test that invalid relationship_type is rejected."""
        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", self.source_doc.id),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "INVALID_TYPE",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("Invalid relationship_type", data["message"])

    def test_nonexistent_source_document_rejected(self):
        """Test that nonexistent source document is rejected."""
        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", 99999),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "NOTES",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_nonexistent_annotation_label_rejected(self):
        """Test that nonexistent annotation label is rejected."""
        mutation = """
            mutation CreateDocRel(
                $sourceDocumentId: String!,
                $targetDocumentId: String!,
                $relationshipType: String!,
                $corpusId: String!,
                $annotationLabelId: String
            ) {
                createDocumentRelationship(
                    sourceDocumentId: $sourceDocumentId,
                    targetDocumentId: $targetDocumentId,
                    relationshipType: $relationshipType,
                    corpusId: $corpusId,
                    annotationLabelId: $annotationLabelId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "sourceDocumentId": to_global_id("DocumentType", self.source_doc.id),
            "targetDocumentId": to_global_id("DocumentType", self.target_doc.id),
            "relationshipType": "RELATIONSHIP",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "annotationLabelId": to_global_id("AnnotationLabelType", 99999),
        }

        result = self.owner_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createDocumentRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())


class DocumentRelationshipServiceTestCase(TestCase):
    """Test DocumentRelationshipService methods for coverage."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.outsider = User.objects.create_user(username="outsider", password="test")

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=False,
        )

        # Create test documents
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        # Create annotation label
        self.annotation_label = AnnotationLabel.objects.create(
            text="Test Label",
            label_type="RELATIONSHIP_LABEL",
            creator=self.owner,
        )

        # Add documents to corpus
        # Add documents to corpus via DocumentPath
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/source_doc_{self.source_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/target_doc_{self.target_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create test relationships
        # Note: DocumentRelationship inherits permissions from source_doc,
        # target_doc, and corpus - no guardian permissions on relationship itself
        self.relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="RELATIONSHIP",
            annotation_label=self.annotation_label,
            creator=self.owner,
            corpus=self.corpus,
        )

        self.note = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"note": "Test note"},
            creator=self.owner,
            corpus=self.corpus,
        )

        # Set permissions on documents and corpus (relationships inherit from these)
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )

    def test_get_visible_relationships_with_source_filter(self):
        """Test filtering by source_document_id."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_visible_relationships(
            user=self.owner,
            source_document_id=self.source_doc.id,
        )
        self.assertEqual(result.count(), 2)

    def test_get_visible_relationships_with_target_filter(self):
        """Test filtering by target_document_id."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_visible_relationships(
            user=self.owner,
            target_document_id=self.target_doc.id,
        )
        self.assertEqual(result.count(), 2)

    def test_get_visible_relationships_with_corpus_filter(self):
        """Test filtering by corpus_id."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_visible_relationships(
            user=self.owner,
            corpus_id=self.corpus.id,
        )
        self.assertEqual(result.count(), 2)

    def test_get_visible_relationships_with_type_filter(self):
        """Test filtering by relationship_type."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_visible_relationships(
            user=self.owner,
            relationship_type="RELATIONSHIP",
        )
        self.assertEqual(result.count(), 1)
        self.assertEqual(result[0].relationship_type, "RELATIONSHIP")

    def test_get_relationships_for_document_nonexistent(self):
        """Test with nonexistent document returns empty queryset."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationships_for_document(
            user=self.owner,
            document_id=99999,
        )
        self.assertEqual(result.count(), 0)

    def test_get_relationships_for_document_no_permission(self):
        """Test with document user can't access returns empty queryset."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationships_for_document(
            user=self.outsider,
            document_id=self.source_doc.id,
        )
        self.assertEqual(result.count(), 0)

    def test_get_relationships_for_document_as_source_only(self):
        """Test include_as_source=True, include_as_target=False."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationships_for_document(
            user=self.owner,
            document_id=self.source_doc.id,
            include_as_source=True,
            include_as_target=False,
        )
        self.assertEqual(result.count(), 2)

    def test_get_relationships_for_document_as_target_only(self):
        """Test include_as_source=False, include_as_target=True."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationships_for_document(
            user=self.owner,
            document_id=self.target_doc.id,
            include_as_source=False,
            include_as_target=True,
        )
        self.assertEqual(result.count(), 2)

    def test_get_relationships_for_document_neither_source_nor_target(self):
        """Test include_as_source=False, include_as_target=False returns empty."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationships_for_document(
            user=self.owner,
            document_id=self.source_doc.id,
            include_as_source=False,
            include_as_target=False,
        )
        self.assertEqual(result.count(), 0)

    def test_get_relationships_for_document_with_corpus_filter(self):
        """Test filtering by corpus_id."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationships_for_document(
            user=self.owner,
            document_id=self.source_doc.id,
            corpus_id=self.corpus.id,
        )
        self.assertEqual(result.count(), 2)

        # Test with wrong corpus returns empty
        result = DocumentRelationshipService.get_relationships_for_document(
            user=self.owner,
            document_id=self.source_doc.id,
            corpus_id=99999,
        )
        self.assertEqual(result.count(), 0)

    def test_get_relationship_by_id_success(self):
        """Test getting a single relationship by ID."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationship_by_id(
            user=self.owner,
            relationship_id=self.relationship.id,
        )
        assert result is not None
        self.assertEqual(result.id, self.relationship.id)

    def test_get_relationship_by_id_not_found(self):
        """Test getting nonexistent relationship returns None."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationship_by_id(
            user=self.owner,
            relationship_id=99999,
        )
        self.assertIsNone(result)

    def test_get_relationship_by_id_no_permission(self):
        """Test getting relationship without permission returns None."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.get_relationship_by_id(
            user=self.outsider,
            relationship_id=self.relationship.id,
        )
        self.assertIsNone(result)

    def test_user_has_permission_read(self):
        """Test user_has_permission for READ permission."""
        from opencontractserver.documents.services import DocumentRelationshipService

        # Owner has READ permission (inherits from docs/corpus)
        result = DocumentRelationshipService.user_has_permission(
            user=self.owner,
            doc_relationship=self.relationship,
            permission_type="READ",
        )
        self.assertTrue(result)

        # Outsider has no permission
        result = DocumentRelationshipService.user_has_permission(
            user=self.outsider,
            doc_relationship=self.relationship,
            permission_type="READ",
        )
        self.assertFalse(result)

    def test_user_has_permission_update(self):
        """Test user_has_permission for UPDATE permission."""
        from opencontractserver.documents.services import DocumentRelationshipService

        # Owner has UPDATE permission
        result = DocumentRelationshipService.user_has_permission(
            user=self.owner,
            doc_relationship=self.relationship,
            permission_type="UPDATE",
        )
        self.assertTrue(result)

    def test_user_has_permission_delete(self):
        """Test user_has_permission for DELETE permission."""
        from opencontractserver.documents.services import DocumentRelationshipService

        # Owner has DELETE permission
        result = DocumentRelationshipService.user_has_permission(
            user=self.owner,
            doc_relationship=self.relationship,
            permission_type="DELETE",
        )
        self.assertTrue(result)

    def test_user_has_permission_invalid_type(self):
        """Test user_has_permission with invalid permission type returns False."""
        from opencontractserver.documents.services import DocumentRelationshipService

        result = DocumentRelationshipService.user_has_permission(
            user=self.owner,
            doc_relationship=self.relationship,
            permission_type="INVALID",
        )
        self.assertFalse(result)


class DocumentRelationshipInheritedPermissionTestCase(TestCase):
    """
    Test that DocumentRelationship correctly inherits permissions from
    source_document + target_document + corpus.

    This is the key test suite to prevent regressions on the permission model.
    """

    def setUp(self):
        """Set up test data with clear permission hierarchy."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test"
        )
        self.outsider = User.objects.create_user(username="outsider", password="test")

        # Create GraphQL clients
        self.owner_client = Client(schema, context_value=TestContext(self.owner))
        self.collaborator_client = Client(
            schema, context_value=TestContext(self.collaborator)
        )
        self.outsider_client = Client(schema, context_value=TestContext(self.outsider))

        # Create test corpus (private)
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.owner,
            is_public=False,
        )

        # Create test documents (private)
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.owner,
            title="Source Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        self.target_doc = Document.objects.create(
            creator=self.owner,
            title="Target Doc",
            pdf_file=pdf_file,
            backend_lock=True,
            is_public=False,
        )

        # Add documents to corpus
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/source_doc_{self.source_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.owner,
            path=f"/target_doc_{self.target_doc.id}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create relationship
        self.relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"note": "Test note"},
            creator=self.owner,
            corpus=self.corpus,
        )

        # Owner gets CRUD on everything
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(
            self.owner, self.source_doc, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.owner, self.target_doc, [PermissionTypes.CRUD]
        )

        # Collaborator gets READ-only on everything
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.source_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.target_doc, [PermissionTypes.READ]
        )

        # Outsider gets nothing

    def test_collaborator_can_see_relationship_via_query(self):
        """Test that collaborator with READ permission can query relationships."""
        query = """
            query GetDocRelationships($documentId: ID) {
                documentRelationships(documentId: $documentId) {
                    edges {
                        node {
                            id
                            relationshipType
                        }
                    }
                }
            }
        """

        variables = {"documentId": to_global_id("DocumentType", self.source_doc.id)}

        result = self.collaborator_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        edges = result["data"]["documentRelationships"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["node"]["relationshipType"], "NOTES")

    def test_outsider_cannot_see_relationship_via_query(self):
        """Test that outsider without permission cannot see relationships."""
        query = """
            query GetDocRelationships($documentId: ID) {
                documentRelationships(documentId: $documentId) {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """

        variables = {"documentId": to_global_id("DocumentType", self.source_doc.id)}

        result = self.outsider_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        edges = result["data"]["documentRelationships"]["edges"]
        self.assertEqual(len(edges), 0)

    def test_collaborator_can_see_but_cannot_delete(self):
        """Test collaborator can see relationship but cannot delete it."""
        # First verify they can see it
        query = """
            query GetDocRelationship($id: ID!) {
                documentRelationship(id: $id) {
                    id
                    relationshipType
                }
            }
        """

        variables = {
            "id": to_global_id("DocumentRelationshipType", self.relationship.id)
        }

        result = self.collaborator_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertIsNotNone(result["data"]["documentRelationship"])

        # Now try to delete - should fail with permission error
        mutation = """
            mutation DeleteDocRel($documentRelationshipId: String!) {
                deleteDocumentRelationship(
                    documentRelationshipId: $documentRelationshipId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "documentRelationshipId": to_global_id(
                "DocumentRelationshipType", self.relationship.id
            )
        }

        result = self.collaborator_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["deleteDocumentRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("permission", data["message"].lower())

        # Verify relationship still exists
        self.assertTrue(
            DocumentRelationship.objects.filter(pk=self.relationship.id).exists()
        )

    def test_partial_document_permission_blocks_visibility(self):
        """Test that missing permission on ONE document blocks relationship visibility."""
        from opencontractserver.documents.services import DocumentRelationshipService

        # Create a user with permission on source_doc but NOT target_doc
        partial_user = User.objects.create_user(username="partial", password="test")
        set_permissions_for_obj_to_user(
            partial_user, self.source_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            partial_user, self.corpus, [PermissionTypes.READ]
        )
        # No permission on target_doc

        # Should not be able to see the relationship
        result = DocumentRelationshipService.get_visible_relationships(
            user=partial_user
        )
        self.assertEqual(result.count(), 0)

    def test_missing_corpus_permission_blocks_visibility(self):
        """Test that missing corpus permission blocks relationship visibility."""
        from opencontractserver.documents.services import DocumentRelationshipService

        # Create a user with permission on documents but NOT corpus
        no_corpus_user = User.objects.create_user(username="nocorpus", password="test")
        set_permissions_for_obj_to_user(
            no_corpus_user, self.source_doc, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            no_corpus_user, self.target_doc, [PermissionTypes.READ]
        )
        # No permission on corpus

        # Should not be able to see the relationship
        result = DocumentRelationshipService.get_visible_relationships(
            user=no_corpus_user
        )
        self.assertEqual(result.count(), 0)
