from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class ComprehensivePermissionTestCase(TestCase):
    def setUp(self):
        # Create users
        self.owner = User.objects.create_user(username="owner", password="password")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="password"
        )
        self.regular_user = User.objects.create_user(
            username="regular", password="password"
        )
        self.anonymous_user = None

        # Create GraphQL clients
        self.owner_client = Client(schema, context_value=TestContext(self.owner))
        self.collaborator_client = Client(
            schema, context_value=TestContext(self.collaborator)
        )
        self.regular_client = Client(
            schema, context_value=TestContext(self.regular_user)
        )
        self.anonymous_client = Client(
            schema, context_value=TestContext(AnonymousUser())
        )

        # Create Corpuses
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        self.shared_corpus = Corpus.objects.create(
            title="Shared Corpus", creator=self.owner, is_public=False
        )

        # Set permissions for shared corpus
        set_permissions_for_obj_to_user(
            self.collaborator, self.shared_corpus, [PermissionTypes.READ]
        )

        # Create Documents
        self.public_doc = Document.objects.create(
            title="Public Doc", creator=self.owner, is_public=True
        )
        self.private_doc = Document.objects.create(
            title="Private Doc", creator=self.owner, is_public=False
        )
        # Store the versioned documents returned by add_document()
        self.public_doc, _, _ = self.public_corpus.add_document(
            document=self.public_doc, user=self.owner
        )
        self.private_doc, _, _ = self.public_corpus.add_document(
            document=self.private_doc, user=self.owner
        )

        # Create Annotations
        # Mark as structural since they're in a corpus (per new permission model)
        # Include corpus field for proper permission inheritance
        self.public_annotation = Annotation.objects.create(
            document=self.public_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            is_public=True,
            structural=True,
        )
        self.private_annotation = Annotation.objects.create(
            document=self.public_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            is_public=False,
            structural=True,
        )

    def test_corpus_visibility(self):
        query = """
        query {
          corpuses {
            edges {
              node {
                id
                title
                isPublic
              }
            }
          }
        }
        """

        # Test for owner
        result = self.owner_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 3)

        # Should be 2 - the public corpus and the shared corpus with collaborator
        result = self.collaborator_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 2)

        # Test for regular user - only the public corpus
        result = self.regular_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 1)

        # Test for anonymous user - only the public corpus
        result = self.anonymous_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 1)

    def test_nested_document_visibility(self):
        query = """
        query($id: ID!) {
          corpus(id: $id) {
            documents {
              edges {
                node {
                  id
                  title
                  isPublic
                }
              }
            }
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", self.public_corpus.id)}

        # Test for owner
        result = self.owner_client.execute(query, variable_values=variables)
        self.assertEqual(len(result["data"]["corpus"]["documents"]["edges"]), 2)

        # Test for regular user
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertEqual(len(result["data"]["corpus"]["documents"]["edges"]), 1)

    def test_nested_annotation_visibility(self):
        query = """
        query($id: String!) {
          document(id: $id) {
            docAnnotations {
              edges {
                node {
                  id
                  isPublic
                }
              }
            }
          }
        }
        """
        variables = {"id": to_global_id("DocumentType", self.public_doc.id)}

        # Test for owner
        result = self.owner_client.execute(query, variable_values=variables)
        print("Result: ", result)
        self.assertEqual(len(result["data"]["document"]["docAnnotations"]["edges"]), 2)

        # Test for regular user
        # With new permission model, structural annotations are visible to anyone who can read the document
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertEqual(len(result["data"]["document"]["docAnnotations"]["edges"]), 2)

    def test_mutation_permissions(self):
        mutation = """
        mutation($id: String!) {
          deleteCorpus(id: $id) {
            ok
            message
          }
        }
        """
        corpus_to_delete = Corpus.objects.create(
            title="Corpus to Delete", creator=self.owner, is_public=True
        )

        # Deletions ARE tied to per instance permissions.
        set_permissions_for_obj_to_user(
            self.owner.id, corpus_to_delete, [PermissionTypes.CRUD]
        )
        variables = {"id": to_global_id("CorpusType", corpus_to_delete.id)}

        # Test for regular user (should fail)
        result = self.regular_client.execute(mutation, variable_values=variables)
        self.assertIsNone(result["data"]["deleteCorpus"])
        self.assertIn("errors", result)

        # Verify corpus still exists in database
        self.assertTrue(Corpus.objects.filter(id=corpus_to_delete.id).exists())

        # Test for owner (should succeed)
        result = self.owner_client.execute(mutation, variable_values=variables)

        # Verify corpus is actually deleted from database
        self.assertFalse(Corpus.objects.filter(id=corpus_to_delete.id).exists())

    def test_mutation_permissions_on_private_object(self):
        mutation = """
        mutation($id: String!) {
          deleteCorpus(id: $id) {
            ok
            message
          }
        }
        """
        private_corpus = Corpus.objects.create(
            title="Private Corpus to Delete", creator=self.owner, is_public=False
        )
        # Deletions ARE tied to per instance permissions.
        set_permissions_for_obj_to_user(
            self.owner.id, private_corpus, [PermissionTypes.CRUD]
        )
        variables = {"id": to_global_id("CorpusType", private_corpus.id)}

        # Test for collaborator (should fail)
        result = self.collaborator_client.execute(mutation, variable_values=variables)
        self.assertIsNone(result["data"]["deleteCorpus"])
        self.assertIn("errors", result)

        # Verify corpus still exists in database
        self.assertTrue(Corpus.objects.filter(id=private_corpus.id).exists())

        # Test for owner (should succeed)
        result = self.owner_client.execute(mutation, variable_values=variables)
        self.assertTrue(result["data"]["deleteCorpus"]["ok"])

        # Verify corpus is actually deleted from database
        self.assertFalse(Corpus.objects.filter(id=private_corpus.id).exists())

    def test_permission_change_effect(self):
        query = """
        query($id: ID!) {
          corpus(id: $id) {
            id
            title
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", self.private_corpus.id)}

        # Before granting permission
        result = self.collaborator_client.execute(query, variable_values=variables)
        self.assertIsNone(result["data"]["corpus"])

        # Grant permission
        set_permissions_for_obj_to_user(
            self.collaborator, self.private_corpus, [PermissionTypes.READ]
        )

        # After granting permission
        result = self.collaborator_client.execute(query, variable_values=variables)
        self.assertIsNotNone(result["data"]["corpus"])
        self.assertEqual(result["data"]["corpus"]["title"], "Private Corpus")

    def test_public_flag_change_effect(self):
        query = """
        query($id: ID!) {
          corpus(id: $id) {
            id
            title
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", self.private_corpus.id)}

        # Before making public
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertIsNone(result["data"]["corpus"])

        # Make corpus public
        self.private_corpus.is_public = True
        self.private_corpus.save()

        # After making public
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertIsNotNone(result["data"]["corpus"])
        self.assertEqual(result["data"]["corpus"]["title"], "Private Corpus")
