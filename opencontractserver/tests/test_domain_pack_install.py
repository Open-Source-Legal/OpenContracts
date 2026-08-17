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
from unittest import mock

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.annotations.models import AuthorityKeyEquivalence
from opencontractserver.corpuses.management.commands.install_domain_pack import (
    Command as DomainPackCommand,
)
from opencontractserver.corpuses.models import Corpus, CorpusGroup

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

        # Installing a base pack MOVES its directory into the install dir, which
        # is a real path on the deployment. Redirect it per-test so a test run
        # never writes into the developer's actual pack cache.
        self.install_dir = self.root / "install-dir"
        override = override_settings(AUTHORITY_PACK_INSTALL_DIR=str(self.install_dir))
        override.enable()
        self.addCleanup(override.disable)

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
        """--check reports the plan without touching the database OR the disk.

        The filesystem half is not redundant. This test predates materialising,
        and installing now MOVES pack directories into the install dir — so
        "writes nothing" acquired a second meaning that nothing asserted. The C1
        preflight added later runs `load_authority_pack --check` per pack, which
        does not materialise; if it ever did, or if a future preflight reached
        for `materialise_pack` to get a stable path, `--check` would start
        moving packs out of the extraction tree while still printing "No changes
        were written".
        """
        out = self._run(self._standard_registry(), check=True)
        self.assertIn("No changes were written", out)
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())
        self.assertFalse(
            AgentConfiguration.objects.filter(slug="testdomain-orchestrator").exists()
        )
        self.assertFalse(
            self.install_dir.exists() and any(self.install_dir.iterdir()),
            "--check must not materialise anything into the install dir",
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

    # ---- installing a base pack is more than loading it ----------------- #
    def test_base_packs_are_materialised_into_the_install_dir(self):
        """A domain install must INSTALL its base packs, not merely load them.

        Loading writes the sections and the taxonomy to the database. But three
        things are read from the pack DIRECTORY at runtime, not from the
        database — ``source_hosts`` (unioned into the SSRF allowlist),
        ``shape_rules``/``abbreviations`` (the pack's citation vocabulary), and
        in-pack provider modules. The install dir is an implicit discovery root
        (``pipeline.registry.authority_pack_dirs``).

        Loading straight from the extraction temp dir therefore produced a pack
        that looked fully installed and had silently lost all three, with
        nothing failing at install time. Asserting on the database alone cannot
        see it, so this asserts on the filesystem.
        """
        self._run(self._standard_registry())
        landed = self.install_dir / "alpha"
        self.assertTrue(
            (landed / "pack.yaml").is_file(),
            "required base pack must be discoverable after install, not left "
            "in a temporary directory that is deleted on exit",
        )
        self.assertTrue((landed / "specs" / "alpha-one.json").is_file())

    def test_wiring_still_reads_pack_files_after_they_are_moved(self):
        """Materialising MOVES the pack; later reads must follow it.

        Regression guard for the obvious way to implement the fix: compute the
        group members from the staged path, then move the directory out from
        under it. The group would come out empty and the install would still
        report success.
        """
        self._run(self._standard_registry())
        self.assertEqual(
            CorpusGroup.objects.get(slug="test-group").corpora.count(),
            2,
            "group membership is derived from pack.yaml, which has moved",
        )

    # ---- --check must be able to fail ----------------------------------- #
    def test_check_fails_on_a_plan_that_would_violate_the_contract(self):
        """C5 — a preflight that cannot fail is worse than no preflight.

        The cap violation used to print an ERROR-styled line and return 0, so
        `--check` reported success for exactly the plan it exists to reject —
        and the real install then wrote every base pack before failing in the
        wiring.
        """
        tarball = self._standard_registry(
            equivalences=[{"from_key": "bb:1", "to_key": "zz:404"}]
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball, check=True)
        self.assertIn("C4", str(ctx.exception))
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())

    def test_unresolvable_equivalence_target_fails_before_any_write(self):
        """C4 — a row pointing at nothing is a no-op nobody would ever notice.

        The citation still extracts, still folds onto the target key, and still
        resolves to nothing. This was named in the module docstring as
        "re-checked here" and was not checked at all.
        """
        tarball = self._standard_registry(
            equivalences=[{"from_key": "bb:1", "to_key": "aa:999"}]
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("aa:999", str(ctx.exception))
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())
        self.assertFalse(
            (self.install_dir / "alpha").exists(),
            "C1/C5: nothing may be written when a file-decidable check fails",
        )

    def test_ungrantable_orchestrator_tool_is_refused(self):
        """C3 — 'if the platform cannot grant a declared tool, the install FAILS'.

        A misspelled tool name was previously stored verbatim on the agent. The
        agent then never calls it, which is indistinguishable from the model
        choosing not to — the failure mode C3 exists to make loud.
        """
        tarball = self._standard_registry(
            orchestrator={
                "instructions_file": "orchestrator.txt",
                "tools": ["search_across_corpora", "search_all_corpora"],
            }
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        message = str(ctx.exception)
        self.assertIn("C3", message)
        self.assertIn("search_all_corpora", message)

    def test_manifest_name_must_match_its_directory(self):
        """The instructions path is built from `name`, so `name` is a path input.

        The traversal guard derived its root from the same field it was
        guarding, so it moved with the attack and always passed: a manifest
        naming itself `../../../../etc` would read an arbitrary file into the
        orchestrator's system prompt.
        """
        self._base_pack("alpha", [("alpha-one", "aa", ["aa:1"])])
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "../../../../etc",
                "title": "T",
                "requires": [{"pack": "alpha", "reason": "r"}],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {
                    "instructions_file": "passwd",
                    "tools": ["search_across_corpora"],
                },
            },
            "use test-group",
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(self._tarball())
        self.assertIn("name", str(ctx.exception))
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())

    # ---- equivalences go through the shared, ownership-aware writer ------ #
    def test_a_curators_manual_row_is_never_clobbered(self):
        """Source ownership: the loader owns `baseline` and nothing else.

        The bare `update_or_create(from_key=...)` this replaced overwrote a
        curator's `manual` row AND relabelled it `baseline` — silently
        redirecting a mapping somebody had deliberately set.
        """
        AuthorityKeyEquivalence.objects.create(
            from_key="bb:1",
            to_key="aa:2",
            source="manual",
            created_by=self.owner,
        )
        self._run(self._standard_registry())

        rows = set(
            AuthorityKeyEquivalence.objects.filter(from_key="bb:1").values_list(
                "to_key", "source"
            )
        )
        self.assertIn(
            ("aa:2", "manual"),
            rows,
            "a manual row must survive a domain install untouched",
        )
        self.assertIn(("aa:1", "baseline"), rows, "the pack's own row still lands")

    def test_a_from_key_may_carry_more_than_one_target(self):
        """The unique constraint is on the PAIR, so one from_key may fan out.

        Keying the upsert on from_key alone raised MultipleObjectsReturned as
        soon as a second target existed — a crash mid-install, after the base
        packs were already written.
        """
        AuthorityKeyEquivalence.objects.create(
            from_key="bb:1", to_key="aa:2", source="baseline"
        )
        self._run(self._standard_registry())
        self.assertEqual(
            AuthorityKeyEquivalence.objects.filter(from_key="bb:1").count(),
            2,
            "both targets coexist; neither overwrites the other",
        )

    def test_present_but_invalid_base_pack_fails_before_any_write(self):
        """C1 says every required pack INSTALLS, not that its pack.yaml exists.

        Checking for the file is the adjacent measurement: a malformed pack
        passes it, then fails partway down the install loop with the packs
        before it already written. Preflighting each pack costs well under 1%
        of the install it guards, so there is no tradeoff to weigh.
        """
        tarball = self._standard_registry()
        # Rebuild the registry with alpha's spec corrupted.
        (self.root / "registry" / "alpha" / "specs" / "alpha-one.json").write_text(
            json.dumps({"sections": [{"heading": "no key", "text": "t"}]}),
            encoding="utf-8",
        )
        tarball = self._tarball()

        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("C1", str(ctx.exception))
        self.assertFalse(
            (self.install_dir / "alpha").exists(),
            "nothing may be materialised when a required pack would not install",
        )
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())

    # ---- manifest-supplied strings that become filesystem paths --------- #
    def test_requires_pack_name_must_be_a_plain_slug(self):
        """`requires[].pack` is a path component, and one of its uses is rmtree.

        The `name` field was guarded and this one was not — the same class of
        bug, one field over. `Path.__truediv__` does not collapse `..`, so
        `install_root / "../../../../var/lib/x"` resolves outside the install
        root, and `materialise_pack` deletes whatever is at `dest` before
        moving onto it.
        """
        self._base_pack("alpha", [("alpha-one", "aa", ["aa:1"])])
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "testdomain",
                "title": "T",
                "requires": [{"pack": "../../../../tmp/evil", "reason": "r"}],
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
        self.assertIn("slug", str(ctx.exception))

    def test_materialise_pack_refuses_a_traversing_name_itself(self):
        """The destructive primitive validates for itself.

        Callers are expected to check their input, but `materialise_pack` is
        where the rmtree lives, so it must not depend on every present and
        future caller having remembered.
        """
        from opencontractserver.corpuses.management.commands.install_authority_pack import (  # noqa: E501
            materialise_pack,
        )

        victim = self.root / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("must survive", encoding="utf-8")

        staged_pack = self.root / "staged-pack"
        staged_pack.mkdir()
        (staged_pack / "pack.yaml").write_text("name: x", encoding="utf-8")

        with self.assertRaises(CommandError):
            materialise_pack(staged_pack, f"../../{victim.name}")
        self.assertTrue(
            (victim / "keep.txt").is_file(), "a refused name must delete nothing"
        )

    def test_duplicate_requires_entries_do_not_half_install(self):
        """`pack_dirs` is a dict and deduped silently; the install loop did not.

        Naming a pack twice installed it, then failed on the second pass looking
        for a directory that had already been moved — with the first pack's
        corpora committed and the wiring never reached.
        """
        self._base_pack("alpha", [("alpha-one", "aa", ["aa:1"])])
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "testdomain",
                "title": "T",
                "requires": [
                    {"pack": "alpha", "reason": "r"},
                    {"pack": "alpha", "reason": "again"},
                ],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {
                    "instructions_file": "orchestrator.txt",
                    "tools": ["search_across_corpora"],
                },
            },
            "use test-group",
        )
        self._run(self._tarball())
        self.assertEqual(
            CorpusGroup.objects.get(slug="test-group").corpora.count(),
            1,
            "a pack named twice installs once and the wiring still lands",
        )

    def test_missing_corpus_group_slug_is_refused(self):
        """An absent slug used to create a group literally named 'None'.

        Every malformed domain pack would then converge onto that one group.
        """
        tarball = self._standard_registry(corpus_group={"title": "no slug here"})
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("corpus_group.slug", str(ctx.exception))
        self.assertFalse(CorpusGroup.objects.filter(slug="None").exists())

    def test_malformed_from_key_fails_before_any_write(self):
        """C4 checked that `to_key` RESOLVES and not that either key is WELL-FORMED.

        A `from_key` missing its colon is non-empty and differs from `to_key`, so
        it passed preflight and was rejected only at write time by
        `upsert_equivalence` — after every base pack had been installed. The
        sibling half of a check I had already written, missed the same way as
        the traversal guard.
        """
        tarball = self._standard_registry(
            equivalences=[{"from_key": "no-colon-here", "to_key": "aa:1"}]
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        message = str(ctx.exception)
        self.assertIn("C4", message)
        self.assertIn("canonical key", message)
        self.assertFalse(
            (self.install_dir / "alpha").exists(),
            "a file-decidable failure must not install anything first",
        )

    def test_unusable_preferred_llm_fails_before_any_write(self):
        """`AgentConfiguration.save()` raises Django's ValidationError, not CommandError.

        Nothing catches it, so a typo'd model spec installed every base pack and
        then surfaced as a bare traceback from inside the wiring — the one
        remaining path that produced a stack trace instead of a diagnosis.
        """
        tarball = self._standard_registry(
            orchestrator={
                "instructions_file": "orchestrator.txt",
                "tools": ["search_across_corpora"],
                "preferred_llm": "not-a-registered-provider:nope",
            }
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("preferred_llm", str(ctx.exception))
        self.assertFalse(
            (self.install_dir / "alpha").exists(),
            "the base packs must not be installed before this is caught",
        )

    def test_overlong_equivalence_note_fails_before_any_write(self):
        """`note` is CharField(255) and the shared upsert does not truncate.

        The bare `update_or_create` this replaced sliced the note to `[:255]`;
        switching to `upsert_equivalence` dropped that without replacing it, so
        an over-long note became a raw Postgres DataError raised mid-wiring,
        after every base pack was installed. Invisible in this pack's own data,
        whose longest note is 107 characters — which is exactly why it needs a
        test rather than an eyeball.

        Rejected rather than truncated: a silently shortened note no longer says
        what its author wrote.
        """
        tarball = self._standard_registry(
            equivalences=[{"from_key": "bb:1", "to_key": "aa:1", "note": "x" * 300}]
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("300 chars", str(ctx.exception))
        self.assertFalse((self.install_dir / "alpha").exists())

    def test_exclude_corpora_naming_an_unknown_corpus_is_refused(self):
        """An exclusion is a claim; one about nothing is a typo with consequences.

        The corpus the author meant to exclude silently stays in the group, and
        the group can then exceed the cap it was trimmed to fit.
        """
        tarball = self._standard_registry(
            corpus_group={
                "slug": "test-group",
                "title": "G",
                "exclude_corpora": ["alpha-tow"],  # typo for alpha-two
            }
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("alpha-tow", str(ctx.exception))

    def test_corpus_group_slug_must_be_a_slug(self):
        """The orchestrator names this in prose and passes it to the tool."""
        tarball = self._standard_registry(
            corpus_group={"slug": "Not A Slug", "title": "G"}
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("corpus_group.slug", str(ctx.exception))

    # ---- argument and manifest validation, before anything is staged ---- #
    def test_tarball_path_must_exist(self):
        """A --tarball pointing at nothing is refused before any fetch."""
        with self.assertRaises(CommandError) as ctx:
            self._run(str(self.root / "no-such-file.tar.gz"))
        self.assertIn("--tarball not found", str(ctx.exception))

    def test_no_domain_and_no_list_is_refused(self):
        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command("install_domain_pack", creator="domainowner", stdout=out)
        self.assertIn("Provide a domain name, or --list", str(ctx.exception))

    def test_invalid_domain_name_is_refused(self):
        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "install_domain_pack", "Not A Slug", creator="domainowner", stdout=out
            )
        self.assertIn("Invalid domain name", str(ctx.exception))

    def test_list_domains_lists_available_and_writes_nothing(self):
        tarball = self._standard_registry()
        out = StringIO()
        call_command(
            "install_domain_pack", tarball=tarball, list_domains=True, stdout=out
        )
        self.assertIn("testdomain", out.getvalue())
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())

    def test_domain_not_found_lists_whats_available(self):
        tarball = self._standard_registry()
        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "install_domain_pack",
                "nosuchdomain",
                tarball=tarball,
                creator="domainowner",
                stdout=out,
            )
        message = str(ctx.exception)
        self.assertIn("not found in registry", message)
        self.assertIn("testdomain", message)

    def test_manifest_name_not_equal_to_directory_is_refused(self):
        """Distinct from the traversal-guard test above: here `name` is a
        well-formed slug that simply differs from the directory it lives in.
        """
        self._base_pack("alpha", [("alpha-one", "aa", ["aa:1"])])
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "otherdomain",
                "title": "T",
                "requires": [{"pack": "alpha", "reason": "r"}],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {"instructions_file": "orchestrator.txt", "tools": []},
            },
            "test-group",
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(self._tarball())
        self.assertIn("does not match its directory", str(ctx.exception))

    def test_malformed_requires_entry_is_refused(self):
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "testdomain",
                "title": "T",
                "requires": ["alpha"],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {"instructions_file": "orchestrator.txt", "tools": []},
            },
            "test-group",
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(self._tarball())
        self.assertIn("malformed `requires` entry", str(ctx.exception))

    def test_empty_requires_is_refused(self):
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "testdomain",
                "title": "T",
                "requires": [],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {"instructions_file": "orchestrator.txt", "tools": []},
            },
            "test-group",
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(self._tarball())
        self.assertIn("declares no `requires`", str(ctx.exception))

    def test_creator_required_to_install(self):
        """A plain install missing --creator refuses cleanly, with no
        --check-flavoured preflight hint muddying the actual error.
        """
        tarball = self._standard_registry()
        out = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "install_domain_pack", "testdomain", tarball=tarball, stdout=out
            )
        self.assertIn("--creator is required to install", str(ctx.exception))
        self.assertNotIn("C1 pack validity not checked", out.getvalue())

    def test_check_without_creator_shows_the_c1_skip_notice(self):
        """--check without --creator still reports the plan; it says plainly
        that C1 (pack validity) was not evaluated rather than let a clean run
        imply it passed.
        """
        tarball = self._standard_registry()
        out = StringIO()
        call_command(
            "install_domain_pack",
            "testdomain",
            tarball=tarball,
            check=True,
            stdout=out,
        )
        self.assertIn("C1 pack validity not checked", out.getvalue())
        self.assertIn("No changes were written", out.getvalue())

    def test_check_report_shows_excluded_corpora(self):
        tarball = self._standard_registry(
            corpus_group={
                "slug": "test-group",
                "title": "G",
                "exclude_corpora": ["alpha-two"],
            }
        )
        out = self._run(tarball, check=True)
        self.assertIn("excluded", out)
        self.assertIn("alpha-two", out)

    # ---- staging: fetch path and the extraction size cap ----------------- #
    def test_stage_fetches_from_the_registry_url_when_no_tarball_is_given(self):
        """Without --tarball, the registry is fetched via --repo/--ref."""
        tarball = self._standard_registry()

        def fake_download(url, dest):
            Path(dest).write_bytes(Path(tarball).read_bytes())

        with mock.patch(
            "opencontractserver.corpuses.management.commands.install_domain_pack."
            "_download_tarball",
            side_effect=fake_download,
        ) as mocked:
            out = StringIO()
            call_command(
                "install_domain_pack",
                "testdomain",
                repo="https://example.invalid/registry.git",
                creator="domainowner",
                stdout=out,
            )
        mocked.assert_called_once()
        self.assertTrue(CorpusGroup.objects.filter(slug="test-group").exists())

    def test_stage_refuses_a_registry_that_expands_past_the_extraction_cap(self):
        tarball = self._standard_registry()
        with mock.patch(
            "opencontractserver.corpuses.management.commands.install_domain_pack."
            "MAX_EXTRACTED_BYTES",
            1,
        ):
            with self.assertRaises(CommandError) as ctx:
                self._run(tarball)
        self.assertIn("bytes; refusing", str(ctx.exception))

    # ---- a base pack failing the REAL install, after preflight passed ---- #
    def test_a_base_pack_failing_after_preflight_reports_whats_already_in(self):
        """Each base pack loads in its own transaction; the ones before a
        failure are installed and stay. The error must say so, and say the
        install converges on re-run — the bare error from
        `load_authority_pack` cannot tell an operator a partial install from
        a no-op.
        """
        self._base_pack("alpha", [("alpha-one", "aa", ["aa:1"])])
        self._base_pack("beta", [("beta-one", "cc", ["cc:1"])])
        self._domain(
            "testdomain",
            {
                "schema_version": 1,
                "name": "testdomain",
                "title": "T",
                "requires": [
                    {"pack": "alpha", "reason": "r"},
                    {"pack": "beta", "reason": "r"},
                ],
                "corpus_group": {"slug": "test-group", "title": "G"},
                "orchestrator": {"instructions_file": "orchestrator.txt", "tools": []},
            },
            "test-group",
        )
        tarball = self._tarball()
        real_call_command = call_command

        def flaky(name, *args, **kwargs):
            if (
                name == "load_authority_pack"
                and not kwargs.get("check")
                and str(kwargs.get("path", "")).endswith("beta")
            ):
                raise CommandError("beta exploded")
            return real_call_command(name, *args, **kwargs)

        with mock.patch(
            "opencontractserver.corpuses.management.commands.install_domain_pack."
            "call_command",
            side_effect=flaky,
        ):
            with self.assertRaises(CommandError) as ctx:
                self._run(tarball)
        message = str(ctx.exception)
        self.assertIn("beta", message)
        self.assertIn("already installed and left in place: alpha", message)
        self.assertIn("installs converge", message)
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())
        self.assertTrue(
            (self.install_dir / "alpha").exists(),
            "the pack that actually installed must stay in place",
        )
        self.assertFalse(
            (self.install_dir / "beta").exists(),
            "a pack that materialised but never loaded must not leave its "
            "source_hosts live in the SSRF-allowlist discovery root",
        )

    # ---- pack.yaml is registry-authored, not domain-pack-authored, but an
    # installer must not trust ANY of its input -------------------------- #
    def test_member_slugs_rejects_a_malformed_corpus_entry(self):
        pack_dir = self.root / "malformed-pack"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump({"name": "malformed-pack", "corpora": ["not-a-dict"]}),
            encoding="utf-8",
        )
        with self.assertRaises(CommandError) as ctx:
            DomainPackCommand()._member_slugs({"malformed-pack": pack_dir}, {})
        self.assertIn("malformed corpus entry", str(ctx.exception))

    def test_section_keys_rejects_a_malformed_corpus_entry(self):
        """The sibling check in `_section_keys` — same defect, different method."""
        pack_dir = self.root / "malformed-pack-2"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump({"name": "malformed-pack-2", "corpora": ["not-a-dict"]}),
            encoding="utf-8",
        )
        with self.assertRaises(CommandError) as ctx:
            DomainPackCommand()._section_keys({"malformed-pack-2": pack_dir})
        self.assertIn("malformed corpus entry", str(ctx.exception))

    def test_section_keys_skips_entries_it_cannot_read(self):
        """A corpus with no spec, a missing spec file, or unparsable JSON is
        skipped rather than crashing the C4 preflight — only a well-formed
        spec contributes keys.
        """
        pack_dir = self.root / "partial-pack"
        (pack_dir / "specs").mkdir(parents=True)
        (pack_dir / "specs" / "good.json").write_text(
            json.dumps({"sections": [{"key": "gp:1"}]}), encoding="utf-8"
        )
        (pack_dir / "specs" / "bad.json").write_text("not json{{{", encoding="utf-8")
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "partial-pack",
                    "corpora": [
                        {"slug": "no-spec"},
                        {"slug": "missing-file", "spec": "specs/missing.json"},
                        {"slug": "bad-json", "spec": "specs/bad.json"},
                        {"slug": "good", "spec": "specs/good.json"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        keys = DomainPackCommand()._section_keys({"partial-pack": pack_dir})
        self.assertEqual(keys, {"gp:1"})

    # ---- `_wire`'s own backstops, reached directly since `_preflight` -----
    # normally catches these first (see the comments on each guard) ------- #
    def test_wire_reports_a_corpus_never_created_by_its_base_pack(self):
        pack_dir = self.root / "orphan-pack"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(
                {"name": "orphan-pack", "corpora": [{"slug": "ghost-corpus"}]}
            ),
            encoding="utf-8",
        )
        domain_dir = self.root / "registry" / "domains" / "testdomain"
        domain_dir.mkdir(parents=True)
        (domain_dir / "orchestrator.txt").write_text("hi", encoding="utf-8")
        manifest = {
            "name": "testdomain",
            "corpus_group": {"slug": "ghost-group", "title": "G"},
            "orchestrator": {"instructions_file": "orchestrator.txt", "tools": []},
            "equivalences": [],
        }
        options = {"creator": "domainowner", "public": False, "check": False}
        with self.assertRaises(CommandError) as ctx:
            DomainPackCommand(stdout=StringIO())._wire(
                manifest, {"orphan-pack": pack_dir}, domain_dir, options
            )
        message = str(ctx.exception)
        self.assertIn("ghost-corpus", message)
        self.assertIn("was not created by its base pack", message)
        self.assertFalse(CorpusGroup.objects.filter(slug="ghost-group").exists())

    def test_wire_still_refuses_an_over_cap_group_if_preflight_is_bypassed(self):
        """Defense in depth: named in the code's own comment as unreachable
        while `_preflight` runs first — kept so a future refactor that widens
        membership in `_wire` without touching `_preflight` still cannot
        silently truncate the group.
        """
        from opencontractserver.constants.tools import (
            MULTI_CORPUS_SEARCH_MAX_CORPORA,
        )

        over = MULTI_CORPUS_SEARCH_MAX_CORPORA + 1
        slugs = [f"cap-{i}" for i in range(over)]
        for slug in slugs:
            Corpus.objects.create(title=slug, slug=slug, creator=self.owner)

        pack_dir = self.root / "cap-pack"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(
                {"name": "cap-pack", "corpora": [{"slug": s} for s in slugs]}
            ),
            encoding="utf-8",
        )
        domain_dir = self.root / "registry" / "domains" / "capdomain"
        domain_dir.mkdir(parents=True)
        (domain_dir / "orchestrator.txt").write_text("hi", encoding="utf-8")
        manifest = {
            "name": "capdomain",
            "corpus_group": {"slug": "cap-group", "title": "G"},
            "orchestrator": {"instructions_file": "orchestrator.txt", "tools": []},
            "equivalences": [],
        }
        options = {"creator": "domainowner", "public": False, "check": False}
        with self.assertRaises(CommandError) as ctx:
            DomainPackCommand(stdout=StringIO())._wire(
                manifest, {"cap-pack": pack_dir}, domain_dir, options
            )
        message = str(ctx.exception)
        self.assertIn("C2", message)
        self.assertIn("silently drop", message)
        self.assertFalse(CorpusGroup.objects.filter(slug="cap-group").exists())

    # ---- wiring: the orchestrator's instructions file and preferred_llm -- #
    def test_unreadable_instructions_file_fails_wiring(self):
        tarball = self._standard_registry(
            orchestrator={"instructions_file": "does-not-exist.txt", "tools": []}
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("instructions_file unreadable", str(ctx.exception))
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())

    def test_valid_preferred_llm_is_applied_to_the_orchestrator(self):
        tarball = self._standard_registry(
            orchestrator={
                "instructions_file": "orchestrator.txt",
                "tools": ["search_across_corpora"],
                "preferred_llm": "gpt-4o",
            }
        )
        self._run(tarball)
        agent = AgentConfiguration.objects.get(slug="testdomain-orchestrator")
        self.assertEqual(agent.preferred_llm, "openai:gpt-4o")

    # ---- the shared, ownership-aware equivalence writer, from this side -- #
    def test_matching_manual_row_is_skipped_not_recreated(self):
        AuthorityKeyEquivalence.objects.create(
            from_key="bb:1", to_key="aa:1", source="manual", created_by=self.owner
        )
        out = self._run(self._standard_registry())
        self.assertIn("left to their existing owner", out)
        row = AuthorityKeyEquivalence.objects.get(from_key="bb:1", to_key="aa:1")
        self.assertEqual(row.source, "manual")

    def test_writer_rejection_after_preflight_passed_is_reported_not_swallowed(self):
        """Defensive: if the writer's validity check ever diverges from
        preflight's own, that divergence must surface as an unmet assertion
        rather than a silent skip counted as a clean install.
        """
        from opencontractserver.enrichment.services.authority_equivalence_ingest import (  # noqa: E501
            SKIPPED_INVALID,
        )

        tarball = self._standard_registry()
        with mock.patch(
            "opencontractserver.enrichment.services.authority_equivalence_ingest."
            "upsert_equivalence",
            return_value=SKIPPED_INVALID,
        ):
            with self.assertRaises(CommandError) as ctx:
                self._run(tarball)
        message = str(ctx.exception)
        self.assertIn("rejected by the shared upsert after passing preflight", message)
        self.assertFalse(CorpusGroup.objects.filter(slug="test-group").exists())

    # ---- equivalence-row shape validation (C4) ---------------------------- #
    def test_malformed_equivalence_row_is_refused(self):
        tarball = self._standard_registry(equivalences=["not-a-dict"])
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("malformed equivalence row", str(ctx.exception))

    def test_equivalence_row_missing_a_key_is_refused(self):
        tarball = self._standard_registry(equivalences=[{"to_key": "aa:1"}])
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("malformed equivalence row", str(ctx.exception))

    def test_equivalence_row_mapping_onto_itself_is_refused(self):
        tarball = self._standard_registry(
            equivalences=[{"from_key": "aa:1", "to_key": "aa:1"}]
        )
        with self.assertRaises(CommandError) as ctx:
            self._run(tarball)
        self.assertIn("onto itself", str(ctx.exception))

    def test_equivalence_key_whitespace_is_stripped_before_validation(self):
        """Preflight validates the same stripped value `upsert_equivalence`
        writes. Without stripping first, a manifest row with incidental
        whitespace (an easy slip in YAML block-scalar indentation) fails
        preflight's `is_valid_canonical_key` — which anchors at the start of
        the string — even though the writer would have accepted it.
        """
        tarball = self._standard_registry(
            equivalences=[{"from_key": " bb:1 ", "to_key": "aa:1", "note": "n"}]
        )
        self._run(tarball)
        self.assertTrue(
            AuthorityKeyEquivalence.objects.filter(
                from_key="bb:1", to_key="aa:1"
            ).exists()
        )

    # ---- the authority-pack-loader guard `materialise_pack` owns itself -- #
    def test_materialise_pack_refuses_a_pack_missing_its_manifest(self):
        """The pack.yaml guard inside `materialise_pack` itself, not just its
        caller's own pre-check — the guard that fires if that promise from a
        caller is ever broken.
        """
        from opencontractserver.corpuses.management.commands.install_authority_pack import (  # noqa: E501
            materialise_pack,
        )

        staged_pack = self.root / "pack-without-manifest"
        staged_pack.mkdir()

        with self.assertRaises(CommandError) as ctx:
            materialise_pack(staged_pack, "pack-without-manifest")
        self.assertIn("missing pack.yaml", str(ctx.exception))
