"""Tests for the Discover hybrid-search GraphQL resolvers.

Covers the five Discover categories backed by ``DiscoverSearchQueryMixin``:
annotations, documents, notes, collections (corpuses), and discussions
(threads). Each resolver fuses a text arm (substring + PostgreSQL full-text)
with a semantic arm (pgvector). These tests exercise the text arm and
permission filtering deterministically by disabling the semantic arm
(``_query_vector`` -> None); one dedicated test re-enables it with a stubbed
query vector to prove fusion surfaces semantic-only hits.
"""

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
        # An annotation owned by ``other`` that must never leak to ``user``.
        # Annotation visibility is *inherited* from the document + corpus
        # (regular annotations have no individual privacy field of their own —
        # see AnnotationQuerySet.visible_to_user), so the only way to hide one
        # from ``user`` is to place it on a container ``user`` cannot read.
        # This proves the discover resolver filters on inherited visibility.
        self.other_private_corpus = Corpus.objects.create(
            title="Other private corpus",
            creator=self.other,
            is_public=False,
        )
        self.other_private_doc = Document.objects.create(
            title="Other private doc",
            creator=self.other,
            is_public=False,
        )
        _link(
            self.other_private_doc,
            self.other_private_corpus,
            self.other,
            "/secret.pdf",
        )
        self.private_other_ann = Annotation.objects.create(
            document=self.other_private_doc,
            corpus=self.other_private_corpus,
            creator=self.other,
            raw_text="indemnify secret confidential",
            page=0,
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

        self.graphene_client = Client(schema, context_value=TestContext(self.user))
        # The query-vector LRU is process-global; clear it so a vector cached by
        # a prior test can't bypass the patch below (and so this test's entries
        # don't leak into the next). See discover_queries._cached_query_vector.
        from config.graphql.discover_queries import _cached_query_vector

        _cached_query_vector.cache_clear()
        self.addCleanup(_cached_query_vector.cache_clear)
        # Disable the semantic arm so these assertions are deterministic.
        p = patch("config.graphql.discover_queries._query_vector", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    # ------------------------------------------------------------------ #
    def _run(self, field, query="indemnification"):
        result = self.graphene_client.execute(
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
        result = self.graphene_client.execute(
            "query D($t: String!){ discoverAnnotations(textSearch:$t){ id rawText } }",
            variables={"t": "indemnify"},  # FTS stems indemnify==indemnification
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        texts = [n["rawText"] for n in result["data"]["discoverAnnotations"]]
        self.assertIn("The seller shall indemnify the buyer for losses", texts)
        # Annotation on an unreadable document/corpus must not appear.
        self.assertNotIn("indemnify secret confidential", texts)

    def test_discover_documents_text_match(self):
        rows = self._run("discoverDocuments")
        self.assertEqual(len(rows), 1)

    def test_discover_documents_is_a_new_category(self):
        result = self.graphene_client.execute(
            "query D($t: String!){ discoverDocuments(textSearch:$t){ id title } }",
            variables={"t": "Indemnification"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [d["title"] for d in result["data"]["discoverDocuments"]]
        self.assertIn("Indemnification Schedule", titles)

    def test_discover_notes_fts_stemming(self):
        # "indemnifications" only matches "indemnification" via FTS stemming
        # (both share the lexeme "indemnif"), proving the new
        # Note.search_vector path works — a plain icontains substring match
        # would miss it, since "indemnifications" is not a substring of the
        # note's title or content.
        result = self.graphene_client.execute(
            "query D($t: String!){ discoverNotes(textSearch:$t){ id title } }",
            variables={"t": "indemnifications"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [n["title"] for n in result["data"]["discoverNotes"]]
        self.assertIn("Indemnification notes", titles)

    def test_discover_corpuses_matches_by_title(self):
        result = self.graphene_client.execute(
            "query D($t: String!){ discoverCorpuses(textSearch:$t){ id title } }",
            variables={"t": "merger"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [c["title"] for c in result["data"]["discoverCorpuses"]]
        self.assertIn("Merger Agreements", titles)

    def test_discover_corpuses_matches_by_contained_content(self):
        # The corpus title/description do NOT contain "indemnification"; it is
        # surfaced via its contained document + annotation matching.
        result = self.graphene_client.execute(
            "query D($t: String!){ discoverCorpuses(textSearch:$t){ id title } }",
            variables={"t": "indemnification"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [c["title"] for c in result["data"]["discoverCorpuses"]]
        self.assertIn("Merger Agreements", titles)

    def test_discover_corpuses_excludes_unreadable_content_match(self):
        # "confidential" appears ONLY in ``private_other_ann``, which lives on a
        # corpus/document ``user`` cannot read. The corpus content-match arm
        # filters Annotation through ``filter_visible`` before collecting corpus
        # ids, AND the final fetch re-filters Corpus through ``filter_visible``,
        # so the unreadable collection must never surface — even though its
        # contained text matches the query. (Mirrors the annotation-arm leak
        # assertion in ``test_discover_annotations_text_match``.)
        result = self.graphene_client.execute(
            "query D($t: String!){ discoverCorpuses(textSearch:$t){ id title } }",
            variables={"t": "confidential"},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        titles = [c["title"] for c in result["data"]["discoverCorpuses"]]
        self.assertNotIn("Other private corpus", titles)

    def test_discover_limit_caps_results(self):
        # A second visible annotation that also matches "indemnify", so without
        # a cap the fused result set would hold more than one row.
        Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Buyer agrees to indemnify the seller as well",
            page=1,
            is_public=True,
        )
        # The default limit surfaces both matches...
        unlimited = self.graphene_client.execute(
            "query D($t: String!){ discoverAnnotations(textSearch:$t){ id } }",
            variables={"t": "indemnify"},
        )
        self.assertIsNone(unlimited.get("errors"), unlimited.get("errors"))
        self.assertGreaterEqual(
            len(unlimited["data"]["discoverAnnotations"]),
            2,
            "control: >1 visible annotation should match before the cap",
        )
        # ...but limit=1 clamps the fused result set to a single row end-to-end
        # (_clamp_limit -> _rrf(..., limit)).
        capped = self.graphene_client.execute(
            "query D($t: String!, $l: Int){"
            " discoverAnnotations(textSearch:$t, limit:$l){ id } }",
            variables={"t": "indemnify", "l": 1},
        )
        self.assertIsNone(capped.get("errors"), capped.get("errors"))
        self.assertEqual(len(capped["data"]["discoverAnnotations"]), 1)

    def test_discover_discussions_matches_message_body_not_just_title(self):
        result = self.graphene_client.execute(
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

        self.graphene_client = Client(schema, context_value=TestContext(self.user))
        # Clear the process-global query-vector LRU so the in-test patch is hit
        # on a cache miss (and doesn't leak into other suites).
        from config.graphql.discover_queries import _cached_query_vector

        _cached_query_vector.cache_clear()
        self.addCleanup(_cached_query_vector.cache_clear)

    def test_semantic_only_hit(self):
        # Resolve the default embedder at runtime — calling
        # get_default_embedder_path() in a decorator would hit the DB during
        # pytest collection (before db access is permitted).
        if not get_default_embedder_path():
            self.skipTest(
                "No default embedder configured; semantic arm cannot be exercised."
            )
        with patch(
            "config.graphql.discover_queries._query_vector",
            return_value=self.vector,
        ):
            result = self.graphene_client.execute(
                "query D($t: String!){ discoverAnnotations(textSearch:$t){ id rawText } }",
                variables={"t": "semantic concept with no shared words"},
            )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        texts = [n["rawText"] for n in result["data"]["discoverAnnotations"]]
        self.assertIn("zzz totally unrelated lexical content", texts)


class DiscoverHelperTest(TestCase):
    """Pure-function coverage for the fusion/ranking helpers (no DB)."""

    def test_clamp_limit_none_and_nonpositive_fall_back_to_default(self):
        from config.graphql.discover_queries import _clamp_limit
        from opencontractserver.constants.search import DISCOVER_DEFAULT_LIMIT

        # None, 0 and negatives all collapse to the documented default rather
        # than producing an empty / inverted slice.
        self.assertEqual(_clamp_limit(None), DISCOVER_DEFAULT_LIMIT)
        self.assertEqual(_clamp_limit(0), DISCOVER_DEFAULT_LIMIT)
        self.assertEqual(_clamp_limit(-1), DISCOVER_DEFAULT_LIMIT)

    def test_clamp_limit_caps_at_semantic_max(self):
        from config.graphql.discover_queries import _clamp_limit
        from opencontractserver.constants.annotations import (
            SEMANTIC_SEARCH_MAX_RESULTS,
        )

        self.assertEqual(_clamp_limit(5), 5)
        self.assertEqual(
            _clamp_limit(SEMANTIC_SEARCH_MAX_RESULTS + 1000),
            SEMANTIC_SEARCH_MAX_RESULTS,
        )

    def test_rrf_tie_break_is_deterministic_and_type_agnostic(self):
        from config.graphql.discover_queries import _rrf

        # Two ids tied on score (each appears once at rank 0 in its own arm)
        # must order deterministically by str(id). Mixing int and str ids would
        # raise TypeError under the old ``(-score, id)`` key; str() keeps it
        # total-orderable.
        fused = _rrf([[2], ["10"]], limit=10)
        self.assertEqual(sorted(fused, key=str), sorted([2, "10"], key=str))
        self.assertEqual(fused, sorted([2, "10"], key=str))
