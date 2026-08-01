"""Database integration tests for the generic authority-pack loader.

The subject is ``tests/fixtures/authority_packs/example_utility`` — a complete
schema-v2 pack invented for this suite. Testing against a fixture rather than a
shipped pack is deliberate: the loader's contract is *pack-shaped input →
converged corpora, taxonomy, metadata schema and relationships*, and pinning
that contract to one jurisdiction's data made the tests re-assert the data
instead of the behavior. Deployments that install a real pack assert their own
identities in their own repository.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from io import StringIO
from pathlib import Path

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from opencontractserver.annotations.models import (
    AuthorityNamespace,
    AuthorityRelationship,
)
from opencontractserver.corpuses.management.commands.load_authority_pack import (
    Command as AuthorityPackLoaderCommand,
)
from opencontractserver.corpuses.management.commands.load_authority_pack import (
    _ValidatedCorpus,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.enrichment.authority_sources import SourceRelationship
from opencontractserver.enrichment.services.authority_relationship_service import (
    AuthorityRelationshipService,
)
from opencontractserver.extracts.models import Column, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

FIXTURE_PACK = (
    Path(__file__).resolve().parent / "fixtures" / "authority_packs" / "example_utility"
)
PACK_NAME = "example_utility"

# (slug, title, number of seed sections in the corpus spec)
PACK_CORPORA = [
    ("example-utility-statutes", "Example Utility Statutes", 2),
    ("example-utility-proceedings", "Example Utility Proceedings", 1),
]


def _yaml(path: Path) -> dict:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"{path} does not contain a YAML mapping")
    return parsed


class AuthorityPackLoaderTests(TestCase):
    """Exercise a complete schema-v2 pack through the generic loader."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="pack-owner",
            # Authority packs are installed by an operator/service account.
            # The default end-user quota is intentionally enforced by the
            # shared import path and is not bypassed by this command.
            is_usage_capped=False,
        )

    def _load_pack(self, *, public: bool = True) -> str:
        stdout = StringIO()
        call_command(
            "load_authority_pack",
            path=str(FIXTURE_PACK),
            creator=self.owner.username,
            public=public,
            no_relink=True,
            stdout=stdout,
        )
        return stdout.getvalue()

    def test_loads_declared_identities_typed_schemas_and_relationships(self):
        self._load_pack()

        expected_corpora = {
            slug: (title, section_count) for slug, title, section_count in PACK_CORPORA
        }
        actual = {
            corpus.slug: corpus
            for corpus in Corpus.objects.filter(
                creator=self.owner,
                slug__in=expected_corpora,
            )
        }
        self.assertEqual(set(actual), set(expected_corpora))

        manifest = _yaml(FIXTURE_PACK / "pack.yaml")
        for slug, (title, section_count) in expected_corpora.items():
            corpus = actual[slug]
            self.assertEqual(corpus.title, title)
            self.assertTrue(corpus.is_public)
            self.assertFalse(corpus.auto_branding_enabled)
            self.assertEqual(
                DocumentPath.objects.filter(
                    corpus=corpus,
                    is_current=True,
                    is_deleted=False,
                ).count(),
                section_count,
            )

            entry = next(
                candidate
                for candidate in manifest["corpora"]
                if candidate["slug"] == slug
            )
            declared_schema = _yaml(FIXTURE_PACK / entry["metadata_schema"])
            declared_fields = {
                field["name"]: (
                    field["data_type"],
                    field.get("validation_config", {}),
                )
                for field in declared_schema["fields"]
            }
            columns = {
                column.name: column
                for column in corpus.metadata_schema.columns.filter(
                    is_manual_entry=True
                )
            }
            self.assertEqual(set(columns), set(declared_fields))
            for name, (data_type, validation_config) in declared_fields.items():
                self.assertEqual(columns[name].data_type, data_type)
                self.assertEqual(
                    columns[name].validation_config or {},
                    validation_config,
                )

        # A prefix declared under exactly one corpus's ``authority_prefixes``
        # binds to that corpus and stops being global.
        statutes = actual["example-utility-statutes"]
        bound = AuthorityNamespace.objects.get(prefix="ex-code")
        self.assertEqual(bound.authority_corpus_id, statutes.id)
        self.assertFalse(bound.is_global)
        self.assertIsNone(bound.baseline_origin)

        # Ownership is never inferred from seed keys or spec aliases. ``ex-rule``
        # is an alias of the proceedings spec but is bound by no corpus entry,
        # so it stays global.
        unbound = AuthorityNamespace.objects.get(prefix="ex-rule")
        self.assertIsNone(unbound.authority_corpus_id)
        self.assertTrue(unbound.is_global)

        declared_edges = {}
        for declaration in _yaml(FIXTURE_PACK / "relationships.yaml")["relationships"]:
            identity = (
                declaration["source_key"],
                declaration["relationship_type"],
                declaration["target_key"],
            )
            declared_edges[identity] = declaration

        rows = {
            (row.source_key, row.relationship_type, row.target_key): row
            for row in AuthorityRelationship.objects.all()
        }
        self.assertEqual(set(rows), set(declared_edges))
        for identity, declaration in declared_edges.items():
            row = rows[identity]
            self.assertEqual(row.source, "baseline")
            self.assertEqual(row.origin, PACK_NAME)
            self.assertEqual(row.verified, declaration["verified"])
            self.assertEqual(row.metadata, declaration["metadata"])

    def test_second_load_is_idempotent_and_preserves_curator_state(self):
        first_output = self._load_pack()

        corpus = Corpus.objects.get(creator=self.owner, slug="example-utility-statutes")
        corpus.preferred_llm = "curator-selected-model"
        corpus.save(update_fields=["preferred_llm", "modified"])
        corpus.refresh_from_db()
        curator_preferred_llm = corpus.preferred_llm
        curator = User.objects.create_user(username="pack-curator")
        set_permissions_for_obj_to_user(
            curator,
            corpus,
            [PermissionTypes.READ],
        )

        column = corpus.metadata_schema.columns.get(name="publisher")
        column.help_text = "Curator-specific publisher guidance"
        column.validation_config = {"required": True}
        column.display_order = 999
        column.save(
            update_fields=[
                "help_text",
                "validation_config",
                "display_order",
                "modified",
            ]
        )

        document = Document.objects.get(
            path_records__corpus=corpus,
            path_records__is_current=True,
            custom_meta__canonical_key="ex-code:12.001",
        )
        self.assertEqual(document.custom_meta["authority_weight"], "CONTROLLING")
        document.custom_meta = {
            **document.custom_meta,
            "curator_note": "Keep this reviewed note.",
            "authority_weight": "INTERPRETIVE",
        }
        document.save(update_fields=["custom_meta", "modified"])

        relationship = AuthorityRelationship.objects.get(
            source_key="ex-rule:2026-14",
            relationship_type="IMPLEMENTS",
            target_key="ex-code:12.001",
        )
        relationship.source = "manual"
        relationship.verified = True
        relationship.metadata = {"curator_note": "Legally reviewed."}
        relationship.save(update_fields=["source", "verified", "metadata", "modified"])

        counts_before = {
            "corpora": Corpus.objects.filter(creator=self.owner).count(),
            "documents": Document.objects.filter(creator=self.owner).count(),
            "paths": DocumentPath.objects.filter(corpus__creator=self.owner).count(),
            "memberships": DocumentPath.objects.filter(
                corpus__creator=self.owner,
                is_current=True,
                is_deleted=False,
            ).count(),
            "fieldsets": Fieldset.objects.filter(corpus__creator=self.owner).count(),
            "columns": Column.objects.filter(
                fieldset__corpus__creator=self.owner
            ).count(),
            "relationships": AuthorityRelationship.objects.count(),
        }

        second_output = self._load_pack()

        self.assertIn("created", first_output)
        self.assertIn("0 created", second_output)
        self.assertEqual(
            counts_before,
            {
                "corpora": Corpus.objects.filter(creator=self.owner).count(),
                "documents": Document.objects.filter(creator=self.owner).count(),
                "paths": DocumentPath.objects.filter(
                    corpus__creator=self.owner
                ).count(),
                "memberships": DocumentPath.objects.filter(
                    corpus__creator=self.owner,
                    is_current=True,
                    is_deleted=False,
                ).count(),
                "fieldsets": Fieldset.objects.filter(
                    corpus__creator=self.owner
                ).count(),
                "columns": Column.objects.filter(
                    fieldset__corpus__creator=self.owner
                ).count(),
                "relationships": AuthorityRelationship.objects.count(),
            },
        )

        corpus.refresh_from_db()
        self.assertEqual(corpus.preferred_llm, curator_preferred_llm)
        self.assertTrue(corpus.user_can(curator, PermissionTypes.READ))
        column.refresh_from_db()
        self.assertEqual(column.help_text, "Curator-specific publisher guidance")
        self.assertEqual(column.validation_config, {"required": True})
        self.assertEqual(column.display_order, 999)
        document.refresh_from_db()
        self.assertEqual(
            document.custom_meta["curator_note"],
            "Keep this reviewed note.",
        )
        self.assertEqual(document.custom_meta["authority_weight"], "INTERPRETIVE")
        relationship.refresh_from_db()
        self.assertEqual(relationship.source, "manual")
        self.assertTrue(relationship.verified)
        self.assertEqual(
            relationship.metadata,
            {"curator_note": "Legally reviewed."},
        )

    def test_default_weight_is_a_soft_seed_default_with_explicit_precedence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir)
            (pack_dir / "sections.json").write_text(
                json.dumps(
                    {
                        "sections": [
                            {
                                "key": "test-law:default",
                                "heading": "Default weight",
                                "text": "Seed text.",
                            },
                            {
                                "key": "test-law:explicit",
                                "heading": "Explicit weight",
                                "text": "Seed text.",
                                "metadata": {
                                    "authority_weight": "ADVOCACY",
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            corpus = AuthorityPackLoaderCommand()._validate_corpus_entry(
                {
                    "title": "Soft defaults",
                    "spec": "sections.json",
                    "default_authority_weight": "EVIDENTIARY",
                },
                pack_dir,
            )

        defaulted, explicit = corpus.sections
        self.assertEqual(
            defaulted.metadata_defaults,
            {"authority_weight": "EVIDENTIARY"},
        )
        self.assertNotIn("authority_weight", defaulted.metadata)
        self.assertEqual(explicit.metadata["authority_weight"], "ADVOCACY")
        self.assertNotIn("authority_weight", explicit.metadata_defaults)

    def test_corpus_authority_prefix_schema_is_explicit_unique_and_declared(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir)
            (pack_dir / "sections.json").write_text(
                json.dumps(
                    {
                        "sections": [
                            {
                                "key": "test-law:1",
                                "heading": "Test law",
                                "text": "Seed text.",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            mappings_path = pack_dir / "mappings.yaml"
            mappings_path.write_text(
                yaml.safe_dump(
                    {
                        "prefixes": {
                            "test-law": {
                                "display_name": "Test Law",
                                "authority_type": "regulation",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            service = AuthorityPackLoaderCommand()
            corpus = service._validate_corpus_entry(
                {
                    "title": "Bound Corpus",
                    "spec": "sections.json",
                    "authority_prefixes": ["test-law"],
                },
                pack_dir,
            )
            self.assertEqual(corpus.authority_prefixes, ("test-law",))
            service._validate_declared_prefixes(mappings_path, [corpus], [])

            with self.assertRaisesMessage(
                CommandError,
                "authority_prefixes must be a list",
            ):
                service._validate_corpus_entry(
                    {
                        "title": "Malformed Binding",
                        "spec": "sections.json",
                        "authority_prefixes": "test-law",
                    },
                    pack_dir,
                )

            with self.assertRaisesMessage(
                CommandError,
                "can belong to only one corpus",
            ):
                service._validate_unique_authority_prefix_bindings(
                    [
                        corpus,
                        replace(corpus, title="Second Bound Corpus"),
                    ]
                )

            with self.assertRaisesMessage(
                CommandError,
                "which this pack does not declare",
            ):
                service._validate_declared_prefixes(
                    mappings_path,
                    [replace(corpus, authority_prefixes=("foreign-law",))],
                    [],
                )

    def test_namespace_binding_is_idempotent_and_preserves_foreign_ownership(self):
        corpus = Corpus.objects.create(
            creator=self.owner,
            title="Namespace Binding Target",
            slug="namespace-binding-target",
        )
        own = AuthorityNamespace.objects.create(
            prefix="pack-owned-law",
            display_name="Pack Owned Law",
            authority_type="regulation",
            source="baseline",
            baseline_origin="binding_pack",
        )
        foreign = AuthorityNamespace.objects.create(
            prefix="foreign-owned-law",
            display_name="Foreign Owned Law",
            authority_type="regulation",
            source="baseline",
            baseline_origin="foreign_pack",
        )
        manual = AuthorityNamespace.objects.create(
            prefix="manual-owned-law",
            display_name="Manual Owned Law",
            authority_type="regulation",
            source="manual",
            created_by=self.owner,
        )

        service = AuthorityPackLoaderCommand()
        service._bind_corpus_authority_prefixes(
            corpus_id=corpus.id,
            prefixes=(own.prefix,),
            origin="binding_pack",
        )
        service._bind_corpus_authority_prefixes(
            corpus_id=corpus.id,
            prefixes=(own.prefix,),
            origin="binding_pack",
        )

        own.refresh_from_db()
        self.assertEqual(own.authority_corpus_id, corpus.id)
        self.assertFalse(own.is_global)
        self.assertIsNone(own.baseline_origin)

        for namespace in (foreign, manual):
            with self.subTest(prefix=namespace.prefix):
                with self.assertRaisesMessage(CommandError, "cannot bind it"):
                    service._bind_corpus_authority_prefixes(
                        corpus_id=corpus.id,
                        prefixes=(namespace.prefix,),
                        origin="binding_pack",
                    )
                namespace.refresh_from_db()
                self.assertIsNone(namespace.authority_corpus_id)
                self.assertTrue(namespace.is_global)

    def test_late_relationship_error_aborts_whole_pack_before_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir)
            # Reuse the fixture pack's real taxonomy and metadata schema so the
            # run reaches relationship validation — the point of the test is
            # that a failure *after* the earlier stages still writes nothing.
            mappings = (
                FIXTURE_PACK / "authority_mappings.example_utility.yaml"
            ).read_text(encoding="utf-8")
            metadata_schema = (
                FIXTURE_PACK / "metadata/authority_source_record.yaml"
            ).read_text(encoding="utf-8")
            spec = {
                "sections": [
                    {
                        "key": "ex-code:12.001",
                        "heading": "Valid first corpus seed",
                        "text": "Valid seed text.",
                    }
                ]
            }
            manifest = {
                "schema_version": 2,
                "name": "atomic_pack",
                "mappings": "mappings.yaml",
                "metadata_schema": "metadata.yaml",
                "relationships": "relationships.yaml",
                "corpora": [
                    {
                        "slug": "atomic-first",
                        "title": "Atomic First",
                        "charter": "first-charter.yaml",
                        "spec": "first.json",
                        "metadata_schema": "metadata.yaml",
                    },
                    {
                        "slug": "atomic-second",
                        "title": "Atomic Second",
                        "charter": "second-charter.yaml",
                        "spec": "second.json",
                        "metadata_schema": "metadata.yaml",
                    },
                ],
            }
            (pack_dir / "pack.yaml").write_text(
                yaml.safe_dump(manifest), encoding="utf-8"
            )
            (pack_dir / "mappings.yaml").write_text(mappings, encoding="utf-8")
            (pack_dir / "metadata.yaml").write_text(metadata_schema, encoding="utf-8")
            (pack_dir / "first-charter.yaml").write_text(
                "purpose: First valid corpus\n", encoding="utf-8"
            )
            (pack_dir / "second-charter.yaml").write_text(
                "purpose: Second valid corpus\n", encoding="utf-8"
            )
            (pack_dir / "first.json").write_text(json.dumps(spec), encoding="utf-8")
            (pack_dir / "second.json").write_text(json.dumps(spec), encoding="utf-8")
            (pack_dir / "relationships.yaml").write_text(
                yaml.safe_dump(
                    {
                        "relationships": [
                            {
                                "source_key": "ex-code:12.001",
                                "relationship_type": "NOT_A_RELATIONSHIP",
                                "target_key": "ex-code:12.002",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(CommandError):
                self._load_pack_from_path(pack_dir)

        self.assertFalse(
            Corpus.objects.filter(
                creator=self.owner,
                slug__in=["atomic-first", "atomic-second"],
            ).exists()
        )
        self.assertFalse(
            AuthorityNamespace.objects.filter(baseline_origin="atomic_pack").exists()
        )
        self.assertFalse(
            AuthorityRelationship.objects.filter(source_key="ex-code:12.001").exists()
        )

    def test_relationship_yaml_rejects_quoted_false_verification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pack_dir = Path(temp_dir)
            (pack_dir / "relationships.yaml").write_text(
                (
                    "relationships:\n"
                    "  - source_key: ex-code:12.001\n"
                    "    relationship_type: IMPLEMENTS\n"
                    "    target_key: ex-code:12.002\n"
                    '    verified: "false"\n'
                ),
                encoding="utf-8",
            )

            with self.assertRaisesMessage(
                CommandError, "verified must be true or false; got 'false'"
            ):
                AuthorityPackLoaderCommand._read_relationships(
                    {"relationships": "relationships.yaml"},
                    pack_dir,
                )

    def test_inline_relationships_join_the_pack_baseline_declaration_set(self):
        origin = "combined-relationship-pack"
        inline = SourceRelationship(
            target_key="ex-code:12.002",
            relationship_type="IMPLEMENTS",
        )
        corpus = _ValidatedCorpus(
            title="Inline Relationships",
            slug="inline-relationships",
            description="",
            sections=[
                AuthoritySection(
                    key="ex-code:12.001",
                    heading="Section 12.001",
                    text="Seed text.",
                    relationships=(inline,),
                )
            ],
            aliases=None,
            persona_text=None,
            metadata_schema=None,
            entry={},
        )
        manifest_declaration = {
            "source_key": "ex-rule:2026-14",
            "relationship_type": "AMENDS",
            "target_key": "ex-code:12.001",
            "verified": False,
            "metadata": {},
        }

        combined = AuthorityPackLoaderCommand._collect_relationship_declarations(
            [corpus],
            [manifest_declaration],
        )

        self.assertEqual(
            {
                (
                    declaration["source_key"],
                    declaration["relationship_type"],
                    declaration["target_key"],
                )
                for declaration in combined
            },
            {
                ("ex-rule:2026-14", "AMENDS", "ex-code:12.001"),
                ("ex-code:12.001", "IMPLEMENTS", "ex-code:12.002"),
            },
        )
        loaded = AuthorityRelationshipService.load_declarations(
            combined,
            origin=origin,
        )
        self.assertEqual(loaded["created"], 2)

        preserved = [
            AuthorityRelationship.objects.create(
                source_key="ex-code:12.001",
                relationship_type="CITES",
                target_key="manual-law:1",
                source="manual",
                origin="curator",
            ),
            AuthorityRelationship.objects.create(
                source_key="ex-code:12.001",
                relationship_type="CITES",
                target_key="provider-law:1",
                source="provider",
                origin=origin,
            ),
            AuthorityRelationship.objects.create(
                source_key="ex-code:12.001",
                relationship_type="CITES",
                target_key="foreign-law:1",
                source="baseline",
                origin="other-pack",
            ),
        ]

        # Both declaration locations are empty on the next pack reload.
        emptied = AuthorityRelationshipService.load_declarations(
            AuthorityPackLoaderCommand._collect_relationship_declarations([], []),
            origin=origin,
        )

        self.assertEqual(emptied["deleted"], 2)
        self.assertFalse(
            AuthorityRelationship.objects.filter(
                source="baseline",
                origin=origin,
            ).exists()
        )
        self.assertEqual(
            AuthorityRelationship.objects.filter(
                pk__in=[row.pk for row in preserved]
            ).count(),
            3,
        )

    def _load_pack_from_path(self, pack_dir: Path) -> None:
        call_command(
            "load_authority_pack",
            path=str(pack_dir),
            creator=self.owner.username,
            no_relink=True,
            stdout=StringIO(),
        )
