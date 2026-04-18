"""Registry of scrapers, keyed by :class:`LegalSource` value.

The tasks and management commands use this registry to iterate all
sources or look up one by its short key (``gaceta``, ``tsj``, ``tcp``).
"""

from __future__ import annotations

from collections.abc import Iterator

from opencontractserver.bolivian_laws.constants import LegalSource
from opencontractserver.bolivian_laws.scrapers.base import BaseScraper
from opencontractserver.bolivian_laws.scrapers.gaceta import GacetaOficialScraper
from opencontractserver.bolivian_laws.scrapers.tcp import (
    TribunalConstitucionalScraper,
)
from opencontractserver.bolivian_laws.scrapers.tsj import (
    TribunalSupremoJusticiaScraper,
)

SCRAPERS: dict[str, type[BaseScraper]] = {
    LegalSource.GACETA.value: GacetaOficialScraper,
    LegalSource.TSJ.value: TribunalSupremoJusticiaScraper,
    LegalSource.TCP.value: TribunalConstitucionalScraper,
}


def get_scraper_class(source_key: str) -> type[BaseScraper]:
    try:
        return SCRAPERS[source_key]
    except KeyError as exc:
        raise KeyError(
            f"Unknown scraper source_key={source_key!r}. "
            f"Valid keys: {sorted(SCRAPERS)}"
        ) from exc


def iter_scraper_classes() -> Iterator[type[BaseScraper]]:
    return iter(SCRAPERS.values())
