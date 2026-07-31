"""Discover section-addressable Texas Utilities Code links."""

from __future__ import annotations

import re

from opencontractserver.pipeline.base.authority_html import extract_authority_links
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
    DiscoveryCandidate,
)
from opencontractserver.utils.safe_http import safe_fetch_text

_CHAPTER_PATH_RE = re.compile(r"/resources/UT/htm/UT\.(?P<chapter>\d+)\.htm$", re.I)
_SECTION_TEXT_RE = re.compile(
    r"(?:§|Sec(?:tion)?\.?)\s*(?P<section>\d+[A-Za-z]?(?:\.\d+[A-Za-z]?)+)",
    re.I,
)


def parse_texas_code_index(html: str, *, index_url: str) -> list[DiscoveryCandidate]:
    candidates: list[DiscoveryCandidate] = []
    for link in extract_authority_links(html, base_url=index_url, keep_fragments=True):
        path, _, fragment = link.url.partition("#")
        path_match = _CHAPTER_PATH_RE.search(path)
        if path_match is None:
            continue
        section_match = _SECTION_TEXT_RE.search(link.text)
        section = fragment.strip() or (
            section_match.group("section") if section_match is not None else ""
        )
        section = section.removeprefix("Sec.").removeprefix("sec.").strip()
        if not re.fullmatch(r"\d+[A-Za-z]?(?:\.\d+[A-Za-z]?)+", section):
            continue
        candidates.append(
            DiscoveryCandidate(
                canonical_key=f"tx-util:{section}",
                url=path,
                title=link.text or f"Texas Utilities Code § {section}",
                extra={
                    "chapter": path_match.group("chapter"),
                    "section": section,
                },
            )
        )
    return candidates


class TexasCodeDiscoveryProvider(BaseAuthorityDiscoveryProvider):
    title = "Texas Utilities Code Index Discovery"
    description = "Discovers official Texas Utilities Code section links."

    def _fetch_index_impl(self, index_url: str, **all_kwargs) -> tuple[str, str]:
        del all_kwargs
        return safe_fetch_text(index_url)

    def _parse_index_impl(
        self, html: str, *, index_url: str, **all_kwargs
    ) -> list[DiscoveryCandidate]:
        del all_kwargs
        return parse_texas_code_index(html, index_url=index_url)
