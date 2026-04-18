"""Base scraper abstractions for Bolivian legal sources.

Design goals:

- **Defensive**: a single broken entry must not abort a batch. The base
  class wraps per-entry parsing in try/except and logs, so ``iter_entries``
  always returns a usable iterator.
- **Testable**: HTTP is injected via an ``httpx.Client`` so tests can use
  ``httpx.MockTransport`` with fixture HTML/PDFs.
- **Rate-limited**: a simple sleep between requests keeps us polite to
  the government sites. The delay is tunable per-source (and zeroed in
  tests).
- **Configurable**: listing URLs and per-source overrides come from
  Django settings / env vars so deployments can point at staging mirrors
  or freeze a specific archive URL without code changes.

Each concrete scraper provides:

- ``source_key`` — matches :class:`LegalSource` values.
- ``default_base_url`` / ``default_listing_paths`` — used if not overridden.
- ``extract_entries(html, url)`` — source-specific HTML parsing.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import time
from collections.abc import Iterable, Iterator
from typing import ClassVar
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "OpenContractsBolivianLawsBot/1.0 " "(+https://github.com/JSv4/OpenContracts)"
)
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_REQUEST_DELAY_SECONDS = 1.0


@dataclasses.dataclass
class ScrapedEntry:
    """A single candidate document discovered by a scraper.

    The scraper produces these from listing pages; the ingestion pipeline
    turns them into ``BolivianLegalDocument`` + ``Document`` records.
    """

    source_key: str
    pdf_url: str
    title: str
    external_id: str = ""
    published_at: dt.date | None = None
    suggested_area: str | None = None
    metadata: dict = dataclasses.field(default_factory=dict)

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        if self.published_at is not None:
            out["published_at"] = self.published_at.isoformat()
        return out


class BaseScraper:
    """Template-method base class for Bolivian legal source scrapers."""

    source_key: ClassVar[str] = ""
    default_base_url: ClassVar[str] = ""
    default_listing_paths: ClassVar[tuple[str, ...]] = ()
    settings_base_url_key: ClassVar[str] = ""
    settings_listing_paths_key: ClassVar[str] = ""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        user_agent: str | None = None,
        request_delay_seconds: float | None = None,
        base_url: str | None = None,
        listing_paths: Iterable[str] | None = None,
    ) -> None:
        if not self.source_key:
            raise NotImplementedError(f"{type(self).__name__} must set source_key.")

        self.user_agent = (
            user_agent
            or getattr(settings, "BOLIVIAN_LAWS_SCRAPER_USER_AGENT", None)
            or DEFAULT_USER_AGENT
        )
        self.request_delay_seconds = (
            request_delay_seconds
            if request_delay_seconds is not None
            else float(
                getattr(
                    settings,
                    "BOLIVIAN_LAWS_REQUEST_DELAY_SECONDS",
                    DEFAULT_REQUEST_DELAY_SECONDS,
                )
            )
        )
        self.base_url = (
            base_url
            or (
                getattr(settings, self.settings_base_url_key, None)
                if self.settings_base_url_key
                else None
            )
            or self.default_base_url
        )
        resolved_paths = listing_paths
        if resolved_paths is None and self.settings_listing_paths_key:
            resolved_paths = getattr(settings, self.settings_listing_paths_key, None)
        if resolved_paths is None:
            resolved_paths = self.default_listing_paths
        self.listing_paths = tuple(resolved_paths)

        self._owns_client = client is None
        self._client = client or httpx.Client(
            headers={"User-Agent": self.user_agent},
            timeout=DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    # -- lifecycle ----------------------------------------------------
    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> BaseScraper:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- public API ---------------------------------------------------
    def iter_entries(
        self,
        *,
        since: dt.date | None = None,
        max_entries: int | None = None,
    ) -> Iterator[ScrapedEntry]:
        """Yield :class:`ScrapedEntry` objects from every listing page.

        ``since`` is passed to :meth:`extract_entries` so subclasses can
        prune; we also filter here as a safety net using
        ``ScrapedEntry.published_at`` when present.
        """
        count = 0
        for listing_url in self._iter_listing_urls():
            try:
                html = self._http_get_text(listing_url)
            except Exception as exc:
                logger.warning(
                    "[%s] failed to fetch listing %s: %s",
                    self.source_key,
                    listing_url,
                    exc,
                )
                continue

            try:
                entries = list(self.extract_entries(html=html, url=listing_url))
            except Exception:
                logger.exception(
                    "[%s] listing parse failure: %s",
                    self.source_key,
                    listing_url,
                )
                continue

            for entry in entries:
                if (
                    since is not None
                    and entry.published_at is not None
                    and entry.published_at < since
                ):
                    continue
                yield entry
                count += 1
                if max_entries is not None and count >= max_entries:
                    return

    def download_pdf(self, entry: ScrapedEntry) -> bytes:
        """Download the PDF bytes for the given entry."""
        return self._http_get_bytes(entry.pdf_url)

    # -- hooks for subclasses -----------------------------------------
    def extract_entries(self, *, html: str, url: str) -> Iterable[ScrapedEntry]:
        """Return entries parsed from a single listing page."""
        # Default implementation: treat every <a href="*.pdf"> as an entry.
        # Concrete scrapers should override for richer metadata.
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a"):
            href = (anchor.get("href") or "").strip()
            if not href.lower().endswith(".pdf"):
                continue
            pdf_url = urljoin(url, href)
            title = (anchor.get_text() or href.rsplit("/", 1)[-1]).strip()
            yield ScrapedEntry(
                source_key=self.source_key,
                pdf_url=pdf_url,
                title=title[:1024],
            )

    # -- helpers ------------------------------------------------------
    def _iter_listing_urls(self) -> Iterator[str]:
        for path in self.listing_paths:
            yield self._absolute(path)

    def _absolute(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return urljoin(self.base_url, path)

    def _http_get_text(self, url: str) -> str:
        self._throttle()
        logger.debug("[%s] GET %s", self.source_key, url)
        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    def _http_get_bytes(self, url: str) -> bytes:
        self._throttle()
        logger.debug("[%s] GET(bytes) %s", self.source_key, url)
        response = self._client.get(url)
        response.raise_for_status()
        return response.content

    def _throttle(self) -> None:
        if self.request_delay_seconds > 0:
            time.sleep(self.request_delay_seconds)
