"""The sideload contract: how an install finds packs that are not in the tree.

The product tree ships one worked example pack. A body of regulation a
deployment actually curates is *its* data, versioned on its own cadence, and
reaches the install through ``AUTHORITY_PACK_ROOTS`` (a directory of packs — one
variable per pack repository) or ``AUTHORITY_PACK_PATHS`` (one entry per pack).
These tests pin discovery, precedence, de-duplication, and the command-line
preflight an operator runs before installing something they did not build.
"""

from __future__ import annotations

import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from opencontractserver.corpuses.models import Corpus
from opencontractserver.pipeline.registry import _pack_namespaces, authority_pack_dirs

User = get_user_model()

FIXTURE_PACK = (
    Path(__file__).resolve().parent / "fixtures" / "authority_packs" / "example_utility"
)


class AuthorityPackDiscoveryTests(TestCase):
    """``authority_pack_dirs()`` — what an install considers installed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bundle = Path(self.tmp.name) / "bundle"
        self.bundle.mkdir()
        for name in ("alpha_pack", "beta_pack"):
            shutil.copytree(FIXTURE_PACK, self.bundle / name)
        # A stray file beside the packs must not be mistaken for one.
        (self.bundle / "README.md").write_text("not a pack", encoding="utf-8")

    def test_in_tree_root_ships_only_the_example_pack(self):
        """The product tree carries an example, not a jurisdiction's data.

        A pack added here is installed on every deployment, offered in every
        Authority Console catalog, and has its providers imported by every
        worker. That is a deliberate, reviewable decision — not somewhere real
        regulatory corpora should accumulate.
        """
        with override_settings(AUTHORITY_PACK_ROOTS=[], AUTHORITY_PACK_PATHS=[]):
            in_tree = {path.name for path in authority_pack_dirs()}
        self.assertEqual(in_tree, {"bolivia"})

    def test_a_root_mounts_every_pack_beneath_it(self):
        with override_settings(
            AUTHORITY_PACK_ROOTS=[str(self.bundle)], AUTHORITY_PACK_PATHS=[]
        ):
            found = authority_pack_dirs()
        names = [path.name for path in found]
        self.assertEqual(names[0], "bolivia", "in-tree packs come first")
        self.assertEqual(set(names[1:]), {"alpha_pack", "beta_pack"})

    def test_a_pack_reachable_twice_is_registered_once(self):
        """Overlapping settings must not double-register a pack.

        Both entries resolve to the same directory, and provider modules are
        imported under a name generated from the pack directory — registering
        it twice would import the same providers under the same module name and
        trip the duplicate-prefix warnings.
        """
        with override_settings(
            AUTHORITY_PACK_ROOTS=[str(self.bundle)],
            AUTHORITY_PACK_PATHS=[str(self.bundle / "alpha_pack")],
        ):
            found = authority_pack_dirs()
        resolved = [path.resolve() for path in found]
        self.assertEqual(len(resolved), len(set(resolved)))
        self.assertEqual(
            sum(path.name == "alpha_pack" for path in found),
            1,
        )

    def test_two_packs_sharing_a_basename_get_distinct_namespaces(self):
        """Different packs may legitimately share a directory basename.

        ``authority_pack_dirs()`` de-duplicates by RESOLVED PATH, so the same
        basename under two different roots yields two entries — the sibling of
        ``test_a_pack_reachable_twice_is_registered_once``, which covers the
        same path reached twice. The synthetic import namespace is derived from
        that basename, so without a guard both import under
        ``_authority_pack.alpha_pack`` and the second re-points the first's
        package at its own directory, silently swapping which code a provider
        name resolves to (and with it the ``__module__``-based host-ownership
        checks). ``AuthorityPackService.catalog`` keys its duplicate check on
        the manifest ``name`` field, so it does not catch this.
        """
        other_bundle = Path(self.tmp.name) / "other_bundle"
        other_bundle.mkdir()
        shutil.copytree(FIXTURE_PACK, other_bundle / "alpha_pack")

        with override_settings(
            AUTHORITY_PACK_ROOTS=[str(self.bundle), str(other_bundle)],
            AUTHORITY_PACK_PATHS=[],
        ):
            found = authority_pack_dirs()

        self.assertEqual(
            sum(path.name == "alpha_pack" for path in found),
            2,
            "both same-named packs must be discovered",
        )
        namespaces = _pack_namespaces(found)
        self.assertEqual(
            len(set(namespaces.values())),
            len(found),
            "every pack directory must map to its own module namespace",
        )
        # A pack whose basename is unique keeps the plain, readable name.
        beta = next(path for path in found if path.name == "beta_pack")
        self.assertEqual(namespaces[beta], "beta_pack")
        # Derived from the path alone, so reset_registry() re-discovery keeps a
        # pack on the same namespace instead of orphaning its cached modules.
        self.assertEqual(namespaces, _pack_namespaces(found))

    def test_a_misconfigured_entry_is_skipped_not_raised(self):
        """A bad path must not take down worker boot or the registry build."""
        with override_settings(
            AUTHORITY_PACK_ROOTS=["/nonexistent/bundle"],
            AUTHORITY_PACK_PATHS=["/nonexistent/pack"],
        ):
            found = authority_pack_dirs()
        self.assertEqual({path.name for path in found}, {"bolivia"})

    def test_a_root_entry_that_is_a_pack_contributes_nothing(self):
        """A root is a directory *of* packs; pointing it at a pack is a typo.

        The pack's own subdirectories (``charters/``, ``specs/``…) are not
        packs, so they must not be mounted as such — the operator gets an empty
        result and a catalog that visibly lacks the pack, rather than four
        malformed entries.
        """
        with override_settings(
            AUTHORITY_PACK_ROOTS=[str(self.bundle / "alpha_pack")],
            AUTHORITY_PACK_PATHS=[],
        ):
            found = [path.name for path in authority_pack_dirs()]
        self.assertNotIn("charters", found)
        self.assertNotIn("specs", found)


class AuthorityPackPreflightCommandTests(TestCase):
    """``load_authority_pack --check`` — validate before installing."""

    def setUp(self):
        self.operator = User.objects.create_user(
            username="sideload-operator",
            is_usage_capped=False,
        )

    def _check(self, path: Path) -> str:
        stdout = StringIO()
        call_command(
            "load_authority_pack",
            path=str(path),
            creator=self.operator.username,
            check=True,
            stdout=stdout,
        )
        return stdout.getvalue()

    def test_check_reports_the_plan_and_writes_nothing(self):
        output = self._check(FIXTURE_PACK)

        self.assertIn("example_utility", output)
        self.assertIn("example-utility-statutes", output)
        self.assertIn("example-utility-proceedings", output)
        self.assertIn("No changes were written", output)
        self.assertFalse(
            Corpus.objects.filter(
                slug__in=[
                    "example-utility-statutes",
                    "example-utility-proceedings",
                ]
            ).exists()
        )

    def test_check_fails_on_an_invalid_pack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir)
            (pack_dir / "pack.yaml").write_text(
                "schema_version: 2\nname: broken\ncorpora: []\n",
                encoding="utf-8",
            )
            with self.assertRaises(CommandError):
                self._check(pack_dir)
