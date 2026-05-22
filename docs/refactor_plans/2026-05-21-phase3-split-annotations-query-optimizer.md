# Phase 3 — Split `annotations/query_optimizer.py` + Relocate Misfiled Optimizers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the 1,507-line `annotations/query_optimizer.py` monolith into focused service modules and move the two misfiled optimizer classes (`Analysis`, `Extract`) plus `MetadataQueryOptimizer` into their correct apps' `services/` packages.

**Architecture:** Pure relocation + encapsulation, no behavior change. Each optimizer class becomes a `*Service` class inheriting `shared.services.BaseService`, living in a per-app `services/` package (one module per responsibility). The "query optimizer" term is retired as a public concept. Existing optimizer tests are the regression gate.

**Tech Stack:** Django 4.x, Python 3.x, pytest / Django test runner, Docker Compose test harness.

**Tracking issue:** #1717 (Service Layer Centralization — Phase 3). Depends on Phase 1 (#1715, merged: `shared/services/`).

---

## Background & Decisions

### What moves where

| Current class (`annotations/query_optimizer.py`) | New class | New module |
|---|---|---|
| `AnnotationQueryOptimizer` | `AnnotationService` | `annotations/services/annotation_service.py` |
| `RelationshipQueryOptimizer` | `RelationshipService` | `annotations/services/relationship_service.py` |
| `AnalysisQueryOptimizer` | `AnalysisService` | `analyzer/services/analysis_service.py` |
| `ExtractQueryOptimizer` | `ExtractService` | `extracts/services/extract_service.py` |

| Current class (`extracts/query_optimizer.py`) | New class | New module |
|---|---|---|
| `MetadataQueryOptimizer` | `MetadataService` | `extracts/services/metadata.py` |

Both `opencontractserver/annotations/query_optimizer.py` and `opencontractserver/extracts/query_optimizer.py` are **deleted** at the end (No-dead-code rule).

### Key decisions

1. **No backward-compat shim.** Unlike Phase 2's `corpus_objs_service.py` shim, Phase 3 updates *every* call site (production + tests) in one PR and deletes the old modules outright. Rationale: the issue says "Update all GraphQL call sites" and "relocate"; CLAUDE.md No-dead-code rule; a relocation shim would mask import drift. If the reviewer prefers a one-release `DeprecationWarning` shim, that is a small additive change — flagged, not assumed.

2. **Relocate, do not rewrite.** Method bodies are copied verbatim. The only edits inside moved code are: (a) class rename, (b) `class X:` → `class X(BaseService):`, (c) updating the cross-class references `RelationshipQueryOptimizer`→`RelationshipService` makes to `AnnotationQueryOptimizer`, (d) the module docstring. Private `_`-prefixed helpers keep their names and bodies. No method renames. Prefetch / `select_related` / bulk-permission / request-cache logic is untouched.

3. **Method names unchanged.** The public surface (`get_document_annotations`, `get_visible_analyses`, `check_extract_permission`, `validate_metadata_column`, etc.) is already `get_*`/`check_*`/`validate_*`. The issue's "expose public `get_*`/`list_*` methods" is already satisfied; renaming would be a rewrite. Keep as-is.

4. **`BaseService` inheritance** is architectural conformance (design doc §5.3). These services keep their own bespoke permission logic — they do not currently call `BaseService.get_or_none`/`filter_visible`/`require_permission`. That is acceptable for Phase 3; deeper consolidation onto `BaseService` helpers is out of scope (future phase).

### Flagged issues (report to reviewer, do NOT fix in Phase 3)

- **F1 — Tier-0 → Tier-1 layering inversion.** `shared/Managers.py` calls `AnnotationQueryOptimizer._compute_effective_permissions` (a *private* method) from a Tier-0 model manager. After the move this becomes `AnnotationService._compute_effective_permissions` — a manager reaching into a service's private internals, the reverse of the intended Tier 1→Tier 0 direction (design doc §5.1). Preserved verbatim here; should be addressed when `BaseService` permission helpers mature (Phase 6).
- **F2 — The issue's call-site list is incomplete.** Issue #1717 names `extract_queries.py`, `extract_mutations.py`, `corpus_queries.py`, `extract_types.py`. The actual production call sites also include `annotation_queries.py`, `corpus_types.py`, `custom_resolvers.py`, `document_types.py` (8 imports), `mcp/resources.py`, `mcp/tools.py`, `shared/Managers.py` (2), and `documents/query_optimizer.py` (3). This plan covers all of them.
- **F3 — Dead code in the moved files.** `AnnotationQueryOptimizer._check_document_permission` and `AnnotationQueryOptimizer._apply_permission_filter` / `RelationshipQueryOptimizer._apply_permission_filter` are self-documented `DEPRECATED` and appear unused (verify via grep during Task 1). Per "relocate, do not rewrite" they are moved as-is; recommend a follow-up cleanup. If the Task 1 grep confirms zero references, deleting them is a reasonable in-scope cleanup — call it out in the commit message either way.
- **F4 — Inconsistent request threading.** `MetadataQueryOptimizer._compute_effective_permissions` takes no `context`/`request` (uses raw `get_users_permissions_for_obj`), while `AnnotationQueryOptimizer._compute_effective_permissions` takes `context`. Two conventions survive the move untouched; unifying them is Phase 4/6 work.

