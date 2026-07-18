- Document-identifier citations now resolve through **durable identity**, not
  display titles: per-document canonical identifiers derive from
  `DocumentPath.external_id` (`cross:` namespace, case-insensitive) → active
  corpus-path basename stem → title stem, shared by the resolver's index, its
  self-mention drop, and the grammar's corpus-shape gate
  (`opencontractserver/enrichment/resolver.py::document_identity_candidates`,
  threaded through `EnrichmentService._build_detection`). The official CROSS
  export titles documents with human-readable SUBJECTS, so the previous
  title-only index left every citation into such corpora unresolvable and the
  grammar gate closed. Ambiguous identities (two documents claiming one
  number) are reported and left unresolved instead of resolved to whichever
  document claimed the index slot first.
- New series-token legacy citation grammar
  (`constants.LEGACY_DOC_IDENTIFIER_CITE_RE`): legacy CBP rulings have BARE
  zero-padded numeric ruling numbers cited as "HRL 087392" / "HQ 084665" —
  invisible to the prefixed shape. Measured on a 500-document official-export
  slice: 707 instances, no false positives (six digits required — 5 digits
  after "NY" is a ZIP code in 148/149 sampled instances; bare numbers without
  a series token are still never mined). Identifier citations and identities
  meet on one canonical key (`constants.canonical_document_identifier`:
  prefixed verbatim, bare digits zero-stripped). On the real 10K
  official-export benchmark this recovers 9,377 citation candidates and
  5,007 resolved graph edges that the prefixed-only grammar missed entirely.
- ZIP import metadata (`meta.csv`) accepts an optional `external_id` column
  (`opencontractserver/utils/metadata_file_parser.py`), stored verbatim on
  `DocumentPath.external_id` by `import_zip_with_folder_structure` (new
  `external_ids_applied` counter; values beyond the 512-char field limit are
  rejected per-row with a warning, never truncated).
- `EnrichmentWriter` span fallback emits the canonical text-span shape —
  `page=0` no-page sentinel (`constants/annotations.py::SPAN_NO_PAGE`) plus
  anchored `text`, built once in
  `opencontractserver/utils/span_projection.py::span_annotation_payload` —
  and re-applying enrichment heals pre-fix `page=1`/text-less span mentions
  in place.
