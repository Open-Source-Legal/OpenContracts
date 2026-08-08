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
from django.test import SimpleTestCase, TestCase

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

    def test_bind_missing_prefix_from_registry_rejected(self):
        # A pack may bind only namespaces the taxonomy already created; a
        # prefix with no AuthorityNamespace row at all is a manifest/mappings
        # mismatch and must fail loudly rather than silently no-op.
        corpus = Corpus.objects.create(
            creator=self.owner,
            title="Missing Namespace Target",
            slug="missing-namespace-target",
        )
        service = AuthorityPackLoaderCommand()
        with self.assertRaisesMessage(
            CommandError, "missing from the namespace registry"
        ):
            service._bind_corpus_authority_prefixes(
                corpus_id=corpus.id,
                prefixes=("never-registered",),
                origin="binding_pack",
            )

    def test_bind_prefix_already_bound_to_a_different_corpus_rejected(self):
        # Once a prefix is bound to one corpus, a second corpus (even from the
        # same pack origin) must not silently steal it.
        corpus_a = Corpus.objects.create(
            creator=self.owner, title="Corpus A", slug="corpus-a"
        )
        corpus_b = Corpus.objects.create(
            creator=self.owner, title="Corpus B", slug="corpus-b"
        )
        AuthorityNamespace.objects.create(
            prefix="shared-law",
            display_name="Shared Law",
            authority_type="regulation",
            source="baseline",
            baseline_origin="binding_pack",
        )
        service = AuthorityPackLoaderCommand()
        service._bind_corpus_authority_prefixes(
            corpus_id=corpus_a.id,
            prefixes=("shared-law",),
            origin="binding_pack",
        )
        with self.assertRaisesMessage(CommandError, "already bound to corpus"):
            service._bind_corpus_authority_prefixes(
                corpus_id=corpus_b.id,
                prefixes=("shared-law",),
                origin="binding_pack",
            )

    def test_apply_metadata_schema_rejects_conflicting_data_type(self):
        # A curator-owned column keeps its data_type; a pack reload that
        # declares the same field name with a different type must abort
        # rather than silently overwrite curator-owned schema.
        corpus = Corpus.objects.create(
            creator=self.owner, title="Metadata Conflict", slug="metadata-conflict"
        )
        fieldset = Fieldset.objects.create(
            name="Existing Fieldset",
            description="Pre-existing metadata schema.",
            corpus=corpus,
            creator=self.owner,
        )
        Column.objects.create(
            fieldset=fieldset,
            name="publisher",
            data_type="STRING",
            is_manual_entry=True,
            output_type="string",
            creator=self.owner,
        )
        schema = {
            "version": 1,
            "fields": [{"name": "publisher", "data_type": "INTEGER"}],
        }
        with self.assertRaisesMessage(
            CommandError, "curator-owned schema was not overwritten"
        ):
            AuthorityPackLoaderCommand._apply_metadata_schema(
                corpus.id, schema, self.owner
            )

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

    def test_repeated_edge_across_manifest_and_section_spec_rejected(self):
        # The same (source, type, target) edge declared BOTH inline on a
        # section AND in the manifest relationships file is an authoring
        # mistake, not a harmless duplicate — reject it so a pack reload
        # can't silently drop one of the two declarations.
        inline = SourceRelationship(
            target_key="ex-code:12.002", relationship_type="IMPLEMENTS"
        )
        corpus = _ValidatedCorpus(
            title="Colliding Relationships",
            slug=None,
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
            "source_key": "ex-code:12.001",
            "relationship_type": "IMPLEMENTS",
            "target_key": "ex-code:12.002",
            "verified": False,
            "metadata": {},
        }
        with self.assertRaisesMessage(
            CommandError,
            "repeats relationship edge across its manifest and section specs",
        ):
            AuthorityPackLoaderCommand._collect_relationship_declarations(
                [corpus], [manifest_declaration]
            )

    def _load_pack_from_path(self, pack_dir: Path) -> None:
        call_command(
            "load_authority_pack",
            path=str(pack_dir),
            creator=self.owner.username,
            no_relink=True,
            stdout=StringIO(),
        )


