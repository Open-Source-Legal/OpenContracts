"""Discover key-addressable ERCOT market notices."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from opencontractserver.pipeline.base.authority_html import extract_authority_links
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)
from opencontractserver.utils.safe_http import safe_fetch_text

_NOTICE_PATH_RE = re.compile(
    r"/services/comm/mkt_notices/(?P<notice>[A-Z]-[A-Z]\d{6}-\d+)/?$", re.I
)


def parse_ercot_market_notice_index(
    html: str, *, index_url: str
) -> list[DiscoveryCandidate]:
    candidates: list[DiscoveryCandidate] = []
    for link in extract_authority_links(html, base_url=index_url):
        match = _NOTICE_PATH_RE.search(urlsplit(link.url).path)
        if match is None:
            continue
        notice = match.group("notice").upper()
        candidates.append(
            DiscoveryCandidate(
                canonical_key=f"ercot-notice:{notice}",
                url=link.url,
                title=link.text or f"ERCOT Market Notice {notice}",
                extra={"notice": notice, "source_identifier": notice},
            )
        )
    return candidates


class ERCOTMarketNoticeDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "ERCOT Market Notice Discovery"
    description = "Discovers ERCOT market-notice detail pages."
    license = "copyright-review-required"
    link_only_discovery = True

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_ercot_market_notice_index(html, index_url=index_url)
