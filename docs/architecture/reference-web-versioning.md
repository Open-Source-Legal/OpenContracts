# Reference Web × Document Versioning — Known Gap (design note, not yet scheduled)

> Status: **acknowledged, deliberately deferred** (2026-06-10). Not an issue
> yet by choice — this note is the durable record of the gap so it isn't
> rediscovered the hard way.

## The scenario

An authority section (e.g. `dgcl:145`) is re-ingested with amended text. The
bootstrapper (`AuthorityCorpusBootstrapper.bootstrap`) version-ups the
document via `create_or_update_text_document` → `import_document`: a **new
`Document` row** becomes the current version at the path; the old row's path
record flips `is_current=False`.

## What stays correct

- **Future resolution**: `find_authority_target` filters
  `path_records__is_current=True`, so any *subsequent* `apply()` /
  `link_external_references` pass targets the new version.
- **Derived annotations on the statute text** (self-citation mentions): the
  enrichment model is *deterministic re-derivation* — if the authority corpus
  has the reference-enrichment CorpusAction installed, importing the new
  version triggers a re-run and the new version gets fresh mentions. Old
  versions keep their old mentions (annotations belong to a Document row and
  never migrate).

## What goes stale

1. **Already-RESOLVED `CorpusReference` rows are never re-pointed.**
   `EnrichmentService.link_external_references` only processes rows with
   `target_document__isnull=True`, so existing references keep pointing at
   the superseded Document. Consequences:
   - The governance graph renders the old node (same title, old pk).
   - Mention `link_url`s keep the old version's slug — clicks land on the
     text *as it stood when cited*. Stale-but-not-broken; for legal work
     "pinned to the cited version" may even be the right default, but it is
     currently an accident, not a decision.
2. **Human annotations on statute text don't survive amendment.** Span
   offsets shift with the text; there is no re-anchoring machinery. This is
   the general (and genuinely hard) annotation-versioning problem — out of
   scope for the reference web.

## The bounded fix (when scheduled)

- Add a `refresh=True` mode to `link_external_references` that re-runs
  `find_authority_target` over **all** LAW refs (not just unresolved),
  re-points `target_document`/`target_corpus` to the current version, and
  rewrites mention `link_url`s. Idempotent, two `bulk_update`s, same shape as
  the existing pass.
- Make the pinning semantics a **product decision** surfaced in the UI:
  "tracks current law" (refresh) vs "pinned to version as cited" (today's
  accidental behaviour) — possibly per-reference via the version-aware
  `?version=` route param the frontend already supports.
- Optional integrity sweep: a periodic check flagging RESOLVED refs whose
  target document is no longer `is_current` (cheap query;
  `target_document__path_records__is_current=False`).

## Related

- Authority ingestion source plan: prefer OLRC USLM XML (US Code) and the
  eCFR REST API over scraping — public domain, section-pre-structured, and
  the USLM identifiers also solve the USC→act-section mapping gap.
