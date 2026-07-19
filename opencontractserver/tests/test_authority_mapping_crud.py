"""Tests for the runtime authority-mappings CRUD surface (Phase 2).

Covers ``AuthorityKeyEquivalenceService`` (superuser gate, key-grammar
validation, manual-only edit/delete, ``created_by`` capture, per-source stats)
and the superuser-only GraphQL connection / mutations that wrap it. The mappings
are global system data with no per-object permissions, so non-superusers see
nothing and cannot write.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.enrichment.services import AuthorityKeyEquivalenceService

User = get_user_model()


class _Ctx:
    """Minimal GraphQL context (mirrors test_authority_frontier_query._Ctx)."""

    def __init__(self, user):
        self.user = user
        self.META = {}


def _run(query, user, **variables):
    from config.graphql.schema import schema
    from config.graphql.testing import Client

    return Client(schema, context_value=_Ctx(user)).execute(query, variables=variables)


class AuthorityKeyEquivalenceServiceTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )
        self.regular = User.objects.create_user(username="joe", password="p")

    # ---- create --------------------------------------------------------------
    def test_create_manual_captures_provenance(self):
        res = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:501", to_key="usc-26:501", note="IRC=Title26"
        )
        assert res.ok, res.error
        assert res.obj is not None  # narrow type for mypy
        assert res.obj.source == "manual"
        assert res.obj.confidence == 1.0
        assert res.obj.note == "IRC=Title26"
        assert res.obj.created_by_id == self.superuser.id

    def test_create_rejects_non_superuser(self):
        res = AuthorityKeyEquivalenceService.create(
            self.regular, from_key="irc:501", to_key="usc-26:501"
        )
        assert not res.ok
        assert not AuthorityKeyEquivalence.objects.filter(from_key="irc:501").exists()

    def test_create_rejects_malformed_key(self):
        res = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="garbage", to_key="usc-26:501"
        )
        assert not res.ok
        assert "from_key" in res.error

    def test_create_rejects_identical_keys(self):
        res = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:1", to_key="irc:1"
        )
        assert not res.ok
        assert "differ" in res.error

    def test_db_constraint_rejects_self_referential_row(self):
        """The service rejects from_key == to_key, but the DB CheckConstraint is
        the backstop for a direct ORM insert / admin action / data import that
        bypasses the service entirely."""
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuthorityKeyEquivalence.objects.create(
                    from_key="irc:1", to_key="irc:1", source="manual"
                )
        assert not AuthorityKeyEquivalence.objects.filter(from_key="irc:1").exists()

    def test_create_rejects_duplicate_pair(self):
        AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:501", to_key="usc-26:501"
        )
        res = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:501", to_key="usc-26:501"
        )
        assert not res.ok
        assert "already exists" in res.error

    # ---- update --------------------------------------------------------------
    def test_update_manual_row(self):
        created = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:501", to_key="usc-26:501"
        ).obj
        assert created is not None  # narrow type for mypy
        res = AuthorityKeyEquivalenceService.update(
            self.superuser, pk=created.pk, to_key="usc-26:502", note="fixed"
        )
        assert res.ok, res.error
        created.refresh_from_db()
        assert created.to_key == "usc-26:502"
        assert created.note == "fixed"

    def test_update_rejects_managed_row(self):
        managed = AuthorityKeyEquivalence.objects.create(
            from_key="exchange-act:99", to_key="usc-15:99", source="baseline"
        )
        res = AuthorityKeyEquivalenceService.update(
            self.superuser, pk=managed.pk, to_key="usc-15:100"
        )
        assert not res.ok
        assert "manual" in res.error
        managed.refresh_from_db()
        assert managed.to_key == "usc-15:99"

    def test_update_rejects_malformed_key(self):
        created = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:501", to_key="usc-26:501"
        ).obj
        assert created is not None  # narrow type for mypy
        res = AuthorityKeyEquivalenceService.update(
            self.superuser, pk=created.pk, from_key="oops"
        )
        assert not res.ok

    def test_update_rejects_collision_with_existing_pair(self):
        a = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:1", to_key="usc-26:1"
        ).obj
        assert a is not None  # narrow type for mypy
        AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:2", to_key="usc-26:2"
        )
        res = AuthorityKeyEquivalenceService.update(
            self.superuser, pk=a.pk, from_key="irc:2", to_key="usc-26:2"
        )
        assert not res.ok
        assert "already exists" in res.error

    # ---- delete --------------------------------------------------------------
    def test_delete_manual_row(self):
        created = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:501", to_key="usc-26:501"
        ).obj
        assert created is not None  # narrow type for mypy
        res = AuthorityKeyEquivalenceService.delete(self.superuser, pk=created.pk)
        assert res.ok
        assert not AuthorityKeyEquivalence.objects.filter(pk=created.pk).exists()

    def test_delete_rejects_managed_row(self):
        managed = AuthorityKeyEquivalence.objects.create(
            from_key="exchange-act:99", to_key="usc-15:99", source="baseline"
        )
        res = AuthorityKeyEquivalenceService.delete(self.superuser, pk=managed.pk)
        assert not res.ok
        assert AuthorityKeyEquivalence.objects.filter(pk=managed.pk).exists()

    def test_delete_rejects_non_superuser(self):
        created = AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:501", to_key="usc-26:501"
        ).obj
        assert created is not None  # narrow type for mypy
        res = AuthorityKeyEquivalenceService.delete(self.regular, pk=created.pk)
        assert not res.ok
        assert AuthorityKeyEquivalence.objects.filter(pk=created.pk).exists()

    # ---- stats / visibility --------------------------------------------------
    def test_stats_by_source(self):
        AuthorityKeyEquivalence.objects.create(
            from_key="exchange-act:99", to_key="usc-15:99", source="baseline"
        )
        AuthorityKeyEquivalenceService.create(
            self.superuser, from_key="irc:501", to_key="usc-26:501"
        )
        stats = AuthorityKeyEquivalenceService.stats(self.superuser)
        by_source = {r["source"]: r["count"] for r in stats["by_source"]}
        assert by_source.get("manual") == 1
        assert by_source.get("baseline", 0) >= 1
        assert stats["total_count"] == sum(by_source.values())

    def test_stats_non_superuser_empty(self):
        assert AuthorityKeyEquivalenceService.stats(self.regular) == {
            "total_count": 0,
            "by_source": [],
        }

    def test_visible_gate(self):
        AuthorityKeyEquivalence.objects.create(
            from_key="exchange-act:99", to_key="usc-15:99", source="baseline"
        )
        assert AuthorityKeyEquivalenceService.visible(self.superuser).exists()
        assert not AuthorityKeyEquivalenceService.visible(self.regular).exists()


_CONN_QUERY = """
    query ($source: String, $search: String) {
      authorityKeyEquivalences(source: $source, search: $search, first: 50) {
        edges { node { fromKey toKey source editable createdByUsername } }
      }
    }
