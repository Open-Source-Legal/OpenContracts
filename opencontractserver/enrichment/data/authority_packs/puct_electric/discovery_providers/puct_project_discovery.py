"""Discover PUCT Interchange project items and individual attachments."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import parse_qsl, urlsplit

from opencontractserver.enrichment.data.authority_packs.puct_electric.publisher_identity import (
    classify_puct_structured_document,
    puct_interchange_key_from_evidence,
)
from opencontractserver.pipeline.base.authority_html import (
    extract_authority_links,
    visible_html_text,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)
from opencontractserver.utils.safe_http import safe_fetch_text

_CONTROL_TEXT_RE = re.compile(
    r"(?:control|project|docket)\s*(?:no\.?|number|#)?\s*(?P<id>\d{4,8})",
    re.I,
)
_ITEM_TEXT_RE = re.compile(r"\bitem\s*(?:no\.?|number|#)?\s*(?P<id>\d+)", re.I)
_TABLE_ROW_RE = re.compile(r"<tr\b[^>]*>(?P<body>.*?)</tr>", re.I | re.S)
_TABLE_CELL_RE = re.compile(r"<td\b[^>]*>(?P<body>.*?)</td>", re.I | re.S)
_DETAIL_FIELD_RE = re.compile(
    r"<p\b[^>]*>\s*<strong\b[^>]*>(?P<label>.*?)</strong>" r"(?P<value>.*?)</p>",
    re.I | re.S,
)
_DOCUMENT_STEM_RE = re.compile(
    r"^(?P<control>\d+)_(?P<item>\d+)_(?P<document_id>[A-Za-z0-9-]+)$"
)
_PUCT_AGENCY_PARTY_RE = re.compile(
    r"^(?:PUBLIC UTILITY COMMISSION|PUC(?:T)?\b|COMMISSIONER\b)",
    re.I,
)
_DISCOVERY_ENVELOPE_SCHEMA = "puct-project-attachments-v1"
_DEFAULT_MAX_DETAIL_PAGES = 250
_MAX_MAX_DETAIL_PAGES = 1000


def _first_attribute(link, *names: str) -> str | None:
    for name in names:
        value = link.attribute(name)
        if value and value.strip():
            return value.strip()
    return None


def _query_values(url: str) -> dict[str, str]:
    return {key.casefold(): value for key, value in parse_qsl(urlsplit(url).query)}


def _first(mapping: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = mapping.get(name.casefold())
        if value:
            return value
    return None


def _clean_html_fragment(value: str) -> str:
    return " ".join(visible_html_text(value).split())


def _iso_filing_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def parse_puct_project_item_pages(
    html: str, *, index_url: str
) -> list[dict[str, str | None]]:
    """Return every filing-item detail URL plus publisher table metadata."""

    default_control = _first(
        _query_values(index_url),
        "ControlNumber",
        "control",
        "project",
    )
    rows: list[dict[str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for row_match in _TABLE_ROW_RE.finditer(html):
        row_html = row_match.group("body")
        detail_link = next(
            (
                link
                for link in extract_authority_links(row_html, base_url=index_url)
                if "/search/documents" in urlsplit(link.url).path.casefold()
            ),
            None,
        )
        if detail_link is None:
            continue
        query = _query_values(detail_link.url)
        control = _first(query, "ControlNumber", "control") or default_control
        item = _first(query, "ItemNumber", "item")
        if not control or not control.isdigit() or not item or not item.isdigit():
            continue
        identity = (control, item)
        if identity in seen:
            continue
        seen.add(identity)
        cells = [
            _clean_html_fragment(match.group("body"))
            for match in _TABLE_CELL_RE.finditer(row_html)
        ]
        rows.append(
            {
                "control_number": control,
                "item_number": item,
                "detail_url": detail_link.url,
                "file_stamp": cells[1] if len(cells) > 1 else None,
                "filing_party": cells[2] if len(cells) > 2 else None,
                "publisher_item_type": cells[3] if len(cells) > 3 else None,
                "filing_description": cells[4] if len(cells) > 4 else None,
            }
        )
    return sorted(rows, key=lambda row: int(str(row["item_number"])))


def parse_puct_project_attachment_page(
    html: str,
    *,
    detail_url: str,
    listing_metadata: dict[str, str | None],
) -> list[DiscoveryCandidate]:
    """Purely parse all publisher attachments for one Interchange filing."""

    query = _query_values(detail_url)
    control = _first(query, "ControlNumber", "control") or str(
        listing_metadata.get("control_number") or ""
    )
    item = _first(query, "ItemNumber", "item") or str(
        listing_metadata.get("item_number") or ""
    )
    if not control.isdigit() or not item.isdigit():
        raise ValueError(f"PUCT detail URL lacks numeric project/item: {detail_url}")

    fields = {
        _clean_html_fragment(match.group("label")).casefold(): _clean_html_fragment(
            match.group("value")
        )
        for match in _DETAIL_FIELD_RE.finditer(html)
    }
    filing_description = (
        fields.get("filing description")
        or listing_metadata.get("filing_description")
        or f"PUCT Project {control}, Item {item}"
    )
    filing_party = (
        fields.get("filing party")
        or listing_metadata.get("filing_party")
        or "Unknown filing party"
    )
    filed_date = _iso_filing_date(
        fields.get("file stamp") or listing_metadata.get("file_stamp")
    )
    government_authored = bool(_PUCT_AGENCY_PARTY_RE.search(str(filing_party)))
    publisher_author_role = "agency" if government_authored else "filing-party"
    publisher_document_type = str(filing_description)

    attachment_links = [
        link
        for link in extract_authority_links(html, base_url=detail_url)
        if "/documents/" in urlsplit(link.url).path.casefold()
        and PurePosixPath(urlsplit(link.url).path).suffix
    ]
    sibling_urls = {
        PurePosixPath(urlsplit(link.url).path).suffix.casefold(): link.url
        for link in attachment_links
    }
    candidates: list[DiscoveryCandidate] = []
    for link in attachment_links:
        filename = PurePosixPath(urlsplit(link.url).path).name
        suffix = PurePosixPath(filename).suffix.casefold()
        stem = PurePosixPath(filename).stem
        identity_match = _DOCUMENT_STEM_RE.fullmatch(stem)
        if (
            identity_match is None
            or identity_match.group("control") != control
            or identity_match.group("item") != item
        ):
            raise ValueError(
                f"PUCT attachment filename does not prove project/item: {filename}"
            )
        document_id = identity_match.group("document_id")
        title_suffix = (
            "native filing package"
            if suffix == ".zip"
            else f"{suffix.lstrip('.').upper()} rendition"
        )
        publisher_title = f"{filing_description} ({title_suffix})"
        key = puct_interchange_key_from_evidence(
            control_number=control,
            item_number=item,
            document_id=document_id,
            document_name=filename,
            title=publisher_document_type,
            publisher_document_type=publisher_document_type,
            publisher_author_role=publisher_author_role,
        )
        if key is None:  # pragma: no cover - numeric fields proved above
            raise ValueError(f"could not derive PUCT identity for {filename}")
        document_kind, _ = classify_puct_structured_document(
            publisher_document_type=publisher_document_type,
            publisher_author_role=publisher_author_role,
        )
        candidates.append(
            DiscoveryCandidate(
                canonical_key=key,
                url=link.url,
                title=publisher_title,
                extra={
                    "control_number": control,
                    "item_number": item,
                    "document_id": document_id,
                    "source_identifier": stem,
                    "parent_key": f"puct-project:{control}",
                    "document_name": filename,
                    "publisher_document_type": publisher_document_type,
                    "publisher_item_type": listing_metadata.get("publisher_item_type"),
                    "publisher_author_role": publisher_author_role,
                    "filing_party": filing_party,
                    "filing_description": filing_description,
                    "filed_date": filed_date,
                    "document_kind": document_kind,
                    "government_authored": government_authored,
                    "attachment_mime_hint": suffix.lstrip("."),
                    "pdf_rendition_url": sibling_urls.get(".pdf"),
                    "native_package_url": sibling_urls.get(".zip"),
                    "display_title": (f"[LEGAL REVIEW REQUIRED] {publisher_title}"),
                },
            )
        )
    return candidates


def parse_puct_project_index(html: str, *, index_url: str) -> list[DiscoveryCandidate]:
    try:
        envelope = json.loads(html)
    except json.JSONDecodeError:
        envelope = None
    if isinstance(envelope, dict) and envelope.get("schema") == (
        _DISCOVERY_ENVELOPE_SCHEMA
    ):
        candidates: list[DiscoveryCandidate] = []
        pages = envelope.get("detail_pages")
        if not isinstance(pages, list):
            raise ValueError("PUCT discovery envelope lacks detail_pages")
        for page in pages:
            if not isinstance(page, dict):
                raise ValueError("PUCT detail page envelope must be a mapping")
            detail_html = page.get("html")
            detail_url = page.get("url")
            metadata = page.get("metadata")
            if (
                not isinstance(detail_html, str)
                or not isinstance(detail_url, str)
                or not isinstance(metadata, dict)
            ):
                raise ValueError("PUCT detail page envelope is malformed")
            candidates.extend(
                parse_puct_project_attachment_page(
                    detail_html,
                    detail_url=detail_url,
                    listing_metadata=metadata,
                )
            )
        return candidates

    # Backward-compatible one-page parsing remains useful for publisher pages
    # that link directly to attachments and for parser fixtures.
    index_query = _query_values(index_url)
    default_control = _first(index_query, "ControlNumber", "control", "project")
    candidates: list[DiscoveryCandidate] = []
    for link in extract_authority_links(html, base_url=index_url):
        query = _query_values(link.url)
        control = _first(query, "ControlNumber", "control", "project") or (
            default_control
        )
        if control is None:
            match = _CONTROL_TEXT_RE.search(link.text)
            control = match.group("id") if match is not None else None
        if control is None or not control.isdigit():
            continue
        item = _first(query, "ItemNumber", "item", "filing")
        if item is None:
            item_match = _ITEM_TEXT_RE.search(link.text)
            item = item_match.group("id") if item_match is not None else None
        document_id = _first(
            query,
            "DocumentId",
            "document",
            "attachment",
            "AttachmentId",
        )
        path = urlsplit(link.url).path
        looks_like_document = bool(
            PurePosixPath(path).suffix
            or re.search(r"(?:document|download|attachment|filing)", path, re.I)
        )
        if item is None and document_id is None and not looks_like_document:
            continue

        title = link.text or PurePosixPath(path).name or f"PUCT Project {control}"
        document_name = PurePosixPath(path).name or None
        publisher_document_type = _first_attribute(
            link,
            "data-document-type",
            "data-document-kind",
            "data-filing-type",
            "data-category",
        )
        publisher_author_role = _first_attribute(
            link,
            "data-author-role",
            "data-publisher-role",
            "data-originator-type",
        )
        document_kind, government_authored = classify_puct_structured_document(
            publisher_document_type=publisher_document_type,
            publisher_author_role=publisher_author_role,
        )
        key = puct_interchange_key_from_evidence(
            control_number=control,
            item_number=item,
            document_id=document_id,
            document_name=document_name,
            title=title,
            publisher_document_type=publisher_document_type,
            publisher_author_role=publisher_author_role,
        )
        if key is None:  # pragma: no cover - fields validated immediately above
            continue
        candidates.append(
            DiscoveryCandidate(
                canonical_key=key,
                url=link.url,
                title=title,
                extra={
                    "control_number": control,
                    "item_number": item,
                    "document_id": document_id,
                    "source_identifier": document_id
                    or (
                        PurePosixPath(path).stem
                        if PurePosixPath(path).suffix
                        else (f"{control}-{item}" if item else control)
                    ),
                    "parent_key": (
                        f"puct-project:{control}"
                        if key != f"puct-project:{control}"
                        else None
                    ),
                    "document_name": document_name,
                    "publisher_document_type": publisher_document_type,
                    "publisher_author_role": publisher_author_role,
                    "document_kind": document_kind,
                    "government_authored": government_authored,
                },
            )
        )
    return candidates


class PUCTProjectDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "PUCT Interchange Project Discovery"
    description = "Discovers PUCT project items and each attached document."
    # The listing contains mixed-rights documents; discovery only records links
    # and the fetch/bootstrap rail enforces each record's rights disposition.
    license = "mixed-review-required"
    link_only_discovery = True

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        extra_ca_certificates = all_kwargs.get("extra_ca_certificates")
        listing_html, final_host = safe_fetch_text(
            index_url,
            extra_ca_certificates=extra_ca_certificates,
        )
        item_pages = parse_puct_project_item_pages(
            listing_html,
            index_url=index_url,
        )
        max_detail_pages = int(
            all_kwargs.get("max_detail_pages", _DEFAULT_MAX_DETAIL_PAGES)
        )
        if not 1 <= max_detail_pages <= _MAX_MAX_DETAIL_PAGES:
            raise ValueError(
                f"max_detail_pages must be between 1 and {_MAX_MAX_DETAIL_PAGES}"
            )
        if len(item_pages) > max_detail_pages:
            raise ValueError(
                "PUCT project listing exceeds max_detail_pages: "
                f"{len(item_pages)} > {max_detail_pages}"
            )
        detail_pages = []
        for metadata in item_pages:
            detail_url = str(metadata["detail_url"])
            detail_html, detail_host = safe_fetch_text(
                detail_url,
                extra_ca_certificates=extra_ca_certificates,
            )
            if detail_host.casefold() != final_host.casefold():
                raise ValueError(
                    "PUCT detail page redirected outside the project listing host"
                )
            detail_pages.append(
                {
                    "url": detail_url,
                    "metadata": metadata,
                    "html": detail_html,
                }
            )
        return (
            json.dumps(
                {
                    "schema": _DISCOVERY_ENVELOPE_SCHEMA,
                    "detail_pages": detail_pages,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            final_host,
        )

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_puct_project_index(html, index_url=index_url)
