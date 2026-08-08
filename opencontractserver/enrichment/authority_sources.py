"""Shared source-record contract and deterministic attachment extraction.

Authority packs all travel through the existing authority-provider ->
``bootstrap_authority_corpus`` -> document-versioning path.  This module gives
those providers one rich, validated interchange record without introducing a
second ingestion rail.  ``AuthoritySourceRecord`` deliberately exposes the
legacy ``AuthoritySection`` attributes (``key``, ``heading`` and ``text``), so
the existing verification gate and bootstrapper can consume either shape.
"""

from __future__ import annotations

import hashlib
import io
import mimetypes
import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from opencontractserver.enrichment.constants import ALL_AUTHORITY_TYPES
from opencontractserver.utils.safe_http import safe_fetch_bytes

_CANONICAL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*:.+$")
_CORPUS_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")
_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_MIME_ALIASES = {
    "application/txt": "text/plain",
    "application/x-pdf": "application/pdf",
    "application/xml": "text/xml",
}
_EXTRACTABLE_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/html",
    "application/xhtml+xml",
    "text/xml",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png",
}
_DEFERRED_PIPELINE_MIME_TYPES = {
    "application/msword",
    "application/vnd.ms-excel",
}
# Office Open XML files are ZIP containers.  These budgets are deliberately
# enforced against the archive directory before any member is decompressed and
# again while selected XML members are streamed.  A small compressed attachment
# therefore cannot expand without bound during DOCX/XLSX extraction.
AUTHORITY_ZIP_MAX_MEMBERS = 2_048
AUTHORITY_ZIP_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
AUTHORITY_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
AUTHORITY_ZIP_MAX_COMPRESSION_RATIO = 200.0
_ZIP_READ_CHUNK_BYTES = 64 * 1024
_OLE_COMPOUND_DOCUMENT_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class AuthorityWeight(StrEnum):
    CONTROLLING = "CONTROLLING"
    IMPLEMENTING = "IMPLEMENTING"
    INTERPRETIVE = "INTERPRETIVE"
    EVIDENTIARY = "EVIDENTIARY"
    ADVOCACY = "ADVOCACY"
    INFORMAL = "INFORMAL"


class InstrumentType(StrEnum):
    STATUTE = "STATUTE"
    REGULATION = "REGULATION"
    FINAL_ORDER = "FINAL_ORDER"
    TARIFF = "TARIFF"
    PROTOCOL = "PROTOCOL"
    PLANNING_GUIDE = "PLANNING_GUIDE"
    OPERATING_GUIDE = "OPERATING_GUIDE"
    REVISION_REQUEST = "REVISION_REQUEST"
    MARKET_NOTICE = "MARKET_NOTICE"
    FORM = "FORM"
    ATTESTATION = "ATTESTATION"
    FAQ = "FAQ"
    STAFF_MEMO = "STAFF_MEMO"
    TESTIMONY = "TESTIMONY"
    COMMENT = "COMMENT"
    TRANSCRIPT = "TRANSCRIPT"
    FILING = "FILING"
    MUNICIPAL_ORDINANCE = "MUNICIPAL_ORDINANCE"
    TECHNICAL_GUIDE = "TECHNICAL_GUIDE"


class SourceStatus(StrEnum):
    CURRENT = "CURRENT"
    EFFECTIVE = "EFFECTIVE"
    ENACTED = "ENACTED"
    SIGNED = "SIGNED"
    ADOPTED = "ADOPTED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    FILED = "FILED"
    PENDING = "PENDING"
    PROPOSED = "PROPOSED"
    DRAFT = "DRAFT"
    WITHDRAWN = "WITHDRAWN"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class RelationshipType(StrEnum):
    CITES = "CITES"
    AMENDS = "AMENDS"
    SUPERSEDES = "SUPERSEDES"
    SUPERSEDED_BY = "SUPERSEDED_BY"
    ADOPTS = "ADOPTS"
    PARTIALLY_ADOPTS = "PARTIALLY_ADOPTS"
    REJECTS = "REJECTS"
    IMPLEMENTS = "IMPLEMENTS"
    INTERPRETS = "INTERPRETS"
    FILED_IN = "FILED_IN"
    RESPONDS_TO = "RESPONDS_TO"
    REVISES = "REVISES"
    INCORPORATES = "INCORPORATES"
    REQUIRES_FORM = "REQUIRES_FORM"
    EXCEPTION_TO = "EXCEPTION_TO"
    EFFECTIVE_VERSION_OF = "EFFECTIVE_VERSION_OF"


