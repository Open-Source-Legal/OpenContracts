# MCP Knowledge-Tool UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an OpenContracts corpus usable as a low-friction knowledge tool over the public MCP interface — working passage+block search, content-searchable annotations, relationship enumeration, bounded full-text, and honest metadata/errors.

**Architecture:** All changes confined to `opencontractserver/mcp/` (tool impls, schemas, formatters) + `opencontractserver/constants/mcp.py` + one new `RelationshipService.get_corpus_relationships` method. Data access reuses existing services (`AnnotationService`, `RelationshipService`, `CoreRelationshipVectorStore`, `CorpusDocumentService`). No new models/migrations.

**Tech Stack:** Django 4.x, pgvector, the MCP `Server`/`Tool` types, `sync_to_async` dispatch (MCP tool handlers are sync). Tests: `opencontractserver/mcp/tests/test_mcp.py` (Django `TestCase`, `_MCPAsyncRunMixin`).

**Spec:** `docs/development/2026-05-31-mcp-knowledge-tool-ux-design.md`
**Issues:** #1858 search · #1859 annotations · #1860 full-text · #1861 polish · #1862 relationships

---

## File Structure

- `opencontractserver/constants/mcp.py` — add snippet/window size constants.
- `opencontractserver/mcp/formatters.py` — add `format_search_passage`, `format_search_block`; trim `format_annotation`.
- `opencontractserver/mcp/tools.py` — rewrite `search_corpus`; extend `list_annotations`; add `list_relationships`; update `get_corpus_info`, `get_document_text`; register `list_relationships` in `get_scoped_tool_handlers`/`TOOL_HANDLERS`.
- `opencontractserver/mcp/server.py` — update tool schemas (scoped `get_scoped_tool_definitions` + global `list_tools`); humanize `_format_tool_error_text`.
- `opencontractserver/annotations/services/relationship_service.py` — add `get_corpus_relationships`.
- `opencontractserver/utils/files.py` — add `read_field_file_text` (Task 6, only if #1841 not yet merged).
- `opencontractserver/mcp/tests/test_mcp.py` — tests per task.
- `CHANGELOG.md` — entry.

Commit order: Task 1 → 2 (#1858) → 3 (#1859) → 4 (#1862) → 5 (#1861) → 6 (#1860, last; rebases on #1841).

---

### Task 1: Constants + formatters foundation

**Files:**
- Modify: `opencontractserver/constants/mcp.py`
- Modify: `opencontractserver/mcp/formatters.py`
- Test: `opencontractserver/mcp/tests/test_mcp.py` (`MCPFormattersTest`)

- [ ] **Step 1: Add constants**

```python
# opencontractserver/constants/mcp.py — append
# Truncation budgets (characters) for MCP tool payloads. Keep AI-facing
# results bounded so a single tool call cannot blow the context window.
MCP_SEARCH_SNIPPET_MAX_CHARS: int = 1_500       # passage hit `text`
MCP_BLOCK_SNIPPET_MAX_CHARS: int = 4_000        # subtree-group block `text`
MCP_REL_ANNOTATION_TEXT_MAX_CHARS: int = 500    # source/target text in list_relationships
MCP_DOCUMENT_TEXT_DEFAULT_CHARS: int = 50_000   # default get_document_text window
MCP_DOCUMENT_TEXT_MAX_CHARS: int = 200_000      # hard cap for get_document_text max_chars
```

- [ ] **Step 2: Add a shared truncation helper + formatters**

```python
# opencontractserver/mcp/formatters.py — add near top (after imports)
def _truncate(text: str, max_chars: int) -> str:
    """Bound a string for AI-facing payloads, marking elision."""
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " …[truncated]"
```

```python
# opencontractserver/mcp/formatters.py — add new formatters
def format_search_passage(annotation: "Annotation", similarity_score=None) -> dict:
    """Format an annotation as a passage-level search hit."""
    from opencontractserver.constants.mcp import MCP_SEARCH_SNIPPET_MAX_CHARS

    return {
        "type": "passage",
        "document_slug": annotation.document.slug if annotation.document_id else None,
        "document_title": (annotation.document.title or "") if annotation.document_id else "",
        "page": annotation.page,
        "text": _truncate(annotation.raw_text or "", MCP_SEARCH_SNIPPET_MAX_CHARS),
        "structural": annotation.structural,
        "similarity_score": (
            float(similarity_score) if similarity_score is not None else None
        ),
    }


def format_search_block(result) -> dict:
    """Format a CoreRelationshipVectorStore result as a block-level search hit.

    ``result`` is a ``RelationshipVectorSearchResult`` (carries block_text,
    label_text, document_id, member ids — no extra DB reads needed).
    """
    from opencontractserver.constants.mcp import MCP_BLOCK_SNIPPET_MAX_CHARS
    from opencontractserver.documents.models import Document

    doc_slug, doc_title = None, ""
    if result.document_id:
        doc = Document.objects.filter(pk=result.document_id).only("slug", "title").first()
        if doc:
            doc_slug, doc_title = doc.slug, (doc.title or "")
    member_count = (1 if result.source_annotation_id else 0) + len(result.target_annotation_ids)
    return {
        "type": "block",
        "document_slug": doc_slug,
        "document_title": doc_title,
        "page": None,
        "label": result.label_text,
        "text": _truncate(result.block_text or "", MCP_BLOCK_SNIPPET_MAX_CHARS),
        "member_count": member_count,
        "similarity_score": float(result.similarity_score),
    }
```

- [ ] **Step 3: Trim `format_annotation` (drop color/created; keep structural delineation)**

```python
# opencontractserver/mcp/formatters.py — replace format_annotation body
def format_annotation(annotation: "Annotation") -> dict:
    """Format an annotation for API response (lean, AI-facing shape)."""
    label_data = None
    if annotation.annotation_label:
        label_data = {
            "text": annotation.annotation_label.text,
            "label_type": annotation.annotation_label.label_type,
        }
    return {
        "id": str(annotation.id),
        "page": annotation.page,
        "raw_text": annotation.raw_text or "",
        "annotation_label": label_data,
        "structural": annotation.structural,
    }
```

- [ ] **Step 4: Write failing formatter tests**

```python
# test_mcp.py — add to MCPFormattersTest
def test_format_search_passage_shape(self):
    from opencontractserver.mcp.formatters import format_search_passage
    # self.annotation seeded in setUpTestData (add if absent: see Task 2 fixtures)
    out = format_search_passage(self.annotation, similarity_score=0.81)
    self.assertEqual(out["type"], "passage")
    self.assertIn("structural", out)
    self.assertEqual(out["similarity_score"], 0.81)

def test_format_annotation_is_lean(self):
    from opencontractserver.mcp.formatters import format_annotation
    out = format_annotation(self.annotation)
    self.assertNotIn("color", out)
    self.assertNotIn("created", out)
    self.assertIn("structural", out)
```

- [ ] **Step 5: Run** `docker compose -f test.yml run --rm django pytest opencontractserver/mcp/tests/test_mcp.py::MCPFormattersTest -q` → PASS (add a `self.annotation` to `MCPFormattersTest.setUpTestData` if missing).

- [ ] **Step 6: Commit**

```bash
git add opencontractserver/constants/mcp.py opencontractserver/mcp/formatters.py opencontractserver/mcp/tests/test_mcp.py
git commit -m "feat(mcp): add search/block formatters + size constants; lean annotation payload"
```

---

### Task 2: `search_corpus` → unified passage + block feed (#1858, block half #1862)

**Files:**
- Modify: `opencontractserver/mcp/tools.py:219-306` (`search_corpus`, `_text_search_fallback`)
- Modify: `opencontractserver/mcp/server.py` (`get_scoped_tool_definitions` search_corpus schema + global `list_tools` search_corpus schema)
- Test: `opencontractserver/mcp/tests/test_mcp.py` (`MCPToolsSearchTest`)

- [ ] **Step 1: Write failing tests**

```python
# test_mcp.py — MCPToolsSearchTest
def test_search_returns_passages_with_type_and_structural(self):
    # embed_text mocked to raise -> text fallback path; corpus has an
    # annotation whose raw_text contains "Contract"
    from unittest.mock import patch
    with patch.object(self.corpus.__class__, "embed_text", side_effect=RuntimeError("no embed")):
        result = search_corpus(self.corpus.slug, "Contract")
    self.assertTrue(all(r["type"] == "passage" for r in result["results"]))
    self.assertTrue(all("structural" in r for r in result["results"]))
    self.assertTrue(all(r["similarity_score"] is None for r in result["results"]))

def test_search_text_fallback_searches_annotation_body(self):
    # Body word that is in annotation.raw_text but NOT in title/description
    from unittest.mock import patch
    with patch.object(self.corpus.__class__, "embed_text", side_effect=RuntimeError("no embed")):
        result = search_corpus(self.corpus.slug, self.body_only_term)
    self.assertGreater(len(result["results"]), 0)

def test_search_granularity_passage_excludes_blocks(self):
    from unittest.mock import patch
    with patch.object(self.corpus.__class__, "embed_text", side_effect=RuntimeError("no embed")):
        result = search_corpus(self.corpus.slug, "Contract", granularity="passage")
    self.assertTrue(all(r["type"] == "passage" for r in result["results"]))

def test_search_structural_false_excludes_structural_passages(self):
    from unittest.mock import patch
    with patch.object(self.corpus.__class__, "embed_text", side_effect=RuntimeError("no embed")):
        result = search_corpus(self.corpus.slug, "Contract", structural=False)
    self.assertTrue(all(r["structural"] is False for r in result["results"]))
```

In `MCPToolsSearchTest.setUpTestData`, ensure at least one **non-structural** annotation whose `raw_text` contains `"Contract"` and a body-only term (set `cls.body_only_term = "indemnification"` and seed an annotation with that text). Keep existing fixtures.

- [ ] **Step 2: Run** the 4 tests → FAIL (`search_corpus() got an unexpected keyword argument 'granularity'`).

- [ ] **Step 3: Rewrite `search_corpus` + replace `_text_search_fallback`**

```python
# opencontractserver/mcp/tools.py — replace search_corpus and _text_search_fallback
def search_corpus(
    corpus_slug: str,
    query: str,
    limit: int = 10,
    granularity: str = "both",            # "passage" | "block" | "both"
    structural: bool | None = None,       # None=both, True=structural only, False=human only
    user: UserOrAnonymous | None = None,
) -> dict:
    """Search a corpus and return a single ranked feed of passages and blocks.

    - ``passage`` hits are annotations (semantic via embeddings, text fallback
      on empty/absent vector).
    - ``block`` hits are ``OC_SUBTREE_GROUP`` relationships (ancestor + full
      descendant subtree) via ``CoreRelationshipVectorStore`` — the aggregation
      unit. Blocks are vector-only (no text fallback).
    """
    from opencontractserver.annotations.services import AnnotationService
    from opencontractserver.corpuses.models import Corpus

    from .formatters import format_search_block, format_search_passage

    limit = min(limit, 50)
    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    embedder_path, query_vector = None, None
    try:
        embedder_path, query_vector = corpus.embed_text(query)
    except (ValueError, TypeError, AttributeError, RuntimeError):
        embedder_path, query_vector = None, None

    formatted: list[dict] = []

    # --- passage half ---
    if granularity in ("passage", "both"):
        ann_qs = AnnotationService.get_corpus_annotations(
            corpus.id, user, structural=structural
        ).select_related("document", "annotation_label")
        passages = []
        if query_vector:
            try:
                passages = list(
                    ann_qs.search_by_embedding(query_vector, embedder_path, top_k=limit)
                )
            except (ValueError, TypeError, AttributeError, RuntimeError):
                passages = []
        if not passages:
            passages = list(ann_qs.filter(raw_text__icontains=query)[:limit])
        for a in passages:
            formatted.append(
                format_search_passage(a, getattr(a, "similarity_score", None))
            )

    # --- block half (vector-only) ---
    if granularity in ("block", "both") and query_vector:
        from opencontractserver.llms.vector_stores.core_relationship_vector_store import (
            CoreRelationshipVectorStore,
            RelationshipVectorSearchQuery,
        )

        try:
            store = CoreRelationshipVectorStore(
                user_id=getattr(user, "pk", None),
                corpus_id=corpus.id,
                embedder_path=embedder_path,
                embed_dim=len(query_vector),
            )
            blocks = store.search(
                RelationshipVectorSearchQuery(
                    query_embedding=query_vector, similarity_top_k=limit
                )
            )
            formatted.extend(format_search_block(b) for b in blocks)
        except (ValueError, TypeError, AttributeError, RuntimeError):
            pass

    # Merge by score; text-fallback passages (None) sort last; cap at limit.
    formatted.sort(
        key=lambda r: (r["similarity_score"] is not None, r["similarity_score"] or 0.0),
        reverse=True,
    )
    return {"query": query, "results": formatted[:limit]}
```

Delete `_text_search_fallback` (now dead). Verify no other references: `grep -rn "_text_search_fallback" opencontractserver/`.

- [ ] **Step 4: Run** the 4 tests → PASS.

- [ ] **Step 5: Update tool schemas** in `server.py`

In `get_scoped_tool_definitions`, replace the `search_corpus` Tool's `inputSchema.properties` with:

```python
"properties": {
    "query": {"type": "string", "description": "Search query"},
    "limit": {"type": "integer", "default": 10, "description": "Max hits (1-50)"},
    "granularity": {
        "type": "string",
        "enum": ["passage", "block", "both"],
        "default": "both",
        "description": "passage = annotation hits; block = aggregated subtree-group hits; both = merged feed",
    },
    "structural": {
        "type": "boolean",
        "description": "Filter passages: omit=all, true=structural only, false=human/analysis only",
    },
},
"required": ["query"],
```

And update its `description` to: `f"Search the '{corpus_slug}' corpus. Returns a ranked feed of passage and block hits (each tagged 'type'); semantic with a text fallback."`. Mirror the same property additions in the **global** `list_tools` `search_corpus` Tool (`server.py:514-688`).

- [ ] **Step 6: Run full search + schema sanity**

`docker compose -f test.yml run --rm django pytest opencontractserver/mcp/tests/test_mcp.py::MCPToolsSearchTest -q` → PASS.

- [ ] **Step 7: Commit**

```bash
git add opencontractserver/mcp/tools.py opencontractserver/mcp/server.py opencontractserver/mcp/tests/test_mcp.py
git commit -m "feat(mcp): unified passage+block search feed with granularity & structural filter (#1858, #1862)"
```

---

### Task 3: `list_annotations` content search, ordering, structural filter (#1859)

**Files:**
- Modify: `opencontractserver/mcp/tools.py:163-216` (`list_annotations`)
- Modify: `opencontractserver/mcp/server.py` scoped + global `list_annotations` schema
- Test: `opencontractserver/mcp/tests/test_mcp.py` (`MCPToolsAnnotationsTest`)

- [ ] **Step 1: Write failing tests**

```python
# test_mcp.py — MCPToolsAnnotationsTest
def test_list_annotations_text_contains(self):
    result = list_annotations(self.corpus.slug, self.document.slug, text_contains=self.known_substr)
    self.assertGreater(result["total_count"], 0)
    self.assertTrue(all(self.known_substr.lower() in a["raw_text"].lower() for a in result["annotations"]))

def test_list_annotations_structural_filter(self):
    result = list_annotations(self.corpus.slug, self.document.slug, structural=False)
    self.assertTrue(all(a["structural"] is False for a in result["annotations"]))

def test_list_annotations_ordered_by_page(self):
    result = list_annotations(self.corpus.slug, self.document.slug, limit=100)
    pages = [a["page"] for a in result["annotations"]]
    self.assertEqual(pages, sorted(pages))

def test_list_annotations_payload_is_lean(self):
    result = list_annotations(self.corpus.slug, self.document.slug, limit=1)
    self.assertNotIn("color", result["annotations"][0])
    self.assertNotIn("created", result["annotations"][0])
```

Set `cls.known_substr` in `setUpTestData` to a substring present in a seeded annotation's `raw_text`. Ensure both a structural and non-structural annotation exist across ≥2 pages.

- [ ] **Step 2: Run** → FAIL (`unexpected keyword argument 'text_contains'`).

- [ ] **Step 3: Implement**

```python
# tools.py — list_annotations signature + body changes
def list_annotations(
    corpus_slug: str,
    document_slug: str,
    page: int | None = None,
    label_text: str | None = None,
    text_contains: str | None = None,
    structural: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    user: UserOrAnonymous | None = None,
) -> dict:
    ...
    qs = AnnotationService.get_document_annotations(
        document_id=document.id, user=user, corpus_id=corpus.id
    )
    if page is not None:
        qs = qs.filter(page=page)
    if label_text:
        qs = qs.filter(annotation_label__text=label_text)
    if text_contains:
        qs = qs.filter(raw_text__icontains=text_contains)
    if structural is not None:
        qs = qs.filter(structural=structural)
    qs = qs.order_by("page", "id")
    total_count = qs.count()
    annotations = list(qs.select_related("annotation_label")[offset : offset + limit])
    return {
        "total_count": total_count,
        "annotations": [format_annotation(a) for a in annotations],
    }
```

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Update schemas** — add to scoped + global `list_annotations` `inputSchema.properties`:

```python
"text_contains": {"type": "string", "description": "Filter annotations whose text contains this substring"},
"structural": {"type": "boolean", "description": "Filter: omit=all, true=structural only, false=human/analysis only"},
```

- [ ] **Step 6: Run** `...::MCPToolsAnnotationsTest -q` → PASS.

- [ ] **Step 7: Commit**

```bash
git add opencontractserver/mcp/tools.py opencontractserver/mcp/server.py opencontractserver/mcp/tests/test_mcp.py
git commit -m "feat(mcp): list_annotations content search + structural filter + page ordering (#1859)"
```

---

### Task 4: `list_relationships` tool + `get_corpus_relationships` (#1862)

**Files:**
- Modify: `opencontractserver/annotations/services/relationship_service.py` (add `get_corpus_relationships`)
- Modify: `opencontractserver/mcp/tools.py` (add `list_relationships`, register in `get_scoped_tool_handlers`)
- Modify: `opencontractserver/mcp/server.py` (scoped + global tool schema + global `TOOL_HANDLERS` registration)
- Modify: `opencontractserver/mcp/formatters.py` (add `format_relationship`)
- Test: `opencontractserver/mcp/tests/test_mcp.py` (new `MCPToolsRelationshipsTest`)

- [ ] **Step 1: Add `get_corpus_relationships` to RelationshipService**

```python
# relationship_service.py — new classmethod (mirrors get_corpus_annotations scoping)
@classmethod
def get_corpus_relationships(cls, corpus_id: int, user, structural=None) -> QuerySet:
    """Corpus-wide relationships visible to ``user`` (mirrors get_corpus_annotations).

    Includes corpus-FK relationships, relationships on visible corpus documents,
    and structural relationships linked via those documents' structural sets.
    """
    from opencontractserver.annotations.models import Relationship
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    try:
        corpus = Corpus.objects.visible_to_user(user).get(id=corpus_id)
    except Corpus.DoesNotExist:
        return Relationship.objects.none()

    doc_ids = CorpusDocumentService.get_corpus_documents(
        user=user, corpus=corpus, include_deleted=False
    ).values_list("id", flat=True)

    from opencontractserver.annotations.models import StructuralAnnotationSet

    set_ids = StructuralAnnotationSet.objects.filter(
        documents__in=doc_ids
    ).values_list("id", flat=True)

    qs = Relationship.objects.filter(
        Q(corpus_id=corpus_id)
        | Q(document_id__in=doc_ids)
        | Q(structural=True, structural_set_id__in=set_ids)
    )
    if structural is not None:
        qs = qs.filter(structural=structural)
    return qs.distinct()
```

- [ ] **Step 2: Add `format_relationship` formatter**

```python
# formatters.py
def format_relationship(rel) -> dict:
    """Format a Relationship as labeled source->target edges."""
    from opencontractserver.constants.mcp import MCP_REL_ANNOTATION_TEXT_MAX_CHARS

    def _node(a):
        return {
            "annotation_id": str(a.id),
            "page": a.page,
            "text": _truncate(a.raw_text or "", MCP_REL_ANNOTATION_TEXT_MAX_CHARS),
        }

    return {
        "id": str(rel.id),
        "label": rel.relationship_label.text if rel.relationship_label_id else None,
        "structural": rel.structural,
        "source": [_node(a) for a in rel.source_annotations.all()],
        "target": [_node(a) for a in rel.target_annotations.all()],
    }
```

- [ ] **Step 3: Add `list_relationships` tool**

```python
# tools.py
def list_relationships(
    corpus_slug: str,
    document_slug: str | None = None,
    structural: bool | None = None,
    label_text: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: UserOrAnonymous | None = None,
) -> dict:
    """List labeled source->target relationships in the corpus (or one document)."""
    from opencontractserver.annotations.services.relationship_service import (
        RelationshipService,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    from .formatters import format_relationship

    limit = min(limit, 100)
    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)

    if document_slug:
        document = CorpusDocumentService.get_corpus_document_by_slug(
            user=user, corpus=corpus, slug=document_slug
        )
        qs = RelationshipService.get_document_relationships(
            document_id=document.id, user=user, corpus_id=corpus.id, structural=structural
        )
    else:
        qs = RelationshipService.get_corpus_relationships(
            corpus_id=corpus.id, user=user, structural=structural
        )

    if label_text:
        qs = qs.filter(relationship_label__text=label_text)

    qs = qs.prefetch_related("source_annotations", "target_annotations").select_related(
        "relationship_label"
    ).order_by("id")
    total_count = qs.count()
    rels = list(qs[offset : offset + limit])
    return {
        "total_count": total_count,
        "relationships": [format_relationship(r) for r in rels],
    }
```

- [ ] **Step 4: Register handler + schema**

In `tools.py:get_scoped_tool_handlers`, add:
```python
"list_relationships": create_scoped_tool_wrapper(list_relationships, corpus_slug),
```
In `server.py:get_scoped_tool_definitions`, append a `Tool(name="list_relationships", description="List labeled source→target relationships in the corpus (or a single document)", inputSchema={...})` with properties `document_slug, structural, label_text, limit (default 50), offset (default 0)`, none required. Mirror in global `list_tools` (with `corpus_slug` required) and add `list_relationships` to the global `TOOL_HANDLERS` map.

- [ ] **Step 5: Write tests** (`MCPToolsRelationshipsTest`)

```python
class MCPToolsRelationshipsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # seed corpus, doc, 2 annotations, 1 non-structural Relationship
        # (label "cross-reference") source=ann_a target=ann_b
        ...
    def test_list_relationships_returns_edges(self):
        from opencontractserver.mcp.tools import list_relationships
        result = list_relationships(self.corpus.slug, self.document.slug)
        self.assertGreaterEqual(result["total_count"], 1)
        rel = result["relationships"][0]
        self.assertEqual(rel["label"], "cross-reference")
        self.assertTrue(rel["source"] and rel["target"])
    def test_list_relationships_structural_filter(self):
        from opencontractserver.mcp.tools import list_relationships
        result = list_relationships(self.corpus.slug, structural=False)
        self.assertTrue(all(r["structural"] is False for r in result["relationships"]))
    def test_list_relationships_corpus_wide(self):
        from opencontractserver.mcp.tools import list_relationships
        result = list_relationships(self.corpus.slug)  # no document_slug
        self.assertGreaterEqual(result["total_count"], 1)
```

- [ ] **Step 6: Run** `...::MCPToolsRelationshipsTest -q` → PASS. Also run a scoped dispatch test asserting `list_relationships` appears in `get_scoped_tool_definitions(slug)` names.

- [ ] **Step 7: Commit**

```bash
git add opencontractserver/annotations/services/relationship_service.py opencontractserver/mcp/tools.py opencontractserver/mcp/server.py opencontractserver/mcp/formatters.py opencontractserver/mcp/tests/test_mcp.py
git commit -m "feat(mcp): list_relationships tool + RelationshipService.get_corpus_relationships (#1862)"
```

---

### Task 5: Polish — in-use labels, actionable errors, descriptions (#1861)

**Files:**
- Modify: `opencontractserver/mcp/tools.py:555-610` (`get_corpus_info`)
- Modify: `opencontractserver/mcp/server.py:359-376` (`_format_tool_error_text`) + tool descriptions
- Test: `opencontractserver/mcp/tests/test_mcp.py`

- [ ] **Step 1: Failing tests**

```python
def test_get_corpus_info_only_in_use_labels(self):
    from opencontractserver.mcp.tools import get_corpus_info
    out = get_corpus_info(self.corpus.slug)
    label_texts = {l["text"] for l in (out["label_set"]["labels"] if out["label_set"] else [])}
    self.assertIn(self.used_label_text, label_texts)
    self.assertNotIn(self.unused_label_text, label_texts)

def test_invalid_document_slug_actionable_error(self):
    # via dispatcher: error text names remediation, no raw "matching query"
    ...  # call get_document_text with bad slug, assert "list_documents" in message
```

Seed a label set on the corpus with one **used** label (on an annotation) and one **unused** label.

- [ ] **Step 2: `get_corpus_info` — filter to in-use labels**

```python
# tools.py get_corpus_info — replace label collection
from opencontractserver.annotations.services import AnnotationService

used_label_ids = set(
    AnnotationService.get_corpus_annotations(corpus.id, user)
    .exclude(annotation_label__isnull=True)
    .values_list("annotation_label_id", flat=True)
    .distinct()
)
label_set_data = None
if corpus.label_set:
    labels = []
    for label in list(corpus.label_set.annotation_labels.all()):
        if label.id in used_label_ids:
            labels.append({
                "text": label.text,
                "color": label.color or "#000000",
                "label_type": label.label_type,
                "description": label.description or "",
            })
        if len(labels) >= 50:
            break
    label_set_data = {
        "title": corpus.label_set.title or "",
        "description": corpus.label_set.description or "",
        "labels": labels,
    }
```

- [ ] **Step 3: Humanize errors in `_format_tool_error_text`**

```python
# server.py _format_tool_error_text — add before final return
from django.core.exceptions import ObjectDoesNotExist
if isinstance(e, ObjectDoesNotExist):
    name = type(e).__name__  # e.g. "DoesNotExist" on Document/Corpus
    cls_name = getattr(getattr(e, "__class__", None), "__qualname__", "")
    if "Document" in cls_name or "document" in str(e).lower():
        return ("No matching document was found in this corpus. "
                "Call list_documents to see valid document_slug values.")
    if "Corpus" in cls_name or "corpus" in str(e).lower():
        return ("No matching corpus was found. "
                "Call list_public_corpuses to see valid corpus_slug values.")
    return "The requested item was not found."
```

Also extend the dispatcher catch: in both `call_tool_handler` (`server.py:448`) and the scoped `call_tool`, add `ObjectDoesNotExist` alongside `(PermissionDenied, ValidationError)` so DoesNotExist is returned as a structured `isError` result instead of raising (it currently raises → generic transport error). Import `ObjectDoesNotExist`.

- [ ] **Step 4: Tighten descriptions** — `search_corpus` (done Task 2), `get_document_text` → `"Get extracted document text in bounded slices (char_offset/max_chars)"`, `list_annotations` → `"List/search a document's annotations (filter by page, label_text, text_contains, structural)"`. Update in scoped + global schemas.

- [ ] **Step 5: Run** the polish tests + `MCPToolsTest` (dispatcher) → PASS.

- [ ] **Step 6: Commit**

```bash
git add opencontractserver/mcp/tools.py opencontractserver/mcp/server.py opencontractserver/mcp/tests/test_mcp.py
git commit -m "feat(mcp): in-use corpus labels, actionable not-found errors, sharper descriptions (#1861)"
```

---

### Task 6: `get_document_text` pagination (#1860) — LAST, depends on #1841

**Files:**
- Modify: `opencontractserver/mcp/tools.py:121-160` (`get_document_text`)
- Modify: `opencontractserver/mcp/server.py` scoped + global `get_document_text` schema
- Modify (only if #1841 NOT merged): `opencontractserver/utils/files.py` (add `read_field_file_text`)
- Test: `opencontractserver/mcp/tests/test_mcp.py` (`MCPToolsDocumentsTest`)

- [ ] **Step 1: Rebase check.** `git fetch origin && git log origin/main --oneline | grep -i 1841`. If #1841 is in main, rebase this branch onto it and SKIP adding the helper (import the existing one). If not, add `read_field_file_text` to `utils/files.py` verbatim from PR #1841 (single source of truth; reconciles trivially when #1841 merges).

- [ ] **Step 2: Failing tests**

```python
def test_get_document_text_pagination(self):
    full = get_document_text(self.corpus.slug, self.doc1.slug)["text"]
    page1 = get_document_text(self.corpus.slug, self.doc1.slug, char_offset=0, max_chars=10)
    self.assertEqual(page1["text"], full[:10])
    self.assertEqual(page1["char_offset"], 0)
    self.assertEqual(page1["next_offset"], 10 if len(full) > 10 else None)
    self.assertEqual(page1["truncated"], len(full) > 10)
    self.assertEqual(page1["total_chars"], len(full))

def test_get_document_text_offset_tail(self):
    full = get_document_text(self.corpus.slug, self.doc1.slug)["text"]
    tail = get_document_text(self.corpus.slug, self.doc1.slug, char_offset=5, max_chars=100000)
    self.assertEqual(tail["text"], full[5:])
    self.assertIsNone(tail["next_offset"])
```

(`get_document_text` with no slice args returns the full text → keep default `max_chars=MCP_DOCUMENT_TEXT_DEFAULT_CHARS`; for docs shorter than the default the existing tests still pass.)

- [ ] **Step 3: Implement**

```python
# tools.py get_document_text
def get_document_text(
    corpus_slug: str,
    document_slug: str,
    char_offset: int = 0,
    max_chars: int | None = None,
    user: UserOrAnonymous | None = None,
) -> dict:
    from opencontractserver.constants.mcp import (
        MCP_DOCUMENT_TEXT_DEFAULT_CHARS,
        MCP_DOCUMENT_TEXT_MAX_CHARS,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService
    from opencontractserver.utils.files import read_field_file_text

    user = user or AnonymousUser()
    corpus = Corpus.objects.visible_to_user(user).get(slug=corpus_slug)
    document = CorpusDocumentService.get_corpus_document_by_slug(
        user=user, corpus=corpus, slug=document_slug
    )

    full_text = ""
    if document.txt_extract_file:
        try:
            full_text = read_field_file_text(document.txt_extract_file, errors="replace")
        except Exception:
            full_text = ""

    total = len(full_text)
    char_offset = max(0, int(char_offset))
    window = MCP_DOCUMENT_TEXT_DEFAULT_CHARS if max_chars is None else max_chars
    window = max(0, min(int(window), MCP_DOCUMENT_TEXT_MAX_CHARS))
    end = char_offset + window
    text = full_text[char_offset:end]
    next_offset = end if end < total else None
    return {
        "document_slug": document.slug,
        "page_count": document.page_count or 0,
        "total_chars": total,
        "char_offset": char_offset,
        "text": text,
        "next_offset": next_offset,
        "truncated": next_offset is not None,
    }
```

- [ ] **Step 4: Update schema** — add `char_offset` (integer, default 0) and `max_chars` (integer) to scoped + global `get_document_text` properties.

- [ ] **Step 5: Run** `...::MCPToolsDocumentsTest -q` → PASS (existing bytes-from-cloud test continues to pass via the helper).

- [ ] **Step 6: Commit**

```bash
git add opencontractserver/mcp/tools.py opencontractserver/mcp/server.py opencontractserver/mcp/tests/test_mcp.py opencontractserver/utils/files.py
git commit -m "feat(mcp): bounded get_document_text slicing via char_offset/max_chars (#1860)"
```

---

### Task 7: Changelog + full MCP suite + PR

- [ ] **Step 1:** Add a `CHANGELOG.md` `[Unreleased]` entry summarizing the 5 components with issue refs.
- [ ] **Step 2:** Run the full MCP suite: `docker compose -f test.yml run --rm django pytest opencontractserver/mcp/tests/test_mcp.py -n 4 --dist loadscope -q` → all PASS.
- [ ] **Step 3:** `pre-commit run --files <changed>` → clean.
- [ ] **Step 4:** Commit changelog; push branch; open umbrella draft PR (body lists components, `Closes #1858 #1859 #1860 #1861 #1862`, notes #1841 dependency for Task 6).

---

## Self-Review

- **Spec coverage:** passage feed (Task 2) ✓, text fallback fix (Task 2) ✓, structural filter+flag (Tasks 2,3) ✓, content search+ordering+lean payload (Task 3) ✓, blocks+granularity (Task 2) ✓, list_relationships+get_corpus_relationships (Task 4) ✓, in-use labels+errors+descriptions (Task 5) ✓, get_document_text pagination+#1841 (Task 6) ✓, constants (Task 1) ✓, tests for each (every task) ✓.
- **Placeholders:** fixture `...` in test stubs are explicitly described (seed instructions inline); no TODO/TBD in production code steps.
- **Type consistency:** `format_search_passage(annotation, similarity_score=None)`, `format_search_block(result)`, `format_relationship(rel)`, `read_field_file_text(field_file, errors=)`, `get_corpus_relationships(corpus_id, user, structural=)` used consistently across tasks.
