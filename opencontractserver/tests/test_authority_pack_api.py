"""Service and GraphQL tests for the trusted authority-pack install surface."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml
from django.contrib.auth import get_user_model
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
