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

import json
import logging
import re
from typing import ClassVar

import requests

from opencontractserver.constants.safe_http import (
    AUTHORITY_PROVIDER_USER_AGENT,
    CONNECT_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
)
from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import (
    SSRFValidationError,
    safe_fetch_bytes,
    safe_fetch_text,
    validate_url,
)

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
# The capture is restricted to digits + hyphen (real FR document numbers are
# ``YYYY-NNNNN``) so a malformed/attacker-influenced Location carrying letters,
# underscores, or URL-special characters (``?``, ``#``, …) fails to match and
# raises rather than silently interpolating them into the step-2 URL and hitting
# the wrong endpoint.
_LOCATION_DOC_NUMBER_RE = re.compile(r"/documents/\d{4}/\d{2}/\d{2}/([\d-]+)/")

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

        Step 2: GET ``/api/v1/documents/{document_number}.json`` for metadata
        via ``safe_fetch_bytes`` (re-validates every redirect hop).

        Step 3: GET ``raw_text_url`` for the full plain-text body; fall back
        to ``abstract`` if that GET raises any exception.

        Args:
            request: The fetch plan returned by :meth:`_locate_impl`.
            **all_kwargs: merged component settings (currently unused).

        Returns:
            A single-element list with the parsed
            :class:`~opencontractserver.enrichment.authorities.AuthoritySection`.

        Raises:
            :exc:`requests.HTTPError`: If step 1 returns a non-200/302 status.
            :exc:`opencontractserver.utils.safe_http.SSRFValidationError`: If the
                step-2 JSON URL (or any of its redirect hops) fails the
                scheme/allowlist/public-IP check.
            :exc:`httpx.HTTPError`: If step 2 returns a non-2xx status.
            :exc:`ValueError`: If the document number cannot be parsed from
                the redirect Location.
        """
        headers = {"User-Agent": AUTHORITY_PROVIDER_USER_AGENT}

        # Step 1 uses raw requests with ``allow_redirects=False``: it needs the
        # 302 Location header WITHOUT following it (the redirect target IS the
        # data we want — the document slug). Because redirects are not followed
        # and ``validate_url`` vets the template-constructed URL up front, there
        # is no SSRF-via-redirect surface on this hop. This step still goes
        # through raw ``requests`` rather than ``safe_fetch_bytes``, so it does
        # NOT get that helper's DNS-pinned connection (issue #2048); the
        # residual DNS-rebind TOCTOU window is mitigated by the fixed
        # federalregister.gov allowlist and the single, non-redirected request.
        #
        # Step 2 previously also used requests.get, which silently follows
        # redirects — a real SSRF gap, since the document_number embedded in the
        # step-2 URL is parsed from the step-1 response (externally influenced).
        # Step 2 now goes through safe_fetch_bytes, which re-validates every
        # redirect hop against the allowlist + public-IP check.

        # --- Step 1: citation redirect → document_number --------------------
        validate_url(request.url)
        step1_resp = requests.get(
            request.url,
            allow_redirects=False,
            headers=headers,
            # requests reads a 2-tuple as (connect, read); reuse the shared
            # safe_http timeout constants instead of a single magic value.
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
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

        # --- Step 2: fetch document JSON (SSRF-safe, re-validates redirects) -
        doc_json_url = _FR_DOC_JSON_URL_TEMPLATE.format(
            base=_FR_API_BASE,
            document_number=document_number,
        )
        # safe_fetch_bytes validates the URL itself (no separate validate_url
        # needed) and re-checks every redirect hop. The JSON body is tiny, so
        # the default 50 MB cap is ample.
        doc_bytes, _ = safe_fetch_bytes(doc_json_url, headers=headers)
        doc = json.loads(doc_bytes)

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
            except SSRFValidationError:
                # An SSRF block (off-allowlist/private host) is a SECURITY signal,
                # not a transient network error — log it distinctly so it is not
                # buried among ordinary fetch failures. We still degrade to the
                # abstract (rather than re-raising) so an FR doc whose raw_text_url
                # points off-host still yields its summary; see
                # test_raw_text_url_offhost_falls_back_to_abstract.
                logger.warning(
                    "FederalRegisterProvider: raw_text_url %s blocked by SSRF "
                    "guard for document %s; falling back to abstract",
                    raw_text_url,
                    document_number,
                )
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
