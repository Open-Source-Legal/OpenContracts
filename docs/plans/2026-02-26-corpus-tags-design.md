# Design: Corpus Tags with Event-Sourced History

**Date**: 2026-02-26
**Status**: Approved

## Problem

Users need to tag a corpus at a point in time (like GitHub tags/releases) with a title, version string, and description — then later view the exact corpus state as it was at that tag. The existing data model supports point-in-time reconstruction for documents (via `DocumentPath` lifecycle history) but not for annotations, relationships, folders, or other corpus-linked objects, which use hard deletes and have no audit trail.

## Solution

Two new models: an append-only **`CorpusEvent`** audit log that captures every mutation to corpus-linked objects, and a lightweight **`CorpusTag`** that marks a named point in time. Reconstruction is a single indexed query against the event log. Snapshots use the **V2 export TypedDicts**, so bridging tags to corpus export/import is trivial.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Event snapshot format | V2 export TypedDicts | Reuse existing serialization; export-at-tag becomes trivial |
| Which models to log | Auto-detect direct `corpus` FK | Zero config per model; covers Annotation, Relationship, Note, CorpusFolder, DocumentPath, Extract, CorpusAction, Conversation |
| Structural annotations | Excluded from event log | Deterministic from document content; recoverable via DocumentPath → Document → StructuralAnnotationSet |
| Storage optimization | Full snapshot per event | Individual snapshots are small (<1KB); no diff chaining complexity |
| Cold start (existing data) | Backfill on first tag | Zero migration cost; first tag = guaranteed baseline |
| Scope | Tag creation + event log + view query | Full MVP: create tags, log events, reconstruct corpus state at any tag |

## Data Model

### CorpusEvent

Append-only audit log for all corpus-linked mutations.

| Field | Type | Purpose |
|-------|------|---------|
| `id` | BigAutoField | Primary key |
| `corpus` | FK → Corpus (CASCADE) | Which corpus |
| `content_type` | FK → ContentType | Which model (Annotation, Relationship, etc.) |
| `object_id` | BigIntegerField | PK of the affected object |
| `event_type` | CharField choices: `CREATED`, `UPDATED`, `DELETED` | What happened |
| `snapshot` | JSONField | V2 export TypedDict for the object at this moment |
| `timestamp` | DateTimeField (indexed) | When it happened |
| `actor` | FK → User (SET_NULL, nullable) | Who did it |

**Indexes**:
- `(corpus, timestamp)` — for tag reconstruction range scans
- `(corpus, content_type, object_id, timestamp)` — for per-object latest-event lookups

### CorpusTag

Named point-in-time marker, analogous to a Git tag or GitHub release.

| Field | Type | Purpose |
|-------|------|---------|
| `id` | BigAutoField | Primary key |
| `corpus` | FK → Corpus (CASCADE) | Which corpus |
| `title` | CharField(256) | Human-readable name |
| `version_tag` | CharField(64) | Version string, e.g. `v1.0.0` |
| `description` | TextField (blank) | Release notes / description |
| `tagged_at` | DateTimeField | The point in time this tag captures |
| `creator` | FK → User (CASCADE) | Who created the tag |
| `created` | DateTimeField (auto_now_add) | When the tag record was created |

**Constraints**:
- `unique_together = (corpus, version_tag)` — no duplicate version strings per corpus

## Event Logging Mechanism

### Signal Handler

Connected to `post_save` and `pre_delete` on all `BaseOCModel` subclasses. Lives in `opencontractserver/corpuses/signals.py`, imported in `CorpusesConfig.ready()`.

**Logic**:
1. **Skip if no direct corpus FK** — checks for `corpus` or `chat_with_corpus` field on the instance
2. **Skip structural annotations/relationships** — `instance.structural == True`
3. **Skip if `_skip_signals` is set** — established pattern for test fixtures and bulk operations
4. **Serialize** — dispatch to correct V2 export serializer based on model class
5. **Create event** — `CorpusEvent.objects.create(...)` with actor from thread-local

### V2 Snapshot Serialization

A dispatcher maps model class → V2 export TypedDict serializer:

| Model | V2 TypedDict |
|-------|-------------|
| `Annotation` | `OpenContractsAnnotationPythonType` |
| `Relationship` | `OpenContractsRelationshipPythonType` |
| `CorpusFolder` | `CorpusFolderExport` |
| `DocumentPath` | `DocumentPathExport` |
| `Note` | Subset of Note fields (title, content, document ref) |
| `Extract` | Subset of Extract fields (name, fieldset ref) |
| `CorpusAction` | `CorpusActionExport` |
| `Conversation` | `ConversationExport` |
| `Corpus` (self) | `OpenContractCorpusV2Type` (for metadata changes) |

