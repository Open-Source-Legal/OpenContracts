"""Tests for the Discover hybrid-search GraphQL resolvers.

Covers the five Discover categories backed by ``DiscoverSearchQueryMixin``:
annotations, documents, notes, collections (corpuses), and discussions
(threads). Each resolver fuses a text arm (substring + PostgreSQL full-text)
with a semantic arm (pgvector). These tests exercise the text arm and
permission filtering deterministically by disabling the semantic arm
(``_query_vector`` -> None); one dedicated test re-enables it with a stubbed
query vector to prove fusion surfaces semantic-only hits.
"""

from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation, Note
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    MessageTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.pipeline.utils import get_default_embedder_path
from opencontractserver.utils.permissioning import (
    PermissionTypes,
    set_permissions_for_obj_to_user,
)

User = get_user_model()


class TestContext:
    """Minimal GraphQL context exposing the authenticated user."""

    def __init__(self, user):
        self.user = user


def _link(document, corpus, user, path):
    DocumentPath.objects.create(
        document=document,
        corpus=corpus,
        path=path,
        version_number=1,
        is_current=True,
        is_deleted=False,
        creator=user,
    )


class DiscoverSearchTextArmTest(TestCase):
    """Text-arm + permission behaviour with the semantic arm disabled."""

    def setUp(self):
        self.user = User.objects.create_user(username="disc_user", password="pw")
        self.other = User.objects.create_user(username="disc_other", password="pw")

        self.corpus = Corpus.objects.create(
            title="Merger Agreements",
            description="A collection of merger docs",
            creator=self.user,
            is_public=True,
            preferred_embedder=get_default_embedder_path(),
        )
        set_permissions_for_obj_to_user(
            user_val=self.user, instance=self.corpus, permissions=[PermissionTypes.ALL]
        )

        self.document = Document.objects.create(
            title="Indemnification Schedule",
            description="Doc describing indemnification",
            creator=self.user,
            is_public=True,
        )
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=self.document,
            permissions=[PermissionTypes.ALL],
        )
        _link(self.document, self.corpus, self.user, "/indemnification.pdf")

        self.annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.user,
            raw_text="The seller shall indemnify the buyer for losses",
            page=0,
            is_public=True,
        )
        # A private annotation owned by ``other`` must never leak to ``user``.
        self.private_other_ann = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.other,
            raw_text="indemnify secret confidential",
            page=1,
            is_public=False,
        )

        self.note = Note.objects.create(
            title="Indemnification notes",
            content="Key points about indemnification clauses",
            document=self.document,
            corpus=self.corpus,
            creator=self.user,
            is_public=True,
        )

        # A thread whose TITLE does not match, but a MESSAGE body does.
        self.thread = Conversation.objects.create(
            title="Q3 deal sync",
            creator=self.user,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            is_public=True,
        )
        ChatMessage.objects.create(
            conversation=self.thread,
            creator=self.user,
            msg_type=MessageTypeChoices.HUMAN,
            content="Lots of discussion about indemnification here",
        )
        # A CHAT (not a thread) whose title matches — must be excluded.
        self.chat = Conversation.objects.create(
            title="indemnification chat",
            creator=self.user,
            conversation_type=ConversationTypeChoices.CHAT,
            is_public=True,
        )

        self.client = Client(schema, context_value=TestContext(self.user))
        # Disable the semantic arm so these assertions are deterministic.
        p = patch("config.graphql.discover_queries._query_vector", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    # ------------------------------------------------------------------ #
    def _run(self, field, query="indemnification"):
        result = self.client.execute(
            """
            query D($t: String!) {
              %s(textSearch: $t) { __typename }
            }
            """ % field,
            variables={"t": query},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        return result["data"][field]

    def test_discover_annotations_text_match(self):
        result = self.client.execute(
            "query D($t: String!){ discoverAnnotations(textSearch:$t){ id rawText } }",
            variables={"t": "indemnify"},  # FTS stems indemnify==indemnification
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        texts = [n["rawText"] for n in result["data"]["discoverAnnotations"]]
        self.assertIn("The seller shall indemnify the buyer for losses", texts)
        # Private annotation owned by other user must not appear.
        self.assertNotIn("indemnify secret confidential", texts)

    def test_discover_documents_text_match(self):
        rows = self._run("discoverDocuments")
        self.assertEqual(len(rows), 1)

    def test_discover_documents_is_a_new_category(self):
        result = self.client.execute(
            "query D($t: String!){ discoverDocuments(textSearch:$t){ id title } }",
            variables={"t": "Indemnification"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [d["title"] for d in result["data"]["discoverDocuments"]]
        self.assertIn("Indemnification Schedule", titles)

    def test_discover_notes_fts_stemming(self):
        # "indemnify" only matches "indemnification" via FTS stemming, proving
        # the new Note.search_vector path works (icontains alone would miss it).
        result = self.client.execute(
            "query D($t: String!){ discoverNotes(textSearch:$t){ id title } }",
            variables={"t": "indemnify"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [n["title"] for n in result["data"]["discoverNotes"]]
        self.assertIn("Indemnification notes", titles)

    def test_discover_corpuses_matches_by_title(self):
        result = self.client.execute(
            "query D($t: String!){ discoverCorpuses(textSearch:$t){ id title } }",
            variables={"t": "merger"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [c["title"] for c in result["data"]["discoverCorpuses"]]
        self.assertIn("Merger Agreements", titles)

    def test_discover_corpuses_matches_by_contained_content(self):
        # The corpus title/description do NOT contain "indemnification"; it is
        # surfaced via its contained document + annotation matching.
        result = self.client.execute(
            "query D($t: String!){ discoverCorpuses(textSearch:$t){ id title } }",
            variables={"t": "indemnification"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [c["title"] for c in result["data"]["discoverCorpuses"]]
        self.assertIn("Merger Agreements", titles)

    def test_discover_discussions_matches_message_body_not_just_title(self):
        result = self.client.execute(
            "query D($t: String!){ discoverDiscussions(textSearch:$t){ id title } }",
            variables={"t": "indemnification"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [c["title"] for c in result["data"]["discoverDiscussions"]]
        # Thread surfaced via its message body even though title is "Q3 deal sync".
        self.assertIn("Q3 deal sync", titles)
        # CHAT-type conversation is excluded even though its title matches.
        self.assertNotIn("indemnification chat", titles)

    def test_empty_query_returns_empty(self):
        for field in (
            "discoverAnnotations",
            "discoverDocuments",
            "discoverNotes",
            "discoverCorpuses",
            "discoverDiscussions",
        ):
            rows = self._run(field, query="   ")
            self.assertEqual(rows, [], field)


class DiscoverSemanticArmTest(TestCase):
    """Prove the semantic arm contributes hits the text arm cannot find."""

    def setUp(self):
        self.user = User.objects.create_user(username="disc_sem", password="pw")
        self.corpus = Corpus.objects.create(
            title="Corpus",
            creator=self.user,
            is_public=True,
            preferred_embedder=get_default_embedder_path(),
        )
        set_permissions_for_obj_to_user(
            user_val=self.user, instance=self.corpus, permissions=[PermissionTypes.ALL]
        )
        self.document = Document.objects.create(
            title="Doc", creator=self.user, is_public=True
        )
        set_permissions_for_obj_to_user(
            user_val=self.user,
            instance=self.document,
            permissions=[PermissionTypes.ALL],
        )
        _link(self.document, self.corpus, self.user, "/doc.pdf")

        # Annotation text shares NO tokens with the query, so only a vector
        # match can surface it.
        self.annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.user,
            raw_text="zzz totally unrelated lexical content",
            page=0,
            is_public=True,
        )
        self.embedder_path = get_default_embedder_path()
        # Store an embedding for the annotation and make the query embed to the
        # same vector so cosine distance is ~0.
        self.vector = [0.5] * 384
        self.annotation.add_embedding(self.embedder_path, self.vector)

        self.client = Client(schema, context_value=TestContext(self.user))

    @skipUnless(
        get_default_embedder_path(),
        "No default embedder configured; semantic arm cannot be exercised.",
    )
    def test_semantic_only_hit(self):
        with patch(
            "config.graphql.discover_queries._query_vector",
            return_value=self.vector,
        ):
            result = self.client.execute(
                "query D($t: String!){ discoverAnnotations(textSearch:$t){ id rawText } }",
                variables={"t": "semantic concept with no shared words"},
            )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        texts = [n["rawText"] for n in result["data"]["discoverAnnotations"]]
        self.assertIn("zzz totally unrelated lexical content", texts)
