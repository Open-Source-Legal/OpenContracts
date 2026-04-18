"""Scrapers for Bolivian legal sources.

This package hosts one scraper per public source (Gaceta Oficial, TSJ,
TCP). Every scraper subclasses :class:`base.BaseScraper` and yields
normalized :class:`base.ScrapedEntry` objects that the ingestion layer
turns into ``BolivianLegalDocument`` records + ``Document`` uploads.
"""

from opencontractserver.bolivian_laws.scrapers.base import (
    BaseScraper,
    ScrapedEntry,
)
from opencontractserver.bolivian_laws.scrapers.registry import (
    SCRAPERS,
    get_scraper_class,
    iter_scraper_classes,
)

__all__ = [
    "BaseScraper",
    "ScrapedEntry",
    "SCRAPERS",
    "get_scraper_class",
    "iter_scraper_classes",
]
