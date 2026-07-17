- Customs enrichment mines series-token legacy citations — `"HQ 084665"`,
  `"HRL 087392"`, `"NY 812345"` (`_LEGACY_RULING_CITE_RE` in
  `opencontractserver/enrichment/services/customs_ruling_citation_service.py`).
  The official export's legacy HQ/NY slice has BARE zero-padded numeric ruling
  numbers, so the prefixed-only grammar captured zero citations there
  (measured: 707 token+number citation instances per 500 documents, no false
  positives; exactly six digits required because 5 digits after "NY" is a ZIP
  code in 148/149 sampled instances). Bare numbers without a series token are
  still never mined. Identity and citations meet on one canonical key
  (`_canonical_ruling_key`: prefixed verbatim; bare digits with leading zeros
  stripped), so a zero-padded path identity (`HQ/084665.txt`) resolves however
  a citation pads it. Live on the 10K benchmark slice (500-doc subset): 163
  citation candidates and 39 resolved graph edges, up from ~1 candidate and 0.
