"""Tests for authority packs.

Covers (1) the static validity of the shipped reference Bolivia pack files and
(2) the generic ``load_authority_pack`` management command end-to-end (taxonomy
load + per-area corpus bootstrap + persona application + idempotency).

See ``docs/architecture/proposals/0002-authority-packs.md``.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from opencontractserver import enrichment
from opencontractserver.annotations.models import AuthorityNamespace
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import (
    CorpusDocumentService,
)
from opencontractserver.enrichment.constants import ALL_AUTHORITY_TYPES

User = get_user_model()

PACK_DIR = Path(enrichment.__file__).parent / "data" / "authority_packs" / "bolivia"
CONSTITUCIONAL_TITLE = "Bolivia — Derecho Constitucional"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class BoliviaPackContentTests(SimpleTestCase):
    """Static integrity of the shipped pack — runs with no DB."""

    def test_manifest_well_formed(self):
        manifest = _load_yaml(PACK_DIR / "pack.yaml")
        for key in ("name", "jurisdiction", "mappings", "corpora"):
            self.assertIn(key, manifest)
        self.assertTrue((PACK_DIR / manifest["mappings"]).is_file())
        self.assertTrue(manifest["corpora"], "manifest declares no corpora")
        for entry in manifest["corpora"]:
            self.assertIn("title", entry)
            self.assertTrue(
                (PACK_DIR / entry["spec"]).is_file(),
                f"missing spec for {entry.get('title')}",
            )
            if entry.get("persona"):
                self.assertTrue((PACK_DIR / entry["persona"]).is_file())

    def test_mappings_schema_valid(self):
        prefixes = (
            _load_yaml(PACK_DIR / "authority_mappings.bolivia.yaml").get("prefixes")
            or {}
        )
        self.assertTrue(prefixes)
        for prefix, spec in prefixes.items():
            for field in ("display_name", "jurisdiction", "authority_type", "aliases"):
                self.assertIn(field, spec, f"{prefix} missing {field}")
            self.assertTrue(spec["jurisdiction"])
            self.assertIn(
                spec["authority_type"],
                ALL_AUTHORITY_TYPES,
                f"{prefix}: {spec['authority_type']!r} is not a valid authority_type",
            )
            self.assertIsInstance(spec["aliases"], list)

    def test_spec_keys_use_declared_prefixes(self):
        declared = set(
            _load_yaml(PACK_DIR / "authority_mappings.bolivia.yaml").get("prefixes")
            or {}
        )
        manifest = _load_yaml(PACK_DIR / "pack.yaml")
        for entry in manifest["corpora"]:
            spec = json.loads((PACK_DIR / entry["spec"]).read_text(encoding="utf-8"))
            self.assertTrue(spec.get("sections"), f"{entry['spec']} has no sections")
            for sec in spec["sections"]:
                for field in ("key", "heading", "text"):
                    self.assertTrue(sec.get(field), f"section missing {field}")
                prefix = sec["key"].split(":", 1)[0]
                self.assertIn(
                    prefix,
                    declared,
                    f"key {sec['key']!r} uses prefix not declared in the mappings",
                )


class LoadAuthorityPackCommandTests(TestCase):
    """The generic loader, exercised against the reference Bolivia pack."""

    def setUp(self):
        self.owner = User.objects.create_user(username="packowner", password="p")

    def _run(self) -> str:
        out = StringIO()
        call_command(
            "load_authority_pack",
            path=str(PACK_DIR),
            creator="packowner",
            stdout=out,
        )
        return out.getvalue()

    def test_load_creates_namespaces_corpus_and_persona(self):
        output = self._run()

        # 1) taxonomy → AuthorityNamespace rows
        self.assertGreaterEqual(
            AuthorityNamespace.objects.filter(jurisdiction="bo").count(), 5
        )
        cpe = AuthorityNamespace.objects.get(prefix="cpe")
        self.assertEqual(cpe.authority_type, "constitution")

        # 2) corpus + content + persona
        corpus = Corpus.objects.get(title=CONSTITUCIONAL_TITLE)
        self.assertEqual(corpus.creator_id, self.owner.id)
        self.assertIn(
            "constitucional", (corpus.corpus_agent_instructions or "").lower()
        )
        self.assertEqual(
            CorpusDocumentService.get_corpus_documents(self.owner, corpus).count(), 4
        )
        self.assertIn("4 created", output)

    def test_load_is_idempotent(self):
        self._run()
        second = self._run()
        # Re-running creates no new corpus and no new documents.
        self.assertEqual(Corpus.objects.filter(title=CONSTITUCIONAL_TITLE).count(), 1)
        self.assertIn("0 created", second)
        corpus = Corpus.objects.get(title=CONSTITUCIONAL_TITLE)
        self.assertEqual(
            CorpusDocumentService.get_corpus_documents(self.owner, corpus).count(), 4
        )
