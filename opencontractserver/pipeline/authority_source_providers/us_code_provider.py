"""US Code authority source provider (OLRC USLM 1.0 XML).

Fetches statute text from the Office of Law Revision Counsel (OLRC) bulk
release-point XML files.  Each title is one large XML file (~10-30 MB)
packaged as a ZIP archive.  The provider downloads and caches the title XML
by (title, release_point), then extracts the one requested <section>.

Canonical key grammar: ``usc-{title}:{section}``
Examples: ``usc-15:78j``, ``usc-15:80a-1``, ``usc-7:1``.

Section identifiers may contain letters and hyphens (e.g. ``78j``, ``80a-1``,
``78aaa``).  They are NEVER int-cast — the OLRC identifier path is the
authoritative source (``/us/usc/t15/s78j``).
"""

from __future__ import annotations

import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import ClassVar

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import safe_fetch_bytes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants (no bare magic strings in logic)
# ---------------------------------------------------------------------------

# Current OLRC release point: "{congress}/{public-law-number}".
# Update this constant when OLRC publishes a new release point.
_DEFAULT_RELEASE_POINT = "119/95"

# USLM 1.0 namespace — every element in the title XML uses this namespace.
_USLM_NS = "http://xml.house.gov/schemas/uslm/1.0"
_NS = {"u": _USLM_NS}

# Canonical-key prefix pattern for the can_handle override.
_USC_PREFIX_RE = re.compile(r"^usc-\d+$")

# OLRC ZIP download URL template.  The ``{padded_title}`` segment is a
# zero-padded two-digit title number (``01``, ``15``, ``26``, …).
_ZIP_URL_TEMPLATE = (
    "https://uscode.house.gov/download/releasepoints/us/pl"
    "/{release_point}/xml_usc{padded_title}@{release_point_flat}.zip"
)

# The name of the XML file inside the ZIP archive.
_XML_MEMBER_TEMPLATE = "usc{padded_title}.xml"

# Human-readable source URL template.
_HUMAN_URL_TEMPLATE = (
    "https://uscode.house.gov/view.xhtml?req=granuleid"
    ":USC-prelim-title{title}-section{section}&num=0&edition=prelim"
)

# USLM element tags that must be EXCLUDED from the text output.
# This covers structural metadata (num, heading) as well as citation/note cruft.
_EXCLUDED_TAGS = {
    # Metadata — section number and title (captured separately as heading/key)
    f"{{{_USLM_NS}}}num",
    f"{{{_USLM_NS}}}heading",
    # Citation and editorial notes
    f"{{{_USLM_NS}}}sourceCredit",
    f"{{{_USLM_NS}}}notes",
    f"{{{_USLM_NS}}}note",
}

# <ref> elements with this class are footnote markers — exclude their text.
_FOOTNOTE_REF_CLASS = "footnoteRef"

# Regex patterns for validating citation components before URL construction.
# Section: digits, optional trailing letters, hyphens — e.g. '2', '78j', '80a-1'.
_USC_SECTION_RE = re.compile(r"^[0-9]+[a-z0-9-]*$", re.IGNORECASE)
# Title must be purely numeric (e.g. '15', '7', '26').
_USC_TITLE_RE = re.compile(r"^\d+$")

# --- USLM <sourceCredit> cross-reference harvest (Phase 3 "uslm" source) ------
# A USLM <sourceCredit> carries the section's legislative history as <ref>
# elements with USLM href paths. We harvest the two forms that line up exactly
# with the grammar's emitted keys (grammars._publ / _stat), so a filing that
# cites the Public Law or Statutes-at-Large form resolves to the ingested USC
# section via find_authority_target / _provider_for:
#   /us/pl/{congress}/{law}[/...]  -> publ:{congress}-{law}   (Pub. L. 111-203)
#   /us/stat/{volume}/{page}[/...] -> stat:{volume}.{page}    (48 Stat. 891)
# Act hrefs (/us/act/<date>/ch.../...) are intentionally NOT harvested — they do
# not map cleanly onto a registry prefix (date/chapter, not a slug).
_SOURCECREDIT_PL_RE = re.compile(r"^/us/pl/(?P<cong>\d+)/(?P<num>\d+)(?:/|$)")
_SOURCECREDIT_STAT_RE = re.compile(r"^/us/stat/(?P<vol>\d+)/(?P<page>\d+)(?:/|$)")
# uslm-harvested equivalences are high- but not perfect-confidence (a Public Law
# amends many sections; the bridge is correct but coarse for whole-PL citations).
_USLM_HARVEST_CONFIDENCE = 0.9

