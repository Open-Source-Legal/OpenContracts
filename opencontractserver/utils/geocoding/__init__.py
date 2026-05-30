"""Offline geocoding utilities — issue #1819.

Pure-Python place resolution from a bundled reference dataset (ISO 3166-1
countries, US states, curated GeoNames city subset). No network at parse
time: same input → same coordinates forever.

Public surface::

    from opencontractserver.utils.geocoding import ResolvedPlace, resolve_place

See ``service.py`` for the resolver contract and ``data/`` for the bundled
reference data (regeneration instructions live in
``docs/credits/geonames.md``).
"""

from opencontractserver.utils.geocoding.service import (
    ResolvedPlace,
    resolve_place,
)

__all__ = ["ResolvedPlace", "resolve_place"]
