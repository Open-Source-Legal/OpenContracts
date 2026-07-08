"""Tests for the AuthorityNamespace management surface (Authority Console Phase 1).

Covers ``AuthorityNamespaceService`` (superuser gate, prefix-grammar validation,
source="manual" + created_by capture, alias normalisation, the
is_global ⊕ authority_corpus invariant, the delete dependency-guard, faceted
stats, the string-joined detail projection), the loader's source-ownership guard
(a re-load must NOT clobber a curator-edited "manual" namespace), and the
superuser-only GraphQL connection / detail / stats / mutations.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from graphql_relay import to_global_id

from opencontractserver.annotations.models import (
    AuthorityFrontier,
    AuthorityKeyEquivalence,
    AuthorityNamespace,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.enrichment.services import AuthorityNamespaceService
from opencontractserver.enrichment.services.authority_mapping_loader import (
    AuthorityMappingLoader,
)

User = get_user_model()


class _Ctx:
    """Minimal GraphQL context (mirrors test_authority_mapping_crud._Ctx)."""

    def __init__(self, user):
        self.user = user
        self.META = {}


def _run(query, user, **variables):
    from config.graphql.schema import schema
    from config.graphql.testing import Client

    return Client(schema, context_value=_Ctx(user)).execute(query, variables=variables)


class AuthorityNamespaceServiceTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )
        self.regular = User.objects.create_user(username="joe", password="p")

    # ---- create --------------------------------------------------------------
    def test_create_stamps_manual_and_provenance(self):
        res = AuthorityNamespaceService.create(
            self.superuser,
            prefix="zz-test",
            display_name="ZZ Test Code",
            jurisdiction="us-zz",
            authority_type="statute",
            aliases=["ZZ Code", "zz code", " Zz Act "],
        )
        assert res.ok, res.error
        assert res.obj is not None
        assert res.obj.source == "manual"
        assert res.obj.created_by_id == self.superuser.id
        # normalised: lowercase + de-dupe + sort + strip
        assert res.obj.aliases == ["zz act", "zz code"]

    def test_create_rejects_non_admin(self):
        res = AuthorityNamespaceService.create(
            self.regular, prefix="zz-test", display_name="ZZ"
        )
        assert not res.ok
        assert not AuthorityNamespace.objects.filter(prefix="zz-test").exists()

    def test_create_rejects_malformed_prefix(self):
        res = AuthorityNamespaceService.create(
            self.superuser, prefix="Not A Prefix!", display_name="X"
        )
        assert not res.ok
        assert "prefix" in res.error.lower()

    def test_create_rejects_bad_authority_type(self):
        res = AuthorityNamespaceService.create(
            self.superuser,
            prefix="zz-test",
            display_name="X",
            authority_type="not-a-type",
        )
        assert not res.ok
        assert "authority_type" in res.error

    def test_create_rejects_duplicate_prefix(self):
        AuthorityNamespaceService.create(
            self.superuser, prefix="zz-test", display_name="X"
        )
        res = AuthorityNamespaceService.create(
            self.superuser, prefix="zz-test", display_name="Y"
        )
        assert not res.ok
        assert "already exists" in res.error

    def test_create_with_corpus_link_forces_non_global(self):
        corpus = Corpus.objects.create(title="C", creator=self.superuser)
        res = AuthorityNamespaceService.create(
            self.superuser,
            prefix="zz-corpus",
            display_name="Corpus Body",
            is_global=True,  # explicitly True, but a corpus link must win
            authority_corpus_id=corpus.id,
        )
        assert res.ok, res.error
        assert res.obj is not None
        assert res.obj.is_global is False
        assert res.obj.authority_corpus_id == corpus.id

    # ---- update --------------------------------------------------------------
    def test_update_stamps_manual(self):
        # A baseline row edited through the service becomes a manual override.
        baseline = AuthorityNamespace.objects.create(
            prefix="zz-base", display_name="Base", source="baseline"
        )
        res = AuthorityNamespaceService.update(
            self.superuser, pk=baseline.pk, display_name="Edited"
        )
        assert res.ok, res.error
        baseline.refresh_from_db()
        assert baseline.display_name == "Edited"
        assert baseline.source == "manual"
        assert baseline.created_by_id == self.superuser.id

    def test_update_rejects_non_admin(self):
        ns = AuthorityNamespace.objects.create(prefix="zz", display_name="X")
        res = AuthorityNamespaceService.update(
            self.regular, pk=ns.pk, display_name="Hacked"
        )
        assert not res.ok
        ns.refresh_from_db()
        assert ns.display_name == "X"

    def test_update_clear_nullable_with_empty_string(self):
        ns = AuthorityNamespace.objects.create(
            prefix="zz", display_name="X", jurisdiction="us-zz"
        )
        res = AuthorityNamespaceService.update(
            self.superuser, pk=ns.pk, jurisdiction=""
        )
        assert res.ok, res.error
        ns.refresh_from_db()
        assert ns.jurisdiction is None

    def test_update_unknown_pk_denied(self):
        # A pk that doesn't exist is opaque (no existence oracle): DENIED, not 404.
        res = AuthorityNamespaceService.update(
            self.superuser, pk=987654321, display_name="X"
        )
        assert not res.ok
        assert res.obj is None

    def test_update_persists_all_partial_fields(self):
        # Per-field partial updates the round-trip GraphQL test doesn't exercise:
        # authority_type / provider / source_root_url / license / is_global, and
        # the _clean() strip-to-None for the nullable string columns.
        corpus = Corpus.objects.create(title="C", creator=self.superuser)
        ns = AuthorityNamespace.objects.create(
            prefix="zz-fields", display_name="X", is_global=True
        )
        res = AuthorityNamespaceService.update(
            self.superuser,
            pk=ns.pk,
            authority_type="regulation",
            provider="  USCodeAuthoritySourceProvider  ",
            source_root_url="  https://example.test  ",
            license="  public-domain  ",
            is_global=False,
            authority_corpus_id=corpus.id,
        )
        assert res.ok, res.error
        ns.refresh_from_db()
        assert ns.authority_type == "regulation"
        # _clean strips surrounding whitespace on the advisory string columns.
        assert ns.provider == "USCodeAuthoritySourceProvider"
        assert ns.source_root_url == "https://example.test"
        assert ns.license == "public-domain"
        # A corpus link forces non-global even though we passed is_global=False.
        assert ns.is_global is False
        assert ns.authority_corpus_id == corpus.id

    def test_update_backfills_created_by_when_null(self):
        # A baseline row seeded with no creator gets stamped on first edit.
        ns = AuthorityNamespace.objects.create(
            prefix="zz-nocreator", display_name="X", source="baseline"
        )
        assert ns.created_by_id is None
        res = AuthorityNamespaceService.update(
            self.superuser, pk=ns.pk, display_name="Edited"
        )
        assert res.ok, res.error
        ns.refresh_from_db()
        assert ns.created_by_id == self.superuser.id

    def test_update_rejects_bad_authority_type(self):
        ns = AuthorityNamespace.objects.create(prefix="zz", display_name="X")
        res = AuthorityNamespaceService.update(
            self.superuser, pk=ns.pk, authority_type="not-a-type"
        )
        assert not res.ok
        assert "authority_type" in res.error
        ns.refresh_from_db()
        assert ns.authority_type in (None, "")

    def test_update_surfaces_save_exception_as_error(self):
        # The save-time guard: a ValidationError raised by save() (carrying a
        # .messages list) is surfaced as a clean operation error, not a 500.
        ns = AuthorityNamespace.objects.create(prefix="zz-saveerr", display_name="X")
        with mock.patch.object(
            AuthorityNamespace, "save", side_effect=ValidationError("boom-update")
        ):
            res = AuthorityNamespaceService.update(
                self.superuser, pk=ns.pk, display_name="Edited"
            )
        assert not res.ok
        assert "boom-update" in res.error

    def test_create_surfaces_save_exception_as_error(self):
        # The create save-time guard (ValidationError path, .messages join).
        with mock.patch.object(
            AuthorityNamespace, "save", side_effect=ValidationError("boom-create")
        ):
            res = AuthorityNamespaceService.create(
                self.superuser, prefix="zz-create-err", display_name="X"
            )
        assert not res.ok
        assert "boom-create" in res.error
        assert not AuthorityNamespace.objects.filter(prefix="zz-create-err").exists()

    def test_create_surfaces_integrity_error_as_error(self):
        # The IntegrityError branch of the create save-guard + the plain-str()
        # branch of _error_text (an IntegrityError has no .messages list).
        with mock.patch.object(
            AuthorityNamespace, "save", side_effect=IntegrityError("dup-key")
        ):
            res = AuthorityNamespaceService.create(
                self.superuser, prefix="zz-int-err", display_name="X"
            )
        assert not res.ok
        assert "dup-key" in res.error

    def test_delete_unknown_pk_denied(self):
        res = AuthorityNamespaceService.delete(self.superuser, pk=987654321)
        assert not res.ok
        assert res.obj is None

    # ---- aliases -------------------------------------------------------------
    def test_set_aliases_normalises(self):
        ns = AuthorityNamespace.objects.create(prefix="zz", display_name="X")
        res = AuthorityNamespaceService.set_aliases(
            self.superuser, pk=ns.pk, aliases=["Beta", "alpha", "ALPHA", " "]
        )
        assert res.ok, res.error
        ns.refresh_from_db()
        assert ns.aliases == ["alpha", "beta"]
        assert ns.source == "manual"

    # ---- delete + guard ------------------------------------------------------
    def test_delete_clean(self):
        ns = AuthorityNamespace.objects.create(prefix="zz-del", display_name="X")
        res = AuthorityNamespaceService.delete(self.superuser, pk=ns.pk)
        assert res.ok, res.error
        assert not AuthorityNamespace.objects.filter(pk=ns.pk).exists()

    def test_delete_guarded_by_dependencies(self):
        ns = AuthorityNamespace.objects.create(prefix="zz-dep", display_name="X")
        AuthorityFrontier.objects.create(canonical_key="zz-dep:1", authority="zz-dep")
        res = AuthorityNamespaceService.delete(self.superuser, pk=ns.pk)
        assert not res.ok
        assert "frontier" in res.error
        assert AuthorityNamespace.objects.filter(pk=ns.pk).exists()

    # ---- stats / visibility --------------------------------------------------
    def test_stats_faceted(self):
        AuthorityNamespace.objects.create(
            prefix="zz-a",
            display_name="A",
            jurisdiction="us-zz",
            authority_type="statute",
            is_global=True,
        )
        stats = AuthorityNamespaceService.stats(self.superuser)
        assert stats["total_count"] >= 1
        scopes = {r["value"]: r["count"] for r in stats["by_scope"]}
        assert scopes.get("global", 0) >= 1

    def test_stats_non_admin_empty(self):
        assert AuthorityNamespaceService.stats(self.regular)["total_count"] == 0

    def test_visible_gate(self):
        AuthorityNamespace.objects.create(prefix="zz", display_name="X")
        assert AuthorityNamespaceService.visible(self.superuser).exists()
        assert not AuthorityNamespaceService.visible(self.regular).exists()

    # ---- detail string-join projection --------------------------------------
    def test_detail_joins_by_colon_anchored_prefix(self):
        ns = AuthorityNamespace.objects.create(prefix="usc-1", display_name="Title 1")
        # A neighbour that must NOT bleed into usc-1 (the usc-1 / usc-15 trap).
        AuthorityNamespace.objects.create(prefix="usc-15", display_name="Title 15")
        AuthorityKeyEquivalence.objects.create(
            from_key="usc-1:1", to_key="other:1", source="baseline"
        )
        AuthorityKeyEquivalence.objects.create(
            from_key="usc-15:78j", to_key="other:2", source="baseline"
        )
        AuthorityFrontier.objects.create(canonical_key="usc-1:1", authority="usc-1")
        AuthorityFrontier.objects.create(canonical_key="usc-15:78j", authority="usc-15")

        detail = AuthorityNamespaceService.detail(self.superuser, "usc-1")
        assert detail is not None
        assert detail.namespace.pk == ns.pk
        out_keys = {e.from_key for e in detail.equivalences_out}
        assert out_keys == {"usc-1:1"}  # usc-15:78j excluded by the colon anchor
        frontier_keys = {f.canonical_key for f in detail.frontier_rows}
        assert frontier_keys == {"usc-1:1"}
        assert detail.reference_total == 0

    def test_detail_unknown_prefix_none(self):
        assert AuthorityNamespaceService.detail(self.superuser, "nope-xyz") is None

    def test_detail_non_admin_none(self):
        AuthorityNamespace.objects.create(prefix="zz", display_name="X")
        assert AuthorityNamespaceService.detail(self.regular, "zz") is None

    def test_detail_effective_provider_none_when_unhandled(self):
        # _effective_provider is best-effort: a prefix no registered provider
        # handles yields None gracefully (the detail call must not raise).
        AuthorityNamespace.objects.create(
            prefix="zz-noprovider", display_name="No Provider Body"
        )
        detail = AuthorityNamespaceService.detail(self.superuser, "zz-noprovider")
        assert detail is not None
        assert detail.effective_provider is None


class AuthorityNamespaceLoaderGuardTests(TestCase):
    """The loader must never clobber a curator-edited (source='manual') namespace."""

    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )

    def test_loader_skips_manual_rows(self):
        # 'dgcl' is a real prefix in authority_mappings.yaml. Replace whatever the
        # seed created with a curator-owned manual row carrying a distinctive alias.
        AuthorityNamespace.objects.filter(prefix="dgcl").delete()
        manual = AuthorityNamespace.objects.create(
            prefix="dgcl",
            display_name="Curator Override Name",
            aliases=["my-curated-alias"],
            source="manual",
            created_by=self.superuser,
        )
        result = AuthorityMappingLoader.load_namespaces()
        assert result["skipped_manual"] >= 1
        manual.refresh_from_db()
        # Untouched: the loader did not overwrite the curator's edits.
        assert manual.source == "manual"
        assert manual.display_name == "Curator Override Name"
        assert manual.aliases == ["my-curated-alias"]

    def test_loader_still_upserts_baseline_rows(self):
        AuthorityNamespace.objects.filter(prefix="dgcl").delete()
        result = AuthorityMappingLoader.load_namespaces()
        # A fresh baseline dgcl row is (re)created and tagged source='baseline'.
        row = AuthorityNamespace.objects.get(prefix="dgcl")
        assert row.source == "baseline"
        assert result["total"] >= 1


_CONN_QUERY = """
    query ($search: String, $scope: String) {
      authorityNamespaces(search: $search, scope: $scope, first: 50) {
        edges { node { prefix displayName scope source aliases frontierCount } }
      }
    }
