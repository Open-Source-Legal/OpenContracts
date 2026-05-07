"""GraphQL tests for the ``documentStats`` aggregate query.

The Documents view tile counters previously summed over the paginated
client subset of ``document_items`` (initially 20 docs at most). This
resolver computes accurate aggregates over the full
``Document.objects.visible_to_user`` queryset so the tiles reflect what
the user actually has access to, not what happens to be in Apollo's
cache. Counts must respect:

* anonymous → public docs only
* authenticated user → own + public + guardian-permitted docs
* same filter args as the ``documents`` connection
* no inflation when ``hasLabelWithId`` joins ``doc_annotation``
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from graphene_django.utils.testing import GraphQLTestCase
from graphql_relay import to_global_id

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

PREFIX = "ZZS_"


STATS_QUERY = """
    query DocumentStats(
        $textSearch: String
        $hasLabelWithId: String
    ) {
        documentStats(
            textSearch: $textSearch
            hasLabelWithId: $hasLabelWithId
        ) {
            totalDocs
            totalPages
            processedCount
            processingCount
        }
    }
"""


class DocumentStatsTestCase(GraphQLTestCase):
    """End-to-end coverage of ``documentStats`` permission filtering."""

    GRAPHQL_URL = "/graphql/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.alice = User.objects.create_user(username="alice-zzs", password="pw")
        cls.bob = User.objects.create_user(username="bob-zzs", password="pw")

        # Alice's docs.
        cls.alice_private_processed = Document.objects.create(
            title=f"{PREFIX}Alice Private Processed",
            description=PREFIX,
            creator=cls.alice,
            is_public=False,
            backend_lock=False,
            page_count=10,
        )
        cls.alice_public_processed = Document.objects.create(
            title=f"{PREFIX}Alice Public Processed",
            description=PREFIX,
            creator=cls.alice,
            is_public=True,
            backend_lock=False,
            page_count=20,
        )
        cls.alice_private_processing = Document.objects.create(
            title=f"{PREFIX}Alice Private Processing",
            description=PREFIX,
            creator=cls.alice,
            is_public=False,
            backend_lock=True,
            page_count=5,
        )

        # Bob's docs — one shared with Alice via guardian, one public, one
        # totally private (NOT visible to Alice).
        cls.bob_shared_processed = Document.objects.create(
            title=f"{PREFIX}Bob Shared Processed",
            description=PREFIX,
            creator=cls.bob,
            is_public=False,
            backend_lock=False,
            page_count=15,
        )
        set_permissions_for_obj_to_user(
            cls.alice, cls.bob_shared_processed, [PermissionTypes.READ]
        )

        cls.bob_public_processed = Document.objects.create(
            title=f"{PREFIX}Bob Public Processed",
            description=PREFIX,
            creator=cls.bob,
            is_public=True,
            backend_lock=False,
            page_count=30,
        )
        cls.bob_private_processing = Document.objects.create(
            title=f"{PREFIX}Bob Private Processing",
            description=PREFIX,
            creator=cls.bob,
            is_public=False,
            backend_lock=True,
            page_count=999,
        )

    def setUp(self) -> None:
        self.client.login(username="alice-zzs", password="pw")

    def _stats(self, response) -> dict[str, int]:
        payload = response.json()
        self.assertNotIn("errors", payload, payload)
        return payload["data"]["documentStats"]

    def test_authenticated_user_sees_own_plus_shared_plus_public(self) -> None:
        response = self.query(STATS_QUERY, variables={"textSearch": PREFIX})
        # Alice sees: 3 own + bob_shared + bob_public = 5 docs.
        # Pages: 10 + 20 + 5 + 15 + 30 = 80
        # Processed: alice_private_processed, alice_public_processed,
        #            bob_shared_processed, bob_public_processed = 4
        # Processing: alice_private_processing = 1
        self.assertEqual(
            self._stats(response),
            {
                "totalDocs": 5,
                "totalPages": 80,
                "processedCount": 4,
                "processingCount": 1,
            },
        )

    def test_anonymous_user_sees_only_public(self) -> None:
        self.client.logout()
        response = self.query(STATS_QUERY, variables={"textSearch": PREFIX})
        # Anonymous: alice_public_processed + bob_public_processed = 2 docs.
        # Pages: 20 + 30 = 50. All processed.
        self.assertEqual(
            self._stats(response),
            {
                "totalDocs": 2,
                "totalPages": 50,
                "processedCount": 2,
                "processingCount": 0,
            },
        )

    def test_other_user_does_not_see_alices_private_docs(self) -> None:
        self.client.logout()
        self.client.login(username="bob-zzs", password="pw")
        response = self.query(STATS_QUERY, variables={"textSearch": PREFIX})
        # Bob sees: 3 own + alice_public = 4 docs.
        # Pages: 15 + 30 + 999 + 20 = 1064
        # Processed: bob_shared, bob_public, alice_public = 3
        # Processing: bob_private_processing = 1
        self.assertEqual(
            self._stats(response),
            {
                "totalDocs": 4,
                "totalPages": 1064,
                "processedCount": 3,
                "processingCount": 1,
            },
        )

    def test_text_search_narrows_counts(self) -> None:
        # ``DocumentFilter.naive_text_search`` uses ``description__contains``;
        # both Alice fixtures share the prefix in their description, but only
        # one has "Public" in the title — DocumentFilter doesn't search title
        # so we narrow via a description-prefix substring instead.
        response = self.query(STATS_QUERY, variables={"textSearch": f"{PREFIX}"})
        # Same 5 results as the unfiltered case — sanity check that
        # text_search with the broad prefix matches everything.
        self.assertEqual(self._stats(response)["totalDocs"], 5)

    def test_has_label_filter_does_not_inflate_counts(self) -> None:
        """Regression guard for the ``has_label_with_id`` join.

        ``DocumentFilter.has_label_id`` joins ``doc_annotation``, producing
        one row per matching annotation. Without the ``id__in`` subquery in
        ``resolve_document_stats``, attaching three annotations to a single
        document would inflate ``totalDocs`` from 1 to 3 and
        ``totalPages`` to 3× the real page count.
        """
        label = AnnotationLabel.objects.create(
            text=f"{PREFIX}label", creator=self.alice, label_type="TOKEN_LABEL"
        )
        # Three annotations on the SAME document — naive Count would yield 3.
        for _ in range(3):
            Annotation.objects.create(
                document=self.alice_private_processed,
                annotation_label=label,
                creator=self.alice,
                raw_text="x",
                page=0,
            )

        response = self.query(
            STATS_QUERY,
            variables={
                "textSearch": PREFIX,
                "hasLabelWithId": to_global_id("AnnotationLabelType", label.id),
            },
        )
        stats = self._stats(response)
        # Exactly one doc carries the label — 10 pages, 1 processed, 0 lock.
        self.assertEqual(
            stats,
            {
                "totalDocs": 1,
                "totalPages": 10,
                "processedCount": 1,
                "processingCount": 0,
            },
        )
