"""Tests for the external authority-source -> ordinary corpus-export bridge.

The collector is intentionally an operator-side sideload tool.  These tests
exercise source-plan validation, the no-fetch link-only boundary, the existing
rights gate, and the V2 artifact contract without invoking an API, view, or
Celery task.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import yaml

from opencontractserver.enrichment.authority_import_artifacts import (
    CollectedAuthorityRecord,
    SourcePlanError,
    build_authority_import_artifacts,
    collect_from_source_plan,
    read_source_plan,
)
from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    RightsStatus,
    SourceRelationship,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    DiscoveryCandidate,
    DiscoveryResult,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.validate_export import validate_export


def _authority_metadata(**overrides) -> dict:
    metadata = {
        "authority_family": "example-family",
        "instrument_type": "REGULATION",
        "publisher": "Example Publisher",
        "jurisdiction": "example",
        "status": "CURRENT",
        "authority_weight": "CONTROLLING",
    }
    metadata.update(overrides)
    return metadata


class _FakeAuthoritySourceProvider(BaseAuthoritySourceProvider):
    supported_prefixes = ("example",)
    license = "public-domain"
    fetch_calls = 0
    rights_status = RightsStatus.PUBLIC_DOMAIN
    link_manifest = False
    last_fetch_kwargs: dict = {}
    relationships: tuple[SourceRelationship, ...] = ()

    def get_component_settings(self) -> dict:
        return {}

    def _locate_impl(self, canonical_key: str, **kwargs) -> AuthorityRequest:
        candidate = kwargs.get("discovery_candidate")
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=(
                candidate.url
                if candidate is not None and candidate.url
                else f"https://publisher.example/{canonical_key.split(':', 1)[1]}"
            ),
            citation=f"Publisher citation {canonical_key}",
        )

    def _fetch_impl(self, request: AuthorityRequest, **kwargs):
        type(self).fetch_calls += 1
        type(self).last_fetch_kwargs = dict(kwargs)
        html = (
            b"Link-only authority source\nOfficial source: https://publisher.example/1"
            if type(self).link_manifest
            else (
                b"<html><body><h1>Official Rule</h1><p>Verified body text.</p>"
                b"</body></html>"
            )
        )
        return [
            AuthoritySourceRecord(
                canonical_key=request.canonical_key,
                title="Publisher title",
                source_url=request.url,
                source_identifier=request.canonical_key,
                publisher="Example Publisher",
                jurisdiction="example",
                authority_type="regulation",
                instrument_type="REGULATION",
                issued_date="2026-01-02",
                effective_from="2026-02-03",
                effective_until=None,
                status="CURRENT",
                authority_weight="CONTROLLING",
                parent_key=None,
                version_label="2026",
                content=html,
                mime_type="text/html",
                corpus_slug="example-corpus",
                metadata={"link_only": True} if type(self).link_manifest else {},
                retrieved_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
                rights_status=type(self).rights_status,
                relationships=type(self).relationships,
                extracted_text=(
                    "Link-only authority source\nOfficial source: "
                    "https://publisher.example/1"
                    if type(self).link_manifest
                    else "Official Rule\n\nVerified body text."
                ),
                publisher_evidence=(
                    AuthorityPublisherEvidence(
                        source="SOURCE_IDENTIFIER",
                        value=request.canonical_key,
                        locator=request.url,
                    ),
                ),
            )
        ]

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        return any(
            evidence.value == canonical_key for evidence in record.publisher_evidence
        )


class _FakeAuthorityDiscoveryProvider:
    candidate_extra: dict = {}
    capped = False

    def discover_candidates(self, index_urls, **kwargs) -> DiscoveryResult:
        del kwargs
        return DiscoveryResult(
            candidates=[
                DiscoveryCandidate(
                    canonical_key="example:live",
                    url="https://publisher.example/live",
                    title="Live publisher title",
                    extra={
                        "index_url": index_urls[0],
                        **self.candidate_extra,
                    },
                )
            ],
            skipped_index_urls={},
            capped=type(self).capped,
        )


def _provider_definition() -> SimpleNamespace:
    return SimpleNamespace(
        name="_FakeAuthoritySourceProvider",
        class_name=(
            "opencontractserver.tests.test_authority_import_artifacts."
            "_FakeAuthoritySourceProvider"
        ),
        component_class=_FakeAuthoritySourceProvider,
    )


def _discovery_definition() -> SimpleNamespace:
    return SimpleNamespace(
        name="_FakeAuthorityDiscoveryProvider",
        class_name=(
            "opencontractserver.tests.test_authority_import_artifacts."
            "_FakeAuthorityDiscoveryProvider"
        ),
        component_class=_FakeAuthorityDiscoveryProvider,
    )


class AuthorityImportArtifactTests(TestCase):
    def setUp(self):
        _FakeAuthoritySourceProvider.fetch_calls = 0
        _FakeAuthoritySourceProvider.rights_status = RightsStatus.PUBLIC_DOMAIN
        _FakeAuthoritySourceProvider.link_manifest = False
        _FakeAuthoritySourceProvider.last_fetch_kwargs = {}
        _FakeAuthoritySourceProvider.relationships = ()
        _FakeAuthorityDiscoveryProvider.candidate_extra = {}
        _FakeAuthorityDiscoveryProvider.capped = False
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.pack_dir = Path(self._temporary.name)
        self._write_pack()

    def _write_pack(self, *, source: dict | None = None) -> None:
        manifest = {
            "schema_version": 2,
            "name": "example_pack",
            "display_name": "Example Pack",
            "sources": "sources.yaml",
            "source_hosts": ["publisher.example"],
            "corpora": [
                {
                    "slug": "example-corpus",
                    "title": "Example Corpus",
                    "description": "An external sideload corpus.",
                }
            ],
        }
        plan = {
            "schema_version": 1,
            "sources": [
                source
                or {
                    "id": "example",
                    "ingestion_mode": "full_content",
                    "corpus_slug": "example-corpus",
                    "source_provider": "_FakeAuthoritySourceProvider",
                    "candidates": [
                        {
                            "canonical_key": "example:1",
                            "url": "https://publisher.example/1",
                            "publisher_title": "Publisher title",
                            "display_title": "[REVIEWED] Display title",
                            "extra": {"source_identifier": "publisher-1"},
                        }
                    ],
                }
            ],
        }
        (self.pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )
        (self.pack_dir / "sources.yaml").write_text(
            yaml.safe_dump(plan, sort_keys=False), encoding="utf-8"
        )

    def _collect(self, *, rights_approved: bool = False):
        with patch(
            "opencontractserver.enrichment.authority_import_artifacts."
            "_provider_definitions",
            return_value=(
                [_provider_definition()],
                [_discovery_definition()],
            ),
        ):
            return collect_from_source_plan(
                self.pack_dir, rights_approved=rights_approved
            )

    def _converter_source_record(
        self,
        *,
        extension: str,
        mime_type: str,
        content: bytes,
        extraction_deferred: bool = False,
    ) -> AuthoritySourceRecord:
        metadata = {}
        extracted_text = f"Verified extracted text for {extension.upper()}"
        if extraction_deferred:
            metadata = {
                "text_extraction_deferred_to_pipeline": True,
                "text_extraction_source_extension": extension,
            }
            extracted_text = None
        return AuthoritySourceRecord(
            canonical_key=f"example:converter-{extension}",
            title=f"Official {extension.upper()} source",
            source_url=f"https://publisher.example/official-source.{extension}",
            source_identifier=f"publisher-{extension}",
            publisher="Example Publisher",
            jurisdiction="example",
            authority_type="regulation",
            instrument_type="REGULATION",
            issued_date="2026-01-02",
            effective_from="2026-02-03",
            effective_until=None,
            status="CURRENT",
            authority_weight="CONTROLLING",
            parent_key=None,
            version_label="2026",
            content=content,
            mime_type=mime_type,
            corpus_slug="example-corpus",
            metadata=metadata,
            retrieved_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            extracted_text=extracted_text,
        )

    def test_source_plan_rejects_http_and_parallel_candidate_modes(self):
        self._write_pack(
            source={
                "id": "bad",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": [
                    {
                        "canonical_key": "example:1",
                        "url": "http://publisher.example/1",
                    }
                ],
                "canonical_keys": ["example:1"],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "exactly one of discovery_provider"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

        self._write_pack(
            source={
                "id": "bad-http",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": [
                    {
                        "canonical_key": "example:1",
                        "url": "http://publisher.example/1",
                    }
                ],
            }
        )
        with self.assertRaisesRegex(SourcePlanError, "must be an HTTPS URL"):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_link_only_locates_but_never_fetches_publisher_content(self):
        self._write_pack(
            source={
                "id": "rights-pending",
                "ingestion_mode": "link_only",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "metadata": _authority_metadata(
                    publisher="Source default publisher",
                    status="PUBLISHED",
                ),
                "parent_relationship_type": "FILED_IN",
                "candidates": [
                    {
                        "canonical_key": "example:1",
                        "url": "https://publisher.example/1",
                        "publisher_title": "Publisher title",
                        "display_title": "[LEGAL REVIEW REQUIRED] Display title",
                        "metadata": {
                            "publisher": "Candidate publisher",
                            "status": "PENDING",
                            "candidate_only": "preserved",
                        },
                        "extra": {
                            "source_identifier": "publisher-1",
                            "parent_key": "example-proceeding:7",
                            "current_version": False,
                        },
                    }
                ],
            }
        )

        records, report = self._collect()

        self.assertEqual(_FakeAuthoritySourceProvider.fetch_calls, 0)
        self.assertEqual(report.fetched, 0)
        self.assertEqual(report.linked, 1)
        self.assertFalse(report.errors)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].ingestion_mode, "link_only")
        self.assertEqual(records[0].record.metadata["source_identifier"], "publisher-1")
        self.assertEqual(records[0].record.metadata["publisher"], "Candidate publisher")
        self.assertEqual(records[0].record.metadata["status"], "PENDING")
        self.assertEqual(records[0].record.metadata["candidate_only"], "preserved")
        self.assertEqual(
            records[0].record.metadata["review_status"],
            "pending_legal_review",
        )
        self.assertIs(records[0].record.metadata["current_version"], False)
        self.assertEqual(
            records[0].record.metadata["parent_proceeding"],
            "example-proceeding:7",
        )
        self.assertNotIn(
            "metadata",
            records[0].record.metadata["discovery_metadata"],
        )
        self.assertEqual(
            [
                relationship.as_dict()
                for relationship in records[0].record.relationships
            ],
            [
                {
                    "target_key": "example-proceeding:7",
                    "relationship_type": "FILED_IN",
                    "verified": False,
                    "metadata": {
                        "review_status": "pending_legal_review",
                        "source_plan_id": "rights-pending",
                        "provenance": "source_plan_parent_key",
                        "candidate_url": "https://publisher.example/1",
                    },
                }
            ],
        )
        self.assertIn("Official source:", records[0].record.text)

    def test_link_only_fails_closed_when_required_authority_metadata_is_missing(self):
        incomplete = _authority_metadata()
        incomplete.pop("authority_weight")
        self._write_pack(
            source={
                "id": "incomplete-link",
                "ingestion_mode": "link_only",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "metadata": incomplete,
                "candidates": [
                    {
                        "canonical_key": "example:1",
                        "url": "https://publisher.example/1",
                    }
                ],
            }
        )

        records, report = self._collect()

        self.assertFalse(records)
        self.assertEqual(_FakeAuthoritySourceProvider.fetch_calls, 0)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("authority_weight", report.errors[0]["error"])

    def test_live_candidate_nested_metadata_overrides_defaults_and_is_stripped(self):
        _FakeAuthorityDiscoveryProvider.candidate_extra = {
            "metadata": {
                "publisher": "Live candidate publisher",
                "status": "PENDING",
                "provider_field": "live",
                "review_status": "reviewed",
            },
            "current_version": True,
            "version_label": None,
            "parent_key": "example-proceeding:live",
        }
        source = {
            "id": "live-link",
            "ingestion_mode": "link_only",
            "corpus_slug": "example-corpus",
            "source_provider": "_FakeAuthoritySourceProvider",
            "discovery_provider": "_FakeAuthorityDiscoveryProvider",
            "index_urls": ["https://publisher.example/index"],
            "metadata": _authority_metadata(),
            "parent_relationship_type": "FILED_IN",
        }
        self._write_pack(source=source)

        records, report = self._collect()

        self.assertFalse(report.errors)
        self.assertEqual(len(records), 1)
        metadata = records[0].record.metadata
        self.assertEqual(metadata["publisher"], "Live candidate publisher")
        self.assertEqual(metadata["status"], "PENDING")
        self.assertEqual(metadata["provider_field"], "live")
        self.assertEqual(metadata["review_status"], "reviewed")
        self.assertIs(metadata["current_version"], True)
        self.assertNotIn("version_label", metadata)
        self.assertNotIn("metadata", metadata["discovery_metadata"])
        self.assertEqual(metadata["parent_proceeding"], "example-proceeding:live")
        self.assertEqual(
            records[0].record.relationships[0].metadata,
            {
                "review_status": "pending_legal_review",
                "source_plan_id": "live-link",
                "provenance": "source_plan_parent_key",
                "candidate_url": "https://publisher.example/live",
            },
        )

        source.pop("parent_relationship_type")
        self._write_pack(source=source)
        records, report = self._collect()
        self.assertFalse(report.errors)
        self.assertNotIn("parent_proceeding", records[0].record.metadata)
        self.assertEqual(records[0].record.relationships, ())

    def test_source_plan_validates_metadata_and_parent_relationship_type(self):
        invalid_metadata = {
            "id": "invalid-metadata",
            "ingestion_mode": "link_only",
            "corpus_slug": "example-corpus",
            "canonical_keys": ["example:1"],
            "metadata": {"instrument_type": "NOT_A_REAL_INSTRUMENT"},
        }
        self._write_pack(source=invalid_metadata)
        with self.assertRaisesRegex(SourcePlanError, "instrument_type"):
            read_source_plan(self.pack_dir / "sources.yaml")

        invalid_metadata["metadata"] = _authority_metadata()
        invalid_metadata["parent_relationship_type"] = "NOT_A_RELATIONSHIP"
        self._write_pack(source=invalid_metadata)
        with self.assertRaisesRegex(SourcePlanError, "parent_relationship_type"):
            read_source_plan(self.pack_dir / "sources.yaml")

        invalid_metadata["parent_relationship_type"] = "FILED_IN"
        invalid_metadata["candidates"] = [
            {
                "canonical_key": "example:1",
                "url": "https://publisher.example/1",
                "extra": {"current_version": "false"},
            }
        ]
        invalid_metadata.pop("canonical_keys")
        self._write_pack(source=invalid_metadata)
        with self.assertRaisesRegex(
            SourcePlanError,
            "current_version must be true, false, or null",
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

        invalid_metadata["candidates"][0]["extra"] = {}
        invalid_metadata["metadata"]["source_plan_id"] = "spoofed-provenance"
        self._write_pack(source=invalid_metadata)
        with self.assertRaisesRegex(SourcePlanError, "builder-owned fields"):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_review_required_full_content_needs_explicit_operator_approval(self):
        _FakeAuthoritySourceProvider.rights_status = RightsStatus.REVIEW_REQUIRED

        refused, refused_report = self._collect()
        approved, approved_report = self._collect(rights_approved=True)

        self.assertFalse(refused)
        self.assertEqual(len(refused_report.errors), 1)
        self.assertIn("authority gate refused", refused_report.errors[0]["error"])
        self.assertEqual(len(approved), 1)
        self.assertFalse(approved_report.errors)
        self.assertTrue(approved[0].rights_approved)

    def test_full_content_rejects_link_only_rights_and_link_manifests(self):
        _FakeAuthoritySourceProvider.rights_status = RightsStatus.LINK_ONLY
        records, report = self._collect(rights_approved=True)
        self.assertFalse(records)
        self.assertIn("rights_status LINK_ONLY", report.errors[0]["error"])

        _FakeAuthoritySourceProvider.rights_status = RightsStatus.PUBLIC_DOMAIN
        _FakeAuthoritySourceProvider.link_manifest = True
        records, report = self._collect(rights_approved=True)
        self.assertFalse(records)
        self.assertIn("link-only manifest", report.errors[0]["error"])

    def test_provider_ca_paths_are_pack_scoped_and_resolved_to_pem_text(self):
        certificate = (
            "-----BEGIN CERTIFICATE-----\n"
            "test-certificate-body\n"
            "-----END CERTIFICATE-----\n"
        )
        certificates_dir = self.pack_dir / "certificates"
        certificates_dir.mkdir()
        (certificates_dir / "publisher.pem").write_text(
            certificate,
            encoding="ascii",
        )
        source = yaml.safe_load(
            (self.pack_dir / "sources.yaml").read_text(encoding="utf-8")
        )["sources"][0]
        source["fetch_kwargs"] = {
            "extra_ca_certificates": ["certificates/publisher.pem"]
        }
        self._write_pack(source=source)

        records, report = self._collect()

        self.assertEqual(len(records), 1)
        self.assertFalse(report.errors)
        self.assertEqual(
            _FakeAuthoritySourceProvider.last_fetch_kwargs["extra_ca_certificates"],
            (certificate,),
        )

        source["fetch_kwargs"] = {"extra_ca_certificates": ["../outside.pem"]}
        self._write_pack(source=source)
        records, report = self._collect()
        self.assertFalse(records)
        self.assertIn("escapes the authority pack", report.errors[0]["error"])

    def test_collection_fetches_a_canonical_identity_only_once_across_sources(self):
        plan_path = self.pack_dir / "sources.yaml"
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        duplicate = dict(plan["sources"][0])
        duplicate["id"] = "duplicate-discovery-result"
        plan["sources"].append(duplicate)
        plan_path.write_text(
            yaml.safe_dump(plan, sort_keys=False),
            encoding="utf-8",
        )

        records, report = self._collect()

        self.assertEqual(len(records), 1)
        self.assertEqual(_FakeAuthoritySourceProvider.fetch_calls, 1)
        self.assertEqual(
            [
                item
                for item in report.skipped
                if item["reason"] == "duplicate canonical_key already collected"
            ],
            [
                {
                    "source_id": "duplicate-discovery-result",
                    "candidate": "example:1",
                    "reason": "duplicate canonical_key already collected",
                }
            ],
        )

    def test_collection_refuses_capped_discovery_results(self):
        self._write_pack(
            source={
                "id": "live-capped",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "discovery_provider": "_FakeAuthorityDiscoveryProvider",
                "index_urls": ["https://publisher.example/index"],
            }
        )
        _FakeAuthorityDiscoveryProvider.capped = True

        records, report = self._collect()

        self.assertFalse(records)
        self.assertEqual(_FakeAuthoritySourceProvider.fetch_calls, 0)
        self.assertEqual(report.discovered, 1)
        self.assertIn("discovery result was capped", report.errors[0]["error"])

    def test_builder_emits_valid_deterministic_v2_zip_with_lineage(self):
        records, report = self._collect()
        self.assertFalse(report.errors)

        first = build_authority_import_artifacts(
            self.pack_dir,
            records,
            supported_mime_types={"text/plain"},
            converter_extensions=(),
        )
        archive_path = first.zip_paths[0]
        first_bytes = archive_path.read_bytes()
        second = build_authority_import_artifacts(
            self.pack_dir,
            records,
            supported_mime_types={"text/plain"},
            converter_extensions=(),
        )

        self.assertEqual(first_bytes, second.zip_paths[0].read_bytes())
        validation = validate_export(archive_path)
        self.assertTrue(validation.ok, validation.errors)
        self.assertFalse(validation.warnings)
        with zipfile.ZipFile(archive_path) as archive:
            data = json.loads(archive.read("data.json"))
            self.assertEqual(data["version"], "2.0")
            self.assertEqual(len(data["annotated_docs"]), 1)
            filename, document = next(iter(data["annotated_docs"].items()))
            self.assertEqual(document["title"], "[REVIEWED] Display title")
            self.assertEqual(document["file_type"], "text/plain")
            self.assertEqual(document["page_count"], 0)
            self.assertEqual(document["pawls_file_content"], [])
            self.assertEqual(
                archive.read(filename), b"Official Rule\n\nVerified body text."
            )
            metadata = document["custom_meta"]
            self.assertEqual(metadata["canonical_key"], "example:1")
            self.assertEqual(metadata["source_mime_type"], "text/html")
            self.assertEqual(metadata["artifact_mime_type"], "text/plain")
            self.assertEqual(
                metadata["content_hash"],
                hashlib.sha256(
                    b"<html><body><h1>Official Rule</h1><p>Verified body text.</p>"
                    b"</body></html>"
                ).hexdigest(),
            )
            self.assertEqual(
                metadata["artifact_content_hash"],
                hashlib.sha256(b"Official Rule\n\nVerified body text.").hexdigest(),
            )
            source_member = metadata["publisher_source_member"]
            publisher_bytes = (
                b"<html><body><h1>Official Rule</h1><p>Verified body text.</p>"
                b"</body></html>"
            )
            self.assertNotEqual(source_member, filename)
            self.assertEqual(archive.read(source_member), publisher_bytes)
            self.assertEqual(
                metadata["publisher_source_content_hash"],
                hashlib.sha256(publisher_bytes).hexdigest(),
            )
            self.assertEqual(metadata["publisher_source_mime_type"], "text/html")
            self.assertEqual(metadata["publisher_source_packaging"], "sidecar")
            path = data["document_paths"][0]
            self.assertEqual(path["document_ref"], filename)
            self.assertEqual(path["external_id"], "example:1")
            self.assertEqual(
                path["ingestion_metadata"]["source_mime_type"], "text/html"
            )
            self.assertEqual(
                path["ingestion_metadata"]["artifact_mime_type"], "text/plain"
            )
            self.assertEqual(
                path["ingestion_metadata"]["publisher_source_member"],
                source_member,
            )
            self.assertEqual(data["ingestion_sources"][0]["active"], False)

        index = json.loads((first.output_dir / "index.json").read_text())
        self.assertEqual(index["cases"][0]["expectedDocumentCount"], 1)
        self.assertEqual(index["cases"][0]["expectedCanonicalKeys"], ["example:1"])
        self.assertTrue(
            index["cases"][0]["sourcePlanFingerprint"].startswith("sha256:")
        )
        self.assertTrue(index["cases"][0]["packFingerprint"].startswith("sha256:"))

    def test_builder_converter_extension_wins_over_native_mime_allowlist(self):
        records, report = self._collect()
        self.assertFalse(report.errors)

        result = build_authority_import_artifacts(
            self.pack_dir,
            records,
            supported_mime_types={"text/html"},
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
            filename, document = next(iter(data["annotated_docs"].items()))
            metadata = document["custom_meta"]
            self.assertTrue(filename.endswith(".html"))
            self.assertEqual(metadata["publisher_source_filename"], "1.html")
            self.assertEqual(metadata["publisher_source_member"], filename)
            self.assertEqual(metadata["publisher_source_packaging"], "document")
            self.assertEqual(document["file_type"], "application/octet-stream")
            self.assertIs(metadata["conversion_required"], True)
            self.assertEqual(
                archive.read(filename),
                (
                    b"<html><body><h1>Official Rule</h1>"
                    b"<p>Verified body text.</p></body></html>"
                ),
            )
            self.assertEqual(set(archive.namelist()), {"data.json", filename})

    def test_builder_preserves_native_document_extension(self):
        publisher_bytes = b"%PDF-1.7\nnative publisher PDF"
        record = self._converter_source_record(
            extension="pdf",
            mime_type="application/pdf",
            content=publisher_bytes,
        )

        result = build_authority_import_artifacts(
            self.pack_dir,
            [CollectedAuthorityRecord(record=record, source_id="native-pdf")],
            supported_mime_types={"text/plain", "application/pdf"},
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
            filename, document = next(iter(data["annotated_docs"].items()))
            metadata = document["custom_meta"]
            self.assertTrue(filename.endswith(".pdf"))
            self.assertEqual(archive.read(filename), publisher_bytes)
            self.assertEqual(document["file_type"], "application/pdf")
            self.assertEqual(metadata["publisher_source_member"], filename)
            self.assertEqual(metadata["publisher_source_packaging"], "document")
            self.assertIs(metadata["conversion_required"], False)

    def test_converter_extensions_keep_exact_publisher_bytes_as_v2_documents(self):
        publisher_sources = {
            "xls": (
                b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1publisher spreadsheet bytes",
                "application/vnd.ms-excel",
            ),
            "pptx": (
                b"PK\x03\x04publisher presentation bytes",
                (
                    "application/vnd.openxmlformats-officedocument."
                    "presentationml.presentation"
                ),
            ),
            "html": (
                b"<html><body><p>Publisher HTML bytes</p></body></html>",
                "text/html",
            ),
            "png": (
                b"\x89PNG\r\n\x1a\npublisher image bytes",
                "image/png",
            ),
        }
        result = build_authority_import_artifacts(
            self.pack_dir,
            [
                CollectedAuthorityRecord(
                    record=self._converter_source_record(
                        extension=extension,
                        mime_type=mime_type,
                        content=content,
                    ),
                    source_id=f"converter-{extension}",
                )
                for extension, (content, mime_type) in publisher_sources.items()
            ],
            supported_mime_types={"text/plain"},
            converter_extensions=publisher_sources,
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
            self.assertEqual(len(data["annotated_docs"]), len(publisher_sources))
            paths_by_ref = {
                path["document_ref"]: path for path in data["document_paths"]
            }
            for filename, document in data["annotated_docs"].items():
                metadata = document["custom_meta"]
                extension = metadata["publisher_source_filename"].rsplit(".", 1)[-1]
                publisher_bytes, publisher_mime = publisher_sources[extension]
                publisher_hash = hashlib.sha256(publisher_bytes).hexdigest()
                ingestion_metadata = paths_by_ref[filename]["ingestion_metadata"]
                with self.subTest(extension=extension):
                    self.assertTrue(filename.endswith(f".{extension}"))
                    self.assertEqual(archive.read(filename), publisher_bytes)
                    self.assertEqual(
                        document["file_type"],
                        "application/octet-stream",
                    )
                    self.assertEqual(document["pdf_file_hash"], publisher_hash)
                    self.assertEqual(
                        metadata["artifact_content_hash"],
                        publisher_hash,
                    )
                    self.assertEqual(
                        metadata["publisher_source_content_hash"],
                        publisher_hash,
                    )
                    self.assertEqual(
                        metadata["publisher_source_mime_type"],
                        publisher_mime,
                    )
                    self.assertEqual(
                        metadata["publisher_source_member"],
                        filename,
                    )
                    self.assertEqual(
                        metadata["publisher_source_packaging"],
                        "document",
                    )
                    self.assertIs(metadata["conversion_required"], True)
                    self.assertEqual(
                        ingestion_metadata["source_mime_type"],
                        publisher_mime,
                    )
                    self.assertEqual(
                        ingestion_metadata["source_content_hash"],
                        publisher_hash,
                    )
                    self.assertEqual(
                        ingestion_metadata["publisher_source_mime_type"],
                        publisher_mime,
                    )
                    self.assertEqual(
                        ingestion_metadata["publisher_source_content_hash"],
                        publisher_hash,
                    )
            self.assertFalse(
                any(name.startswith("publisher-source-") for name in archive.namelist())
            )

    def test_registered_converter_extension_uses_document_packaging(self):
        publisher_bytes = b"<html><body>Publisher source</body></html>"
        record = self._converter_source_record(
            extension="html",
            mime_type="text/html",
            content=publisher_bytes,
        )

        with patch(
            "opencontractserver.enrichment.authority_import_artifacts."
            "_registered_converter_extensions",
            return_value=frozenset({"html"}),
        ) as registered_extensions:
            result = build_authority_import_artifacts(
                self.pack_dir,
                [CollectedAuthorityRecord(record=record, source_id="registered-html")],
                supported_mime_types={"text/plain"},
            )

        registered_extensions.assert_called_once_with()
        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
            filename, document = next(iter(data["annotated_docs"].items()))
            self.assertTrue(filename.endswith(".html"))
            self.assertEqual(archive.read(filename), publisher_bytes)
            self.assertEqual(document["file_type"], "application/octet-stream")
            self.assertEqual(
                document["custom_meta"]["publisher_source_packaging"],
                "document",
            )

    def test_deferred_extraction_never_falls_back_to_a_text_sidecar(self):
        publisher_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1publisher spreadsheet bytes"
        record = self._converter_source_record(
            extension="xls",
            mime_type="application/vnd.ms-excel",
            content=publisher_bytes,
            extraction_deferred=True,
        )
        wrapped = CollectedAuthorityRecord(
            record=record,
            source_id="deferred-xls",
        )

        with self.assertRaisesRegex(
            SourcePlanError,
            "deferred text extraction.*neither native nor supported",
        ):
            build_authority_import_artifacts(
                self.pack_dir,
                [wrapped],
                supported_mime_types={"text/plain"},
                converter_extensions=(),
            )

        result = build_authority_import_artifacts(
            self.pack_dir,
            [wrapped],
            supported_mime_types={"text/plain"},
            converter_extensions={"xls"},
        )
        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
            filename, document = next(iter(data["annotated_docs"].items()))
            metadata = document["custom_meta"]
            self.assertTrue(filename.endswith(".xls"))
            self.assertEqual(archive.read(filename), publisher_bytes)
            self.assertEqual(document["file_type"], "application/octet-stream")
            self.assertEqual(metadata["publisher_source_member"], filename)
            self.assertEqual(metadata["publisher_source_packaging"], "document")
            self.assertNotIn("publisher-source-", " ".join(archive.namelist()))

    def test_portable_rendition_uses_existing_document_and_original_file_rails(self):
        package_bytes = b"PK\x03\x04exact publisher ZIP package"
        rendition_bytes = b"%PDF-1.7\npublisher PDF rendition"
        record = replace(
            self._converter_source_record(
                extension="zip",
                mime_type="application/zip",
                content=package_bytes,
            ),
            extracted_text=None,
            metadata={
                "text_extraction_deferred_to_pipeline": True,
                "text_extraction_source_extension": "pdf",
            },
            portable_rendition_content=rendition_bytes,
            portable_rendition_mime_type="application/pdf",
            portable_rendition_filename="official-rendition.pdf",
        )

        result = build_authority_import_artifacts(
            self.pack_dir,
            [CollectedAuthorityRecord(record=record, source_id="zip-package")],
            supported_mime_types={"text/plain", "application/pdf"},
            converter_extensions=(),
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
            filename, document = next(iter(data["annotated_docs"].items()))
            metadata = document["custom_meta"]
            self.assertTrue(filename.endswith(".pdf"))
            self.assertEqual(archive.read(filename), rendition_bytes)
            self.assertEqual(document["file_type"], "application/pdf")
            self.assertEqual(
                document["pdf_file_hash"],
                hashlib.sha256(rendition_bytes).hexdigest(),
            )
            self.assertEqual(metadata["publisher_source_packaging"], "sidecar")
            self.assertEqual(
                archive.read(metadata["publisher_source_member"]),
                package_bytes,
            )
            self.assertEqual(
                metadata["publisher_source_content_hash"],
                hashlib.sha256(package_bytes).hexdigest(),
            )
            self.assertEqual(
                metadata["portable_rendition_content_hash"],
                hashlib.sha256(rendition_bytes).hexdigest(),
            )
            self.assertEqual(
                metadata["portable_rendition_mime_type"],
                "application/pdf",
            )
            self.assertIs(metadata["conversion_required"], False)

    def test_builder_keeps_provider_relationships_provisional_and_auditable(self):
        _FakeAuthoritySourceProvider.relationships = (
            SourceRelationship(
                target_key="example-parent:7",
                relationship_type="FILED_IN",
                metadata={"source": "publisher listing"},
            ),
        )
        records, report = self._collect()
        self.assertFalse(report.errors)

        result = build_authority_import_artifacts(
            self.pack_dir,
            records,
            supported_mime_types={"text/plain"},
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
        relationship = next(iter(data["annotated_docs"].values()))["custom_meta"][
            "relationships"
        ][0]
        self.assertIs(relationship["verified"], False)
        self.assertEqual(relationship["metadata"]["source"], "publisher listing")
        self.assertEqual(
            relationship["metadata"]["review_status"],
            "pending_legal_review",
        )
        self.assertEqual(relationship["metadata"]["source_plan_id"], "example")
        self.assertEqual(
            relationship["metadata"]["provenance"],
            "authority_source_provider",
        )
        index = json.loads((result.output_dir / "index.json").read_text())
        self.assertEqual(
            index["cases"][0]["expectedProviderRelationships"],
            [
                {
                    "sourceKey": "example:1",
                    "relationshipType": "FILED_IN",
                    "targetKey": "example-parent:7",
                }
            ],
        )

        _FakeAuthoritySourceProvider.relationships = (
            SourceRelationship(
                target_key="example-parent:7",
                relationship_type="FILED_IN",
                verified=True,
            ),
        )
        records, report = self._collect()
        self.assertFalse(report.errors)
        with self.assertRaisesRegex(SourcePlanError, "must not be pre-verified"):
            build_authority_import_artifacts(
                self.pack_dir,
                records,
                supported_mime_types={"text/plain"},
            )

    def test_direct_record_builder_preserves_operator_source_plan_identity(self):
        record = _FakeAuthoritySourceProvider()._fetch_impl(
            AuthorityRequest(
                canonical_key="example:1",
                url="https://publisher.example/1",
            )
        )[0]
        result = build_authority_import_artifacts(
            self.pack_dir,
            [
                CollectedAuthorityRecord(
                    record=record,
                    source_id="manual-source",
                    display_title="Manual display title",
                )
            ],
            supported_mime_types={"text/plain"},
        )
        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
        path = data["document_paths"][0]
        self.assertEqual(path["ingestion_metadata"]["source_plan_id"], "manual-source")

    def test_builder_disambiguates_member_names_without_changing_titles(self):
        first = _FakeAuthoritySourceProvider()._fetch_impl(
            AuthorityRequest(
                canonical_key="example:1",
                url="https://publisher.example/1",
            )
        )[0]
        second = _FakeAuthoritySourceProvider()._fetch_impl(
            AuthorityRequest(
                canonical_key="example:2",
                url="https://publisher.example/2",
            )
        )[0]
        result = build_authority_import_artifacts(
            self.pack_dir,
            [
                CollectedAuthorityRecord(record=first, source_id="first"),
                CollectedAuthorityRecord(record=second, source_id="second"),
            ],
            supported_mime_types={"text/plain"},
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
        self.assertEqual(len(data["annotated_docs"]), 2)
        self.assertEqual(
            {document["title"] for document in data["annotated_docs"].values()},
            {"Publisher title"},
        )
        self.assertEqual(len(set(data["annotated_docs"])), 2)

    def test_builder_disambiguator_survives_long_title_truncation(self):
        first = _FakeAuthoritySourceProvider()._fetch_impl(
            AuthorityRequest(
                canonical_key="example:1",
                url="https://publisher.example/1",
            )
        )[0]
        second = _FakeAuthoritySourceProvider()._fetch_impl(
            AuthorityRequest(
                canonical_key="example:2",
                url="https://publisher.example/2",
            )
        )[0]
        long_title = "Identical publisher filing title " + ("detail " * 30)
        result = build_authority_import_artifacts(
            self.pack_dir,
            [
                CollectedAuthorityRecord(
                    record=first,
                    source_id="first",
                    display_title=long_title,
                ),
                CollectedAuthorityRecord(
                    record=second,
                    source_id="second",
                    display_title=long_title,
                ),
            ],
            supported_mime_types={"text/plain"},
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
        self.assertEqual(len(data["annotated_docs"]), 2)
        self.assertEqual(
            {document["title"] for document in data["annotated_docs"].values()},
            {long_title},
        )
        self.assertEqual(len(set(data["annotated_docs"])), 2)