"""

_STATS_QUERY = """
    query { authorityMappingStats { totalCount bySource { source count } } }
"""

_CREATE = """
    mutation ($from: String!, $to: String!, $note: String) {
      createAuthorityKeyEquivalence(fromKey: $from, toKey: $to, note: $note) {
        ok message obj { fromKey toKey source editable }
      }
    }
"""

_UPDATE = """
    mutation ($id: ID!, $to: String) {
      updateAuthorityKeyEquivalence(id: $id, toKey: $to) { ok message obj { toKey } }
    }
"""

_DELETE = """
    mutation ($id: ID!) {
      deleteAuthorityKeyEquivalence(id: $id) { ok message }
    }
"""


class AuthorityMappingGraphQLTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )
        self.regular = User.objects.create_user(username="joe", password="p")

    def test_connection_superuser_sees_rows_regular_empty(self):
        AuthorityKeyEquivalence.objects.create(
            from_key="exchange-act:99", to_key="usc-15:99", source="baseline"
        )
        res = _run(_CONN_QUERY, self.superuser)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        edges = res["data"]["authorityKeyEquivalences"]["edges"]
        assert len(edges) >= 1
        node = next(
            e["node"] for e in edges if e["node"]["fromKey"] == "exchange-act:99"
        )
        assert node["editable"] is False  # baseline → read-only

        res2 = _run(_CONN_QUERY, self.regular)
        self.assertIsNone(res2.get("errors"), res2.get("errors"))
        assert res2["data"]["authorityKeyEquivalences"]["edges"] == []

    def test_create_update_delete_round_trip(self):
        # create
        res = _run(_CREATE, self.superuser, **{"from": "irc:777", "to": "usc-26:777"})
        self.assertIsNone(res.get("errors"), res.get("errors"))
        payload = res["data"]["createAuthorityKeyEquivalence"]
        assert payload["ok"], payload["message"]
        assert payload["obj"]["editable"] is True
        row = AuthorityKeyEquivalence.objects.get(from_key="irc:777")
        assert row.created_by_id == self.superuser.id

        from graphql_relay import to_global_id

        gid = to_global_id("AuthorityKeyEquivalenceNode", row.pk)
        # update
        res = _run(_UPDATE, self.superuser, id=gid, to="usc-26:778")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["updateAuthorityKeyEquivalence"]["ok"]
        row.refresh_from_db()
        assert row.to_key == "usc-26:778"
        # delete
        res = _run(_DELETE, self.superuser, id=gid)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["deleteAuthorityKeyEquivalence"]["ok"]
        assert not AuthorityKeyEquivalence.objects.filter(pk=row.pk).exists()

    def test_create_denied_for_non_superuser(self):
        res = _run(_CREATE, self.regular, **{"from": "irc:777", "to": "usc-26:777"})
        self.assertIsNone(res.get("errors"), res.get("errors"))
        payload = res["data"]["createAuthorityKeyEquivalence"]
        assert payload["ok"] is False
        assert not AuthorityKeyEquivalence.objects.filter(from_key="irc:777").exists()

    def test_mutation_on_managed_row_rejected(self):
        from graphql_relay import to_global_id

        managed = AuthorityKeyEquivalence.objects.create(
            from_key="exchange-act:99", to_key="usc-15:99", source="baseline"
        )
        gid = to_global_id("AuthorityKeyEquivalenceNode", managed.pk)
        res = _run(_DELETE, self.superuser, id=gid)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["deleteAuthorityKeyEquivalence"]["ok"] is False
        assert AuthorityKeyEquivalence.objects.filter(pk=managed.pk).exists()

    def test_stats_query(self):
        AuthorityKeyEquivalence.objects.create(
            from_key="exchange-act:99", to_key="usc-15:99", source="baseline"
        )
        res = _run(_STATS_QUERY, self.superuser)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        stats = res["data"]["authorityMappingStats"]
        assert stats["totalCount"] >= 1
        assert any(r["source"] == "baseline" for r in stats["bySource"])