---

## File Structure

**New files (8):**
- `opencontractserver/annotations/services/__init__.py` — re-exports `AnnotationService`, `RelationshipService`.
- `opencontractserver/annotations/services/annotation_service.py` — `AnnotationService` (from `AnnotationQueryOptimizer`).
- `opencontractserver/annotations/services/relationship_service.py` — `RelationshipService` (from `RelationshipQueryOptimizer`).
- `opencontractserver/analyzer/services/__init__.py` — re-exports `AnalysisService`.
- `opencontractserver/analyzer/services/analysis_service.py` — `AnalysisService` (from `AnalysisQueryOptimizer`).
- `opencontractserver/extracts/services/__init__.py` — re-exports `ExtractService`, `MetadataService`.
- `opencontractserver/extracts/services/extract_service.py` — `ExtractService` (from `ExtractQueryOptimizer`).
- `opencontractserver/extracts/services/metadata.py` — `MetadataService` (from `MetadataQueryOptimizer`).

**Deleted files (2):**
- `opencontractserver/annotations/query_optimizer.py`
- `opencontractserver/extracts/query_optimizer.py`

**Modified production files (14):**
- `config/graphql/annotation_queries.py`, `corpus_queries.py`, `corpus_types.py`, `custom_resolvers.py`, `document_types.py`, `extract_mutations.py`, `extract_queries.py`, `extract_types.py`
- `opencontractserver/mcp/resources.py`, `opencontractserver/mcp/tools.py`
- `opencontractserver/shared/Managers.py`
- `opencontractserver/documents/query_optimizer.py`
- `opencontractserver/extracts/diff.py`, `opencontractserver/utils/importing.py` (stale doc-comment references only)

**Modified test files (12):** see Task 5.

**New test file (1):** `opencontractserver/tests/test_service_layer_phase3.py`.

---

## A note on TDD for this plan

This is a **relocation refactor with zero new behavior**. The existing optimizer test suite *is* the test suite — it is the regression gate the issue mandates. Standard red-green TDD ("write a failing test first") does not apply to moving code. Instead:

- Tasks 1–3 create the new modules; correctness is verified by running the *existing* tests against the new import paths in Task 5.
- Task 7 adds genuinely new tests for the new public surface (importability, `BaseService` inheritance, old-module removal).
- The plan commits frequently and runs targeted test files after each milestone.

---

## Task 1: Create `annotations/services/` package

**Files:**
- Create: `opencontractserver/annotations/services/__init__.py`
- Create: `opencontractserver/annotations/services/annotation_service.py`
- Create: `opencontractserver/annotations/services/relationship_service.py`

- [ ] **Step 1: Confirm dead-code status of deprecated helpers (F3)**

Run:
```bash
grep -rn "_check_document_permission\|_apply_permission_filter" --include=*.py config/ opencontractserver/
```
Expected: matches only inside `annotations/query_optimizer.py` itself. Record the result in the Task 9 commit message. (If external callers exist, keep the methods; if none, they still move verbatim in this plan — deletion is a separate reviewer call.)

- [ ] **Step 2: Create `annotation_service.py`**

Copy `opencontractserver/annotations/query_optimizer.py` lines 1–817 (module docstring + imports + the entire `AnnotationQueryOptimizer` class) into the new file, with these exact changes:

- Replace the module docstring (lines 1–5) with:
  ```python
  """Annotation fetch + permission service.

  Relocated from ``annotations/query_optimizer.py`` (Service Layer
  Centralization, Phase 3 — issue #1717). Direct database queries with
  smart prefetching and permission filtering; no caching layer.
  """
  ```
- Add to the imports block:
  ```python
  from opencontractserver.shared.services import BaseService
  ```
- Rename the class declaration `class AnnotationQueryOptimizer:` → `class AnnotationService(BaseService):`.
- Leave every method body, every `_`-prefixed helper, and every inline `from ... import ...` byte-for-byte identical.

- [ ] **Step 3: Create `relationship_service.py`**

Copy `opencontractserver/annotations/query_optimizer.py` lines 820–1093 (the `RelationshipQueryOptimizer` class) into the new file. Add a module docstring and imports header:

