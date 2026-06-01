"""
Tests for GraphQL corpus query optimization (documentCount and annotationCount fields).

Tests cover:
1. documentCount field returns correct count
2. annotationCount field returns correct count
3. Label counts are correctly passed to LabelSet
4. Query uses annotations rather than N+1 queries
"""

from django.http import HttpRequest
from django.test import RequestFactory, TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation, AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.users.models import User


class TestCorpusDocumentCountField(TestCase):
    """Test the documentCount field on CorpusType."""

    user: User
    corpus: Corpus
    doc1: Document
    doc2: Document
    doc3: Document
    empty_corpus: Corpus
    factory: RequestFactory
    request: HttpRequest
    graphene_client: Client

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="test_user",
            password="testpass123",
            email="test@test.com",
        )

        # Create a corpus
        cls.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=cls.user,
            is_public=True,
        )

        # Create documents and add them to corpus via DocumentPath
        cls.doc1 = Document.objects.create(
            title="Document 1",
            creator=cls.user,
        )
        cls.doc2 = Document.objects.create(
            title="Document 2",
            creator=cls.user,
        )
        cls.doc3 = Document.objects.create(
            title="Document 3",
            creator=cls.user,
        )

        # Add documents to corpus via DocumentPath
        DocumentPath.objects.create(
            document=cls.doc1,
            corpus=cls.corpus,
            path="/doc1.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.user,
        )
        DocumentPath.objects.create(
            document=cls.doc2,
            corpus=cls.corpus,
            path="/doc2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.user,
        )
        # doc3 is deleted - should not count
        DocumentPath.objects.create(
            document=cls.doc3,
            corpus=cls.corpus,
            path="/doc3.pdf",
            version_number=1,
            is_current=True,
            is_deleted=True,
            creator=cls.user,
        )

        # Create an empty corpus for testing zero count
        cls.empty_corpus = Corpus.objects.create(
            title="Empty Corpus",
            creator=cls.user,
            is_public=True,
        )

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user
        self.graphene_client = Client(schema, context_value=self.request)

    def test_document_count_returns_correct_count(self):
        """Test that documentCount returns the correct number of active documents."""
        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetCorpus($id: ID!) {
                corpus(id: $id) {
                    id
                    title
                    documentCount
                }
            }
        """

        result = self.graphene_client.execute(query, variables={"id": corpus_gid})

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        corpus = result["data"]["corpus"]
        self.assertEqual(corpus["title"], "Test Corpus")
        # Should be 2 (doc1 and doc2), not 3 (doc3 is deleted)
        self.assertEqual(corpus["documentCount"], 2)

    def test_document_count_returns_zero_for_empty_corpus(self):
        """Test that documentCount returns 0 for corpus with no documents."""
        corpus_gid = to_global_id("CorpusType", self.empty_corpus.id)

        query = """
            query GetCorpus($id: ID!) {
                corpus(id: $id) {
                    id
                    title
                    documentCount
                }
            }
        """

        result = self.graphene_client.execute(query, variables={"id": corpus_gid})

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        corpus = result["data"]["corpus"]
        self.assertEqual(corpus["title"], "Empty Corpus")
        self.assertEqual(corpus["documentCount"], 0)

    def test_document_count_in_list_query(self):
        """Test that documentCount works in corpuses list query."""
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            id
                            title
                            documentCount
                        }
                    }
                }
            }
        """

        result = self.graphene_client.execute(query)

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        edges = result["data"]["corpuses"]["edges"]
        # Find our test corpuses
        corpuses_by_title = {edge["node"]["title"]: edge["node"] for edge in edges}

        self.assertIn("Test Corpus", corpuses_by_title)
        self.assertIn("Empty Corpus", corpuses_by_title)

        self.assertEqual(corpuses_by_title["Test Corpus"]["documentCount"], 2)
        self.assertEqual(corpuses_by_title["Empty Corpus"]["documentCount"], 0)