# Tags whose text content contributes to the section body.
_TEXT_CONTRIBUTING_TAGS = {
    f"{{{_USLM_NS}}}chapeau",
    f"{{{_USLM_NS}}}content",
    f"{{{_USLM_NS}}}p",
    f"{{{_USLM_NS}}}subsection",
    f"{{{_USLM_NS}}}paragraph",
    f"{{{_USLM_NS}}}clause",
    f"{{{_USLM_NS}}}subclause",
    f"{{{_USLM_NS}}}item",
    f"{{{_USLM_NS}}}subitem",
}


def _validate_usc_components(title: str, section: str) -> None:
    """Raise ValueError if *title* or *section* contain unexpected characters.

    Rejects values that could be injected into URLs or XPath expressions.
    Valid examples: title='15', section='78j', section='80a-1', section='2'.
    """
    if not _USC_TITLE_RE.match(title):
        raise ValueError(f"Invalid USC title component: {title!r}")
    if not _USC_SECTION_RE.match(section):
        raise ValueError(f"Invalid USC section component: {section!r}")


def _padded_title(title: str) -> str:
    """Zero-pad a title number to two digits (e.g. '5' → '05', '15' → '15')."""
    return title.zfill(2)


def _release_point_flat(release_point: str) -> str:
    """Convert '119/95' → '119-95' for use in filenames."""
    return release_point.replace("/", "-")


def _is_excluded(element: ET.Element) -> bool:
    """Return True if *element* should be skipped entirely (tag or class)."""
    if element.tag in _EXCLUDED_TAGS:
        return True
    # <ref class="footnoteRef"> — footnote markers inline in body text.
    if element.tag == f"{{{_USLM_NS}}}ref":
        cls = element.get("class", "")
        if _FOOTNOTE_REF_CLASS in cls.split():
            return True
    return False


def _collect_text(element: ET.Element) -> list[str]:
    """Recursively collect text from *element*, excluding sourceCredit/notes.

    Returns a list of non-empty strings gathered in document order.  The
    caller joins them with a single space and strips.
    """
    if _is_excluded(element):
        return []

    parts: list[str] = []

    # Leading text of this element (before any child element).
    if element.text and element.text.strip():
        parts.append(element.text.strip())

    for child in element:
        parts.extend(_collect_text(child))
        # Text that follows the child's closing tag (tail belongs to parent).
        if not _is_excluded(child) and child.tail and child.tail.strip():
            parts.append(child.tail.strip())

    return parts


def parse_sourcecredit_keys(section_el: ET.Element) -> list[str]:
    """Return the ``publ:``/``stat:`` canonical keys cited in *section_el*'s
    ``<sourceCredit>`` (sorted, de-duplicated).

    Pure (no DB): scans every ``<ref href>`` under the section's
    ``<sourceCredit>`` and maps the Public-Law / Statutes-at-Large href forms to
    the grammar's emitted key shapes. Returns ``[]`` when there is no
    ``<sourceCredit>`` or no recognised cross-reference.
    """
    sc = section_el.find("u:sourceCredit", _NS)
    if sc is None:
        return []
    keys: set[str] = set()
    for ref in sc.iter(f"{{{_USLM_NS}}}ref"):
        href = (ref.get("href") or "").strip()
        if not href:
            continue
        m = _SOURCECREDIT_PL_RE.match(href)
        if m:
            keys.add(f"publ:{m.group('cong')}-{m.group('num')}")
            continue
        m = _SOURCECREDIT_STAT_RE.match(href)
        if m:
            keys.add(f"stat:{m.group('vol')}.{m.group('page')}")
    return sorted(keys)


