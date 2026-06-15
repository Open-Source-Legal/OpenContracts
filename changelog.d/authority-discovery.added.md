- Added open-vocabulary authority detection (Tier-2a): generic citation-shape
  grammars (`opencontractserver/enrichment/grammars.py`) now recognise US Code,
  CFR, Federal Register, Public Law, state, and municipal citations plus named
  Acts outside the built-in registry, classified by jurisdiction/authority type.
  New `discover_authorities` agent tool and `EnrichmentService.discover()`
  surface them; the trusted registry tier wins on overlap so existing behaviour
  is unchanged.
