# MCP Knowledge-Tool UX — Design

**Date:** 2026-05-31
**Status:** Approved (design); pre-implementation
**Branch:** `feature/mcp-knowledge-tool-ux` (off `origin/main`)
**Packaging:** one umbrella PR, 5 commits → 5 tracking issues (#1858–#1862)

## Background

The public MCP interface (`opencontractserver/mcp/`) is meant to let an AI use an
OpenContracts corpus as a low-friction knowledge tool. A hands-on evaluation of
the live deployment (`cite.opensource.legal/mcp/corpus/{slug}/`, v1.27.1) against
real corpora found the three headline capabilities are not usable today:

| Capability | Tool | Observed |
|---|---|---|
| Full-text retrieval | `get_document_text` | Crashes: `"Object of type bytes is not JSON serializable"` (`isError: true`) on every document |
| Text / semantic search | `search_corpus` | Returns `{"results": []}` for every query, including exact document titles |
| Annotation search | `list_annotations` | Works, but only filters by `page` / exact `label_text` — cannot search annotation *content* |

Net effect: an AI connecting to a corpus cannot answer a question about it.

### Root causes (code, current branch)

1. **`get_document_text` bytes crash** — `tools.py` reads `txt_extract_file.open("r").read()`
   and puts the result straight into a `json.dumps`-ed payload. On S3/GCS the
   django-storages backend returns `bytes` from text-mode reads, which is not
   JSON-serializable. This is fixed by **PR #1841** (the `read_field_file_text()`
   helper). #1841 is a prerequisite for this initiative's full-text work, not part
   of it.
2. **`search_corpus` always empty** — two compounding bugs in `tools.py:search_corpus`:
   - It searches **document-level** embeddings (`get_corpus_documents().search_by_embedding(...)`),
     filtered by the corpus's current `embedder_path`. OpenContracts embeddings live
     at the **annotation/chunk** level, so the document-level join is empty.
   - When the vector path returns an empty list it `return`s immediately; the text
     fallback only runs inside the `except`, so on any embedding-configured server
     the fallback is dead code.
   - Even when it worked, it returned only `{slug, title, similarity_score}` — no
     passage text, no page, no citation. Low value for RAG.
3. **`list_annotations` is not "search"** — no content/text parameter; results are
   not ordered by reading position; payload carries low-signal, high-token fields.
4. **Polish gaps** — `get_corpus_info` advertises the full seeded "Default Labels"
   set (irrelevant to the corpus, misleads the AI about `label_text`); errors leak
   raw Python/Django exception strings with no remediation hint; tool descriptions
   are terse and oversell (`search_corpus` says "Semantic search" with no mention of
   granularity or that it can return nothing).

## Goals

Make a corpus usable as a knowledge tool via the public MCP interface:

- Semantic + text search returns **passages** (matched text + page + document),
  and never silently returns empty when matchable content exists.
- Annotations are searchable by **content**, filterable by **kind** (structural vs
  human/analysis), and returned in reading order.
- Search returns a **single ranked feed** of granular passages and aggregated
  `OC_SUBTREE_GROUP` blocks, each self-describing via `type`.
- **Relationships** are reachable: as aggregated "block" hits in search and as
  explicit labeled edges via a dedicated `list_relationships` tool.
- Full text is retrievable in **bounded slices** (no token blowout).
- Corpus metadata and errors are **honest and actionable**.

## Non-Goals

