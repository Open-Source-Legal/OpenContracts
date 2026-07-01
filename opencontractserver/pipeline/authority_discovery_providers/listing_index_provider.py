"""Config-driven "listing index" discovery provider (Phase 2, issue #2054).

The ONE reference implementation of ``BaseAuthorityDiscoveryProvider``: given an
index-page URL and a declarative :class:`ListingIndexRule` (a regex over the raw
HTML plus a canonical-key template), it lists candidate documents. The crawler
logic itself is completely jurisdiction-agnostic — a different publisher plugs
in a different ``ListingIndexRule`` (``link_pattern`` / ``canonical_key_template``
/ ``prefix``), not different code, so ONE class serves every "regularly
structured listing page" publisher (a paginated table of links to individual
documents — the shape PR #1305's Gaceta Oficial / TSJ / TCP scrapers all shared,
per ``docs/architecture/proposals/0002-authority-packs.md`` §6).

No HTML-parsing library dependency: ``_parse_index_impl`` applies the
caller-supplied regex directly to the raw HTML text via ``re.finditer``. This
keeps the engine dependency-free (this repo carries no BeautifulSoup/lxml) and
fully deterministic against a fixture string in tests, at the cost of requiring
a rule tuned to each source's actual markup. A publisher whose markup is too
irregular for one templated regex can subclass
``BaseAuthorityDiscoveryProvider`` directly and override ``_parse_index_impl``
with bespoke parsing — this class is the common case, not the only case.

Illustrative worked example (Bolivia's Gaceta Oficial, per the proposal's
motivating case) — NOT a verified live scraper: nobody in this repo has
inspected the real site's current HTML, so no real index URL or host is wired
in here or into the shipped ``bolivia`` pack. See
``opencontractserver/tests/test_listing_index_discovery_provider.py`` for a
synthetic, Gaceta-Oficial-*shaped* fixture exercising this engine end-to-end
against mocked HTML — the pattern the proposal doc credits to PR #1305's
``httpx.MockTransport`` testing approach. An operator who has verified a real
publisher's markup supplies their own ``ListingIndexRule`` (e.g. via the
``discover_authority_candidates`` management command); wiring a *verified* rule
into a pack's own config is a follow-up left to that operator, not to this PR.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urljoin

from opencontractserver.constants.safe_http import AUTHORITY_PROVIDER_USER_AGENT
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)
from opencontractserver.utils.safe_http import safe_fetch_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ListingIndexRule:
    """Declarative extraction rule for one publisher's index-page markup.

    ``link_pattern`` is a regex applied to the raw fetched index-page HTML via
    ``re.finditer``. It MUST define a named group ``url`` (the document link —
    resolved against the index page URL if relative) and MAY define any other
    named groups (e.g. ``id``, ``date``) consumed by ``canonical_key_template``,
    plus an optional ``title`` group used as the candidate's human-readable
    heading.

    ``canonical_key_template`` is a ``str.format`` template consuming ``prefix``
    plus the regex's named groups, e.g. ``"{prefix}:{id}"`` ->
    ``"bo-gaceta:2024-1234"``. A match missing a group the template references
    is skipped (not raised) so one malformed row in a listing page does not
    abort the whole page.
    """

    link_pattern: str
    canonical_key_template: str
    prefix: str

    def __post_init__(self) -> None:
        try:
            compiled = re.compile(self.link_pattern)
        except re.error as exc:
            raise ValueError(
                f"invalid link_pattern {self.link_pattern!r}: {exc}"
            ) from exc
        if "url" not in compiled.groupindex:
            raise ValueError(
                "link_pattern must define a named group 'url' "
                f"(got groups: {sorted(compiled.groupindex)})"
            )


class ListingIndexDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    """Generic regex-driven listing-index crawler.

    Callers MUST pass a ``rule=ListingIndexRule(...)`` keyword to
    ``discover_candidates()`` (forwarded through as ``**direct_kwargs``, exactly
    like ``BaseAuthoritySourceProvider.locate``/``fetch`` forward provider
    settings) — the class itself carries no jurisdiction-specific state.
    """

    title = "Listing Index Discovery Provider"
    description = (
        "Config-driven crawler: lists candidate documents from a publisher's "
        "index/listing page via a declarative regex + canonical-key template. "
        "Fetches nothing beyond the index page itself — document ingestion "
        "happens later via a citation-keyed BaseAuthoritySourceProvider."
    )
    license: ClassVar[str] = "public-domain"  # noqa: A003

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> str:
        text, _ = safe_fetch_text(
            index_url, headers={"User-Agent": AUTHORITY_PROVIDER_USER_AGENT}
        )
        return text

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        rule = all_kwargs.get("rule")
        if not isinstance(rule, ListingIndexRule):
            raise ValueError(
                "ListingIndexDiscoveryProvider requires a rule=ListingIndexRule(...) "
                "kwarg (pass it to discover_candidates())."
            )
        pattern = re.compile(rule.link_pattern)
        candidates: list[DiscoveryCandidate] = []
        for match in pattern.finditer(html):
            groups = match.groupdict()
            url = groups.get("url")
            if not url:
                continue
            try:
                canonical_key = rule.canonical_key_template.format(
                    prefix=rule.prefix, **groups
                )
            except (KeyError, IndexError) as exc:
                logger.debug(
                    "listing index: skipping match missing template field: %s", exc
                )
                continue
            candidates.append(
                DiscoveryCandidate(
                    canonical_key=canonical_key,
                    url=urljoin(index_url, url),
                    title=groups.get("title"),
                    extra={"index_url": index_url},
                )
            )
        return candidates
