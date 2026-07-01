- **Defined-term extraction: cap on unique terms, not raw regex hits.**
  `ReferenceExtractor._terms` (`opencontractserver/enrichment/extractor.py`) capped on
  every regex hit (including duplicates skipped via `slug in seen`), so a document with
  many repeated early definition sites (e.g. 50× `(the "Company")`) exhausted the
  `MAX_DEFINED_TERMS` budget before later *distinct* terms were reached — silent
  under-extraction. The cap is now on `emitted` (unique) terms; a separate, larger
  `MAX_DEFINED_TERM_SCAN` (`= DEFINED_TERM_SCAN_MULTIPLIER * MAX_DEFINED_TERMS`, in
  `opencontractserver/enrichment/constants.py`) bounds total hits inspected so a
  duplicate-heavy document still terminates. This also removed an unreachable
  `emitted >= MAX_DEFINED_TERMS` branch in the old `or` guard. Dead constants
  `_TERM_PAREN_RE`/`_TERM_MEANS_RE` (superseded by the combined `_TERM_RE`) were deleted.
  Regression coverage: `test_defined_term_cap_counts_unique_terms_not_raw_hits`
  (`opencontractserver/tests/test_enrichment_extractor.py`) reproduces the exact
  duplicate-then-distinct scenario that was previously broken, and
  `ReferenceTypeFilterTests` (`opencontractserver/tests/test_generic_grammars.py`)
  covers the `GenericCitationExtractor.extract(reference_types=...)` gate.
