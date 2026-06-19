import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityKeyEquivalence
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
        assert summary["skipped_manual"] == 1
        row = AuthorityKeyEquivalence.objects.get(
            from_key=_FIXTURE_FROM, to_key=_FIXTURE_TO
        )
        assert row.source == "manual"
        assert row.note == "curator"

    def test_rejects_malformed_key(self):
        path = _write_yaml(
            'equivalences:\n  - {from_key: "garbage", to_key: "usc-26:401"}\n'
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
            "skipped_manual": 0,
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
        assert summary["skipped_manual"] == 1
        row = AuthorityKeyEquivalence.objects.get(
            from_key="test-act:2", to_key="usc-99:2"
        )
        assert row.source == "manual"
        assert row.note == "curator override"


class LoadAuthorityMappingsCommandTests(TestCase):
    def test_command_loads_baseline(self):
        out = StringIO()
        call_command("load_authority_mappings", stdout=out)
        assert AuthorityKeyEquivalence.objects.filter(
            from_key="irc:401", to_key="usc-26:401"
        ).exists()
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
