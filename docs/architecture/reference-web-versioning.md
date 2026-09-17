# Reference Web × Document Versioning — Design

> Status: **proposed** (2026-09-17). Supersedes the 2026-06-10 "known gap"
> note that lived here; the code has moved since (relink now re-points
> resolved refs) and this document reflects the code as it stands on `main`.

## TL;DR

Every link table stores a `Document.pk`, and a `Document` row **is a
version**. The stable things people actually mean when they link are the
*logical document* (`Document.version_tree_id`) and, for law, the
*authority* (`custom_meta.canonical_key`). Nothing today says which of the
two a link means, so version-ups either silently rewrite history
(authority updated) or silently leak it (citing document updated).

The fix is one invariant, no new tables, no migration:

> **Links are pinned to the version they were made against. That pinned
> row *is* the history. "Current" is derived at read time through the
> version tree. Derived rows are re-derived; user-authored document-level
> rows are carried forward.**

We do **not** version annotations or relationships. Re-anchoring spans
across amended text is a separate, hard problem and is explicitly out of
scope (see *Not in scope*).

## Ground truth (what exists)

| Concept | Stable identity | Where it is pinned to a version today |
|---|---|---|
| Logical document | `Document.version_tree_id`; current = `is_current=True` + active `DocumentPath` | — |
| Authority | `custom_meta.canonical_key`; resolved by `enrichment/authorities.py::find_authority_target` (`path_records__is_current=True`) | — |
| Authority → authority edge | `AuthorityRelationship(source_key, target_key)` — key-based, already version-independent (pinned by `test_authority_ingestion_invariants.py::test_relationship_identity_survives_document_version_and_deletion`) | never |
| Citation (mention → target) | `CorpusReference.canonical_key` | `source_annotation` (→ citing version), `target_document`, `target_annotation` |
| Doc → doc edge | — | `DocumentRelationship.source_document` / `target_document` |
| Within-doc section link | — | `Relationship.document` + annotation M2Ms |
| Clickable mention | — | `Annotation.link_url` = `/d/{creator}/{corpus}/{doc_slug}`; **slug is per version** (`Document.save` mints `title-2` for v2) |

Version-up path: `AuthorityCorpusBootstrapper.bootstrap` →
`create_or_update_text_document` → `documents/versioning.py::import_document`
(`status="updated"`): new `Document` row, same `version_tree_id`, old row
`is_current=False`, old `DocumentPath` `is_current=False`, new path
`version_number+1`. Nothing about annotations, relationships, or references
is touched.

## Gaps (verified against `main`)

**G1 — Authority version-up rewrites history.**
`EnrichmentService._link_external` overwrites `target_document` /
`target_corpus` in place whenever `find_authority_target` returns a
different row. After DGCL §145 is re-ingested there is no record that a
2019 contract's citation ever resolved to the 2019 text.
`target_annotation` is *not* rewritten, so it can point into the superseded
version while `target_document` points at the new one.

**G2 — …but usually it doesn't even run.**
`relink_corpora_for_keys` (the hook `bootstrap_authority_corpus`,
`AuthorityPackService._relink_installed`, and the discovery crawl fire after
an ingest) pre-filters to corpora holding **`STATUS_EXTERNAL`** refs for the
keys. A corpus whose refs to that key are all already `RESOLVED` is never
selected. Net effect today: after an authority update, some corpora track
the new text, most keep pointing at the old row — nondeterministic from the
user's point of view.

**G3 — Old mention links 404.**
`link_url` carries the version's slug with no `?v=`. Once that version is
superseded, `slug_queries.py::_resolve_document_in_corpus_by_slugs` requires
`path_records__is_current=True` and returns nothing. `_restamp_mention_links`
repairs this only when G2 lets relink run.

**G4 — Citing-document version-up leaks history into current views.**
Re-uploading a contract creates v2; enrichment (CorpusAction or a manual
run) writes fresh mentions + `CorpusReference` rows against v2, and v1's rows
stay — which is correct as *history*. But nothing filters them out of
current views: `CorpusReferenceService` gates on
`Document.objects.visible_to_user`, which does not exclude superseded
versions (every corpus-scoped query in `corpus_queries.py` adds
`path_records__is_current=True` on top for exactly this reason). So the
authority's References panel, `DocumentType.inboundReferences`,
`CorpusType.inboundReferences` and `corpusReferences(documentId=…)` show the
same citation twice (v1 and v2) — and keep showing citations from documents
the user soft-deleted from the corpus.
`DocumentRelationshipService` has the same hole, and
`writer.py::_reconcile_document_graph` projects doc→doc edges from *all*
`REF_DOCUMENT` rows in the corpus, so superseded versions become ghost nodes
in the governance graph.

**G5 — User-authored doc→doc links do not follow the document.**
A hand-made `DocumentRelationship` (RELATIONSHIP or NOTES) between A and B
stays on A-v1 after A is re-uploaded. The current A appears to have lost its
relationships.

Not a gap, worth stating: `Relationship` (within-document section links) and
structural annotations are version-specific derived artefacts and are
correctly re-derived on the new version. `AuthorityRelationship` is already
right.

## Design — four changes

### 1. `CorpusReference.target_*` is write-once: "as cited"

`_link_external` becomes a promote/demote pass only:

- `EXTERNAL → RESOLVED`: set `target_document` / `target_corpus` /
  `target_annotation` once, to the version current *at that moment*.
