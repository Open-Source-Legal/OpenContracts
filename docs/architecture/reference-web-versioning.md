# Reference Web and Document Versioning

Implemented from the design in PR #2389. A `Document` row is one immutable
version; `version_tree_id` identifies the logical document.

**Citations preserve the text originally cited. Current text is derived from
the version tree. Human annotations require an explicit review before a new
annotation is created on the next version.**

## Citations: original and current text

`CorpusReference.target_document`, `target_corpus`, and `target_annotation`
identify the original target. The enrichment link pass preserves these FKs
when a canonical key still resolves within the same version tree. It replaces
them if the key resolves to a different tree, and clears them together if the
key is no longer available to the corpus audience. Replacing the document also
clears its old target annotation.

`CorpusReferenceType` exposes both views:

| Field | Meaning |
|---|---|
| `targetDocument` | Pinned document version |
| `targetVersionNumber` | Pinned version number in the target corpus |
| `targetIsSuperseded` | Whether that document has been superseded |
| `currentTargetDocument` | Visible current document in the same tree and corpus, or null |
| `currentTargetVersionNumber` | Its version number, or null |

Current-target and version-number lookups are batched per source corpus and
request. Both the current document and its active corpus path must be visible.
An inaccessible newer version exposes no document ID or version number.

Mention links use `/d/{creator}/{corpus}/{document-slug}?v=N`. The existing
`CentralRouteManager` and `documentInCorpusBySlugs(versionNumber:)` route
support handles these pinned URLs. The version selector changes the document
slug as well as the version parameter when switching versions. The References
panel offers separate **Cited vN** and **Current vN** links.

Migration `annotations/0106` repairs existing resolved mention URLs in batches.
This matters for corpora containing only resolved references: the external-key
relink trigger does not revisit them after an authority update. That trigger
can remain unchanged because current targets are derived at read time.

## Current and historical relationships

`CorpusReferenceService` defaults to sources with an active, non-deleted
`DocumentPath` in the reference's own corpus. Shared structural sources are
matched through their structural annotation set. References from superseded
or removed source documents remain stored as history.

`corpusReferences` and the `inboundReferences` fields accept
`includeHistorical: Boolean = false`. The References panel exposes this as
**Show superseded versions**. Inbound references to the current document
include citations pinned to an older version of the same tree.

`DocumentRelationshipService` likewise requires both endpoints to have active
paths in the relationship's corpus. Explicit historical document views load
historical annotations and relationships, including the original annotation
endpoints. Permission and analysis/extract privacy checks still apply.

On `import_document(..., status="updated")`, handwritten `DocumentRelationship`
rows are copied in both directions to the new document. The other endpoint
must still be active in that corpus, so updating A, then B, then A again does
not revive earlier combinations of endpoints. The original rows remain.
Rows whose `data` contains `analysis_id` belong to enrichment and are skipped.

The enrichment graph projection uses current source paths and resolves pinned
targets to active documents within the same tree. Reconciliation removes old
derived edges without removing their historical `CorpusReference` evidence
or handwritten relationships. `AuthorityRelationship` already uses canonical
keys and needs no version migration.

## Human annotation review

`AnnotationVersionDecision` records one decision for an old annotation against
its immediately following document version:

| Field | Purpose |
|---|---|
| `annotation` | Original annotation, unchanged |
| `target_document` | Next version being reviewed |
| `decision` | `REAPPROVED`, `CORRECTED`, or `DROPPED` |
| `successor` | Ordinary annotation on the new document, nullable |
| `creator`, `created` | Reviewer and review time |

A database constraint makes `(annotation, target_document)` unique. Transactions
lock the source annotation and target document; repeated decisions cannot
leave duplicate successors. A missing decision is the derived state `STALE`.

`AnnotationVersionReviewService` reviews human rows on `document.parent` in the
selected corpus. Structural, analysis, extract, corpus-action, and grounding
annotations are excluded. A v3 upload reviews v2's annotations, including
successors created by v1-to-v2 review; it does not resurrect v1's stale rows.

An exact, unique text match proposes a placement. TXT offsets and PDF tokens
use the shared `span_projection` helpers. Missing or repeated text needs
manual placement. Document-level labels need approval but no spatial placement.
Nothing is copied just because a proposal exists.

- **Approve** creates a successor from the server's recomputed proposal.
- **Place** uses the normal viewer selection workflow. The server rebuilds the
  text and bounds from the new document's offsets or tokens, disregarding
  client-supplied text and bounding boxes. A changed placement or label records
  `CORRECTED`; accepting the unchanged proposal records `REAPPROVED`.
- **Drop** records the review without creating a successor.

The reviewer needs UPDATE on both the target document and corpus, and READ on
the source evidence. Decisions target only the active, immediately following
version. Label changes must use a compatible label from the corpus label set.

GraphQL provides `annotationVersionReview(documentId, corpusId)`,
`carryForwardAnnotation`, and `dropStaleAnnotation`. Each review row includes
the original annotation, state, proposal, successor, reviewer, and review time.
`DocumentType.staleAnnotationCount(corpusId)` supplies the header's stale count;
`AnnotationType.versionState` describes an old annotation's next-version review.

The **Carried-over annotations** panel supports review on desktop and mobile.
Approving, placing, or dropping refreshes the list and stale count. A rejected
placement stays pending and does not appear as a saved annotation. Read-only
viewers can inspect decisions but cannot make them.

Within-document `Relationship` rows remain on their original version. Reviewers
re-create relationships between successor annotations; the panel explains this.
Structural annotations and enrichment relationships are regenerated from the
new document. No automatic semantic re-anchoring or transitive lineage is stored.

## Regression coverage

- `test_reference_versioning.py`: pinned citations, visible current targets,
  legacy URL repair, current/history filtering, soft deletion, both directions
  of handwritten relationship carry-forward, and graph reconciliation.
- `test_annotation_version_review.py`: exact/ambiguous/missing TXT matches, real
  PDF projection and selection validation, all review outcomes, label changes,
  next-hop review, uniqueness, permissions, and historical GraphQL evidence.
- Existing enrichment, versioning, relationship privacy, and governance suites
  cover compatibility. `test_schema_parity.py` guards the updated SDL contract.
- Browser component tests exercise review actions and failure handling, cited
  and current links, stale counts, read-only access, and version navigation.
