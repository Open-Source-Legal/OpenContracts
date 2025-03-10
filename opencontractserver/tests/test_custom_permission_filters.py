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

        # Create GraphQL clients
        self.client1 = Client(schema, context_value=TestContext(self.user1))
        self.client2 = Client(schema, context_value=TestContext(self.user2))

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
        result1 = self.client1.execute(query)
        self.assertEqual(len(result1["data"]["corpuses"]["edges"]), 1)
        self.assertEqual(
            result1["data"]["corpuses"]["edges"][0]["node"]["title"], "Corpus 1"
        )

        # Test for user2
        result2 = self.client2.execute(query)
        self.assertEqual(len(result2["data"]["corpuses"]["edges"]), 1)
        self.assertEqual(
            result2["data"]["corpuses"]["edges"][0]["node"]["title"], "Corpus 2"
        )

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

        # Test for user1
        result1 = self.client1.execute(query)
        self.assertEqual(len(result1["data"]["annotationLabels"]["edges"]), 1)
        self.assertEqual(
            result1["data"]["annotationLabels"]["edges"][0]["node"]["text"], "Label 1"
        )

        # Test for user2
        result2 = self.client2.execute(query)
        self.assertEqual(len(result2["data"]["annotationLabels"]["edges"]), 1)
        self.assertEqual(
            result2["data"]["annotationLabels"]["edges"][0]["node"]["text"], "Label 2"
        )

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

        # Add documents to corpuses
        self.corpus1.documents.add(self.document1)
        self.corpus2.documents.add(self.document2)

        # Test for user1
        result1 = self.client1.execute(query)
        self.assertEqual(len(result1["data"]["corpuses"]["edges"]), 1)
        self.assertEqual(
            len(result1["data"]["corpuses"]["edges"][0]["node"]["documents"]["edges"]),
            1,
        )
        self.assertEqual(
            result1["data"]["corpuses"]["edges"][0]["node"]["documents"]["edges"][0][
                "node"
            ]["title"],
            "Document 1",
        )

        # Test for user2
        result2 = self.client2.execute(query)
        self.assertEqual(len(result2["data"]["corpuses"]["edges"]), 1)
        self.assertEqual(
            len(result2["data"]["corpuses"]["edges"][0]["node"]["documents"]["edges"]),
            1,
        )
        self.assertEqual(
            result2["data"]["corpuses"]["edges"][0]["node"]["documents"]["edges"][0][
                "node"
            ]["title"],
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
        result1 = self.client2.execute(query)
        self.assertEqual(len(result1["data"]["corpuses"]["edges"]), 1)
        self.assertEqual(
            result1["data"]["corpuses"]["edges"][0]["node"]["title"], "Corpus 2"
        )

        # Grant permission to user2 for corpus1
        set_permissions_for_obj_to_user(
            self.user2, self.corpus1, [PermissionTypes.READ]
        )

        # Test again for user2
        # NOTE - we ARE NOW filtering on per-instance level permissions, so preceding permission change will affect
        # returned values.
        result2 = self.client2.execute(query)
        self.assertEqual(len(result2["data"]["corpuses"]["edges"]), 2)
        titles = [
            edge["node"]["title"] for edge in result2["data"]["corpuses"]["edges"]
        ]
        self.assertIn("Corpus 2", titles)
        self.assertIn("Corpus 1", titles)
