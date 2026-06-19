"""CFR authority source provider (eCFR Versioner API).

Fetches Code of Federal Regulations (CFR) section text from the eCFR Versioner
full-text XML API.  Snapshots are immutable past-date responses that cache well.

Canonical key grammar: ``cfr-{title}:{part}.{section}``
Examples: ``cfr-40:261.4``, ``cfr-17:240.10b-5``.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import ClassVar

import requests

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.enrichment.constants import _CFR_PREFIX_RE
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Known-good snapshot date.  Use an immutable past date so responses are
# stable and cache-friendly.  Update this constant when a newer snapshot
# is needed.
_SNAPSHOT_DATE = "2024-01-01"

# Canonical-key prefix pattern for the can_handle override is imported from
# enrichment.constants (single source of truth shared with classify_prefix).

# eCFR Versioner full-text XML endpoint template.
_ECFR_FULL_URL_TEMPLATE = (
    "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml"
)

# Human-readable eCFR URL template.
_ECFR_HUMAN_URL_TEMPLATE = (
    "https://www.ecfr.gov/current/title-{title}/section-{section}"
)

# HTTP User-Agent header.
_USER_AGENT = (
    "OpenContracts-authority-provider/1.0 "
    "(https://github.com/Open-Source-Legal/OpenContracts; "
    "contact: opensource@opencontracts.dev)"
)

# Regex patterns for validating citation components before URL construction.
# CFR title: digits only (e.g. '40', '17').
_CFR_TITLE_RE = re.compile(r"^\d+$")
# CFR part: digits only (e.g. '261', '240').
_CFR_PART_RE = re.compile(r"^\d+$")
# CFR section: digits, dot, digits/letters/hyphens — e.g. '261.4', '240.10b-5'.
_CFR_SECTION_RE = re.compile(r"^\d+\.[0-9a-z-]+$", re.IGNORECASE)


def _validate_cfr_components(title: str, part: str, section: str) -> None:
    """Raise ValueError if CFR components contain unexpected characters.

    Rejects values that could be injected into URLs or XPath expressions.
    Valid examples: title='40', part='261', section='261.4', section='240.10b-5'.
    """
    if not _CFR_TITLE_RE.match(title):
        raise ValueError(f"Invalid CFR title component: {title!r}")
    if not _CFR_PART_RE.match(part):
        raise ValueError(f"Invalid CFR part component: {part!r}")
    if not _CFR_SECTION_RE.match(section):
        raise ValueError(f"Invalid CFR section component: {section!r}")


def _extract_part(section: str) -> str:
    """Derive CFR part number from a section string.

    The part is the integer prefix before the first '.'.  For example:
      ``"261.4"``   → ``"261"``
      ``"240.10b-5"`` → ``"240"``

    Args:
        section: CFR section string, e.g. ``"261.4"``.

    Returns:
        Part number as a string, e.g. ``"261"``.
    """
    return section.split(".")[0]


def _flatten_element_text(element: ET.Element) -> str:
    """Collect all text within *element*, flattening inline child tags.

    Concatenates ``element.text`` and the ``text``/``tail`` of every
    descendant in document order.  This flattens ``<I>``, ``<E>``, ``<a>``
    and similar inline elements that wrap emphasised or linked text within
    a ``<P>`` node.

    Args:
        element: The XML element to collect text from.

    Returns:
        A single string with all text, whitespace collapsed.
    """
    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in element.iter():
        if child is element:
            continue
        if child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


class CFRAuthoritySourceProvider(BaseAuthoritySourceProvider):
    """Provides CFR section text from the eCFR Versioner full-text XML API.

    Handles any ``cfr-{N}`` prefix (any title) via regex rather than a fixed
    tuple.  ``supported_prefixes`` lists commonly cited titles for registry
    display; ``can_handle`` uses the regex so all titles work without code
    changes.
    """

    title = "Code of Federal Regulations"
    description = (
        "Fetches CFR sections from the eCFR Versioner full-text XML API "
        "(public domain, no API key required)."
    )
    license: ClassVar[str] = "public-domain"  # noqa: A003

    # Representative titles for registry display.  can_handle() accepts
    # all cfr-{N} prefixes via regex.
    supported_prefixes: ClassVar[tuple[str, ...]] = (
        "cfr-1",
        "cfr-2",
        "cfr-5",
        "cfr-12",
        "cfr-17",
        "cfr-26",
        "cfr-29",
        "cfr-40",
        "cfr-47",
    )

    # ---- public override ---------------------------------------------------

    def can_handle(self, canonical_key: str) -> bool:
        """Accept any ``cfr-{digits}`` prefix."""
        prefix = canonical_key.split(":", 1)[0]
        return bool(_CFR_PREFIX_RE.match(prefix))

    # ---- abstract implementations -----------------------------------------

    def _locate_impl(
        self, canonical_key: str, **all_kwargs: object
    ) -> AuthorityRequest:
        """Derive the eCFR fetch plan for *canonical_key* — pure, no I/O.

        Args:
            canonical_key: e.g. ``"cfr-40:261.4"``.
            **all_kwargs: merged component settings; ``snapshot_date`` may
                override the module default.

        Returns:
            An :class:`AuthorityRequest` with URL, params, citation, and
            extra metadata.
        """
        snapshot_date: str = str(all_kwargs.get("snapshot_date", _SNAPSHOT_DATE))

        prefix, section = canonical_key.split(":", 1)
        # prefix = "cfr-40", extract title digit string "40"
        title = prefix[len("cfr-") :]

        part = _extract_part(section)
        _validate_cfr_components(title, part, section)
        url = _ECFR_FULL_URL_TEMPLATE.format(date=snapshot_date, title=title)
        source_url = _ECFR_HUMAN_URL_TEMPLATE.format(title=title, section=section)
        citation = f"{title} CFR {section}"

        return AuthorityRequest(
            canonical_key=canonical_key,
            url=url,
            params={"part": part, "section": section},
            citation=citation,
            extra={
                "title": title,
                "section": section,
                "part": part,
                "source_url": source_url,
            },
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs: object
    ) -> list[AuthoritySection]:
        """Download the eCFR title XML and extract the requested section.

        Args:
            request: The fetch plan returned by :meth:`_locate_impl`.
            **all_kwargs: merged component settings (unused here).

        Returns:
            A single-element list with the parsed
            :class:`~opencontractserver.enrichment.authorities.AuthoritySection`,
            or an empty list if the section is not found.
        """
        extra = request.extra
        section = extra.get("section", "")
        source_url = extra.get("source_url", "")

        response = requests.get(
            request.url,
            params=request.params,
            headers={"User-Agent": _USER_AGENT},
            timeout=30,
            allow_redirects=False,
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)

        # GPO XML uses various DIV types (DIV5/DIV6/DIV8) — match by attribute.
        # The eCFR API may return the section as the root element itself (when
        # ?section= filtering is used) or as a descendant of a parent DIV.
        # Check the root element first, then fall back to a descendant search.
        if root.get("TYPE") == "SECTION" and root.get("N") == section:
            section_el: ET.Element | None = root
        else:
            section_el = None
            for el in root.iter():
                if el.get("TYPE") == "SECTION" and el.get("N") == section:
                    section_el = el
                    break
        if section_el is None:
            logger.warning(
                "CFRProvider: section %s not found in title XML (url=%s)",
                section,
                request.url,
            )
            return []

        # Heading: text of the HEAD child element.
        head_el = section_el.find("HEAD")
        heading = (head_el.text or "").strip() if head_el is not None else ""

        # Text: concatenate all <P> descendants in document order, flattening
        # inline tags (<I>, <E>, <a>, etc.).
        p_parts: list[str] = [
            _flatten_element_text(p_el)
            for p_el in section_el.iter("P")
            if _flatten_element_text(p_el)
        ]
        text = " ".join(p_parts)
        text = re.sub(r"\s+", " ", text).strip()

        return [
            AuthoritySection(
                key=request.canonical_key,
                heading=heading,
                text=text,
                source_url=source_url,
            )
        ]
