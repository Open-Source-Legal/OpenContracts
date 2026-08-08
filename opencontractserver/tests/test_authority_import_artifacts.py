"""Tests for the external authority-source -> ordinary corpus-export bridge.

The collector is intentionally an operator-side sideload tool.  These tests
exercise source-plan validation, the no-fetch link-only boundary, the existing
rights gate, and the V2 artifact contract without invoking an API, view, or
Celery task.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import replace
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import yaml

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.enrichment.authority_import_artifacts import (
    ArtifactCase,
    CollectedAuthorityRecord,
    CollectionReport,
    SourcePlanError,
    _build_export_payload,
    _candidate_discovery_metadata,
    _candidate_promoted_metadata,
    _configured_supported_mime_types,
    _content_sentinel,
    _corpus_aliases,
    _corpus_export_config,
    _json_safe,
    _manifest_corpora,
    _normalize_records,
    _normalize_relationship_type,
    _pack_name,
    _provider_definitions,
    _publisher_source_filename,
    _publisher_source_sidecar_member,
    _read_pack_manifest,
    _registered_converter_extensions,
    _require_canonical_key,
    _require_http_url,
    _require_publisher_content_record,
    _require_string,
    _source_plan_path,
    _validate_authority_metadata,
    build_authority_import_artifacts,
    collect_from_source_plan,
    read_source_plan,
    write_aggregate_manifest,
    write_collection_report,
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
    # Test-only escape hatches so individual tests can force a malformed or
    # unusual provider response without a bespoke provider subclass. ``None``
    # preserves the default, historical behavior exercised by every other
    # test in this module.
    fetch_override = None
    can_handle_override = None
    verify_evidence_override = None

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
        if type(self).fetch_override is not None:
            return type(self).fetch_override(request)
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

    def can_handle(self, canonical_key: str) -> bool:
        if type(self).can_handle_override is not None:
            return type(self).can_handle_override(canonical_key)
        return super().can_handle(canonical_key)

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        if type(self).verify_evidence_override is not None:
            return type(self).verify_evidence_override(canonical_key, record)
        return any(
            evidence.value == canonical_key for evidence in record.publisher_evidence
        )


class _FakeAuthorityDiscoveryProvider:
    candidate_extra: dict = {}
    capped = False
    skipped_index_urls: dict = {}
    discover_error: Exception | None = None

    def discover_candidates(self, index_urls, **kwargs) -> DiscoveryResult:
        del kwargs
        if type(self).discover_error is not None:
            raise type(self).discover_error
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
            skipped_index_urls=dict(type(self).skipped_index_urls),
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
        _FakeAuthoritySourceProvider.fetch_override = None
        _FakeAuthoritySourceProvider.can_handle_override = None
        _FakeAuthoritySourceProvider.verify_evidence_override = None
        _FakeAuthorityDiscoveryProvider.candidate_extra = {}
        _FakeAuthorityDiscoveryProvider.capped = False
        _FakeAuthorityDiscoveryProvider.skipped_index_urls = {}
        _FakeAuthorityDiscoveryProvider.discover_error = None
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.pack_dir = Path(self._temporary.name)
        self._write_pack()

    def _authority_source_record(
        self, canonical_key: str, **overrides
    ) -> AuthoritySourceRecord:
        """Build a minimally valid AuthoritySourceRecord for direct provider
        override tests that need precise control over what "fetch" returns."""

        defaults = dict(
            canonical_key=canonical_key,
            title="Publisher title",
            source_url=f"https://publisher.example/{canonical_key.split(':', 1)[-1]}",
            source_identifier=canonical_key,
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
            content=b"<html><body>Verified body text.</body></html>",
            mime_type="text/html",
            corpus_slug="example-corpus",
            metadata={},
            retrieved_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            extracted_text="Verified body text.",
            publisher_evidence=(
                AuthorityPublisherEvidence(
                    source="SOURCE_IDENTIFIER",
                    value=canonical_key,
                    locator=f"https://publisher.example/{canonical_key.split(':', 1)[-1]}",
                ),
            ),
        )
        defaults.update(overrides)
        return AuthoritySourceRecord(**defaults)

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

    # -- read_source_plan validation gauntlet --------------------------------

    def test_source_plan_rejects_malformed_yaml_and_non_mapping_top_level(self):
        plan_path = self.pack_dir / "sources.yaml"
        plan_path.write_text("sources: [1, 2\n", encoding="utf-8")
        with self.assertRaisesRegex(SourcePlanError, "Could not read source plan"):
            read_source_plan(plan_path)

        plan_path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with self.assertRaisesRegex(SourcePlanError, "must be a YAML mapping"):
            read_source_plan(plan_path)

    def test_source_plan_rejects_wrong_schema_version(self):
        plan_path = self.pack_dir / "sources.yaml"
        plan_path.write_text(
            yaml.safe_dump({"schema_version": 999, "sources": []}), encoding="utf-8"
        )
        with self.assertRaisesRegex(SourcePlanError, "schema_version must be"):
            read_source_plan(plan_path)

    def test_source_plan_rejects_empty_sources_list(self):
        plan_path = self.pack_dir / "sources.yaml"
        plan_path.write_text(
            yaml.safe_dump({"schema_version": 1, "sources": []}), encoding="utf-8"
        )
        with self.assertRaisesRegex(
            SourcePlanError, "sources must be a non-empty list"
        ):
            read_source_plan(plan_path)

    def test_source_plan_rejects_non_mapping_source_entries(self):
        plan_path = self.pack_dir / "sources.yaml"
        plan_path.write_text(
            yaml.safe_dump({"schema_version": 1, "sources": ["not-a-mapping"]}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SourcePlanError, r"sources\[0\] must be a mapping"):
            read_source_plan(plan_path)

    def test_source_plan_rejects_unknown_source_keys(self):
        self._write_pack(
            source={
                "id": "bad",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
                "bogus_key": True,
            }
        )
        with self.assertRaisesRegex(SourcePlanError, "unknown keys"):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_rejects_missing_source_id(self):
        self._write_pack(
            source={
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, r"\.id must be a non-empty string"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_rejects_duplicate_source_ids(self):
        plan_path = self.pack_dir / "sources.yaml"
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        plan["sources"].append(dict(plan["sources"][0]))
        plan_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
        with self.assertRaisesRegex(SourcePlanError, "duplicates"):
            read_source_plan(plan_path)

    def test_source_plan_rejects_invalid_ingestion_mode(self):
        self._write_pack(
            source={
                "id": "bad-mode",
                "ingestion_mode": "partial_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
            }
        )
        with self.assertRaisesRegex(SourcePlanError, "ingestion_mode must be one of"):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_discovery_provider_requires_non_empty_index_urls(self):
        self._write_pack(
            source={
                "id": "no-urls",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "discovery_provider": "_FakeAuthorityDiscoveryProvider",
                "index_urls": [],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "index_urls must be a non-empty list"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_index_urls_only_valid_with_discovery_provider(self):
        self._write_pack(
            source={
                "id": "stray-urls",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
                "index_urls": ["https://publisher.example/index"],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "index_urls is only valid with discovery_provider"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_rejects_empty_canonical_keys_list(self):
        self._write_pack(
            source={
                "id": "empty-keys",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": [],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "canonical_keys must be a non-empty list"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_rejects_empty_candidates_list(self):
        self._write_pack(
            source={
                "id": "empty-candidates",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": [],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "candidates must be a non-empty list"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_kwargs_must_be_mappings(self):
        self._write_pack(
            source={
                "id": "bad-kwargs",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
                "discovery_kwargs": ["not", "a", "mapping"],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "discovery_kwargs must be a mapping"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_rejects_invalid_corpus_slug(self):
        self._write_pack(
            source={
                "id": "bad-slug",
                "ingestion_mode": "full_content",
                "corpus_slug": "Not A Valid Slug!",
                "canonical_keys": ["example:1"],
            }
        )
        with self.assertRaisesRegex(SourcePlanError, "corpus_slug is invalid"):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_link_only_requires_corpus_slug(self):
        self._write_pack(
            source={
                "id": "no-slug-link",
                "ingestion_mode": "link_only",
                "canonical_keys": ["example:1"],
                "metadata": _authority_metadata(),
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "corpus_slug is required for link_only"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_parent_relationship_type_requires_link_only_mode(self):
        self._write_pack(
            source={
                "id": "full-content-parent",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
                "parent_relationship_type": "FILED_IN",
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "parent_relationship_type is only valid for"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_rejects_invalid_canonical_key_in_canonical_keys_list(self):
        self._write_pack(
            source={
                "id": "bad-canonical-key",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["Not A Valid Key"],
            }
        )
        with self.assertRaisesRegex(SourcePlanError, "not a canonical authority key"):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_validates_candidate_entries(self):
        self._write_pack(
            source={
                "id": "bad-candidate-shape",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": ["not-a-mapping"],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, r"candidates\[0\] must be a mapping"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

        self._write_pack(
            source={
                "id": "bad-candidate-keys",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": [{"canonical_key": "example:1", "bogus": True}],
            }
        )
        with self.assertRaisesRegex(SourcePlanError, "has unknown keys"):
            read_source_plan(self.pack_dir / "sources.yaml")

        self._write_pack(
            source={
                "id": "both-titles",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": [
                    {
                        "canonical_key": "example:1",
                        "title": "A",
                        "publisher_title": "B",
                    }
                ],
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "cannot declare both title and publisher_title"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

        self._write_pack(
            source={
                "id": "bad-extra",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": [
                    {"canonical_key": "example:1", "extra": "not-a-mapping"}
                ],
            }
        )
        with self.assertRaisesRegex(SourcePlanError, r"\.extra must be a mapping"):
            read_source_plan(self.pack_dir / "sources.yaml")

    def test_source_plan_validates_candidate_filter_schema(self):
        self._write_pack(
            source={
                "id": "bad-filters-shape",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
                "candidate_filters": "not-a-mapping",
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "candidate_filters must be a mapping"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

        self._write_pack(
            source={
                "id": "unknown-filter-key",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
                "candidate_filters": {"bogus_filter": ["x"]},
            }
        )
        with self.assertRaisesRegex(
            SourcePlanError, "candidate_filters has unknown keys"
        ):
            read_source_plan(self.pack_dir / "sources.yaml")

        self._write_pack(
            source={
                "id": "filter-not-list",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
                "candidate_filters": {"include_title": "not-a-list"},
            }
        )
        with self.assertRaisesRegex(SourcePlanError, "must be a list of regex strings"):
            read_source_plan(self.pack_dir / "sources.yaml")

        self._write_pack(
            source={
                "id": "filter-bad-regex",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "canonical_keys": ["example:1"],
                "candidate_filters": {"include_title": ["[unterminated"]},
            }
        )
        with self.assertRaisesRegex(SourcePlanError, "invalid regex"):
            read_source_plan(self.pack_dir / "sources.yaml")

    # -- pack-relative CA certificate resolution -----------------------------

    def test_ca_certificate_kwargs_validation_errors(self):
        cases = [
            ("not-a-list", "non-empty list"),
            ([123], "pack-relative PEM path"),
            (["/etc/ssl/cert.pem"], "must be pack-relative"),
            (["missing.pem"], "does not name a readable file"),
        ]
        for extra_ca_certificates, expected in cases:
            with self.subTest(extra_ca_certificates=extra_ca_certificates):
                source = yaml.safe_load(
                    (self.pack_dir / "sources.yaml").read_text(encoding="utf-8")
                )["sources"][0]
                source["fetch_kwargs"] = {
                    "extra_ca_certificates": extra_ca_certificates
                }
                self._write_pack(source=source)
                records, report = self._collect()
                self.assertFalse(records)
                self.assertIn(expected, report.errors[0]["error"])

    def test_ca_certificate_size_and_content_validation(self):
        certificates_dir = self.pack_dir / "certificates"
        certificates_dir.mkdir(exist_ok=True)
        source = yaml.safe_load(
            (self.pack_dir / "sources.yaml").read_text(encoding="utf-8")
        )["sources"][0]

        oversized = certificates_dir / "oversized.pem"
        oversized.write_bytes(
            b"-----BEGIN CERTIFICATE-----\n" + b"A" * (1024 * 1024 + 1)
        )
        source["fetch_kwargs"] = {
            "extra_ca_certificates": ["certificates/oversized.pem"]
        }
        self._write_pack(source=source)
        records, report = self._collect()
        self.assertFalse(records)
        self.assertIn("exceeds the 1 MiB certificate limit", report.errors[0]["error"])

        non_ascii = certificates_dir / "non-ascii.pem"
        non_ascii.write_bytes("café-----BEGIN CERTIFICATE-----".encode())
        source["fetch_kwargs"] = {
            "extra_ca_certificates": ["certificates/non-ascii.pem"]
        }
        self._write_pack(source=source)
        records, report = self._collect()
        self.assertFalse(records)
        self.assertIn("could not be read as PEM", report.errors[0]["error"])

        no_markers = certificates_dir / "no-markers.pem"
        no_markers.write_text("just some text", encoding="ascii")
        source["fetch_kwargs"] = {
            "extra_ca_certificates": ["certificates/no-markers.pem"]
        }
        self._write_pack(source=source)
        records, report = self._collect()
        self.assertFalse(records)
        self.assertIn(
            "must contain CA certificate PEM and no private key",
            report.errors[0]["error"],
        )

        with_private_key = certificates_dir / "with-key.pem"
        with_private_key.write_text(
            "-----BEGIN CERTIFICATE-----\nbody\n-----END CERTIFICATE-----\n"
            "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----\n",
            encoding="ascii",
        )
        source["fetch_kwargs"] = {
            "extra_ca_certificates": ["certificates/with-key.pem"]
        }
        self._write_pack(source=source)
        records, report = self._collect()
        self.assertFalse(records)
        self.assertIn(
            "must contain CA certificate PEM and no private key",
            report.errors[0]["error"],
        )

    # -- _collect_from_source_plan_impl branches -----------------------------

    def test_discovery_reports_skipped_index_urls_as_errors(self):
        self._write_pack(
            source={
                "id": "discovery-skips",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "discovery_provider": "_FakeAuthorityDiscoveryProvider",
                "index_urls": ["https://publisher.example/index"],
            }
        )
        _FakeAuthorityDiscoveryProvider.skipped_index_urls = {
            "https://publisher.example/index": "robots.txt disallowed crawling"
        }

        records, report = self._collect()

        self.assertEqual(len(records), 1)
        skip_errors = [
            item for item in report.errors if item["candidate"].startswith("https://")
        ]
        self.assertEqual(
            skip_errors,
            [
                {
                    "source_id": "discovery-skips",
                    "candidate": "https://publisher.example/index",
                    "error": "robots.txt disallowed crawling",
                }
            ],
        )

    def test_discovery_provider_exception_is_captured_per_source(self):
        self._write_pack(
            source={
                "id": "discovery-explodes",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "discovery_provider": "_FakeAuthorityDiscoveryProvider",
                "index_urls": ["https://publisher.example/index"],
            }
        )
        _FakeAuthorityDiscoveryProvider.discover_error = RuntimeError("boom")

        records, report = self._collect()

        self.assertFalse(records)
        self.assertEqual(_FakeAuthoritySourceProvider.fetch_calls, 0)
        self.assertIn("RuntimeError: boom", report.errors[0]["error"])

    def test_unresolvable_source_provider_name_is_captured_per_source(self):
        self._write_pack(
            source={
                "id": "bad-provider-name",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "source_provider": "NoSuchProviderClass",
                "canonical_keys": ["example:1"],
            }
        )

        records, report = self._collect()

        self.assertFalse(records)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("resolved to 0 registered classes", report.errors[0]["error"])

    def test_canonical_keys_mode_collects_without_discovery_or_candidates(self):
        self._write_pack(
            source={
                "id": "canonical-only",
                "ingestion_mode": "link_only",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "metadata": _authority_metadata(),
                "canonical_keys": ["example:1"],
            }
        )

        records, report = self._collect()

        self.assertFalse(report.errors)
        self.assertEqual(report.discovered, 1)
        self.assertEqual(len(records), 1)
        # No DiscoveryCandidate exists for this mode, so both discovery
        # provenance and promoted extras must fall back to empty mappings.
        self.assertEqual(records[0].record.metadata["discovery_metadata"], {})

    def test_auto_routes_to_provider_via_can_handle_when_source_provider_omitted(self):
        self._write_pack(
            source={
                "id": "auto-route",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": [
                    {
                        "canonical_key": "example:1",
                        "url": "https://publisher.example/1",
                    }
                ],
            }
        )

        records, report = self._collect()

        self.assertFalse(report.errors)
        self.assertEqual(len(records), 1)
        self.assertEqual(_FakeAuthoritySourceProvider.fetch_calls, 1)

    def test_auto_routing_fails_closed_when_no_provider_handles_the_key(self):
        self._write_pack(
            source={
                "id": "no-provider-handles",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "candidates": [
                    {
                        "canonical_key": "unhandled:1",
                        "url": "https://publisher.example/1",
                    }
                ],
            }
        )

        records, report = self._collect()

        self.assertFalse(records)
        self.assertIn(
            "no registered authority source provider handles",
            report.errors[0]["error"],
        )

    def test_fetch_returning_no_records_is_captured(self):
        _FakeAuthoritySourceProvider.fetch_override = lambda request: []

        records, report = self._collect()

        self.assertFalse(records)
        self.assertIn("source provider returned no records", report.errors[0]["error"])

    def test_fetch_returning_duplicate_keys_within_a_batch_is_captured(self):
        _FakeAuthoritySourceProvider.fetch_override = lambda request: [
            self._authority_source_record("example:1"),
            self._authority_source_record("example:1"),
        ]

        records, report = self._collect()

        self.assertFalse(records)
        self.assertIn("returned duplicate canonical_key", report.errors[0]["error"])

    def test_fetch_expanding_to_already_collected_key_is_captured(self):
        self._write_pack(
            source={
                "id": "first",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "candidates": [
                    {
                        "canonical_key": "example:1",
                        "url": "https://publisher.example/1",
                    }
                ],
            }
        )
        plan_path = self.pack_dir / "sources.yaml"
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        plan["sources"].append(
            {
                "id": "second",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "candidates": [
                    {
                        "canonical_key": "example:2",
                        "url": "https://publisher.example/2",
                    }
                ],
            }
        )
        plan_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")

        # Both sources' fetch() always returns the SAME canonical_key
        # ("example:1"), simulating a provider that expands a distinct
        # requested candidate into an already-collected identity.
        _FakeAuthoritySourceProvider.fetch_override = lambda request: [
            self._authority_source_record("example:1")
        ]

        records, report = self._collect()

        self.assertEqual(len(records), 1)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.errors[0]["source_id"], "second")
        self.assertIn(
            "expanded 'example:2' to already-collected canonical_key",
            report.errors[0]["error"],
        )

    def test_fetch_returning_mixed_rights_status_is_captured(self):
        _FakeAuthoritySourceProvider.fetch_override = lambda request: [
            self._authority_source_record(
                "example:1", rights_status=RightsStatus.PUBLIC_DOMAIN
            ),
            self._authority_source_record(
                "example:1b", rights_status=RightsStatus.REVIEW_REQUIRED
            ),
        ]

        records, report = self._collect()

        self.assertFalse(records)
        self.assertIn("returned mixed rights_status values", report.errors[0]["error"])

    def test_provider_cannot_handle_expanded_canonical_key_is_captured(self):
        # The gate's own publisher-evidence check would otherwise reject this
        # scenario first (a mismatched canonical_key also fails independent
        # verification), so force verification to pass and isolate the
        # can_handle() check that runs after the gate.
        _FakeAuthoritySourceProvider.verify_evidence_override = (
            lambda canonical_key, record: True
        )
        _FakeAuthoritySourceProvider.fetch_override = lambda request: [
            self._authority_source_record("other-authority:1")
        ]

        records, report = self._collect()

        self.assertFalse(records)
        self.assertIn("unsupported canonical_key", report.errors[0]["error"])

    def test_publisher_evidence_verification_failure_is_captured(self):
        # AuthorityGateService.evaluate() already calls
        # provider.verify_publisher_evidence(record.canonical_key, record) for
        # every record as a precondition of GATE_OK, so a verifier that always
        # returns False never reaches the collector's own post-gate re-check
        # (it is rejected by the gate first, with a different message). Let
        # the first two calls (the gate's own checks) succeed and only fail
        # from the third call onward, which is exactly the collector's
        # independent re-verification -- defense in depth against a verifier
        # whose answer could legitimately differ between calls.
        call_count = {"n": 0}

        def _flaky_verify(canonical_key, record):
            call_count["n"] += 1
            return call_count["n"] <= 2

        _FakeAuthoritySourceProvider.verify_evidence_override = _flaky_verify

        records, report = self._collect()

        self.assertFalse(records)
        self.assertIn(
            "publisher evidence did not verify canonical_key",
            report.errors[0]["error"],
        )

    def test_candidate_filters_include_and_exclude_by_title_and_url(self):
        self._write_pack(
            source={
                "id": "filtered",
                "ingestion_mode": "full_content",
                "corpus_slug": "example-corpus",
                "source_provider": "_FakeAuthoritySourceProvider",
                "candidate_filters": {
                    "include_title": ["Keep"],
                    "exclude_url": ["skip-me"],
                },
                "candidates": [
                    {
                        "canonical_key": "example:keep",
                        "url": "https://publisher.example/keep",
                        "publisher_title": "Keep this filing",
                    },
                    {
                        "canonical_key": "example:drop-title",
                        "url": "https://publisher.example/drop",
                        "publisher_title": "Drop this filing",
                    },
                    {
                        "canonical_key": "example:drop-url",
                        "url": "https://publisher.example/skip-me",
                        "publisher_title": "Keep-worded but excluded url",
                    },
                ],
            }
        )

        records, report = self._collect()

        self.assertEqual({item.record.key for item in records}, {"example:keep"})
        skipped_reasons = {
            item["candidate"]: item["reason"]
            for item in report.skipped
            if item["reason"] == "candidate_filters"
        }
        self.assertEqual(
            skipped_reasons,
            {
                "example:drop-title": "candidate_filters",
                "example:drop-url": "candidate_filters",
            },
        )

    # -- _require_publisher_content_record extra branches --------------------

    def test_require_publisher_content_record_rejects_a_section_for_full_content(self):
        section = AuthoritySection(key="example:1", heading="A stub", text="stub text")
        with self.assertRaisesRegex(
            TypeError, "must return AuthoritySourceRecord with publisher bytes"
        ):
            _require_publisher_content_record(
                section, source_id="direct", canonical_key="example:1"
            )

    def test_require_publisher_content_record_rejects_link_manifest_text(self):
        record = self._authority_source_record(
            "example:1",
            extracted_text=(
                "Link-only authority source\nOfficial source: "
                "https://publisher.example/1"
            ),
        )
        with self.assertRaisesRegex(
            ValueError, "link-manifest text instead of publisher content"
        ):
            _require_publisher_content_record(
                record, source_id="direct", canonical_key="example:1"
            )

    def test_require_publisher_content_record_checks_deferred_extraction_bytes(self):
        record = self._authority_source_record(
            "example:1",
            content=(
                b"Link-only authority source\nOfficial source: "
                b"https://publisher.example/1"
            ),
            extracted_text=None,
            metadata={"text_extraction_deferred_to_pipeline": True},
        )
        with self.assertRaisesRegex(
            ValueError, "link-manifest text instead of publisher content"
        ):
            _require_publisher_content_record(
                record, source_id="direct", canonical_key="example:1"
            )

    def test_require_publisher_content_record_rejects_zero_byte_content(self):
        class _MalformedSourceRecord(AuthoritySourceRecord):
            """A hand-rolled subclass simulating a custom provider that
            bypasses AuthoritySourceRecord's own construction-time
            non-empty-content validation, per the boundary check's own
            comment ("keep the boundary check explicit so custom/test
            providers cannot bypass the full-content contract")."""

            def __post_init__(self) -> None:
                pass

        malformed = _MalformedSourceRecord(
            canonical_key="example:1",
            title="Publisher title",
            source_url="https://publisher.example/1",
            source_identifier="example:1",
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
            content=b"",
            mime_type="text/html",
            corpus_slug="example-corpus",
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            extracted_text="placeholder text so .text is never touched",
        )
        with self.assertRaisesRegex(ValueError, "returned zero publisher bytes"):
            _require_publisher_content_record(
                malformed, source_id="direct", canonical_key="example:1"
            )

    # -- build_authority_import_artifacts branches ---------------------------

    def test_authority_section_without_corpus_slug_is_rejected(self):
        section = AuthoritySection(
            key="example:no-slug", heading="No slug section", text="Some text."
        )
        wrapped = CollectedAuthorityRecord(
            record=section, source_id="direct", ingestion_mode="link_only"
        )
        with self.assertRaisesRegex(SourcePlanError, "requires source corpus_slug"):
            build_authority_import_artifacts(
                self.pack_dir, [wrapped], supported_mime_types={"text/plain"}
            )

    def test_record_targeting_undeclared_corpus_is_rejected(self):
        section = AuthoritySection(
            key="example:undeclared",
            heading="Undeclared corpus section",
            text="Some text.",
        )
        wrapped = CollectedAuthorityRecord(
            record=section,
            source_id="direct",
            corpus_slug="not-a-declared-corpus",
            ingestion_mode="link_only",
        )
        with self.assertRaisesRegex(SourcePlanError, "undeclared corpus"):
            build_authority_import_artifacts(
                self.pack_dir, [wrapped], supported_mime_types={"text/plain"}
            )

    def test_export_validation_failure_is_surfaced(self):
        records, report = self._collect()
        self.assertFalse(report.errors)
        fake_validation = SimpleNamespace(
            ok=False, errors=["structural annotation set is malformed"], warnings=[]
        )
        with patch(
            "opencontractserver.utils.validate_export.validate_export",
            return_value=fake_validation,
        ):
            with self.assertRaisesRegex(
                SourcePlanError, "structural annotation set is malformed"
            ):
                build_authority_import_artifacts(
                    self.pack_dir, records, supported_mime_types={"text/plain"}
                )

    def test_link_only_authority_section_builds_a_complete_v2_artifact(self):
        section = AuthoritySection(
            key="example:link-stub",
            heading="Link-only stub heading",
            text=(
                "Link-only authority source.\n\nOfficial source: "
                "https://publisher.example/1"
            ),
            source_url="https://publisher.example/1",
            metadata={
                **_authority_metadata(),
                "rights_status": "LINK_ONLY",
                "ingestion_mode": "link_only",
                "source_url": "https://publisher.example/1",
                "source_identifier": "publisher-stub-1",
                "retrieved_at": "2026-07-26T00:00:00+00:00",
            },
            relationships=(
                SourceRelationship(
                    target_key="example-proceeding:1",
                    relationship_type="FILED_IN",
                    metadata={"provenance": "source_plan_parent_key"},
                ),
            ),
        )
        wrapped = CollectedAuthorityRecord(
            record=section,
            source_id="link-source",
            corpus_slug="example-corpus",
            display_title="Link-only stub heading",
            ingestion_mode="link_only",
            rights_approved=False,
        )

        result = build_authority_import_artifacts(
            self.pack_dir,
            [wrapped],
            supported_mime_types={"text/plain"},
            converter_extensions=(),
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
            filename, document = next(iter(data["annotated_docs"].items()))
            self.assertEqual(document["title"], "Link-only stub heading")
            self.assertEqual(document["file_type"], "text/plain")
            self.assertEqual(archive.read(filename), section.text.encode("utf-8"))
            metadata = document["custom_meta"]
            self.assertEqual(metadata["canonical_key"], "example:link-stub")
            self.assertEqual(metadata["ingestion_mode"], "link_only")
            self.assertEqual(metadata["source_identifier"], "publisher-stub-1")
            self.assertEqual(metadata["source_mime_type"], "text/plain")
            self.assertEqual(
                metadata["relationships"],
                [
                    {
                        "target_key": "example-proceeding:1",
                        "relationship_type": "FILED_IN",
                        "verified": False,
                        "metadata": {"provenance": "source_plan_parent_key"},
                    }
                ],
            )
            path = data["document_paths"][0]
            self.assertEqual(path["external_id"], "publisher-stub-1")
            self.assertEqual(
                path["ingestion_metadata"]["retrieved_at"],
                "2026-07-26T00:00:00+00:00",
            )

    def test_portable_rendition_rejected_when_unsupported_and_unconvertible(self):
        record = replace(
            self._authority_source_record("example:1"),
            extracted_text=None,
            metadata={
                "text_extraction_deferred_to_pipeline": True,
                "text_extraction_source_extension": "xyz",
            },
            portable_rendition_content=b"unsupported rendition bytes",
            portable_rendition_mime_type="application/x-unsupported",
            portable_rendition_filename="rendition.xyz",
        )
        with self.assertRaisesRegex(
            SourcePlanError,
            "neither native nor supported by a registered file converter",
        ):
            build_authority_import_artifacts(
                self.pack_dir,
                [CollectedAuthorityRecord(record=record, source_id="bad-rendition")],
                supported_mime_types={"text/plain"},
                converter_extensions=(),
            )

    def test_duplicate_canonical_key_with_matching_content_is_deduped_silently(self):
        first = self._authority_source_record("example:1")
        second = self._authority_source_record("example:1")
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
        self.assertEqual(len(data["annotated_docs"]), 1)

    def test_duplicate_canonical_key_with_conflicting_content_is_rejected(self):
        first = self._authority_source_record("example:1")
        second = self._authority_source_record(
            "example:1",
            content=b"<html><body>Different verified body text.</body></html>",
            extracted_text="Different verified body text.",
        )
        with self.assertRaisesRegex(SourcePlanError, "produced multiple contents"):
            build_authority_import_artifacts(
                self.pack_dir,
                [
                    CollectedAuthorityRecord(record=first, source_id="first"),
                    CollectedAuthorityRecord(record=second, source_id="second"),
                ],
                supported_mime_types={"text/plain"},
            )

    def test_corpus_spec_aliases_are_attached_to_documents(self):
        spec_path = self.pack_dir / "corpus-spec.json"
        spec_path.write_text(
            json.dumps({"aliases": ["dgcl", "delaware-code-title-8"]}),
            encoding="utf-8",
        )
        manifest = yaml.safe_load(
            (self.pack_dir / "pack.yaml").read_text(encoding="utf-8")
        )
        manifest["corpora"][0]["spec"] = "corpus-spec.json"
        (self.pack_dir / "pack.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

        records, report = self._collect()
        self.assertFalse(report.errors)
        result = build_authority_import_artifacts(
            self.pack_dir, records, supported_mime_types={"text/plain"}
        )

        with zipfile.ZipFile(result.zip_paths[0]) as archive:
            data = json.loads(archive.read("data.json"))
        document = next(iter(data["annotated_docs"].values()))
        self.assertEqual(
            document["custom_meta"]["authority_aliases"],
            ["dgcl", "delaware-code-title-8"],
        )

    # -- _normalize_records direct branches -----------------------------------

    def test_normalize_records_rejects_unsupported_ingestion_mode(self):
        record = AuthoritySection(
            key="example:bogus-mode", heading="Bogus mode", text="some text"
        )
        wrapped = CollectedAuthorityRecord(
            record=record,
            source_id="direct",
            corpus_slug="example-corpus",
            ingestion_mode="partial_content",
        )
        with self.assertRaisesRegex(
            SourcePlanError, "unsupported ingestion_mode 'partial_content'"
        ):
            _normalize_records(
                [wrapped],
                pack_dir=self.pack_dir,
                corpus_entry={"slug": "example-corpus", "title": "Example Corpus"},
                pack_name="example_pack",
                supported_mime_types=frozenset({"text/plain"}),
                converter_extensions=frozenset(),
                source_plan_fingerprint="sha256:aaa",
                pack_fingerprint="sha256:bbb",
            )

    def test_normalize_records_rejects_invalid_canonical_key_format(self):
        record = AuthoritySection(
            key="Not A Valid Key", heading="Bad key", text="some text"
        )
        wrapped = CollectedAuthorityRecord(
            record=record,
            source_id="direct",
            corpus_slug="example-corpus",
            ingestion_mode="link_only",
        )
        with self.assertRaisesRegex(SourcePlanError, "invalid canonical_key"):
            _normalize_records(
                [wrapped],
                pack_dir=self.pack_dir,
                corpus_entry={"slug": "example-corpus", "title": "Example Corpus"},
                pack_name="example_pack",
                supported_mime_types=frozenset({"text/plain"}),
                converter_extensions=frozenset(),
                source_plan_fingerprint="sha256:aaa",
                pack_fingerprint="sha256:bbb",
            )

    def test_normalize_records_rejects_empty_input(self):
        with self.assertRaisesRegex(SourcePlanError, "has no records"):
            _normalize_records(
                [],
                pack_dir=self.pack_dir,
                corpus_entry={"slug": "example-corpus", "title": "Example Corpus"},
                pack_name="example_pack",
                supported_mime_types=frozenset({"text/plain"}),
                converter_extensions=frozenset(),
                source_plan_fingerprint="sha256:aaa",
                pack_fingerprint="sha256:bbb",
            )

    # -- _publisher_source_filename / _publisher_source_sidecar_member -------

    def test_publisher_source_filename_rejects_non_string_explicit_value(self):
        record = replace(
            self._authority_source_record("example:1"),
            metadata={"publisher_source_filename": 123},
        )
        with self.assertRaisesRegex(
            SourcePlanError, "publisher_source_filename must be non-empty text"
        ):
            _publisher_source_filename(
                record,
                source_url=record.source_url,
                canonical_key="example:1",
                converter_extensions=frozenset(),
            )

    def test_publisher_source_filename_rejects_backslashes(self):
        record = replace(
            self._authority_source_record("example:1"),
            metadata={"publisher_source_filename": "sub\\dir\\file.txt"},
        )
        with self.assertRaisesRegex(
            SourcePlanError, "publisher_source_filename uses backslashes"
        ):
            _publisher_source_filename(
                record,
                source_url=record.source_url,
                canonical_key="example:1",
                converter_extensions=frozenset(),
            )

    def test_publisher_source_filename_uses_explicit_value_when_valid(self):
        record = replace(
            self._authority_source_record("example:1"),
            metadata={"publisher_source_filename": "custom-name.pdf"},
        )
        name = _publisher_source_filename(
            record,
            source_url=record.source_url,
            canonical_key="example:1",
            converter_extensions=frozenset(),
        )
        self.assertEqual(name, "custom-name.pdf")

    def test_publisher_source_sidecar_member_falls_back_to_canonical_key(self):
        member = _publisher_source_sidecar_member(
            source_url="https://publisher.example/",
            canonical_key="example:1",
            source_digest="a" * 64,
        )
        self.assertTrue(member.startswith(f"publisher-source-{'a' * 64}"))
        self.assertIn("example", member)

    # -- _build_export_payload direct branches --------------------------------

    def _default_corpus_config(self) -> dict:
        return {
            "post_processors": [],
            "preferred_embedder": None,
            "corpus_agent_instructions": None,
            "document_agent_instructions": None,
        }

    def _normalize_default_pack_records(self) -> list[dict]:
        records, report = self._collect()
        self.assertFalse(report.errors)
        return _normalize_records(
            records,
            pack_dir=self.pack_dir,
            corpus_entry={"slug": "example-corpus", "title": "Example Corpus"},
            pack_name="example_pack",
            supported_mime_types=frozenset({"text/plain"}),
            converter_extensions=frozenset(),
            source_plan_fingerprint="sha256:aaa",
            pack_fingerprint="sha256:bbb",
        )

    def test_build_export_payload_rejects_filename_content_conflicts(self):
        first = self._normalize_default_pack_records()[0]
        conflicting = {
            "filename": first["filename"],
            "content_bytes": b"totally different bytes",
        }
        with self.assertRaisesRegex(SourcePlanError, "has conflicting contents"):
            _build_export_payload(
                pack_name="example_pack",
                corpus_entry={"slug": "example-corpus", "title": "Example Corpus"},
                records=[first, conflicting],
                corpus_config=self._default_corpus_config(),
            )

    def test_build_export_payload_requires_sidecar_member_name(self):
        first = dict(self._normalize_default_pack_records()[0])
        first["publisher_source_packaging"] = "sidecar"
        first["publisher_source_member"] = None
        with self.assertRaisesRegex(
            SourcePlanError, "sidecar packaging requires a publisher_source_member"
        ):
            _build_export_payload(
                pack_name="example_pack",
                corpus_entry={"slug": "example-corpus", "title": "Example Corpus"},
                records=[first],
                corpus_config=self._default_corpus_config(),
            )

    def test_build_export_payload_rejects_sidecar_content_conflicts(self):
        first = self._normalize_default_pack_records()[0]
        self.assertEqual(first["publisher_source_packaging"], "sidecar")
        second = dict(first)
        second["canonical_key"] = "example:2"
        second["filename"] = "second-document-filename"
        second["source_content_bytes"] = b"a different publisher payload"
        with self.assertRaisesRegex(
            SourcePlanError, "ZIP source member .* has conflicting contents"
        ):
            _build_export_payload(
                pack_name="example_pack",
                corpus_entry={"slug": "example-corpus", "title": "Example Corpus"},
                records=[first, second],
                corpus_config=self._default_corpus_config(),
            )

    # -- registry-backed defaults ----------------------------------------------

    def test_provider_definitions_reflects_the_real_pipeline_registry(self):
        source_definitions, discovery_definitions = _provider_definitions()
        self.assertIsInstance(source_definitions, list)
        self.assertIsInstance(discovery_definitions, list)

    def test_configured_supported_mime_types_always_includes_text_plain(self):
        result = _configured_supported_mime_types()
        self.assertIn("text/plain", result)

    def test_configured_supported_mime_types_fails_closed_on_registry_error(self):
        with patch(
            "opencontractserver.pipeline.registry.get_allowed_mime_types",
            side_effect=RuntimeError("registry unavailable"),
        ):
            result = _configured_supported_mime_types()
        self.assertEqual(result, frozenset({"text/plain"}))

    def test_registered_converter_extensions_fails_closed_on_registry_error(self):
        with patch(
            "opencontractserver.pipeline.registry.get_all_file_converters_cached",
            side_effect=RuntimeError("registry unavailable"),
        ):
            result = _registered_converter_extensions()
        self.assertEqual(result, frozenset())

    # -- pack/manifest/plan-path resolution helpers ---------------------------

    def test_pack_name_rejects_falsy_name_and_dirname(self):
        with self.assertRaisesRegex(
            SourcePlanError, "pack name must be a non-empty string"
        ):
            _pack_name({"name": None}, Path(""))

    def test_read_pack_manifest_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as empty_dir:
            with self.assertRaisesRegex(
                SourcePlanError, "Could not read authority pack"
            ):
                _read_pack_manifest(Path(empty_dir))

    def test_read_pack_manifest_rejects_non_mapping_content(self):
        with tempfile.TemporaryDirectory() as non_mapping_dir:
            (Path(non_mapping_dir) / "pack.yaml").write_text(
                "- a\n- list\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                SourcePlanError, "pack manifest must be a mapping"
            ):
                _read_pack_manifest(Path(non_mapping_dir))

    def test_source_plan_path_rejects_path_escaping_pack_dir(self):
        with self.assertRaisesRegex(
            SourcePlanError, "escapes the authority pack directory"
        ):
            _source_plan_path(self.pack_dir, {"sources": "../outside.yaml"}, None)

    def test_source_plan_path_rejects_missing_file(self):
        with self.assertRaisesRegex(SourcePlanError, "source plan not found"):
            _source_plan_path(self.pack_dir, {"sources": "does-not-exist.yaml"}, None)

    # -- _corpus_export_config -------------------------------------------------

    def test_corpus_export_config_loads_persona_text(self):
        persona_path = self.pack_dir / "persona.md"
        persona_path.write_text(
            "  You are a diligent legal analyst.  \n", encoding="utf-8"
        )
        config = _corpus_export_config(
            pack_dir=self.pack_dir,
            manifest={},
            corpus_entry={"slug": "example-corpus", "persona": "persona.md"},
        )
        self.assertEqual(
            config["corpus_agent_instructions"], "You are a diligent legal analyst."
        )

    def test_corpus_export_config_rejects_persona_path_escaping_pack_dir(self):
        with self.assertRaisesRegex(SourcePlanError, "escapes the pack directory"):
            _corpus_export_config(
                pack_dir=self.pack_dir,
                manifest={},
                corpus_entry={"slug": "example-corpus", "persona": "../outside.md"},
            )

    def test_corpus_export_config_rejects_missing_persona_file(self):
        with self.assertRaisesRegex(SourcePlanError, "Could not read corpus persona"):
            _corpus_export_config(
                pack_dir=self.pack_dir,
                manifest={},
                corpus_entry={"slug": "example-corpus", "persona": "missing.md"},
            )

    def test_corpus_export_config_normalizes_explicit_none_post_processors(self):
        config = _corpus_export_config(
            pack_dir=self.pack_dir,
            manifest={},
            corpus_entry={"slug": "example-corpus", "post_processors": None},
        )
        self.assertEqual(config["post_processors"], [])

    def test_corpus_export_config_rejects_non_string_post_processors(self):
        with self.assertRaisesRegex(
            SourcePlanError, "post_processors must be a list of strings"
        ):
            _corpus_export_config(
                pack_dir=self.pack_dir,
                manifest={},
                corpus_entry={"slug": "example-corpus", "post_processors": [1, 2]},
            )

    # -- _manifest_corpora -------------------------------------------------------

    def test_manifest_corpora_rejects_missing_or_empty_corpora(self):
        with self.assertRaisesRegex(
            SourcePlanError, "must declare a non-empty corpora list"
        ):
            _manifest_corpora({})
        with self.assertRaisesRegex(
            SourcePlanError, "must declare a non-empty corpora list"
        ):
            _manifest_corpora({"corpora": []})

    def test_manifest_corpora_rejects_non_mapping_entry(self):
        with self.assertRaisesRegex(SourcePlanError, r"corpora\[0\] must be a mapping"):
            _manifest_corpora({"corpora": ["not-a-mapping"]})

    def test_manifest_corpora_rejects_invalid_slug(self):
        with self.assertRaisesRegex(SourcePlanError, r"corpora\[0\]\.slug is invalid"):
            _manifest_corpora({"corpora": [{"slug": "Not Valid!", "title": "X"}]})

    def test_manifest_corpora_rejects_missing_title(self):
        with self.assertRaisesRegex(
            SourcePlanError, r"corpora\[0\]\.title is required"
        ):
            _manifest_corpora({"corpora": [{"slug": "valid-slug"}]})

    def test_manifest_corpora_rejects_duplicate_slug(self):
        with self.assertRaisesRegex(SourcePlanError, "duplicate corpus slug"):
            _manifest_corpora(
                {
                    "corpora": [
                        {"slug": "dup-slug", "title": "First"},
                        {"slug": "dup-slug", "title": "Second"},
                    ]
                }
            )

    # -- _corpus_aliases -----------------------------------------------------

    def test_corpus_aliases_returns_none_when_spec_not_declared(self):
        self.assertIsNone(_corpus_aliases(self.pack_dir, {"slug": "example-corpus"}))

    def test_corpus_aliases_rejects_spec_path_escaping_pack_dir(self):
        with self.assertRaisesRegex(SourcePlanError, "escapes the pack directory"):
            _corpus_aliases(
                self.pack_dir, {"slug": "example-corpus", "spec": "../outside.json"}
            )

    def test_corpus_aliases_rejects_missing_or_invalid_json_spec(self):
        with self.assertRaisesRegex(SourcePlanError, "Could not read corpus spec"):
            _corpus_aliases(
                self.pack_dir, {"slug": "example-corpus", "spec": "missing.json"}
            )

        bad_json = self.pack_dir / "bad-spec.json"
        bad_json.write_text("{not valid json", encoding="utf-8")
        with self.assertRaisesRegex(SourcePlanError, "Could not read corpus spec"):
            _corpus_aliases(
                self.pack_dir, {"slug": "example-corpus", "spec": "bad-spec.json"}
            )

    def test_corpus_aliases_returns_none_when_spec_omits_aliases(self):
        spec_path = self.pack_dir / "no-aliases-spec.json"
        spec_path.write_text(json.dumps({}), encoding="utf-8")
        self.assertIsNone(
            _corpus_aliases(
                self.pack_dir,
                {"slug": "example-corpus", "spec": "no-aliases-spec.json"},
            )
        )

    def test_corpus_aliases_rejects_non_string_alias_entries(self):
        spec_path = self.pack_dir / "bad-aliases-spec.json"
        spec_path.write_text(json.dumps({"aliases": ["ok", 123]}), encoding="utf-8")
        with self.assertRaisesRegex(
            SourcePlanError, "aliases must be a list of strings"
        ):
            _corpus_aliases(
                self.pack_dir,
                {"slug": "example-corpus", "spec": "bad-aliases-spec.json"},
            )

    # -- small validation primitives ------------------------------------------

    def test_json_safe_handles_dates_enums_and_rejects_unsupported_types(self):
        self.assertEqual(_json_safe(date(2026, 1, 15)), "2026-01-15")

        class _SampleEnum(Enum):
            A = "sample-enum-value"

        self.assertEqual(_json_safe(_SampleEnum.A), "sample-enum-value")

        with self.assertRaisesRegex(SourcePlanError, "contains non-JSON value"):
            _json_safe(object())

    def test_require_string_rejects_non_string_and_blank_values(self):
        with self.assertRaisesRegex(SourcePlanError, "must be a non-empty string"):
            _require_string(123, "label")
        with self.assertRaisesRegex(SourcePlanError, "must be a non-empty string"):
            _require_string("   ", "label")

    def test_require_http_url_rejects_non_https(self):
        with self.assertRaisesRegex(SourcePlanError, "must be an HTTPS URL"):
            _require_http_url("http://publisher.example/1", "label")

    def test_require_canonical_key_rejects_bad_format(self):
        with self.assertRaisesRegex(SourcePlanError, "not a canonical authority key"):
            _require_canonical_key("Not A Valid Key", "label")

    def test_normalize_relationship_type_rejects_non_string(self):
        with self.assertRaisesRegex(
            SourcePlanError, "must be a relationship type string"
        ):
            _normalize_relationship_type(123, "label")

    def test_content_sentinel_rejects_blank_text(self):
        with self.assertRaisesRegex(
            SourcePlanError, "authority record has no extracted text"
        ):
            _content_sentinel("   \n\t  ")

    def test_candidate_discovery_metadata_handles_none_candidate(self):
        self.assertEqual(_candidate_discovery_metadata(None), {})

    def test_candidate_promoted_metadata_handles_none_candidate(self):
        self.assertEqual(
            _candidate_promoted_metadata(None, canonical_key="example:1"), {}
        )

    # -- _validate_authority_metadata -----------------------------------------

    def test_validate_authority_metadata_rejects_non_mapping(self):
        with self.assertRaisesRegex(SourcePlanError, "must be a mapping"):
            _validate_authority_metadata("not-a-mapping", "label")

    def test_validate_authority_metadata_rejects_non_string_keys(self):
        with self.assertRaisesRegex(SourcePlanError, "keys must be non-empty strings"):
            _validate_authority_metadata({123: "value"}, "label")

    def test_validate_authority_metadata_rejects_non_json_safe_values(self):
        with self.assertRaisesRegex(SourcePlanError, "must contain JSON-safe values"):
            _validate_authority_metadata({"custom_field": float("nan")}, "label")

    def test_validate_authority_metadata_rejects_invalid_authority_type(self):
        with self.assertRaisesRegex(SourcePlanError, "authority_type must be one of"):
            _validate_authority_metadata({"authority_type": "not-a-real-type"}, "label")

    def test_validate_authority_metadata_rejects_invalid_authority_weight(self):
        with self.assertRaisesRegex(
            SourcePlanError, "not a recognized authority weight"
        ):
            _validate_authority_metadata(
                {"authority_weight": "not-a-real-weight"}, "label"
            )

    def test_validate_authority_metadata_rejects_invalid_status(self):
        with self.assertRaisesRegex(SourcePlanError, "not a recognized source status"):
            _validate_authority_metadata({"status": "not-a-real-status"}, "label")

    def test_validate_authority_metadata_normalizes_and_rejects_dates(self):
        normalized = _validate_authority_metadata(
            {"issued_date": "2026-01-15"}, "label"
        )
        self.assertEqual(normalized["issued_date"], "2026-01-15")

        with self.assertRaisesRegex(SourcePlanError, "filed_date"):
            _validate_authority_metadata({"filed_date": "not-a-date"}, "label")

    # -- write_collection_report / write_aggregate_manifest --------------------

    def test_write_collection_report_persists_json(self):
        report = CollectionReport(
            pack_name="example_pack",
            plan_path=str(self.pack_dir / "sources.yaml"),
            discovered=3,
            fetched=2,
            linked=1,
            rights_approved=True,
            source_plan_fingerprint="sha256:aaa",
            pack_fingerprint="sha256:bbb",
            decisions=[{"source_id": "s", "candidate": "example:1"}],
            errors=[],
        )
        output_dir = self.pack_dir / "imports"
        path = write_collection_report(output_dir, report)
        self.assertTrue(path.is_file())
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["pack_name"], "example_pack")
        self.assertEqual(payload["discovered"], 3)
        self.assertTrue(payload["rights_approved"])

    def test_write_aggregate_manifest_persists_relative_zip_paths(self):
        case = ArtifactCase(
            pack_name="example_pack",
            corpus_slug="example-corpus",
            corpus_title="Example Corpus",
            export_zip_path=str(self.pack_dir / "imports" / "example-corpus.zip"),
            expected_document_title="A Title",
            expected_content_text="Some sentinel text",
            expected_canonical_keys=("example:1",),
            expected_document_count=1,
            expected_provider_relationships=(),
            source_plan_fingerprint="sha256:aaa",
            pack_fingerprint="sha256:bbb",
        )
        manifest_path = self.pack_dir / "manifest" / "aggregate.json"
        result_path = write_aggregate_manifest(manifest_path, [case])
        self.assertTrue(result_path.is_file())
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["cases"][0]["packName"], "example_pack")
        self.assertEqual(
            payload["cases"][0]["exportZipPath"],
            os.path.relpath(
                self.pack_dir / "imports" / "example-corpus.zip",
                manifest_path.parent,
            ),
        )
