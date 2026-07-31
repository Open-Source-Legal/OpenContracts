"""Shared authority source-record and attachment extraction tests."""

from __future__ import annotations

import io
import zipfile
from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase
from pypdf import PdfWriter

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    parse_section_spec,
)
from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RelationshipType,
    RightsStatus,
    SourceRelationship,
    SourceStatus,
    extract_authority_text,
    fetch_and_extract_authority_record,
    infer_authority_mime_type,
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