- Already `RESOLVED`: keep the pinned FKs if the key still resolves to a
  document in the **same `version_tree_id`**. Re-point only if the key moved
  to a different tree (pack rebuilt under a new document); demote to
  `EXTERNAL` only if the key no longer resolves for the corpus's audience.
- Never touch `target_annotation` on its own.

History is now the row you already have. G1 closed. G2 becomes moot for
version-ups (relink is only needed when a *new* authority lands, which is
exactly what the `EXTERNAL` pre-filter already targets) — leave the trigger
alone.

"Current law" is a derived read, not a stored pointer. Add to
`CorpusReferenceService` one helper and to `CorpusReferenceType` two fields:

- `currentTargetDocument: DocumentType` — `Document` with
  `version_tree_id = target_document.version_tree_id`, `is_current=True`,
  active path in `target_corpus`, visible to the caller (reuse
  `resolve_visible_fk` semantics; one extra `select_related`/prefetch on
  the connection, no per-row query).
- `targetIsSuperseded: Boolean` — `target_document.is_current == False`.

### 2. Mention links are permanent links

`utils/frontend_paths.py::document_in_corpus_path` gains
`version_number: int | None`, emitting `?v=N` (the frontend
`CentralRouteManager` already reads `?v=` and the slug resolver already
drops the `is_current` constraint when a version is given).
`_restamp_mention_links` stamps the pinned version's number (from the
`DocumentPath` rows `_link_external` already fetches). A pinned URL never
goes stale, so the restamp pass only has work on a status change, and the
existing orange "older version" badge on the document page is the
"newer text exists" affordance for free. G3 closed.

The product decision the old note asked for is thereby made: **a citation
opens the text as it stood when cited; the current text is one click away.**
That is the correct legal default and it is also the cheapest one.

### 3. Current views exclude superseded sources by default

Add one `Q` to `CorpusReferenceService._source_visible_q`: the source
annotation's document must have an active `DocumentPath`
(`is_current=True, is_deleted=False`) in the reference's `corpus`. Expose it
as `include_historical: bool = False` on the service methods and an
`includeHistorical: Boolean = false` argument on `corpusReferences` /
`inboundReferences` — the history stays one flag away, and the References
panel can offer a "show superseded versions" toggle later without a
backend change.

Apply the same active-path filter in
`DocumentRelationshipService._get_visible_document_ids` and restrict the
`expected` set in `writer.py::_reconcile_document_graph` to sources with an
active path, so the governance graph and its projection agree with the
References panel. (The projection is derived; pruning a superseded
version's edges loses nothing — the `CorpusReference` rows remain.) G4
closed.

### 4. Carry user-authored `DocumentRelationship` rows forward

In `import_document`'s `updated` branch, after `new_doc` exists: for every
`DocumentRelationship` where `source_document` or `target_document` is
`old_doc` **and** `data` has no `analysis_id` (i.e. not enrichment-owned),
create the same row against `new_doc`. The old row stays (history); the
unique constraint is satisfied because `new_doc` is a new pk. One helper in
`documents/versioning.py`, ~15 lines. Enrichment-owned rows are not copied —
they are re-derived by the next run (change 3 already keeps the projection
honest). G5 closed.

### Frontend (small)

`DocumentReferencesPanel`: query the two new fields; on an inbound/outbound
row where `targetIsSuperseded`, render a quiet "cited v1 · current v3" badge
whose second half links to `currentTargetDocument`. No new state, no new
routes.

## Not in scope (deliberately)

- **Re-anchoring human annotations / `Relationship`s across amended text.**
  Offsets shift; this is the general annotation-versioning problem. If it is
  ever wanted for authorities specifically, the cheap first cut is exact
  `raw_text` match on the new version's `txt_extract_file` — plain-text
  sections make that unusually tractable — but it is a separate change.
- **Storing a "tracks current law" mode per reference.** Change 1 + the
  derived field give both answers from one row; a stored mode would be a
  second source of truth.
- **Schema changes.** None are needed. `version_tree_id` and
  `canonical_key` already exist and are indexed.

## Tests (unit + isolated integration, all backend unless noted)

1. `test_enrichment_linking.py` — bootstrap DGCL v1, enrich a filing corpus,
   assert `RESOLVED` → v1 with `link_url` ending `?v=1`; bootstrap v2 with
   changed text; assert `target_document` still v1, `currentTargetDocument`
   is v2, `targetIsSuperseded` true, `link_url` unchanged and still resolves
   through `resolveDocumentInCorpus(versionNumber=1)`. Same test, key moved
   to a different tree → re-pointed; key gone → demoted.
2. `test_corpus_reference_service.py` (new) — citing doc re-uploaded and
   re-enriched: default query returns only v2 sources; `include_historical`
   returns both; soft-deleted source documents excluded by default.
3. `test_document_versioning.py` — `import_document(updated)` carries
   user-authored `DocumentRelationship` rows forward (both directions,
   RELATIONSHIP and NOTES), skips enrichment-owned rows, preserves the old
   rows.
4. `test_enrichment_writer.py` — `_reconcile_document_graph` ignores
   superseded sources; governance graph query has no ghost node after a
   re-upload.
5. `test_schema_parity.py` — regenerate `schema.graphql` for the two fields
   and one argument.
6. Playwright CT — References panel renders the superseded badge and both
   links from a mocked `corpusReferences` payload.

## Size

Backend ≈ 150–250 LOC across `enrichment_service.py`,
`corpus_reference_service.py`, `relationships.py`, `writer.py`,
`frontend_paths.py`, `versioning.py`, two GraphQL types; frontend ≈ 60 LOC.
No migration. One PR, or two if the frontend badge is split out.
