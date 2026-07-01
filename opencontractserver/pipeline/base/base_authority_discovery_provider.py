"""Base class for authority DISCOVERY providers (Phase 2, issue #2054).

``BaseAuthoritySourceProvider`` (``base_authority_source_provider.py``) is
citation-KEYED: given a *known* ``canonical_key``, it resolves the fetch plan and
downloads the section text. ``BaseAuthorityDiscoveryProvider`` answers a
different question: crawl a publisher's index/listing page(s) for documents
NOBODY HAS CITED YET, and surface them as candidates (canonical_key + url +
minimal metadata) for ``AuthorityFrontierService`` to seed. It never fetches full
document text or ingests anything — that stays the job of a (separately
registered) ``BaseAuthoritySourceProvider`` once a frontier row is routed to one.

Motivating case (``docs/architecture/proposals/0002-authority-packs.md`` §7, gap
3): Bolivia's official sources (Gaceta Oficial / TSJ / TCP) are listing-page
publishers, not key-addressable — nobody can build a deterministic
``canonical_key -> URL`` ``BaseAuthoritySourceProvider`` for them, because the
"key" a citation would use does not exist until an operator has actually crawled
the index and discovered it. This abstraction closes that gap.

Design mirrors ``BaseAuthoritySourceProvider``'s locate/fetch split:
    - ``_fetch_index_impl`` (I/O): download ONE index/listing page. MUST route
      through ``safe_fetch_text``/``safe_fetch_bytes`` (the SSRF gate).
    - ``_parse_index_impl`` (pure): turn an ALREADY-FETCHED index page into
      ``DiscoveryCandidate`` objects — no I/O, so tests exercise it directly
      against fixture HTML with zero network calls (the same
      ``httpx.MockTransport``-style testing precedent credited to PR #1305 in
      the proposal doc, adapted here to patching/mocking the fetch step so the
      parse step stays pure and deterministic).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import ClassVar

import httpx

from opencontractserver.enrichment.constants import (
    AUTHORITY_LICENSE_PUBLIC_DOMAIN,
    DISCOVERY_DEFAULT_MAX_CANDIDATES,
    DISCOVERY_MAX_MAX_CANDIDATES,
)
from opencontractserver.pipeline.base.base_component import PipelineComponentBase
from opencontractserver.utils.numbers import clamp_int
from opencontractserver.utils.safe_http import SSRFValidationError

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryCandidate:
    """A document FOUND on a publisher index page — not yet fetched or ingested.

    Mirrors ``AuthorityRequest``'s "found, not yet fetched" shape (see
    ``base_authority_source_provider.AuthorityRequest``): ``discover_candidates()``
    turns an index page into these; nothing here performs I/O or ingestion.
    Seeding a ``DiscoveryCandidate`` into ``AuthorityFrontier`` (via
    ``AuthorityFrontierService.seed_from_discovery``) only QUEUES it for the
    existing ``discover_and_bootstrap`` runtime, which resolves it via whatever
    ``BaseAuthoritySourceProvider`` (if any) ``can_handle``s its canonical_key —
    this class does not fetch the document body itself.
    """

    canonical_key: str  # e.g. "bo-gaceta:2024-1234"
    url: str  # the document's own URL (not the index page it was found on)
    title: str | None = None  # human-readable heading, if the index page has one
    # Provider-owned scratch (e.g. the index_url the candidate was found on).
    # Always-dict (never None) so callers index it without guards.
    extra: dict = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    """Outcome of one ``discover_candidates()`` run — never silently truncated.

    ``skipped_index_urls`` maps an index URL to the reason it produced zero
    candidates (SSRF validation failure, HTTP error, …) so a mis-configured or
    unreachable index page is visible to the operator instead of silently
    folding into an empty result.
    """

    candidates: list[DiscoveryCandidate]
    skipped_index_urls: dict[str, str]
    # True only when max_candidates ACTUALLY cut discovery short — i.e. at
    # least one more distinct candidate is PROVABLY left unprocessed (either
    # later in the same already-parsed index page, or in an index_url this run
    # never got to fetch). If the cap is reached exactly as the very last
    # distinct candidate from the very last already-fetched page is collected,
    # capped is False: nothing was left out, so raising max_candidates would
    # not surface more documents. Never determined by fetching an extra page
    # just to check — only data already in memory from this run.
    capped: bool


class BaseAuthorityDiscoveryProvider(PipelineComponentBase, ABC):
    """Crawls a publisher's index/listing page(s) for undiscovered candidates.

    A discovery provider owns a family of PUBLISHER index pages (not a
    canonical_key family like ``BaseAuthoritySourceProvider``): given one or
    more index URLs, it lists candidate documents nobody has cited yet.

    ClassVars mirror ``BaseAuthoritySourceProvider``'s registry-facing metadata
    (``license`` / ``priority`` / ``enabled``) so the pipeline registry and any
    future console surface can display discovery providers the same way.
    """

    # The authority body's licence — gates discovery to public-domain sources
    # only, mirroring BaseAuthoritySourceProvider.license. discover_candidates()
    # refuses to run (raises PermissionError) unless this is "public-domain".
    license: ClassVar[str] = AUTHORITY_LICENSE_PUBLIC_DOMAIN  # noqa: A003
    # Lower priority value = preferred. Unused by today's single reference
    # provider; kept for registry symmetry with BaseAuthoritySourceProvider and
    # for future provider-selection logic (e.g. an operator surface choosing
    # among several discovery providers for one publisher).
    priority: ClassVar[int] = 100
    # Set False to exclude a provider from registry-facing listings.
    enabled: ClassVar[bool] = True

    # ---- public API -----------------------------------------------------------
    def discover_candidates(
        self,
        index_urls: Sequence[str],
        *,
        max_candidates: int | None = None,
        **direct_kwargs,
    ) -> DiscoveryResult:
        """Fetch + parse index page(s) into candidates, bounded by max_candidates.

        Every index page is fetched via ``_fetch_index_impl`` (which MUST route
        through ``safe_fetch_text``/``safe_fetch_bytes`` — the SSRF gate) and
        parsed via the pure ``_parse_index_impl``. An index URL that fails SSRF
        validation or any other fetch error is recorded in
        ``DiscoveryResult.skipped_index_urls`` and the run continues with the
        remaining URLs — one bad host never aborts discovery of the others.

        Candidates are de-duplicated by ``canonical_key`` within one run (a
        paginated listing whose pages overlap must not seed the same key twice)
        and the run stops as soon as ``max_candidates`` distinct candidates have
        been collected — the per-run bound the crawl proposal requires.
        ``DiscoveryResult.capped`` reports whether that bound ACTUALLY cut
        anything short (see its field docstring) — reaching the cap on the
        very last available candidate is reported as NOT capped, since nothing
        was left out.

        Raises:
            PermissionError: if ``self.license`` is not ``"public-domain"`` — a
                discovery provider must never crawl a non-public-domain source
                (mirrors ``AuthorityGateService``'s license check).
        """
        if self.license != AUTHORITY_LICENSE_PUBLIC_DOMAIN:
            raise PermissionError(
                f"{type(self).__name__}: license {self.license!r} is not "
                "public-domain; discovery is refused."
            )
        merged = {**self.get_component_settings(), **direct_kwargs}
        cap = clamp_int(
            (
                DISCOVERY_DEFAULT_MAX_CANDIDATES
                if max_candidates is None
                else max_candidates
            ),
            lower=1,
            upper=DISCOVERY_MAX_MAX_CANDIDATES,
        )

        url_list = list(index_urls)
        candidates: list[DiscoveryCandidate] = []
        skipped: dict[str, str] = {}
        seen_keys: set[str] = set()

        for url_idx, index_url in enumerate(url_list):
            try:
                html = self._fetch_index_impl(index_url, **merged)
            except SSRFValidationError as exc:
                skipped[index_url] = f"blocked: {exc}"
                continue
            except (httpx.HTTPError, OSError) as exc:
                logger.warning(
                    "discover_candidates: failed to fetch index %s: %s",
                    index_url,
                    exc,
                )
                skipped[index_url] = f"error: {exc}"
                continue

            # Materialize (not just iterate) so a look-ahead can prove whether
            # anything distinct remains on THIS page once the cap is hit —
            # never fetch another page just to answer that question.
            page_candidates = list(
                self._parse_index_impl(html, index_url=index_url, **merged)
            )
            for cand_idx, candidate in enumerate(page_candidates):
                if candidate.canonical_key in seen_keys:
                    continue
                seen_keys.add(candidate.canonical_key)
                candidates.append(candidate)
                if len(candidates) >= cap:
                    more_in_page = any(
                        later.canonical_key not in seen_keys
                        for later in page_candidates[cand_idx + 1 :]
                    )
                    more_urls_unfetched = url_idx + 1 < len(url_list)
                    return DiscoveryResult(
                        candidates=candidates,
                        skipped_index_urls=skipped,
                        capped=more_in_page or more_urls_unfetched,
                    )

        # Every index_url was processed (fetched, skipped, or exhausted) and
        # the cap was never reached — nothing was truncated.
        return DiscoveryResult(
            candidates=candidates, skipped_index_urls=skipped, capped=False
        )

    # ---- subclass contract ------------------------------------------------- #
    @abstractmethod
    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> str:
        """Download ONE index/listing page. MUST route through safe_http."""

    @abstractmethod
    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        """Pure: extract candidates from an ALREADY-FETCHED index page."""
