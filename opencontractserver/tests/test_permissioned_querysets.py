from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation, Note
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    generate_permissions_md_table_for_object,
    set_permissions_for_obj_to_user,
)

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

        # Create Documents (inherits corpus permissions)
        self.public_doc = Document.objects.create(
            title="Public Doc", creator=self.owner, is_public=True
        )
        self.private_doc = Document.objects.create(
            title="Private Doc", creator=self.owner, is_public=False
        )
        self.public_corpus.documents.add(self.public_doc, self.private_doc)

        # Create Annotations (inherits corpus permissions)
        self.public_annotation = Annotation.objects.create(
            document=self.public_doc,
            creator=self.owner,
            is_public=True,
            corpus=self.public_corpus,
        )
        self.private_annotation_public_corpus = Annotation.objects.create(
            document=self.public_doc,
            creator=self.owner,
            is_public=False,
            corpus=self.public_corpus,
        )
        self.private_annotation = Annotation.objects.create(
            document=self.public_doc,
            creator=self.owner,
            is_public=False,
            corpus=self.private_corpus,
        )

        # Create Notes (inherits corpus permissions)
        self.public_note = Note.objects.create(
            document=self.public_doc,
            creator=self.owner,
            is_public=True,
            corpus=self.public_corpus,
            title="Public Note",
            content="Public content",
        )

        # This is a private note, but it is in a public corpus.
        self.private_note_public_corpus = Note.objects.create(
            document=self.public_doc,
            creator=self.owner,
            is_public=False,
            corpus=self.public_corpus,
            title="Private Note",
            content="Private content",
        )
        self.private_note = Note.objects.create(
            document=self.public_doc,
            creator=self.owner,
            is_public=False,
            corpus=self.private_corpus,
            title="Private Note",
            content="Private content",
        )

        # Create Conversations (does NOT inherit corpus permissions)
        self.public_conversation = Conversation.objects.create(
            title="Public Conversation",
            creator=self.owner,
            is_public=True,
            chat_with_corpus=self.public_corpus,
        )
        self.private_conversation = Conversation.objects.create(
            title="Private Conversation",
            creator=self.owner,
            is_public=False,
            chat_with_corpus=self.public_corpus,
        )

        # Create ChatMessages (does NOT inherit corpus permissions)
        self.public_message = ChatMessage.objects.create(
            conversation=self.public_conversation,
            creator=self.owner,
            is_public=True,
            content="Public message",
        )
        self.private_message = ChatMessage.objects.create(
            conversation=self.private_conversation,
            creator=self.owner,
            is_public=False,
            content="Private message",
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

        # Test for collaborator
        result = self.collaborator_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 2)  # Public + Shared

        # Test for regular user
        result = self.regular_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 1)  # Only Public

        # Test for anonymous user
        result = self.anonymous_client.execute(query)
        print(f"test_corpus_visibility: {result}")
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 1)  # Only Public

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
        print(f"test_nested_document_visibility: {result}")

        self.assertEqual(len(result["data"]["corpus"]["documents"]["edges"]), 2)

        # Test for regular user
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertEqual(
            len(result["data"]["corpus"]["documents"]["edges"]), 1
        )  # Only Public

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
        print(f"test_nested_annotation_visibility: {result}")

        self.assertEqual(len(result["data"]["document"]["docAnnotations"]["edges"]), 3)

        # Test for regular user
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertEqual(
            len(result["data"]["document"]["docAnnotations"]["edges"]), 2
        )  # Only Public

    def test_notes_visibility(self):
        query = """
        query {
          notes {
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
        self.assertEqual(len(result["data"]["notes"]["edges"]), 3)  # Both notes

        print(
            generate_permissions_md_table_for_object(
                [self.regular_user, self.collaborator, self.owner], self.public_note
            )
        )
        print(
            generate_permissions_md_table_for_object(
                [self.regular_user, self.collaborator, self.owner], self.private_note
            )
        )

        # Test for regular user
        result = self.regular_client.execute(query)
        self.assertEqual(len(result["data"]["notes"]["edges"]), 2)  # Only Public

    def test_conversations_visibility(self):
        query = """
        query {
          conversations {
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
        print(f"test_conversations_visibility: {result}")
        self.assertEqual(
            len(result["data"]["conversations"]["edges"]), 2
        )  # Both conversations

        # Test for regular user
        result = self.regular_client.execute(query)
        self.assertEqual(
            len(result["data"]["conversations"]["edges"]), 1
        )  # Only Public

    def test_corpus_permission_inheritance(self):
        """Test that models correctly inherit or don't inherit corpus permissions"""
        # Grant collaborator access to private_corpus
        set_permissions_for_obj_to_user(
            self.collaborator, self.private_corpus, [PermissionTypes.READ]
        )

        # Create private objects in private_corpus
        private_doc = Document.objects.create(
            title="Private Doc in Private Corpus", creator=self.owner, is_public=False
        )
        self.private_corpus.documents.add(private_doc)

        Annotation.objects.create(
            document=private_doc,
            creator=self.owner,
            is_public=False,
            corpus=self.private_corpus,
        )

        Note.objects.create(
            document=private_doc,
            creator=self.owner,
            is_public=False,
            corpus=self.private_corpus,
            title="Private Note in Private Corpus",
            content="Private content",
        )

        Conversation.objects.create(
            title="Private Conversation in Private Corpus",
            creator=self.owner,
            is_public=False,
            chat_with_corpus=self.private_corpus,
        )

        # Test document visibility (should inherit corpus permissions)
        doc_query = """
        query {
          documents {
            edges {
              node {
                id
                title
              }
            }
          }
        }
        """
        result = self.collaborator_client.execute(doc_query)
        print(f"test_corpus_permission_inheritance: {result}")

        doc_titles = [
            edge["node"]["title"] for edge in result["data"]["documents"]["edges"]
        ]
        self.assertNotIn("Private Doc in Private Corpus", doc_titles)

        # Test annotation visibility (should inherit corpus permissions)
        annotation_query = """
        query {
          annotations {
            edges {
              node {
                id
                document {
                  title
                }
              }
            }
          }
        }
        """
        result = self.collaborator_client.execute(annotation_query)
        print(f"test_corpus_permission_inheritance: {result}")
        doc_titles = [
            edge["node"]["document"]["title"]
            for edge in result["data"]["annotations"]["edges"]
            if edge["node"]["document"]
        ]
        self.assertIn("Private Doc in Private Corpus", doc_titles)

        # Test note visibility (should inherit corpus permissions)
        note_query = """
        query {
          notes {
            edges {
              node {
                id
                title
              }
            }
          }
        }
        """
        result = self.collaborator_client.execute(note_query)
        print(f"test_corpus_permission_inheritance notes: {result}")
        note_titles = [
            edge["node"]["title"] for edge in result["data"]["notes"]["edges"]
        ]
        self.assertIn("Private Note in Private Corpus", note_titles)

        # Test conversation visibility (should NOT inherit corpus permissions)
        conversation_query = """
        query {
          conversations {
            edges {
              node {
                id
                title
              }
            }
          }
        }
        """
        result = self.collaborator_client.execute(conversation_query)
        conversation_titles = [
            edge["node"]["title"] for edge in result["data"]["conversations"]["edges"]
        ]
        self.assertNotIn("Private Conversation in Private Corpus", conversation_titles)

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

        variables = {"id": to_global_id("CorpusType", corpus_to_delete.id)}

        print(
            generate_permissions_md_table_for_object(
                [self.regular_user, self.collaborator, self.owner], corpus_to_delete
            )
        )

        # Test for regular user (should fail)
        result = self.regular_client.execute(mutation, variable_values=variables)
        print(f"test_mutation_permissions: {result}")
        self.assertIsNone(result["data"]["deleteCorpus"])
        self.assertIn("errors", result)

        # Verify corpus still exists in database
        self.assertTrue(Corpus.objects.filter(id=corpus_to_delete.id).exists())

        # Deletions ARE tied to per instance permissions.
        set_permissions_for_obj_to_user(
            self.regular_user, corpus_to_delete, [PermissionTypes.CRUD]
        )

        print(
            generate_permissions_md_table_for_object(
                [self.regular_user, self.collaborator, self.owner], corpus_to_delete
            )
        )

        # Test for regular user (should fail)
        result = self.regular_client.execute(mutation, variable_values=variables)

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
        print(f"test_mutation_permissions_on_private_object: {result}")
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