Reuses existing V2 export utility functions from `opencontractserver/utils/export_v2.py` where possible.

### Actor Tracking

New middleware in `opencontractserver/shared/middleware.py` stores `request.user` in thread-local storage. Signal handler reads from thread-local. For Celery tasks, actor comes from task context (or is `None` for system operations).

## Tag Creation & Backfill

### CreateCorpusTag Mutation

1. Validate user has UPDATE permission on corpus
2. Validate `version_tag` is unique for this corpus
3. Set `tagged_at = timezone.now()` (or accept custom timestamp for retroactive tags)
4. **If no CorpusEvent records exist for this corpus** (first tag):
   - Query all non-structural Annotations, Relationships, Notes, CorpusFolders, DocumentPaths, Extracts, CorpusActions, Conversations linked to the corpus
   - Bulk-create `CorpusEvent` records with `event_type=CREATED`, `timestamp=tagged_at`
   - Snapshot the Corpus itself (metadata) as a special event
   - Use `_skip_signals` pattern during bulk insert
5. Create the `CorpusTag` record

**Backfill performance**: For ~700 objects (500 user annotations + 50 folders + 100 paths + misc), this is a single bulk insert completing in under a second.

### Other Mutations

- `UpdateCorpusTag` — edit title, description (not version_tag or tagged_at)
- `DeleteCorpusTag` — remove the tag record (events are NOT deleted)

## Reconstruction Query

### GraphQL Query: `corpusAtTag(corpusId, tagId)`

**Algorithm**:

```sql
SELECT DISTINCT ON (content_type_id, object_id)
    content_type_id, object_id, event_type, snapshot
FROM corpus_event
WHERE corpus_id = :corpus_id
  AND timestamp <= :tagged_at
ORDER BY content_type_id, object_id, timestamp DESC
```

Filter out rows where `event_type = DELETED`. Group remaining snapshots by content_type. Return structured response:

- **documents**: From DocumentPath snapshots → linked Document data
- **annotations**: Non-structural, user-created annotations
- **relationships**: Non-structural relationships
- **folders**: Folder tree at that point in time
- **structural data**: Reconstructed via DocumentPath → Document → StructuralAnnotationSet chain
- **corpus_metadata**: Corpus fields at that point in time

Also expose `corpusTags(corpusId)` to list all tags for a corpus.

### Performance

The composite index `(corpus, content_type, object_id, timestamp)` makes the `DISTINCT ON` query efficient. For a corpus with 1,000 events, this is a fast index scan.

## Testing Strategy

- **Signal tests**: Verify events created on save/delete, structural skipped, non-corpus models skipped
- **Backfill tests**: Create corpus with data, create first tag, verify CREATED events for all objects
- **Reconstruction tests**: Create corpus, mutate objects across multiple tags, verify each tag reconstructs correctly
- **Permission tests**: Only corpus UPDATE users can create/delete tags; tag view respects corpus visibility
- **Edge cases**: Empty corpus, duplicate version_tag rejection, deleting tag preserves events

## Files to Create/Modify

| File | Change |
|------|--------|
| `opencontractserver/corpuses/models.py` | Add `CorpusEvent`, `CorpusTag` models |
| `opencontractserver/corpuses/signals.py` | New: event logging signal handlers |
| `opencontractserver/corpuses/apps.py` | Import signals in `ready()` |
| `opencontractserver/corpuses/event_serializers.py` | New: V2 snapshot serializers (reusing export utils) |
| `opencontractserver/shared/middleware.py` | New: thread-local actor tracking middleware |
| `config/graphql/graphene_types.py` | Add `CorpusTagType`, `CorpusAtTagType` types |
| `config/graphql/queries.py` | Add `corpus_tags`, `corpus_at_tag` queries |
| `config/graphql/corpus_tag_mutations.py` | New: Create/Update/Delete tag mutations |
| `config/graphql/schema.py` | Wire in new types/queries/mutations |
| `opencontractserver/tests/test_corpus_tags.py` | New: comprehensive test suite |
| Migration | New `CorpusEvent` and `CorpusTag` tables |

## Future Extensions (Out of Scope)

- **Export at tag**: Generate a V2 export ZIP of the corpus at a given tag (snapshots are already in the right format)
- **Diff between tags**: Show what changed between two tags
- **Tag-based branching**: Fork a corpus from a tag into a new corpus
- **Compaction**: Periodically compact old events between tags to reduce storage
