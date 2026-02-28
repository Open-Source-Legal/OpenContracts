import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from graphene.test import Client
from graphql_relay import from_global_id, to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

User = get_user_model()

logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class AnnotationTreeTestCase(TestCase):

    maxDiff = None  # Add this line at the class level

    def setUp(self):
        # Create a test user
        # Setup a test user
        with transaction.atomic():
            self.user = User.objects.create_user(username="bob", password="12345678")
        logger.info(f"Created test user: {self.user}")

        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.client = Client(schema, context_value=TestContext(self.user))

        logger.info("Created test clients")

        # Create test data
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        original_doc = Document.objects.create(title="Test Document", creator=self.user)
        self.document, _, _ = self.corpus.add_document(
            document=original_doc, user=self.user
        )
        self.annotation_label = AnnotationLabel.objects.create(
            text="Test Label", creator=self.user
        )

        # Create a hierarchy of annotations
        self.root_annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.annotation_label,
            raw_text="Root Annotation",
            creator=self.user,
            parent=None,  # Root annotation has no parent
        )

        self.child_annotation_1 = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.annotation_label,
            raw_text="Child Annotation 1",
            creator=self.user,
            parent=self.root_annotation,
        )

        self.child_annotation_2 = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.annotation_label,
            raw_text="Child Annotation 2",
            creator=self.user,
            parent=self.root_annotation,
        )

        self.grandchild_annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.annotation_label,
            raw_text="Grandchild Annotation",
            creator=self.user,
            parent=self.child_annotation_1,
        )

    def test_descendants_tree(self):
        # Construct the GraphQL query
        query = """
        query($id: ID!) {
            annotation(id: $id) {
                id
                descendantsTree
            }
        }
        """
        variables = {"id": to_global_id("AnnotationType", self.root_annotation.id)}

        # Execute the query
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        # Access the returned tree directly
        descendants_tree = result["data"]["annotation"]["descendantsTree"]

        # Expected flat list of descendants with immediate children's IDs
        expected_descendants_tree = [
            {
                "id": to_global_id("AnnotationType", self.child_annotation_1.id),
                "raw_text": "Child Annotation 1",
                "children": [
                    to_global_id("AnnotationType", self.grandchild_annotation.id)
                ],
            },
            {
                "id": to_global_id("AnnotationType", self.child_annotation_2.id),
                "raw_text": "Child Annotation 2",
                "children": [],
            },
            {
                "id": to_global_id("AnnotationType", self.grandchild_annotation.id),
                "raw_text": "Grandchild Annotation",
                "children": [],
            },
        ]

        self.assertEqual(descendants_tree, expected_descendants_tree)

    def test_full_tree(self):
        # Test with grandchild annotation
        query = """
        query($id: ID!) {
            annotation(id: $id) {
                id
                fullTree
            }
        }
        """
        variables = {
            "id": to_global_id("AnnotationType", self.grandchild_annotation.id)
        }

        # Execute the query
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        # Access the returned tree directly
        full_tree = result["data"]["annotation"]["fullTree"]

        # Expected flat list of full tree with immediate children's IDs
        expected_full_tree = [
            {
                "id": to_global_id("AnnotationType", self.root_annotation.id),
                "raw_text": "Root Annotation",
                "children": [
                    to_global_id("AnnotationType", self.child_annotation_1.id),
                    to_global_id("AnnotationType", self.child_annotation_2.id),
                ],
            },
            {
                "id": to_global_id("AnnotationType", self.child_annotation_1.id),
                "raw_text": "Child Annotation 1",
                "children": [
                    to_global_id("AnnotationType", self.grandchild_annotation.id)
                ],
            },
            {
                "id": to_global_id("AnnotationType", self.child_annotation_2.id),
                "raw_text": "Child Annotation 2",
                "children": [],
            },
            {
                "id": to_global_id("AnnotationType", self.grandchild_annotation.id),
                "raw_text": "Grandchild Annotation",
                "children": [],
            },
        ]

        self.assertEqual(full_tree, expected_full_tree)

    def test_stress_test(self):
        # Programmatically create a large tree with at least 1000 annotations
        total_nodes = 0
        max_nodes = 1000

        # Create the root annotation
        root_annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.annotation_label,
            raw_text="Root Annotation",
            creator=self.user,
            parent=None,
        )
        total_nodes += 1

        # Level order traversal to build a balanced binary tree
        current_level = [root_annotation]

        while total_nodes < max_nodes:
            next_level = []
            for parent_annotation in current_level:
                # Create left child
                left_child = Annotation.objects.create(
                    document=self.document,
                    corpus=self.corpus,
                    annotation_label=self.annotation_label,
                    raw_text=f"Annotation {total_nodes + 1}",
                    creator=self.user,
                    parent=parent_annotation,
                )
                total_nodes += 1
                next_level.append(left_child)

                if total_nodes >= max_nodes:
                    break

                # Create right child
                right_child = Annotation.objects.create(
                    document=self.document,
                    corpus=self.corpus,
                    annotation_label=self.annotation_label,
                    raw_text=f"Annotation {total_nodes + 1}",
                    creator=self.user,
                    parent=parent_annotation,
                )
                total_nodes += 1
                next_level.append(right_child)

                if total_nodes >= max_nodes:
                    break
            current_level = next_level

        # Test the descendants_tree resolver
        query = """
        query($id: ID!) {
            annotation(id: $id) {
                id
                descendantsTree
            }
        }
        """
        variables = {"id": to_global_id("AnnotationType", root_annotation.id)}

        # Execute the query
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        # Access the returned tree directly
        descendants_tree = result["data"]["annotation"]["descendantsTree"]

        # Since we can't manually create the expected output for 1000 nodes,
        # we'll test that the number of returned nodes matches the total nodes minus 1 (excluding root)
        self.assertEqual(len(descendants_tree), total_nodes - 1)

        # Optionally, test a few known nodes
        # For example, check that the first child of the root is correct
        first_child_id = descendants_tree[0]["id"]
        first_child_annotation = Annotation.objects.get(
            id=from_global_id(first_child_id)[1]
        )
        self.assertEqual(first_child_annotation.parent_id, root_annotation.id)

        # Test the full_tree resolver
        query = """
        query($id: ID!) {
            annotation(id: $id) {
                id
                fullTree
            }
        }
        """
        variables = {"id": to_global_id("AnnotationType", root_annotation.id)}

        # Execute the query
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        # Access the returned tree directly
        full_tree = result["data"]["annotation"]["fullTree"]

        # Test that the number of nodes in full_tree matches total_nodes
        self.assertEqual(len(full_tree), total_nodes)

        # Assert that the root is correctly included
        root_node = next(
            (
                node
                for node in full_tree
                if node["id"] == to_global_id("AnnotationType", root_annotation.id)
            ),
            None,
        )
        self.assertIsNotNone(root_node)
        self.assertEqual(root_node["raw_text"], "Root Annotation")
        self.assertEqual(
            len(root_node["children"]), 2
        )  # Root should have two children in a balanced binary tree

    def test_mid_node_subtree_and_descendants(self):
        # Create a balanced binary tree with 20 nodes
        total_nodes = 0
        max_nodes = 20

        # Create the root annotation
        root_annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.annotation_label,
            raw_text="Root Annotation",
            creator=self.user,
            parent=None,
        )
        total_nodes += 1

        # Level order traversal to build a balanced binary tree
        current_level = [root_annotation]

        while total_nodes < max_nodes:
            next_level = []
            for parent_annotation in current_level:
                # Create left child
                left_child = Annotation.objects.create(
                    document=self.document,
                    corpus=self.corpus,
                    annotation_label=self.annotation_label,
                    raw_text=f"Annotation {total_nodes + 1}",
                    creator=self.user,
                    parent=parent_annotation,
                )
                total_nodes += 1
                next_level.append(left_child)

                if total_nodes >= max_nodes:
                    break

                # Create right child
                right_child = Annotation.objects.create(
                    document=self.document,
                    corpus=self.corpus,
                    annotation_label=self.annotation_label,
                    raw_text=f"Annotation {total_nodes + 1}",
                    creator=self.user,
                    parent=parent_annotation,
                )
                total_nodes += 1
                next_level.append(right_child)

                if total_nodes >= max_nodes:
                    break
            current_level = next_level

        # Pick a mid-level node (e.g., node with raw_text="Annotation 10")
        mid_node = Annotation.objects.get(raw_text="Annotation 10")

        # Test the descendants_tree resolver
        query = """
        query($id: ID!) {
            annotation(id: $id) {
                id
                descendantsTree
            }
        }
        """
        variables = {"id": to_global_id("AnnotationType", mid_node.id)}

        # Execute the query
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        # Access the returned tree directly
        descendants_tree = result["data"]["annotation"]["descendantsTree"]

        # Expected number of descendants (excluding the mid_node itself)
        expected_descendants_count = Annotation.objects.filter(
            id__in=self.get_descendant_ids(mid_node)
        ).count()

        self.assertEqual(len(descendants_tree), expected_descendants_count)

        # Test the subtree resolver
        query = """
        query($id: ID!) {
            annotation(id: $id) {
                id
                subtree
            }
        }
        """
        variables = {"id": to_global_id("AnnotationType", mid_node.id)}

        # Execute the query
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        # Access the returned tree directly
        subtree = result["data"]["annotation"]["subtree"]

        # Calculate expected number of nodes in subtree (ancestors + mid_node + descendants)
        expected_subtree_count = (
            len(self.get_ancestor_ids(mid_node)) + 1 + expected_descendants_count
        )

        self.assertEqual(len(subtree), expected_subtree_count)

        # Ensure that root_annotation is included in the subtree
        root_node = next(
            (
                node
                for node in subtree
                if node["id"] == to_global_id("AnnotationType", root_annotation.id)
            ),
            None,
        )
        self.assertIsNotNone(root_node)

    def get_descendant_ids(self, node):
        """
        Helper method to get all descendant IDs of a given node.
        """
        from django_cte import CTE, with_cte

        def get_descendants(cte):
            base_qs = Annotation.objects.filter(parent_id=node.id).values("id")
            recursive_qs = cte.join(Annotation, parent_id=cte.col.id).values("id")
            return base_qs.union(recursive_qs, all=True)

        cte = CTE.recursive(get_descendants)
        descendants_qs = with_cte(cte, select=cte.queryset())
        descendant_ids = [item["id"] for item in descendants_qs.values("id")]
        return descendant_ids

    def get_ancestor_ids(self, node):
        """
        Helper method to get all ancestor IDs of a given node.
        """
        ancestors = []
        while node.parent_id is not None:
            node = node.parent
            ancestors.append(node.id)
        return ancestors
