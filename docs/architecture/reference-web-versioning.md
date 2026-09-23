# Reference Web and Document Versioning

Implemented from the design in PR #2389. A `Document` row is one immutable
version; `version_tree_id` identifies the logical document.

**Citations preserve the text originally cited. Current text is derived from
the version tree. Human annotations and their relationships are carried onto
each new version automatically where possible, and stay flagged until a person
checks them.**

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

## Human annotations: automatic carry, human review

`opencontractserver/annotations/services/version_review.py::AnnotationVersionReviewService`
owns this. When a new version finishes parsing, `set_doc_lock_state` queues
`carry_annotations_to_new_version`, which calls `carry_version`. For each
corpus of the new version, every human annotation on the parent gets one
`AnnotationVersionDecision` (one per annotation, `OneToOne`):

| `decision` | Set by | Meaning |
|---|---|---|
| `AUTO` | system | Unique exact text match; `successor` created, unreviewed |
| `STALE` | system | No unique match; no successor, needs placement |
| `REAPPROVED` | reviewer | Successor confirmed unchanged |
| `CORRECTED` | reviewer | Successor re-placed or relabelled |
| `DROPPED` | reviewer | No longer applies; successor (if any) deleted |

`AUTO` and `STALE` are *pending*: `reviewer`/`reviewed_at` stay null and
`DocumentType.annotationsNeedingReview(corpusId)` counts them. Successors keep
the original author as `creator`; the reviewer is recorded on the decision.
"Human" excludes structural, analysis, extract, corpus-action and grounding
rows (`human_annotations`). TXT offsets and PDF tokens use the shared
`span_projection` helpers; repeated text is never auto-placed.

**Multi-hop.** A v3 upload carries v2's human annotations, including v2
successors, so an unreviewed `AUTO` chain stays `AUTO`. `STALE` rows still
waiting on v2 are *moved* to v3 and matched again against its text, so an
annotation is never stranded on a superseded version. Pending rows on a
superseded version are history and cannot be acted on. Annotations older than
the parent that never received a decision (pre-feature data) are not revived.

**Relationships.** `_carry_relationships` copies a human `Relationship` onto the
new version once every source and target annotation has a successor there — at
carry time or when a later review supplies the last endpoint. Copies are
deduplicated by label and endpoint sets. Dropping a successor deletes any
carried edge it leaves without a source or target. Edges to structural or
analysis annotations stay on their original version.

**Review.** `carryForwardAnnotation` approves a pending row (optionally with a
`placement` or `annotationLabelId`, which makes it `CORRECTED`);
`dropStaleAnnotation` drops it. The server rebuilds text and bounds from the
new document's offsets or tokens and ignores client-supplied text. Reviewers
need UPDATE on the target document and corpus and READ on the source evidence;
only the current version's pending rows accept decisions. Both paths lock the
target document, then the decision row, so a review never races the carry.

**Visibility.** `AnnotationType.versionState` reports a row's forward decision
if it has one, otherwise how it arrived: on the current version an `AUTO`
annotation reads *Auto-carried · unreviewed*, a confirmed one *Approved* or
*Corrected*, and a freshly drawn one has no state. The sidebar
(`VersionStateBadge`), the **Carried-over annotations** panel and the version
pill all use the same labels; pending states are highlighted.

## Regression coverage

- `test_reference_versioning.py`: pinned citations, visible current targets,
  legacy URL repair, current/history filtering, soft deletion, both directions
  of handwritten relationship carry-forward, and graph reconciliation.
- `test_annotation_version_review.py`: automatic carry (`AUTO`/`STALE`,
  idempotence, the unlock trigger), relationship follow-through and pruning,
  every review outcome, multi-hop retargeting, real PDF tokens, permissions,
  and the GraphQL round trip with historical evidence.
- Existing enrichment, versioning, relationship privacy, and governance suites
  cover compatibility. `test_schema_parity.py` guards the updated SDL contract.
- Browser component tests exercise pending vs confirmed badges, review actions
  and failure handling, dropping a carried successor, cited and current links,
  read-only access, and version navigation.
