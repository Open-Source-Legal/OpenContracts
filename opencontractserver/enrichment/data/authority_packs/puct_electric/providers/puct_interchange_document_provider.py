"""Fetch one PUCT Interchange project item or attachment."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from typing import ClassVar
from urllib.parse import parse_qs, urlsplit

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
    extract_authority_archive_members,
    extract_authority_text,
    fetch_and_extract_authority_record,
    parse_optional_bool,
)
from opencontractserver.enrichment.data.authority_packs.puct_electric.publisher_identity import (
    classify_puct_structured_document,
    is_exact_puct_final_order_title,
    puct_interchange_key_from_evidence,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import safe_fetch_bytes


def classify_puct_interchange_document(
    canonical_key: str,
    title: str,
    *,
    publisher_document_type: object = None,
    publisher_author_role: object = None,
) -> tuple[InstrumentType, AuthorityWeight, SourceStatus, str, RightsStatus]:
    """Classify only publisher-explicit PUCT document families.

    Interchange is a mixed-rights filing repository, not a homogeneous agency
    publication.  An unfamiliar attachment title must be parked for review
    rather than guessed to be a staff memorandum.
    """

    lowered = title.casefold()
    document_kind, government_authored = classify_puct_structured_document(
        publisher_document_type=publisher_document_type,
        publisher_author_role=publisher_author_role,
    )
    if canonical_key.startswith("puct-order:"):
        if (
            document_kind != "FINAL_ORDER"
            or not government_authored
            or not is_exact_puct_final_order_title(
                str(publisher_document_type or title)
            )
        ):
            raise ValueError(
                "PUCT final-order classification requires exact structured "
                "publisher evidence"
            )
        return (
            InstrumentType.FINAL_ORDER,
            AuthorityWeight.CONTROLLING,
            SourceStatus.ADOPTED,
            "puct-electric-rules-and-orders",
            RightsStatus.PUBLIC_DOMAIN,
        )
    if "testimony" in lowered:
        instrument = InstrumentType.TESTIMONY
        weight = AuthorityWeight.EVIDENTIARY
    elif "comment" in lowered:
        instrument = InstrumentType.COMMENT
        weight = AuthorityWeight.ADVOCACY
    elif "transcript" in lowered:
        instrument = InstrumentType.TRANSCRIPT
        weight = AuthorityWeight.EVIDENTIARY
    elif any(
        marker in lowered
        for marker in (
            "staff memo",
            "staff memorandum",
            "staff recommendation",
            "commission staff",
            "proposal for decision",
            "briefing",
            "report",
            "analysis",
        )
    ):
        instrument = InstrumentType.STAFF_MEMO
        weight = AuthorityWeight.INTERPRETIVE
    elif canonical_key.startswith("puct-project:") and canonical_key.count(":") == 1:
        # The project landing page is the stable parent-proceeding record, not
        # an attached party filing.
        return (
            InstrumentType.STAFF_MEMO,
            AuthorityWeight.INTERPRETIVE,
            SourceStatus.PUBLISHED,
            "puct-large-load-proceedings",
            RightsStatus.REVIEW_REQUIRED,
        )
    else:
        # Interchange is a filing system. Preserve unrecognized procedural
        # filings as exactly that instead of guessing a more authoritative
        # document class or dropping the publisher file.
        instrument = InstrumentType.FILING
        weight = (
            AuthorityWeight.INTERPRETIVE
            if government_authored
            else AuthorityWeight.ADVOCACY
        )
    return (
        instrument,
        weight,
        SourceStatus.FILED,
        "puct-large-load-proceedings",
        RightsStatus.REVIEW_REQUIRED,
    )


class PUCTInterchangeDocumentAuthoritySourceProvider(BaseAuthoritySourceProvider):
    title = "PUCT Large-Load Proceedings"
    description = "Fetches a discovered PUCT Interchange project item or attachment."
    supported_prefixes: ClassVar[tuple[str, ...]] = ("puct-project", "puct-order")
    # Interchange contains both agency works and third-party submissions.
    license: ClassVar[str] = "mixed-review-required"

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        candidate = all_kwargs.get("discovery_candidate")
        if candidate is not None:
            return AuthorityRequest(
                canonical_key=canonical_key,
                url=candidate.url,
                extra={"title": candidate.title, **dict(candidate.extra)},
            )
        parts = canonical_key.split(":")
        if len(parts) == 2 and parts[0] == "puct-project" and parts[1].isdigit():
            control = parts[1]
            return AuthorityRequest(
                canonical_key=canonical_key,
                url=(
                    "https://interchange.puc.texas.gov/search/filings/"
                    f"?ControlNumber={control}"
                ),
                extra={
                    "title": f"PUCT Project No. {control}",
                    "control_number": control,
                    "source_identifier": control,
                },
            )
        raise ValueError(
            f"{canonical_key!r} requires its discovery candidate attachment URL"
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        title = request.extra.get("title") or request.canonical_key
        instrument, weight, status, corpus_slug, rights = (
            classify_puct_interchange_document(
                request.canonical_key,
                str(title),
                publisher_document_type=request.extra.get("publisher_document_type"),
                publisher_author_role=request.extra.get("publisher_author_role"),
            )
        )
        source_identifier = request.extra.get("source_identifier") or (
            request.canonical_key.split(":", 1)[1]
        )
        control = request.extra.get("control_number")
        if control is None and request.canonical_key.startswith("puct-project:"):
            control = request.canonical_key.split(":")[1]
        parent_key = request.extra.get("parent_key")
        if parent_key is None and control and ":item:" in request.canonical_key:
            parent_key = f"puct-project:{control}"
        evidence_fields = {
            "control_number": control,
            "item_number": request.extra.get("item_number"),
            "document_id": request.extra.get("document_id"),
            "document_name": request.extra.get("document_name"),
            "archive_member_name": None,
            "title": (
                request.extra.get("publisher_document_type")
                or request.extra.get("title")
            ),
            "publisher_document_type": request.extra.get("publisher_document_type"),
            "publisher_author_role": request.extra.get("publisher_author_role"),
        }
        if any(
            evidence_fields.get(field)
            for field in ("item_number", "document_id", "document_name")
        ):
            publisher_evidence = (
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.LISTING_METADATA,
                    value=json.dumps(
                        evidence_fields,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    locator=request.url,
                ),
            )
        else:
            publisher_evidence = (
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.URL,
                    value=request.url,
                    locator=request.url,
                ),
            )
        relationships = (
            (
                SourceRelationship(
                    target_key=str(parent_key),
                    relationship_type=RelationshipType.FILED_IN,
                    metadata={"review_status": "pending_legal_review"},
                ),
            )
            if parent_key
            else ()
        )
        current_version = parse_optional_bool(
            request.extra.get("current_version"),
            field_name="current_version",
        )
        record_metadata = {
            "rights_basis": (
                "final agency order; government legal edict"
                if rights == RightsStatus.PUBLIC_DOMAIN
                else "mixed-rights proceeding attachment; review required"
            ),
            **{
                key: value
                for key, value in request.extra.items()
                if key
                not in {
                    "title",
                    "source_identifier",
                    "parent_key",
                    "version_label",
                    "issued_date",
                    "filed_date",
                    "effective_from",
                    "current_version",
                }
            },
        }
        shared_record_kwargs = {
            "canonical_key": request.canonical_key,
            "title": str(title),
            "source_identifier": str(source_identifier),
            "publisher": "Public Utility Commission of Texas",
            "jurisdiction": "us-tx",
            "authority_type": "admin-rule",
            "instrument_type": instrument,
            "status": status,
            "authority_weight": weight,
            "corpus_slug": corpus_slug,
            "parent_key": str(parent_key) if parent_key else None,
            "version_label": request.extra.get("version_label"),
            "issued_date": request.extra.get("issued_date"),
            "filed_date": request.extra.get("filed_date"),
            "effective_from": request.extra.get("effective_from"),
            "effective_until": request.extra.get("effective_until"),
            "authority_family": "puct-proceeding",
            "current_version": current_version,
            "rights_status": rights,
            "relationships": relationships,
            "publisher_evidence": publisher_evidence,
        }
        extra_ca_certificates = all_kwargs.get("extra_ca_certificates")
        max_bytes = all_kwargs.get("max_bytes")
        if urlsplit(request.url).path.casefold().endswith(".zip"):
            pdf_rendition_url = request.extra.get("pdf_rendition_url")
            if not isinstance(pdf_rendition_url, str) or not pdf_rendition_url.strip():
                raise ValueError(
                    f"{request.canonical_key}: native filing package lacks its "
                    "publisher PDF rendition"
                )
            self._validate_declared_url(
                pdf_rendition_url,
                label="PDF rendition",
            )
            fetch_kwargs = {
                "extra_ca_certificates": extra_ca_certificates,
            }
            if max_bytes is not None:
                fetch_kwargs["max_bytes"] = int(max_bytes)
            source_content, final_host = safe_fetch_bytes(
                request.url,
                params=request.params,
                **fetch_kwargs,
            )
            if not zipfile.is_zipfile(io.BytesIO(source_content)):
                raise ValueError(
                    f"{request.canonical_key}: publisher .ZIP response is not "
                    "a readable ZIP archive"
                )
            rendition_content, rendition_final_host = safe_fetch_bytes(
                pdf_rendition_url,
                **fetch_kwargs,
            )
            if not rendition_content.startswith(b"%PDF-"):
                raise ValueError(
                    f"{request.canonical_key}: publisher PDF rendition is not PDF"
                )
            package_metadata = {
                **record_metadata,
                "final_source_host": final_host,
                "pdf_rendition_url": pdf_rendition_url,
                "pdf_rendition_content_hash": hashlib.sha256(
                    rendition_content
                ).hexdigest(),
                "pdf_rendition_mime_type": "application/pdf",
                "pdf_rendition_final_host": rendition_final_host,
            }
            try:
                extracted_text = extract_authority_text(
                    rendition_content,
                    "application/pdf",
                )
            except ValueError:
                # Keep the exact ZIP as the hash-bound publisher source and
                # send the publisher's own PDF rendition through the ordinary
                # PDF/OCR ingest pipeline.
                extracted_text = None
                package_metadata["text_extraction_deferred_to_pipeline"] = True
                package_metadata["text_extraction_source_extension"] = "pdf"
            record = AuthoritySourceRecord(
                source_url=request.url,
                content=source_content,
                mime_type="application/zip",
                extracted_text=extracted_text,
                portable_rendition_content=rendition_content,
                portable_rendition_mime_type="application/pdf",
                portable_rendition_filename=PurePosixPath(
                    urlsplit(pdf_rendition_url).path
                ).name,
                metadata=package_metadata,
                **shared_record_kwargs,
            )
            records = [record]
            for member in extract_authority_archive_members(source_content):
                member_key = puct_interchange_key_from_evidence(
                    control_number=control,
                    item_number=request.extra.get("item_number"),
                    document_id=request.extra.get("document_id"),
                    document_name=request.extra.get("document_name"),
                    archive_member_name=member.name,
                    title=request.extra.get("publisher_document_type"),
                    publisher_document_type=request.extra.get(
                        "publisher_document_type"
                    ),
                    publisher_author_role=request.extra.get("publisher_author_role"),
                )
                if member_key is None:
                    raise ValueError(
                        f"{request.canonical_key}: could not derive identity for "
                        f"archive member {member.name!r}"
                    )
                extraction_basis = "native_archive_member"
                try:
                    member_text = extract_authority_text(
                        member.content,
                        member.mime_type,
                    )
                except ValueError:
                    # Some publisher-native PDFs and images are image-only.
                    # Retain their exact bytes as the document and let the
                    # configured PDF/converter pipeline perform OCR.
                    member_text = None
                    extraction_basis = "pipeline_deferred_native_archive_member"
                member_evidence_fields = {
                    **evidence_fields,
                    "archive_member_name": member.name,
                }
                member_record_kwargs = {
                    **shared_record_kwargs,
                    "canonical_key": member_key,
                    "title": f"{title} (native member: {member.name})",
                    "source_identifier": (f"{source_identifier}!/{member.name}"),
                    "publisher_evidence": (
                        AuthorityPublisherEvidence(
                            source=PublisherEvidenceSource.LISTING_METADATA,
                            value=json.dumps(
                                member_evidence_fields,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            locator=request.url,
                        ),
                    ),
                }
                records.append(
                    AuthoritySourceRecord(
                        source_url=request.url,
                        content=member.content,
                        mime_type=member.mime_type,
                        extracted_text=member_text,
                        metadata={
                            **record_metadata,
                            "final_source_host": final_host,
                            "archive_parent_key": request.canonical_key,
                            "archive_member_name": member.name,
                            "publisher_source_filename": member.name,
                            "archive_member_content_hash": hashlib.sha256(
                                member.content
                            ).hexdigest(),
                            "archive_member_mime_type": member.mime_type,
                            "archive_member_size": len(member.content),
                            "text_extraction_basis": extraction_basis,
                            "pdf_rendition_url": pdf_rendition_url,
                            "pdf_rendition_content_hash": hashlib.sha256(
                                rendition_content
                            ).hexdigest(),
                            "pdf_rendition_mime_type": "application/pdf",
                            "pdf_rendition_final_host": rendition_final_host,
                            **(
                                {
                                    "text_extraction_deferred_to_pipeline": True,
                                    "text_extraction_source_extension": (
                                        PurePosixPath(member.name)
                                        .suffix.lstrip(".")
                                        .casefold()
                                    ),
                                }
                                if member_text is None
                                else {}
                            ),
                        },
                        **member_record_kwargs,
                    )
                )
        else:
            record = fetch_and_extract_authority_record(
                url=request.url,
                metadata=record_metadata,
                params=request.params,
                max_bytes=(int(max_bytes) if max_bytes is not None else None),
                extra_ca_certificates=extra_ca_certificates,
                **shared_record_kwargs,
            )
            records = [record]
        return records

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        for evidence in record.publisher_evidence:
            if evidence.source == PublisherEvidenceSource.LISTING_METADATA:
                try:
                    fields = json.loads(evidence.value)
                except json.JSONDecodeError:
                    continue
                if not isinstance(fields, dict):
                    continue
                derived = puct_interchange_key_from_evidence(
                    control_number=fields.get("control_number"),
                    item_number=fields.get("item_number"),
                    document_id=fields.get("document_id"),
                    document_name=fields.get("document_name"),
                    archive_member_name=fields.get("archive_member_name"),
                    title=fields.get("title"),
                    publisher_document_type=fields.get("publisher_document_type"),
                    publisher_author_role=fields.get("publisher_author_role"),
                )
                if derived == canonical_key:
                    return True
            elif evidence.source == PublisherEvidenceSource.URL:
                parsed = urlsplit(evidence.value)
                query = {
                    key.casefold(): values[-1]
                    for key, values in parse_qs(parsed.query).items()
                    if values
                }
                control = query.get("controlnumber") or query.get("control")
                if control and re.fullmatch(r"\d{4,8}", control):
                    if canonical_key == f"puct-project:{control}":
                        return True
        return False
