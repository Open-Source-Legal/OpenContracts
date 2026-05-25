"""Tests for the corpus voting feature.

Covers:

1. ``CorpusVoteService`` — auth + anonymous voting, self-vote block, dedup,
   vote-type switching, idempotent removal, READ permission gate.
2. ``CorpusVote`` model — partial UNIQUE constraints (auth + anon branches).
3. Denormalized count maintenance on ``Corpus`` via signal handlers.
4. ``GraphQL`` voteCorpus / removeCorpusVote mutations end-to-end through
   graphene's schema (covers the session-key bootstrap path that lives in
   ``voting_mutations.py``).

Designed to be runnable in isolation:

    docker compose -f test.yml run django \\
        python manage.py test opencontractserver.tests.test_corpus_voting --keepdb
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusVote,
    CorpusVoteType,
)
from opencontractserver.corpuses.services import CorpusVoteService

if TYPE_CHECKING:
    from opencontractserver.users.models import User as UserType

User = get_user_model()


def _corpus_relay_id(pk: int) -> str:
    """Encode a Corpus pk as the Relay global ID used by the GraphQL surface."""
    from graphql_relay import to_global_id

    return to_global_id("CorpusType", pk)


class CorpusVoteServiceTests(TestCase):
    """Service-layer behavioural contract for corpus voting."""

    # Declared at class level so mypy can see attributes assigned in
    # ``setUpTestData`` — the django-stubs plugin doesn't infer ``cls.foo``
    # assignments inside ``@classmethod`` into the class namespace.
    owner: UserType
    alice: UserType
    bob: UserType
    public_corpus: Corpus
    private_corpus: Corpus

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(
            username="owner", password="pw", email="owner@example.com"
        )
        cls.alice = User.objects.create_user(
            username="alice", password="pw", email="alice@example.com"
        )
        cls.bob = User.objects.create_user(
            username="bob", password="pw", email="bob@example.com"
        )
        cls.public_corpus = Corpus.objects.create(
            title="Public",
            description="public",
            creator=cls.owner,
            is_public=True,
        )
        cls.private_corpus = Corpus.objects.create(
            title="Private",
            description="private",
            creator=cls.owner,
            is_public=False,
        )

    # ----------------------------------------------------------------- auth
    def test_cast_vote_creates_authenticated_vote(self) -> None:
        result = CorpusVoteService.cast_vote(
            self.alice, self.public_corpus.pk, "upvote"
        )
        self.assertTrue(result.ok, msg=result.error)
        assert result.value is not None
        self.assertEqual(result.value.corpus_id, self.public_corpus.pk)
        self.assertEqual(result.value.creator_id, self.alice.pk)
        self.assertEqual(result.value.vote_type, "upvote")
        self.assertIsNone(result.value.session_key)

    def test_cast_vote_switches_vote_type(self) -> None:
        CorpusVoteService.cast_vote(self.alice, self.public_corpus.pk, "upvote")
        result = CorpusVoteService.cast_vote(
            self.alice, self.public_corpus.pk, "downvote"
        )
        self.assertTrue(result.ok)
        assert result.value is not None
        self.assertEqual(result.value.vote_type, "downvote")
        # Only one row — switching shouldn't insert a second vote.
        self.assertEqual(
            CorpusVote.objects.filter(
                corpus=self.public_corpus, creator=self.alice
            ).count(),
            1,
        )

    def test_cast_vote_blocks_self_vote(self) -> None:
        result = CorpusVoteService.cast_vote(
            self.owner, self.public_corpus.pk, "upvote"
        )
        self.assertFalse(result.ok)
        self.assertIn("own corpus", result.error.lower())

    def test_cast_vote_idor_safe_when_corpus_missing(self) -> None:
        result = CorpusVoteService.cast_vote(self.alice, 9_999_999, "upvote")
        self.assertFalse(result.ok)
        # Same denial text for "no permission" vs "doesn't exist" — pin it.
        self.assertIn("permission", result.error.lower())

    def test_cast_vote_anonymous_blocked_on_private_corpus(self) -> None:
        # Anonymous users can only see public corpuses; their READ check
        # against a private corpus collapses to the unified IDOR denial.
        result = CorpusVoteService.cast_vote(
            AnonymousUser(),
            self.private_corpus.pk,
            "upvote",
            session_key="anon-session-1",
        )
        self.assertFalse(result.ok)
        self.assertIn("permission", result.error.lower())

    def test_cast_vote_authenticated_blocked_on_private_corpus(self) -> None:
        # Alice has no explicit READ grant and isn't the creator.
        result = CorpusVoteService.cast_vote(
            self.alice, self.private_corpus.pk, "upvote"
        )
        self.assertFalse(result.ok)
        self.assertIn("permission", result.error.lower())

    def test_cast_vote_rejects_invalid_vote_type(self) -> None:
        result = CorpusVoteService.cast_vote(
            self.alice, self.public_corpus.pk, "sideways"
        )
        self.assertFalse(result.ok)
        self.assertIn("Invalid vote_type", result.error)

    # ------------------------------------------------------------ anonymous
    def test_cast_vote_anonymous_creates_session_keyed_vote(self) -> None:
        result = CorpusVoteService.cast_vote(
            AnonymousUser(),
            self.public_corpus.pk,
            "upvote",
            session_key="anon-1",
            ip_address="203.0.113.10",
        )
        self.assertTrue(result.ok, msg=result.error)
        assert result.value is not None
        self.assertIsNone(result.value.creator_id)
        self.assertEqual(result.value.session_key, "anon-1")
        self.assertTrue(result.value.ip_hash)  # salted SHA-256, just exists

    def test_cast_vote_anonymous_requires_session_key(self) -> None:
        result = CorpusVoteService.cast_vote(
            AnonymousUser(), self.public_corpus.pk, "upvote"
        )
        self.assertFalse(result.ok)
        self.assertIn("session", result.error.lower())

    def test_cast_vote_anonymous_idempotent_on_repeat(self) -> None:
        first = CorpusVoteService.cast_vote(
            AnonymousUser(),
            self.public_corpus.pk,
            "upvote",
            session_key="anon-2",
        )
        second = CorpusVoteService.cast_vote(
            AnonymousUser(),
            self.public_corpus.pk,
            "upvote",
            session_key="anon-2",
        )
        self.assertTrue(first.ok and second.ok)
        # Same row updated, not a new one.
        assert first.value is not None and second.value is not None
        self.assertEqual(first.value.pk, second.value.pk)

    def test_cast_vote_does_not_let_user_take_over_anon_vote(self) -> None:
        # Alice's session voted as anon; later Alice logs in and votes
        # again.  The two branches MUST stay separate — otherwise a
        # logged-in user could "claim" an anonymous vote and double-count.
        CorpusVoteService.cast_vote(
            AnonymousUser(),
            self.public_corpus.pk,
            "upvote",
            session_key="alice-session",
        )
        CorpusVoteService.cast_vote(self.alice, self.public_corpus.pk, "upvote")
        votes = CorpusVote.objects.filter(corpus=self.public_corpus)
        self.assertEqual(votes.count(), 2)
        self.assertEqual(votes.filter(creator__isnull=True).count(), 1)
        self.assertEqual(votes.filter(creator=self.alice).count(), 1)

    # ----------------------------------------------------------- remove
    def test_remove_vote_idempotent_when_nothing_to_remove(self) -> None:
        result = CorpusVoteService.remove_vote(self.alice, self.public_corpus.pk)
        self.assertTrue(result.ok)
        self.assertFalse(result.value)  # nothing removed

    def test_remove_vote_removes_authenticated_vote(self) -> None:
        CorpusVoteService.cast_vote(self.alice, self.public_corpus.pk, "upvote")
        result = CorpusVoteService.remove_vote(self.alice, self.public_corpus.pk)
        self.assertTrue(result.ok)
        self.assertTrue(result.value)
        self.assertFalse(
            CorpusVote.objects.filter(
                corpus=self.public_corpus, creator=self.alice
            ).exists()
        )

    def test_remove_vote_removes_anonymous_vote(self) -> None:
        CorpusVoteService.cast_vote(
            AnonymousUser(),
            self.public_corpus.pk,
            "downvote",
            session_key="anon-r",
        )
        result = CorpusVoteService.remove_vote(
            AnonymousUser(),
            self.public_corpus.pk,
            session_key="anon-r",
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.value)
        self.assertFalse(
            CorpusVote.objects.filter(
                corpus=self.public_corpus, session_key="anon-r"
            ).exists()
        )

    # --------------------------------------------------------- my_vote
    def test_get_user_vote_type_returns_current_state(self) -> None:
        self.assertIsNone(
            CorpusVoteService.get_user_vote_type(self.alice, self.public_corpus)
        )
        CorpusVoteService.cast_vote(self.alice, self.public_corpus.pk, "upvote")
        self.assertEqual(
            CorpusVoteService.get_user_vote_type(self.alice, self.public_corpus),
            "upvote",
        )

    def test_get_user_vote_type_for_anonymous(self) -> None:
        CorpusVoteService.cast_vote(
            AnonymousUser(),
            self.public_corpus.pk,
            "downvote",
            session_key="anon-x",
        )
        self.assertEqual(
            CorpusVoteService.get_user_vote_type(
                AnonymousUser(),
                self.public_corpus,
                session_key="anon-x",
            ),
            "downvote",
        )
        # Different session — no vote.
        self.assertIsNone(
            CorpusVoteService.get_user_vote_type(
                AnonymousUser(),
                self.public_corpus,
                session_key="other-anon",
            )
        )


class CorpusVoteCountDenormalizationTests(TransactionTestCase):
    """Signal-driven count maintenance on ``Corpus``.

    Uses ``TransactionTestCase`` because the recompute signal commits its
    ``QuerySet.update(...)`` outside of any per-test transaction guard,
    and Django's ``TestCase`` (with its enclosing transaction) would
    obscure the post-commit count refresh.
    """

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="owner-dn", password="pw", email="o-dn@example.com"
        )
        self.alice = User.objects.create_user(
            username="alice-dn", password="pw", email="a-dn@example.com"
        )
        self.bob = User.objects.create_user(
            username="bob-dn", password="pw", email="b-dn@example.com"
        )
        self.corpus = Corpus.objects.create(
            title="Counts",
            description="counts",
            creator=self.owner,
            is_public=True,
        )

    def _refresh(self) -> Corpus:
        self.corpus.refresh_from_db()
        return self.corpus

    def test_create_upvote_increments_upvote_count(self) -> None:
        CorpusVoteService.cast_vote(self.alice, self.corpus.pk, "upvote")
        c = self._refresh()
        self.assertEqual(c.upvote_count, 1)
        self.assertEqual(c.downvote_count, 0)
        self.assertEqual(c.score, 1)

    def test_switching_vote_type_recomputes_both_counts(self) -> None:
        CorpusVoteService.cast_vote(self.alice, self.corpus.pk, "upvote")
        CorpusVoteService.cast_vote(self.bob, self.corpus.pk, "downvote")
        c1 = self._refresh()
        self.assertEqual(c1.score, 0)

        CorpusVoteService.cast_vote(self.alice, self.corpus.pk, "downvote")
        c2 = self._refresh()
        self.assertEqual(c2.upvote_count, 0)
        self.assertEqual(c2.downvote_count, 2)
        self.assertEqual(c2.score, -2)

    def test_remove_vote_decrements_count(self) -> None:
        CorpusVoteService.cast_vote(self.alice, self.corpus.pk, "upvote")
        CorpusVoteService.remove_vote(self.alice, self.corpus.pk)
        c = self._refresh()
        self.assertEqual(c.upvote_count, 0)
        self.assertEqual(c.score, 0)


class CorpusVoteUniqueConstraintTests(TransactionTestCase):
    """Pin the two partial UNIQUE indexes added in migration 0049."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="owner-c", password="pw", email="o-c@example.com"
        )
        self.alice = User.objects.create_user(
            username="alice-c", password="pw", email="a-c@example.com"
        )
        self.corpus = Corpus.objects.create(
            title="ConstraintCorpus",
            description="x",
            creator=self.owner,
            is_public=True,
        )

    def test_one_vote_per_user_per_corpus(self) -> None:
        CorpusVote.objects.create(
            corpus=self.corpus,
            creator=self.alice,
            vote_type=CorpusVoteType.UPVOTE,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CorpusVote.objects.create(
                    corpus=self.corpus,
                    creator=self.alice,
                    vote_type=CorpusVoteType.DOWNVOTE,
                )

    def test_one_anon_vote_per_session_per_corpus(self) -> None:
        CorpusVote.objects.create(
            corpus=self.corpus,
            creator=None,
            session_key="dup-sess",
            vote_type=CorpusVoteType.UPVOTE,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CorpusVote.objects.create(
                    corpus=self.corpus,
                    creator=None,
                    session_key="dup-sess",
                    vote_type=CorpusVoteType.DOWNVOTE,
                )

    def test_partial_index_allows_anon_alongside_authenticated(self) -> None:
        # The partial conditions deliberately partition the namespace so
        # the auth and anon branches do not collide.
        CorpusVote.objects.create(
            corpus=self.corpus,
            creator=self.alice,
            vote_type=CorpusVoteType.UPVOTE,
        )
        # No exception — anonymous slot is independent.
        CorpusVote.objects.create(
            corpus=self.corpus,
            creator=None,
            session_key="independent-sess",
            vote_type=CorpusVoteType.UPVOTE,
        )

    def test_partial_index_allows_unbounded_null_session_under_auth(self) -> None:
        """A second auth vote on a different corpus must succeed — pin that the
        partial UNIQUE doesn't accidentally fire across all-NULL session keys.
        """
        other = Corpus.objects.create(
            title="Other",
            description="o",
            creator=self.owner,
            is_public=True,
        )
        CorpusVote.objects.create(
            corpus=self.corpus,
            creator=self.alice,
            vote_type=CorpusVoteType.UPVOTE,
        )
        # Same alice, different corpus — must not collide.
        CorpusVote.objects.create(
            corpus=other,
            creator=self.alice,
            vote_type=CorpusVoteType.UPVOTE,
        )


# --------------------------------------------------------------------------- #
# GraphQL mutation integration                                                #
# --------------------------------------------------------------------------- #


class CorpusVoteGraphQLTests(TransactionTestCase):
    """End-to-end check that the voteCorpus / removeCorpusVote mutations
    work for both authenticated and anonymous callers and surface the
    refreshed counts on the response.
    """

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="owner-gql", password="pw", email="o-gql@example.com"
        )
        self.alice = User.objects.create_user(
            username="alice-gql", password="pw", email="a-gql@example.com"
        )
        self.public_corpus = Corpus.objects.create(
            title="GQL Public",
            description="g",
            creator=self.owner,
            is_public=True,
        )
        # graphene-django's Client stubs are incomplete (``execute`` isn't
        # advertised in the type stubs), so erase the type for the test
        # surface where we drive the schema directly.
        self.client: Any = Client(schema)
        self.factory = RequestFactory()

    def _build_request(self, user, *, with_session: bool = True):
        request = self.factory.post("/graphql/")
        request.user = user
        if with_session:
            # Tests don't go through SessionMiddleware; emulate the
            # signed_cookies backend with a minimal in-memory session
            # so the voting mutation's session-key plumbing works.
            from django.contrib.sessions.backends.signed_cookies import (
                SessionStore,
            )

            request.session = SessionStore()
        return request

    def test_vote_corpus_authenticated_records_vote_and_returns_counts(self) -> None:
        query = """
            mutation($id: String!) {
                voteCorpus(corpusId: $id, voteType: "upvote") {
                    ok
                    message
                    obj { id upvoteCount downvoteCount score myVote }
                }
            }
        """
        request = self._build_request(self.alice)
        result = self.client.execute(
            query,
            variables={"id": _corpus_relay_id(self.public_corpus.pk)},
            context_value=request,
        )
        self.assertIsNone(result.get("errors"))
        payload = result["data"]["voteCorpus"]
        self.assertTrue(payload["ok"], msg=payload["message"])
        self.assertEqual(payload["obj"]["upvoteCount"], 1)
        self.assertEqual(payload["obj"]["score"], 1)
        self.assertEqual(payload["obj"]["myVote"], "UPVOTE")

    def test_vote_corpus_anonymous_records_session_keyed_vote(self) -> None:
        query = """
            mutation($id: String!) {
                voteCorpus(corpusId: $id, voteType: "downvote") {
                    ok
                    obj { id score myVote }
                }
            }
        """
        request = self._build_request(AnonymousUser())
        result = self.client.execute(
            query,
            variables={"id": _corpus_relay_id(self.public_corpus.pk)},
            context_value=request,
        )
        self.assertIsNone(result.get("errors"))
        payload = result["data"]["voteCorpus"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["obj"]["score"], -1)
        # my_vote should reflect the just-cast anonymous vote
        # (the resolver uses the same session key the mutation persisted).
        self.assertEqual(payload["obj"]["myVote"], "DOWNVOTE")
        # And the row should exist with a session_key, no creator.
        self.assertTrue(
            CorpusVote.objects.filter(
                corpus=self.public_corpus,
                creator__isnull=True,
                session_key__isnull=False,
            ).exists()
        )

    def test_remove_corpus_vote_clears_authenticated_vote(self) -> None:
        CorpusVoteService.cast_vote(self.alice, self.public_corpus.pk, "upvote")
        query = """
            mutation($id: String!) {
                removeCorpusVote(corpusId: $id) {
                    ok
                    message
                    obj { id score myVote }
                }
            }
        """
        request = self._build_request(self.alice)
        result = self.client.execute(
            query,
            variables={"id": _corpus_relay_id(self.public_corpus.pk)},
            context_value=request,
        )
        payload = result["data"]["removeCorpusVote"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["obj"]["score"], 0)
        self.assertIsNone(payload["obj"]["myVote"])

    def test_vote_corpus_self_vote_blocked(self) -> None:
        query = """
            mutation($id: String!) {
                voteCorpus(corpusId: $id, voteType: "upvote") {
                    ok
                    message
                }
            }
        """
        request = self._build_request(self.owner)
        result = self.client.execute(
            query,
            variables={"id": _corpus_relay_id(self.public_corpus.pk)},
            context_value=request,
        )
        payload = result["data"]["voteCorpus"]
        self.assertFalse(payload["ok"])
        self.assertIn("own", payload["message"].lower())

    def test_vote_corpus_invalid_corpus_id_returns_idor_safe_message(
        self,
    ) -> None:
        query = """
            mutation($id: String!) {
                voteCorpus(corpusId: $id, voteType: "upvote") {
                    ok
                    message
                }
            }
        """
        request = self._build_request(self.alice)
        # Plainly malformed global id — must produce the unified denial,
        # not a 500 or a different "Invalid id" path.
        result = self.client.execute(
            query,
            variables={"id": "not-a-real-id"},
            context_value=request,
        )
        payload = result["data"]["voteCorpus"]
        self.assertFalse(payload["ok"])
        self.assertIn("permission", payload["message"].lower())

    def test_my_vote_resolver_reflects_current_user(self) -> None:
        CorpusVoteService.cast_vote(self.alice, self.public_corpus.pk, "upvote")
        # Query as alice
        query = """
            query($id: ID!) {
                corpus(id: $id) {
                    id
                    upvoteCount
                    score
                    myVote
                }
            }
        """
        request = self._build_request(self.alice)
        result = self.client.execute(
            query,
            variables={"id": _corpus_relay_id(self.public_corpus.pk)},
            context_value=request,
        )
        self.assertIsNone(result.get("errors"), msg=json.dumps(result))
        self.assertEqual(result["data"]["corpus"]["myVote"], "UPVOTE")
        self.assertEqual(result["data"]["corpus"]["upvoteCount"], 1)

    def test_top_sort_excludes_personal_corpus_on_discovery_surface(self) -> None:
        """The ``orderBy: "top"`` discovery sort hides personal corpora.

        Personal corpora are single-user singletons that have no meaningful
        ranking against shared content, so the filter strips them anywhere
        the user is browsing the cross-user discovery surface (``mine`` is
        not True). This pins the behavior end-to-end through graphene.
        """
        # A personal corpus is auto-created for every user by a signal
        # handler — one per user is enforced by the
        # ``one_personal_corpus_per_user`` constraint, so reuse alice's.
        personal_corpus = Corpus.objects.get(creator=self.alice, is_personal=True)
        query = """
            query {
                corpuses(orderBy: "-top") { edges { node { id } } }
            }
        """
        request = self._build_request(self.alice)
        result = self.client.execute(query, context_value=request)
        self.assertIsNone(result.get("errors"), msg=json.dumps(result))
        returned_ids = {
            edge["node"]["id"] for edge in result["data"]["corpuses"]["edges"]
        }
        self.assertNotIn(_corpus_relay_id(personal_corpus.pk), returned_ids)

    def test_top_sort_on_mine_tab_keeps_personal_corpus(self) -> None:
        """The ``mine=True`` (My Corpuses) tab keeps personal corpora visible
        even under a Top sort, so users always see all of their own content.

        Regression test for the silent personal-corpus drop noted on PR #1789
        review (the original filter excluded ``is_personal=True`` on every
        Top-sorted query, including the user's own tab).
        """
        personal_corpus = Corpus.objects.get(creator=self.alice, is_personal=True)
        query = """
            query {
                corpuses(orderBy: "-top", mine: true) { edges { node { id } } }
            }
        """
        request = self._build_request(self.alice)
        result = self.client.execute(query, context_value=request)
        self.assertIsNone(result.get("errors"), msg=json.dumps(result))
        returned_ids = {
            edge["node"]["id"] for edge in result["data"]["corpuses"]["edges"]
        }
        self.assertIn(_corpus_relay_id(personal_corpus.pk), returned_ids)

    def test_my_vote_resolver_uses_service_fallback_when_not_annotated(
        self,
    ) -> None:
        """``resolve_my_vote`` falls back to ``CorpusVoteService.get_user_vote_type``
        when the corpus instance wasn't fetched through ``CorpusType.get_queryset``.

        The fast path (covered by ``test_corpuses_list_my_vote_is_not_n_plus_one``)
        reads the ``_viewer_vote`` annotation that ``get_queryset`` attaches.
        Any nested resolver path that hands a freshly-loaded ``Corpus`` to the
        resolver — e.g. one that constructs the instance via the ORM directly
        rather than through graphene's list pipeline — won't have the
        annotation, and must still produce the viewer's correct vote via
        the per-row service call.
        """
        from types import SimpleNamespace

        from config.graphql.corpus_types import CorpusType

        CorpusVoteService.cast_vote(self.alice, self.public_corpus.pk, "upvote")

        # Reload via the ORM directly so ``_viewer_vote`` is NOT set.
        unannotated = Corpus.objects.get(pk=self.public_corpus.pk)
        self.assertFalse(hasattr(unannotated, "_viewer_vote"))

        # Build a minimal info-shaped object — the resolver only reads
        # ``info.context.user`` and ``info.context.session``.
        info = SimpleNamespace(
            context=self._build_request(self.alice, with_session=False)
        )

        self.assertEqual(CorpusType.resolve_my_vote(unannotated, info), "UPVOTE")

        # And the no-vote branch: a viewer with no prior vote should
        # get ``None`` from the fallback (not a crash on the missing
        # annotation, and not the previous viewer's vote leaking through).
        bob = User.objects.create_user(
            username="bob-fallback", password="pw", email="b-fb@example.com"
        )
        info_bob = SimpleNamespace(context=self._build_request(bob, with_session=False))
        self.assertIsNone(CorpusType.resolve_my_vote(unannotated, info_bob))

    def test_corpuses_list_my_vote_is_not_n_plus_one(self) -> None:
        """The corpus list resolver must annotate ``my_vote`` with a single
        per-page ``Subquery`` rather than firing one query per card.

        Regression test for the N+1 noted on PR #1789. The annotation is
        attached in ``CorpusType.get_queryset``; without it,
        ``resolve_my_vote`` falls back to a per-row
        ``CorpusVoteService.get_user_vote_type`` call (one ``CorpusVote``
        query per corpus in the page).
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # Seed a population large enough that an N+1 would be obvious.
        extra_corpora = [
            Corpus.objects.create(
                title=f"GQL Public {i}",
                description="extra",
                creator=self.owner,
                is_public=True,
            )
            for i in range(10)
        ]
        # Vote on a subset so my_vote returns both null and non-null values.
        for corpus in extra_corpora[:3]:
            CorpusVoteService.cast_vote(self.alice, corpus.pk, "upvote")

        list_query = """
            query {
                corpuses(first: 25) {
                    edges { node { id myVote upvoteCount } }
                }
            }
        """
        request = self._build_request(self.alice)
        with CaptureQueriesContext(connection) as ctx:
            result = self.client.execute(list_query, context_value=request)

        self.assertIsNone(result.get("errors"), msg=json.dumps(result))
        edges = result["data"]["corpuses"]["edges"]
        # Sanity: at least the seeded set + the public corpus from setUp.
        self.assertGreaterEqual(len(edges), 11)

        # A standalone "look up the viewer's vote" query against
        # ``CorpusVote`` per card is exactly the N+1 the annotation fixes.
        # The annotated Subquery rides on the main corpus SELECT (so it
        # *embeds* a reference to ``corpuses_corpusvote``); the N+1 case
        # starts the SELECT directly from that table.
        vote_lookups = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].lstrip().startswith('SELECT "corpuses_corpusvote"')
        ]
        self.assertEqual(
            vote_lookups,
            [],
            msg=f"Expected no per-row CorpusVote lookups, got {len(vote_lookups)}: {vote_lookups}",
        )

        # And the annotation should actually return the vote values.
        my_votes = sorted((edge["node"]["myVote"] or "NONE") for edge in edges)
        self.assertIn("UPVOTE", my_votes)
        self.assertIn("NONE", my_votes)


class AnonymousVotingMiddlewareIntegrationTests(TransactionTestCase):
    """Drive the real ``/graphql/`` URL through Django's middleware stack.

    The unit-level GraphQL tests above bypass middleware (they hit
    ``schema.execute`` with a hand-rolled ``RequestFactory`` request), so
    they cannot catch interactions between the voting flow's session
    bootstrap and the production ``conditional_csrf_exempt`` gate.

    This class uses the Django test client (which runs the full
    ``SessionMiddleware`` → ``CsrfViewMiddleware`` → view chain) to pin
    the bug fixed in this PR: an anonymous vote forces a ``sessionid``
    cookie into existence, and the *next* anonymous POST used to 403
    with "CSRF verification failed" because the cookie was treated as
    session-authenticated when it wasn't.
    """

    def setUp(self) -> None:
        super().setUp()
        owner = User.objects.create_user(
            username="anon-vote-owner",
            password="pw",
            email="anon-vote-owner@example.com",
        )
        self.public_corpus = Corpus.objects.create(
            title="Anon-votable",
            description="public",
            creator=owner,
            is_public=True,
        )

    def _vote_payload(self, vote_type: str) -> str:
        return json.dumps(
            {
                "query": """
                    mutation($id: String!, $type: String!) {
                        voteCorpus(corpusId: $id, voteType: $type) {
                            ok
                            message
                            obj { id score myVote }
                        }
                    }
                """,
                "variables": {
                    "id": _corpus_relay_id(self.public_corpus.pk),
                    "type": vote_type,
                },
            }
        )

    def test_repeated_anonymous_votes_do_not_403_on_csrf(self) -> None:
        """Second anonymous POST after a vote must not trip CSRF.

        Step 1 succeeded before this fix too — the first vote arrived
        with no session cookie, so ``conditional_csrf_exempt`` short-
        circuited on the no-cookie branch and the vote was recorded
        (incidentally setting ``sessionid`` via ``_ensure_session_key``).

        Step 2 is the regression: the browser now carries the freshly
        minted ``sessionid``. Pre-fix, the cookie alone tipped the gate
        into the CSRF-enforced branch — no token cookie / header was
        ever set, so the request 403'd, ``errorLink`` clobbered the
        SPA's auth state, and the user saw the "Session expired" toast
        plus the cascade in the screenshots. Post-fix, the empty session
        carries no ``_auth_user_id`` so the gate stays in the bypass
        branch and the vote toggles cleanly.
        """
        from django.conf import settings as django_settings
        from django.test import Client as DjangoClient

        client = DjangoClient(enforce_csrf_checks=True)

        # Step 1 — first vote: no session cookie yet, bypass branch.
        r1 = client.post(
            "/graphql/",
            data=self._vote_payload("upvote"),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 200, msg=r1.content[:500])
        payload1 = r1.json()
        self.assertNotIn("errors", payload1, msg=json.dumps(payload1))
        self.assertTrue(
            payload1["data"]["voteCorpus"]["ok"],
            msg=payload1["data"]["voteCorpus"]["message"],
        )
        # The mutation should have materialised an anonymous session.
        session_cookie_name = getattr(
            django_settings, "SESSION_COOKIE_NAME", "sessionid"
        )
        self.assertIn(
            session_cookie_name,
            client.cookies,
            msg="Expected anonymous-vote bootstrap to set the session cookie",
        )

        # Step 2 — second vote with the sessionid cookie now in flight.
        # This is the request that 403'd pre-fix.
        r2 = client.post(
            "/graphql/",
            data=self._vote_payload("downvote"),
            content_type="application/json",
        )
        self.assertEqual(
            r2.status_code,
            200,
            msg=(
                "Anonymous re-vote after sessionid bootstrap must not "
                f"trip CSRF; got {r2.status_code} with body {r2.content[:500]!r}"
            ),
        )
        payload2 = r2.json()
        self.assertNotIn("errors", payload2, msg=json.dumps(payload2))
        self.assertTrue(payload2["data"]["voteCorpus"]["ok"])
        # And the vote actually switched.
        self.assertEqual(payload2["data"]["voteCorpus"]["obj"]["myVote"], "DOWNVOTE")
