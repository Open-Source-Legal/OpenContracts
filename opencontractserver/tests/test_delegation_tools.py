"""Unit tests for the delegation tool factory."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath

User = get_user_model()


class FilterByScopeTests(TestCase):
    """Tests for ``filter_by_scope`` chat-scope filtering of agent querysets."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="u", password="x", email="u@example.com"
        )
        self.corpus_a = Corpus.objects.create(title="A", creator=self.user)
        self.corpus_b = Corpus.objects.create(title="B", creator=self.user)

        # Document `doc_in_a` lives in corpus_a via DocumentPath (the actual
        # Document <-> Corpus relation in this codebase — there is no FK or
        # M2M directly on Document).
        self.doc_in_a = Document.objects.create(title="D", creator=self.user)
        DocumentPath.objects.create(
            document=self.doc_in_a,
            corpus=self.corpus_a,
            path="/d.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        self.global_agent = AgentConfiguration.objects.create(
            name="Global",
            slug="global-bot",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="g",
        )
        self.corpus_a_agent = AgentConfiguration.objects.create(
            name="A Bot",
            slug="a-bot",
            scope="CORPUS",
            corpus=self.corpus_a,
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="a",
        )
        self.corpus_b_agent = AgentConfiguration.objects.create(
            name="B Bot",
            slug="b-bot",
            scope="CORPUS",
            corpus=self.corpus_b,
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="b",
        )

    def test_standalone_doc_chat_yields_global_only(self):
        from opencontractserver.llms.tools.delegation_tools import filter_by_scope

        qs = AgentConfiguration.objects.all()
        result = list(filter_by_scope(qs, corpus_id=None, document_id=None))
        slugs = {a.slug for a in result}
        self.assertIn("global-bot", slugs)
        self.assertNotIn("a-bot", slugs)
        self.assertNotIn("b-bot", slugs)

    def test_corpus_chat_yields_global_plus_that_corpus(self):
        from opencontractserver.llms.tools.delegation_tools import filter_by_scope

        qs = AgentConfiguration.objects.all()
        result = list(filter_by_scope(qs, corpus_id=self.corpus_a.id, document_id=None))
        slugs = {a.slug for a in result}
        self.assertIn("global-bot", slugs)
        self.assertIn("a-bot", slugs)
        self.assertNotIn("b-bot", slugs)

    def test_doc_in_corpus_chat_yields_global_plus_that_corpus(self):
        from opencontractserver.llms.tools.delegation_tools import filter_by_scope

        qs = AgentConfiguration.objects.all()
        result = list(filter_by_scope(qs, corpus_id=None, document_id=self.doc_in_a.id))
        slugs = {a.slug for a in result}
        self.assertIn("global-bot", slugs)
        self.assertIn("a-bot", slugs)
        self.assertNotIn("b-bot", slugs)

    def test_doc_without_corpus_yields_global_only(self):
        # Standalone doc — not in any corpus (no DocumentPath).
        standalone = Document.objects.create(title="standalone", creator=self.user)
        from opencontractserver.llms.tools.delegation_tools import filter_by_scope

        qs = AgentConfiguration.objects.all()
        result = list(filter_by_scope(qs, corpus_id=None, document_id=standalone.id))
        slugs = {a.slug for a in result}
        # Only assert behaviour for agents we created in setUp: corpus-scoped
        # agents must NOT appear, but the global one must. Other test-DB
        # fixtures (e.g. seeded defaults) are tolerated as long as they're
        # not corpus-scoped to A or B.
        self.assertIn("global-bot", slugs)
        self.assertNotIn("a-bot", slugs)
        self.assertNotIn("b-bot", slugs)
        # No result should be a CORPUS-scoped agent.
        scopes = {a.scope for a in result}
        self.assertEqual(scopes - {"GLOBAL"}, set())