```python
"""Relationship fetch + permission service.

Relocated from ``annotations/query_optimizer.py`` (Service Layer
Centralization, Phase 3 — issue #1717).
"""

from typing import Optional

from django.db.models import Count, Q, QuerySet, Value

from opencontractserver.annotations.services.annotation_service import (
    AnnotationService,
)
from opencontractserver.shared.services import BaseService
```

Then paste the class body with these exact changes:
- `class RelationshipQueryOptimizer:` → `class RelationshipService(BaseService):`.
- Inside `get_document_relationships`: `AnnotationQueryOptimizer._compute_effective_permissions(` → `AnnotationService._compute_effective_permissions(` and `AnnotationQueryOptimizer._get_document_for_request(` → `AnnotationService._get_document_for_request(`.
- Inside `get_relationship_summary`: `AnnotationQueryOptimizer._compute_effective_permissions(` → `AnnotationService._compute_effective_permissions(`.
- All other lines (including the inner `from opencontractserver.annotations.models import Relationship` etc.) unchanged.

Note: the original `RelationshipQueryOptimizer` had no top-level Django imports (it relied on function-local imports); the header above adds the names its bodies reference (`Q`, `QuerySet`, `Value`, `Count`). Verify against the pasted body — if a name is only used function-locally, it can stay function-local instead. The safe move is to keep imports exactly where the original had them and only add the `AnnotationService` + `BaseService` imports. Prefer that: **keep the original's import placement; add only `AnnotationService` and `BaseService` imports.**

- [ ] **Step 4: Create `__init__.py`**

```python
"""Annotations service-layer package.

Service Layer Centralization, Phase 3 (issue #1717).
"""

from opencontractserver.annotations.services.annotation_service import (
    AnnotationService,
)
from opencontractserver.annotations.services.relationship_service import (
    RelationshipService,
)

__all__ = ["AnnotationService", "RelationshipService"]
```

- [ ] **Step 5: Smoke-test the imports**

Run:
```bash
docker compose -f test.yml run --rm django python -c "from opencontractserver.annotations.services import AnnotationService, RelationshipService; from opencontractserver.shared.services import BaseService; assert issubclass(AnnotationService, BaseService); assert issubclass(RelationshipService, BaseService); print('OK')"
```
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add opencontractserver/annotations/services/
git commit -m "Add annotations/services package (Phase 3, #1717)"
```

---

## Task 2: Create `analyzer/services/` package

**Files:**
- Create: `opencontractserver/analyzer/services/__init__.py`
- Create: `opencontractserver/analyzer/services/analysis_service.py`

- [ ] **Step 1: Create `analysis_service.py`**

Copy `opencontractserver/annotations/query_optimizer.py` lines 1096–1302 (the `AnalysisQueryOptimizer` class) into the new file. Header:

```python
"""Analysis fetch + permission service.

Relocated from ``annotations/query_optimizer.py`` — ``AnalysisQueryOptimizer``
was misfiled in the ``annotations`` app. Service Layer Centralization,
Phase 3 (issue #1717).
"""

from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Count, Exists, OuterRef, Q, QuerySet

from opencontractserver.shared.services import BaseService

if TYPE_CHECKING:
    from opencontractserver.analyzer.models import Analysis
```

Class change: `class AnalysisQueryOptimizer:` → `class AnalysisService(BaseService):`. All method bodies and function-local imports unchanged. (As in Task 1 Step 3, prefer keeping the original's function-local import placement; only the `BaseService` import and the `TYPE_CHECKING`/`QuerySet`/etc. names actually referenced at module scope need to be at the top. Verify the pasted body and trim the header to exactly what is used module-scoped.)

- [ ] **Step 2: Create `__init__.py`**

```python
"""Analyzer service-layer package.

Service Layer Centralization, Phase 3 (issue #1717).
"""

from opencontractserver.analyzer.services.analysis_service import AnalysisService

__all__ = ["AnalysisService"]
```

- [ ] **Step 3: Smoke-test**

Run:
```bash
docker compose -f test.yml run --rm django python -c "from opencontractserver.analyzer.services import AnalysisService; from opencontractserver.shared.services import BaseService; assert issubclass(AnalysisService, BaseService); print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add opencontractserver/analyzer/services/
git commit -m "Add analyzer/services package, relocate AnalysisService (Phase 3, #1717)"
```

---

## Task 3: Create `extracts/services/` package

**Files:**
- Create: `opencontractserver/extracts/services/__init__.py`
- Create: `opencontractserver/extracts/services/extract_service.py`
- Create: `opencontractserver/extracts/services/metadata.py`

- [ ] **Step 1: Create `extract_service.py`**

Copy `opencontractserver/annotations/query_optimizer.py` lines 1305–1507 (the `ExtractQueryOptimizer` class) into the new file. Header:

```python
"""Extract fetch + permission service.

Relocated from ``annotations/query_optimizer.py`` — ``ExtractQueryOptimizer``
was misfiled in the ``annotations`` app. Service Layer Centralization,
Phase 3 (issue #1717).
"""

