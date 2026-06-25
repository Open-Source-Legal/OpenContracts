import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from opencontractserver.annotations.models import (
    AuthorityKeyEquivalence,
    AuthorityNamespace,
)
from opencontractserver.enrichment.services.authority_mapping_loader import (
    AuthorityMappingLoader,
)


def _write_yaml(body: str) -> Path:
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    fh.write(body)
    fh.close()
    return Path(fh.name)


# Synthetic key pairs used as clean-slate fixtures. They deliberately do NOT
# appear in the shipped ``authority_mappings.yaml`` (and are therefore not
# pre-seeded into the test DB by the baseline migrations 0087/0092), so these
# tests exercise create/skip semantics against a known-absent starting state.
# Real keys like ``irc:401`` ship in the baseline, so reusing them here would
# collide with the migration-seeded rows.
_FIXTURE_FROM = "test-act:1"
_FIXTURE_TO = "usc-99:1"
_FIXTURE_FROM_2 = "test-act:2"
_FIXTURE_TO_2 = "usc-99:2"


class AuthorityKeyEquivalenceBaselineChoiceTests(TestCase):
    def test_baseline_is_a_valid_source(self):
        eq = AuthorityKeyEquivalence(
            from_key=_FIXTURE_FROM, to_key=_FIXTURE_TO, source="baseline"
        )
        eq.full_clean()


class AuthorityMappingLoaderTests(TestCase):
    def test_loads_pairs_as_baseline(self):
        path = _write_yaml(
            "equivalences:\n"
            f'  - {{from_key: "{_FIXTURE_FROM}", to_key: "{_FIXTURE_TO}"}}\n'
            f'  - {{from_key: "{_FIXTURE_FROM_2}", to_key: "{_FIXTURE_TO_2}", '
            'note: "synthetic fixture"}\n'
        )
        summary = AuthorityMappingLoader.load(path=path)
        assert summary["created"] == 2
        row = AuthorityKeyEquivalence.objects.get(
            from_key=_FIXTURE_FROM, to_key=_FIXTURE_TO
        )
        assert row.source == "baseline"
        assert row.confidence == 1.0
        assert (
            AuthorityKeyEquivalence.objects.get(from_key=_FIXTURE_FROM_2).note
            == "synthetic fixture"
        )

    def test_idempotent(self):
        path = _write_yaml(
            "equivalences:\n"
            f'  - {{from_key: "{_FIXTURE_FROM}", to_key: "{_FIXTURE_TO}"}}\n'
        )
        AuthorityMappingLoader.load(path=path)
        summary = AuthorityMappingLoader.load(path=path)
        assert summary["created"] == 0
        assert summary["updated"] == 1
        assert (
            AuthorityKeyEquivalence.objects.filter(from_key=_FIXTURE_FROM).count() == 1
        )

    def test_skips_manual_rows(self):
        AuthorityKeyEquivalence.objects.create(
            from_key=_FIXTURE_FROM,
            to_key=_FIXTURE_TO,
            source="manual",
            note="curator",
        )
        path = _write_yaml(
            "equivalences:\n"
            f'  - {{from_key: "{_FIXTURE_FROM}", to_key: "{_FIXTURE_TO}"}}\n'
        )
        summary = AuthorityMappingLoader.load(path=path)
        assert summary["skipped_owned"] == 1
        row = AuthorityKeyEquivalence.objects.get(
            from_key=_FIXTURE_FROM, to_key=_FIXTURE_TO
        )
        assert row.source == "manual"
        assert row.note == "curator"

    def test_skips_importer_owned_rows(self):
        # Source-ownership partition: the loader owns only "baseline"; an
        # importer-owned uslm/popular_name row must survive a reload untouched.
        AuthorityKeyEquivalence.objects.create(
            from_key=_FIXTURE_FROM,
            to_key=_FIXTURE_TO,
            source="popular_name",
            confidence=0.85,
            note="OLRC table",
        )
        path = _write_yaml(
            "equivalences:\n"
            f'  - {{from_key: "{_FIXTURE_FROM}", to_key: "{_FIXTURE_TO}"}}\n'
        )
        summary = AuthorityMappingLoader.load(path=path)
        assert summary["skipped_owned"] == 1
        row = AuthorityKeyEquivalence.objects.get(
            from_key=_FIXTURE_FROM, to_key=_FIXTURE_TO
        )
        assert row.source == "popular_name"
        assert row.confidence == 0.85
        assert row.note == "OLRC table"

    def test_rejects_malformed_key(self):
        path = _write_yaml(
            'equivalences:\n  - {from_key: "garbage", to_key: "usc-26:401"}\n'
        )
        with self.assertRaises(ValueError):
            AuthorityMappingLoader.load(path=path)

    def test_rejects_self_equivalence(self):
        # A key cannot bridge to itself; the reader must reject it fail-fast
        # rather than letting the loader silently drop it from the tally.
        path = _write_yaml(
            'equivalences:\n  - {from_key: "test-act:1", to_key: "test-act:1"}\n'
        )
        with self.assertRaises(ValueError):
            AuthorityMappingLoader.load(path=path)

    def test_default_yaml_loads(self):
        summary = AuthorityMappingLoader.load()
        assert summary["total"] >= 19
        assert AuthorityKeyEquivalence.objects.filter(
            from_key="exchange-act:10", to_key="usc-15:78j"
        ).exists()

    def test_rejects_entry_missing_keys(self):
        path = _write_yaml('equivalences:\n  - {to_key: "usc-26:401"}\n')
        with self.assertRaises(ValueError):
            AuthorityMappingLoader.load(path=path)

    def test_dedupes_duplicate_pairs(self):
        path = _write_yaml(
            "equivalences:\n"
            '  - {from_key: "test-act:1", to_key: "usc-99:1"}\n'
            '  - {from_key: "test-act:1", to_key: "usc-99:1"}\n'
        )
        summary = AuthorityMappingLoader.load(path=path)
        assert summary["created"] == 1
        assert summary["total"] == 1
        assert (
            AuthorityKeyEquivalence.objects.filter(
                from_key="test-act:1", to_key="usc-99:1"
            ).count()
            == 1
        )

    def test_empty_equivalences_is_noop(self):
        path = _write_yaml("equivalences: []\n")
        summary = AuthorityMappingLoader.load(path=path)
        assert summary == {
            "created": 0,
            "updated": 0,
            "skipped_owned": 0,
            "total": 0,
        }

    def test_baseline_then_manual_override_then_reload_skips(self):
        # Load as baseline, an operator overrides it to manual, a reload must NOT
        # clobber the override — the feature's core safety guarantee.
        path = _write_yaml(
            'equivalences:\n  - {from_key: "test-act:2", to_key: "usc-99:2"}\n'
        )
        AuthorityMappingLoader.load(path=path)
        AuthorityKeyEquivalence.objects.filter(
            from_key="test-act:2", to_key="usc-99:2"
        ).update(source="manual", note="curator override")

        summary = AuthorityMappingLoader.load(path=path)
        assert summary["skipped_owned"] == 1
        row = AuthorityKeyEquivalence.objects.get(
            from_key="test-act:2", to_key="usc-99:2"
        )
        assert row.source == "manual"
        assert row.note == "curator override"


