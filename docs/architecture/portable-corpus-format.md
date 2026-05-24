# Portable Corpus Format — A Proposal

**Status:** Proposal / draft for discussion. Not implemented.
**Companion docs:** [`corpus_export_import_v2.md`](corpus_export_import_v2.md), [`corpus-export-format-spec.md`](corpus-export-format-spec.md), [`corpus_forking.md`](corpus_forking.md)
**Format version (proposed):** `"version": "3.0"`

---

## 1. The Proposal in One Paragraph

Replace the current V2 export/import ZIP with a **content-addressed corpus bundle** modeled on the matter2 VCS — a self-contained directory of blobs (sharded by SHA-256), JSON manifests, and a HEAD pointer — that is byte-identical whether produced by `oc export`, materialized by `oc clone`, or shipped back by `oc push`. The server stays on Postgres + S3 and transcodes between its native storage and the bundle at the boundary. The bundle is the canonical interchange format, the canonical local-checkout format, and the canonical input to a new local SDK that exposes the same agent-tool API the server does — so any LLM workflow that runs against a corpus today via MCP or GraphQL can run against a `.opencontracts/` directory on a laptop tomorrow, offline. Pushing changes back is a fast-forward operation under optimistic concurrency: the server only accepts pushes whose parent matches its current HEAD, and the client handles fetch-and-rebase locally when its push is rejected.

## 2. Motivation

Three concrete prizes, in priority order:

1. **Clone-and-go LLM workflows.** `oc clone <corpus>` produces a directory you can point pydantic-ai, LangChain, or a custom agent at without ever round-tripping to a server. The current MCP server is read-only and remote; this makes the same surface local-first. This is the headline.
2. **Reproducible distribution.** Public corpora become citable, forkable artifacts. A regulator can publish a reference corpus; firms fork it. Same shape as Hugging Face Datasets, but for enterprise knowledge bases.
3. **Provenance and dedup at the right granularity.** Every derived entity (PAWLs, embeddings, structural annotations) carries a producer fingerprint and a content hash. A PDF used in 500 corpora is stored once. A re-run of the same parser on the same input is a cache hit, not a recompute.

A fourth, longer-horizon prize — collaborative annotation workflows where multiple reviewers' changes can merge — is enabled but not delivered by this proposal. It becomes a future capability rather than a Phase-1 goal.

## 3. What This Collapses

Today OpenContracts has:

- **V1 export ZIP** — legacy importer, retained for backward compatibility
- **V2 export ZIP** — current export/import format ([`corpus_export_import_v2.md`](corpus_export_import_v2.md))
- **No local format** — corpora live only on the server; the MCP server is the only external read surface
- **`fork_corpus` Celery task** — currently builds an in-memory V2 ZIP and re-imports it server-side ([`corpus_forking.md`](corpus_forking.md))

This proposal converges these into **one canonical bundle format** that is:

- What `oc export` produces
- What `oc clone` materializes locally
- What the local SDK reads from and writes to
- What `oc push` ships back
- What `oc import` ingests
- What `fork_corpus` internally produces and consumes

Same bytes. One spec. V1 imports continue to work via a one-way migration shim; V2 imports continue to work for a defined deprecation window.

## 4. Non-Goals

Explicitly out of scope for this proposal — these are deferred to future work or excluded by design:

- **Git-style branching/merging UX.** The bundle's substrate supports a DAG of commits and could grow branches later, but a `oc branch` / `oc merge` command surface is not delivered here. The model is: clone, mutate locally, push (fast-forward). Server has one HEAD per corpus.
- **Server-side substrate change.** Postgres stays the source of truth on the server. Content-addressed object storage on the server (and the cross-corpus blob dedup it would enable at the infra level) is a separate, later optimization.
- **Federation / peer-to-peer sync.** All clones pull from and push to a server. No client-to-client sync.
- **Per-entity diff-and-merge conflict UX.** The client-side rebase logic in Phase 4 starts with strict semantics and grows incrementally; a real conflict-resolution UI is out of scope for v1.
- **Mutable analyses, extracts, and conversations.** These are server-side computations or workflow artifacts; the bundle ships them as read-only state.
- **Permission portability.** django-guardian permissions are tied to a server-side User table. The bundle ships a `creator` reference; on import or push, all identity is re-resolved against the receiving system.