"""

_STATS_QUERY = """
    query {
      authorityNamespaceStats {
        totalCount
        byScope { value count }
        byAuthorityType { value count }
      }
    }
"""

_DETAIL_QUERY = """
    query ($prefix: String!) {
      authorityNamespaceDetail(prefix: $prefix) {
        namespace { prefix displayName }
        equivalencesOut { fromKey toKey }
        frontierRows { canonicalKey discoveryState }
        referenceTotal
        effectiveProvider
      }
    }
"""

_CREATE = """
    mutation ($prefix: String!, $name: String!, $aliases: [String]) {
      createAuthorityNamespace(prefix: $prefix, displayName: $name, aliases: $aliases) {
        ok message obj { prefix source aliases }
      }
    }
"""

_UPDATE = """
    mutation ($id: ID!, $name: String) {
      updateAuthorityNamespace(id: $id, displayName: $name) {
        ok message obj { displayName source }
      }
    }
"""

_CREATE_WITH_CORPUS = """
    mutation ($prefix: String!, $name: String!, $corpusId: ID) {
      createAuthorityNamespace(
        prefix: $prefix, displayName: $name, authorityCorpusId: $corpusId
      ) {
        ok message obj { prefix }
      }
    }
"""

_UPDATE_CORPUS = """
    mutation ($id: ID!, $corpusId: ID) {
      updateAuthorityNamespace(id: $id, authorityCorpusId: $corpusId) {
        ok message obj { displayName }
      }
    }