class USCodeAuthoritySourceProvider(BaseAuthoritySourceProvider):
    """Provides statute text from OLRC USLM 1.0 title XML release-point ZIPs.

    Handles any ``usc-{N}`` prefix (50+ titles) via regex rather than a fixed
    tuple.  ``supported_prefixes`` lists the most commonly cited titles for
    registry display and relink hints; ``can_handle`` uses the regex so all
    titles work without code changes.
    """

    title = "United States Code"
    description = (
        "Fetches US Code sections from OLRC USLM 1.0 release-point XML "
        "(public domain, no API key required)."
    )
    license: ClassVar[str] = "public-domain"

    # Representative titles for registry display / relink hints.
    # can_handle() accepts *all* usc-{N} prefixes via regex.
    supported_prefixes: ClassVar[tuple[str, ...]] = (
        "usc-1",
        "usc-7",
        "usc-11",
        "usc-12",
        "usc-15",
        "usc-17",
        "usc-26",
        "usc-28",
        "usc-42",
    )

    # ---- public override -------------------------------------------------- #

    def can_handle(self, canonical_key: str) -> bool:
        """Accept any ``usc-{digits}`` prefix (not just the listed titles)."""
        prefix = canonical_key.split(":", 1)[0]
        return bool(_USC_PREFIX_RE.match(prefix))

    # ---- abstract implementations ----------------------------------------- #

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        """Derive the fetch plan for *canonical_key* — pure, no I/O.

        Args:
            canonical_key: e.g. ``"usc-15:78j"``.
            **all_kwargs: merged component settings (may include
                ``release_point`` to override the module default).

        Returns:
            An :class:`AuthorityRequest` with URL, citation, and extra metadata.
        """
        release_point = all_kwargs.get("release_point", _DEFAULT_RELEASE_POINT)

        prefix, section = canonical_key.split(":", 1)
        # prefix = "usc-15", extract title digit string "15"
        title = prefix[len("usc-") :]  # e.g. "15"

        _validate_usc_components(title, section)

        padded = _padded_title(title)
        flat = _release_point_flat(release_point)

        zip_url = _ZIP_URL_TEMPLATE.format(
            release_point=release_point,
            padded_title=padded,
            release_point_flat=flat,
        )

        source_url = _HUMAN_URL_TEMPLATE.format(title=title, section=section)

        # USLM identifier for the section, e.g. "/us/usc/t15/s78j"
        identifier = f"/us/usc/t{title}/s{section}"

        return AuthorityRequest(
            canonical_key=canonical_key,
            url=zip_url,
            citation=f"{title} U.S.C. § {section}",
            extra={
                "title": title,
                "section": section,
                "identifier": identifier,
                "release_point": release_point,
                "padded_title": padded,
                "source_url": source_url,
            },
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySection]:
        """Download the title XML and extract the requested section.

        Delegates the actual bytes acquisition to :meth:`_load_title_xml` so
        tests can patch that single seam without touching HTTP or ZIP logic.

        Args:
            request: The fetch plan returned by :meth:`_locate_impl`.
            **all_kwargs: merged component settings (unused here; forwarded
                for future caching / throttle settings).

        Returns:
            A single-element list containing the parsed
            :class:`~opencontractserver.enrichment.authorities.AuthoritySection`,
            or an empty list if the section is not found in the XML.
        """
        extra = request.extra or {}
        identifier = extra.get("identifier", "")
        title = extra.get("title", "")
        section = extra.get("section", "")
        source_url = extra.get("source_url", "")

        xml_bytes = self._load_title_xml(request)

        root = ET.fromstring(xml_bytes)

        # Register namespace so XPath with the 'u' prefix works.
        ET.register_namespace("", _USLM_NS)

        _section_tag = f"{{{_USLM_NS}}}section"
        section_el: ET.Element | None = None
        for el in root.iter(_section_tag):
            if el.get("identifier") == identifier:
                section_el = el
                break
        if section_el is None:
            logger.warning(
                "USCodeProvider: section %s not found in title %s XML",
                identifier,
                title,
            )
            return []

        # --- heading ---------------------------------------------------------
        heading_el = section_el.find("u:heading", _NS)
        heading = (heading_el.text or "").strip() if heading_el is not None else ""

        # --- section number (preserved verbatim — never int-cast) ------------
        num_el = section_el.find("u:num", _NS)
        section_num = (
            (num_el.get("value") or "").strip() if num_el is not None else section
        )
        # Canonical key uses the exact string from the XML num/@value.
        canonical_key = f"usc-{title}:{section_num}"

        # --- USLM <sourceCredit> equivalence harvest (best-effort side-effect) -
        # Bridge the section's Public-Law / Statutes-at-Large cross-references to
        # the canonical USC key so a filing citing the PL/Stat form resolves to
        # this ingested section. Guarded: a malformed sourceCredit (or a non-sync
        # call context) must NEVER fail the text fetch — it only forfeits the
        # optional bridge.
        try:
            self._harvest_sourcecredit_equivalences(section_el, canonical_key)
        except Exception as exc:  # noqa: BLE001 — optional enrichment side-effect
            logger.warning(
                "USCodeProvider: sourceCredit harvest skipped for %s: %s",
                canonical_key,
                exc,
            )

        # --- text body (excluding sourceCredit / notes) ----------------------
        text_parts: list[str] = []

        # Iterate direct children in document order, collecting contributing text.
        for child in section_el:
            if _is_excluded(child):
                continue
            child_tag = child.tag
            if child_tag in _TEXT_CONTRIBUTING_TAGS or child_tag in {
                f"{{{_USLM_NS}}}chapeau",
                f"{{{_USLM_NS}}}content",
            }:
                text_parts.extend(_collect_text(child))
            elif child_tag not in _EXCLUDED_TAGS:
                # Catch any other structural elements (e.g. subsection at top)
                text_parts.extend(_collect_text(child))

        text = " ".join(text_parts).strip()
        # Collapse runs of whitespace to a single space.
        text = re.sub(r"\s+", " ", text)

        return [
            AuthoritySection(
                key=canonical_key,
                heading=heading,
                text=text,
                source_url=source_url,
            )
        ]

    # ---- seam for testing -------------------------------------------------- #

    def _load_title_xml(self, request: AuthorityRequest) -> bytes:
        """Download and unzip the OLRC title XML.

        Override or patch this method in tests to return fixture bytes without
        making any network calls.

        Args:
            request: Fetch plan; ``request.url`` is the ZIP URL and
                ``request.extra["padded_title"]`` names the XML member.

        Returns:
            Raw UTF-8 bytes of the unzipped title XML.
        """
        extra = request.extra or {}
        padded = extra.get("padded_title", "")
        member_name = _XML_MEMBER_TEMPLATE.format(padded_title=padded)

        logger.info("USCodeProvider: downloading %s", request.url)
        zip_bytes, _ = safe_fetch_bytes(request.url)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            return zf.read(member_name)

    # ---- USLM equivalence harvest ----------------------------------------- #

    def _harvest_sourcecredit_equivalences(
        self, section_el: ET.Element, canonical_key: str
    ) -> dict:
        """Upsert ``source="uslm"`` equivalences from the section's sourceCredit.

        Each harvested ``publ:``/``stat:`` key (see
        :func:`parse_sourcecredit_keys`) is bridged to ``canonical_key`` via the
        source-scoped writer (never clobbers baseline/manual/popular_name rows).
        Runs in the synchronous ingestion path (``discover_and_bootstrap`` →
        ``provider.fetch``), so the ORM write is safe. Returns per-outcome counts.
        """
        from opencontractserver.enrichment.services.authority_equivalence_ingest import (  # noqa: E501
            CREATED,
            SKIPPED_OWNED,
            UPDATED,
            upsert_equivalence,
        )

        counts = {CREATED: 0, UPDATED: 0, SKIPPED_OWNED: 0}
        for from_key in parse_sourcecredit_keys(section_el):
            outcome = upsert_equivalence(
                from_key=from_key,
                to_key=canonical_key,
                source="uslm",
                confidence=_USLM_HARVEST_CONFIDENCE,
                note="USLM sourceCredit cross-reference",
            )
            if outcome in counts:
                counts[outcome] += 1
        if counts[CREATED] or counts[UPDATED]:
            logger.info(
                "USCodeProvider: harvested %s sourceCredit equivalence(s) for %s",
                counts[CREATED] + counts[UPDATED],
                canonical_key,
            )
        return counts