## 5. The Bundle on Disk

```
.opencontracts/
  objects/                          # Content-addressed blob store, sharded by SHA-256
    ab/
      cdef...                       #   One file per stored blob, zlib-compressed
    ...
  manifests/                        # Per-entity-type and per-document manifests
    corpus.json                     #   Corpus row + agent config + label set refs
    documents/
      <doc-uuid>.json               #   Per-document manifest (matter2-style ZIP manifest for PDF internals, plus pointers to derived artifacts)
    annotations/
      <doc-uuid>.json               #   All annotations for one document (splittable for partial clones)
    structural_sets/
      <content-hash>.json           #   Structural annotation set (already content-hashed in V2)
    folders.json                    #   Folder tree
    document_paths.json             #   DocumentPath version history
    labels.json                     #   Label set + label definitions
    relationships/
      <doc-uuid>.json               #   Non-structural relationships, per-doc
    extracts.json                   #   Manual metadata schema (Fieldset + Columns + Datacells)
    conversations.json              #   Optional; conversations + messages (read-only on push)
    notes/
      <doc-uuid>.json               #   Notes (per document)
  pipeline.lock                     # Producer fingerprints: parsers, embedders, post-processors
  refs/
    HEAD                            #   The checkpoint hash this clone is currently at
    server                          #   The server-side HEAD hash at clone time (for push freshness check)
  log/                              # Local commit DAG (matter2-shaped)
    <checkpoint-hash>               #   One file per local commit
  index                             # Staging area (JSON map of path -> object hash)
  cache/
    oc.sqlite                       # Lazily-built local SQLite index for fast queries (NOT in the wire format; see §11)
    hash_cache.json                 # mtime/size -> hash cache for working tree
  config.toml                       # Local preferences (preferred embedder override, etc.)
```

Properties:

- **Self-contained.** Every byte needed to reconstruct any version of any artifact lives in `objects/` and `manifests/`. No external paths, no absolute references, no implicit DB. (This mirrors matter2 §2 and §12.)
- **Wire-equivalent.** A tar of `.opencontracts/` (minus `cache/` and `index`) is the canonical interchange format. `oc export` produces it; `oc clone` materializes it.
- **Splittable manifests.** Per-document and per-entity-type manifests mean a partial clone (e.g., "I only want these 50 documents") fetches only the manifest blobs it needs. The corpus-level `corpus.json` is the index.
- **Client-private cache.** `cache/` and `index` are local-only optimizations. The wire format never includes them. Deleting `cache/` only costs a slower next query.

## 6. The Five Layers

The bundle is built up in five layers, each a strict generalization of matter2's two-layer (blob + manifest) model:

| Layer | Examples | matter2 Equivalent |
|---|---|---|
| **1. Blob** | SHA-256-addressed opaque bytes (PDF internals, raw PDFs, PAWLs blobs, embedding blobs, note text) | Direct port. |
| **2. Manifest** | Per-document interior maps (matter2-style); per-entity-type collection manifests (annotations, relationships, folders) | Direct port + one rung higher. |
| **3. Entity** | Documents, Annotations, Notes, Relationships as typed rows in manifest JSON, each carrying blob hash references for bulky fields | New — matter2 tracks files; we track typed entities. |
| **4. Provenance** | `pipeline.lock` (parser/embedder/post-processor fingerprints) + per-entity `producer` metadata | New — gives cache-invalidation and re-computability. |
| **5. Workflow** | Local SDK runtime exposing the agent-tool API against the local bundle | New — this is what turns a clone into a usable artifact, not just an archive. |

The architectural commitment is that **anything on the server's MCP/agent-tool surface must have a local-runtime equivalent that reads `.opencontracts/` instead of the live DB.** That alignment is what makes "clone and go" real.

## 7. Server / Client Split

Two halves, with a deliberately narrow contract between them.

### 7.1 Server

- **Storage**: Postgres + S3, as today. No substrate change.
- **What's new**: a `current_HEAD_hash` per corpus (the hash of the canonical manifest at the current state). Updated atomically on any mutation that affects the bundle (annotation create/edit/delete, document add/remove, etc.). Cached aggressively.
- **Endpoints (added)**:
  - `GET /api/corpus/<id>/bundle/HEAD` — returns current HEAD hash.
  - `GET /api/corpus/<id>/bundle/objects?have=<hash>,<hash>,...` — incremental fetch; returns only objects the client doesn't already have. Supports streaming.
  - `POST /api/corpus/<id>/bundle/push` — accepts `{new_objects, new_manifests, new_HEAD, parent_HEAD}`. Validates `parent_HEAD == current_HEAD_hash`. If yes: bulk-ingests new objects (skipping any whose hash is already present), updates DB rows, atomically advances HEAD. If no: rejects with `409 Conflict` and current HEAD.