class RightsStatus(StrEnum):
    """Per-record rights disposition.

    ``REVIEW_REQUIRED`` is intentionally the default.  A public web page is not,
    by itself, evidence that its attached work is public domain.
    """

    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    LICENSED = "LICENSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    LINK_ONLY = "LINK_ONLY"


class PublisherEvidenceSource(StrEnum):
    """Publisher-owned signal from which a provider verified a record key."""

    SOURCE_IDENTIFIER = "SOURCE_IDENTIFIER"
    TITLE = "TITLE"
    URL = "URL"
    PARSED_CONTENT = "PARSED_CONTENT"
    LISTING_METADATA = "LISTING_METADATA"


def _enum_value(value: str | StrEnum, enum_type: type[StrEnum], field_name: str) -> str:
    try:
        return enum_type(value).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(
            f"{field_name} must be one of: {allowed}; got {value!r}"
        ) from exc


def parse_authority_date(value: date | datetime | str | None) -> date | None:
    """Normalize an authority date without guessing ambiguous local formats."""

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(
            f"authority date must be ISO text or date, got {type(value).__name__}"
        )
    cleaned = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"authority date {value!r} is not YYYY-MM-DD or the explicit MM/DD/YYYY "
        "format used by the source"
    )


def parse_optional_bool(value: object, *, field_name: str) -> bool | None:
    """Accept only a real JSON boolean or null at provider boundaries."""

    if value is None:
        return None
    if type(value) is not bool:
        raise ValueError(f"{field_name} must be true, false, or null; got {value!r}")
    return value


_STATUS_ALIASES = {
    "IN EFFECT": SourceStatus.EFFECTIVE,
    "IN_FORCE": SourceStatus.EFFECTIVE,
    "IN FORCE": SourceStatus.EFFECTIVE,
    "FINAL": SourceStatus.ADOPTED,
    "ACTIVE": SourceStatus.CURRENT,
    "RETIRED": SourceStatus.SUPERSEDED,
}


def normalize_source_status(value: str | SourceStatus) -> str:
    """Map a publisher status to the controlled vocabulary or fail explicitly."""

    if isinstance(value, SourceStatus):
        return value.value
    cleaned = str(value).strip().upper().replace("-", "_")
    cleaned = _STATUS_ALIASES.get(cleaned, cleaned)
    return _enum_value(cleaned, SourceStatus, "status")


def host_matches_declared_sources(
    host: str | None,
    declared_hosts: Iterable[str],
) -> bool:
    """Return whether *host* belongs to one provider's declared host family.

    Pack declarations use registrable publisher hosts (for example
    ``ercot.com``) while real URLs commonly use a publisher-owned subdomain
    (``www.ercot.com``).  Matching is exact-or-dot-suffix and never a bare
    string suffix, so ``notercot.com`` cannot satisfy ``ercot.com``.
    """

    normalized = (host or "").strip().rstrip(".").casefold()
    if not normalized:
        return False
    for declared in declared_hosts:
        allowed = str(declared).strip().rstrip(".").casefold()
        if allowed and (normalized == allowed or normalized.endswith(f".{allowed}")):
            return True
    return False


