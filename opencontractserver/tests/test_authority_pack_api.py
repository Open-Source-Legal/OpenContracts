"""Service and GraphQL tests for the trusted authority-pack install surface."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    AuthorityNamespace,
    AuthorityRelationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment.services.authority_pack_service import (
    CONCURRENT_INSTALL_MESSAGE,
    AuthorityPackCorpusPlan,
    AuthorityPackService,
)
from opencontractserver.enrichment.services.authority_permissions import DENIED

User = get_user_model()


class AuthorityPackAPITests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="pack-admin",
            is_superuser=True,
            is_staff=True,
            is_usage_capped=False,
        )
        self.regular = User.objects.create_user(username="pack-reader")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.pack_dir = Path(self.temp_dir.name) / "portable_pack"
        self._write_pack()

    def _write_pack(
        self,
        *,
        approval_status: str = "pending_legal_review",
        text: str = "Trusted sideload placeholder.",
    ) -> None:
        self.pack_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": 2,
            "name": "portable_test_pack",
            "display_name": "Portable Test Pack",
            "description": "A small portable authority-pack fixture.",
            "jurisdiction": "test",
            "corpora": [
                {
                    "slug": "portable-test-corpus",
                    "title": "Portable Test Corpus",
                    "description": "Install target for a later corpus sideload.",
                    "charter": "charter.yaml",
                    "spec": "sections.json",
                }
            ],
        }
        (self.pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(manifest), encoding="utf-8"
        )
        (self.pack_dir / "charter.yaml").write_text(
            yaml.safe_dump(
                {
                    "purpose": "Provide a stable corpus target.",
                    "approval_status": approval_status,
                }
            ),
            encoding="utf-8",
        )
        (self.pack_dir / "sections.json").write_text(
            json.dumps(
                {
                    "sections": [
                        {
                            "key": "portable-test:1",
                            "heading": "Portable placeholder",
                            "text": text,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def _configured_catalog(self):
        return mock.patch(
            "opencontractserver.enrichment.services.authority_pack_service."
            "authority_pack_dirs",
            return_value=[self.pack_dir],
        )

    @staticmethod
    def _context(user):
        return SimpleNamespace(user=user)

    def test_non_admin_is_denied_before_catalog_discovery(self):
        with mock.patch(
            "opencontractserver.enrichment.services.authority_pack_service."
            "authority_pack_dirs",
            side_effect=AssertionError("non-admin must not inspect configured packs"),
        ):
            self.assertEqual(AuthorityPackService.catalog(self.regular), [])
            self.assertIsNone(
                AuthorityPackService.preflight(self.regular, "portable_test_pack")
            )
            result = AuthorityPackService.install(
                self.regular,
                pack_id="portable_test_pack",
                expected_fingerprint="sha256:not-visible",
                relink=False,
            )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, DENIED)

        query = schema.execute_sync(
            """
            {
              authorityPacks { id }
              authorityPackPreflight(packId: "portable_test_pack") { id }
            }
            """,
            context_value=self._context(self.regular),
        )
        self.assertIsNone(query.errors)
        self.assertEqual(query.data["authorityPacks"], [])
        self.assertIsNone(query.data["authorityPackPreflight"])

    def test_catalog_is_dynamic_and_preflight_performs_zero_writes(self):
        configured: list[Path] = []
        with mock.patch(
            "opencontractserver.enrichment.services.authority_pack_service."
            "authority_pack_dirs",
            return_value=configured,
        ):
            self.assertEqual(AuthorityPackService.catalog(self.admin), [])
            configured.append(self.pack_dir)

            before = (
                Corpus.objects.count(),
                Document.objects.count(),
                AuthorityNamespace.objects.count(),
                AuthorityRelationship.objects.count(),
            )
            catalog = AuthorityPackService.catalog(self.admin)
            preflight = AuthorityPackService.preflight(self.admin, "portable_test_pack")
            after = (
                Corpus.objects.count(),
                Document.objects.count(),
                AuthorityNamespace.objects.count(),
                AuthorityRelationship.objects.count(),
            )

        self.assertEqual(before, after)
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].pack_id, "portable_test_pack")
        self.assertTrue(catalog[0].valid)
        self.assertTrue(catalog[0].can_install)
        self.assertFalse(catalog[0].can_publish)
        self.assertEqual(catalog[0].approval_status, "pending_legal_review")
        self.assertIsNotNone(preflight)
        self.assertEqual(preflight.fingerprint, catalog[0].fingerprint)
        self.assertEqual(preflight.installed_count, 0)
        self.assertIsNone(preflight.corpora[0].corpus_id)

    def test_changed_pack_rejects_stale_fingerprint_without_writes(self):
        with self._configured_catalog():
            preflight = AuthorityPackService.preflight(self.admin, "portable_test_pack")
            self.assertIsNotNone(preflight)
            self._write_pack(text="Changed after the administrator reviewed it.")
            result = AuthorityPackService.install(
                self.admin,
                pack_id="portable_test_pack",
                expected_fingerprint=preflight.fingerprint,
                relink=False,
            )

        self.assertFalse(result.ok)
        self.assertIn("changed after preflight", result.error)
        self.assertFalse(
            Corpus.objects.filter(
                creator=self.admin, slug="portable-test-corpus"
            ).exists()
        )
        self.assertFalse(Document.objects.filter(creator=self.admin).exists())

    def test_graphql_installs_privately_and_returns_global_corpus_id(self):
        with self._configured_catalog():
            preflight = AuthorityPackService.preflight(self.admin, "portable_test_pack")
            self.assertIsNotNone(preflight)
            result = schema.execute_sync(
                """
                mutation Install(
                  $packId: String!
                  $fingerprint: String!
                ) {
                  installAuthorityPack(
                    packId: $packId
                    expectedFingerprint: $fingerprint
                    publish: false
                  ) {
                    ok
                    message
                    result
                    pack {
                      id
                      installed
                      fullyPublic
                      corpora {
                        corpusId
                        installed
                        isPublic
                      }
                    }
                  }
                }
                """,
                variable_values={
                    "packId": "portable_test_pack",
                    "fingerprint": preflight.fingerprint,
                },
                context_value=self._context(self.admin),
            )

        self.assertIsNone(result.errors)
        payload = result.data["installAuthorityPack"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "Authority pack installed privately.")
        self.assertEqual(payload["result"]["corpora"], 1)
        self.assertTrue(payload["pack"]["installed"])
        self.assertFalse(payload["pack"]["fullyPublic"])

        corpus = Corpus.objects.get(creator=self.admin, slug="portable-test-corpus")
        self.assertFalse(corpus.is_public)
        self.assertEqual(
            payload["pack"]["corpora"][0]["corpusId"],
            to_global_id("CorpusType", corpus.pk),
        )
        self.assertTrue(payload["pack"]["corpora"][0]["installed"])
        self.assertFalse(payload["pack"]["corpora"][0]["isPublic"])

    def test_pending_review_pack_cannot_be_published(self):
        with self._configured_catalog():
            preflight = AuthorityPackService.preflight(self.admin, "portable_test_pack")
            self.assertIsNotNone(preflight)
            result = schema.execute_sync(
                """
                mutation Publish($packId: String!, $fingerprint: String!) {
                  installAuthorityPack(
                    packId: $packId
                    expectedFingerprint: $fingerprint
                    publish: true
                  ) {
                    ok
                    message
                    pack { id }
                  }
                }
                """,
                variable_values={
                    "packId": "portable_test_pack",
                    "fingerprint": preflight.fingerprint,
                },
                context_value=self._context(self.admin),
            )

        self.assertIsNone(result.errors)
        payload = result.data["installAuthorityPack"]
        self.assertFalse(payload["ok"])
        self.assertIn("not approved", payload["message"])
        self.assertIsNone(payload["pack"])
        self.assertFalse(
            Corpus.objects.filter(
                creator=self.admin, slug="portable-test-corpus"
            ).exists()
        )

    def test_approved_pack_can_be_published_with_its_documents(self):
        self._write_pack(approval_status="approved")
        with self._configured_catalog():
            preflight = AuthorityPackService.preflight(self.admin, "portable_test_pack")
            self.assertIsNotNone(preflight)
            self.assertTrue(preflight.can_publish)
            result = AuthorityPackService.install(
                self.admin,
                pack_id="portable_test_pack",
                expected_fingerprint=preflight.fingerprint,
                publish=True,
                relink=False,
            )

        self.assertTrue(result.ok, result.error)
        corpus = Corpus.objects.get(creator=self.admin, slug="portable-test-corpus")
        self.assertTrue(corpus.is_public)
        self.assertTrue(corpus._get_active_documents().get().is_public)

    def test_post_commit_relink_failure_is_a_warning_not_an_install_failure(self):
        """A relink blowing up must not report a committed install as failed.

        ``_install_plan`` commits taxonomy/corpora/relationships, THEN runs the
        reactive relink.  Letting that raise told the operator "install failed"
        about a pack that is in the database, and the retry — idempotent —
        silently converges to a no-op, so the two never reconcile.
        """
        with self._configured_catalog():
            preflight = AuthorityPackService.preflight(self.admin, "portable_test_pack")
            with mock.patch(
                "opencontractserver.enrichment.services.EnrichmentService."
                "relink_corpora_for_keys",
                side_effect=RuntimeError("relink exploded"),
            ):
                result = AuthorityPackService.install(
                    self.admin,
                    pack_id="portable_test_pack",
                    expected_fingerprint=preflight.fingerprint,
                    relink=True,
                )

        self.assertTrue(result.ok, result.error)
        # The install really happened...
        corpus = Corpus.objects.get(creator=self.admin, slug="portable-test-corpus")
        self.assertEqual(corpus._get_active_documents().count(), 1)
        # ...and the failure is still surfaced rather than swallowed.
        self.assertEqual(len(result.value.post_commit_warnings), 1)
        self.assertIn("relink exploded", result.value.post_commit_warnings[0])
        self.assertIn("relink exploded", result.value.as_dict()["warnings"][0])
        self.assertIsNone(result.value.relink_summary)

    def test_post_install_refresh_failure_falls_back_to_the_preflight_plan(self):
        """The response re-read is post-commit too, and was in the caught tuple.

        ``install`` re-runs ``preflight_path`` after the write purely to report
        fresh state.  A CommandError there used to be indistinguishable from a
        validation failure and turned a committed install into ``ok=False``.
        """
        real_preflight = AuthorityPackService.preflight_path.__func__
        calls: list[int] = []

        def flaky_preflight(cls, pack_dir, *, creator):
            # ``install`` preflights twice: once to build the plan it validates
            # the fingerprint against, once afterwards to re-read the installed
            # state. Only the second — the post-commit one — fails here.
            calls.append(1)
            if len(calls) > 1:
                raise CommandError("pack vanished mid-install")
            return real_preflight(cls, pack_dir, creator=creator)

        with self._configured_catalog():
            preflight = AuthorityPackService.preflight(self.admin, "portable_test_pack")
            calls.clear()
            with mock.patch.object(
                AuthorityPackService,
                "preflight_path",
                classmethod(flaky_preflight),
            ):
                result = AuthorityPackService.install(
                    self.admin,
                    pack_id="portable_test_pack",
                    expected_fingerprint=preflight.fingerprint,
                    relink=False,
                )

        self.assertTrue(result.ok, result.error)
        self.assertTrue(
            Corpus.objects.filter(
                creator=self.admin, slug="portable-test-corpus"
            ).exists()
        )
        self.assertIn("pack vanished mid-install", result.value.post_commit_warnings[0])
        # Falls back to the approved pre-install plan instead of returning None.
        self.assertEqual(result.value.pack.fingerprint, preflight.fingerprint)

    def test_concurrent_install_race_returns_a_clean_failure_and_writes_nothing(self):
        """Two first-installs of the same pack race on the slug constraint.

        ``_preflight_corpus_identities`` reads without a lock, so both callers
        can see "no such corpus" and then collide inside
        ``get_or_create(slug=…, creator=…)``.  The loser must get a curated
        retry message, not a raw constraint dump — and nothing of its attempt
        may survive.
        """
        with self._configured_catalog():
            preflight = AuthorityPackService.preflight(self.admin, "portable_test_pack")
            with mock.patch(
                "opencontractserver.enrichment.services.authority_pack_service."
                "bootstrap_authority_corpus",
                side_effect=IntegrityError(
                    "duplicate key value violates unique constraint "
                    '"uniq_corpus_slug_per_creator_cs"'
                ),
            ):
                result = AuthorityPackService.install(
                    self.admin,
                    pack_id="portable_test_pack",
                    expected_fingerprint=preflight.fingerprint,
                    relink=False,
                )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, CONCURRENT_INSTALL_MESSAGE)
        self.assertNotIn("uniq_corpus_slug_per_creator_cs", result.error)
        self.assertFalse(
            Corpus.objects.filter(
                creator=self.admin, slug="portable-test-corpus"
            ).exists()
        )

    def test_catalog_identifier_cannot_be_used_as_a_filesystem_path(self):
        with self._configured_catalog():
            self.assertIsNone(
                AuthorityPackService.preflight(self.admin, str(self.pack_dir))
            )
            result = AuthorityPackService.install(
                self.admin,
                pack_id="../portable_pack",
                expected_fingerprint="sha256:irrelevant",
                relink=False,
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, DENIED)
        self.assertFalse(
            Corpus.objects.filter(
                creator=self.admin, slug="portable-test-corpus"
            ).exists()
        )


class AuthorityPackPlanValidationTests(TestCase):
    """Catalog/plan/manifest-level validation and fault-isolation.

    ``catalog()`` and ``preflight()`` must never raise — a broken configured
    pack becomes an invalid ``AuthorityPackPlan`` entry (so an operator can see
    and repair it), not a 500. These tests pin exactly that fault-isolation
    plus the lower-level manifest/fingerprint helpers it depends on.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username="plan-admin",
            is_superuser=True,
            is_staff=True,
            is_usage_capped=False,
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def _configured(self, *dirs):
        return mock.patch(
            "opencontractserver.enrichment.services.authority_pack_service."
            "authority_pack_dirs",
            return_value=list(dirs),
        )

    def test_catalog_flags_duplicate_pack_ids_as_invalid(self):
        # Two configured directories whose manifests declare the SAME pack
        # name are ambiguous — installing "the" pack would be a coin flip.
        # Both entries must come back invalid, not just one.
        dirs = []
        for name in ("first", "second"):
            pack_dir = self.root / name
            pack_dir.mkdir()
            (pack_dir / "pack.yaml").write_text(
                yaml.safe_dump({"name": "dup_pack", "corpora": []}),
                encoding="utf-8",
            )
            dirs.append(pack_dir)

        with self._configured(*dirs):
            plans = AuthorityPackService.catalog(self.admin)

        self.assertEqual(len(plans), 2)
        for plan in plans:
            self.assertFalse(plan.valid)
            self.assertEqual(plan.pack_id, "dup_pack")
            self.assertIn(
                "declared by more than one configured authority-pack directory",
                plan.validation_error,
            )

    def test_catalog_handles_pack_directory_without_a_manifest(self):
        # No pack.yaml at all: every manifest read fails, so the catalog must
        # fall back to the directory name for identity and surface the
        # underlying error rather than raising out of catalog().
        pack_dir = self.root / "no_manifest_pack"
        pack_dir.mkdir()

        with self._configured(pack_dir):
            plans = AuthorityPackService.catalog(self.admin)

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertFalse(plan.valid)
        self.assertEqual(plan.pack_id, "no_manifest_pack")
        self.assertIn("No pack.yaml manifest", plan.validation_error)
        self.assertEqual(plan.fingerprint, "")
        self.assertEqual(plan.source_hosts, ())
        self.assertEqual(plan.schema_version, 1)

    def _write_broken_schema_pack(self, name: str) -> Path:
        # A manifest that parses fine as YAML (so _read_manifest succeeds)
        # but fails preflight_path's schema_version check, AND declares a
        # malformed source_hosts entry — so _invalid_plan's own re-parse of
        # source_hosts also hits its except branch.
        pack_dir = self.root / name
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": "two",
                    "name": name,
                    "source_hosts": ["https://not-a-bare-host.example"],
                    "corpora": [],
                }
            ),
            encoding="utf-8",
        )
        return pack_dir

    def test_catalog_captures_a_preflight_failure_as_an_invalid_plan(self):
        pack_dir = self._write_broken_schema_pack("broken_schema_pack")

        with self._configured(pack_dir):
            plans = AuthorityPackService.catalog(self.admin)

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertFalse(plan.valid)
        self.assertEqual(plan.pack_id, "broken_schema_pack")
        self.assertIn("Unsupported pack schema_version", plan.validation_error)
        # _invalid_plan's non-int schema_version fallback.
        self.assertEqual(plan.schema_version, 1)
        # _invalid_plan's malformed-source_hosts except branch.
        self.assertEqual(plan.source_hosts, ())
        # The manifest itself is well-formed YAML, so the fingerprint hash
        # over pack.yaml still succeeds.
        self.assertTrue(plan.fingerprint.startswith("sha256:"))

    def test_preflight_captures_a_failure_as_an_invalid_plan(self):
        pack_dir = self._write_broken_schema_pack("broken_schema_pack_2")

        with self._configured(pack_dir):
            plan = AuthorityPackService.preflight(self.admin, "broken_schema_pack_2")

        self.assertIsNotNone(plan)
        self.assertFalse(plan.valid)
        self.assertIn("Unsupported pack schema_version", plan.validation_error)

    def test_install_path_rejects_a_stale_fingerprint(self):
        pack_dir = self.root / "install_path_pack"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "install_path_pack",
                    "corpora": [{"title": "A", "spec": "a.json"}],
                }
            ),
            encoding="utf-8",
        )
        (pack_dir / "a.json").write_text(
            json.dumps(
                {"sections": [{"key": "ex-code:1", "heading": "H", "text": "T"}]}
            ),
            encoding="utf-8",
        )
        with self.assertRaisesMessage(CommandError, "validate it again"):
            AuthorityPackService.install_path(
                pack_dir,
                creator=self.admin,
                expected_fingerprint="sha256:definitely-stale",
            )

    def test_preflight_path_rejects_unsupported_schema_version(self):
        pack_dir = self.root / "unsupported_schema"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump({"schema_version": 3, "name": "p", "corpora": []}),
            encoding="utf-8",
        )
        with self.assertRaisesMessage(CommandError, "Unsupported pack schema_version"):
            AuthorityPackService.preflight_path(pack_dir, creator=self.admin)

    def test_preflight_path_rejects_authority_prefixes_without_mappings(self):
        # A corpus entry binds a namespace prefix, but the pack declares no
        # 'mappings' file at all — there is nothing for that prefix to trace
        # back to.
        pack_dir = self.root / "prefix_needs_mappings"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "prefix_needs_mappings",
                    "corpora": [
                        {
                            "title": "A",
                            "spec": "a.json",
                            "authority_prefixes": ["some-law"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (pack_dir / "a.json").write_text(
            json.dumps(
                {"sections": [{"key": "some-law:1", "heading": "H", "text": "T"}]}
            ),
            encoding="utf-8",
        )
        with self.assertRaisesMessage(
            CommandError,
            "requires the pack manifest to declare 'mappings'",
        ):
            AuthorityPackService.preflight_path(pack_dir, creator=self.admin)

    def test_read_manifest_rejects_malformed_yaml(self):
        pack_dir = self.root / "malformed_yaml"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            "name: p\n  bad_indent: [\n", encoding="utf-8"
        )
        with self.assertRaisesMessage(CommandError, "Could not parse"):
            AuthorityPackService._read_manifest(pack_dir)

    def test_read_manifest_rejects_non_mapping_yaml(self):
        pack_dir = self.root / "non_mapping_yaml"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text("- a\n- b\n", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "must contain a top-level mapping"):
            AuthorityPackService._read_manifest(pack_dir)

    def test_resolve_catalog_pack_rejects_invalid_pack_id(self):
        with self.assertRaises(CommandError):
            AuthorityPackService._resolve_catalog_pack("")
        with self.assertRaises(CommandError):
            AuthorityPackService._resolve_catalog_pack(None)

    def test_pack_approval_status_pending_review_and_mixed(self):
        def _plan(status: str) -> AuthorityPackCorpusPlan:
            return AuthorityPackCorpusPlan(
                slug="s",
                title="T",
                approval_status=status,
                installed=False,
                is_public=False,
                corpus_id=None,
                action="CREATE",
                section_count=1,
            )

        self.assertEqual(
            AuthorityPackService._pack_approval_status(
                [_plan("approved"), _plan("pending_legal_review")]
            ),
            "pending_legal_review",
        )
        self.assertEqual(
            AuthorityPackService._pack_approval_status(
                [_plan("approved"), _plan("deprecated")]
            ),
            "mixed",
        )

    def test_declarative_fingerprint_skips_non_dict_corpora_entries(self):
        # A manifest whose 'corpora' list holds a non-dict entry cannot pass
        # full preflight validation, but declarative_fingerprint() is used to
        # detect drift WITHOUT running that validation, so its inner loop must
        # tolerate (skip) the malformed entry rather than crashing.
        pack_dir = self.root / "non_dict_corpora_entry"
        pack_dir.mkdir()
        (pack_dir / "pack.yaml").write_text(
            yaml.safe_dump({"name": "p", "corpora": ["not-a-dict"]}),
            encoding="utf-8",
        )
        fingerprint = AuthorityPackService.declarative_fingerprint(pack_dir)
        self.assertTrue(fingerprint.startswith("sha256:"))

    def test_hash_files_rejects_a_path_outside_the_pack_directory(self):
        pack_dir = self.root / "hash_pack"
        pack_dir.mkdir()
        outside = self.root / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "escapes its directory"):
            AuthorityPackService._hash_files(pack_dir, [outside])

    def test_pack_file_rejects_a_non_string_relative_path(self):
        with self.assertRaisesMessage(
            CommandError, "must be a non-empty relative path"
        ):
            AuthorityPackService._pack_file(self.root, 123, label="Manifest 'mappings'")
        with self.assertRaisesMessage(
            CommandError, "must be a non-empty relative path"
        ):
            AuthorityPackService._pack_file(
                self.root, "   ", label="Manifest 'mappings'"
            )

    def test_pack_file_rejects_a_path_escaping_the_pack_directory(self):
        pack_dir = self.root / "escape_pack"
        pack_dir.mkdir()
        (self.root / "outside.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesMessage(
            CommandError, "escapes the authority pack directory"
        ):
            AuthorityPackService._pack_file(
                pack_dir, "../outside.json", label="Corpus 'A' spec"
            )