- **What stays the same**: existing GraphQL mutations, the MCP server, all current corpus-edit UX. Server-side users continue to mutate via the normal API; the HEAD hash bumps as a side effect.

### 7.2 Client

A real matter2-shaped repository on disk, not a passive cache:

- **Has its own DAG.** Local commits are real commits with parent pointers. The local HEAD advances independently of the server's.
- **Has a staging area** (`index`). `oc add` stages local edits, `oc commit` produces a new local checkpoint.
- **Tracks the server's HEAD-at-clone-time** in `refs/server`. This is the parent the next push will build on (or the base for a rebase if push fails).
- **Can rebase its local commits onto a newer server HEAD** when a push is rejected (see §8).
- **Built on matter2's library API** for the VCS layer. We do not re-implement the object store, commit lifecycle, or DAG semantics — those are matter2's job. We add the entity-and-manifest layer on top.

The split's value: **the server contract is frozen and trivially implementable; the client can grow more sophisticated independently.** A v1 client can be brain-dead about rebase ("abort, tell user to re-do their changes against new HEAD"); a v2 client can auto-merge additive changes; a v3 client can offer a real conflict-resolution UI. Server stays the same throughout.

## 8. Clone and Push Protocol

### 8.1 Clone

```
1. Client: GET /api/corpus/<id>/bundle/HEAD            → server returns H
2. Client: GET /api/corpus/<id>/bundle/objects?have=   → server streams all objects
3. Client: writes objects/, manifests/, refs/HEAD = H, refs/server = H
4. Client: writes pipeline.lock from server-supplied producer registry
5. Client: SDK builds cache/oc.sqlite lazily on first query
```

Incremental refresh follows the same protocol but with `?have=<hashes>` populated from the client's existing object store.

### 8.2 Push (the happy path)

```
1. User makes local edits (e.g., new annotations).
2. oc add / oc commit produces a new local checkpoint C_new with parent C_old (where C_old == refs/server).
3. oc push:
   a. Client collects objects + manifests added since refs/server.
   b. POST /api/corpus/<id>/bundle/push
        {new_objects, new_manifests, new_HEAD=C_new, parent_HEAD=C_old}
   c. Server checks current_HEAD_hash == C_old. Yes → ingest, advance HEAD to C_new, return 200.
   d. Client updates refs/server = C_new.
```

### 8.3 Push (rejected — the rebase case)

```
1. Client: POST .../bundle/push with parent_HEAD = C_old.
2. Server: current HEAD is now C_old' (someone else pushed). Returns 409 {current_HEAD: C_old'}.
3. Client: GET .../bundle/objects?have=<known hashes>   → fetches the diff.
4. Client: rebases its local commits (C_old → C_new) onto C_old' → produces C_new'.
5. Client: retries push with parent_HEAD = C_old', new_HEAD = C_new'.
```

The rebase logic in step 4 is the spot where the client grows over time:

- **v1**: refuses to rebase, surfaces the local-vs-remote diff to the user, asks them to re-apply manually.
- **v1.5**: auto-rebases entities that are strictly additive (new annotations, new notes, new labels, new relationships). Conflicts only on same-entity edits.
- **v2**: real conflict-resolution UI for same-entity touches.

### 8.4 What the Server Never Has to Do

The server **never** does conflict resolution, **never** does per-entity merges, **never** has to understand the client's local DAG. It accepts fast-forwards or rejects with a hash. This is the entire reason the model is tractable.

## 9. Mutable-Locally vs. Read-Only

Explicit boundary. This is also the SDK's write API surface.