class AuthorityPackEntryValidationTests(TestCase):
    """``_validate_corpus_entry`` structural validation, called in isolation.

    Each malformed shape must abort before any DB write (the whole point of
    validating an entry up front — see the docstring on
    ``_validate_corpus_entry``), so these are pure input -> ``CommandError``
    checks against the method directly rather than a full pack install.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pack_dir = Path(self._tmp.name)

    def _write_spec(self, name: str = "a.json", key: str = "ex-code:1") -> str:
        (self.pack_dir / name).write_text(
            json.dumps({"sections": [{"key": key, "heading": "H", "text": "T"}]}),
            encoding="utf-8",
        )
        return name

    def test_entry_must_be_a_mapping(self):
        with self.assertRaisesMessage(
            CommandError, "Each corpora[] entry must be a mapping."
        ):
            AuthorityPackLoaderCommand()._validate_corpus_entry(
                "not-a-mapping", self.pack_dir  # type: ignore[arg-type]
            )

    def test_title_must_be_a_non_empty_string(self):
        self._write_spec()
        with self.assertRaisesMessage(CommandError, "non-empty string 'title'"):
            AuthorityPackLoaderCommand()._validate_corpus_entry(
                {"title": 123, "spec": "a.json"}, self.pack_dir
            )

    def test_schema_v2_requires_a_stable_slug(self):
        self._write_spec()
        with self.assertRaisesMessage(CommandError, "must declare a stable 'slug'"):
            AuthorityPackLoaderCommand()._validate_corpus_entry(
                {"title": "A", "spec": "a.json"},
                self.pack_dir,
                schema_version=2,
            )

    def test_slug_must_match_the_allowed_pattern(self):
        self._write_spec()
        with self.assertRaisesMessage(CommandError, "lowercase letters/digits/hyphens"):
            AuthorityPackLoaderCommand()._validate_corpus_entry(
                {"title": "A", "spec": "a.json", "slug": "Bad Slug!"},
                self.pack_dir,
            )

    def test_description_must_be_a_string(self):
        self._write_spec()
        with self.assertRaisesMessage(CommandError, "description must be a string"):
            AuthorityPackLoaderCommand()._validate_corpus_entry(
                {"title": "A", "spec": "a.json", "description": 123},
                self.pack_dir,
            )

    def test_schema_v2_requires_a_charter(self):
        self._write_spec()
        with self.assertRaisesMessage(CommandError, "needs a 'charter'"):
            AuthorityPackLoaderCommand()._validate_corpus_entry(
                {"title": "A", "spec": "a.json", "slug": "a"},
                self.pack_dir,
                schema_version=2,
            )

    def test_charter_must_declare_a_non_empty_purpose(self):
        self._write_spec()
        (self.pack_dir / "charter.yaml").write_text(
            "legal_owner: null\n", encoding="utf-8"
        )
        with self.assertRaisesMessage(
            CommandError, "charter must declare a non-empty 'purpose'"
        ):
            AuthorityPackLoaderCommand()._validate_corpus_entry(
                {"title": "A", "spec": "a.json", "charter": "charter.yaml"},
                self.pack_dir,
            )

    def test_unknown_default_authority_weight_rejected(self):
        self._write_spec()
        with self.assertRaisesMessage(CommandError, "unknown default_authority_weight"):
            AuthorityPackLoaderCommand()._validate_corpus_entry(
                {
                    "title": "A",
                    "spec": "a.json",
                    "default_authority_weight": "NOT_A_REAL_WEIGHT",
                },
                self.pack_dir,
            )


class AuthorityPackAuthorityPrefixValidationTests(SimpleTestCase):
    """``_validate_authority_prefixes`` — no DB, no pack files needed."""

    def test_prefix_must_be_valid_and_at_most_64_chars(self):
        with self.assertRaisesMessage(CommandError, "at most 64 characters"):
            AuthorityPackLoaderCommand._validate_authority_prefixes(
                {"authority_prefixes": ["Not A Valid Prefix!"]}, title="A"
            )

    def test_prefix_cannot_repeat_within_one_corpus(self):
        with self.assertRaisesMessage(CommandError, "repeats authority prefix"):
            AuthorityPackLoaderCommand._validate_authority_prefixes(
                {"authority_prefixes": ["dup-law", "dup-law"]}, title="A"
            )


class AuthorityPackYamlMappingReadTests(SimpleTestCase):
    """``_read_yaml_mapping`` — the shared charter/mappings/metadata reader."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pack_dir = Path(self._tmp.name)

    def test_missing_file_rejected(self):
        missing = self.pack_dir / "missing.yaml"
        with self.assertRaisesMessage(CommandError, "not found"):
            AuthorityPackLoaderCommand._read_yaml_mapping(missing, label="thing")

    def test_malformed_yaml_rejected(self):
        path = self.pack_dir / "bad.yaml"
        path.write_text("key: [unterminated", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "Could not parse"):
            AuthorityPackLoaderCommand._read_yaml_mapping(path, label="thing")

    def test_non_mapping_yaml_rejected(self):
        path = self.pack_dir / "list.yaml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "must contain a mapping"):
            AuthorityPackLoaderCommand._read_yaml_mapping(path, label="thing")


