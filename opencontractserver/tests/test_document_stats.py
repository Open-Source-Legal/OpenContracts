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
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

PREFIX = "ZZS_"


STATS_QUERY = """
    query DocumentStats(
        $textSearch: String
        $hasLabelWithId: String
        $inCorpusWithId: String
        $includeCaml: Boolean
    ) {
        documentStats(
            textSearch: $textSearch
            hasLabelWithId: $hasLabelWithId
            inCorpusWithId: $inCorpusWithId
            includeCaml: $includeCaml
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
        # ``DocumentFilter.naive_text_search`` matches on ``description``.
        # Re-tag a single Alice doc with a unique substring so the search
        # matches exactly that one document — otherwise this test would be
        # a duplicate of ``test_authenticated_user_sees_own_plus_shared_plus_public``
        # (the prefix matches every fixture).
        narrow_token = f"{PREFIX}NEEDLE"
        self.alice_public_processed.description = narrow_token
        self.alice_public_processed.save(update_fields=["description"])

        response = self.query(STATS_QUERY, variables={"textSearch": narrow_token})
        # Only the re-tagged doc matches — 20 pages, processed.
        self.assertEqual(
            self._stats(response),
            {
                "totalDocs": 1,
                "totalPages": 20,
                "processedCount": 1,
                "processingCount": 0,
            },
        )

    def test_in_corpus_filter_narrows_counts(self) -> None:
        """``inCorpusWithId`` (frontend forces ``includeCaml=True``) narrows
        the aggregate to documents in the selected corpus.

        Mirrors the corpus-filter path the Documents view exercises when the
        user picks a corpus — the resolver must honour the same
        ``DocumentFilter`` plumbing the list query uses, including the
        ``include_caml`` flag's effect on which related documents appear.
        """
        # A corpus owned by Alice that holds two of her docs (private +
        # public). The third Alice doc and all Bob docs are NOT in it.
        # ``DocumentFilter.in_corpus`` looks up membership via
        # ``DocumentPath`` (corpus_id + is_current + not is_deleted), so
        # the test directly seeds those rows rather than going through the
        # heavier ``CorpusObjsService.add_document_to_corpus`` flow,
        # which clones the document into a corpus-isolated copy.
        corpus = Corpus.objects.create(
            title=f"{PREFIX}corpus",
            description=PREFIX,
            creator=self.alice,
            is_public=False,
        )
        for doc in (self.alice_private_processed, self.alice_public_processed):
            DocumentPath.objects.create(
                document=doc,
                corpus=corpus,
                creator=self.alice,
                path=f"/{doc.title}",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )

        response = self.query(
            STATS_QUERY,
            variables={
                "textSearch": PREFIX,
                "inCorpusWithId": to_global_id("CorpusType", corpus.id),
                # Frontend hard-codes ``includeCaml=True`` whenever a corpus
                # is selected; mirror that here so the resolver path under
                # test matches what the UI actually sends.
                "includeCaml": True,
            },
        )
        self.assertEqual(
            self._stats(response),
            {
                "totalDocs": 2,
                "totalPages": 30,
                "processedCount": 2,
                "processingCount": 0,
            },
        )

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