"""

_SET_ALIASES = """
    mutation ($id: ID!, $aliases: [String]!) {
      setAuthorityNamespaceAliases(id: $id, aliases: $aliases) {
        ok obj { aliases }
      }
    }
"""

_DELETE = """
    mutation ($id: ID!) {
      deleteAuthorityNamespace(id: $id) { ok message }
    }
"""


class AuthorityNamespaceGraphQLTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )
        self.regular = User.objects.create_user(username="joe", password="p")

    def test_connection_superuser_sees_rows_regular_empty(self):
        AuthorityNamespace.objects.create(
            prefix="zz-conn", display_name="ZZ", is_global=True
        )
        res = _run(_CONN_QUERY, self.superuser)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        prefixes = [
            e["node"]["prefix"] for e in res["data"]["authorityNamespaces"]["edges"]
        ]
        assert "zz-conn" in prefixes

        res2 = _run(_CONN_QUERY, self.regular)
        self.assertIsNone(res2.get("errors"), res2.get("errors"))
        assert res2["data"]["authorityNamespaces"]["edges"] == []

    def test_scope_filter(self):
        AuthorityNamespace.objects.create(
            prefix="zz-global", display_name="G", is_global=True
        )
        corpus = Corpus.objects.create(title="C", creator=self.superuser)
        AuthorityNamespace.objects.create(
            prefix="zz-corpus",
            display_name="C",
            is_global=False,
            authority_corpus=corpus,
        )
        res = _run(_CONN_QUERY, self.superuser, scope="corpus")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        prefixes = [
            e["node"]["prefix"] for e in res["data"]["authorityNamespaces"]["edges"]
        ]
        assert "zz-corpus" in prefixes
        assert "zz-global" not in prefixes

    def test_create_update_set_aliases_delete_round_trip(self):
        res = _run(
            _CREATE,
            self.superuser,
            prefix="zz-rt",
            name="Round Trip",
            aliases=["Foo", "foo", "Bar"],
        )
        self.assertIsNone(res.get("errors"), res.get("errors"))
        payload = res["data"]["createAuthorityNamespace"]
        assert payload["ok"], payload["message"]
        assert payload["obj"]["source"] == "manual"
        assert payload["obj"]["aliases"] == ["bar", "foo"]
        row = AuthorityNamespace.objects.get(prefix="zz-rt")
        gid = to_global_id("AuthorityNamespaceNode", row.pk)

        res = _run(_UPDATE, self.superuser, id=gid, name="Renamed")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["updateAuthorityNamespace"]["ok"]
        row.refresh_from_db()
        assert row.display_name == "Renamed"

        res = _run(_SET_ALIASES, self.superuser, id=gid, aliases=["zeta", "alpha"])
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["setAuthorityNamespaceAliases"]["obj"]["aliases"] == [
            "alpha",
            "zeta",
        ]

        res = _run(_DELETE, self.superuser, id=gid)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["deleteAuthorityNamespace"]["ok"]
        assert not AuthorityNamespace.objects.filter(pk=row.pk).exists()

    def test_create_denied_for_non_superuser(self):
        res = _run(_CREATE, self.regular, prefix="zz-deny", name="X", aliases=[])
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["createAuthorityNamespace"]["ok"] is False
        assert not AuthorityNamespace.objects.filter(prefix="zz-deny").exists()

    def test_create_rejects_malformed_corpus_id(self):
        # A non-empty but undecodable global id must NOT silently fall through to
        # "no corpus" (creating a stray global namespace) — it must be an error.
        res = _run(
            _CREATE_WITH_CORPUS,
            self.superuser,
            prefix="zz-badcorpus",
            name="X",
            corpusId="totally-bogus-id",
        )
        self.assertIsNone(res.get("errors"), res.get("errors"))
        payload = res["data"]["createAuthorityNamespace"]
        assert payload["ok"] is False
        assert "authority_corpus_id" in (payload["message"] or "").lower()
        assert not AuthorityNamespace.objects.filter(prefix="zz-badcorpus").exists()

    def test_update_rejects_malformed_corpus_id(self):
        ns = AuthorityNamespace.objects.create(
            prefix="zz-updcorpus", display_name="X", is_global=True
        )
        gid = to_global_id("AuthorityNamespaceNode", ns.pk)
        res = _run(_UPDATE_CORPUS, self.superuser, id=gid, corpusId="totally-bogus-id")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        payload = res["data"]["updateAuthorityNamespace"]
        assert payload["ok"] is False
        assert "authority_corpus_id" in (payload["message"] or "").lower()

    def test_detail_query(self):
        AuthorityNamespace.objects.create(prefix="zz-d", display_name="Detail")
        AuthorityKeyEquivalence.objects.create(
            from_key="zz-d:1", to_key="other:1", source="baseline"
        )
        res = _run(_DETAIL_QUERY, self.superuser, prefix="zz-d")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        detail = res["data"]["authorityNamespaceDetail"]
        assert detail["namespace"]["prefix"] == "zz-d"
        assert {e["fromKey"] for e in detail["equivalencesOut"]} == {"zz-d:1"}
        assert detail["referenceTotal"] == 0

    def test_detail_denied_for_non_superuser(self):
        AuthorityNamespace.objects.create(prefix="zz-d", display_name="Detail")
        res = _run(_DETAIL_QUERY, self.regular, prefix="zz-d")
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["authorityNamespaceDetail"] is None

    def test_stats_query(self):
        AuthorityNamespace.objects.create(
            prefix="zz-s", display_name="S", is_global=True
        )
        res = _run(_STATS_QUERY, self.superuser)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        stats = res["data"]["authorityNamespaceStats"]
        assert stats["totalCount"] >= 1
