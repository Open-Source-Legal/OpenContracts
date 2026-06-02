import logging

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class PermissionFilteringTestCase(TestCase):
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(username="user1", password="password1")
        self.user2 = User.objects.create_user(username="user2", password="password2")
        # A no-grant superuser. Under the scoped-admin contract (2026-05) a
        # superuser is authorized over data like a normal user, so this admin is
        # a "stranger" to user1/user2's private labels and must NOT see them.
        # Username is class-unique to avoid colliding with other test classes'
        # superusers under xdist.
        self.superuser = User.objects.create_superuser(
            username="perm_filter_admin", password="adminpass"
        )

        # Create GraphQL clients
        self.client1 = Client(schema, context_value=TestContext(self.user1))
        self.client2 = Client(schema, context_value=TestContext(self.user2))
        self.client_super = Client(schema, context_value=TestContext(self.superuser))

        # Create test data
        self.corpus1 = Corpus.objects.create(title="Corpus 1", creator=self.user1)
        self.corpus2 = Corpus.objects.create(title="Corpus 2", creator=self.user2)

        self.document1 = Document.objects.create(title="Document 1", creator=self.user1)
        self.document2 = Document.objects.create(title="Document 2", creator=self.user2)

        self.label1 = AnnotationLabel.objects.create(text="Label 1", creator=self.user1)
        self.label2 = AnnotationLabel.objects.create(text="Label 2", creator=self.user2)

        self.annotation1 = Annotation.objects.create(
            document=self.document1, annotation_label=self.label1, creator=self.user1
        )
        self.annotation2 = Annotation.objects.create(
            document=self.document2, annotation_label=self.label2, creator=self.user2
        )

        # Set permissions
        set_permissions_for_obj_to_user(
            self.user1, self.corpus1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user1, self.document1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(self.user1, self.label1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            self.user1, self.annotation1, [PermissionTypes.READ]
        )

        set_permissions_for_obj_to_user(
            self.user2, self.corpus2, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user2, self.document2, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(self.user2, self.label2, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            self.user2, self.annotation2, [PermissionTypes.READ]
        )

    def test_corpus_permission_filtering(self):
        query = """
        query {
            corpuses {
                edges {
                    node {
                        id
                        title
                    }
                }
            }
        }
        """

        # Test for user1
        # Each user now also has a personal corpus (auto-created on user creation)
        result1 = self.client1.execute(query)
        self.assertEqual(
            len(result1["data"]["corpuses"]["edges"]), 2
        )  # corpus1 + personal
        titles1 = [
            edge["node"]["title"] for edge in result1["data"]["corpuses"]["edges"]
        ]
        self.assertIn("Corpus 1", titles1)

        # Test for user2
        # Each user now also has a personal corpus (auto-created on user creation)
        result2 = self.client2.execute(query)
        self.assertEqual(
            len(result2["data"]["corpuses"]["edges"]), 2
        )  # corpus2 + personal
        titles2 = [
            edge["node"]["title"] for edge in result2["data"]["corpuses"]["edges"]
        ]
        self.assertIn("Corpus 2", titles2)

    def test_document_permission_filtering(self):
        query = """
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

        # Test for user1
        result1 = self.client1.execute(query)
        self.assertEqual(len(result1["data"]["documents"]["edges"]), 1)
        self.assertEqual(
            result1["data"]["documents"]["edges"][0]["node"]["title"], "Document 1"
        )

        # Test for user2
        result2 = self.client2.execute(query)
        self.assertEqual(len(result2["data"]["documents"]["edges"]), 1)
        self.assertEqual(
            result2["data"]["documents"]["edges"][0]["node"]["title"], "Document 2"
        )

    def test_annotation_label_permission_filtering(self):
        query = """
        query {
            annotationLabels {
                edges {
                    node {
                        id
                        text
                    }
                }
            }
        }
        """

        def _label_texts(result):
            return {
                edge["node"]["text"]
                for edge in result["data"]["annotationLabels"]["edges"]
            }

        # Test for user1: sees its OWN private label, never user2's private one.
        # Membership (not exact count) keeps the assertion robust to unrelated
        # public/seed labels that other parallel tests may make visible — the
        # permission-filtering contract under test is "a user never sees another
        # user's PRIVATE label".
        texts1 = _label_texts(self.client1.execute(query))
        self.assertIn("Label 1", texts1)
        self.assertNotIn("Label 2", texts1)

        # Test for user2: mirror.
        texts2 = _label_texts(self.client2.execute(query))
        self.assertIn("Label 2", texts2)
        self.assertNotIn("Label 1", texts2)

        # No-grant superuser is computed like a stranger: sees NEITHER private
        # label (no blanket superuser bypass for data visibility, 2026-05).
        texts_super = _label_texts(self.client_super.execute(query))
        self.assertNotIn("Label 1", texts_super)
        self.assertNotIn("Label 2", texts_super)

    def test_annotation_permission_filtering(self):
        query = """
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

        # Test for user1
        result1 = self.client1.execute(query)
        self.assertEqual(len(result1["data"]["annotations"]["edges"]), 1)
        self.assertEqual(
            result1["data"]["annotations"]["edges"][0]["node"]["document"]["title"],
            "Document 1",
        )

        # Test for user2
        result2 = self.client2.execute(query)
        self.assertEqual(len(result2["data"]["annotations"]["edges"]), 1)
        self.assertEqual(
            result2["data"]["annotations"]["edges"][0]["node"]["document"]["title"],
            "Document 2",
        )

    def test_nested_permission_filtering(self):
        query = """
        query {
            corpuses {
                edges {
                    node {
                        id
                        title
                        documents {
                            edges {
                                node {
                                    id
                                    title
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        # Add documents to corpuses using add_document (corpus isolation)
        doc1_copy, _, _ = self.corpus1.add_document(
            document=self.document1, user=self.user1
        )
        doc2_copy, _, _ = self.corpus2.add_document(
            document=self.document2, user=self.user2
        )

        # Test for user1
        # Each user now also has a personal corpus (auto-created on user creation)
        result1 = self.client1.execute(query)
        self.assertEqual(
            len(result1["data"]["corpuses"]["edges"]), 2
        )  # corpus1 + personal
        # Find corpus1 in the results (not the personal corpus)
        corpus1_edge = next(
            (
                e
                for e in result1["data"]["corpuses"]["edges"]
                if e["node"]["title"] == "Corpus 1"
            ),
            None,
        )
        assert corpus1_edge is not None
        self.assertEqual(len(corpus1_edge["node"]["documents"]["edges"]), 1)
        self.assertEqual(
            corpus1_edge["node"]["documents"]["edges"][0]["node"]["title"],
            "Document 1",
        )

        # Test for user2
        # Each user now also has a personal corpus (auto-created on user creation)
        result2 = self.client2.execute(query)
        self.assertEqual(
            len(result2["data"]["corpuses"]["edges"]), 2
        )  # corpus2 + personal
        # Find corpus2 in the results (not the personal corpus)
        corpus2_edge = next(
            (
                e
                for e in result2["data"]["corpuses"]["edges"]
                if e["node"]["title"] == "Corpus 2"
            ),
            None,
        )
        assert corpus2_edge is not None
        self.assertEqual(len(corpus2_edge["node"]["documents"]["edges"]), 1)
        self.assertEqual(
            corpus2_edge["node"]["documents"]["edges"][0]["node"]["title"],
            "Document 2",
        )

    def test_permission_change(self):
        query = """
        query {
            corpuses {
                edges {
                    node {
                        id
                        title
                    }
                }
            }
        }
        """

        # Initial test for user2
        # Each user now also has a personal corpus (auto-created on user creation)
        result1 = self.client2.execute(query)
        self.assertEqual(
            len(result1["data"]["corpuses"]["edges"]), 2
        )  # corpus2 + personal
        titles1 = [
            edge["node"]["title"] for edge in result1["data"]["corpuses"]["edges"]
        ]
        self.assertIn("Corpus 2", titles1)

        # Grant permission to user2 for corpus1
        set_permissions_for_obj_to_user(
            self.user2, self.corpus1, [PermissionTypes.READ]
        )

        # Test again for user2 - permission grant above SHOULD have affected the result
        result2 = self.client2.execute(query)
        self.assertEqual(
            len(result2["data"]["corpuses"]["edges"]), 3
        )  # corpus1 + corpus2 + personal
        titles = [
            edge["node"]["title"] for edge in result2["data"]["corpuses"]["edges"]
        ]
        self.assertIn("Corpus 2", titles)
        self.assertIn("Corpus 1", titles)