from typing import TYPE_CHECKING, Any, Optional

from django.db.models import Exists, OuterRef, Q, QuerySet

from opencontractserver.shared.services import BaseService

if TYPE_CHECKING:
    from opencontractserver.extracts.models import Extract
```

Class change: `class ExtractQueryOptimizer:` → `class ExtractService(BaseService):`. Method bodies unchanged. Trim the header to exactly the names used at module scope.

- [ ] **Step 2: Create `metadata.py`**

Copy `opencontractserver/extracts/query_optimizer.py` lines 1–583 in full. Changes:
- Replace the module docstring with:
  ```python
  """Metadata (Datacell) fetch + permission service.

  Relocated from ``extracts/query_optimizer.py`` (Service Layer
  Centralization, Phase 3 — issue #1717). Same permission model as the
  annotation service: effective = MIN(document, corpus).
  """
  ```
- Add `from opencontractserver.shared.services import BaseService` to the import block.
- `class MetadataQueryOptimizer:` → `class MetadataService(BaseService):`.
- Everything else byte-for-byte identical (the existing `from __future__ import annotations`, `from collections import defaultdict`, `from django.db.models import QuerySet`, `from opencontractserver.extracts.models import Column, Datacell` all stay).

- [ ] **Step 3: Create `__init__.py`**

```python
"""Extracts service-layer package.

Service Layer Centralization, Phase 3 (issue #1717).
"""

from opencontractserver.extracts.services.extract_service import ExtractService
from opencontractserver.extracts.services.metadata import MetadataService

