"""Domain-pack install: the contract, exercised.

A domain pack composes base packs and supplies the wiring that belongs to none
of them — a corpus group, an orchestrator, and cross-pack equivalences. These
tests assert the install contract (see the registry repo's DOMAIN_PACKS.md),
because the failure this layer exists to prevent is an install that reports
success while leaving the assembly unreachable.

Each test names the assertion it covers.
"""

from __future__ import annotations

import json
import tarfile
import tempfile
from io import StringIO
from pathlib import Path

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.corpuses.models import CorpusGroup

User = get_user_model()


class DomainPackInstallTests(TestCase):
    """Synthetic registries, built per-test, exercising each contract clause."""

    def setUp(self):
        # is_usage_capped=False: the cap test installs one corpus per allowed
        # group member, and the default per-user document cap (10) would trip
        # first — a fixture artefact unrelated to any assertion under test.
        self.owner = User.objects.create_user(
            username="domainowner", password="p", is_usage_capped=False
        )
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    # ---- fixture helpers ------------------------------------------------ #
    def _base_pack(self, name: str, corpora: list[tuple[str, str, list[str]]]) -> None:
        """corpora: [(corpus_slug, prefix, [section_keys])]"""
        pack = self.root / "registry" / name
        (pack / "specs").mkdir(parents=True, exist_ok=True)
        (pack / "personas").mkdir(parents=True, exist_ok=True)
        (pack / "charters").mkdir(parents=True, exist_ok=True)
        entries = []
        for slug, prefix, keys in corpora:
            spec_rel = f"specs/{slug}.json"
            (pack / spec_rel).write_text(
                json.dumps(
                    {
                        "sections": [
                            {
                                "key": k,
                                "heading": f"H {k}",
                                "text": f"Body of {k}.",
                                "source_url": "https://example.gov/",
                            }
                            for k in keys
                        ]
                    }
                ),
                encoding="utf-8",
            )
            persona_rel = f"personas/{slug}.txt"
            (pack / persona_rel).write_text(f"You are {slug}.", encoding="utf-8")
            charter_rel = f"charters/{slug}.yaml"
            (pack / charter_rel).write_text(
                yaml.safe_dump(
                    {
                        "title": f"Corpus {slug}",
                        "slug": slug,
                        "purpose": f"Test corpus {slug}.",
                        "include": ["test sections"],
                        "exclude": ["everything else"],
                        "authority_tiers": {"default": "IMPLEMENTING"},
                        "approval_status": "harvested_unreviewed",
                    }
                ),
                encoding="utf-8",
            )
            entries.append(
                {
                    "slug": slug,
                    "title": f"Corpus {slug}",
                    "authority_prefixes": [prefix],
                    "spec": spec_rel,
                    "persona": persona_rel,
                    "charter": charter_rel,
                    "default_authority_weight": "IMPLEMENTING",
                }
            )
        (pack / "authority_mappings.yaml").write_text(
            yaml.safe_dump(
                {
                    "prefixes": {
                        prefix: {
                            "name": f"{prefix} authority",
                            "authority_type": "regulation",
                            "jurisdiction": "us",
                        }
                        for _, prefix, _ in corpora
                    },
                    "equivalences": [],
                    "rewrite_rules": [],
                }
            ),
            encoding="utf-8",
        )
        (pack / "pack.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": name,
                    "schema_version": 2,
                    "jurisdiction": "us",
                    "mappings": "authority_mappings.yaml",
                    "corpora": entries,
                }
            ),
            encoding="utf-8",
        )

    def _domain(self, name: str, manifest: dict, instructions: str) -> None:
        d = self.root / "registry" / "domains" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "orchestrator.txt").write_text(instructions, encoding="utf-8")
        (d / "domain.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    def _tarball(self) -> str:
        path = self.root / "registry.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            tar.add(self.root / "registry", arcname="registry-main")
        return str(path)

    def _standard_registry(self, **domain_overrides) -> str:
        self._base_pack(
            "alpha",
            [("alpha-one", "aa", ["aa:1", "aa:2"]), ("alpha-two", "bb", ["bb:1"])],
        )
        manifest = {
            "schema_version": 1,
            "name": "testdomain",
            "title": "Test domain",
            "requires": [{"pack": "alpha", "reason": "because"}],
            "corpus_group": {"slug": "test-group", "title": "Test group"},
            "orchestrator": {
                "instructions_file": "orchestrator.txt",
                "tools": ["search_across_corpora"],
            },
            "equivalences": [
                {"from_key": "bb:1", "to_key": "aa:1", "note": "shared title"}
            ],
        }
        manifest.update(domain_overrides)
        self._domain(
            "testdomain",
            manifest,
            "Call search_across_corpora with corpus_group=test-group.",
        )
        return self._tarball()

    def _run(self, tarball: str, **extra) -> str:
        out = StringIO()
        call_command(
            "install_domain_pack",
            "testdomain",
            tarball=tarball,
            creator="domainowner",
            stdout=out,
            **extra,
        )
        return out.getvalue()

    # ---- the contract --------------------------------------------------- #
    def test_installs_group_orchestrator_and_equivalences(self):
        """C2/C3/C4 — the wiring a domain pack exists to supply is created."""
        out = self._run(self._standard_registry())

        group = CorpusGroup.objects.get(slug="test-group")
        self.assertEqual(
            sorted(group.corpora.values_list("slug", flat=True)),
            ["alpha-one", "alpha-two"],
            "C2: every corpus contributed by a required base pack joins the group",
        )
        agent = AgentConfiguration.objects.get(slug="testdomain-orchestrator")
        self.assertEqual(group.default_agent_id, agent.pk, "C3: orchestrator bound")
        self.assertIn("search_across_corpora", agent.available_tools)
        self.assertIn("test-group", agent.system_instructions)
        self.assertTrue(
            AuthorityKeyEquivalence.objects.filter(
                from_key="bb:1", to_key="aa:1"
            ).exists(),
            "C4: the cross-pack equivalence is written",
        )
        self.assertIn("installed", out.lower())

    def test_check_writes_nothing(self):
        """--check reports the plan without touching the database."""
        out = self._run(self._standard_registry(), check=True)
        self.assertIn("No changes were written", out)
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())
        self.assertFalse(
            AgentConfiguration.objects.filter(slug="testdomain-orchestrator").exists()
        )

    def test_install_is_idempotent(self):
        """C6 — re-running converges; nothing is duplicated."""
        tarball = self._standard_registry()
        self._run(tarball)
        self._run(tarball)
        self.assertEqual(CorpusGroup.objects.filter(slug="test-group").count(), 1)
        self.assertEqual(
            AgentConfiguration.objects.filter(slug="testdomain-orchestrator").count(), 1
        )
        self.assertEqual(
            AuthorityKeyEquivalence.objects.filter(from_key="bb:1").count(), 1
        )
        self.assertEqual(CorpusGroup.objects.get(slug="test-group").corpora.count(), 2)

    def test_missing_base_pack_fails_before_writing(self):
        """C1 — a partial install that reports success is the failure to prevent."""
        tarball = self._standard_registry(
            requires=[{"pack": "nonexistent", "reason": "x"}]
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("C1", str(ctx.exception))
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())

    def test_orchestrator_that_never_names_the_group_slug_fails(self):
        """C3 — corpus_group is a REQUIRED tool argument.

        An agent that is never told the slug cannot call the tool, and that
        failure is indistinguishable from the model choosing not to call it —
        so it has to be caught at install, not observed later as bad answers.
        """
        self._base_pack("alpha", [("alpha-one", "aa", ["aa:1"])])
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "testdomain",
                "title": "T",
                "requires": [{"pack": "alpha", "reason": "r"}],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {
                    "instructions_file": "orchestrator.txt",
                    "tools": ["search_across_corpora"],
                },
            },
            "Search broadly. (never names the group)",
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(self._tarball())
        self.assertIn("C3", str(ctx.exception))
        # The rollback is the point: no half-wired group survives.
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())

    def test_domain_declaring_authority_is_refused(self):
        """C7 — authority belongs to a base pack, where its provenance lives."""
        self._base_pack("alpha", [("alpha-one", "aa", ["aa:1"])])
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "testdomain",
                "title": "T",
                "requires": [{"pack": "alpha", "reason": "r"}],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {"instructions_file": "orchestrator.txt", "tools": []},
                "prefixes": {"zz": {"name": "smuggled"}},
            },
            "test-group",
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(self._tarball())
        self.assertIn("C7", str(ctx.exception))

    def test_group_over_platform_cap_is_an_error_not_a_truncation(self):
        """C2 — exceeding the cap must fail loudly.

        search_across_corpora searches the first N corpora BY ID and logs a
        warning, which silently drops the most recently added — a corpus is
        excluded precisely because it is new. Truncating here would reproduce
        that in the installer.
        """
        from opencontractserver.constants.tools import MULTI_CORPUS_SEARCH_MAX_CORPORA

        over = MULTI_CORPUS_SEARCH_MAX_CORPORA + 1
        self._base_pack("alpha", [(f"c{i}", f"p{i}", [f"p{i}:1"]) for i in range(over)])
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "testdomain",
                "title": "T",
                "requires": [{"pack": "alpha", "reason": "r"}],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {
                    "instructions_file": "orchestrator.txt",
                    "tools": ["search_across_corpora"],
                },
            },
            "use test-group",
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(self._tarball())
        message = str(ctx.exception)
        self.assertIn("C2", message)
        self.assertIn("silently drop", message)

    def test_excluded_corpora_are_left_out_of_the_group(self):
        """exclude_corpora is a claim that a corpus is reachable another way."""
        tarball = self._standard_registry(
            corpus_group={
                "slug": "test-group",
                "title": "G",
                "exclude_corpora": ["alpha-two"],
            }
        )
        self._run(tarball)
        self.assertEqual(
            list(
                CorpusGroup.objects.get(slug="test-group").corpora.values_list(
                    "slug", flat=True
                )
            ),
            ["alpha-one"],
        )