- Fixing the bytes crash itself (that is PR #1841).
- New models, migrations, or embedding-generation changes.
- Reranking, hybrid fusion scoring, or cross-corpus search.
- Changes to the global (non-scoped) `/mcp` endpoint beyond what falls out of
  shared tool implementations.

## Architecture

All changes are confined to:

- `opencontractserver/mcp/tools.py` — tool implementations
- `opencontractserver/mcp/server.py` — scoped + global tool **schemas** and the
  tool-dispatch error formatting
- `opencontractserver/mcp/formatters.py` — response formatters
- `opencontractserver/constants/mcp.py` — new size/limit constants
- `opencontractserver/mcp/tests/test_mcp.py` — tests

Data access reuses existing services only:

- `AnnotationService.get_corpus_annotations(corpus_id, user, structural=...)` →
  permission-filtered `AnnotationQuerySet` (already accepts a `structural`
  tri-state filter; includes structural Text-Block chunks that carry body prose;
  the queryset has `search_by_embedding` via `VectorSearchViaEmbeddingMixin`).
- `CoreRelationshipVectorStore(corpus_id=...)` → corpus-scoped, visibility-filtered
  vector search over `OC_SUBTREE_GROUP` relationships (the embedded ancestor→subtree
  "blocks"; issue #1645). Uses the same corpus embedder, so block and passage cosine
  scores are directly comparable and mergeable.
- `RelationshipService.get_document_relationships(document_id, corpus_id, user)` →
  permission-filtered relationship queryset for explicit edge enumeration. A
  corpus-wide `get_corpus_relationships` (mirroring `get_corpus_annotations`) is
  added if not present.
- `CorpusDocumentService` for corpus/document gating (unchanged).

This honors the CLAUDE.md services-layer rule for MCP tools (no inline
`visible_to_user` / `user_can` composition).

**No new models or migrations.**

## Components

### Component 1 — `search_corpus` → unified passage + block feed (Issue A, extended by Issue E)

Rewrite `search_corpus` to return a single ranked feed mixing two result types,
discriminated by `type`:

- `type: "passage"` — an annotation hit.
- `type: "block"` — an `OC_SUBTREE_GROUP` relationship hit (ancestor + full
  descendant subtree), the embedded aggregation unit.

New params: `granularity` (`"passage" | "block" | "both"`, default `"both"`) and
`structural` (tri-state: `null` = both, `true` = structural only, `false` =
human/analysis only — applied to the passage half).

```
# Passage half (annotations)
qs = AnnotationService.get_corpus_annotations(corpus.id, user, structural=structural) \
        .select_related("document", "annotation_label")
embedder_path, query_vector = corpus.embed_text(query)
passages = []
if granularity in ("passage", "both"):
    if query_vector:
        passages = list(qs.search_by_embedding(query_vector, embedder_path, top_k=limit))
    if not passages:                          # empty OR no vector OR vector error
        passages = list(qs.filter(raw_text__icontains=query)[:limit])   # text fallback

# Block half (subtree-group relationships)
blocks = []
if granularity in ("block", "both") and query_vector:
    blocks = CoreRelationshipVectorStore(corpus_id=corpus.id, user=user).search(query, top_k=limit)

# Merge by similarity_score (same embedder → comparable), cap at limit
results = merge_by_score(
    [format_search_passage(a) for a in passages],
    [format_search_block(b) for b in blocks],
)[:limit]
return {"query": query, "results": results}
```

- The empty-vector case falls through to passage text search (fixes the
  dead-fallback bug). Vector errors (`ValueError`/`TypeError`/`AttributeError`/
  `RuntimeError`) are caught and also fall through.
- `format_search_passage(ann)` → `{type: "passage", document_slug, document_title,
  page, text, structural, similarity_score}` — `text` = `raw_text` truncated to
  `MCP_SEARCH_SNIPPET_MAX_CHARS`; `similarity_score` `null` on text fallback; the
  explicit `structural` flag delineates layout-derived vs human/analysis hits.
- `format_search_block(rel)` → `{type: "block", document_slug, document_title, page,
  label, text, member_count, similarity_score}` — `text` = aggregated subtree text
  truncated to `MCP_BLOCK_SNIPPET_MAX_CHARS`.
- Text-fallback passages (score `null`) sort after scored hits; block search only
  runs when a query vector exists (blocks are vector-only).
- Envelope `{query, results}` is unchanged (current output is empty, so nothing real
  regresses); each result now self-describes via `type`.

Schema/description (`server.py`): document the `type` discriminator, `granularity`
and `structural` params, and that results are semantic with a passage text fallback.

### Component 2 — `list_annotations` content search, ordering, structural filter (Issue B)

- Add optional `text_contains: str` → `qs.filter(raw_text__icontains=text_contains)`.
- Add optional `structural` tri-state filter (`null`/`true`/`false`) via
  `get_corpus_annotations(..., structural=...)` / document-scoped equivalent.
- Order results `("page", "id")` for stable reading order.
- Lean payload via `format_annotation`: keep `{id, page, raw_text,
  annotation_label:{text,label_type}, structural}` — the explicit `structural` flag
  delineates the two kinds; drop `color` and `created` (low signal, high token cost).
- Update schema + description for the new params.

> Note: `format_annotation` is shared with the annotation **resource** path. The lean
> shape will be applied consistently; the resource handler test is updated to match.

### Component 3 — `get_document_text` pagination (Issue C) — depends on #1841

- Add `char_offset: int = 0` and `max_chars: int = MCP_DOCUMENT_TEXT_DEFAULT_CHARS`
  (hard-capped at `MCP_DOCUMENT_TEXT_MAX_CHARS`).
- Return `{document_slug, page_count, total_chars, char_offset, text, next_offset, truncated}`
  where `next_offset` is `char_offset + len(text)` when more remains, else `null`.
- **Char-based, not page-based:** `txt_extract_file` is a flat string with no reliable
  page boundaries. Page-level access is served by Component 1 (returns `page`) +
  `list_annotations(page=N)`.
- Read routed through `read_field_file_text()` (from #1841). This commit is sequenced
  **last** and rebases on top of #1841 once it merges; if #1841 stalls, cherry-pick the
  helper.

### Component 4 — Polish (Issue D)

- `get_corpus_info`: return only labels **actually present** on the corpus's
  annotations — `get_corpus_annotations(corpus.id, user)` → distinct
  `annotation_label` (text/color/label_type/description), capped at the existing 50 —
  instead of the full seeded label set. Stops advertising irrelevant labels.
- Error handling in the tool dispatcher (`server.py` scoped + global `call_tool`,
  via `_format_tool_error_text`): map `Document.DoesNotExist` / `Corpus.DoesNotExist`
  to actionable messages that echo the attempted identifier and name the remediation
  tool (e.g. `No document 'x' in corpus 'y'. Call list_documents to see valid slugs.`).
  Keep `isError: true`. Never emit raw exception strings.
- Tighten `search_corpus` / `get_document_text` / `list_annotations` descriptions to
  state granularity and the search → read → cite workflow.

### Component 5 — relationships: unified search blocks + `list_relationships` (Issue E)

Two parts:

1. **Unified search "blocks"** — the block half of Component 1's feed
   (`format_search_block`, `granularity`, `CoreRelationshipVectorStore`). Specified
   in Component 1; tracked under Issue E because it is the relationship-aggregation
   surface.
2. **New `list_relationships` tool** for explicit graph navigation (distinct from
   search): `list_relationships(document_slug=None, structural=None, label_text=None,
   limit=50, offset=0)`. Returns labeled directed edges:

   ```
   {id, label, structural,
    source: [{annotation_id, page, text}],
    target: [{annotation_id, page, text}]}
   ```

   - Backed by `RelationshipService`: `get_document_relationships(document_id,
     corpus_id, user)` when `document_slug` is given, else a corpus-wide
     `get_corpus_relationships(corpus_id, user)` (added mirroring
     `get_corpus_annotations` if absent).
   - Filter by `structural` (tri-state) and `label_text` (exact label match).
   - Source/target annotation `text` truncated to `MCP_REL_ANNOTATION_TEXT_MAX_CHARS`.
   - New schema entry in both scoped (`get_scoped_tool_definitions`) and global tool
     lists, plus a handler in `get_scoped_tool_handlers`.

   The two surfaces answer different questions: search blocks = "what aggregated
   content is *relevant*"; `list_relationships` = "what is explicitly *connected*"
   (parent/child, cross-references, human- or analysis-drawn edges).

## Constants

Add to `opencontractserver/constants/mcp.py` (alongside `MAX_THREAD_MESSAGE_LENGTH`):

- `MCP_SEARCH_SNIPPET_MAX_CHARS` — passage `text` truncation (e.g. 1500)
- `MCP_BLOCK_SNIPPET_MAX_CHARS` — block (subtree-group) `text` truncation (e.g. 4000)
- `MCP_REL_ANNOTATION_TEXT_MAX_CHARS` — source/target annotation `text` in
  `list_relationships` (e.g. 500)
- `MCP_DOCUMENT_TEXT_DEFAULT_CHARS` — default `get_document_text` window (e.g. 50000)
- `MCP_DOCUMENT_TEXT_MAX_CHARS` — hard cap for `max_chars` (e.g. 200000)

Exact values finalized in the implementation plan.

## Error-handling philosophy

Keep the existing `isError` envelope (already correct). Humanize messages; echo the
identifier the caller supplied; point to the remediation tool. Do not leak raw
Python/Django exception text.

## Testing

Extend `opencontractserver/mcp/tests/test_mcp.py` (seed corpus + documents +
annotations; embeddings where the vector path is exercised):

- **search_corpus (passages):** vector path returns passages in the new shape;
  empty-vector → text-fallback returns `raw_text__icontains` matches; `type:"passage"`
  + `structural` flag present; `similarity_score` null on fallback.
- **search_corpus (unified feed):** with seeded subtree-group relationships, `granularity:"both"`
  returns interleaved `type:"passage"` and `type:"block"` hits sorted by score;
  `granularity:"passage"`/`"block"` restrict correctly; `structural=false` excludes
  structural passages.
- **list_relationships:** returns labeled source→target edges; `structural` and
  `label_text` filters work; corpus-wide (no `document_slug`) vs document-scoped;
  permission filtering via `RelationshipService`.
- **list_annotations:** `text_contains` filters by content; `structural` tri-state
  filter works; results ordered by page; lean payload shape asserted (no `color`/`created`).
- **get_document_text:** slicing by `char_offset`/`max_chars`; `next_offset`/`truncated`
  correctness; bytes-from-cloud-storage handled (via #1841 helper).
- **get_corpus_info:** only in-use labels returned (seeded-but-unused labels excluded).
- **errors:** invalid document slug → actionable message, `isError: true`, no raw
  exception text.

## Sequencing & dependencies

- Components 1, 2, 4, 5 are independent of #1841.
- Component 3 depends on #1841's `read_field_file_text`; its commit goes last and
  rebases once #1841 merges.
- Component 5's "block" half extends Component 1's `search_corpus`; land them as one
  search commit (or 1 then 5 in sequence) since they touch the same function. The
  `list_relationships` tool is additive and independent.
- One feature branch, one umbrella PR with 5 commits closing 5 tracking issues:
  - **A = search (unified feed)** → #1858 (Component 1)
  - **B = annotations (content search + structural filter)** → #1859 (Component 2)
  - **C = full-text (pagination)** → #1860 (Component 3, depends on #1841)
  - **D = polish** → #1861 (Component 4)
  - **E = relationships (search blocks + list_relationships)** → #1862 (Component 5)

## Risks

- **Annotation embeddings may not exist under the corpus's `embedder_path`** on some
  corpora; the text fallback guarantees non-empty results when matchable content
  exists, so search degrades gracefully rather than returning nothing.
- **Shared `format_annotation`** touches the resource path; covered by updating that
  test and verifying both call sites.
- **Subtree-group relationships may not be embedded** on a given corpus (depends on
  whether the parser materialized + embedded them). The block half then returns
  empty; the passage half still answers, so the unified feed degrades to passages —
  acceptable. Block search is vector-only (no text fallback) by design.
- **Score comparability across the two vector stores** relies on both using the same
  corpus embedder. The merge sorts by `similarity_score` and places text-fallback
  passages (score `null`) last; if a store returns scores on a different scale this
  ordering could skew — verified in the unified-feed test with seeded data.