__all__ = ["ExtractService", "MetadataService"]
```

- [ ] **Step 4: Smoke-test**

Run:
```bash
docker compose -f test.yml run --rm django python -c "from opencontractserver.extracts.services import ExtractService, MetadataService; from opencontractserver.shared.services import BaseService; assert issubclass(ExtractService, BaseService); assert issubclass(MetadataService, BaseService); print('OK')"
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add opencontractserver/extracts/services/
git commit -m "Add extracts/services package, relocate ExtractService + MetadataService (Phase 3, #1717)"
```

---

## Task 4: Update production call sites

At this point the old `query_optimizer.py` files still exist (deleted in Task 6), so the app stays importable throughout. Each edit below: change the import path/symbol **and** rename every usage of the old class name *within that import's scope*.

**Mapping for symbol + import path:**

| Old symbol | New symbol | New import |
|---|---|---|
| `AnnotationQueryOptimizer` | `AnnotationService` | `from opencontractserver.annotations.services import AnnotationService` |
| `RelationshipQueryOptimizer` | `RelationshipService` | `from opencontractserver.annotations.services import RelationshipService` |
| `AnalysisQueryOptimizer` | `AnalysisService` | `from opencontractserver.analyzer.services import AnalysisService` |
| `ExtractQueryOptimizer` | `ExtractService` | `from opencontractserver.extracts.services import ExtractService` |
| `MetadataQueryOptimizer` | `MetadataService` | `from opencontractserver.extracts.services import MetadataService` |

> **CRITICAL — do not corrupt `DocumentRelationshipQueryOptimizer`.** `document_types.py` and `corpus_queries.py` also reference `DocumentRelationshipQueryOptimizer` (a *different*, Phase-4 class in `documents/query_optimizer.py`). Never run a blind `replace_all` of `RelationshipQueryOptimizer` — it would rewrite `DocumentRelationshipQueryOptimizer` too. Use targeted edits keyed on the surrounding import line.

- [ ] **Step 1: `config/graphql/annotation_queries.py`**

Import block at line 82 (`AnnotationQueryOptimizer`) → `AnnotationService`. Usages at lines 95, 108 (`AnnotationQueryOptimizer.get_document_annotations`, `AnnotationQueryOptimizer.get_corpus_annotations`) → `AnnotationService.*`.

- [ ] **Step 2: `config/graphql/corpus_queries.py`**

Import block at line 298 imports `AnalysisQueryOptimizer, ExtractQueryOptimizer` from `annotations.query_optimizer` → split into two imports: `from opencontractserver.analyzer.services import AnalysisService` and `from opencontractserver.extracts.services import ExtractService`. Usages at lines 362 (`AnalysisQueryOptimizer.get_visible_analyses`), 367 (`ExtractQueryOptimizer.get_visible_extracts`) → `AnalysisService.*` / `ExtractService.*`. Import at line 409 (`MetadataQueryOptimizer`) → `from opencontractserver.extracts.services import MetadataService`; usage on the following lines → `MetadataService.*`. Leave `DocumentRelationshipQueryOptimizer` (lines ~306, 381) untouched.

- [ ] **Step 3: `config/graphql/corpus_types.py`**

Import at line 234 (`AnnotationQueryOptimizer`) → `AnnotationService`; usage at line 249 → `AnnotationService.get_document_annotations`.

- [ ] **Step 4: `config/graphql/custom_resolvers.py`**

Import at line 95 (`AnnotationQueryOptimizer`) → `AnnotationService`; usages at lines 114, 141 → `AnnotationService.get_document_annotations`.

- [ ] **Step 5: `config/graphql/document_types.py`** (8 import blocks)

Lines 247, 273, 1006, 1111 import `AnnotationQueryOptimizer` → `AnnotationService`. Lines 306, 354, 1054, 1097 import `RelationshipQueryOptimizer` → `RelationshipService`. Update each import's in-scope usages:
- 247 → usage `AnnotationQueryOptimizer.get_document_annotations` at 251.
- 273 → usage at 284.
- 1006 → usage at 1032.
- 1111 → usage at 1118 (`get_extract_annotation_summary`).
- 306 → usage at 324 (`get_document_relationships`).
- 354 → usage at 364.
- 1054 → usage at 1071.
- 1097 → usage at 1104 (`get_relationship_summary`).
Leave the four `DocumentRelationshipQueryOptimizer` blocks (lines ~185–192, 411–419, 437–456) **untouched**.

- [ ] **Step 6: `config/graphql/extract_mutations.py`**

Imports at lines 388 and 473 (`MetadataQueryOptimizer`) → `from opencontractserver.extracts.services import MetadataService`; rename in-scope usages → `MetadataService.*`.

- [ ] **Step 7: `config/graphql/extract_queries.py`**

- Lines 157, 175, 196 import `ExtractQueryOptimizer` → `from opencontractserver.extracts.services import ExtractService`; usages → `ExtractService.*`.
- Lines 307, 321, 341 import `MetadataQueryOptimizer` → `MetadataService`; usages → `MetadataService.*`.
- Lines 426, 442 import `AnalysisQueryOptimizer` → `from opencontractserver.analyzer.services import AnalysisService`; usages → `AnalysisService.*`.

- [ ] **Step 8: `config/graphql/extract_types.py`**

- Lines 99, 168 import `ExtractQueryOptimizer` → `ExtractService`; usages → `ExtractService.*`.
- Lines 318, 336 import `AnalysisQueryOptimizer` → `AnalysisService`; usages → `AnalysisService.*`.

- [ ] **Step 9: `opencontractserver/mcp/resources.py`**

Import at line 126 (`AnnotationQueryOptimizer`) → `AnnotationService`; usage at line 142 → `AnnotationService.get_document_annotations`. Also update the prose comment at line 123 (`AnnotationQueryOptimizer's effective…` → `AnnotationService's effective…`).

- [ ] **Step 10: `opencontractserver/mcp/tools.py`**

Import at line 186 (`AnnotationQueryOptimizer`) → `AnnotationService`; usage at line 199 → `AnnotationService.get_document_annotations`.

- [ ] **Step 11: `opencontractserver/shared/Managers.py`**

Imports at lines 833 and 1146 (`AnnotationQueryOptimizer`) → `from opencontractserver.annotations.services import AnnotationService`. Usages `AnnotationQueryOptimizer._compute_effective_permissions` at lines 845 and 1157 → `AnnotationService._compute_effective_permissions`. Update the explanatory comments referencing `AnnotationQueryOptimizer` at lines 660, 827, 915, 1080 → `AnnotationService`. (This is flagged issue **F1** — the inversion is preserved deliberately.)

- [ ] **Step 12: `opencontractserver/documents/query_optimizer.py`**

This file is itself a Phase-4 optimizer (not moved now), but it *imports the relocated classes*. Update:
- Import block at line 70 (`AnalysisQueryOptimizer, ExtractQueryOptimizer`) → two imports: `from opencontractserver.analyzer.services import AnalysisService` and `from opencontractserver.extracts.services import ExtractService`. Usages at 113–114, 122 → `ExtractService.get_visible_extracts`, `AnalysisService.get_visible_analyses`.
- Import block at line 184 (`ExtractQueryOptimizer`) → `ExtractService`; usage at 201.
- Import block at line 226 (`AnalysisQueryOptimizer`) → `AnalysisService`; usage at 242.
- Update the docstring reference at line 31 (`Follows the least-privilege model from AnnotationQueryOptimizer`) → `AnnotationService`.

- [ ] **Step 13: Verify no stale production references remain**

Run:
```bash
grep -rn "QueryOptimizer\|query_optimizer" --include=*.py config/graphql/ opencontractserver/mcp/ opencontractserver/shared/Managers.py | grep -i "annotation\|extract\|analysis\|metadata" | grep -v "DocumentRelationshipQueryOptimizer"
```
Expected: no output. (Any remaining hit is a missed call site or a stale comment — fix it.)

- [ ] **Step 14: Django check**

Run:
```bash
docker compose -f test.yml run --rm django python manage.py check
```
Expected: `System check identified no issues`.

- [ ] **Step 15: Commit**

```bash
git add config/graphql/ opencontractserver/mcp/ opencontractserver/shared/Managers.py opencontractserver/documents/query_optimizer.py
git commit -m "Repoint production call sites to relocated services (Phase 3, #1717)"
```

---

## Task 5: Update test imports

Each test file below imports a relocated class. Update import paths/symbols using the Task 4 mapping. **Imports only** — no test logic, no assertions, no fixtures change (CLAUDE.md "don't touch old tests" — import-path updates forced by a relocation are mechanical and required; nothing else changes).

- [ ] **Step 1: Update single-symbol test imports**

In each file, repoint the import and rename in-file usages of the class:
- `opencontractserver/tests/performance_optimizations/test_base.py:10` — `AnnotationQueryOptimizer` → `AnnotationService`.
- `opencontractserver/tests/permissioning/test_comment_permission.py:25` — `AnnotationQueryOptimizer` → `AnnotationService`.
- `opencontractserver/tests/permissioning/test_metadata_query_optimizer.py:48` — `MetadataQueryOptimizer` → `MetadataService` (`from opencontractserver.extracts.services import MetadataService`).
- `opencontractserver/tests/permissioning/test_version_aware_query_optimizer.py:13` — `AnnotationQueryOptimizer` → `AnnotationService`.
- `opencontractserver/tests/test_annotation_privacy.py:17` — `AnnotationQueryOptimizer` → `AnnotationService`.
- `opencontractserver/tests/test_corpus_annotations_query.py:17` — `AnnotationQueryOptimizer` → `AnnotationService`.
- `opencontractserver/tests/test_get_document_knowledge_optimizations.py:30` — `AnnotationQueryOptimizer` → `AnnotationService`.
- `opencontractserver/tests/test_analysis_annotation_import.py:161` — `AnnotationQueryOptimizer` → `AnnotationService`.
- `opencontractserver/tests/test_structural_annotations_graphql_backwards_compat.py:876` — `RelationshipQueryOptimizer` → `RelationshipService`.
- `opencontractserver/tests/test_visibility_managers.py:626` — `AnnotationQueryOptimizer` → `AnnotationService` (usage `AnnotationQueryOptimizer._compute_effective_permissions` at line 629).

- [ ] **Step 2: Update multi-symbol test imports**

- `opencontractserver/tests/test_query_optimizer_structural_sets.py:23` imports `AnnotationQueryOptimizer, RelationshipQueryOptimizer` from `annotations.query_optimizer` → single import `from opencontractserver.annotations.services import AnnotationService, RelationshipService`. Rename usages throughout the file.
- `opencontractserver/tests/permissioning/test_query_optimizer_methods.py:46` imports `AnnotationQueryOptimizer, ExtractQueryOptimizer, RelationshipQueryOptimizer` → split: `from opencontractserver.annotations.services import AnnotationService, RelationshipService` **and** `from opencontractserver.extracts.services import ExtractService`. Also update the three function-local imports at lines 404, 1568, 1631 (`AnalysisQueryOptimizer` → `from opencontractserver.analyzer.services import AnalysisService`). Rename all in-file usages.

- [ ] **Step 3: Verify no stale test references remain**

Run:
```bash
grep -rn "AnnotationQueryOptimizer\|\bRelationshipQueryOptimizer\|AnalysisQueryOptimizer\|ExtractQueryOptimizer\|MetadataQueryOptimizer\|annotations.query_optimizer\|extracts.query_optimizer" --include=*.py opencontractserver/tests/
```
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add opencontractserver/tests/
git commit -m "Repoint optimizer test imports to relocated services (Phase 3, #1717)"
```

