"""Tests for authority packs.

Covers (1) the static validity of the shipped reference Bolivia pack files and
(2) the generic ``load_authority_pack`` management command end-to-end (taxonomy
load + per-area corpus bootstrap + persona application + idempotency).

See ``docs/architecture/proposals/0002-authority-packs.md``.
"""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
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

# A declared prefix borrowed from the reference mappings, so synthetic packs use
# a real authority_type vocab entry without re-declaring the whole taxonomy.
BOLIVIA_MAPPINGS = PACK_DIR / "authority_mappings.bolivia.yaml"


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
            CorpusDocumentService.get_corpus_documents_visible_to_user(
                self.owner, corpus
            ).count(),
            4,
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
            CorpusDocumentService.get_corpus_documents_visible_to_user(
                self.owner, corpus
            ).count(),
            4,
        )


class LoadAuthorityPackEdgeCaseTests(TestCase):
    """Synthetic packs that exercise the loader's branches and error paths."""

    def setUp(self):
        self.owner = User.objects.create_user(username="edgeowner", password="p")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pack_dir = Path(self._tmp.name)

    # ---- helpers ---------------------------------------------------------
    def _write(self, rel: str, content: str) -> None:
        path = self.pack_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_pack(
        self,
        manifest: dict,
        *,
        specs: dict | None = None,
        personas: dict | None = None,
        copy_mappings: bool = False,
    ) -> None:
        self._write("pack.yaml", yaml.safe_dump(manifest, allow_unicode=True))
        for rel, spec in (specs or {}).items():
            self._write(rel, json.dumps(spec))
        for rel, text in (personas or {}).items():
            self._write(rel, text)
        if copy_mappings:
            self._write(
                manifest["mappings"],
                BOLIVIA_MAPPINGS.read_text(encoding="utf-8"),
            )

    def _run(self, **extra) -> str:
        out = StringIO()
        call_command(
            "load_authority_pack",
            path=str(self.pack_dir),
            creator="edgeowner",
            stdout=out,
            **extra,
        )
        return out.getvalue()

    @staticmethod
    def _one_section_spec(key: str = "cpe:1") -> dict:
        return {
            "sections": [
                {"key": key, "heading": "Artículo 1", "text": "Texto del artículo."}
            ]
        }

    # ---- happy-path branches --------------------------------------------
    def test_public_flag_publishes_corpus(self):
        self._write_pack(
            {"name": "p", "corpora": [{"title": "Pack Area A", "spec": "a.json"}]},
            specs={"a.json": self._one_section_spec()},
        )
        self._run(public=True)
        corpus = Corpus.objects.get(title="Pack Area A")
        self.assertTrue(corpus.is_public)
        # --public must also cascade to the seeded documents: the authority
        # would resolve for nobody but the owner otherwise. The cascade is
        # synchronous — Corpus.save() with is_public transitioning runs
        # _propagate_public_status_to_documents() inline (no Celery needed).
        docs = CorpusDocumentService.get_corpus_documents(self.owner, corpus)
        self.assertTrue(docs.exists())
        self.assertTrue(all(d.is_public for d in docs))

    def test_relink_summary_printed_once(self):
        # Two corpora → exactly ONE re-link sweep (deferred until after the
        # loop), so the summary line appears once, not once per corpus.
        self._write_pack(
            {
                "name": "p",
                "corpora": [
                    {"title": "Area A", "spec": "a.json"},
                    {"title": "Area B", "spec": "b.json"},
                ],
            },
            specs={
                "a.json": self._one_section_spec("cpe:1"),
                "b.json": self._one_section_spec("bo-ley:2"),
            },
        )
        output = self._run()
        self.assertEqual(output.count("Re-link:"), 1)

    def test_no_relink_skips_relink(self):
        self._write_pack(
            {"name": "p", "corpora": [{"title": "Area A", "spec": "a.json"}]},
            specs={"a.json": self._one_section_spec()},
        )
        output = self._run(no_relink=True)
        self.assertNotIn("Re-link:", output)

    def test_taxonomy_only_pack_loads_namespaces(self):
        # A pack may declare just taxonomy (no corpora) — that is valid, not a
        # silent no-op.
        self._write_pack(
            {"name": "p", "mappings": "m.yaml"},
            copy_mappings=True,
        )
        self._run()
        self.assertGreaterEqual(
            AuthorityNamespace.objects.filter(jurisdiction="bo").count(), 5
        )

    def test_persona_idempotent_and_modified_persisted(self):
        # Finding #7: an unchanged persona must NOT rewrite the corpus.
        # Finding #2: a CHANGED persona must save AND advance ``modified``.
        self._write_pack(
            {
                "name": "p",
                "corpora": [
                    {"title": "Area A", "spec": "a.json", "persona": "persona.txt"}
                ],
            },
            specs={"a.json": self._one_section_spec()},
            personas={"persona.txt": "Persona uno"},
        )
        self._run()
        corpus = Corpus.objects.get(title="Area A")
        self.assertEqual(corpus.corpus_agent_instructions, "Persona uno")
        m1 = corpus.modified

        # Re-run unchanged → no rewrite, ``modified`` frozen.
        self._run()
        corpus.refresh_from_db()
        self.assertEqual(corpus.modified, m1)

        # Change the persona → rewrite + ``modified`` advances (proves the
        # update_fields write actually carried the timestamp).
        self._write("persona.txt", "Persona dos")
        self._run()
        corpus.refresh_from_db()
        self.assertEqual(corpus.corpus_agent_instructions, "Persona dos")
        self.assertGreater(corpus.modified, m1)

    def test_model_override_applied(self):
        self._write_pack(
            {
                "name": "p",
                "corpora": [
                    {
                        "title": "Area A",
                        "spec": "a.json",
                        "preferred_embedder": "opencontractserver.pipeline.x.Custom",
                    }
                ],
            },
            specs={"a.json": self._one_section_spec()},
        )
        self._run()
        corpus = Corpus.objects.get(title="Area A")
        self.assertEqual(
            corpus.preferred_embedder, "opencontractserver.pipeline.x.Custom"
        )

    # ---- error / guard branches -----------------------------------------
    def test_missing_pack_yaml(self):
        with self.assertRaises(CommandError):
            self._run()

    def test_unknown_creator(self):
        self._write_pack(
            {"name": "p", "corpora": [{"title": "A", "spec": "a.json"}]},
            specs={"a.json": self._one_section_spec()},
        )
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "load_authority_pack",
                path=str(self.pack_dir),
                creator="nobody",
                stdout=out,
            )

    def test_empty_manifest_rejected(self):
        # Neither mappings nor corpora → nothing to load (catches a typo'd key).
        self._write_pack({"name": "p"})
        with self.assertRaises(CommandError):
            self._run()

    def test_corpora_null_rejected(self):
        self._write("pack.yaml", "name: p\ncorpora:\n")
        with self.assertRaises(CommandError):
            self._run()

    def test_corpora_wrong_type_rejected(self):
        self._write("pack.yaml", "name: p\ncorpora: not-a-list\n")
        with self.assertRaises(CommandError):
            self._run()

    def test_missing_mappings_file_rejected(self):
        self._write_pack(
            {
                "name": "p",
                "mappings": "nope.yaml",
                "corpora": [{"title": "A", "spec": "a.json"}],
            },
            specs={"a.json": self._one_section_spec()},
        )
        with self.assertRaises(CommandError):
            self._run()

    def test_missing_spec_file_rejected(self):
        self._write_pack(
            {"name": "p", "corpora": [{"title": "A", "spec": "missing.json"}]}
        )
        with self.assertRaises(CommandError):
            self._run()

    def test_malformed_sections_rejected(self):
        self._write_pack(
            {"name": "p", "corpora": [{"title": "A", "spec": "a.json"}]},
            specs={"a.json": {"sections": [{"heading": "no key", "text": "x"}]}},
        )
        with self.assertRaises(CommandError):
            self._run()

    def test_missing_persona_aborts_before_creating_corpus(self):
        # Finding #3: the persona is resolved BEFORE bootstrap, so a missing
        # persona file must not leave a half-loaded corpus behind.
        self._write_pack(
            {
                "name": "p",
                "corpora": [{"title": "A", "spec": "a.json", "persona": "missing.txt"}],
            },
            specs={"a.json": self._one_section_spec()},
        )
        with self.assertRaises(CommandError):
            self._run()
        self.assertFalse(Corpus.objects.filter(title="A").exists())

    def test_entry_missing_title_rejected(self):
        self._write_pack(
            {"name": "p", "corpora": [{"spec": "a.json"}]},
            specs={"a.json": self._one_section_spec()},
        )
        with self.assertRaises(CommandError):
            self._run()

    def test_taxonomy_not_loaded_when_corpora_invalid(self):
        # The pack is validated end-to-end BEFORE any DB write, so a manifest
        # with valid mappings but a malformed corpora entry (missing spec file)
        # must abort WITHOUT persisting taxonomy — no hybrid "namespaces loaded,
        # zero corpora" state that the idempotent re-run can't surface.
        self._write_pack(
            {
                "name": "p",
                "mappings": "m.yaml",
                "corpora": [{"title": "A", "spec": "missing.json"}],
            },
            copy_mappings=True,
        )
        with self.assertRaises(CommandError):
            self._run()
        self.assertEqual(
            AuthorityNamespace.objects.filter(jurisdiction="bo").count(), 0
        )

    def test_aliases_wrong_type_rejected(self):
        # A spec whose 'aliases' is a bare string (not a list) would be iterated
        # character-by-character downstream and corrupt the alias registry, so
        # the loader must reject it instead of seeding the corpus.
        self._write_pack(
            {"name": "p", "corpora": [{"title": "A", "spec": "a.json"}]},
            specs={
                "a.json": {
                    "aliases": "CPE",
                    "sections": [
                        {"key": "cpe:1", "heading": "Artículo 1", "text": "Texto."}
                    ],
                }
            },
        )
        with self.assertRaises(CommandError):
            self._run()
        self.assertFalse(Corpus.objects.filter(title="A").exists())
