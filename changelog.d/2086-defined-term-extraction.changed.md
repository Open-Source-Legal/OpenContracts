- **Reference extraction is gated by requested `reference_types`.**
  `ReferenceExtractor.extract()` (`opencontractserver/enrichment/extractor.py`) and
  `GenericCitationExtractor.extract()` (`opencontractserver/enrichment/grammars.py`) now
  accept a `reference_types` argument and skip grammar passes whose output type is not
  requested. Because every generic grammar pass emits `REF_LAW` candidates, an apply/scan
  for only `REF_DEFINED_TERM` no longer runs all nine grammar passes wastefully — the
  enrichment service (`enrichment_service.py`) passes the wanted set through to
  `generic.extract(...)`.
