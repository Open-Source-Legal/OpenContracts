- **De-joined `Annotation.visible_to_user` — `EXISTS` subqueries, no more
  `.distinct()`** (issue #1906, Tier 3 of #1908).
  `AnnotationQuerySet.visible_to_user`
  (`opencontractserver/shared/QuerySets.py`) previously reached structural-set
  document visibility through the `structural_set__documents` reverse-FK join,
  which fans one annotation out to one row per document in the set and so forced
  a trailing `.distinct()`. That `DISTINCT` knocked the un-scoped "Browse
  annotations" `COUNT(*)` and `ORDER BY -modified` page off any single index (a
  full scan + dedup over hundreds of thousands of rows). Document-, corpus-, and
  structural-set visibility are now expressed as correlated `EXISTS` subqueries,
  so the outer query stays on the `annotation` table alone — no joins, no row
  fan-out, no `.distinct()`. The returned row set is **identical** to the old
  predicate; this is pinned by the `visible_to_user ⟺ user_can(READ)` invariant
  (`opencontractserver/tests/permissioning/test_authorization_invariants.py`)
  and by new de-join regression tests
  (`opencontractserver/tests/test_annotation_visibility_exists.py`).
- **New composite index `annot_structural_modified_idx` on
  `Annotation(structural, modified)`** (migration
  `opencontractserver/annotations/migrations/0077_annotation_structural_modified_index.py`,
  built `CONCURRENTLY`). Backs the `structural=<bool>` + `ORDER BY -modified`
  query shape used by the anonymous / Discover browse and the `structural`
  filter on the annotations connection — usable only now that the predicate is
  de-joined. The unfiltered `-modified` page keeps using the single-column
  `modified` index, so the new index is purely additive.
- **Cached annotation count retained, now justified rather than a band-aid**
  (`CachedCountQuerySetMixin`, `config/graphql/annotation_queries.py`). The
  Tier-3 de-join removes the `DISTINCT` + M2M fan-out the count used to pay for,
  but a `COUNT(*)` over the permission predicate is an OR across several
  dimensions (creator / public / structural / analysis / extract / doc / corpus)
  that no single index satisfies, so it remains an O(n) scan that graphene-django
  re-fires on every infinite-scroll page. Issue #1906 conditioned removal of the
  cache on the count becoming "index-cheap"; it does not, so the cache stays and
  its docstring now documents that reasoning.