class AuthorityNamespaceLoaderTests(TestCase):
    _NS_YAML = (
        "prefixes:\n"
        "  test-body:\n"
        '    display_name: "Test Body of Law"\n'
        '    jurisdiction: "us-federal"\n'
        '    authority_type: "statute"\n'
        '    aliases: ["the test act", "test body"]\n'
    )

    def test_load_namespaces_creates_global_row(self):
        path = _write_yaml(self._NS_YAML)
        summary = AuthorityMappingLoader.load_namespaces(path=path)
        assert summary["created"] == 1
        ns = AuthorityNamespace.objects.get(prefix="test-body")
        assert ns.display_name == "Test Body of Law"
        assert ns.jurisdiction == "us-federal"
        assert ns.authority_type == "statute"
        assert ns.is_global is True
        assert ns.aliases == ["test body", "the test act"]  # sorted, deduped

    def test_load_namespaces_idempotent(self):
        path = _write_yaml(self._NS_YAML)
        AuthorityMappingLoader.load_namespaces(path=path)
        summary = AuthorityMappingLoader.load_namespaces(path=path)
        assert summary["created"] == 0
        assert summary["updated"] == 1
        assert AuthorityNamespace.objects.filter(prefix="test-body").count() == 1

    def test_load_namespaces_skips_corpus_linked_row(self):
        # A corpus-scoped namespace owning the same prefix must NOT be flipped
        # to global by a baseline reload.
        from django.contrib.auth import get_user_model

        from opencontractserver.corpuses.models import Corpus

        User = get_user_model()
        user = User.objects.create_user(username="ns-owner", password="x")
        corpus = Corpus.objects.create(title="Authority Corpus", creator=user)
        AuthorityNamespace.objects.create(
            prefix="test-body",
            display_name="Corpus-owned",
            is_global=False,
            authority_corpus=corpus,
        )
        path = _write_yaml(self._NS_YAML)
        summary = AuthorityMappingLoader.load_namespaces(path=path)
        assert summary["skipped_corpus_linked"] == 1
        ns = AuthorityNamespace.objects.get(prefix="test-body")
        assert ns.is_global is False
        assert ns.display_name == "Corpus-owned"

    def test_load_all_returns_both_summaries(self):
        summary = AuthorityMappingLoader.load_all()
        assert set(summary) == {"namespaces", "equivalences"}
        assert summary["equivalences"]["total"] >= 19
        # The shipped sec-rule body of law is upserted as a global namespace.
        assert AuthorityNamespace.objects.filter(
            prefix="sec-rule", is_global=True
        ).exists()

    def test_default_yaml_seeds_known_bodies(self):
        AuthorityMappingLoader.load_namespaces()
        ns = AuthorityNamespace.objects.get(prefix="exchange-act")
        assert ns.display_name == "Securities Exchange Act of 1934"
        assert "exchange act" in ns.aliases