class TestCorpusAnnotationCountField(TestCase):
    """Test the annotationCount field on CorpusType."""

    user: User
    label: AnnotationLabel
    corpus: Corpus
    doc1: Document
    doc2: Document
    doc3: Document
    empty_corpus: Corpus
    factory: RequestFactory
    request: HttpRequest
    graphene_client: Client

    @classmethod
    def setUpTestData(cls):
        """Create test data with documents and annotations."""
        cls.user = User.objects.create_user(
            username="annot_count_user",
            password="testpass123",
            email="annot_count@test.com",
        )

        # Create annotation labels
        cls.label = AnnotationLabel.objects.create(
            text="Test Label",
            label_type="SPAN_LABEL",
            creator=cls.user,
        )

        # Create a corpus
        cls.corpus = Corpus.objects.create(
            title="Annotated Corpus",
            creator=cls.user,
            is_public=True,
        )

        # Create documents and add them to corpus
        cls.doc1 = Document.objects.create(title="ADoc 1", creator=cls.user)
        cls.doc2 = Document.objects.create(title="ADoc 2", creator=cls.user)
        cls.doc3 = Document.objects.create(title="ADoc 3 (deleted)", creator=cls.user)

        DocumentPath.objects.create(
            document=cls.doc1,
            corpus=cls.corpus,
            path="/adoc1.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.user,
        )
        DocumentPath.objects.create(
            document=cls.doc2,
            corpus=cls.corpus,
            path="/adoc2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.user,
        )
        # doc3 is in a deleted path — annotations on it should not count
        DocumentPath.objects.create(
            document=cls.doc3,
            corpus=cls.corpus,
            path="/adoc3.pdf",
            version_number=1,
            is_current=True,
            is_deleted=True,
            creator=cls.user,
        )

        # Create annotations on active documents
        for i in range(3):
            Annotation.objects.create(
                document=cls.doc1,
                annotation_label=cls.label,
                creator=cls.user,
                raw_text=f"annotation {i} on doc1",
                page=0,
            )
        for i in range(2):
            Annotation.objects.create(
                document=cls.doc2,
                annotation_label=cls.label,
                creator=cls.user,
                raw_text=f"annotation {i} on doc2",
                page=0,
            )
        # Annotation on deleted document — should not count
        Annotation.objects.create(
            document=cls.doc3,
            annotation_label=cls.label,
            creator=cls.user,
            raw_text="annotation on deleted doc",
            page=0,
        )

        # Create an empty corpus
        cls.empty_corpus = Corpus.objects.create(
            title="Empty Annotated Corpus",
            creator=cls.user,
            is_public=True,
        )

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user
        self.graphene_client = Client(schema, context_value=self.request)

    def test_annotation_count_returns_correct_count(self):
        """Test that annotationCount returns the correct number for a single corpus."""
        corpus_gid = to_global_id("CorpusType", self.corpus.id)

        query = """
            query GetCorpus($id: ID!) {
                corpus(id: $id) {
                    id
                    title
                    annotationCount
                }
            }
        """

        result = self.graphene_client.execute(query, variables={"id": corpus_gid})

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        corpus = result["data"]["corpus"]
        self.assertEqual(corpus["title"], "Annotated Corpus")
        # 3 on doc1 + 2 on doc2 = 5 (doc3 is deleted so its annotation excluded)
        self.assertEqual(corpus["annotationCount"], 5)

    def test_annotation_count_returns_zero_for_empty_corpus(self):
        """Test that annotationCount returns 0 for corpus with no documents."""
        corpus_gid = to_global_id("CorpusType", self.empty_corpus.id)

        query = """
            query GetCorpus($id: ID!) {
                corpus(id: $id) {
                    id
                    title
                    annotationCount
                }
            }
        """

        result = self.graphene_client.execute(query, variables={"id": corpus_gid})

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        corpus = result["data"]["corpus"]
        self.assertEqual(corpus["title"], "Empty Annotated Corpus")
        self.assertEqual(corpus["annotationCount"], 0)

    def test_annotation_count_in_list_query(self):
        """Test that annotationCount works in corpuses list query (uses subquery)."""
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            id
                            title
                            annotationCount
                        }
                    }
                }
            }
        """

        result = self.graphene_client.execute(query)

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        edges = result["data"]["corpuses"]["edges"]
        corpuses_by_title = {edge["node"]["title"]: edge["node"] for edge in edges}

        self.assertIn("Annotated Corpus", corpuses_by_title)
        self.assertIn("Empty Annotated Corpus", corpuses_by_title)

        self.assertEqual(corpuses_by_title["Annotated Corpus"]["annotationCount"], 5)
        self.assertEqual(
            corpuses_by_title["Empty Annotated Corpus"]["annotationCount"], 0
        )

    def test_both_counts_in_list_query(self):
        """Test that documentCount and annotationCount work together."""
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            id
                            title
                            documentCount
                            annotationCount
                        }
                    }
                }
            }
        """

        result = self.graphene_client.execute(query)

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        edges = result["data"]["corpuses"]["edges"]
        corpuses_by_title = {edge["node"]["title"]: edge["node"] for edge in edges}

        annotated = corpuses_by_title["Annotated Corpus"]
        self.assertEqual(annotated["documentCount"], 2)
        self.assertEqual(annotated["annotationCount"], 5)


