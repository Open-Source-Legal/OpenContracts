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

We do **not** version annotations or relationships, and we do not try to
re-anchor human annotations automatically across amended text. What we do
is make their state visible: after a version-up, every human annotation on
the previous version is **stale** until a person **re-approves** it,
**corrects** it, or **drops** it on the new version (change 5).

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
`link_url` carries the version's slug with no `?v=`. Without a version,
`slug_queries.py::_resolve_document_in_corpus_by_slugs` requires
`path_records__is_current=True`, so a superseded slug resolves to nothing.
The resolver, the `documentInCorpusBySlugs(versionNumber:)` argument and the
frontend `?v=` route param already handle versioned lookups end to end; the
only missing piece is that nothing writes `?v=N` into `link_url`
(`utils/frontend_paths.py::document_in_corpus_path` has no version
parameter). `_restamp_mention_links` repairs the slug only when G2 lets
relink run.

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

## Design — five changes

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

### 5. Human annotations: surface stale vs. re-approved vs. corrected

Annotations stay pinned to the version they were drawn on. We add **one
small decision table** and derive everything else:

```
AnnotationVersionDecision
  annotation        FK Annotation   (the one on the OLD version)
  target_document   FK Document     (the NEW version it was reviewed against)
  decision          REAPPROVED | CORRECTED | DROPPED
  successor         FK Annotation, null   (the row on the new version, if any)
  creator, created
  unique (annotation, target_document)
```

States, derived per human (non-structural) annotation on `current.parent`:

| State | Meaning |
|---|---|
| **stale** | no decision row targeting the current version |
| **re-approved** | decision `REAPPROVED`; successor has the same `raw_text` and label |
| **corrected** | decision `CORRECTED`; successor differs in text, bounds or label |
| **dropped** | decision `DROPPED`; reviewer said it no longer applies |

Only the parent hop is reviewed (v1→v2, then v2→v3 reviews v2's rows
including successors). That keeps the stale set bounded and each hop
auditable; there is no transitive lineage to maintain.

Workflow, in one service (`AnnotationVersionReviewService`):

- `pending(document, corpus)` — human annotations on `document.parent`
  with no decision for `document`, each with a **proposed placement**:
  exact `raw_text` match in the new version's `txt_extract_file`, projected
  onto PDF tokens via `opencontractserver/utils/span_projection.py` (the
  same helper the enrichment writer uses). Plain-text authority sections
  match almost always; PDFs fall back to manual placement.
- `carry_forward(annotation, target_document, placement)` — creates the
  successor as an ordinary annotation on the new version and writes the
  decision. `REAPPROVED` if text and label are unchanged from the proposal,
  else `CORRECTED`. The successor is a normal row: no annotation versioning.
- `drop(annotation, target_document)` — decision only.

GraphQL: one query `annotationVersionReview(documentId, corpusId)` returning
`{annotation, state, proposedPlacement, successor}` rows, two mutations
(`carryForwardAnnotation`, `dropStaleAnnotation`), and
`DocumentType.staleAnnotationCount(corpusId)` so the existing version badge
can show "3 stale". `AnnotationType.versionState` exposes the same enum on
an old version's page so each annotation there wears its chip.

This is the one schema change in the plan: one table, one migration,
nothing on `Annotation` itself.

### Frontend (small)

`DocumentReferencesPanel`: query the two new fields; on an inbound/outbound
row where `targetIsSuperseded`, render a quiet "cited v1 · current v3" badge
whose second half links to `currentTargetDocument`. No new state, no new
routes.

Version badge: append the stale count when non-zero. Document page: a
"Carried-over annotations" panel on the current version listing
`pending()` rows with **Approve** (accept proposal), **Place** (manual, then
saves as corrected), and **Drop**; on an older version each human
annotation shows its state chip.

## Not in scope (deliberately)

- **Automatic re-anchoring of human annotations.** Offsets shift; deciding
  that an annotation still holds on amended text is a human call. Change 5
  proposes a placement by exact text match and records the decision; it
  never moves or silently copies an annotation. `Relationship`s between
  human annotations follow the same rule: re-created by the reviewer on the
  new version, never migrated.
- **Storing a "tracks current law" mode per reference.** Change 1 + the
  derived field give both answers from one row; a stored mode would be a
  second source of truth.
- **Schema changes beyond the decision table.** Changes 1–4 need none;
  `version_tree_id` and `canonical_key` already exist and are indexed.

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
6. `test_annotation_version_review.py` (new) — after `import_document`
   version-up: every human annotation on v1 is `stale` and structural ones
   are excluded; `pending()` proposes an exact-text placement for a plain
   text authority and `None` when the text was removed; `carry_forward`
   with the proposal yields `REAPPROVED`, with an edited span or label
   yields `CORRECTED`; `drop` yields `DROPPED`; a v3 version-up reviews v2's
   successors, not v1's rows; the unique constraint rejects a second
   decision for the same pair; permission: reviewer needs UPDATE on the
   document.
7. Playwright CT — References panel renders the superseded badge and both
   links; the carried-over panel renders stale rows with Approve / Place /
   Drop and the version badge shows the stale count.

## Size

Changes 1–4: backend ≈ 150–250 LOC across `enrichment_service.py`,
`corpus_reference_service.py`, `relationships.py`, `writer.py`,
`frontend_paths.py`, `versioning.py`, two GraphQL types; frontend ≈ 60 LOC;
no migration. Change 5: one model + migration, one service, one query, two
mutations, ≈ 250 LOC backend plus the review panel. Ship as two PRs: links
(1–4) first, annotation review (5) second.