---

## Task 6: Delete the old `query_optimizer.py` monoliths

- [ ] **Step 1: Confirm zero remaining references**

Run:
```bash
grep -rn "annotations.query_optimizer\|annotations\.query_optimizer\|extracts.query_optimizer\|extracts\.query_optimizer" --include=*.py config/ opencontractserver/
```
Expected: no output (`documents/query_optimizer.py` and other apps' optimizers are different files and must NOT appear).

- [ ] **Step 2: Delete the files**

```bash
git rm opencontractserver/annotations/query_optimizer.py opencontractserver/extracts/query_optimizer.py
```

- [ ] **Step 3: Django check**

Run:
```bash
docker compose -f test.yml run --rm django python manage.py check
```
Expected: `System check identified no issues`.

- [ ] **Step 4: Commit**

```bash
git commit -m "Delete annotations/ and extracts/ query_optimizer.py monoliths (Phase 3, #1717)"
```

---

## Task 7: Add Phase 3 service-layer tests

**Files:**
- Create: `opencontractserver/tests/test_service_layer_phase3.py`
- Test: same file.

- [ ] **Step 1: Write the new test module**

```python
"""Phase 3 (issue #1717) — verify the relocated service packages.

The relocated optimizer classes are exercised behaviorally by the existing
optimizer test suite (test_query_optimizer_methods.py, test_metadata_
query_optimizer.py, etc.). This module locks in the *relocation contract*:
the new public import surface, BaseService conformance, and the removal of
the old monolith modules.
"""

import importlib

from django.test import SimpleTestCase

from opencontractserver.shared.services import BaseService


class Phase3ServiceRelocationTests(SimpleTestCase):
    def test_annotation_services_importable(self):
        from opencontractserver.annotations.services import (
            AnnotationService,
            RelationshipService,
        )

        self.assertTrue(issubclass(AnnotationService, BaseService))
        self.assertTrue(issubclass(RelationshipService, BaseService))

    def test_analysis_service_importable(self):
        from opencontractserver.analyzer.services import AnalysisService

        self.assertTrue(issubclass(AnalysisService, BaseService))

    def test_extract_services_importable(self):
        from opencontractserver.extracts.services import (
            ExtractService,
            MetadataService,
        )

        self.assertTrue(issubclass(ExtractService, BaseService))
        self.assertTrue(issubclass(MetadataService, BaseService))

    def test_public_methods_preserved(self):
        """The public fetch surface survived the relocation unrenamed."""
        from opencontractserver.analyzer.services import AnalysisService
        from opencontractserver.annotations.services import (
            AnnotationService,
            RelationshipService,
        )
        from opencontractserver.extracts.services import (
            ExtractService,
            MetadataService,
        )

        self.assertTrue(hasattr(AnnotationService, "get_document_annotations"))
        self.assertTrue(hasattr(AnnotationService, "get_corpus_annotations"))
        self.assertTrue(hasattr(RelationshipService, "get_document_relationships"))
        self.assertTrue(hasattr(AnalysisService, "get_visible_analyses"))
        self.assertTrue(hasattr(ExtractService, "get_visible_extracts"))
        self.assertTrue(hasattr(MetadataService, "get_documents_metadata_batch"))

    def test_old_monolith_modules_removed(self):
        """The pre-Phase-3 import paths must no longer resolve (no shim)."""
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("opencontractserver.annotations.query_optimizer")
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("opencontractserver.extracts.query_optimizer")
```

- [ ] **Step 2: Run the new tests**

Run:
```bash
docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_service_layer_phase3 --keepdb
```
Expected: 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add opencontractserver/tests/test_service_layer_phase3.py
git commit -m "Add Phase 3 service relocation tests (#1717)"
```

---

## Task 8: Update CHANGELOG and stale doc-comment references

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `opencontractserver/extracts/diff.py` (docstring at line ~101)
- Modify: `opencontractserver/utils/importing.py` (comment at line ~168)
- Modify: `opencontractserver/annotations/models.py` (comment at line ~1363)
- Modify: `opencontractserver/shared/QuerySets.py` (docstring references at lines ~35, 399, 410)

- [ ] **Step 1: Fix stale prose references**

In each non-CHANGELOG file above, replace stale text:
- `ExtractQueryOptimizer.get_extract_datacells` → `ExtractService.get_extract_datacells` (`extracts/diff.py`).
- `AnnotationQueryOptimizer._compute_effective_permissions` → `AnnotationService._compute_effective_permissions` (`utils/importing.py`).
- `query_optimizer.py` → `the annotation service` (`annotations/models.py:1363`).
- `AnnotationQueryOptimizer.get_corpus_annotations()` → `AnnotationService.get_corpus_annotations()`, and `AnnotationQueryOptimizer` → `AnnotationService` (`shared/QuerySets.py`).

These are comments/docstrings only — no code behavior. Verify with:
```bash
grep -rn "AnnotationQueryOptimizer\|ExtractQueryOptimizer\|AnalysisQueryOptimizer\|MetadataQueryOptimizer" --include=*.py opencontractserver/ config/ | grep -v "DocumentRelationship"
```
Expected: no output.

- [ ] **Step 2: Add CHANGELOG entry**

Under `## [Unreleased]`, add:
```markdown
### Changed
- **Service Layer Centralization Phase 3 (#1717):** Split the 1,507-line
  `annotations/query_optimizer.py` monolith into per-app `services/`
  packages and relocated the two misfiled optimizer classes.
  `AnnotationQueryOptimizer`/`RelationshipQueryOptimizer` →
  `annotations/services/` (`AnnotationService`, `RelationshipService`);
  `AnalysisQueryOptimizer` → `analyzer/services/analysis_service.py`
  (`AnalysisService`); `ExtractQueryOptimizer` + `MetadataQueryOptimizer`
  → `extracts/services/` (`ExtractService`, `MetadataService`). All
  classes now inherit `shared.services.BaseService`. Pure relocation —
  query/permission/prefetch behavior is unchanged; the existing optimizer
  test suite is the regression gate. The old `query_optimizer.py` modules
  in `annotations/` and `extracts/` are deleted (no compatibility shim).
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md opencontractserver/extracts/diff.py opencontractserver/utils/importing.py opencontractserver/annotations/models.py opencontractserver/shared/QuerySets.py
git commit -m "Update CHANGELOG and stale references for Phase 3 (#1717)"
```

---

## Task 9: Full regression run + pre-commit

- [ ] **Step 1: Run pre-commit**

Run:
```bash
pre-commit run --all-files
```
Expected: all hooks pass (black/isort/flake8 may auto-format the new files — if so, `git add` the changes and amend the relevant commit or add a fixup commit).

- [ ] **Step 2: Run the optimizer regression suite (the issue's named gate)**

Run:
```bash
docker compose -f test.yml run --rm django pytest -n 4 --dist loadscope \
  opencontractserver/tests/permissioning/test_query_optimizer_methods.py \
  opencontractserver/tests/permissioning/test_metadata_query_optimizer.py \
  opencontractserver/tests/permissioning/test_version_aware_query_optimizer.py \
  opencontractserver/tests/permissioning/test_comment_permission.py \
  opencontractserver/tests/test_query_optimizer_structural_sets.py \
  opencontractserver/tests/test_corpus_annotations_query.py \
  opencontractserver/tests/test_annotation_privacy.py \
  opencontractserver/tests/test_get_document_knowledge_optimizations.py \
  opencontractserver/tests/test_analysis_annotation_import.py \
  opencontractserver/tests/test_visibility_managers.py \
  opencontractserver/tests/test_structural_annotations_graphql_backwards_compat.py \
  opencontractserver/tests/test_extract_iterations.py \
  opencontractserver/tests/performance_optimizations/test_base.py \
  opencontractserver/tests/test_service_layer_phase3.py
```
Expected: all pass. Any failure is a relocation defect — diff the moved class against the original (`git show HEAD~N:opencontractserver/annotations/query_optimizer.py`) to find the divergence; do NOT change test expectations.

- [ ] **Step 3: Run GraphQL-resolver-touching suites**

Run the extract/corpus/document GraphQL test files whose resolvers were repointed in Task 4 (e.g. `test_extract_iterations.py`, `test_corpus_annotations_query.py`, and any `test_*extract*`, `test_*corpus*query*`, `test_*document*relationship*` files). If unsure of the exact set, run the broader directory:
```bash
docker compose -f test.yml run --rm django pytest -n 4 --dist loadscope opencontractserver/tests/ -k "extract or corpus or annotation or relationship or metadata or mcp"
```
Expected: all pass.

- [ ] **Step 4: Final stale-reference sweep**

Run:
```bash
grep -rn "query_optimizer" --include=*.py config/ opencontractserver/ | grep -i "annotation\|extract\b\|analysis\|metadata"
```
Expected: no output except `documents/query_optimizer.py`'s own filename in unrelated contexts (its internal `AnalysisService`/`ExtractService` imports are correct now).

- [ ] **Step 5: Commit any pre-commit fixups; push branch**

```bash
git status   # confirm clean
git push -u origin feature/split-annotations-query-optimizer-1717
```

- [ ] **Step 6: Open the PR**

`gh pr create` targeting `main`, title `Service layer centralization — Phase 3: split annotations/query_optimizer.py (#1717)`, body summarizing the relocation, the no-shim decision, and flagged issues F1–F4.

---

## Self-Review

- **Spec coverage:** Issue #1717 scope items — split `annotations/query_optimizer.py` (Tasks 1–3); `AnnotationQueryOptimizer`/`RelationshipQueryOptimizer` → `annotations/services/` (Task 1); `AnalysisQueryOptimizer` → `analyzer/services/` (Task 2); `ExtractQueryOptimizer` + `MetadataQueryOptimizer` → `extracts/services/` (Task 3); optimizer logic as private service internals + public `get_*` methods (preserved as-is, Tasks 1–3); update GraphQL call sites (Task 4 — superset of the four named files, see F2); relocate-not-rewrite with optimizer tests as regression gate (Task 9). All covered.
- **Placeholder scan:** No TBD/TODO/"add error handling". Code-bearing steps show exact content; relocation steps give exact line ranges + exact textual changes.
- **Type/name consistency:** Class names `AnnotationService`/`RelationshipService`/`AnalysisService`/`ExtractService`/`MetadataService` and module paths used identically in Tasks 1–8. Method names unchanged from originals.
- **Risk:** The one non-mechanical hazard — `replace_all` corrupting `DocumentRelationshipQueryOptimizer` — is called out explicitly in Task 4 and excluded in every affected step.