class AuthorityPackMetadataSchemaValidationTests(SimpleTestCase):
    """``_read_metadata_schema`` — every malformed shape, in isolation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pack_dir = Path(self._tmp.name)

    def _write(self, name: str, data: dict) -> Path:
        path = self.pack_dir / name
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return path

    def test_unsupported_version_rejected(self):
        path = self._write("m1.yaml", {"version": 2, "fields": []})
        with self.assertRaisesMessage(CommandError, "unsupported version"):
            AuthorityPackLoaderCommand._read_metadata_schema(path, title="A")

    def test_empty_fields_rejected(self):
        path = self._write("m2.yaml", {"version": 1, "fields": []})
        with self.assertRaisesMessage(CommandError, "non-empty 'fields' list"):
            AuthorityPackLoaderCommand._read_metadata_schema(path, title="A")

    def test_field_must_be_a_mapping(self):
        path = self._write("m3.yaml", {"version": 1, "fields": ["not-a-mapping"]})
        with self.assertRaisesMessage(CommandError, "must be a mapping"):
            AuthorityPackLoaderCommand._read_metadata_schema(path, title="A")

    def test_field_needs_a_name(self):
        path = self._write(
            "m4.yaml", {"version": 1, "fields": [{"data_type": "STRING"}]}
        )
        with self.assertRaisesMessage(CommandError, "needs a name"):
            AuthorityPackLoaderCommand._read_metadata_schema(path, title="A")

    def test_field_name_cannot_repeat(self):
        path = self._write(
            "m5.yaml",
            {
                "version": 1,
                "fields": [
                    {"name": "x", "data_type": "STRING"},
                    {"name": "x", "data_type": "STRING"},
                ],
            },
        )
        with self.assertRaisesMessage(CommandError, "repeats field"):
            AuthorityPackLoaderCommand._read_metadata_schema(path, title="A")

    def test_invalid_data_type_rejected(self):
        path = self._write(
            "m6.yaml", {"version": 1, "fields": [{"name": "x", "data_type": "NOPE"}]}
        )
        with self.assertRaisesMessage(CommandError, "invalid data_type"):
            AuthorityPackLoaderCommand._read_metadata_schema(path, title="A")

    def test_validation_config_must_be_a_mapping(self):
        path = self._write(
            "m7.yaml",
            {
                "version": 1,
                "fields": [
                    {
                        "name": "x",
                        "data_type": "STRING",
                        "validation_config": ["nope"],
                    }
                ],
            },
        )
        with self.assertRaisesMessage(
            CommandError, "validation_config must be a mapping"
        ):
            AuthorityPackLoaderCommand._read_metadata_schema(path, title="A")

    def test_choice_field_requires_choices(self):
        path = self._write(
            "m8.yaml",
            {
                "version": 1,
                "fields": [
                    {"name": "x", "data_type": "CHOICE", "validation_config": {}}
                ],
            },
        )
        with self.assertRaisesMessage(
            CommandError, "requires validation_config.choices"
        ):
            AuthorityPackLoaderCommand._read_metadata_schema(path, title="A")


class AuthorityPackUniqueSlugValidationTests(SimpleTestCase):
    def test_duplicate_corpus_slugs_rejected(self):
        duplicated = [
            _ValidatedCorpus(
                title=f"T{i}",
                slug="dup-slug",
                description="",
                sections=[],
                aliases=None,
                persona_text=None,
                metadata_schema=None,
                entry={},
            )
            for i in range(2)
        ]
        with self.assertRaisesMessage(CommandError, "repeats corpus slug"):
            AuthorityPackLoaderCommand._validate_unique_corpus_slugs(duplicated)


class AuthorityPackCorpusIdentityTests(TestCase):
    """``_preflight_corpus_identities`` — resolving v2 stable slugs against
    pre-existing corpora owned by the same creator."""

    def setUp(self):
        self.owner = User.objects.create_user(username="identity-owner")

    @staticmethod
    def _spec(*, title: str, slug: str) -> _ValidatedCorpus:
        return _ValidatedCorpus(
            title=title,
            slug=slug,
            description="",
            sections=[],
            aliases=None,
            persona_text=None,
            metadata_schema=None,
            entry={},
        )

    def test_ambiguous_title_match_rejected(self):
        # Two existing corpora share a title (no unique constraint on title
        # alone) but have distinct slugs; a pack declaring a THIRD, new slug
        # for that title cannot tell which one it means.
        Corpus.objects.create(creator=self.owner, title="Dup Title", slug="slug-a")
        Corpus.objects.create(creator=self.owner, title="Dup Title", slug="slug-b")
        with self.assertRaisesMessage(CommandError, "ambiguous for creator"):
            AuthorityPackLoaderCommand._preflight_corpus_identities(
                [self._spec(title="Dup Title", slug="slug-c")], self.owner
            )

    def test_title_match_with_conflicting_existing_slug_rejected(self):
        # A pre-existing corpus already has ITS OWN slug; a pack trying to
        # claim the same title with a DIFFERENT slug must not silently
        # re-point it.
        Corpus.objects.create(
            creator=self.owner, title="Solo Title", slug="existing-slug"
        )
        with self.assertRaisesMessage(CommandError, "already has slug"):
            AuthorityPackLoaderCommand._preflight_corpus_identities(
                [self._spec(title="Solo Title", slug="new-slug")], self.owner
            )

    def test_legacy_unslugged_corpus_adopts_the_declared_slug(self):
        # A corpus created before slugs were mandatory (simulated here via a
        # direct ``.update()`` — ``Corpus.save()`` always auto-generates a
        # slug, so this state cannot arise through the normal ORM path but is
        # exactly the historical-data shape the fallback exists to handle).
        legacy = Corpus.objects.create(creator=self.owner, title="Legacy Title")
        Corpus.objects.filter(pk=legacy.pk).update(slug=None)
        resolved = AuthorityPackLoaderCommand._preflight_corpus_identities(
            [self._spec(title="Legacy Title", slug="new-slug")], self.owner
        )
        self.assertEqual(resolved, {"new-slug": legacy.id})


class AuthorityPackDeclaredPrefixValidationTests(SimpleTestCase):
    """``_validate_declared_prefixes`` — every key/prefix must trace to the
    pack's own mappings 'prefixes' declaration."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pack_dir = Path(self._tmp.name)

    def _write_mappings(self, prefixes: dict) -> Path:
        path = self.pack_dir / "mappings.yaml"
        path.write_text(yaml.safe_dump({"prefixes": prefixes}), encoding="utf-8")
        return path

    def test_mappings_prefixes_must_be_non_empty(self):
        path = self._write_mappings({})
        with self.assertRaisesMessage(CommandError, "non-empty 'prefixes' mapping"):
            AuthorityPackLoaderCommand._validate_declared_prefixes(path, [], [])

    def test_section_key_prefix_must_be_declared(self):
        path = self._write_mappings({"ex-code": {"display_name": "Ex Code"}})
        corpus = _ValidatedCorpus(
            title="A",
            slug=None,
            description="",
            sections=[AuthoritySection(key="undeclared:1", heading="H", text="T")],
            aliases=None,
            persona_text=None,
            metadata_schema=None,
            entry={},
        )
        with self.assertRaisesMessage(CommandError, "key 'undeclared:1' uses prefix"):
            AuthorityPackLoaderCommand._validate_declared_prefixes(path, [corpus], [])

    def test_relationship_source_prefix_must_be_declared(self):
        path = self._write_mappings({"ex-code": {"display_name": "Ex Code"}})
        with self.assertRaisesMessage(
            CommandError, "Relationship source 'undeclared:1' uses prefix"
        ):
            AuthorityPackLoaderCommand._validate_declared_prefixes(
                path,
                [],
                [
                    {
                        "source_key": "undeclared:1",
                        "relationship_type": "CITES",
                        "target_key": "ex-code:1",
                    }
                ],
            )


