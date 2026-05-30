"""
Tests for SmartLabelSearchOrCreateMutation and SmartLabelListMutation.

These mutations provide intelligent label creation with automatic labelset management.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import LabelType, PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    """Mock context for GraphQL client."""

    def __init__(self, user):
        self.user = user


class SmartLabelMutationTestCase(TestCase):
    """Test cases for smart label mutations."""

    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", password="otherpassword"
        )

        # Create GraphQL client
        self.client = Client(schema, context_value=TestContext(self.user))
        self.other_client = Client(schema, context_value=TestContext(self.other_user))

        # Create test corpus WITHOUT labelset
        self.corpus_without_labelset = Corpus.objects.create(
            title="Corpus Without Labelset",
            description="Test corpus without labelset",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus_without_labelset, [PermissionTypes.CRUD]
        )

        # Create test corpus WITH labelset
        self.labelset = LabelSet.objects.create(
            title="Test Labelset",
            description="Test labelset",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.labelset, [PermissionTypes.CRUD]
        )

        self.corpus_with_labelset = Corpus.objects.create(
            title="Corpus With Labelset",
            description="Test corpus with labelset",
            creator=self.user,
            label_set=self.labelset,
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus_with_labelset, [PermissionTypes.CRUD]
        )

        # Create existing label in labelset
        self.existing_label = AnnotationLabel.objects.create(
            text="Existing Label",
            description="An existing label",
            label_type=LabelType.SPAN_LABEL,
            color="#FF0000",
            creator=self.user,
        )
        self.labelset.annotation_labels.add(self.existing_label)

    def test_smart_label_create_with_existing_labelset(self):
        """Test creating a new label when labelset already exists."""
        mutation = """
            mutation SmartLabelSearchOrCreate(
                $corpusId: String!
                $searchTerm: String!
                $labelType: String!
                $color: String
                $description: String
                $createIfNotFound: Boolean
            ) {
                smartLabelSearchOrCreate(
                    corpusId: $corpusId
                    searchTerm: $searchTerm
                    labelType: $labelType
                    color: $color
                    description: $description
                    createIfNotFound: $createIfNotFound
                ) {
                    ok
                    message
                    labelCreated
                    labelsetCreated
                    labels {
                        id
                        text
                        color
                        labelType
                    }
                    labelset {
                        id
                        title
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_with_labelset.id),
            "searchTerm": "New Test Label",
            "labelType": LabelType.SPAN_LABEL.value,
            "color": "#0000FF",
            "description": "A new test label",
            "createIfNotFound": True,
        }

        result = self.client.execute(mutation, variables=variables)

        # Assert no errors
        self.assertIsNone(result.get("errors"))

        # Assert success
        data = result["data"]["smartLabelSearchOrCreate"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Created label 'New Test Label'")
        self.assertTrue(data["labelCreated"])
        self.assertFalse(data["labelsetCreated"])

        # Assert label was created
        self.assertEqual(len(data["labels"]), 1)
        self.assertEqual(data["labels"][0]["text"], "New Test Label")
        self.assertEqual(data["labels"][0]["color"], "#0000FF")

        # Assert labelset is the existing one
        self.assertEqual(data["labelset"]["title"], "Test Labelset")

        # Verify in database
        new_label = AnnotationLabel.objects.filter(text="New Test Label").first()
        self.assertIsNotNone(new_label)
        self.assertEqual(new_label.color, "#0000FF")
        self.assertEqual(new_label.description, "A new test label")
        self.assertIn(new_label, self.labelset.annotation_labels.all())

    def test_smart_label_create_with_new_labelset(self):
        """Test creating both labelset and label when corpus has no labelset."""
        mutation = """
            mutation SmartLabelSearchOrCreate(
                $corpusId: String!
                $searchTerm: String!
                $labelType: String!
                $createIfNotFound: Boolean
                $labelsetTitle: String
                $labelsetDescription: String
            ) {
                smartLabelSearchOrCreate(
                    corpusId: $corpusId
                    searchTerm: $searchTerm
                    labelType: $labelType
                    createIfNotFound: $createIfNotFound
                    labelsetTitle: $labelsetTitle
                    labelsetDescription: $labelsetDescription
                ) {
                    ok
                    message
                    labelCreated
                    labelsetCreated
                    labels {
                        id
                        text
                        labelType
                    }
                    labelset {
                        id
                        title
                        description
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_without_labelset.id),
            "searchTerm": "First Label",
            "labelType": LabelType.TOKEN_LABEL.value,
            "createIfNotFound": True,
            "labelsetTitle": "New Labelset",
            "labelsetDescription": "Created by smart mutation",
        }

        result = self.client.execute(mutation, variables=variables)

        # Assert no errors
        self.assertIsNone(result.get("errors"))

        # Assert success
        data = result["data"]["smartLabelSearchOrCreate"]
        self.assertTrue(data["ok"])
        self.assertIn("Created labelset", data["message"])
        self.assertTrue(data["labelCreated"])
        self.assertTrue(data["labelsetCreated"])

        # Assert label was created
        self.assertEqual(len(data["labels"]), 1)
        self.assertEqual(data["labels"][0]["text"], "First Label")

        # Assert labelset was created
        self.assertEqual(data["labelset"]["title"], "New Labelset")
        self.assertEqual(data["labelset"]["description"], "Created by smart mutation")

        # Verify corpus now has labelset
        self.corpus_without_labelset.refresh_from_db()
        self.assertIsNotNone(self.corpus_without_labelset.label_set)
        self.assertEqual(self.corpus_without_labelset.label_set.title, "New Labelset")

    def test_smart_label_search_existing(self):
        """Test searching for an existing label."""
        mutation = """
            mutation SmartLabelSearchOrCreate(
                $corpusId: String!
                $searchTerm: String!
                $labelType: String!
                $createIfNotFound: Boolean
            ) {
                smartLabelSearchOrCreate(
                    corpusId: $corpusId
                    searchTerm: $searchTerm
                    labelType: $labelType
                    createIfNotFound: $createIfNotFound
                ) {
                    ok
                    message
                    labelCreated
                    labels {
                        id
                        text
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_with_labelset.id),
            "searchTerm": "Existing",  # Partial match for "Existing Label"
            "labelType": LabelType.SPAN_LABEL.value,
            "createIfNotFound": False,  # Don't create if not found
        }

        result = self.client.execute(mutation, variables=variables)

        # Assert no errors
        self.assertIsNone(result.get("errors"))

        # Assert success
        data = result["data"]["smartLabelSearchOrCreate"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Found 1 matching label(s)")
        self.assertFalse(data["labelCreated"])

        # Assert existing label was found
        self.assertEqual(len(data["labels"]), 1)
        self.assertEqual(data["labels"][0]["text"], "Existing Label")

    def test_smart_label_no_permission(self):
        """Test that users without permission cannot create labels."""
        mutation = """
            mutation SmartLabelSearchOrCreate(
                $corpusId: String!
                $searchTerm: String!
                $labelType: String!
                $createIfNotFound: Boolean
            ) {
                smartLabelSearchOrCreate(
                    corpusId: $corpusId
                    searchTerm: $searchTerm
                    labelType: $labelType
                    createIfNotFound: $createIfNotFound
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_with_labelset.id),
            "searchTerm": "Unauthorized Label",
            "labelType": LabelType.SPAN_LABEL.value,
            "createIfNotFound": True,
        }

        # Use other_client (user without permissions)
        result = self.other_client.execute(mutation, variables=variables)

        # Assert no errors but permission denied
        self.assertIsNone(result.get("errors"))
        data = result["data"]["smartLabelSearchOrCreate"]
        self.assertFalse(data["ok"])
        self.assertIn("permission", data["message"].lower())

    def test_smart_label_invalid_corpus(self):
        """Test with invalid corpus ID."""
        mutation = """
            mutation SmartLabelSearchOrCreate(
                $corpusId: String!
                $searchTerm: String!
                $labelType: String!
            ) {
                smartLabelSearchOrCreate(
                    corpusId: $corpusId
                    searchTerm: $searchTerm
                    labelType: $labelType
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", 99999),  # Non-existent ID
            "searchTerm": "Test",
            "labelType": LabelType.SPAN_LABEL.value,
        }

        result = self.client.execute(mutation, variables=variables)

        # Assert no GraphQL errors but mutation failed
        self.assertIsNone(result.get("errors"))
        data = result["data"]["smartLabelSearchOrCreate"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Corpus not found")

    def test_smart_label_list_mutation(self):
        """Test the SmartLabelListMutation."""
        mutation = """
            mutation SmartLabelList(
                $corpusId: String!
                $labelType: String
            ) {
                smartLabelList(
                    corpusId: $corpusId
                    labelType: $labelType
                ) {
                    ok
                    message
                    hasLabelset
                    canCreateLabels
                    labels {
                        id
                        text
                        labelType
                    }
                }
            }
        """

        # Test with corpus that has labelset
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_with_labelset.id),
        }

        result = self.client.execute(mutation, variables=variables)

        # Assert no errors
        self.assertIsNone(result.get("errors"))

        # Assert success
        data = result["data"]["smartLabelList"]
        self.assertTrue(data["ok"])
        self.assertTrue(data["hasLabelset"])
        self.assertTrue(data["canCreateLabels"])
        self.assertEqual(len(data["labels"]), 1)
        self.assertEqual(data["labels"][0]["text"], "Existing Label")

        # Test with corpus without labelset
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_without_labelset.id),
        }

        result = self.client.execute(mutation, variables=variables)

        data = result["data"]["smartLabelList"]
        self.assertTrue(data["ok"])
        self.assertFalse(data["hasLabelset"])
        self.assertTrue(data["canCreateLabels"])
        self.assertEqual(len(data["labels"]), 0)
        self.assertEqual(data["message"], "No labelset configured for this corpus")

    def test_smart_label_list_filter_by_type(self):
        """Test filtering labels by type in SmartLabelListMutation."""
        # Add a token label to the labelset
        token_label = AnnotationLabel.objects.create(
            text="Token Label",
            label_type=LabelType.TOKEN_LABEL,
            creator=self.user,
        )
        self.labelset.annotation_labels.add(token_label)

        mutation = """
            mutation SmartLabelList(
                $corpusId: String!
                $labelType: String
            ) {
                smartLabelList(
                    corpusId: $corpusId
                    labelType: $labelType
                ) {
                    ok
                    labels {
                        text
                        labelType
                    }
                }
            }
        """

        # Filter for SPAN_LABEL only
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_with_labelset.id),
            "labelType": LabelType.SPAN_LABEL.value,
        }

        result = self.client.execute(mutation, variables=variables)
        data = result["data"]["smartLabelList"]

        self.assertTrue(data["ok"])
        self.assertEqual(len(data["labels"]), 1)
        self.assertEqual(data["labels"][0]["text"], "Existing Label")

        # Filter for TOKEN_LABEL only
        variables["labelType"] = LabelType.TOKEN_LABEL.value

        result = self.client.execute(mutation, variables=variables)
        data = result["data"]["smartLabelList"]

        self.assertTrue(data["ok"])
        self.assertEqual(len(data["labels"]), 1)
        self.assertEqual(data["labels"][0]["text"], "Token Label")

    def test_smart_label_list_denies_unreadable_corpus(self):
        """SmartLabelList must not leak a private corpus's labels (IDOR).

        ``corpus_with_labelset`` is private and owned by ``self.user``;
        ``other_user`` has no permission on it. Before the corpus-READ gate
        was added, any logged-in user could enumerate the labelset taxonomy
        of a corpus they cannot read. The mutation must now return the same
        IDOR-safe "Corpus not found" response it returns for a missing
        corpus — no labels, no labelset signal.
        """
        mutation = """
            mutation SmartLabelList($corpusId: String!) {
                smartLabelList(corpusId: $corpusId) {
                    ok
                    message
                    hasLabelset
                    canCreateLabels
                    labels {
                        text
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_with_labelset.id),
        }

        # other_client = user WITHOUT any permission on the private corpus
        result = self.other_client.execute(mutation, variables=variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["smartLabelList"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Corpus not found")
        self.assertFalse(data["hasLabelset"])
        self.assertFalse(data["canCreateLabels"])
        self.assertEqual(len(data["labels"]), 0)

    def test_smart_label_auto_labelset_title(self):
        """Test automatic labelset title generation when not provided."""
        mutation = """
            mutation SmartLabelSearchOrCreate(
                $corpusId: String!
                $searchTerm: String!
                $labelType: String!
                $createIfNotFound: Boolean
            ) {
                smartLabelSearchOrCreate(
                    corpusId: $corpusId
                    searchTerm: $searchTerm
                    labelType: $labelType
                    createIfNotFound: $createIfNotFound
                ) {
                    ok
                    labelset {
                        title
                    }
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_without_labelset.id),
            "searchTerm": "Auto Title Test",
            "labelType": LabelType.SPAN_LABEL.value,
            "createIfNotFound": True,
            # Note: NOT providing labelsetTitle
        }

        result = self.client.execute(mutation, variables=variables)

        data = result["data"]["smartLabelSearchOrCreate"]
        self.assertTrue(data["ok"])
        # Should auto-generate title based on corpus title
        self.assertEqual(
            data["labelset"]["title"], f"{self.corpus_without_labelset.title} Labels"
        )

    def test_smart_label_case_insensitive_search(self):
        """Test that label search is case-insensitive."""
        mutation = """
            mutation SmartLabelSearchOrCreate(
                $corpusId: String!
                $searchTerm: String!
                $labelType: String!
                $createIfNotFound: Boolean
            ) {
                smartLabelSearchOrCreate(
                    corpusId: $corpusId
                    searchTerm: $searchTerm
                    labelType: $labelType
                    createIfNotFound: $createIfNotFound
                ) {
                    ok
                    labels {
                        text
                    }
                }
            }
        """

        # Search with different case
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus_with_labelset.id),
            "searchTerm": "existing",  # lowercase search for "Existing Label"
            "labelType": LabelType.SPAN_LABEL.value,
            "createIfNotFound": False,
        }

        result = self.client.execute(mutation, variables=variables)

        data = result["data"]["smartLabelSearchOrCreate"]
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["labels"]), 1)
        self.assertEqual(data["labels"][0]["text"], "Existing Label")