| Bucket | Entities | Notes |
|---|---|---|
| **Locally mutable, pushable** | Annotations, notes, relationships, new labels, folder structure, document add/remove (with source file present) | The core annotator + curator workflows. All structured, all cheap. |
| **Locally mutable, server-recomputed on push** | Embeddings — client may produce them locally with the corpus's embedder, but server may regenerate to ensure consistency with `Corpus.preferred_embedder` | Avoids forcing local users to carry the embedder. |
| **Locally read-only** | Extracts (auto-generated), analyses, conversations, structural annotation sets (when produced server-side), permissions, action trail | Server-side computations or identity-bound. Mutating locally would mean inventing results. |
| **Never in the bundle** | Ingestion source credentials, internal user PII beyond what `pipeline.lock` records, session tokens | Excluded by design. |

The locally-mutable set is also the merge-friendly set: every entity in it is either strictly additive (new things) or has a clear last-write-wins fallback (same-entity edits). This is what makes future client-side auto-merge viable.

## 10. Provenance — `pipeline.lock`

A TOML file at the bundle root, structured like:

```toml
[parsers.docling]
name = "docling"
version = "2.4.1"
config_hash = "f3a7..."

[embedders.openai-text-embedding-3-large]
name = "openai/text-embedding-3-large"
dimension = 3072
normalize = true
config_hash = "9c11..."

[post_processors]
order = ["pii-redactor", "section-tagger"]

[post_processors.pii-redactor]
module = "opencontractserver.pipeline.post_processors.pii"
version = "1.2.0"
```

Every derived entity in the manifests carries a `producer` field that references a key in `pipeline.lock`. Implications:

- **Cache invalidation is automatic.** A change to an embedder's config hash → all embeddings produced under the old hash are stale, but still present and queryable. The client can offer to regenerate.
- **Reproducibility is bounded by `pipeline.lock`.** If you receive a bundle and run the same pipeline.lock locally, you should get bit-identical derived artifacts (subject to non-determinism in the underlying models, which is on the model authors, not us).
- **Embeddings are deduplicated by producer + input.** A vector is content-addressed by `sha256(producer_id || input_text_hash)`. Same text + same embedder = same blob = one copy.

This generalizes today's narrow `Corpus.preferred_embedder` + `created_with_embedder` pattern (see [`embeddings_creation_and_retrieval.md`](embeddings_creation_and_retrieval.md)) to the whole pipeline.

## 11. Performance and Substrate Choices

This was the question that nearly torpedoed the design. The answer is a clean three-way split.

### 11.1 Canonical Wire Format: JSON Manifests + Content-Addressed Blobs

Not SQLite. Not Parquet. JSON manifests + zlib-compressed SHA-256-addressed blobs, exactly the matter2 model. Reasons:

- **No SQLite write cost on the server.** Postgres stays the source of truth; the server emits JSON manifests directly via bulk `json_agg` queries (see §11.4 below). It never writes SQLite.
- **Streamable.** JSON manifests can be written entry-by-entry; the bundle builder never has to hold the whole corpus in memory.
- **Language-agnostic.** Any consumer can read JSON. SQLite would tie clients to a specific binding.
- **Diffable at the hash level.** Two bundles can be compared by HEAD hash before any content is touched.

### 11.2 Client-Side Cache: SQLite (with sqlite-vss for Vectors)

The client SDK builds `cache/oc.sqlite` lazily on first query, from the bundle's manifests. Rebuilt automatically when the bundle is updated (any local commit invalidates it). Reasons:

- **Fast queries.** Loading + parsing JSON manifests on every query would be miserable. SQLite indices make annotation/document/embedding queries fast.
- **Vector search.** `sqlite-vss` (or a similar embedded vector library) gives the local SDK the same retrieval surface the server's pgvector provides. Without this, the LLM-workflow story doesn't really land.
- **Not in the wire format.** Server never sees it; pure client-side optimization.

### 11.3 Server Storage: Postgres + S3 (Unchanged)

The server keeps its existing schema. The new export path queries the existing tables and emits the canonical bundle. The new import path bulk-ingests bundle contents into the existing tables. **No production data migration is required to ship this.**

A later, separate proposal could move the server's S3 `FileField` storage to a content-addressed sharded layout, gaining cross-corpus blob dedup at the infra level. That's a pure optimization that doesn't change the bundle format and isn't required for any of the user-facing wins above.

### 11.4 The Five Performance Levers on the Server

The user concern was "crawling SQL is going to be a real pain." It would be — if the server rebuilt the whole bundle on every operation, the way V2 does today. The fix is architectural, not format-driven:

1. **Cached HEAD hashes.** Server stores `current_HEAD_hash` per corpus, invalidated on any mutation. `GET .../bundle/HEAD` is a single indexed lookup. If a client's bundle is up to date, the entire export operation does zero DB work beyond that lookup.

2. **Incremental fetch / push (the big one).** Content-addressed storage means clones, fetches, and pushes are all O(Δ) instead of O(corpus). After the first clone, only changed objects move. A 100k-annotation corpus where 50 annotations changed pushes 50 objects, not 100k. **This is the single biggest performance win in the whole proposal.**

3. **Bulk JSON-aggregation queries, not ORM loops.** Today's V2 walks the ORM in Python (`for doc in corpus.documents: ... for ann in doc.annotations: ...`). One `SELECT jsonb_agg(jsonb_build_object(...)) FROM annotations WHERE corpus_id = $1` per entity type is two orders of magnitude faster. This is a worthwhile optimization to apply to V2 *today* even without the rest of this proposal.

4. **Streamed bundle assembly.** Build objects and write them to the output stream as they're produced. Never materialize the whole bundle in heap. (V2 builds `data.json` in memory; this drops that ceiling entirely.)

5. **Splittable manifests.** Per-document and per-entity-type manifests mean a partial clone fetches only the manifest blobs it needs. A client interested in 50 of 5000 documents fetches 50 doc manifests, not 5000.

### 11.5 The Residual Cost

The *first* full clone of a brand-new big corpus is still O(n) — there's no way around serializing every entity once. Modern hardware does this fine with proper bulk SQL (a 100k-annotation corpus should serialize in seconds). The win is that everything after the first clone — fetches, pushes, re-clones, fork operations — is O(Δ).

## 12. V1 / V2 Migration Story