class TestLabelSetCountOptimization(TestCase):
    """Test that LabelSet counts are efficiently resolved via corpus annotations."""

    user: User
    label_set: LabelSet
    doc_labels: list[AnnotationLabel]
    span_labels: list[AnnotationLabel]
    token_labels: list[AnnotationLabel]
    corpus: Corpus
    factory: RequestFactory
    request: HttpRequest
    graphene_client: Client

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="label_test_user",
            password="testpass123",
            email="label@test.com",
        )

        # Create a label set with various label types
        cls.label_set = LabelSet.objects.create(
            title="Test Label Set",
            creator=cls.user,
        )

        # Create labels of different types
        cls.doc_labels = []
        for i in range(3):
            label = AnnotationLabel.objects.create(
                text=f"Doc Label {i}",
                label_type="DOC_TYPE_LABEL",
                creator=cls.user,
            )
            label.included_in_labelsets.add(cls.label_set)
            cls.doc_labels.append(label)

        cls.span_labels = []
        for i in range(5):
            label = AnnotationLabel.objects.create(
                text=f"Span Label {i}",
                label_type="SPAN_LABEL",
                creator=cls.user,
            )
            label.included_in_labelsets.add(cls.label_set)
            cls.span_labels.append(label)

        cls.token_labels = []
        for i in range(2):
            label = AnnotationLabel.objects.create(
                text=f"Token Label {i}",
                label_type="TOKEN_LABEL",
                creator=cls.user,
            )
            label.included_in_labelsets.add(cls.label_set)
            cls.token_labels.append(label)

        # Create a corpus with this label set
        cls.corpus = Corpus.objects.create(
            title="Labeled Corpus",
            creator=cls.user,
            is_public=True,
            label_set=cls.label_set,
        )

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user
        self.graphene_client = Client(schema, context_value=self.request)

    def test_label_counts_in_corpus_list_query(self):
        """Test that label counts are correctly returned in corpus list query."""
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            id
                            title
                            labelSet {
                                id
                                title
                                docLabelCount
                                spanLabelCount
                                tokenLabelCount
                            }
                        }
                    }
                }
            }
        """

        result = self.graphene_client.execute(query)

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        edges = result["data"]["corpuses"]["edges"]
        # Find our labeled corpus
        labeled_corpus = None
        for edge in edges:
            if edge["node"]["title"] == "Labeled Corpus":
                labeled_corpus = edge["node"]
                break

        self.assertIsNotNone(
            labeled_corpus, "Labeled Corpus not found in query results"
        )
        assert labeled_corpus is not None
        self.assertIsNotNone(labeled_corpus["labelSet"], "LabelSet should not be None")

        label_set = labeled_corpus["labelSet"]
        self.assertEqual(label_set["title"], "Test Label Set")
        self.assertEqual(label_set["docLabelCount"], 3)
        self.assertEqual(label_set["spanLabelCount"], 5)
        self.assertEqual(label_set["tokenLabelCount"], 2)


class TestCorpusBySlugsCounts(TestCase):
    """Test that corpusBySlugs resolver annotates count subqueries."""

    user: User
    corpus: Corpus
    doc1: Document
    doc2: Document
    factory: RequestFactory
    request: HttpRequest
    graphene_client: Client

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="slug_count_user",
            password="testpass123",
            email="slug_count@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Slug Corpus",
            creator=cls.user,
            is_public=True,
        )

        cls.doc1 = Document.objects.create(title="SDoc 1", creator=cls.user)
        cls.doc2 = Document.objects.create(title="SDoc 2", creator=cls.user)

        DocumentPath.objects.create(
            document=cls.doc1,
            corpus=cls.corpus,
            path="/sdoc1.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.user,
        )
        DocumentPath.objects.create(
            document=cls.doc2,
            corpus=cls.corpus,
            path="/sdoc2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=cls.user,
        )

        label = AnnotationLabel.objects.create(
            text="Slug Label",
            label_type="SPAN_LABEL",
            creator=cls.user,
        )
        for i in range(4):
            Annotation.objects.create(
                document=cls.doc1,
                annotation_label=label,
                creator=cls.user,
                raw_text=f"annot {i}",
                page=0,
            )

    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user
        self.graphene_client = Client(schema, context_value=self.request)

    def test_corpus_by_slugs_returns_document_count(self):
        """corpusBySlugs should return efficient documentCount."""
        query = """
            query ($userSlug: String!, $corpusSlug: String!) {
                corpusBySlugs(userSlug: $userSlug, corpusSlug: $corpusSlug) {
                    id
                    title
                    documentCount
                }
            }
        """
        result = self.graphene_client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.corpus.slug,
            },
        )
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )
        corpus = result["data"]["corpusBySlugs"]
        self.assertEqual(corpus["documentCount"], 2)

    def test_corpus_by_slugs_returns_annotation_count(self):
        """corpusBySlugs should return efficient annotationCount."""
        query = """
            query ($userSlug: String!, $corpusSlug: String!) {
                corpusBySlugs(userSlug: $userSlug, corpusSlug: $corpusSlug) {
                    id
                    title
                    annotationCount
                }
            }
        """
        result = self.graphene_client.execute(
            query,
            variables={
                "userSlug": self.user.slug,
                "corpusSlug": self.corpus.slug,
            },
        )
        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )
        corpus = result["data"]["corpusBySlugs"]
        self.assertEqual(corpus["annotationCount"], 4)


class TestCorpusQueryEfficiency(TestCase):
    """
    Test that corpus queries use subqueries/annotations instead of N+1 queries.

    Uses assertNumQueries to verify query count stays constant regardless of data size.
    """

    user: User
    corpuses: list[Corpus]
    factory: RequestFactory
    request: HttpRequest
    graphene_client: Client

    @classmethod
    def setUpTestData(cls):
        """Create test data with multiple corpuses to test N+1 prevention."""
        cls.user = User.objects.create_user(
            username="efficiency_user",
            password="testpass123",
            email="efficiency@test.com",
        )

        # Create multiple corpuses with documents and annotations
        cls.corpuses = []
        for i in range(5):
            corpus = Corpus.objects.create(
                title=f"Efficiency Corpus {i}",
                creator=cls.user,
                is_public=True,
            )
            cls.corpuses.append(corpus)

            # Create documents for each corpus
            for j in range(3):
                doc = Document.objects.create(
                    title=f"Efficiency Doc {i}-{j}",
                    creator=cls.user,
                )
                DocumentPath.objects.create(
                    document=doc,
                    corpus=corpus,
                    path=f"/eff_doc_{i}_{j}.pdf",
                    version_number=1,
                    is_current=True,
                    is_deleted=False,
                    creator=cls.user,
                )

                # Create annotations for each document
                label = AnnotationLabel.objects.create(
                    text=f"Eff Label {i}-{j}",
                    label_type="SPAN_LABEL",
                    creator=cls.user,
                )
                for k in range(2):
                    Annotation.objects.create(
                        document=doc,
                        annotation_label=label,
                        creator=cls.user,
                        raw_text=f"eff annot {i}-{j}-{k}",
                        page=0,
                    )

    def setUp(self):
        """Set up test client."""
        self.factory = RequestFactory()
        self.request = self.factory.get("/graphql")
        self.request.user = self.user
        self.graphene_client = Client(schema, context_value=self.request)

    def test_corpuses_list_query_no_n_plus_1_for_counts(self):
        """
        Verify corpuses list query uses constant number of queries for counts.

        With N+1 problem, query count would scale with corpus count.
        With subquery optimization, query count stays constant.
        """
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            id
                            title
                            documentCount
                            annotationCount
                        }
                    }
                }
            }
        """

        # First run to warm up any caches
        self.graphene_client.execute(query)

        # Second run with query counting
        # The exact number may vary based on auth/permission checks,
        # but it should NOT scale with number of corpuses (no N+1)
        with self.assertNumQueries(5):
            # Expected queries:
            # 1. Content type check
            # 2-3. Permission checks with tree CTEs
            # 4. Main corpuses query with COALESCE subqueries for counts
            # 5. Prefetch for categories
            # NOTE: documents M2M was removed - counts now via DocumentPath subqueries
            # The counts (documentCount, annotationCount) come from subqueries
            # within the main query, not N+1 per corpus
            result = self.graphene_client.execute(query)

        self.assertIsNone(
            result.get("errors"), f"GraphQL errors: {result.get('errors')}"
        )

        edges = result["data"]["corpuses"]["edges"]
        # Verify we got all our test corpuses
        efficiency_corpuses = [
            e for e in edges if e["node"]["title"].startswith("Efficiency Corpus")
        ]
        self.assertEqual(len(efficiency_corpuses), 5)

        # Verify counts are populated (not None)
        for edge in efficiency_corpuses:
            self.assertIsNotNone(edge["node"]["documentCount"])
            self.assertIsNotNone(edge["node"]["annotationCount"])
            # Each corpus should have 3 documents and 6 annotations (3 docs * 2 annots)
            self.assertEqual(edge["node"]["documentCount"], 3)
            self.assertEqual(edge["node"]["annotationCount"], 6)