class NamespaceReseedOwnershipTests(TestCase):
    """The ``post_migrate`` namespace convergence (``ensure_seeded``) must honour
    the same source-ownership partition as ``AuthorityMappingLoader.load_namespaces``.

    Regression for the seed-clobber bug: ``ensure_seeded`` runs on every
    production ``migrate`` (and every test flush) and used to ``update_or_create``
    every shipped-prefix namespace unconditionally — silently reverting a
    curator's ``source="manual"`` edits (display_name / jurisdiction /
    authority_type / aliases) on the next deploy, defeating the console's headline
    "a re-load can no longer clobber a curator's runtime edits" guarantee. The
    loader already skips manual/corpus-linked rows; the seed must too.
    """

    def test_reseed_preserves_manual_namespace_edits(self):
        from opencontractserver.enrichment._namespace_seed import ensure_seeded

        # "dgcl" is a shipped baseline prefix the seed converges. A curator edits
        # it through the console (stamped source="manual").
        AuthorityNamespace.objects.update_or_create(
            prefix="dgcl",
            defaults={
                "display_name": "CURATOR EDITED",
                "jurisdiction": "us-de",
                "authority_type": "statute",
                "aliases": ["curator alias", "dgcl"],
                "is_global": True,
                "source": "manual",
            },
        )

        ensure_seeded()  # simulate the post_migrate / flush convergence

        ns = AuthorityNamespace.objects.get(prefix="dgcl")
        assert ns.source == "manual"
        assert ns.display_name == "CURATOR EDITED"
        assert "curator alias" in ns.aliases

    def test_reseed_skips_corpus_linked_row(self):
        from django.contrib.auth import get_user_model

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.enrichment._namespace_seed import ensure_seeded

        User = get_user_model()
        user = User.objects.create_user(username="reseed-owner", password="x")
        corpus = Corpus.objects.create(title="Reseed Authority Corpus", creator=user)
        # A corpus-scoped namespace owning a shipped prefix must never be flipped
        # global / clobbered by the convergence.
        AuthorityNamespace.objects.filter(prefix="dgcl").delete()
        AuthorityNamespace.objects.create(
            prefix="dgcl",
            display_name="Corpus-owned DGCL",
            is_global=False,
            authority_corpus=corpus,
        )

        ensure_seeded()

        ns = AuthorityNamespace.objects.get(prefix="dgcl")
        assert ns.is_global is False
        assert ns.display_name == "Corpus-owned DGCL"

    def test_reseed_still_converges_baseline_rows(self):
        # The convergence must still (re)create a shipped baseline prefix that is
        # absent — its whole reason for existing (post-flush re-seed).
        from opencontractserver.enrichment._namespace_seed import ensure_seeded

        AuthorityNamespace.objects.filter(prefix="dgcl").delete()
        ensure_seeded()
        ns = AuthorityNamespace.objects.get(prefix="dgcl")
        assert ns.is_global is True
        assert ns.source == "baseline"


class LoadAuthorityMappingsCommandTests(TestCase):
    def test_command_loads_baseline(self):
        out = StringIO()
        call_command("load_authority_mappings", stdout=out)
        assert AuthorityKeyEquivalence.objects.filter(
            from_key="irc:401", to_key="usc-26:401"
        ).exists()
        assert AuthorityNamespace.objects.filter(prefix="exchange-act").exists()
        assert "created" in out.getvalue().lower()


class AuthorityMappingsMigrationTests(TestCase):
    """Verify the data migration's effect: the shipped baseline loads.

    The rows are seeded by data migrations 0087/0092 at DB-creation time, but a
    ``TransactionTestCase`` in any other module truncates the table on a reused
    ``--keepdb`` database and migrations do not re-run, so asserting bare
    persistence is flaky (``test_authority_discovery`` works around the same
    flush with a get_or_create safety net). We instead invoke the loader the
    migration calls — it is idempotent and source-scoped — then assert the
    baseline rows the YAML ships are present as ``source="baseline"``.
    """

    def test_baseline_rows_present_after_migrations(self):
        AuthorityMappingLoader.load()
        assert AuthorityKeyEquivalence.objects.filter(
            from_key="irc:401", to_key="usc-26:401", source="baseline"
        ).exists()
        assert AuthorityKeyEquivalence.objects.filter(
            from_key="exchange-act:10", to_key="usc-15:78j", source="baseline"
        ).exists()
