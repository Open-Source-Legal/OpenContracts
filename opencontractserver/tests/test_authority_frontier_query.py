"""Tests for the global, superuser-only ``authorityFrontier`` GraphQL connection
and ``authorityFrontierStats`` summary, plus the
``AuthorityFrontierService.admin_state_counts`` aggregation that backs the
authority-sources monitor's chips.

``AuthorityFrontier`` is a system-managed global queue with no per-object
permissions, so the surface is gated to superusers (everyone else sees nothing).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment.services import AuthorityFrontierService

User = get_user_model()


class _Ctx:
    """Minimal GraphQL context (mirrors test_governance_graph._Ctx)."""

    def __init__(self, user):
        self.user = user
        self.META = {}


FRONTIER_QUERY = """
    query ($state: String, $jur: String, $prov: String) {
      authorityFrontier(
        discoveryState: $state
        jurisdiction: $jur
        provider: $prov
        first: 50
      ) {
        edges {
          node {
            canonicalKey
            authority
            jurisdiction
            authorityType
            discoveryState
            provider
            mentionCount
            distinctCorpusCount
          }
        }
      }
    }
"""

STATS_QUERY = """
    query ($jur: String) {
      authorityFrontierStats(jurisdiction: $jur) {
        totalCount
        byState { state count }
      }
    }
"""


def _run(query, user, **variables):
    from config.graphql.schema import schema
    from config.graphql.testing import Client

    return Client(schema, context_value=_Ctx(user)).execute(query, variables=variables)


class AuthorityFrontierQueryTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )
        self.regular = User.objects.create_user(username="joe", password="p")
        # Deterministic frontier: 2 federal (ingested + failed), 2 Delaware (queued).
        AuthorityFrontier.objects.create(
            canonical_key="usc-15:78j",
            authority="usc-15",
            jurisdiction="us-federal",
            authority_type="statute",
            discovery_state="ingested",
            provider="USCodeAuthoritySourceProvider",
            mention_count=142,
            distinct_corpus_count=9,
        )
        AuthorityFrontier.objects.create(
            canonical_key="cfr-17:240.10b",
            authority="cfr-17",
            jurisdiction="us-federal",
            authority_type="regulation",
            discovery_state="failed",
            provider="CFRAuthoritySourceProvider",
            mention_count=88,
            distinct_corpus_count=6,
        )
        AuthorityFrontier.objects.create(
            canonical_key="dgcl:145",
            authority="dgcl",
            jurisdiction="us-de",
            authority_type="statute",
            discovery_state="queued",
            mention_count=54,
            distinct_corpus_count=4,
        )
        AuthorityFrontier.objects.create(
            canonical_key="dgcl:203",
            authority="dgcl",
            jurisdiction="us-de",
            authority_type="statute",
            discovery_state="queued",
            mention_count=30,
            distinct_corpus_count=3,
        )

    # ---- connection: gating + order + filters --------------------------------
    def test_superuser_sees_all_rows_backlog_first(self):
        res = _run(FRONTIER_QUERY, self.superuser)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        edges = res["data"]["authorityFrontier"]["edges"]
        self.assertEqual(len(edges), 4)
        # Default order is -mention_count (backlog-first).
        self.assertEqual(
            [e["node"]["canonicalKey"] for e in edges],
            ["usc-15:78j", "cfr-17:240.10b", "dgcl:145", "dgcl:203"],
        )

    def test_non_superuser_sees_nothing(self):
        res = _run(FRONTIER_QUERY, self.regular)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        self.assertEqual(res["data"]["authorityFrontier"]["edges"], [])

    def test_filter_by_state_and_jurisdiction(self):
        res = _run(FRONTIER_QUERY, self.superuser, state="queued", jur="us-de")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        keys = {
            e["node"]["canonicalKey"] for e in res["data"]["authorityFrontier"]["edges"]
        }
        self.assertEqual(keys, {"dgcl:145", "dgcl:203"})

    def test_filter_by_provider(self):
        res = _run(FRONTIER_QUERY, self.superuser, prov="CFRAuthoritySourceProvider")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        keys = [
            e["node"]["canonicalKey"] for e in res["data"]["authorityFrontier"]["edges"]
        ]
        self.assertEqual(keys, ["cfr-17:240.10b"])

    # ---- stats: GraphQL --------------------------------------------------------
    def test_stats_superuser_full_breakdown(self):
        res = _run(STATS_QUERY, self.superuser)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        stats = res["data"]["authorityFrontierStats"]
        self.assertEqual(stats["totalCount"], 4)
        self.assertEqual(
            {r["state"]: r["count"] for r in stats["byState"]},
            {"ingested": 1, "failed": 1, "queued": 2},
        )

    def test_stats_facet_aware(self):
        res = _run(STATS_QUERY, self.superuser, jur="us-de")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        stats = res["data"]["authorityFrontierStats"]
        self.assertEqual(stats["totalCount"], 2)
        self.assertEqual(
            {r["state"]: r["count"] for r in stats["byState"]}, {"queued": 2}
        )

    def test_stats_non_superuser_empty(self):
        res = _run(STATS_QUERY, self.regular)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        stats = res["data"]["authorityFrontierStats"]
        self.assertEqual(stats["totalCount"], 0)
        self.assertEqual(stats["byState"], [])

    # ---- stats: service logic (what the resolver delegates to) -----------------
    def test_service_admin_state_counts(self):
        counts = AuthorityFrontierService.admin_state_counts(self.superuser)
        self.assertEqual(counts["total_count"], 4)
        self.assertEqual(
            {r["state"]: r["count"] for r in counts["by_state"]},
            {"ingested": 1, "failed": 1, "queued": 2},
        )
        # Non-superuser is empty.
        self.assertEqual(
            AuthorityFrontierService.admin_state_counts(self.regular),
            {"total_count": 0, "by_state": []},
        )
        # Facet: provider.
        cfr = AuthorityFrontierService.admin_state_counts(
            self.superuser, provider="CFRAuthoritySourceProvider"
        )
        self.assertEqual(cfr["total_count"], 1)
        self.assertEqual(
            {r["state"]: r["count"] for r in cfr["by_state"]}, {"failed": 1}
        )

    def test_service_admin_state_counts_remaining_facets(self):
        # The non-state facet branches the GraphQL surface doesn't expose:
        # authority_type, authority, and free-text search.

        # Facet: authority_type — 3 statutes (usc-15 ingested + 2 dgcl queued).
        by_type = AuthorityFrontierService.admin_state_counts(
            self.superuser, authority_type="statute"
        )
        self.assertEqual(by_type["total_count"], 3)
        self.assertEqual(
            {r["state"]: r["count"] for r in by_type["by_state"]},
            {"ingested": 1, "queued": 2},
        )

        # Facet: authority — the two Delaware (dgcl) queued rows.
        by_authority = AuthorityFrontierService.admin_state_counts(
            self.superuser, authority="dgcl"
        )
        self.assertEqual(by_authority["total_count"], 2)
        self.assertEqual(
            {r["state"]: r["count"] for r in by_authority["by_state"]}, {"queued": 2}
        )

        # Facet: free-text search over canonical_key / authority (icontains).
        by_search = AuthorityFrontierService.admin_state_counts(
            self.superuser, search="dgcl"
        )
        self.assertEqual(by_search["total_count"], 2)
        self.assertEqual(
            {r["state"]: r["count"] for r in by_search["by_state"]}, {"queued": 2}
        )
