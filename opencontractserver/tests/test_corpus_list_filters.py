"""GraphQL tests for corpus list view filters and tab counts.

Covers the ``mine``, ``isPublic``, ``sharedWithMe`` filter args on the
``corpuses`` connection and the ``corpusFilterCounts`` query that drives
the tab badges in the Corpuses list view.

Each test scopes results with ``textSearch="ZZF_"`` (a unique fixture
prefix) so the personal "My Documents" corpus auto-created on user signup
doesn't pollute the assertions.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from graphene_django.utils.testing import GraphQLTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

# Unique prefix used for every fixture title so tests can ignore the
# per-user personal corpus auto-created on signup.
PREFIX = "ZZF_"


CORPUSES_QUERY = """
    query Corpuses(
        $mine: Boolean
        $isPublic: Boolean
        $sharedWithMe: Boolean
        $textSearch: String
    ) {
        corpuses(
            mine: $mine
            isPublic: $isPublic
            sharedWithMe: $sharedWithMe
            textSearch: $textSearch
        ) {
            edges {
                node {
                    id
                    title
                    isPublic
                }
            }
        }
    }
"""

COUNTS_QUERY = """
    query Counts($textSearch: String) {
        corpusFilterCounts(textSearch: $textSearch) {
            all
            mine
            shared
            public
        }
    }
"""


class CorpusListFiltersAndCountsTestCase(GraphQLTestCase):
    """End-to-end check that tab filters and counts agree on the same set."""

    GRAPHQL_URL = "/graphql/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.alice = User.objects.create_user(username="alice-zzf", password="pw")
        cls.bob = User.objects.create_user(username="bob-zzf", password="pw")

        cls.alice_private = Corpus.objects.create(
            title=f"{PREFIX}Alice Private", creator=cls.alice, is_public=False
        )
        cls.alice_public = Corpus.objects.create(
            title=f"{PREFIX}Alice Public", creator=cls.alice, is_public=True
        )

        # Bob's corpus shared explicitly with Alice (READ permission).
        cls.bob_shared = Corpus.objects.create(
            title=f"{PREFIX}Bob Shared", creator=cls.bob, is_public=False
        )
        set_permissions_for_obj_to_user(
            cls.alice, cls.bob_shared, [PermissionTypes.READ]
        )

        cls.bob_public = Corpus.objects.create(
            title=f"{PREFIX}Bob Public", creator=cls.bob, is_public=True
        )

        # Bob's totally private corpus (NOT visible to Alice).
        cls.bob_private = Corpus.objects.create(
            title=f"{PREFIX}Bob Private", creator=cls.bob, is_public=False
        )

    def setUp(self) -> None:
        self.client.login(username="alice-zzf", password="pw")

    def _titles(self, response) -> set[str]:
        payload = response.json()
        self.assertNotIn("errors", payload, payload)
        return {edge["node"]["title"] for edge in payload["data"]["corpuses"]["edges"]}

    def test_all_tab_returns_visible_corpuses(self) -> None:
        response = self.query(CORPUSES_QUERY, variables={"textSearch": PREFIX})
        self.assertResponseNoErrors(response)
        # Alice sees: her two corpuses, Bob's shared, Bob's public.
        # She does NOT see Bob's private corpus.
        self.assertEqual(
            self._titles(response),
            {
                f"{PREFIX}Alice Private",
                f"{PREFIX}Alice Public",
                f"{PREFIX}Bob Shared",
                f"{PREFIX}Bob Public",
            },
        )

    def test_mine_filter_returns_only_creator_owned(self) -> None:
        response = self.query(
            CORPUSES_QUERY, variables={"mine": True, "textSearch": PREFIX}
        )
        self.assertEqual(
            self._titles(response),
            {f"{PREFIX}Alice Private", f"{PREFIX}Alice Public"},
        )

    def test_public_filter_returns_only_public_visible(self) -> None:
        response = self.query(
            CORPUSES_QUERY, variables={"isPublic": True, "textSearch": PREFIX}
        )
        self.assertEqual(
            self._titles(response),
            {f"{PREFIX}Alice Public", f"{PREFIX}Bob Public"},
        )

    def test_shared_filter_excludes_own_and_public(self) -> None:
        response = self.query(
            CORPUSES_QUERY,
            variables={"sharedWithMe": True, "textSearch": PREFIX},
        )
        # "Shared" = visible to me, not mine, not public.
        self.assertEqual(self._titles(response), {f"{PREFIX}Bob Shared"})

    def test_text_search_combines_with_filters(self) -> None:
        response = self.query(
            CORPUSES_QUERY,
            variables={"mine": True, "textSearch": f"{PREFIX}Alice Public"},
        )
        self.assertEqual(self._titles(response), {f"{PREFIX}Alice Public"})

    def test_counts_match_filtered_lists(self) -> None:
        response = self.query(COUNTS_QUERY, variables={"textSearch": PREFIX})
        self.assertResponseNoErrors(response)
        counts = response.json()["data"]["corpusFilterCounts"]
        self.assertEqual(counts, {"all": 4, "mine": 2, "shared": 1, "public": 2})

    def test_counts_respect_text_search(self) -> None:
        # Backend text_search uses substring contains on title/description.
        # Use the literal title prefix shared by both Alice fixtures so the
        # match set is deterministic.
        response = self.query(COUNTS_QUERY, variables={"textSearch": f"{PREFIX}Alice"})
        counts = response.json()["data"]["corpusFilterCounts"]
        # Matches Alice Private + Alice Public — both mine, one public.
        self.assertEqual(counts, {"all": 2, "mine": 2, "shared": 0, "public": 1})

    def test_anonymous_user_cannot_see_private_corpuses(self) -> None:
        self.client.logout()
        response = self.query(CORPUSES_QUERY, variables={"textSearch": PREFIX})
        self.assertEqual(
            self._titles(response),
            {f"{PREFIX}Alice Public", f"{PREFIX}Bob Public"},
        )

    def test_anonymous_user_mine_returns_empty(self) -> None:
        self.client.logout()
        response = self.query(
            CORPUSES_QUERY, variables={"mine": True, "textSearch": PREFIX}
        )
        self.assertEqual(self._titles(response), set())

    def test_anonymous_user_shared_returns_empty(self) -> None:
        self.client.logout()
        response = self.query(
            CORPUSES_QUERY,
            variables={"sharedWithMe": True, "textSearch": PREFIX},
        )
        self.assertEqual(self._titles(response), set())

    def test_anonymous_counts_zero_mine_and_shared(self) -> None:
        self.client.logout()
        response = self.query(COUNTS_QUERY, variables={"textSearch": PREFIX})
        counts = response.json()["data"]["corpusFilterCounts"]
        # Anonymous: 2 visible (both public), 0 mine, 0 shared.
        self.assertEqual(counts, {"all": 2, "mine": 0, "shared": 0, "public": 2})
