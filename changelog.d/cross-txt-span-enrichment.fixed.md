- **Customs-ruling enrichment produced zero output for the official CROSS TXT
  bulk export** (10,000-document run: 0 HTS annotations, 0 citation mentions,
  0 references, 0 graph edges — see
  `docs/benchmarks/pr2153-cross-txt-enrichment-handoff.md`). Root cause was a
  format gate in
  `opencontractserver/enrichment/services/customs_ruling_citation_service.py::enrich_corpus`
  that skipped every non-PDF document before either detection regex ran, even
  though `text/plain` documents are a fully supported span-anchored
  representation. Anchoring type is now an input to persistence, not an
  eligibility gate: PDF documents keep TOKEN annotations (unchanged branch),
  TXT documents get `SPAN_LABEL` annotations in the canonical
  `{start, end, text}` / `page=0` shape (`_write_hts_annotations` span branch;
  citations via `EnrichmentWriter`'s existing span fallback).
- **`EnrichmentWriter` span-fallback mentions advertised a nonexistent PDF
  page** (`opencontractserver/enrichment/writer.py::_get_or_create_mention`):
  the fallback wrote `page=1` and omitted the anchored text, while the
  canonical text-anchor path (`opencontractserver/utils/annotation_anchoring.py::_anchor_text`)
  uses `page=0` (suppressed by the frontend) and includes `text`. The fallback
  now matches the canonical shape, re-running enrichment heals pre-fix span
  rows in place (same row, FKs survive — mirroring the span→token backfill),
  and the shape itself is now built in one place
  (`opencontractserver/utils/span_projection.py::span_annotation_payload` +
  the `SPAN_NO_PAGE` sentinel in `opencontractserver/constants/annotations.py`)
  instead of three hand-written copies.
- **Ruling-citation resolution keyed on display titles**, which the official
  exporter fills with human-readable subjects (non-unique, control-character
  laden) — so citations could never resolve, and title collisions silently
  resolved to the last-indexed document. Canonical identity is now derived per
  document from `DocumentPath.external_id` (`cross:` namespace) → active
  corpus-path basename stem → title stem fallback
  (`CustomsRulingCitationService._build_ruling_identity_index`), and ambiguous
  identities are reported (`canonical_id_collisions` + warning) and left
  unresolved instead of being silently overwritten.
- **HTS dedupe missed importer sidecar rows**: it filtered only the TOKEN-typed
  label row and only `data.char_span.start`, while imported producer spans
  carry the offset in `json.start` on a TOKEN-typed label. Dedupe now matches
  by label text across both representations, so enrichment never paints a
  duplicate highlight over official-export sidecar annotations (which are
  retained untouched as source evidence). HTS rows also now record the run's
  `Analysis` (provenance parity with citation mentions).
- Regression coverage: `opencontractserver/tests/test_customs_ruling_enrichment.py`
  (two-document TXT corpus, PDF-branch preservation, path identity + collisions,
  sidecar reconciliation, rerun idempotency, and an official-export-shaped
  ZIP → `zip-to-corpus` import → enrichment contract test).
