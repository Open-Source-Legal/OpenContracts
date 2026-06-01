"""
Tests for CorpusCategory model and GraphQL operations.

Tests cover:
1. Model creation and validation
2. Category ordering
3. Corpus-category relationship (ManyToMany)
4. GraphQL queries for categories
5. GraphQL mutations (create/update corpus with categories)
6. Permission checks
7. corpusCount computed field
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.constants.corpus_categories import (
    DEFAULT_CATEGORY_COLOR,
    DEFAULT_CATEGORY_ICON,
    MAX_CATEGORY_DESCRIPTION_LENGTH,
)
from opencontractserver.corpuses.models import Corpus, CorpusCategory
from opencontractserver.corpuses.services import CorpusCategoryService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


@pytest.mark.django_db
class TestCorpusCategoryModel:
    """Test CorpusCategory model functionality."""

    @pytest.fixture(autouse=True)
    def clear_categories(self):
        """Clear seeded categories before each test."""
        CorpusCategory.objects.all().delete()

    def test_create_category(self):
        """Test basic category creation with all fields."""
        user = User.objects.create_user(username="testuser", password="test")

        category = CorpusCategory.objects.create(
            name="Model Legislation",
            description="Legislative documents and bills",
            icon="scroll",
            color="#3B82F6",
            sort_order=1,
            creator=user,
        )

        assert category.name == "Model Legislation"
        assert category.description == "Legislative documents and bills"
        assert category.icon == "scroll"
        assert category.color == "#3B82F6"
        assert category.sort_order == 1
        assert category.creator == user

    def test_create_category_with_defaults(self):
        """Test category creation with default values."""
        user = User.objects.create_user(username="testuser", password="test")

        category = CorpusCategory.objects.create(
            name="Model Contracts",
            creator=user,
        )

        assert category.name == "Model Contracts"
        assert category.description == ""
        assert category.icon == "folder"
        assert category.color == "#3B82F6"
        assert category.sort_order == 0

    def test_category_str_method(self):
        """Test __str__ returns category name."""
        user = User.objects.create_user(username="testuser", password="test")

        category = CorpusCategory.objects.create(
            name="Model Legal Documents",
            creator=user,
        )

        assert str(category) == "Model Legal Documents"

    def test_category_unique_name(self):
        """Test that category names must be unique."""
        user = User.objects.create_user(username="testuser", password="test")

        CorpusCategory.objects.create(
            name="Model Unique Test",
            creator=user,
        )

        # Try to create another category with the same name - should fail
        with pytest.raises(Exception):  # IntegrityError or ValidationError
            CorpusCategory.objects.create(
                name="Model Unique Test",
                creator=user,
            )

    def test_category_ordering(self):
        """Test categories are ordered by sort_order, then name."""
        user = User.objects.create_user(username="testuser", password="test")

        # Create categories in random order
        cat_c = CorpusCategory.objects.create(
            name="Model C Category", sort_order=2, creator=user
        )
        cat_a = CorpusCategory.objects.create(
            name="Model A Category", sort_order=1, creator=user
        )
        cat_b = CorpusCategory.objects.create(
            name="Model B Category", sort_order=1, creator=user
        )
        cat_d = CorpusCategory.objects.create(
            name="Model D Category", sort_order=0, creator=user
        )

        # Query all categories
        categories = list(CorpusCategory.objects.all())

        # Should be ordered by sort_order first, then name
        assert categories[0] == cat_d  # sort_order=0
        assert categories[1] == cat_a  # sort_order=1, name=A
        assert categories[2] == cat_b  # sort_order=1, name=B
        assert categories[3] == cat_c  # sort_order=2

    def test_corpus_category_relationship(self):
        """Test assigning categories to a corpus."""
        user = User.objects.create_user(username="testuser", password="test")

        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        cat1 = CorpusCategory.objects.create(name="Model Legal", creator=user)
        cat2 = CorpusCategory.objects.create(name="Model Contracts", creator=user)
        cat3 = CorpusCategory.objects.create(name="Model Legislation", creator=user)

        # Assign categories to corpus
        corpus.categories.add(cat1, cat2)

        # Verify assignment
        assert corpus.categories.count() == 2
        assert cat1 in corpus.categories.all()
        assert cat2 in corpus.categories.all()
        assert cat3 not in corpus.categories.all()

        # Verify reverse relationship
        # `corpuses` is the related_name of Corpus.categories (M2M); django-stubs
        # cannot resolve dynamically-generated reverse accessors from related_name.
        assert corpus in cat1.corpuses.all()  # type: ignore[attr-defined]
        assert corpus in cat2.corpuses.all()  # type: ignore[attr-defined]
        assert corpus not in cat3.corpuses.all()  # type: ignore[attr-defined]

    def test_corpus_multiple_categories(self):
        """Test a corpus can have multiple categories."""
        user = User.objects.create_user(username="testuser", password="test")

        corpus = Corpus.objects.create(title="Multi-Category Corpus", creator=user)

        categories = [
            CorpusCategory.objects.create(name=f"Model Category {i}", creator=user)
            for i in range(5)
        ]

        corpus.categories.set(categories)

        assert corpus.categories.count() == 5

    def test_category_multiple_corpuses(self):
        """Test a category can be assigned to multiple corpuses."""
        user = User.objects.create_user(username="testuser", password="test")

        category = CorpusCategory.objects.create(name="Model Legal Multi", creator=user)

        corpuses = [
            Corpus.objects.create(title=f"Corpus {i}", creator=user) for i in range(3)
        ]

        for corpus in corpuses:
            corpus.categories.add(category)

        # `corpuses` is the related_name of Corpus.categories (M2M); django-stubs
        # cannot resolve dynamically-generated reverse accessors from related_name.
        assert category.corpuses.count() == 3  # type: ignore[attr-defined]

    def test_remove_category_from_corpus(self):
        """Test removing a category from a corpus."""
        user = User.objects.create_user(username="testuser", password="test")

        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        cat1 = CorpusCategory.objects.create(name="Model Legal Remove", creator=user)
        cat2 = CorpusCategory.objects.create(
            name="Model Contracts Remove", creator=user
        )

        corpus.categories.add(cat1, cat2)
        assert corpus.categories.count() == 2

        # Remove one category
        corpus.categories.remove(cat1)

        assert corpus.categories.count() == 1
        assert cat2 in corpus.categories.all()
        assert cat1 not in corpus.categories.all()

    def test_clear_corpus_categories(self):
        """Test clearing all categories from a corpus."""
        user = User.objects.create_user(username="testuser", password="test")

        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        cat1 = CorpusCategory.objects.create(name="Model Legal Clear", creator=user)
        cat2 = CorpusCategory.objects.create(name="Model Contracts Clear", creator=user)

        corpus.categories.add(cat1, cat2)
        assert corpus.categories.count() == 2

        # Clear all categories
        corpus.categories.clear()

        assert corpus.categories.count() == 0


class TestCorpusCategoryGraphQLQueries(TestCase):
    """Test GraphQL queries for CorpusCategory."""

    user: User
    cat1: CorpusCategory
    cat2: CorpusCategory
    cat3: CorpusCategory
    corpus1: Corpus
    corpus2: Corpus
    corpus3: Corpus
    graphene_client: Client

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        # Clear any seeded categories to ensure test isolation
        CorpusCategory.objects.all().delete()

        cls.user = User.objects.create_user(
            username="gql_user",
            password="testpass123",
            email="gql@test.com",
        )

        # Create categories with unique names (prefixed to avoid conflicts)
        cls.cat1 = CorpusCategory.objects.create(
            name="Test Legislation",
            description="Legislative documents",
            icon="scroll",
            color="#FF0000",
            sort_order=1,
            creator=cls.user,
        )
        cls.cat2 = CorpusCategory.objects.create(
            name="Test Contracts",
            description="Contract documents",
            icon="file-text",
            color="#00FF00",
            sort_order=2,
            creator=cls.user,
        )
        cls.cat3 = CorpusCategory.objects.create(
            name="Test Research",
            description="Research materials",
            icon="book",
            color="#0000FF",
            sort_order=0,
            creator=cls.user,
        )

        # Create corpuses with categories
        cls.corpus1 = Corpus.objects.create(
            title="Legal Corpus",
            creator=cls.user,
            is_public=True,
        )
        cls.corpus1.categories.add(cls.cat1, cls.cat2)

        cls.corpus2 = Corpus.objects.create(
            title="Research Corpus",
            creator=cls.user,
            is_public=True,
        )
        cls.corpus2.categories.add(cls.cat3)

        cls.corpus3 = Corpus.objects.create(
            title="Multi-Category Corpus",
            creator=cls.user,
            is_public=True,
        )
        cls.corpus3.categories.add(cls.cat1, cls.cat3)

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user
        self.graphene_client = Client(schema, context_value=self.request)

    def test_query_corpus_categories(self):
        """Test querying all corpus categories."""
        query = """
            query {
                corpusCategories {
                    edges {
                        node {
                            id
                            name
                            description
                            icon
                            color
                            sortOrder
                        }
                    }
                }
            }
        """

        result = self.graphene_client.execute(query)

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Verify we get all categories
        edges = result["data"]["corpusCategories"]["edges"]
        self.assertEqual(len(edges), 3)

        # Verify ordering (sort_order, then name)
        # Test Research (0), Test Legislation (1), Test Contracts (2)
        self.assertEqual(edges[0]["node"]["name"], "Test Research")
        self.assertEqual(edges[1]["node"]["name"], "Test Legislation")
        self.assertEqual(edges[2]["node"]["name"], "Test Contracts")

        # Verify first category details
        first_category = edges[0]["node"]
        self.assertEqual(first_category["name"], "Test Research")
        self.assertEqual(first_category["description"], "Research materials")
        self.assertEqual(first_category["icon"], "book")
        self.assertEqual(first_category["color"], "#0000FF")
        self.assertEqual(first_category["sortOrder"], 0)

    def test_category_corpus_count(self):
        """Test the corpusCount computed field."""
        query = """
            query {
                corpusCategories {
                    edges {
                        node {
                            id
                            name
                            corpusCount
                        }
                    }
                }
            }
        """

        result = self.graphene_client.execute(query)

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        edges = result["data"]["corpusCategories"]["edges"]

        # Find categories by name and check counts
        categories_by_name = {edge["node"]["name"]: edge["node"] for edge in edges}

        # Test Research: corpus2, corpus3 = 2 corpuses
        self.assertEqual(categories_by_name["Test Research"]["corpusCount"], 2)

        # Test Legislation: corpus1, corpus3 = 2 corpuses
        self.assertEqual(categories_by_name["Test Legislation"]["corpusCount"], 2)

        # Test Contracts: corpus1 = 1 corpus
        self.assertEqual(categories_by_name["Test Contracts"]["corpusCount"], 1)

    def test_corpus_categories_field(self):
        """Test querying categories on a corpus."""
        corpus_gid = to_global_id("CorpusType", self.corpus1.id)

        query = """
            query GetCorpus($id: ID!) {
                corpus(id: $id) {
                    id
                    title
                    categories {
                        id
                        name
                        icon
                        color
                    }
                }
            }
        """

        result = self.graphene_client.execute(query, variables={"id": corpus_gid})

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        corpus = result["data"]["corpus"]
        self.assertEqual(corpus["title"], "Legal Corpus")

        # Verify categories
        categories = corpus["categories"]
        self.assertEqual(len(categories), 2)

        category_names = {cat["name"] for cat in categories}
        self.assertEqual(category_names, {"Test Legislation", "Test Contracts"})

    def test_category_corpus_count_with_permissions(self):
        """Test corpusCount only includes visible corpuses."""
        # Create another user
        other_user = User.objects.create_user(
            username="other_user",
            password="testpass123",
        )

        # Create a private corpus with cat1 (Legislation)
        private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=other_user,
            is_public=False,
        )
        private_corpus.categories.add(self.cat1)

        # Query as original user (should not see private corpus)
        query = """
            query {
                corpusCategories {
                    edges {
                        node {
                            name
                            corpusCount
                        }
                    }
                }
            }
        """

        result = self.graphene_client.execute(query)

        edges = result["data"]["corpusCategories"]["edges"]
        categories_by_name = {edge["node"]["name"]: edge["node"] for edge in edges}

        # Test Legislation should still show 2 (not 3) because private_corpus is not visible
        self.assertEqual(categories_by_name["Test Legislation"]["corpusCount"], 2)


class TestCorpusCategoryGraphQLMutations(TestCase):
    """Test GraphQL mutations involving corpus categories."""

    user: User
    cat1: CorpusCategory
    cat2: CorpusCategory
    cat3: CorpusCategory
    graphene_client: Client

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        # Clear any seeded categories to ensure test isolation
        CorpusCategory.objects.all().delete()

        cls.user = User.objects.create_user(
            username="gql_user",
            password="testpass123",
            email="gql@test.com",
        )

        # Create categories with unique names
        cls.cat1 = CorpusCategory.objects.create(
            name="Mut Legislation",
            creator=cls.user,
        )
        cls.cat2 = CorpusCategory.objects.create(
            name="Mut Contracts",
            creator=cls.user,
        )
        cls.cat3 = CorpusCategory.objects.create(
            name="Mut Research",
            creator=cls.user,
        )

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user
        self.graphene_client = Client(schema, context_value=self.request)

    def test_create_corpus_with_categories(self):
        """Test creating a corpus with category assignment."""
        cat1_gid = to_global_id("CorpusCategoryType", self.cat1.id)
        cat2_gid = to_global_id("CorpusCategoryType", self.cat2.id)

        mutation = """
            mutation CreateCorpus($title: String!, $categories: [ID]) {
                createCorpus(title: $title, categories: $categories) {
                    ok
                    message
                    objId
                }
            }
        """

        result = self.graphene_client.execute(
            mutation,
            variables={
                "title": "New Legal Corpus",
                "categories": [cat1_gid, cat2_gid],
            },
        )

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Verify mutation succeeded
        mutation_result = result["data"]["createCorpus"]
        self.assertTrue(mutation_result["ok"])
        self.assertIsNotNone(mutation_result["objId"])

        # Get the created corpus and verify categories
        from graphql_relay import from_global_id

        corpus_pk = from_global_id(mutation_result["objId"])[1]
        corpus = Corpus.objects.get(pk=corpus_pk)

        self.assertEqual(corpus.categories.count(), 2)
        self.assertIn(self.cat1, corpus.categories.all())
        self.assertIn(self.cat2, corpus.categories.all())

    def test_create_corpus_without_categories(self):
        """Test creating a corpus without categories."""
        mutation = """
            mutation CreateCorpus($title: String!) {
                createCorpus(title: $title) {
                    ok
                    message
                    objId
                }
            }
        """

        result = self.graphene_client.execute(
            mutation,
            variables={"title": "Uncategorized Corpus"},
        )

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Verify mutation succeeded
        mutation_result = result["data"]["createCorpus"]
        self.assertTrue(mutation_result["ok"])

        # Get the created corpus and verify no categories
        from graphql_relay import from_global_id

        corpus_pk = from_global_id(mutation_result["objId"])[1]
        corpus = Corpus.objects.get(pk=corpus_pk)

        self.assertEqual(corpus.categories.count(), 0)

    def test_update_corpus_categories(self):
        """Test updating corpus categories."""
        # Create corpus with initial categories
        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        corpus.categories.add(self.cat1)
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        # Update to different categories
        corpus_gid = to_global_id("CorpusType", corpus.id)
        cat2_gid = to_global_id("CorpusCategoryType", self.cat2.id)
        cat3_gid = to_global_id("CorpusCategoryType", self.cat3.id)

        mutation = """
            mutation UpdateCorpus($id: String!, $categories: [ID]) {
                updateCorpus(id: $id, categories: $categories) {
                    ok
                    message
                    objId
                }
            }
        """

        result = self.graphene_client.execute(
            mutation,
            variables={
                "id": corpus_gid,
                "categories": [cat2_gid, cat3_gid],
            },
        )

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Verify mutation succeeded
        mutation_result = result["data"]["updateCorpus"]
        self.assertTrue(mutation_result["ok"])

        # Refresh corpus and verify categories were replaced
        corpus.refresh_from_db()

        self.assertEqual(corpus.categories.count(), 2)
        self.assertIn(self.cat2, corpus.categories.all())
        self.assertIn(self.cat3, corpus.categories.all())
        self.assertNotIn(self.cat1, corpus.categories.all())

    def test_clear_corpus_categories(self):
        """Test clearing categories by passing empty list."""
        # Create corpus with categories
        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        corpus.categories.add(self.cat1, self.cat2)
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        corpus_gid = to_global_id("CorpusType", corpus.id)

        mutation = """
            mutation UpdateCorpus($id: String!, $categories: [ID]) {
                updateCorpus(id: $id, categories: $categories) {
                    ok
                    message
                }
            }
        """

        result = self.graphene_client.execute(
            mutation,
            variables={
                "id": corpus_gid,
                "categories": [],
            },
        )

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Verify categories were cleared
        corpus.refresh_from_db()
        self.assertEqual(corpus.categories.count(), 0)

    def test_update_corpus_add_categories(self):
        """Test adding categories to corpus that had none."""
        # Create corpus without categories
        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        corpus_gid = to_global_id("CorpusType", corpus.id)
        cat1_gid = to_global_id("CorpusCategoryType", self.cat1.id)

        mutation = """
            mutation UpdateCorpus($id: String!, $categories: [ID]) {
                updateCorpus(id: $id, categories: $categories) {
                    ok
                    message
                }
            }
        """

        result = self.graphene_client.execute(
            mutation,
            variables={
                "id": corpus_gid,
                "categories": [cat1_gid],
            },
        )

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Verify category was added
        corpus.refresh_from_db()
        self.assertEqual(corpus.categories.count(), 1)
        self.assertIn(self.cat1, corpus.categories.all())

    def test_create_corpus_with_invalid_category_id(self):
        """Test creating a corpus with non-existent category ID fails gracefully."""
        # Use a valid global ID format but with non-existent database ID
        invalid_cat_gid = to_global_id("CorpusCategoryType", 99999)

        mutation = """
            mutation CreateCorpus($title: String!, $categories: [ID]) {
                createCorpus(title: $title, categories: $categories) {
                    ok
                    message
                    objId
                }
            }
        """

        result = self.graphene_client.execute(
            mutation,
            variables={
                "title": "Test Invalid Category",
                "categories": [invalid_cat_gid],
            },
        )

        # Should fail with appropriate error
        mutation_result = result.get("data", {}).get("createCorpus", {})
        if mutation_result:
            # If mutation returns a result, ok should be False
            self.assertFalse(mutation_result["ok"])
        else:
            # Or we should have errors
            self.assertIsNotNone(result.get("errors"))

    def test_create_corpus_with_duplicate_category_ids(self):
        """Test that duplicate category IDs are handled correctly (deduplicated)."""
        cat1_gid = to_global_id("CorpusCategoryType", self.cat1.id)

        mutation = """
            mutation CreateCorpus($title: String!, $categories: [ID]) {
                createCorpus(title: $title, categories: $categories) {
                    ok
                    message
                    objId
                }
            }
        """

        result = self.graphene_client.execute(
            mutation,
            variables={
                "title": "Test Duplicate Categories",
                # Same category ID passed multiple times
                "categories": [cat1_gid, cat1_gid, cat1_gid],
            },
        )

        # Should succeed - duplicates should be handled
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        mutation_result = result["data"]["createCorpus"]
        self.assertTrue(mutation_result["ok"])

        # Get the created corpus and verify only one category (deduplicated)
        from graphql_relay import from_global_id

        corpus_pk = from_global_id(mutation_result["objId"])[1]
        corpus = Corpus.objects.get(pk=corpus_pk)

        # ManyToMany relationship naturally deduplicates
        self.assertEqual(corpus.categories.count(), 1)
        self.assertIn(self.cat1, corpus.categories.all())

    def test_update_corpus_with_invalid_category_id(self):
        """Test updating a corpus with non-existent category ID fails gracefully."""
        # Create corpus
        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])

        corpus_gid = to_global_id("CorpusType", corpus.id)
        invalid_cat_gid = to_global_id("CorpusCategoryType", 99999)

        mutation = """
            mutation UpdateCorpus($id: String!, $categories: [ID]) {
                updateCorpus(id: $id, categories: $categories) {
                    ok
                    message
                }
            }
        """

        result = self.graphene_client.execute(
            mutation,
            variables={
                "id": corpus_gid,
                "categories": [invalid_cat_gid],
            },
        )

        # Should fail with appropriate error
        mutation_result = result.get("data", {}).get("updateCorpus", {})
        if mutation_result:
            self.assertFalse(mutation_result["ok"])
        else:
            self.assertIsNotNone(result.get("errors"))


class TestCorpusCategoryPermissions(TestCase):
    """Test permission checks for corpus category operations."""

    owner: User
    other_user: User
    category: CorpusCategory
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        # Clear any seeded categories to ensure test isolation
        CorpusCategory.objects.all().delete()

        cls.owner = User.objects.create_user(
            username="owner",
            password="testpass123",
        )
        cls.other_user = User.objects.create_user(
            username="other_user",
            password="testpass123",
        )

        cls.category = CorpusCategory.objects.create(
            name="Perm Legal",
            creator=cls.owner,
        )

        cls.corpus = Corpus.objects.create(
            title="Owner's Corpus",
            creator=cls.owner,
        )
        cls.corpus.categories.add(cls.category)

        # Grant owner CRUD permissions
        set_permissions_for_obj_to_user(cls.owner, cls.corpus, [PermissionTypes.CRUD])

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()

    def test_user_cannot_modify_others_corpus_categories(self):
        """Test IDOR prevention - users cannot modify categories on corpuses they don't own."""
        # Try to update corpus as other_user
        request = self.factory.get("/graphql")
        request.user = self.other_user
        client = Client(schema, context_value=request)

        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        mutation = """
            mutation UpdateCorpus($id: String!, $categories: [ID]) {
                updateCorpus(id: $id, categories: $categories) {
                    ok
                    message
                }
            }
        """

        result = client.execute(
            mutation,
            variables={
                "id": corpus_gid,
                "categories": [],  # Try to clear categories
            },
        )

        # Should fail or have error
        mutation_result = result.get("data", {}).get("updateCorpus", {})

        # Either mutation returns ok=False, or we get errors
        if mutation_result:
            self.assertFalse(mutation_result["ok"])
        else:
            self.assertIsNotNone(result.get("errors"))

        # Verify categories were not modified
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.categories.count(), 1)
        self.assertIn(self.category, self.corpus.categories.all())

    def test_owner_can_modify_corpus_categories(self):
        """Test owner can successfully modify corpus categories."""
        request = self.factory.get("/graphql")
        request.user = self.owner
        client = Client(schema, context_value=request)

        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        mutation = """
            mutation UpdateCorpus($id: String!, $categories: [ID]) {
                updateCorpus(id: $id, categories: $categories) {
                    ok
                    message
                }
            }
        """

        result = client.execute(
            mutation,
            variables={
                "id": corpus_gid,
                "categories": [],  # Clear categories
            },
        )

        # Check for errors
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        # Should succeed
        mutation_result = result["data"]["updateCorpus"]
        self.assertTrue(mutation_result["ok"])

        # Verify categories were cleared
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.categories.count(), 0)