| Format | Plan |
|---|---|
| **V1 zip** | Continue to accept on import for a defined deprecation window (12 months from V3 GA, suggested). Import converts to internal storage; export produces V3 only. No new V1 features. Eventually retire. |
| **V2 zip** | Continue to accept on import indefinitely (it's a strict subset of what V3 represents — see [`corpus_export_import_v2.md`](corpus_export_import_v2.md)). The V2 export path becomes a thin shim over V3: build the V3 bundle, then degrade to the V2 ZIP shape for compatibility. Eventually deprecate when no V2-only consumers remain. |
| **V3 bundle** | New canonical format. New `oc clone` / `oc push` endpoints. New SDK. Becomes the default for fork, export, and import. |

`fork_corpus` (see [`corpus_forking.md`](corpus_forking.md)) is internally rewritten to use the V3 bundle path — same in-memory artifact, just shaped differently. User-facing semantics unchanged.

Issue [#1608](https://github.com/Open-Source-Legal/OpenContracts/issues/1608) (slug-based user references) becomes a prerequisite for V3, since the bundle should not embed user emails as identifiers.

## 13. Local SDK API Sketch

The interface design goal: **same agent-tool API as the server, just pointed at the local bundle.**

```python
from opencontracts.local import Corpus

# Open a cloned bundle
corpus = Corpus.open(".opencontracts")

# Read API (mirrors MCP server tools)
docs = corpus.list_documents()
text = corpus.get_document_text(doc_id)
annotations = corpus.get_annotations(doc_id)
hits = corpus.search_corpus("indemnification clauses", limit=10)  # vector search via sqlite-vss

# Agent tools (same wrapper protocol as server-side)
from opencontracts.local.agent_tools import build_tools
tools = build_tools(corpus, user=local_user)

# Use with any agent framework
from pydantic_ai import Agent
agent = Agent("claude-opus-4-7", tools=tools)
result = agent.run_sync("What are the indemnification terms?")

# Write API (creates local commits)
with corpus.transaction(author="alice@example.com") as tx:
    tx.create_annotation(document_id=..., label="Indemnity", span=...)
    tx.create_note(document_id=..., text="See clause 12")
    checkpoint = tx.commit(message="Annotated indemnity clauses")

# Sync
corpus.fetch()  # pulls server HEAD, fast-forwards if possible
corpus.push()   # pushes local commits; rebases on rejection (v1: surfaces conflicts, v1.5+: auto-merges additive)
```

The SDK is Python-first because the existing agent tools are Python (pydantic-ai). The bundle format is language-agnostic, so a future TypeScript or Rust SDK is straightforward.

## 14. Phased Shipping Plan

Each phase is independently shippable. You can stop after any phase and have a real product.

### Phase 0 — Design and Alignment (this doc)

Pin the bundle spec, the server/client contract, the mutable/immutable boundary. No code.

### Phase 1 — Bundle Format and Server Transcoding

- Implement the bundle spec on the server: write the JSON-manifest builder using bulk `json_agg` queries; build the content-addressed object store as a server-side artifact (cached, hash-indexed).
- New `oc export` produces V3 bundles. New `oc import` consumes V3 bundles.
- V2 export retained as a thin shim over V3. `fork_corpus` migrated to V3 internally.
- **Shippable as:** a faster, smaller, content-addressed export/import format. No user-visible API changes beyond the new format.

### Phase 2 — Clone Endpoint and Read-Only SDK

- `GET .../bundle/HEAD` and `GET .../bundle/objects?have=...` endpoints.
- `oc clone` CLI command + Python API.
- Local SDK with full read API (documents, annotations, vector search via sqlite-vss, agent-tool wrapper).
- **Shippable as:** "clone a corpus to your laptop and run agent workflows offline." This is the headline LLM-workflow win and the announceable milestone.

### Phase 3 — Local Mutation

- Staging + commit lifecycle on the client (`oc add`, `oc commit`, `oc status`, `oc log`).
- Write API in the SDK (`tx.create_annotation`, etc.).
- No push yet — local commits stay local.
- **Shippable as:** offline annotator / curator workflows. Useful for solo work and for users who export their results another way.

### Phase 4 — Push and Rebase (v1)

- `POST .../bundle/push` endpoint with fast-forward check.
- `oc push` CLI command.
- Client-side rebase v1: on rejection, fetch + surface the conflict to the user as "here are your local changes, here's the new server state, please re-apply."
- **Shippable as:** the full clone → mutate → push loop for single-user workflows.

### Phase 5 — Smart Rebase (v1.5)

- Client auto-rebases strictly-additive changes (new annotations, new notes, new labels) on conflict.
- Same-entity edits still surface as conflicts.
- **Shippable as:** practical multi-user workflows where most concurrent changes are additive.

### Phase 6 — Conflict-Resolution UX (v2)

- Real per-entity conflict surfaces in the SDK and (optionally) in a CLI tool.
- **Shippable as:** the full collaborative-annotation story.

### Phase 7+ — Optional Wins

- Server-side content-addressed blob storage (cross-corpus dedup at the infra level).
- Delta storage in the object store (matter2's reserved-but-unused path; xdelta3 against the prior version of the same internal file).
- Partial clones (sparse-checkout equivalent).
- LFS-equivalent for outsized PDFs.
- TypeScript SDK.

## 15. Open Questions

Decisions deferred for explicit discussion before Phase 1 starts:

1. **Embedder ship-by-default or regenerate?** The bundle could ship embeddings (bulky, but instantly usable) or omit them (smaller, but requires local embedder access to be useful). Suggested default: ship them, with a `--shallow` flag on `oc clone` to omit. `pipeline.lock` makes regeneration deterministic when needed.

2. **CLI binary: `oc` standalone, or extend matter2?** Standalone is cleaner branding; reusing matter2's CLI shell would be faster. Suggested: standalone `oc` binary that depends on matter2 as a library for the VCS substrate.

3. **What does "write access" mean for push?** Today, corpus permissions are django-guardian object-level. The push endpoint should check the standard `update_corpus` permission. New annotations, notes, labels should require nothing more than `update_corpus`. Document add/remove may want a higher bar. Decide before Phase 4.

4. **Conversation history on bundle: included by default or opt-in?** V2 has this as a flag. Suggested: opt-in on export, since conversations can contain sensitive content and are workflow rather than knowledge.

5. **Server-side bundle cache invalidation granularity.** Per-corpus HEAD hash bumps on any mutation. Is that fine, or do we need finer granularity (e.g., per-document, so that touching one doc doesn't invalidate the bundle of an unrelated doc on a per-doc clone)? Probably fine to start coarse and refine.

6. **Permissions on a fork-via-clone path.** Cloning a public corpus → fork is clear (you own the fork). Cloning a private corpus you have READ on → ??? Is the local copy yours forever (matter2's view of the world), or is it lease-style (must re-clone after expiry)? Suggested: clone-is-fork. Cleaner contract.

7. **Schema versioning inside manifests.** Each manifest type carries its own schema version (e.g., `annotations/<doc>.json` has `"manifest_schema_version": 1`)? Or does the bundle have one top-level version (`"version": "3.0"`)? Probably both: top-level for major format, per-manifest for in-place schema evolution.

## 16. Decisions Already Made (with Rationale)

These were debated in the design conversation and are now fixed assumptions for Phase 1 work:

| Decision | Rationale |
|---|---|
| **JSON manifests + content-addressed blobs as the canonical wire format** | No server-side SQLite cost; streamable; diffable at hash level; language-agnostic. |
| **SQLite as client-side cache only** | Fast local queries + vector search; never in the wire format; rebuilt lazily. |
| **Server-side storage unchanged (Postgres + S3)** | No production data migration to ship this. Substrate change is a separate, later, optional optimization. |
| **Server only accepts fast-forward pushes** | Trivial server contract; client owns merge sophistication; client can grow without server changes. |
| **Client is a full matter2-shaped repo with local DAG, not a passive cache** | Required for client-side rebase to be possible. matter2's library does the VCS work. |
| **Mutable-locally set is annotations, notes, relationships, new labels, folders, documents** | Strictly additive or last-write-wins fallback — auto-merge-friendly. |
| **Embeddings auto-regenerate server-side on push** | Avoid forcing the local user to carry embedder credentials. |
| **No git-style branching UX in v1** | Engineering cost too high relative to current user-pull; substrate supports it, ship it later if demanded. |
| **`pipeline.lock` carries producer fingerprints for every derived artifact** | Cache invalidation; reproducibility; foundation for re-running pipelines deterministically. |
| **Splittable per-entity-type manifests** | Partial clones; parallel fetch; cheap diffs at the manifest level. |

---

## Appendix A: Comparison to Existing Mechanisms

| Concern | Current (V1/V2) | This Proposal |
|---|---|---|
| Format | Monolithic ZIP with one `data.json` | Sharded object store + splittable JSON manifests |
| Bundle build cost | O(n) every time | O(n) first time, O(Δ) thereafter |
| Cross-corpus blob dedup | Partial (`pdf_file_hash`, `content_hash`) | Native, automatic for all blobs |
| Local-checkout format | None | Same as wire format |
| LLM-workflow surface | MCP server (remote, read-only) | Local SDK against bundle (offline, read+write) |
| Identity preservation across import | None (fresh PKs everywhere) | UUID identity + content hashes; preserved |
| Conflict on re-import | Duplicates | Fast-forward check; rejected if HEAD moved |
| Provenance | `parser_name`/`parser_version` on structural sets only | `pipeline.lock` covers every derived artifact |
| User PII | Email-based references | Slug-based (depends on issue #1608) |
| Embeddings | Not exported; regenerated | Optionally shipped; producer-fingerprinted |
| Analyses/Analyzers | Lost on round-trip | Read-only in bundle; provenance preserved |

## Appendix B: What This Doesn't Solve

In the interest of intellectual honesty:

- **Annotation re-anchoring across document versions** is still the unsolved hard problem of OpenContracts and this proposal doesn't fix it. An annotation is content-addressed against a *specific version* of a document; if the document is reparsed or re-OCR'd, the annotation may dangle. The bundle makes this *visible* (you can see exactly which document-version an annotation attached to) but doesn't automatically migrate annotations across versions. That's a separate piece of work.
- **Schema evolution for the manifest formats** will eventually bite. We need a discipline of forward-compatible schema changes from day one (additive fields tolerated; renames require schema-version bumps). The `manifest_schema_version` field per manifest type is the hook for this.
- **Adversarial inputs.** The bundle format must be defended against the same zip-bomb / path-traversal / size-bomb concerns the V2 importer already handles (see `opencontractserver/constants/zip_import.py`). The matter2 hash-based design helps (you validate every blob's hash on read) but doesn't replace the existing protections.
- **Distributed identity.** A corpus pushed to two different servers becomes two unrelated histories from those servers' perspectives. There is no federation story in this proposal — every clone has exactly one upstream.

---

*This is a proposal. Reactions, objections, and alternative framings are explicitly welcome. The shape will change in response to feedback before any code is written.*
