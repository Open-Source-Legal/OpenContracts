"""Tests for subset authority discovery (the /admin/authorities "run selected").

Covers:
- ``CrawlAuthoritiesService.discover_selected`` — loops
  ``discover_and_bootstrap`` over exactly the given rows (depth 0, no
  seed-from-wanted / no child seeding), returns the outcome census, and tallies
  ids that don't exist.
- ``RunAuthorityDiscoveryMutation`` — superuser-only, decodes global IDs,
  enqueues the fire-and-forget task with the resolved pks, and rejects
  non-superusers / id-less calls.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.testing import Client
from opencontractserver.annotations.models import AuthorityFrontier

User = get_user_model()

_SVC = "opencontractserver.enrichment.services.crawl_authorities_service"


class _GQLContext:
    def __init__(self, user):
        self.user = user


def _frontier(canonical_key, **over):
    defaults = dict(
        authority=canonical_key.split(":", 1)[0],
        jurisdiction="us-federal",
        authority_type="statute",
        mention_count=1,
        distinct_corpus_count=1,
    )
    defaults.update(over)
    return AuthorityFrontier.objects.create(canonical_key=canonical_key, **defaults)


class DiscoverSelectedServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ds-svc", password="p")
        self.r1 = _frontier("usc-15:78j", mention_count=10)
        self.r2 = _frontier("cfr-17:240.10b-5", mention_count=5)

    def test_loops_discover_and_bootstrap_and_tallies_outcomes(self):
        from opencontractserver.enrichment.services.crawl_authorities_service import (
            CrawlAuthoritiesService,
        )

        statuses = {
            "usc-15:78j": "ingested",
            "cfr-17:240.10b-5": "unsupported",
        }

        def fake_dab(*, creator_id, frontier_row, make_public, relink_async):
            # Subset discovery relinks asynchronously, like the crawl path.
            assert relink_async is True
            assert creator_id == self.user.id
            return {"status": statuses[frontier_row.canonical_key]}

        with mock.patch(
            f"{_SVC}.AuthorityDiscoveryService.discover_and_bootstrap",
            side_effect=fake_dab,
        ) as dab, mock.patch(
            f"{_SVC}.AuthorityFrontierService.seed_from_wanted_authorities"
        ) as seed, mock.patch(
            f"{_SVC}.AuthorityFrontierService.seed_child_keys"
        ) as seed_children:
            summary = CrawlAuthoritiesService.discover_selected(
                creator_id=self.user.id,
                frontier_ids=[self.r1.id, self.r2.id, 9_999_999],
            )

        # One discover_and_bootstrap per EXISTING row; the bogus id is skipped.
        assert dab.call_count == 2
        # Depth 0: subset discovery never seeds from wanted authorities nor seeds
        # the ingested authority's own children.
        seed.assert_not_called()
        seed_children.assert_not_called()

        assert summary["requested"] == 3
        assert summary["processed"] == 2
        assert summary["not_found"] == 1
        assert summary["outcomes"] == {"ingested": 1, "unsupported": 1}
        assert summary["ingested"] == 1

    def test_dedupes_requested_ids(self):
        from opencontractserver.enrichment.services.crawl_authorities_service import (
            CrawlAuthoritiesService,
        )

        with mock.patch(
            f"{_SVC}.AuthorityDiscoveryService.discover_and_bootstrap",
            return_value={"status": "ingested"},
        ) as dab:
            summary = CrawlAuthoritiesService.discover_selected(
                creator_id=self.user.id,
                frontier_ids=[self.r1.id, self.r1.id, self.r1.id],
            )

        assert dab.call_count == 1
        assert summary["requested"] == 1
        assert summary["processed"] == 1


class RunAuthorityDiscoveryMutationTests(TestCase):
    MUT = """
    mutation Run($ids: [ID!]!) {
      runAuthorityDiscovery(frontierIds: $ids) { ok message count }
    }
    """

    def setUp(self):
        self.su = User.objects.create_user(
            username="ds-su", password="p", is_superuser=True
        )
        self.user = User.objects.create_user(username="ds-usr", password="p")
        self.r1 = _frontier("usc-15:78j", mention_count=3)
        self.r2 = _frontier("cfr-17:240.10b-5", mention_count=2)
        # Lazy import (schema build under coverage instrumentation).
        from config.graphql.schema import schema

        self.client = Client(schema)

    def _execute(self, ids, user):
        return self.client.execute(  # type: ignore[attr-defined]
            self.MUT,
            variable_values={"ids": ids},
            context_value=_GQLContext(user),
        )

    def _gid(self, row):
        return to_global_id("AuthorityFrontierNode", row.id)

    def test_superuser_enqueues_task_with_resolved_pks(self):
        from opencontractserver.tasks import corpus_tasks

        with mock.patch.object(
            corpus_tasks.discover_selected_authorities, "delay"
        ) as delay:
            res = self._execute([self._gid(self.r1), self._gid(self.r2)], self.su)

        assert res.get("errors") is None, res
        data = res["data"]["runAuthorityDiscovery"]
        assert data["ok"] is True, data
        assert data["count"] == 2
        delay.assert_called_once()
        kwargs = delay.call_args.kwargs
        assert kwargs["frontier_ids"] == [self.r1.id, self.r2.id]
        assert kwargs["creator_id"] == self.su.id

    def test_non_superuser_denied(self):
        from opencontractserver.tasks import corpus_tasks

        with mock.patch.object(
            corpus_tasks.discover_selected_authorities, "delay"
        ) as delay:
            res = self._execute([self._gid(self.r1)], self.user)

        assert res.get("errors") is None, res
        data = res["data"]["runAuthorityDiscovery"]
        assert data["ok"] is False
        delay.assert_not_called()

    def test_no_valid_ids_rejected(self):
        from opencontractserver.tasks import corpus_tasks

        with mock.patch.object(
            corpus_tasks.discover_selected_authorities, "delay"
        ) as delay:
            res = self._execute(["not-a-relay-id"], self.su)

        assert res.get("errors") is None, res
        data = res["data"]["runAuthorityDiscovery"]
        assert data["ok"] is False
        delay.assert_not_called()

    def test_mixes_valid_and_invalid_ids(self):
        from opencontractserver.tasks import corpus_tasks

        with mock.patch.object(
            corpus_tasks.discover_selected_authorities, "delay"
        ) as delay:
            res = self._execute(
                [self._gid(self.r1), "garbage", self._gid(self.r2)], self.su
            )

        assert res.get("errors") is None, res
        data = res["data"]["runAuthorityDiscovery"]
        assert data["ok"] is True, data
        assert data["count"] == 2
        delay.assert_called_once()
        assert delay.call_args.kwargs["frontier_ids"] == [self.r1.id, self.r2.id]


class AuthorityFrontierIngestableResolverTests(TestCase):
    """Exercise the ``authorityFrontier`` query resolver path for the new
    ``ingestable`` / ``predictedProvider`` fields — the resolver runs against the
    ``AuthorityFrontier`` MODEL instance graphene passes as root, so a regression
    here catches helper-on-the-wrong-object bugs the mutation/service tests miss.
    """

    QUERY = """
    query {
      authorityFrontier(first: 10) {
        edges { node { canonicalKey ingestable predictedProvider } }
      }
    }
    """

    def setUp(self):
        self.su = User.objects.create_user(
            username="af-su", password="p", is_superuser=True
        )
        _frontier("usc-15:78j", mention_count=9)
        _frontier("dgcl:145", jurisdiction="us-de", mention_count=2)
        from config.graphql.schema import schema

        self.client = Client(schema)

    def test_ingestable_and_predicted_provider_resolve(self):
        def fake_provider_for(canonical_key):
            if canonical_key == "usc-15:78j":
                return ("USCodeAuthoritySourceProvider", object(), canonical_key)
            return (None, None, None)

        with mock.patch(
            "opencontractserver.enrichment.services.authority_discovery_service"
            ".AuthorityDiscoveryService._provider_for",
            side_effect=fake_provider_for,
        ):
            res = self.client.execute(  # type: ignore[attr-defined]
                self.QUERY, context_value=_GQLContext(self.su)
            )

        assert res.get("errors") is None, res
        nodes = {
            e["node"]["canonicalKey"]: e["node"]
            for e in res["data"]["authorityFrontier"]["edges"]
        }
        assert nodes["usc-15:78j"]["ingestable"] is True
        assert (
            nodes["usc-15:78j"]["predictedProvider"] == "USCodeAuthoritySourceProvider"
        )
        assert nodes["dgcl:145"]["ingestable"] is False
        assert nodes["dgcl:145"]["predictedProvider"] is None
