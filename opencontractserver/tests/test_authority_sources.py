"""Shared authority source-record and attachment extraction tests."""

from __future__ import annotations

import io
import sys
import zipfile
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from pypdf import PdfWriter

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    parse_section_spec,
)
from opencontractserver.enrichment.authority_sources import (
    AuthorityArchiveMember,
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RelationshipType,
    RightsStatus,
    SourceRelationship,
    SourceStatus,
    _read_zip_member_bounded,
    _validated_zip_members,
    extract_authority_archive_members,
    extract_authority_text,
    fetch_and_extract_authority_record,
    host_matches_declared_sources,
    infer_authority_mime_type,
    normalize_mime_type,
    normalize_source_status,
    parse_authority_date,
)


class AuthoritySourceRecordTests(SimpleTestCase):
    def _record(self, **overrides) -> AuthoritySourceRecord:
        values: dict[str, Any] = {
            "canonical_key": "ercot-pgrr:145",
            "title": "PGRR 145",
            "source_url": "https://www.ercot.com/mktrules/issues/PGRR145",
            "source_identifier": "PGRR145",
            "publisher": "ERCOT",
            "jurisdiction": "us-tx-ercot",
            "authority_type": "admin-rule",
            "instrument_type": InstrumentType.REVISION_REQUEST,
            "issued_date": "2026-06-18",
            "effective_from": "07/11/2026",
            "effective_until": None,
            "status": SourceStatus.APPROVED,
            "authority_weight": AuthorityWeight.EVIDENTIARY,
            "parent_key": None,
            "version_label": "approved",
            "content": b"PGRR 145 approved text",
            "mime_type": "text/plain",
            "corpus_slug": "ercot-large-load-revision-history",
            "rights_status": RightsStatus.REVIEW_REQUIRED,
            "publisher_evidence": (
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.PARSED_CONTENT,
                    value="PGRR145",
                ),
            ),
        }
        values.update(overrides)
        return AuthoritySourceRecord(**values)

    def test_record_validates_and_exposes_legacy_section_surface(self):
        relationships = (
            SourceRelationship(
                target_key="ercot-planning:9",
                relationship_type=RelationshipType.REVISES,
            ),
            SourceRelationship(
                target_key="ercot-pgrr:115",
                relationship_type=RelationshipType.SUPERSEDES,
            ),
        )
        record = self._record(relationships=relationships)
        assert record.key == "ercot-pgrr:145"
        assert record.heading == "PGRR 145"
        assert record.text == "PGRR 145 approved text"
        assert record.content_hash is not None
        assert len(record.content_hash) == 64
        metadata = record.as_document_metadata()
        assert metadata["effective_from"] == "2026-07-11"
        assert "effective_date_review_status" not in metadata
        assert metadata["authority_weight"] == "EVIDENTIARY"
        metadata_relationships = metadata["relationships"]
        assert isinstance(metadata_relationships, list)
        assert metadata_relationships[0]["relationship_type"] == "REVISES"
        assert metadata["supersedes_key"] == "ercot-pgrr:115"

    def test_current_record_without_effective_date_carries_explicit_review_state(self):
        record = self._record(effective_from=None, current_version=True)

        metadata = record.as_document_metadata()

        assert metadata["effective_date_review_status"] == "UNKNOWN_NEEDS_REVIEW"

    def test_historical_record_without_effective_date_does_not_claim_current_review_state(
        self,
    ):
        record = self._record(effective_from=None, current_version=False)

        metadata = record.as_document_metadata()

        assert "effective_date_review_status" not in metadata

    def test_unknown_controlled_values_fail_instead_of_guessing(self):
        with self.assertRaisesMessage(ValueError, "status must be one of"):
            self._record(status="maybe approved")
        with self.assertRaisesMessage(ValueError, "instrument_type must be one of"):
            self._record(instrument_type="WEB_PAGE")
        with self.assertRaisesMessage(ValueError, "ALL_AUTHORITY_TYPES"):
            self._record(authority_type="tariff")

    def test_content_hash_mismatch_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "content_hash mismatch"):
            self._record(content_hash="0" * 64)

    def test_portable_rendition_requires_complete_safe_fields(self):
        with self.assertRaisesMessage(
            ValueError,
            "portable rendition content, MIME type, and filename",
        ):
            self._record(portable_rendition_content=b"%PDF-1.7")
        with self.assertRaisesMessage(
            ValueError,
            "portable_rendition_filename must be one safe filename segment",
        ):
            self._record(
                portable_rendition_content=b"%PDF-1.7",
                portable_rendition_mime_type="application/pdf",
                portable_rendition_filename="../rendition.pdf",
            )

        record = self._record(
            portable_rendition_content=b"%PDF-1.7",
            portable_rendition_mime_type="Application/PDF; charset=binary",
            portable_rendition_filename="rendition.pdf",
        )
        self.assertEqual(record.portable_rendition_mime_type, "application/pdf")

    def test_record_rejects_invalid_corpus_slug_and_relationship_shape(self):
        with self.assertRaisesMessage(ValueError, "corpus_slug must be"):
            self._record(corpus_slug="ERCOT Rules")
        with self.assertRaisesMessage(ValueError, "SourceRelationship instances"):
            self._record(relationships=({"target_key": "ercot-planning:9"},))

    def test_current_version_requires_a_real_boolean(self):
        with self.assertRaisesMessage(
            ValueError, "current_version must be true, false, or null"
        ):
            self._record(current_version="false")

    def test_publisher_evidence_requires_typed_nonempty_signals(self):
        with self.assertRaisesMessage(
            ValueError, "AuthorityPublisherEvidence instances"
        ):
            self._record(publisher_evidence=({"source": "TITLE", "value": "x"},))
        with self.assertRaisesMessage(ValueError, "non-empty string"):
            AuthorityPublisherEvidence(
                source=PublisherEvidenceSource.TITLE,
                value=" ",
            )

    def test_relationship_verification_requires_a_real_boolean(self):
        with self.assertRaisesMessage(
            ValueError, "verified must be true or false; got 'false'"
        ):
            SourceRelationship(
                target_key="ercot-planning:9",
                relationship_type="REVISES",
                verified="false",  # type: ignore[arg-type]
            )

        with self.assertRaisesMessage(
            ValueError, "verified must be true or false; got 'false'"
        ):
            parse_section_spec(
                {
                    "sections": [
                        {
                            "key": "ercot-pgrr:145",
                            "heading": "PGRR 145",
                            "text": "Revision request text.",
                            "relationships": [
                                {
                                    "target_key": "ercot-planning:9",
                                    "relationship_type": "REVISES",
                                    "verified": "false",
                                }
                            ],
                        }
                    ]
                },
                label="quoted verification",
            )

    def test_date_and_status_normalization_are_explicit(self):
        parsed = parse_authority_date("07/11/2026")
        assert parsed is not None
        assert parsed.isoformat() == "2026-07-11"
        assert normalize_source_status("in effect") == "EFFECTIVE"
        with self.assertRaises(ValueError):
            parse_authority_date("11/07/26")

    def test_relationship_vocabulary_matches_shared_constants(self):
        assert {item.value for item in RelationshipType} == set(
            C.AUTHORITY_RELATIONSHIP_TYPES
        )

    def test_parse_authority_date_accepts_datetime_and_rejects_non_string_types(self):
        parsed = parse_authority_date(datetime(2026, 1, 1, 12, 0))
        assert parsed is not None
        self.assertEqual(parsed.isoformat(), "2026-01-01")

        with self.assertRaisesMessage(
            ValueError, "authority date must be ISO text or date, got int"
        ):
            parse_authority_date(12345)  # type: ignore[arg-type]

    def test_host_matches_declared_sources_exact_subdomain_and_bare_suffix(self):
        # A missing/blank host never matches, regardless of declared hosts.
        self.assertFalse(host_matches_declared_sources(None, ["ercot.com"]))
        self.assertFalse(host_matches_declared_sources("   ", ["ercot.com"]))
        # Exact and dot-suffix (subdomain) matches succeed.
        self.assertTrue(host_matches_declared_sources("ercot.com", ["ercot.com"]))
        self.assertTrue(host_matches_declared_sources("www.ercot.com", ["ercot.com"]))
        # A bare string suffix (no leading dot) must NOT satisfy the match --
        # this is the exact SSRF-adjacent guarantee the docstring promises.
        self.assertFalse(host_matches_declared_sources("notercot.com", ["ercot.com"]))

    def test_relationship_target_key_must_be_canonical(self):
        with self.assertRaisesMessage(
            ValueError, "invalid relationship target canonical key"
        ):
            SourceRelationship(
                target_key="bad key no colon",
                relationship_type=RelationshipType.CITES,
            )

    def test_publisher_evidence_locator_must_be_non_empty_when_set(self):
        with self.assertRaisesMessage(
            ValueError,
            "publisher evidence locator must be a non-empty string when set",
        ):
            AuthorityPublisherEvidence(
                source=PublisherEvidenceSource.TITLE,
                value="v",
                locator="   ",
            )

    def test_publisher_evidence_locator_round_trips_when_valid(self):
        evidence = AuthorityPublisherEvidence(
            source=PublisherEvidenceSource.TITLE,
            value="v",
            locator="  page 3  ",
        )
        self.assertEqual(evidence.locator, "page 3")
        self.assertEqual(evidence.as_dict()["locator"], "page 3")

    def test_record_rejects_invalid_canonical_key(self):
        with self.assertRaisesMessage(ValueError, "invalid canonical_key"):
            self._record(canonical_key="Bad Key")

    def test_record_rejects_empty_string_fields(self):
        with self.assertRaisesMessage(ValueError, "title must be a non-empty string"):
            self._record(title="   ")

    def test_record_rejects_empty_or_non_bytes_content(self):
        with self.assertRaisesMessage(ValueError, "content must be non-empty bytes"):
            self._record(content=b"")
        with self.assertRaisesMessage(ValueError, "content must be non-empty bytes"):
            self._record(content="not bytes")

    def test_record_rejects_effective_until_before_effective_from(self):
        with self.assertRaisesMessage(
            ValueError, "effective_until cannot precede effective_from"
        ):
            self._record(effective_from="2026-01-01", effective_until="2025-01-01")

    def test_record_rejects_invalid_parent_key(self):
        with self.assertRaisesMessage(ValueError, "invalid parent_key"):
            self._record(parent_key="bad parent")

    def test_record_accepts_and_strips_a_valid_parent_key(self):
        record = self._record(parent_key="  ercot-planning:9  ")
        self.assertEqual(record.parent_key, "ercot-planning:9")

    def test_record_rejects_non_bytes_or_empty_portable_rendition_content(self):
        with self.assertRaisesMessage(
            ValueError, "portable_rendition_content must be non-empty bytes"
        ):
            self._record(
                portable_rendition_content="not-bytes",
                portable_rendition_mime_type="application/pdf",
                portable_rendition_filename="rendition.pdf",
            )
        with self.assertRaisesMessage(
            ValueError, "portable_rendition_content must be non-empty bytes"
        ):
            self._record(
                portable_rendition_content=b"",
                portable_rendition_mime_type="application/pdf",
                portable_rendition_filename="rendition.pdf",
            )

    def test_record_normalizes_naive_retrieved_at_and_rejects_non_datetime(self):
        with self.assertRaisesMessage(ValueError, "retrieved_at must be a datetime"):
            self._record(retrieved_at="not-a-datetime")

        record = self._record(retrieved_at=datetime(2026, 1, 1, 12, 0))
        self.assertIsNotNone(record.retrieved_at.tzinfo)
        self.assertEqual(record.retrieved_at.isoformat(), "2026-01-01T12:00:00+00:00")

    def test_record_source_mime_type_property_mirrors_mime_type(self):
        record = self._record()
        self.assertEqual(record.source_mime_type, record.mime_type)

    def test_source_metadata_refresh_removes_stale_fields_and_keeps_curator_state(
        self,
    ):
        merged = AuthorityCorpusBootstrapper._merge_source_metadata(
            existing_meta={
                "canonical_key": "old-key:1",
                "status": "CURATOR_STATUS",
                "supersedes_key": "old-law:1",
                "amends_key": "old-law:2",
                "authority_provider_fields": [
                    "status",
                    "supersedes_key",
                    "amends_key",
                ],
                # A stored string is one field name, not an iterable of
                # single-character locks.
                "authority_curator_fields": "status",
                "authority_curator_overrides": {"amends_key": "curator-law:2"},
            },
            source_meta={
                "status": "SUPERSEDED",
                "publisher": "ERCOT",
            },
            canonical_key="ercot-pgrr:145",
            aliases=None,
        )

        self.assertEqual(merged["canonical_key"], "ercot-pgrr:145")
        self.assertEqual(merged["authority"], "ercot-pgrr")
        self.assertEqual(merged["status"], "CURATOR_STATUS")
        self.assertNotIn("supersedes_key", merged)
        self.assertEqual(merged["amends_key"], "curator-law:2")
        self.assertEqual(merged["authority_curator_fields"], ["status"])
        self.assertEqual(
            merged["authority_provider_fields"],
            ["amends_key", "publisher", "status"],
        )

        malformed_lock = AuthorityCorpusBootstrapper._merge_source_metadata(
            existing_meta={
                "status": "OLD",
                "authority_provider_fields": ["status"],
                "authority_curator_fields": 7,
            },
            source_meta={"status": "CURRENT"},
            canonical_key="ercot-pgrr:145",
            aliases=None,
        )
        self.assertEqual(malformed_lock["status"], "CURRENT")
        self.assertEqual(malformed_lock["authority_curator_fields"], [])