@dataclass(frozen=True)
class SourceRelationship:
    """One typed edge from the containing record to ``target_key``."""

    target_key: str
    relationship_type: str | RelationshipType
    verified: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # ``verified`` controls admission to the production governance graph.
        # Refuse truthy strings/integers at the shared contract boundary so a
        # quoted YAML value such as ``"false"`` cannot become verified through
        # Python's ``bool(...)`` coercion.
        if type(self.verified) is not bool:
            raise ValueError(f"verified must be true or false; got {self.verified!r}")
        target = self.target_key.strip()
        if not _CANONICAL_KEY_RE.fullmatch(target):
            raise ValueError(f"invalid relationship target canonical key {target!r}")
        object.__setattr__(self, "target_key", target)
        object.__setattr__(
            self,
            "relationship_type",
            _enum_value(self.relationship_type, RelationshipType, "relationship_type"),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def as_dict(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "relationship_type": str(self.relationship_type),
            "verified": self.verified,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AuthorityPublisherEvidence:
    """One raw, publisher-originated identity signal.

    ``AuthoritySourceRecord.canonical_key`` is application-owned and therefore
    cannot verify itself.  Rich providers attach the raw publisher value they
    parsed (an identifier, title, URL component, or body/listing field), and
    implement ``BaseAuthoritySourceProvider.verify_publisher_evidence`` to
    derive the canonical identity from this value.  The shared gate invokes
    that provider-specific verifier and fails closed when evidence is absent.
    """

    source: str | PublisherEvidenceSource
    value: str
    locator: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source",
            _enum_value(
                self.source, PublisherEvidenceSource, "publisher evidence source"
            ),
        )
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("publisher evidence value must be a non-empty string")
        object.__setattr__(self, "value", self.value.strip())
        if self.locator is not None:
            if not isinstance(self.locator, str) or not self.locator.strip():
                raise ValueError(
                    "publisher evidence locator must be a non-empty string when set"
                )
            object.__setattr__(self, "locator", self.locator.strip())

    def as_dict(self) -> dict[str, str]:
        result = {"source": str(self.source), "value": self.value}
        if self.locator is not None:
            result["locator"] = self.locator
        return result


@dataclass(frozen=True)
class AuthorityArchiveMember:
    """One safely bounded publisher file read from a ZIP attachment."""

    name: str
    content: bytes
    mime_type: str


@dataclass(frozen=True)
class AuthoritySourceRecord:
    """Normalized provider output consumed by the existing authority bootstrap."""

    canonical_key: str
    title: str
    source_url: str
    source_identifier: str
    publisher: str
    jurisdiction: str
    authority_type: str
    instrument_type: str | InstrumentType
    issued_date: date | datetime | str | None
    effective_from: date | datetime | str | None
    effective_until: date | datetime | str | None
    status: str | SourceStatus
    authority_weight: str | AuthorityWeight
    parent_key: str | None
    version_label: str | None
    content: bytes
    mime_type: str
    corpus_slug: str
    metadata: Mapping[str, object] = field(default_factory=dict)
    relationships: tuple[SourceRelationship, ...] = ()
    authority_family: str | None = None
    filed_date: date | datetime | str | None = None
    published_date: date | datetime | str | None = None
    retrieved_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    current_version: bool | None = None
    rights_status: str | RightsStatus = RightsStatus.REVIEW_REQUIRED
    extracted_text: str | None = None
    content_hash: str | None = None
    publisher_evidence: tuple[AuthorityPublisherEvidence, ...] = ()
    portable_rendition_content: bytes | None = None
    portable_rendition_mime_type: str | None = None
    portable_rendition_filename: str | None = None

    def __post_init__(self) -> None:
        key = self.canonical_key.strip()
        if not _CANONICAL_KEY_RE.fullmatch(key):
            raise ValueError(f"invalid canonical_key {key!r}")
        object.__setattr__(self, "canonical_key", key)

        for field_name in (
            "title",
            "source_url",
            "source_identifier",
            "publisher",
            "jurisdiction",
            "authority_type",
            "corpus_slug",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())

        if self.authority_type not in ALL_AUTHORITY_TYPES:
            raise ValueError(
                f"authority_type {self.authority_type!r} is not in the shared "
                "ALL_AUTHORITY_TYPES vocabulary"
            )
        if not _CORPUS_SLUG_RE.fullmatch(self.corpus_slug):
            raise ValueError(
                "corpus_slug must be 1-128 lowercase letters/digits/hyphens, "
                "with no leading or trailing hyphen"
            )
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("content must be non-empty bytes")
        object.__setattr__(
            self,
            "current_version",
            parse_optional_bool(
                self.current_version,
                field_name="current_version",
            ),
        )

        object.__setattr__(
            self,
            "instrument_type",
            _enum_value(self.instrument_type, InstrumentType, "instrument_type"),
        )
        object.__setattr__(
            self,
            "authority_weight",
            _enum_value(self.authority_weight, AuthorityWeight, "authority_weight"),
        )
        object.__setattr__(self, "status", normalize_source_status(self.status))
        object.__setattr__(
            self,
            "rights_status",
            _enum_value(self.rights_status, RightsStatus, "rights_status"),
        )

        for field_name in (
            "issued_date",
            "effective_from",
            "effective_until",
            "filed_date",
            "published_date",
        ):
            object.__setattr__(
                self, field_name, parse_authority_date(getattr(self, field_name))
            )
        effective_from = parse_authority_date(self.effective_from)
        effective_until = parse_authority_date(self.effective_until)
        if (
            effective_from is not None
            and effective_until is not None
            and effective_until < effective_from
        ):
            raise ValueError("effective_until cannot precede effective_from")
        if self.parent_key is not None:
            parent = self.parent_key.strip()
            if not _CANONICAL_KEY_RE.fullmatch(parent):
                raise ValueError(f"invalid parent_key {parent!r}")
            object.__setattr__(self, "parent_key", parent)

        normalized_mime = normalize_mime_type(self.mime_type)
        object.__setattr__(self, "mime_type", normalized_mime)
        digest = hashlib.sha256(self.content).hexdigest()
        if self.content_hash is not None and self.content_hash.lower() != digest:
            raise ValueError(
                f"content_hash mismatch for {self.canonical_key}: "
                f"declared {self.content_hash}, computed {digest}"
            )
        object.__setattr__(self, "content_hash", digest)
        rendition_fields = (
            self.portable_rendition_content,
            self.portable_rendition_mime_type,
            self.portable_rendition_filename,
        )
        if any(value is not None for value in rendition_fields):
            if not all(value is not None for value in rendition_fields):
                raise ValueError(
                    "portable rendition content, MIME type, and filename must "
                    "be supplied together"
                )
            if (
                not isinstance(self.portable_rendition_content, bytes)
                or not self.portable_rendition_content
            ):
                raise ValueError("portable_rendition_content must be non-empty bytes")
            rendition_mime = normalize_mime_type(str(self.portable_rendition_mime_type))
            object.__setattr__(
                self,
                "portable_rendition_mime_type",
                rendition_mime,
            )
            rendition_filename = str(self.portable_rendition_filename)
            if (
                not rendition_filename
                or "\x00" in rendition_filename
                or "\\" in rendition_filename
                or rendition_filename in {".", ".."}
                or PurePosixPath(rendition_filename).name != rendition_filename
            ):
                raise ValueError(
                    "portable_rendition_filename must be one safe filename segment"
                )
            object.__setattr__(
                self,
                "portable_rendition_filename",
                rendition_filename,
            )
        if not isinstance(self.retrieved_at, datetime):
            raise ValueError("retrieved_at must be a datetime")
        if self.retrieved_at.tzinfo is None:
            object.__setattr__(
                self, "retrieved_at", self.retrieved_at.replace(tzinfo=timezone.utc)
            )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        publisher_evidence = tuple(self.publisher_evidence)
        if not all(
            isinstance(evidence, AuthorityPublisherEvidence)
            for evidence in publisher_evidence
        ):
            raise ValueError(
                "publisher_evidence must contain AuthorityPublisherEvidence instances"
            )
        object.__setattr__(self, "publisher_evidence", publisher_evidence)
        relationships = tuple(self.relationships)
        if not all(
            isinstance(relationship, SourceRelationship)
            for relationship in relationships
        ):
            raise ValueError("relationships must contain SourceRelationship instances")
        object.__setattr__(self, "relationships", relationships)

    # Compatibility surface for AuthorityGateService and the existing bootstrap.
    @property
    def key(self) -> str:
        return self.canonical_key

    @property
    def heading(self) -> str:
        return self.title

    @property
    def text(self) -> str:
        return self.extracted_text or extract_authority_text(
            self.content, self.mime_type
        )

    @property
    def source_mime_type(self) -> str:
        return self.mime_type

    def as_document_metadata(self) -> dict[str, object]:
        """Return JSON-safe shared fields plus provider-specific metadata."""

        relationship_fields = {
            RelationshipType.SUPERSEDES.value: "supersedes_key",
            RelationshipType.SUPERSEDED_BY.value: "superseded_by_key",
            RelationshipType.ADOPTS.value: "adopts_key",
            RelationshipType.REJECTS.value: "rejects_key",
            RelationshipType.AMENDS.value: "amends_key",
        }
        relationship_shortcuts: dict[str, str] = {}
        for relationship in self.relationships:
            field_name = relationship_fields.get(str(relationship.relationship_type))
            if field_name is not None and field_name not in relationship_shortcuts:
                relationship_shortcuts[field_name] = relationship.target_key

        common: dict[str, object] = {
            "authority_family": self.authority_family
            or self.canonical_key.split(":", 1)[0],
            "instrument_type": str(self.instrument_type),
            "publisher": self.publisher,
            "jurisdiction": self.jurisdiction,
            "authority_type": self.authority_type,
            "canonical_key": self.canonical_key,
            "source_identifier": self.source_identifier,
            "source_url": self.source_url,
            "parent_proceeding": self.parent_key,
            "filed_date": _date_text(self.filed_date),
            "issued_date": _date_text(self.issued_date),
            "published_date": _date_text(self.published_date),
            "effective_from": _date_text(self.effective_from),
            "effective_until": _date_text(self.effective_until),
            # A current authority without a stated effective date must carry
            # an explicit review state.  This is intentionally derived at the
            # shared record boundary so every pack, including future packs,
            # fails closed without provider-specific bookkeeping.
            "effective_date_review_status": (
                "UNKNOWN_NEEDS_REVIEW"
                if self.current_version is not False and self.effective_from is None
                else None
            ),
            "status": str(self.status),
            "authority_weight": str(self.authority_weight),
            "current_version": self.current_version,
            "version_label": self.version_label,
            "retrieved_at": self.retrieved_at.isoformat(),
            "content_hash": self.content_hash,
            "source_mime_type": self.mime_type,
            "rights_status": str(self.rights_status),
            "publisher_evidence": [
                evidence.as_dict() for evidence in self.publisher_evidence
            ],
            "relationships": [rel.as_dict() for rel in self.relationships],
            **relationship_shortcuts,
        }
        return {
            **dict(self.metadata),
            **{key: value for key, value in common.items() if value is not None},
        }


def _date_text(value: date | datetime | str | None) -> str | None:
    parsed = parse_authority_date(value)
    return parsed.isoformat() if parsed is not None else None


class _VisibleHTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1
        elif not self._hidden_depth and tag.lower() in {
            "p",
            "br",
            "div",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "section",
            "article",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._hidden_depth = max(0, self._hidden_depth - 1)
        elif not self._hidden_depth and tag.lower() in {
            "p",
            "div",
            "li",
            "tr",
            "section",
            "article",
        }:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def normalize_mime_type(value: str) -> str:
    mime = (value or "").split(";", 1)[0].strip().lower()
    mime = _MIME_ALIASES.get(mime, mime)
    if not mime or "/" not in mime:
        raise ValueError(f"invalid MIME type {value!r}")
    return mime


def infer_authority_mime_type(content: bytes, source_url: str = "") -> str:
    """Infer only formats the shared extractor can identify confidently."""

    sample = content[:512].lstrip()
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(_OLE_COMPOUND_DOCUMENT_MAGIC):
        suffix = PurePosixPath(source_url).suffix.casefold()
        if suffix in {".xls", ".xlt", ".xlw"}:
            return "application/vnd.ms-excel"
        if suffix in {".doc", ".dot"}:
            return "application/msword"
        return "application/x-ole-storage"
    if content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(_validated_zip_members(archive))
        except zipfile.BadZipFile as exc:
            raise ValueError("source begins like ZIP but is malformed") from exc
        if "word/document.xml" in names:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "ppt/presentation.xml" in names:
            return (
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            )
        if "xl/workbook.xml" in names:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        raise ValueError("unsupported ZIP attachment (expected DOCX or XLSX)")
    lowered = sample.lower()
    if lowered.startswith(
        (
            b"<!doctype html",
            b"<html",
            b"<head",
            b"<body",
            b"<p",
            b"<div",
            b"<h1",
            b"<h2",
            b"<table",
        )
    ):
        return "text/html"
    if lowered.startswith(b"<?xml") or lowered.startswith(b"<"):
        return "text/xml"
    guessed, _ = mimetypes.guess_type(PurePosixPath(source_url).name)
    if guessed:
        normalized_guess = normalize_mime_type(guessed)
        if normalized_guess in _EXTRACTABLE_MIME_TYPES:
            return normalized_guess
        raise ValueError(
            f"unsupported authority attachment MIME type {normalized_guess!r}"
        )
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "could not infer a supported MIME type for binary source"
        ) from exc
    return "text/plain"


def _clean_extracted_text(value: str) -> str:
    lines = [
        _WHITESPACE_RE.sub(" ", line).strip()
        for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    collapsed: list[str] = []
    for line in lines:
        if line or (collapsed and collapsed[-1]):
            collapsed.append(line)
    return "\n".join(collapsed).strip()


def _validated_zip_members(
    archive: zipfile.ZipFile,
) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > AUTHORITY_ZIP_MAX_MEMBERS:
        raise ValueError(
            "Office Open XML ZIP member-count budget exceeded: "
            f"{len(infos)} > {AUTHORITY_ZIP_MAX_MEMBERS}"
        )
    total_size = 0
    members: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        if info.filename in members:
            raise ValueError(f"ZIP contains duplicate member {info.filename!r}")
        if info.flag_bits & 0x1:
            raise ValueError(
                f"Office Open XML ZIP member {info.filename!r} is encrypted"
            )
        if info.file_size < 0:
            raise ValueError(
                f"Office Open XML ZIP member {info.filename!r} has invalid size"
            )
        if info.file_size > AUTHORITY_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise ValueError(
                "Office Open XML ZIP per-member uncompressed-byte budget "
                f"exceeded by {info.filename!r}: {info.file_size} > "
                f"{AUTHORITY_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES}"
            )
        if info.file_size:
            compression_ratio = info.file_size / max(info.compress_size, 1)
            if compression_ratio > AUTHORITY_ZIP_MAX_COMPRESSION_RATIO:
                raise ValueError(
                    "Office Open XML ZIP compression-ratio budget exceeded by "
                    f"{info.filename!r}: {compression_ratio:.1f} > "
                    f"{AUTHORITY_ZIP_MAX_COMPRESSION_RATIO:.1f}"
                )
        total_size += info.file_size
        if total_size > AUTHORITY_ZIP_MAX_UNCOMPRESSED_BYTES:
            raise ValueError(
                "Office Open XML ZIP uncompressed-byte budget exceeded: "
                f"{total_size} > {AUTHORITY_ZIP_MAX_UNCOMPRESSED_BYTES}"
            )
        members[info.filename] = info
    return members


def _read_zip_member_bounded(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    remaining_budget: int,
) -> bytes:
    parts: list[bytes] = []
    observed = 0
    with archive.open(info) as member:
        while True:
            chunk = member.read(
                min(_ZIP_READ_CHUNK_BYTES, remaining_budget - observed + 1)
            )
            if not chunk:
                break
            observed += len(chunk)
            if observed > remaining_budget:
                raise ValueError(
                    "Office Open XML ZIP uncompressed-byte budget exceeded "
                    f"while reading {info.filename!r}"
                )
            parts.append(chunk)
    return b"".join(parts)


def extract_authority_archive_members(
    content: bytes,
    *,
    allowed_mime_types: Iterable[str] | None = None,
) -> tuple[AuthorityArchiveMember, ...]:
    """Read every safe, supported file from a publisher ZIP attachment.

    This deliberately returns in-memory member bytes instead of extracting to
    disk. The shared ZIP member-count, size, and compression-ratio budgets
    therefore apply to ordinary publisher archives as well as OOXML files.
    Paths must be canonical relative POSIX paths; traversal, absolute paths,
    backslashes, duplicates, and nested ZIPs fail closed.
    """

    allowed = (
        frozenset(normalize_mime_type(value) for value in allowed_mime_types)
        if allowed_mime_types is not None
        else frozenset((*_EXTRACTABLE_MIME_TYPES, *_DEFERRED_PIPELINE_MIME_TYPES))
    )
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = _validated_zip_members(archive)
            extracted: list[AuthorityArchiveMember] = []
            remaining_budget = AUTHORITY_ZIP_MAX_UNCOMPRESSED_BYTES
            for raw_name, info in sorted(members.items()):
                if info.is_dir():
                    continue
                if "\\" in raw_name:
                    raise ValueError(
                        f"ZIP member uses a non-canonical separator: {raw_name!r}"
                    )
                path = PurePosixPath(raw_name)
                if (
                    path.is_absolute()
                    or not path.parts
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or str(path) != raw_name
                ):
                    raise ValueError(f"unsafe ZIP member path {raw_name!r}")
                member_content = _read_zip_member_bounded(
                    archive,
                    info,
                    remaining_budget=remaining_budget,
                )
                remaining_budget -= len(member_content)
                if not member_content:
                    raise ValueError(f"ZIP member {raw_name!r} is empty")
                try:
                    mime_type = infer_authority_mime_type(
                        member_content,
                        raw_name,
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"unsupported ZIP member {raw_name!r}: {exc}"
                    ) from exc
                if mime_type not in allowed:
                    raise ValueError(
                        f"ZIP member {raw_name!r} has disallowed MIME type "
                        f"{mime_type!r}"
                    )
                extracted.append(
                    AuthorityArchiveMember(
                        name=raw_name,
                        content=member_content,
                        mime_type=mime_type,
                    )
                )
    except zipfile.BadZipFile as exc:
        raise ValueError("malformed publisher ZIP attachment") from exc
    if not extracted:
        raise ValueError("publisher ZIP attachment contains no files")
    return tuple(extracted)


def _extract_zip_xml(content: bytes, member_names: list[str]) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = _validated_zip_members(archive)
            parts = []
            extracted_bytes = 0
            for name in member_names:
                info = members.get(name)
                if info is None:
                    continue
                member_bytes = _read_zip_member_bounded(
                    archive,
                    info,
                    remaining_budget=min(
                        AUTHORITY_ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES,
                        AUTHORITY_ZIP_MAX_UNCOMPRESSED_BYTES - extracted_bytes,
                    ),
                )
                extracted_bytes += len(member_bytes)
                root = ET.fromstring(member_bytes)
                parts.append(" ".join(text for text in root.itertext() if text))
    except (zipfile.BadZipFile, ET.ParseError) as exc:
        raise ValueError("malformed Office Open XML attachment") from exc
    return "\n".join(parts)


def extract_authority_text(content: bytes, mime_type: str) -> str:
    """Extract deterministic searchable text or raise on an unsupported format."""

    mime = normalize_mime_type(mime_type)
    if mime in {"text/plain", "text/markdown"}:
        text = content.decode("utf-8", errors="replace")
    elif mime in {"text/html", "application/xhtml+xml"}:
        parser = _VisibleHTMLTextParser()
        parser.feed(content.decode("utf-8", errors="replace"))
        text = "".join(parser.parts)
    elif mime in {"text/xml", "application/xml"}:
        try:
            text = " ".join(ET.fromstring(content).itertext())
        except ET.ParseError as exc:
            raise ValueError("malformed XML authority source") from exc
    elif mime == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError("could not parse PDF authority source") from exc
    elif mime == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        text = _extract_zip_xml(content, ["word/document.xml"])
    elif mime == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                all_members = _validated_zip_members(archive)
                members = [
                    name
                    for name in all_members
                    if (
                        name.startswith("ppt/slides/slide")
                        or name.startswith("ppt/notesSlides/notesSlide")
                    )
                    and name.endswith(".xml")
                ]
            text = _extract_zip_xml(content, sorted(members))
        except zipfile.BadZipFile as exc:
            raise ValueError("malformed PPTX authority source") from exc
    elif mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                all_members = _validated_zip_members(archive)
                members = [
                    name
                    for name in all_members
                    if name == "xl/sharedStrings.xml"
                    or (name.startswith("xl/worksheets/") and name.endswith(".xml"))
                ]
            text = _extract_zip_xml(content, sorted(members))
        except zipfile.BadZipFile as exc:
            raise ValueError("malformed XLSX authority source") from exc
    elif mime == "image/png":
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise ValueError(
                "PNG authority extraction requires Pillow and pytesseract"
            ) from exc
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > 50_000_000:
                    raise ValueError(
                        "PNG authority source exceeds the 50-megapixel OCR cap"
                    )
                image.load()
                text = pytesseract.image_to_string(image)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("could not OCR PNG authority source") from exc
    else:
        raise ValueError(f"unsupported authority source MIME type {mime!r}")

    cleaned = _clean_extracted_text(text)
    if not cleaned:
        raise ValueError(f"authority source {mime!r} contained no extractable text")
    return cleaned


def fetch_and_extract_authority_record(
    *,
    url: str,
    canonical_key: str,
    title: str,
    source_identifier: str,
    publisher: str,
    jurisdiction: str,
    authority_type: str,
    instrument_type: str | InstrumentType,
    status: str | SourceStatus,
    authority_weight: str | AuthorityWeight,
    corpus_slug: str,
    parent_key: str | None = None,
    version_label: str | None = None,
    issued_date: date | datetime | str | None = None,
    effective_from: date | datetime | str | None = None,
    effective_until: date | datetime | str | None = None,
    authority_family: str | None = None,
    filed_date: date | datetime | str | None = None,
    published_date: date | datetime | str | None = None,
    current_version: bool | None = None,
    rights_status: str | RightsStatus = RightsStatus.REVIEW_REQUIRED,
    metadata: Mapping[str, object] | None = None,
    relationships: tuple[SourceRelationship, ...] = (),
    publisher_evidence: tuple[AuthorityPublisherEvidence, ...] = (),
    mime_type: str | None = None,
    max_bytes: int | None = None,
    params: dict | None = None,
    headers: dict | None = None,
    extra_ca_certificates: tuple[str, ...] | None = None,
) -> AuthoritySourceRecord:
    """Fetch through the shared SSRF-safe boundary and build a rich record."""

    fetch_kwargs: dict[str, Any] = {
        "params": params,
        "headers": headers,
        "extra_ca_certificates": extra_ca_certificates,
    }
    if max_bytes is not None:
        fetch_kwargs["max_bytes"] = max_bytes
    content, final_host = safe_fetch_bytes(url, **fetch_kwargs)
    detected_mime = (
        normalize_mime_type(mime_type)
        if mime_type
        else (infer_authority_mime_type(content, url))
    )
    merged_metadata = dict(metadata or {})
    try:
        extracted = extract_authority_text(content, detected_mime)
    except ValueError:
        source_extension = PurePosixPath(urlsplit(url).path).suffix.lstrip(".").lower()
        try:
            from opencontractserver.pipeline.file_converters.gotenberg_converter import (
                GOTENBERG_SUPPORTED_EXTENSIONS,
            )

            converter_supported = source_extension in {
                extension.casefold() for extension in GOTENBERG_SUPPORTED_EXTENSIONS
            }
        except ImportError:
            converter_supported = False
        pipeline_can_defer = detected_mime in {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        if not (converter_supported or pipeline_can_defer):
            raise
        extracted = None
        merged_metadata["text_extraction_deferred_to_pipeline"] = True
        merged_metadata["text_extraction_source_extension"] = source_extension
    return AuthoritySourceRecord(
        canonical_key=canonical_key,
        title=title,
        source_url=url,
        source_identifier=source_identifier,
        publisher=publisher,
        jurisdiction=jurisdiction,
        authority_type=authority_type,
        instrument_type=instrument_type,
        issued_date=issued_date,
        effective_from=effective_from,
        effective_until=effective_until,
        status=status,
        authority_weight=authority_weight,
        parent_key=parent_key,
        version_label=version_label,
        content=content,
        mime_type=detected_mime,
        corpus_slug=corpus_slug,
        metadata={**merged_metadata, "final_source_host": final_host},
        relationships=relationships,
        publisher_evidence=publisher_evidence,
        authority_family=authority_family,
        filed_date=filed_date,
        published_date=published_date,
        current_version=current_version,
        rights_status=rights_status,
        extracted_text=extracted,
    )
