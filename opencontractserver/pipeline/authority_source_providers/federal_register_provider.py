"""Federal Register authority source provider (Federal Register API v1).

Fetches Federal Register document text via a two-hop strategy:
  1. Resolve a volume/page citation to a document number via the FR citation
     redirect endpoint (302 response, Location header carries the slug).
  2. Fetch the document metadata JSON, then retrieve the full plain-text body
     from ``raw_text_url`` (falls back to ``abstract`` if the body GET fails).

Canonical key grammar: ``fedreg:{volume}.{page}``
Examples: ``fedreg:88.1722``, ``fedreg:88.2371``.
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

import requests

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import safe_fetch_text, validate_url

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Federal Register API base URL.
_FR_API_BASE = "https://www.federalregister.gov"

# Step-1 citation redirect URL template.
# Pattern: /citation/{volume}-FR-{page}  →  302  →  /documents/{d}/{slug}
_FR_CITATION_URL_TEMPLATE = "{base}/citation/{volume}-FR-{page}"

# Step-2 document JSON endpoint template.
_FR_DOC_JSON_URL_TEMPLATE = "{base}/api/v1/documents/{document_number}.json"

# Regex to extract the document number from the redirect Location path.
# e.g. /documents/2023/01/13/2023-00485/some-slug  →  group(1) = "2023-00485"
_LOCATION_DOC_NUMBER_RE = re.compile(r"/documents/\d{4}/\d{2}/\d{2}/([^/]+)/")

# HTTP User-Agent header.
_USER_AGENT = (
    "OpenContracts-authority-provider/1.0 "
    "(https://github.com/Open-Source-Legal/OpenContracts; "
    "contact: opensource@opencontracts.dev)"
)

# Regex for parsing a Federal Register citation to derive volume and page.
# Matches e.g. "88 FR 2371" and "88 FR 12345".
_FR_CITATION_RE = re.compile(r"(\d+)\s+FR\s+(\d+)")

# Regex patterns for validating citation components before URL construction.
# Volume and page must be purely numeric.
_FR_VOLUME_RE = re.compile(r"^\d+$")
_FR_PAGE_RE = re.compile(r"^\d+$")


def _validate_fr_components(volume: str, page: str) -> None:
    """Raise ValueError if Federal Register volume or page contain unexpected characters.

    Valid examples: volume='88', page='2371'.
    """
    if not _FR_VOLUME_RE.match(volume):
        raise ValueError(f"Invalid Federal Register volume component: {volume!r}")
    if not _FR_PAGE_RE.match(page):
        raise ValueError(f"Invalid Federal Register page component: {page!r}")


class FederalRegisterAuthoritySourceProvider(BaseAuthoritySourceProvider):
    """Provides Federal Register document text via the FR API v1.

    The ``fedreg`` prefix is the sole supported prefix.  The default
    :meth:`can_handle` (exact prefix membership check) is sufficient.
    """

    title = "Federal Register"
    description = (
        "Fetches Federal Register documents from the FR API v1 via a "
        "two-hop citation redirect + document JSON strategy "
        "(public domain, no API key required)."
    )
    license: ClassVar[str] = "public-domain"  # noqa: A003

    supported_prefixes: ClassVar[tuple[str, ...]] = ("fedreg",)

    # ---- abstract implementations -----------------------------------------

    def _locate_impl(
        self, canonical_key: str, **all_kwargs: object
    ) -> AuthorityRequest:
        """Derive the Federal Register fetch plan for *canonical_key* — pure, no I/O.

        Args:
            canonical_key: e.g. ``"fedreg:88.1722"``.
            **all_kwargs: merged component settings (currently unused).

        Returns:
            An :class:`AuthorityRequest` with the step-1 citation-redirect URL
            and volume/page in ``extra``.
        """
        # canonical_key = "fedreg:88.1722"  →  volume="88", page="1722"
        _, volume_page = canonical_key.split(":", 1)
        volume, page = volume_page.split(".", 1)

        _validate_fr_components(volume, page)

        citation = f"{volume} FR {page}"
        step1_url = _FR_CITATION_URL_TEMPLATE.format(
            base=_FR_API_BASE,
            volume=volume,
            page=page,
        )

        return AuthorityRequest(
            canonical_key=canonical_key,
            url=step1_url,
            citation=citation,
            extra={"volume": volume, "page": page},
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs: object
    ) -> list[AuthoritySection]:
        """Execute the two-hop fetch for the Federal Register document.

        Step 1: GET the citation redirect URL (expecting a 302).  Parse the
        ``Location`` header to extract the ``document_number``.

        Step 2: GET ``/api/v1/documents/{document_number}.json`` for metadata.

        Step 3: GET ``raw_text_url`` for the full plain-text body; fall back
        to ``abstract`` if that GET raises any exception.

        Args:
            request: The fetch plan returned by :meth:`_locate_impl`.
            **all_kwargs: merged component settings (currently unused).

        Returns:
            A single-element list with the parsed
            :class:`~opencontractserver.enrichment.authorities.AuthoritySection`.

        Raises:
            :exc:`requests.HTTPError`: If steps 1 or 2 return non-200/302
                status codes.
            :exc:`ValueError`: If the document number cannot be parsed from
                the redirect Location.
        """
        headers = {"User-Agent": _USER_AGENT}

        # Steps 1+2 are SSRF-guarded by validate_url() (scheme/allowlist/DNS) but
        # use raw requests rather than safe_fetch_*: step 1 needs the 302 Location
        # header (no body) and step 2 is the FR-API metadata JSON, which is
        # practically bounded. Only the large full-text body (step 3) goes through
        # safe_fetch_text's size cap.

        # --- Step 1: citation redirect → document_number --------------------
        validate_url(request.url)
        step1_resp = requests.get(
            request.url,
            allow_redirects=False,
            headers=headers,
            timeout=15,
        )
        # A successful citation lookup is a 302 redirect (not an error status, so
        # raise_for_status() passes it through). Surface a 4xx/5xx as a clear
        # HTTPError instead of the confusing "could not parse … from ''" below.
        step1_resp.raise_for_status()
        location = step1_resp.headers.get("Location", "")
        match = _LOCATION_DOC_NUMBER_RE.search(location)
        if match is None:
            raise ValueError(
                f"FederalRegisterProvider: could not parse document_number "
                f"from Location header {location!r} (step-1 URL: {request.url})"
            )
        document_number = match.group(1)

        # --- Step 2: fetch document JSON ------------------------------------
        doc_json_url = _FR_DOC_JSON_URL_TEMPLATE.format(
            base=_FR_API_BASE,
            document_number=document_number,
        )
        validate_url(doc_json_url)
        doc_resp = requests.get(doc_json_url, headers=headers, timeout=30)
        doc_resp.raise_for_status()
        doc = doc_resp.json()

        heading: str = doc.get("title", "")
        html_url: str = doc.get("html_url", "")
        abstract: str = doc.get("abstract", "")
        raw_text_url: str = doc.get("raw_text_url", "")

        # Derive canonical key from the JSON citation (authoritative page number).
        json_citation: str = doc.get("citation", "")
        citation_match = _FR_CITATION_RE.match(json_citation) if json_citation else None
        if citation_match:
            key = f"fedreg:{citation_match.group(1)}.{citation_match.group(2)}"
        else:
            key = request.canonical_key

        # --- Step 3: fetch full plain-text body (fall back to abstract) -----
        # safe_fetch_text enforces the allowlist + IP validation centrally;
        # SSRFValidationError is raised for any non-allowlisted/private host,
        # which the except block catches and degrades gracefully to abstract.
        text = abstract
        if raw_text_url:
            try:
                text, _ = safe_fetch_text(raw_text_url, headers=headers)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "FederalRegisterProvider: raw_text_url fetch failed (%s); "
                    "falling back to abstract for document %s",
                    raw_text_url,
                    document_number,
                )

        return [
            AuthoritySection(
                key=key,
                heading=heading,
                text=text,
                source_url=html_url,
            )
        ]
