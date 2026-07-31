"""Static contract tests for the four GridDossier authority packs.

These tests deliberately avoid database access. Provider parser behavior lives
in provider-specific tests; this module protects the portable data contract
shared by pack loading, provider routing, and Corpus Group composition.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from urllib.parse import urlparse

import yaml

from opencontractserver.enrichment.authority_sources import (
    AuthoritySourceRecord,
    SourceRelationship,
)
from opencontractserver.enrichment.constants import ALL_AUTHORITY_TYPES
from opencontractserver.enrichment.data.mappings import (
    iter_equivalences,
    iter_prefixes,
    iter_rewrite_rules,
    load_mappings_file,
)

PACK_ROOT = (
    Path(__file__).resolve().parents[1] / "enrichment" / "data" / "authority_packs"
)

EXPECTED_CORPORA = {
    "texas_electric_law": [
        ("texas-electric-statutes", "Texas Electric Statutes"),
        (
            "texas-large-load-legislative-history",
            "Texas Large-Load Legislative History",
        ),
    ],
    "puct_electric": [
        (
            "puct-electric-rules-and-orders",
            "PUCT Electric Rules and Controlling Orders",
        ),
        ("puct-large-load-proceedings", "PUCT Large-Load Proceedings"),
    ],
    "ercot_large_load": [
        ("ercot-current-large-load-rules", "ERCOT Current Large-Load Rules"),
        (
            "ercot-large-load-revision-history",
            "ERCOT Large-Load Revision History",
        ),
        (
            "ercot-large-load-implementation",
            "ERCOT Large-Load Implementation Materials",
        ),
    ],
    "oncor_delivery": [
        ("oncor-current-delivery-tariff", "Oncor Current Delivery Tariff"),
        (
            "oncor-tariff-history",
            "Oncor Tariff History and Regulatory Filings",
        ),
        (
            "oncor-service-requirements",
            "Oncor Service and Construction Requirements",
        ),
    ],
}

EXPECTED_METADATA_FIELDS = {
    "authority_family",
    "instrument_type",
    "publisher",
    "jurisdiction",
    "canonical_key",
    "source_identifier",
    "source_url",
    "parent_proceeding",
    "filed_date",
    "issued_date",
    "published_date",
    "effective_from",
    "effective_until",
    "effective_date_review_status",
    "status",
    "authority_weight",
    "current_version",
    "version_label",
    "supersedes_key",
    "superseded_by_key",
    "adopts_key",
    "rejects_key",
    "amends_key",
    "retrieved_at",
    "content_hash",
    "source_mime_type",
}

METADATA_DATA_TYPES = {
    "STRING",
    "TEXT",
    "BOOLEAN",
    "INTEGER",
    "FLOAT",
    "DATE",
    "DATETIME",
    "URL",
    "EMAIL",
    "CHOICE",
    "MULTI_CHOICE",
    "JSON",
}


def _yaml(path: Path) -> dict:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"{path} does not contain a YAML mapping")
    return parsed


class GridDossierAuthorityPackDataTests(TestCase):
    def test_manifests_declare_exact_portable_corpora(self):
        seen_slugs: set[str] = set()
        seen_titles: set[str] = set()

        for pack_name, expected_corpora in EXPECTED_CORPORA.items():
            pack_dir = PACK_ROOT / pack_name
            manifest = _yaml(pack_dir / "pack.yaml")

            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["name"], pack_name)
            self.assertTrue((pack_dir / manifest["mappings"]).is_file())
            self.assertTrue((pack_dir / manifest["metadata_schema"]).is_file())
            self.assertTrue((pack_dir / manifest["relationships"]).is_file())

            actual_corpora = [
                (entry["slug"], entry["title"]) for entry in manifest["corpora"]
            ]
            self.assertEqual(actual_corpora, expected_corpora)
            for entry in manifest["corpora"]:
                for field in ("charter", "spec", "persona", "metadata_schema"):
                    self.assertTrue(
                        (pack_dir / entry[field]).is_file(),
                        f"{pack_name}: missing {field} file for {entry['slug']}",
                    )
                charter = _yaml(pack_dir / entry["charter"])
                self.assertEqual(charter["slug"], entry["slug"])
                self.assertEqual(charter["title"], entry["title"])
                self.assertTrue(charter["purpose"].strip())
                self.assertEqual(charter["approval_status"], "pending_legal_review")

            for slug, title in actual_corpora:
                self.assertNotIn(slug, seen_slugs)
                self.assertNotIn(title, seen_titles)
                seen_slugs.add(slug)
                seen_titles.add(title)

        self.assertEqual(len(seen_slugs), 10)
        self.assertEqual(len(seen_titles), 10)

    def test_mappings_specs_and_relationship_sources_use_owned_prefixes(self):
        core_prefixes = set(iter_prefixes(load_mappings_file()))
        pack_prefix_owners: dict[str, str] = {}

        for pack_name in EXPECTED_CORPORA:
            pack_dir = PACK_ROOT / pack_name
            manifest = _yaml(pack_dir / "pack.yaml")
            mappings_data = load_mappings_file(pack_dir / manifest["mappings"])
            prefixes = iter_prefixes(mappings_data)
            iter_equivalences(mappings_data)
            iter_rewrite_rules(mappings_data)

            for prefix, spec in prefixes.items():
                self.assertNotIn(prefix, core_prefixes)
                self.assertNotIn(prefix, pack_prefix_owners)
                self.assertIn(spec["authority_type"], ALL_AUTHORITY_TYPES)
                pack_prefix_owners[prefix] = pack_name

            for corpus in manifest["corpora"]:
                spec = json.loads(
                    (pack_dir / corpus["spec"]).read_text(encoding="utf-8")
                )
                self.assertTrue(spec["sections"])
                for section in spec["sections"]:
                    self.assertTrue(section["heading"])
                    self.assertTrue(section["text"])
                    self.assertIn(section["key"].split(":", 1)[0], prefixes)

            relationships = _yaml(pack_dir / manifest["relationships"])["relationships"]
            identities: set[tuple[str, str, str]] = set()
            for declaration in relationships:
                self.assertIn(declaration["source_key"].split(":", 1)[0], prefixes)
                relation = SourceRelationship(
                    target_key=declaration["target_key"],
                    relationship_type=declaration["relationship_type"],
                    verified=declaration["verified"],
                    metadata=declaration["metadata"],
                )
                identity = (
                    declaration["source_key"],
                    str(relation.relationship_type),
                    relation.target_key,
                )
                self.assertNotIn(identity, identities)
                identities.add(identity)

        self.assertEqual(len(pack_prefix_owners), 16)

    def test_shared_metadata_schema_is_complete_and_identical(self):
        serialized_schemas: set[str] = set()

        for pack_name in EXPECTED_CORPORA:
            pack_dir = PACK_ROOT / pack_name
            manifest = _yaml(pack_dir / "pack.yaml")
            schema_path = pack_dir / manifest["metadata_schema"]
            schema = _yaml(schema_path)
            self.assertEqual(set(schema), {"version", "fields"})
            self.assertEqual(schema["version"], 1)

            fields = schema["fields"]
            names = [field["name"] for field in fields]
            self.assertEqual(set(names), EXPECTED_METADATA_FIELDS)
            self.assertEqual(len(names), len(set(names)))
            for field in fields:
                self.assertIn(field["data_type"], METADATA_DATA_TYPES)
                self.assertIsInstance(field.get("validation_config", {}), dict)
                if field["data_type"] in {"CHOICE", "MULTI_CHOICE"}:
                    self.assertTrue(field["validation_config"]["choices"])

            serialized_schemas.add(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            len(serialized_schemas),
            1,
            "portable packs must ship the same shared metadata contract",
        )

    def test_golden_source_records_conform_to_shared_record_contract(self):
        for pack_name, expected_corpora in EXPECTED_CORPORA.items():
            pack_dir = PACK_ROOT / pack_name
            manifest = _yaml(pack_dir / "pack.yaml")
            allowed_hosts = manifest["source_hosts"]
            corpus_slugs = {slug for slug, _title in expected_corpora}
            fixture = json.loads(
                (pack_dir / "fixtures" / "source_records.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(fixture["review_status"], "pending_legal_review")
            self.assertTrue(fixture["records"])

            for raw_record in fixture["records"]:
                hostname = urlparse(raw_record["source_url"]).hostname or ""
                self.assertTrue(
                    any(
                        hostname == allowed or hostname.endswith(f".{allowed}")
                        for allowed in allowed_hosts
                    ),
                    f"{raw_record['source_url']} is outside {allowed_hosts}",
                )
                self.assertIn(raw_record["corpus_slug"], corpus_slugs)
                record_data = dict(raw_record)
                record_data["relationships"] = tuple(
                    SourceRelationship(**relationship)
                    for relationship in raw_record["relationships"]
                )
                record_data["content"] = (
                    f"Deterministic golden content for {raw_record['canonical_key']}."
                ).encode()
                record = AuthoritySourceRecord(**record_data)
                self.assertIsInstance(record.current_version, bool)
                self.assertNotIn("current_version", record.metadata)

    def test_oncor_history_uses_immutable_version_identity(self):
        pack_dir = PACK_ROOT / "oncor_delivery"
        fixture = json.loads(
            (pack_dir / "fixtures" / "source_records.json").read_text(encoding="utf-8")
        )
        by_key = {record["canonical_key"]: record for record in fixture["records"]}
        logical_key = "oncor-tariff:retail-delivery"
        historical_key = "oncor-tariff:retail-delivery-2017-11-27"

        self.assertIn(logical_key, by_key)
        self.assertIn(historical_key, by_key)
        self.assertTrue(by_key[logical_key]["current_version"])
        self.assertFalse(by_key[historical_key]["current_version"])
        self.assertEqual(by_key[historical_key]["effective_from"], "2017-11-27")
        self.assertEqual(by_key[historical_key]["version_label"], "revision-20")
        self.assertNotIn("fixture_only", by_key[historical_key]["metadata"])
        edges = {
            (edge["relationship_type"], edge["target_key"])
            for edge in by_key[historical_key]["relationships"]
        }
        self.assertIn(("EFFECTIVE_VERSION_OF", logical_key), edges)
        self.assertIn(("SUPERSEDED_BY", logical_key), edges)

    def test_every_declared_prefix_is_bound_to_exactly_one_pack_corpus(self):
        """Each pack must say which of its corpora owns each citation prefix.

        This is not bookkeeping. ``_reconcile_archive_authority_metadata``
        (``opencontractserver/tasks/import_tasks_v2.py``) only reconciles typed
        metadata and promotes provider-authored relationships for documents
        whose canonical-key prefix is bound to the corpus being imported, and it
        returns immediately when the target corpus owns no prefix at all. A pack
        that declares a prefix in its mappings but never assigns it to a corpus
        therefore imports its documents with their relationships stranded in
        ``custom_meta`` and never reaching ``AuthorityRelationship`` — silently,
        and without failing any import.

        A prefix binds to at most one corpus (``_bind_corpus_authority_prefixes``
        refuses to move an already-bound prefix), so this is a partition.
        """
        for pack_name in EXPECTED_CORPORA:
            with self.subTest(pack=pack_name):
                manifest = _yaml(PACK_ROOT / pack_name / "pack.yaml")
                mappings_name = manifest["mappings"]
                declared = set(
                    _yaml(PACK_ROOT / pack_name / mappings_name).get("prefixes", {})
                )
                self.assertTrue(declared, f"{pack_name} declares no citation prefixes")

                bound: dict[str, str] = {}
                for corpus in manifest["corpora"]:
                    for prefix in corpus.get("authority_prefixes", []):
                        self.assertNotIn(
                            prefix,
                            bound,
                            f"{pack_name} binds {prefix!r} to both "
                            f"{bound.get(prefix)!r} and {corpus['slug']!r}; a "
                            "prefix may own exactly one corpus",
                        )
                        bound[prefix] = corpus["slug"]

                self.assertEqual(
                    set(bound),
                    declared,
                    f"{pack_name}: every declared prefix must be bound to one of "
                    "its corpora via 'authority_prefixes', or sideloaded imports "
                    "silently drop that prefix's authority relationships. "
                    f"Unbound: {sorted(declared - set(bound))}; "
                    f"bound but undeclared: {sorted(set(bound) - declared)}",
                )
