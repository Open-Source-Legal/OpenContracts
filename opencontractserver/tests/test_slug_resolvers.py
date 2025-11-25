from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document


class TestContext:
    """Minimal GraphQL context with a `user` attribute."""

    def __init__(self, user):
        self.user = user


class SlugResolverTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="JSv4", password="x")
        # Create corpuses and documents
        cls.corpus = Corpus.objects.create(title="Repo One", creator=cls.user)
        original_doc = Document.objects.create(
            title="Master Agreement", creator=cls.user
        )
        cls.original_doc_slug = (
            original_doc.slug
        )  # Keep track of original slug for comparison
        cls.doc, _, _ = cls.corpus.add_document(document=original_doc, user=cls.user)
        # Create a second document with same title to test per-user uniqueness
        cls.doc2 = Document.objects.create(title="Master Agreement", creator=cls.user)
        # Another user with same corpus/doc titles should be allowed same slugs
        cls.user_b = User.objects.create_user(username="OtherUser", password="x")
        cls.corpus_b = Corpus.objects.create(title="Repo One", creator=cls.user_b)
        cls.doc_b = Document.objects.create(
            title="Master Agreement", creator=cls.user_b
        )

    def setUp(self):
        self.client = Client(schema, context_value=TestContext(self.user))

    def test_model_slug_generation_and_uniqueness(self):
        # User slug exists
        self.assertTrue(self.user.slug)
        # Corpus slug unique per creator
        self.assertTrue(self.corpus.slug)
        # Documents have unique slugs under same user
        self.assertNotEqual(self.doc.slug, self.doc2.slug)
        # Other user's corpus/doc may reuse the same slugs
        self.assertEqual(self.corpus.slug, self.corpus_b.slug)
        # Use original doc slug for comparison (before add_document created a new document)
        self.assertEqual(self.original_doc_slug, self.doc_b.slug)

    def test_user_by_slug_query(self):
        query = """
            query($slug: String!) {
              userBySlug(slug: $slug) { id username slug }
            }
        """
        res = self.client.execute(query, variables={"slug": self.user.slug})
        self.assertIsNone(res.get("errors"))
        self.assertEqual(res["data"]["userBySlug"]["slug"], self.user.slug)

    def test_corpus_by_slugs_query(self):
        query = """
            query($u: String!, $c: String!) {
              corpusBySlugs(userSlug: $u, corpusSlug: $c) { id slug }
            }
        """
        res = self.client.execute(
            query, variables={"u": self.user.slug, "c": self.corpus.slug}
        )
        self.assertIsNone(res.get("errors"))
        self.assertEqual(res["data"]["corpusBySlugs"]["slug"], self.corpus.slug)

    def test_document_by_slugs_query(self):
        query = """
            query($u: String!, $d: String!) {
              documentBySlugs(userSlug: $u, documentSlug: $d) { id slug }
            }
        """
        res = self.client.execute(
            query, variables={"u": self.user.slug, "d": self.doc.slug}
        )
        self.assertIsNone(res.get("errors"))
        self.assertEqual(res["data"]["documentBySlugs"]["slug"], self.doc.slug)

    def test_document_in_corpus_by_slugs_query(self):
        query = """
            query($u: String!, $c: String!, $d: String!) {
              documentInCorpusBySlugs(userSlug: $u, corpusSlug: $c, documentSlug: $d) {
                id
                slug
              }
            }
        """
        res = self.client.execute(
            query,
            variables={"u": self.user.slug, "c": self.corpus.slug, "d": self.doc.slug},
        )
        self.assertIsNone(res.get("errors"))
        self.assertEqual(res["data"]["documentInCorpusBySlugs"]["slug"], self.doc.slug)

        # If document is not in corpus, expect null
        res2 = self.client.execute(
            query,
            variables={
                "u": self.user.slug,
                "c": self.corpus.slug,
                "d": self.doc2.slug,  # doc2 not added to corpus
            },
        )
        self.assertIsNone(res2.get("errors"))
        self.assertIsNone(res2["data"]["documentInCorpusBySlugs"])