class AuthorityPackRelationshipFileValidationTests(SimpleTestCase):
    """``_read_relationships`` — malformed relationships.yaml shapes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pack_dir = Path(self._tmp.name)

    def _write(self, name: str, content: str) -> str:
        (self.pack_dir / name).write_text(content, encoding="utf-8")
        return name

    def test_schema_version_must_be_1(self):
        rel = self._write("r1.yaml", "schema_version: 2\nrelationships: []\n")
        with self.assertRaisesMessage(CommandError, "schema_version must be 1"):
            AuthorityPackLoaderCommand._read_relationships(
                {"relationships": rel}, self.pack_dir
            )

    def test_relationships_key_must_be_a_list(self):
        rel = self._write("r2.yaml", "relationships: not-a-list\n")
        with self.assertRaisesMessage(
            CommandError, "must contain a 'relationships' list"
        ):
            AuthorityPackLoaderCommand._read_relationships(
                {"relationships": rel}, self.pack_dir
            )

    def test_relationship_entry_must_be_a_mapping(self):
        rel = self._write("r3.yaml", "relationships:\n  - just-a-string\n")
        with self.assertRaisesMessage(CommandError, "must be a mapping"):
            AuthorityPackLoaderCommand._read_relationships(
                {"relationships": rel}, self.pack_dir
            )

    def test_source_key_must_match_canonical_shape(self):
        rel = self._write(
            "r4.yaml",
            (
                "relationships:\n"
                "  - source_key: 'BAD KEY'\n"
                "    relationship_type: CITES\n"
                "    target_key: ex-code:1\n"
            ),
        )
        with self.assertRaisesMessage(CommandError, "has invalid source_key"):
            AuthorityPackLoaderCommand._read_relationships(
                {"relationships": rel}, self.pack_dir
            )

    def test_repeated_edge_within_the_file_rejected(self):
        rel = self._write(
            "r5.yaml",
            (
                "relationships:\n"
                "  - source_key: ex-code:1\n"
                "    relationship_type: CITES\n"
                "    target_key: ex-code:2\n"
                "  - source_key: ex-code:1\n"
                "    relationship_type: CITES\n"
                "    target_key: ex-code:2\n"
            ),
        )
        with self.assertRaisesMessage(CommandError, "repeats edge"):
            AuthorityPackLoaderCommand._read_relationships(
                {"relationships": rel}, self.pack_dir
            )
