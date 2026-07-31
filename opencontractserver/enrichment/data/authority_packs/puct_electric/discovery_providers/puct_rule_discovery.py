"""Discover PUCT Chapter 25 electric-rule pages."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from opencontractserver.pipeline.base.authority_html import extract_authority_links
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)
from opencontractserver.utils.safe_http import safe_fetch_text

_RULE_PATH_RE = re.compile(
    r"/agency/rulesnlaws/subrules/electric/(?P<section>25\.\d+[A-Za-z]?)/?$",
    re.I,
)


def parse_puct_rule_index(html: str, *, index_url: str) -> list[DiscoveryCandidate]:
    candidates: list[DiscoveryCandidate] = []
    for link in extract_authority_links(html, base_url=index_url):
        match = _RULE_PATH_RE.search(urlsplit(link.url).path)
        if match is None:
            continue
        section = match.group("section")
        candidates.append(
            DiscoveryCandidate(
                canonical_key=f"tx-admin-puct:{section}",
                url=link.url,
                title=link.text or f"16 Texas Administrative Code § {section}",
                extra={"section": section},
            )
        )
    return candidates


class PUCTRuleDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "PUCT Electric Rule Discovery"
    description = "Discovers official PUCT Chapter 25 electric-rule pages."

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_puct_rule_index(html, index_url=index_url)