class AuthorityAttachmentExtractionTests(SimpleTestCase):
    @staticmethod
    def _docx_with_members(
        members: list[tuple[str, bytes]],
        *,
        compression: int = zipfile.ZIP_DEFLATED,
    ) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
            for name, value in members:
                archive.writestr(name, value)
        return buffer.getvalue()

    def test_visible_html_excludes_script_and_style(self):
        content = (
            b"<html><style>hidden css</style><body><h1>Rule 25.361</h1>"
            b"<script>hidden()</script><p>Effective text.</p></body></html>"
        )
        assert infer_authority_mime_type(content) == "text/html"
        text = extract_authority_text(content, "text/html")
        assert "Rule 25.361" in text
        assert "Effective text." in text
        assert "hidden" not in text

    def test_docx_xml_is_extracted_without_optional_python_docx(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "word/document.xml",
                (
                    '<w:document xmlns:w="urn:test"><w:body><w:p>'
                    "<w:r><w:t>Large-load form</w:t></w:r>"
                    "</w:p></w:body></w:document>"
                ),
            )
        content = buffer.getvalue()
        mime = infer_authority_mime_type(content, "form.docx")
        assert mime.endswith("wordprocessingml.document")
        assert extract_authority_text(content, mime) == "Large-load form"

    def test_office_zip_member_count_budget_fails_in_inference(self):
        content = self._docx_with_members(
            [
                ("word/document.xml", b"<document>text</document>"),
                ("word/styles.xml", b"<styles/>"),
            ],
            compression=zipfile.ZIP_STORED,
        )
        with (
            patch(
                "opencontractserver.enrichment.authority_sources."
                "AUTHORITY_ZIP_MAX_MEMBERS",
                1,
            ),
            self.assertRaisesMessage(ValueError, "member-count budget exceeded"),
        ):
            infer_authority_mime_type(content, "document.docx")

    def test_office_zip_total_uncompressed_budget_fails_explicitly(self):
        content = self._docx_with_members(
            [
                ("word/document.xml", b"<document>1234</document>"),
                ("word/styles.xml", b"<styles>5678</styles>"),
            ],
            compression=zipfile.ZIP_STORED,
        )
        with (
            patch(
                "opencontractserver.enrichment.authority_sources."
                "AUTHORITY_ZIP_MAX_UNCOMPRESSED_BYTES",
                20,
            ),
            patch(
                "opencontractserver.enrichment.authority_sources."
                "AUTHORITY_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES",
                100,
            ),
            self.assertRaisesMessage(ValueError, "uncompressed-byte budget exceeded"),
        ):
            extract_authority_text(
                content,
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document",
            )

    def test_office_zip_per_member_budget_fails_explicitly(self):
        content = self._docx_with_members(
            [("word/document.xml", b"<document>large</document>")],
            compression=zipfile.ZIP_STORED,
        )
        with (
            patch(
                "opencontractserver.enrichment.authority_sources."
                "AUTHORITY_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES",
                8,
            ),
            self.assertRaisesMessage(
                ValueError, "per-member uncompressed-byte budget exceeded"
            ),
        ):
            infer_authority_mime_type(content, "document.docx")

    def test_office_zip_compression_ratio_budget_fails_explicitly(self):
        content = self._docx_with_members(
            [("word/document.xml", b"<document>" + b"A" * 2_000 + b"</document>")]
        )
        with (
            patch(
                "opencontractserver.enrichment.authority_sources."
                "AUTHORITY_ZIP_MAX_COMPRESSION_RATIO",
                2.0,
            ),
            self.assertRaisesMessage(ValueError, "compression-ratio budget exceeded"),
        ):
            infer_authority_mime_type(content, "document.docx")

    def test_office_zip_encrypted_member_is_rejected_before_read(self):
        content = bytearray(
            self._docx_with_members(
                [("word/document.xml", b"<document>text</document>")],
                compression=zipfile.ZIP_STORED,
            )
        )
        local_header = content.find(b"PK\x03\x04")
        central_header = content.find(b"PK\x01\x02")
        self.assertGreaterEqual(local_header, 0)
        self.assertGreaterEqual(central_header, 0)
        content[local_header + 6 : local_header + 8] = (1).to_bytes(2, "little")
        content[central_header + 8 : central_header + 10] = (1).to_bytes(2, "little")
        with self.assertRaisesMessage(ValueError, "is encrypted"):
            infer_authority_mime_type(bytes(content), "document.docx")

    def test_truncated_legacy_xls_magic_fails_explicitly(self):
        with self.assertRaisesMessage(ValueError, "unsupported authority attachment"):
            infer_authority_mime_type(b"\xd0\xcf\x11\xe0legacy-xls", "form.xls")

    def test_legacy_xls_mime_is_inferred_from_ole_magic_and_extension(self):
        content = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-xls"

        self.assertEqual(
            infer_authority_mime_type(content, "https://publisher.example/form.xls"),
            "application/vnd.ms-excel",
        )

    @patch(
        "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
        return_value=(
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-xls",
            "publisher.example",
        ),
    )
    def test_fetch_factory_defers_legacy_xls_extraction_to_converter(self, fetch):
        record = fetch_and_extract_authority_record(
            url="https://publisher.example/form.xls",
            canonical_key="example:legacy-xls",
            title="Legacy spreadsheet",
            source_identifier="legacy-xls",
            publisher="Example Publisher",
            jurisdiction="example",
            authority_type="regulation",
            instrument_type="REGULATION",
            status="CURRENT",
            authority_weight="CONTROLLING",
            corpus_slug="example-corpus",
            rights_status="PUBLIC_DOMAIN",
        )

        fetch.assert_called_once()
        self.assertEqual(
            record.content,
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-xls",
        )
        self.assertEqual(record.mime_type, "application/vnd.ms-excel")
        self.assertIsNone(record.extracted_text)
        self.assertIs(
            record.metadata["text_extraction_deferred_to_pipeline"],
            True,
        )
        self.assertEqual(record.metadata["text_extraction_source_extension"], "xls")
        self.assertEqual(record.metadata["final_source_host"], "publisher.example")

    def test_fetch_factory_defers_textless_scanned_pdf_to_pipeline(self):
        pdf_buffer = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(pdf_buffer)
        scanned_pdf = pdf_buffer.getvalue()

        with patch(
            "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
            return_value=(scanned_pdf, "publisher.example"),
        ) as fetch:
            record = fetch_and_extract_authority_record(
                url="https://publisher.example/scanned-order.pdf",
                canonical_key="example:scanned-order",
                title="Scanned order",
                source_identifier="scanned-order",
                publisher="Example Publisher",
                jurisdiction="example",
                authority_type="regulation",
                instrument_type="FINAL_ORDER",
                status="CURRENT",
                authority_weight="CONTROLLING",
                corpus_slug="example-corpus",
                rights_status="PUBLIC_DOMAIN",
            )

        fetch.assert_called_once()
        self.assertEqual(record.content, scanned_pdf)
        self.assertEqual(record.mime_type, "application/pdf")
        self.assertIsNone(record.extracted_text)
        self.assertIs(
            record.metadata["text_extraction_deferred_to_pipeline"],
            True,
        )
        self.assertEqual(record.metadata["text_extraction_source_extension"], "pdf")
        self.assertEqual(record.metadata["final_source_host"], "publisher.example")

    @patch(
        "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
        return_value=(b"<p>Official rule text</p>", "puc.texas.gov"),
    )
    def test_fetch_factory_uses_safe_boundary_and_provenance(self, fetch):
        record = fetch_and_extract_authority_record(
            url="https://puc.texas.gov/rule",
            canonical_key="tx-admin-puct:25.361",
            title="Rule 25.361",
            source_identifier="16-TAC-25.361",
            publisher="PUCT",
            jurisdiction="us-tx",
            authority_type="regulation",
            instrument_type="REGULATION",
            status="CURRENT",
            authority_weight="CONTROLLING",
            corpus_slug="puct-electric-rules-and-controlling-orders",
            rights_status="PUBLIC_DOMAIN",
            publisher_evidence=(
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.PARSED_CONTENT,
                    value="Rule 25.361",
                ),
            ),
        )
        fetch.assert_called_once()
        assert record.text == "Official rule text"
        assert record.metadata["final_source_host"] == "puc.texas.gov"

    def test_normalize_mime_type_rejects_invalid_value(self):
        with self.assertRaisesMessage(ValueError, "invalid MIME type"):
            normalize_mime_type("garbage")

    def test_infer_authority_mime_type_detects_png(self):
        content = b"\x89PNG\r\n\x1a\n" + b"restofpngdata"
        self.assertEqual(infer_authority_mime_type(content), "image/png")

    def test_infer_authority_mime_type_detects_legacy_doc_and_generic_ole(self):
        ole_content = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-doc"
        self.assertEqual(
            infer_authority_mime_type(ole_content, "form.doc"),
            "application/msword",
        )
        # An OLE compound document with no recognized suffix is reported as a
        # generic OLE storage blob rather than guessed at.
        self.assertEqual(
            infer_authority_mime_type(ole_content, "form.unknownext"),
            "application/x-ole-storage",
        )

    def test_infer_authority_mime_type_rejects_malformed_zip_magic(self):
        content = b"PK\x03\x04" + b"garbage-not-a-real-zip-body"
        with self.assertRaisesMessage(
            ValueError, "source begins like ZIP but is malformed"
        ):
            infer_authority_mime_type(content, "x.docx")

    def test_infer_authority_mime_type_detects_pptx_and_xlsx_zip_roots(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("ppt/presentation.xml", "<presentation/>")
        self.assertEqual(
            infer_authority_mime_type(buffer.getvalue(), "deck.pptx"),
            "application/vnd.openxmlformats-officedocument."
            "presentationml.presentation",
        )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("xl/workbook.xml", "<workbook/>")
        self.assertEqual(
            infer_authority_mime_type(buffer.getvalue(), "load.xlsx"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_infer_authority_mime_type_rejects_unsupported_zip_attachment(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("readme.txt", "hello")
        with self.assertRaisesMessage(
            ValueError, "unsupported ZIP attachment (expected DOCX or XLSX)"
        ):
            infer_authority_mime_type(buffer.getvalue(), "file.zip")

    def test_infer_authority_mime_type_detects_generic_xml(self):
        content = b'<?xml version="1.0"?><root><item>Rule text</item></root>'
        self.assertEqual(infer_authority_mime_type(content), "text/xml")

    def test_infer_authority_mime_type_rejects_unsupported_guessed_extension(self):
        content = b"not actually a zip file, just text pretending"
        with self.assertRaisesMessage(
            ValueError, "unsupported authority attachment MIME type 'application/zip'"
        ):
            infer_authority_mime_type(content, "archive.zip")

    def test_infer_authority_mime_type_rejects_undecodable_binary_without_guess(self):
        content = bytes([0xFF, 0xFE, 0x00, 0x01, 0x02])
        with self.assertRaisesMessage(
            ValueError, "could not infer a supported MIME type for binary source"
        ):
            infer_authority_mime_type(content, "")

    def test_infer_authority_mime_type_falls_back_to_plain_text(self):
        content = b"Just plain ascii text with no markup at all."
        self.assertEqual(infer_authority_mime_type(content, ""), "text/plain")

    def test_generic_xml_text_extraction_success_and_malformed(self):
        content = b'<?xml version="1.0"?><root><item>Rule text</item></root>'
        self.assertEqual(extract_authority_text(content, "text/xml"), "Rule text")

        with self.assertRaisesMessage(ValueError, "malformed XML authority source"):
            extract_authority_text(b"<not valid", "text/xml")

    def test_pdf_extraction_wraps_parse_errors(self):
        with self.assertRaisesMessage(
            ValueError, "could not parse PDF authority source"
        ):
            extract_authority_text(b"definitely-not-a-real-pdf-file", "application/pdf")

    def test_docx_extraction_skips_missing_member_and_yields_no_text(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/styles.xml", "<styles/>")
        with self.assertRaisesMessage(ValueError, "contained no extractable text"):
            extract_authority_text(
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document",
            )

    def test_docx_extraction_rejects_malformed_member_xml(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", "<not-valid-xml")
        with self.assertRaisesMessage(
            ValueError, "malformed Office Open XML attachment"
        ):
            extract_authority_text(
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document",
            )

    def test_pptx_slide_and_notes_text_is_extracted(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("ppt/presentation.xml", "<presentation/>")
            archive.writestr(
                "ppt/slides/slide1.xml",
                "<sld><t>Grid reliability standard</t></sld>",
            )
            archive.writestr(
                "ppt/notesSlides/notesSlide1.xml",
                "<notes><t>Speaker notes</t></notes>",
            )
        content = buffer.getvalue()
        mime = infer_authority_mime_type(content, "deck.pptx")
        self.assertTrue(mime.endswith("presentationml.presentation"))
        text = extract_authority_text(content, mime)
        self.assertIn("Grid reliability standard", text)
        self.assertIn("Speaker notes", text)

    def test_pptx_extraction_rejects_malformed_zip(self):
        with self.assertRaisesMessage(ValueError, "malformed PPTX authority source"):
            extract_authority_text(
                b"not a zip file",
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation",
            )

    def test_xlsx_shared_strings_and_worksheet_text_is_extracted(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("xl/workbook.xml", "<workbook/>")
            archive.writestr(
                "xl/sharedStrings.xml",
                "<sst><si><t>Peak Demand MW</t></si></sst>",
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                "<worksheet><sheetData><row><c><v>12345</v></c></row>"
                "</sheetData></worksheet>",
            )
        content = buffer.getvalue()
        mime = infer_authority_mime_type(content, "load.xlsx")
        self.assertTrue(mime.endswith("spreadsheetml.sheet"))
        text = extract_authority_text(content, mime)
        self.assertIn("Peak Demand MW", text)
        self.assertIn("12345", text)

    def test_xlsx_extraction_rejects_malformed_zip(self):
        with self.assertRaisesMessage(ValueError, "malformed XLSX authority source"):
            extract_authority_text(
                b"not a zip file",
                "application/vnd.openxmlformats-officedocument." "spreadsheetml.sheet",
            )

    @staticmethod
    def _tiny_png() -> bytes:
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
        return buffer.getvalue()

    def test_png_ocr_extracts_text_via_pytesseract(self):
        png_bytes = self._tiny_png()
        with patch("pytesseract.image_to_string", return_value="Scanned text here"):
            text = extract_authority_text(png_bytes, "image/png")
        self.assertEqual(text, "Scanned text here")

    def test_png_ocr_enforces_megapixel_cap(self):
        png_bytes = self._tiny_png()
        fake_image = MagicMock()
        fake_image.width = 10_000
        fake_image.height = 10_000
        fake_image.__enter__.return_value = fake_image
        fake_image.__exit__.return_value = False
        with patch("PIL.Image.open", return_value=fake_image):
            with self.assertRaisesMessage(ValueError, "50-megapixel OCR cap"):
                extract_authority_text(png_bytes, "image/png")

    def test_png_ocr_wraps_generic_exceptions(self):
        png_bytes = self._tiny_png()
        with patch(
            "pytesseract.image_to_string",
            side_effect=RuntimeError("tesseract binary missing"),
        ):
            with self.assertRaisesMessage(
                ValueError, "could not OCR PNG authority source"
            ):
                extract_authority_text(png_bytes, "image/png")

    def test_png_ocr_requires_pillow_and_pytesseract(self):
        png_bytes = self._tiny_png()
        # Simulate the optional OCR dependency being absent by forcing the
        # in-function ``import pytesseract`` to raise ImportError.
        with patch.dict(sys.modules, {"pytesseract": None}):
            with self.assertRaisesMessage(
                ValueError,
                "PNG authority extraction requires Pillow and pytesseract",
            ):
                extract_authority_text(png_bytes, "image/png")

    def test_fetch_factory_propagates_max_bytes_to_safe_fetch(self):
        with patch(
            "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
            return_value=(b"plain text content", "example.com"),
        ) as fetch:
            fetch_and_extract_authority_record(
                url="https://example.com/doc.txt",
                canonical_key="example:doc",
                title="Doc",
                source_identifier="doc",
                publisher="Example",
                jurisdiction="example",
                authority_type="regulation",
                instrument_type="REGULATION",
                status="CURRENT",
                authority_weight="CONTROLLING",
                corpus_slug="example-corpus",
                rights_status="PUBLIC_DOMAIN",
                max_bytes=12345,
            )
        fetch.assert_called_once_with(
            "https://example.com/doc.txt",
            params=None,
            headers=None,
            extra_ca_certificates=None,
            max_bytes=12345,
        )

    def test_fetch_factory_missing_gotenberg_converter_still_defers_pdf(self):
        pdf_buffer = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(pdf_buffer)
        scanned_pdf = pdf_buffer.getvalue()

        # Force the optional gotenberg-converter import inside the except
        # branch to fail, exercising the ImportError fallback that still
        # defers PDF/DOCX extraction to the parsing pipeline.
        with patch.dict(
            sys.modules,
            {
                "opencontractserver.pipeline.file_converters."
                "gotenberg_converter": None
            },
        ):
            with patch(
                "opencontractserver.enrichment.authority_sources." "safe_fetch_bytes",
                return_value=(scanned_pdf, "publisher.example"),
            ):
                record = fetch_and_extract_authority_record(
                    url="https://publisher.example/scanned-order.pdf",
                    canonical_key="example:scanned-order-2",
                    title="Scanned order",
                    source_identifier="scanned-order-2",
                    publisher="Example Publisher",
                    jurisdiction="example",
                    authority_type="regulation",
                    instrument_type="FINAL_ORDER",
                    status="CURRENT",
                    authority_weight="CONTROLLING",
                    corpus_slug="example-corpus",
                    rights_status="PUBLIC_DOMAIN",
                )
        self.assertIsNone(record.extracted_text)
        self.assertIs(record.metadata["text_extraction_deferred_to_pipeline"], True)
        self.assertEqual(record.metadata["text_extraction_source_extension"], "pdf")

    def test_fetch_factory_reraises_when_neither_converter_nor_pipeline_defers(
        self,
    ):
        # ``.json`` is not a Gotenberg-convertible extension and forcing the
        # MIME type to ``text/xml`` (which the pipeline cannot itself defer)
        # means the original parse failure must propagate unchanged.
        with patch(
            "opencontractserver.enrichment.authority_sources.safe_fetch_bytes",
            return_value=(b"<not valid xml", "publisher.example"),
        ):
            with self.assertRaisesMessage(ValueError, "malformed XML authority source"):
                fetch_and_extract_authority_record(
                    url="https://publisher.example/weird.json",
                    canonical_key="example:weird-json",
                    title="Weird JSON-ish",
                    source_identifier="weird-json",
                    publisher="Example Publisher",
                    jurisdiction="example",
                    authority_type="regulation",
                    instrument_type="REGULATION",
                    status="CURRENT",
                    authority_weight="CONTROLLING",
                    corpus_slug="example-corpus",
                    rights_status="PUBLIC_DOMAIN",
                    mime_type="text/xml",
                )


class AuthorityArchiveMemberExtractionTests(SimpleTestCase):
    """Cover the ZIP-attachment member extraction entry point end to end.

    ``extract_authority_archive_members`` reads every safe member out of a
    publisher ZIP (as opposed to ``extract_authority_text``, which only cares
    about the single OOXML text payload). None of the existing tests called
    it directly.
    """

    def test_extract_archive_members_happy_path(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("readme.txt", "Hello world")
        members = extract_authority_archive_members(buffer.getvalue())
        self.assertEqual(len(members), 1)
        member = members[0]
        self.assertIsInstance(member, AuthorityArchiveMember)
        self.assertEqual(member.name, "readme.txt")
        self.assertEqual(member.content, b"Hello world")
        self.assertEqual(member.mime_type, "text/plain")

    def test_extract_archive_members_rejects_backslash_separator(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo(filename="folder\\evil.txt")
            archive.writestr(info, "data")
        with self.assertRaisesMessage(ValueError, "non-canonical separator"):
            extract_authority_archive_members(buffer.getvalue())

    def test_extract_archive_members_rejects_unsafe_path_traversal(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../evil.txt", "data")
        with self.assertRaisesMessage(ValueError, "unsafe ZIP member path"):
            extract_authority_archive_members(buffer.getvalue())

    def test_extract_archive_members_rejects_unsafe_absolute_path(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo(filename="/etc/passwd")
            archive.writestr(info, "data")
        with self.assertRaisesMessage(ValueError, "unsafe ZIP member path"):
            extract_authority_archive_members(buffer.getvalue())

    def test_extract_archive_members_rejects_empty_member(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("empty.txt", "")
        with self.assertRaisesMessage(ValueError, "is empty"):
            extract_authority_archive_members(buffer.getvalue())

    def test_extract_archive_members_wraps_inference_failure(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("data.bin", bytes([0xFF, 0xFE, 0x00, 0x01, 0x02]))
        with self.assertRaisesMessage(ValueError, "unsupported ZIP member 'data.bin':"):
            extract_authority_archive_members(buffer.getvalue())

    def test_extract_archive_members_rejects_disallowed_mime_type(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("readme.txt", "Hello world")
        with self.assertRaisesMessage(ValueError, "has disallowed MIME type"):
            extract_authority_archive_members(
                buffer.getvalue(), allowed_mime_types=["text/html"]
            )

    def test_extract_archive_members_rejects_malformed_zip(self):
        with self.assertRaisesMessage(ValueError, "malformed publisher ZIP attachment"):
            extract_authority_archive_members(b"not a zip at all")

    def test_extract_archive_members_skips_directories_and_requires_a_file(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo(filename="folder/")
            archive.writestr(info, "")
        # A directory-only archive is skipped entry-by-entry (``continue``)
        # and then fails the "at least one file" post-condition explicitly,
        # rather than silently returning an empty tuple.
        with self.assertRaisesMessage(
            ValueError, "publisher ZIP attachment contains no files"
        ):
            extract_authority_archive_members(buffer.getvalue())


class AuthorityZipMemberHelperTests(SimpleTestCase):
    """Directly exercise the private ZIP-safety helpers.

    These are exercised indirectly elsewhere via patched module-level budget
    constants, but the duplicate-member and invalid-declared-size guards need
    a hand-built ``ZipInfo`` (a legitimate zip file can't declare a negative
    size or, via the public ``zipfile`` API, silently violate its own
    invariants), so we call the helper directly with a minimal fake archive.
    """

    class _FakeArchive:
        def __init__(self, infos: list[zipfile.ZipInfo]) -> None:
            self._infos = infos

        def infolist(self) -> list[zipfile.ZipInfo]:
            return self._infos

    def test_validated_zip_members_rejects_duplicate_member_names(self):
        infos = [
            zipfile.ZipInfo(filename="dup.txt"),
            zipfile.ZipInfo(filename="dup.txt"),
        ]
        with self.assertRaisesMessage(ValueError, "ZIP contains duplicate member"):
            _validated_zip_members(self._FakeArchive(infos))  # type: ignore[arg-type]

    def test_validated_zip_members_rejects_invalid_declared_size(self):
        info = zipfile.ZipInfo(filename="bad.txt")
        info.file_size = -1
        with self.assertRaisesMessage(ValueError, "has invalid size"):
            _validated_zip_members(self._FakeArchive([info]))  # type: ignore[arg-type]

    def test_read_zip_member_bounded_rejects_runtime_overrun(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("big.txt", b"0123456789")
        content = buffer.getvalue()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            info = archive.infolist()[0]
            # The declared size passes validation; this exercises the
            # separate runtime guard that distrusts the actual bytes read
            # against the caller-supplied remaining budget.
            with self.assertRaisesMessage(
                ValueError,
                "uncompressed-byte budget exceeded while reading",
            ):
                _read_zip_member_bounded(archive, info, remaining_budget=3)