class TestCorpusCategoryManagementMutations(TestCase):
    """Test the superuser-only CRUD mutations for managing CorpusCategory.

    Covers create / update / delete via the GraphQL API, including the
    superuser gate, validation, and unique-name enforcement.
    """

    superuser: User
    regular_user: User
    existing: CorpusCategory

    @classmethod
    def setUpTestData(cls):
        # Clear seeded categories so corpus_count / list assertions are stable.
        CorpusCategory.objects.all().delete()

        cls.superuser = User.objects.create_user(
            username="cat_admin",
            password="testpass123",
            is_superuser=True,
            is_staff=True,
        )
        cls.regular_user = User.objects.create_user(
            username="cat_regular",
            password="testpass123",
        )
        cls.existing = CorpusCategory.objects.create(
            name="Existing Category",
            description="Seeded for update/delete tests",
            icon="folder",
            color="#3B82F6",
            sort_order=5,
            creator=cls.superuser,
        )

    def _client_for(self, user):
        factory = RequestFactory()
        request = factory.post("/graphql")
        request.user = user
        return Client(schema, context_value=request)

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #
    def test_superuser_can_create_category(self):
        client = self._client_for(self.superuser)
        mutation = """
            mutation Create($name: String!, $icon: String, $color: String, $sortOrder: Int) {
                createCorpusCategory(name: $name, icon: $icon, color: $color, sortOrder: $sortOrder) {
                    ok
                    message
                    obj { id name icon color sortOrder }
                }
            }
        """
        result = client.execute(
            mutation,
            variables={
                "name": "Statutes",
                "icon": "scroll",
                "color": "#10B981",
                "sortOrder": 2,
            },
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        payload = result["data"]["createCorpusCategory"]
        self.assertTrue(payload["ok"], payload["message"])
        self.assertEqual(payload["obj"]["name"], "Statutes")
        self.assertEqual(payload["obj"]["icon"], "scroll")
        self.assertEqual(payload["obj"]["color"], "#10B981")
        self.assertEqual(payload["obj"]["sortOrder"], 2)
        self.assertTrue(CorpusCategory.objects.filter(name="Statutes").exists())

    def test_create_uses_default_icon_and_color(self):
        client = self._client_for(self.superuser)
        mutation = """
            mutation Create($name: String!) {
                createCorpusCategory(name: $name) {
                    ok
                    obj { icon color sortOrder }
                }
            }
        """
        result = client.execute(mutation, variables={"name": "Minimal"})
        self.assertIsNone(result.get("errors"), result.get("errors"))
        payload = result["data"]["createCorpusCategory"]
        self.assertTrue(payload["ok"])
        # Pull the expected defaults from the constants the service uses, so a
        # change to the defaults can't leave this test silently asserting a
        # stale value.
        self.assertEqual(payload["obj"]["icon"], DEFAULT_CATEGORY_ICON)
        self.assertEqual(payload["obj"]["color"], DEFAULT_CATEGORY_COLOR)
        self.assertEqual(payload["obj"]["sortOrder"], 0)

    def test_regular_user_cannot_create_category(self):
        client = self._client_for(self.regular_user)
        mutation = """
            mutation Create($name: String!) {
                createCorpusCategory(name: $name) { ok message obj { id } }
            }
        """
        result = client.execute(mutation, variables={"name": "Sneaky"})
        payload = result["data"]["createCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("superuser", payload["message"].lower())
        self.assertFalse(CorpusCategory.objects.filter(name="Sneaky").exists())

    def test_create_rejects_duplicate_name(self):
        client = self._client_for(self.superuser)
        mutation = """
            mutation Create($name: String!) {
                createCorpusCategory(name: $name) { ok message }
            }
        """
        result = client.execute(mutation, variables={"name": "Existing Category"})
        payload = result["data"]["createCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("already exists", payload["message"].lower())

    def test_anonymous_user_cannot_create_category(self):
        # The @login_required decorator must reject unauthenticated callers
        # before the superuser gate is reached, surfacing a GraphQL error
        # rather than an ok=false payload.
        client = self._client_for(AnonymousUser())
        mutation = """
            mutation Create($name: String!) {
                createCorpusCategory(name: $name) { ok message obj { id } }
            }
        """
        result = client.execute(mutation, variables={"name": "Anonymous"})
        self.assertIsNotNone(result.get("errors"))
        self.assertIsNone(result["data"]["createCorpusCategory"])
        self.assertFalse(CorpusCategory.objects.filter(name="Anonymous").exists())

    def test_create_rejects_blank_name(self):
        client = self._client_for(self.superuser)
        mutation = """
            mutation Create($name: String!) {
                createCorpusCategory(name: $name) { ok message }
            }
        """
        result = client.execute(mutation, variables={"name": "   "})
        payload = result["data"]["createCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("empty", payload["message"].lower())

    def test_create_rejects_invalid_color(self):
        client = self._client_for(self.superuser)
        mutation = """
            mutation Create($name: String!, $color: String) {
                createCorpusCategory(name: $name, color: $color) { ok message }
            }
        """
        result = client.execute(
            mutation, variables={"name": "BadColor", "color": "blue"}
        )
        payload = result["data"]["createCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("color", payload["message"].lower())
        self.assertFalse(CorpusCategory.objects.filter(name="BadColor").exists())

    def test_create_rejects_overly_long_description(self):
        client = self._client_for(self.superuser)
        mutation = """
            mutation Create($name: String!, $description: String) {
                createCorpusCategory(name: $name, description: $description) {
                    ok
                    message
                }
            }
        """
        result = client.execute(
            mutation,
            variables={
                "name": "LongDesc",
                "description": "x" * (MAX_CATEGORY_DESCRIPTION_LENGTH + 1),
            },
        )
        payload = result["data"]["createCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("description", payload["message"].lower())
        self.assertFalse(CorpusCategory.objects.filter(name="LongDesc").exists())

    # ------------------------------------------------------------------ #
    # Update
    # ------------------------------------------------------------------ #
    def test_superuser_can_update_category(self):
        client = self._client_for(self.superuser)
        gid = to_global_id("CorpusCategoryType", self.existing.id)
        mutation = """
            mutation Update($id: ID!, $name: String, $sortOrder: Int) {
                updateCorpusCategory(id: $id, name: $name, sortOrder: $sortOrder) {
                    ok
                    obj { name sortOrder }
                }
            }
        """
        result = client.execute(
            mutation,
            variables={"id": gid, "name": "Renamed Category", "sortOrder": 9},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        payload = result["data"]["updateCorpusCategory"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["obj"]["name"], "Renamed Category")
        self.assertEqual(payload["obj"]["sortOrder"], 9)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, "Renamed Category")
        self.assertEqual(self.existing.sort_order, 9)

    def test_update_rejects_duplicate_name(self):
        other = CorpusCategory.objects.create(
            name="Other Category", creator=self.superuser
        )
        client = self._client_for(self.superuser)
        gid = to_global_id("CorpusCategoryType", other.id)
        mutation = """
            mutation Update($id: ID!, $name: String) {
                updateCorpusCategory(id: $id, name: $name) { ok message }
            }
        """
        result = client.execute(
            mutation, variables={"id": gid, "name": "Existing Category"}
        )
        payload = result["data"]["updateCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("already exists", payload["message"].lower())
        other.refresh_from_db()
        self.assertEqual(other.name, "Other Category")

    def test_regular_user_cannot_update_category(self):
        client = self._client_for(self.regular_user)
        gid = to_global_id("CorpusCategoryType", self.existing.id)
        mutation = """
            mutation Update($id: ID!, $name: String) {
                updateCorpusCategory(id: $id, name: $name) { ok message }
            }
        """
        result = client.execute(mutation, variables={"id": gid, "name": "Hacked"})
        payload = result["data"]["updateCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("superuser", payload["message"].lower())
        self.existing.refresh_from_db()
        self.assertNotEqual(self.existing.name, "Hacked")

    def test_update_nonexistent_category(self):
        client = self._client_for(self.superuser)
        gid = to_global_id("CorpusCategoryType", 999999)
        mutation = """
            mutation Update($id: ID!, $name: String) {
                updateCorpusCategory(id: $id, name: $name) { ok message }
            }
        """
        result = client.execute(mutation, variables={"id": gid, "name": "X"})
        payload = result["data"]["updateCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())

    def test_update_with_no_fields_is_noop(self):
        """An update supplying no fields must not issue a DB write.

        All-``None`` kwargs would otherwise still fire a ``save`` that only
        bumps ``modified``; the service short-circuits to a successful no-op
        instead. ``assertNumQueries(0)`` proves nothing touched the DB.
        """
        with self.assertNumQueries(0):
            result = CorpusCategoryService.update_category(
                self.superuser, self.existing
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.value, self.existing)

    def test_update_rejects_overly_long_description(self):
        client = self._client_for(self.superuser)
        gid = to_global_id("CorpusCategoryType", self.existing.id)
        mutation = """
            mutation Update($id: ID!, $description: String) {
                updateCorpusCategory(id: $id, description: $description) {
                    ok
                    message
                }
            }
        """
        result = client.execute(
            mutation,
            variables={
                "id": gid,
                "description": "x" * (MAX_CATEGORY_DESCRIPTION_LENGTH + 1),
            },
        )
        payload = result["data"]["updateCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("description", payload["message"].lower())

    # ------------------------------------------------------------------ #
    # Delete
    # ------------------------------------------------------------------ #
    def test_superuser_can_delete_category(self):
        target = CorpusCategory.objects.create(name="To Delete", creator=self.superuser)
        # Attach to a corpus to confirm the M2M link is cleaned up but the
        # corpus survives.
        corpus = Corpus.objects.create(title="Has Category", creator=self.superuser)
        corpus.categories.add(target)

        client = self._client_for(self.superuser)
        gid = to_global_id("CorpusCategoryType", target.id)
        mutation = """
            mutation Delete($id: ID!) {
                deleteCorpusCategory(id: $id) { ok message }
            }
        """
        result = client.execute(mutation, variables={"id": gid})
        self.assertIsNone(result.get("errors"), result.get("errors"))
        payload = result["data"]["deleteCorpusCategory"]
        self.assertTrue(payload["ok"])
        self.assertFalse(CorpusCategory.objects.filter(pk=target.pk).exists())
        # Corpus itself must survive; only the M2M link is gone.
        self.assertTrue(Corpus.objects.filter(pk=corpus.pk).exists())
        self.assertEqual(corpus.categories.count(), 0)

    def test_regular_user_cannot_delete_category(self):
        target = CorpusCategory.objects.create(name="Protected", creator=self.superuser)
        client = self._client_for(self.regular_user)
        gid = to_global_id("CorpusCategoryType", target.id)
        mutation = """
            mutation Delete($id: ID!) {
                deleteCorpusCategory(id: $id) { ok message }
            }
        """
        result = client.execute(mutation, variables={"id": gid})
        payload = result["data"]["deleteCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("superuser", payload["message"].lower())
        self.assertTrue(CorpusCategory.objects.filter(pk=target.pk).exists())

    def test_delete_nonexistent_category(self):
        client = self._client_for(self.superuser)
        gid = to_global_id("CorpusCategoryType", 888888)
        mutation = """
            mutation Delete($id: ID!) {
                deleteCorpusCategory(id: $id) { ok message }
            }
        """
        result = client.execute(mutation, variables={"id": gid})
        payload = result["data"]["deleteCorpusCategory"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())
