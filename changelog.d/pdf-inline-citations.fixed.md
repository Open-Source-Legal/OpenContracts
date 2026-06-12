- **Inline citations now render on PDF documents.** The enrichment writer
  (`opencontractserver/enrichment/writer.py`) projected nothing visible on
  PDFs: it stored every reference mention as a `SPAN_LABEL` char-offset
  annotation, which the PDF viewer (token-indexed PAWLs renderer) cannot
  paint — citations showed in the References panel but never inline on the
  filings themselves. Mentions on PDF documents are now projected onto PAWLs
  token bounding boxes via PlasmaPDF (`TOKEN_LABEL`, real page numbers
  instead of the hardcoded `page=1`), with the char span preserved in
  `data.char_span` for dedupe. Projection handles real-ingest drift between
  `txt_extract_file` and the PAWLs text via whitespace-insensitive
  ordinal-occurrence remapping (covers hard line-wraps and see-quoted SECTION
  refs whose raw text extends left of the span start) and falls back to the
  span representation when the mention text genuinely is not in the PAWLs
  text. Re-running enrichment upgrades pre-fix span mentions **in place**
  (same row — `CorpusReference`/`Relationship` FKs survive), so a corpus
  re-enrich is also the backfill.
- **Shared span→token projection utility.** The format-aware document-text
  loader and the PlasmaPDF span projection moved from private helpers in
  `opencontractserver/utils/extraction_grounding.py` to
  `opencontractserver/utils/span_projection.py`
  (`load_document_text_and_layer`, `project_span_to_token_annotation`);
  datacell grounding and the enrichment writer now share one implementation.
- **Reference-mention merge fixed and made usable.**
  `useReferenceMentions` (frontend): (1) the analyses discovery query used
  `analyses(corpusId:)` — an argument that does not exist in the schema and
  was silently ignored (see validation gap below), so the hook swept every
  enrichment analysis platform-wide; it now uses the real
  `analyzedCorpusId` filter. (2) The per-analysis fetch used a `useLazyQuery`
  handle re-executed in a loop, whose promise was observed never settling —
  replaced with `client.query`. (3) The fetch now uses a lean
  `GET_REFERENCE_MENTIONS_FOR_ANALYSIS` selection: the previous full
  selection (per-annotation userFeedback / relationships / document / corpus)
  measured **~176s** server-side for 108 mentions vs ~0s for the lean one.
  Net effect: inline cites appear within seconds of opening a PDF.
- **Known issues surfaced during this work (deliberately NOT fixed here):**
  (1) `GraphQLView(validation_rules=[DepthLimit…])` REPLACES graphql-core's
  spec rule set, so standard GraphQL validation (unknown arguments/fields,
  variable types) is disabled on the served endpoint; ~34 shipped frontend
  documents currently fail spec validation (`scripts/validate_frontend_graphql.py`
  enumerates them) — restoring `[*specified_rules, …]` must land with those
  query fixes (documented in `config/graphql/schema.py`). (2) Presigned file
  URLs are cached for `FILE_URL_SHARED_CACHE_TTL=21600`s while
  `AWS_QUERYSTRING_EXPIRE` defaults to 3600s — cached links 403 for hours.
  (3) `Document.update_summary`'s docstring claims it updates
  `md_summary_file` but it only writes a revision, so intelligence-panel
  summary coverage stays 0%. (4) `add_document`-triggered agent actions
  re-fire on agent-authored document writes (runaway agent loop / unbounded
  LLM spend).
