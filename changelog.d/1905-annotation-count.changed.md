- **Cheap exact `totalCount` for the un-scoped annotations browse.** The
  "Browse annotations" view's exact "Total Annotations" tile is a `COUNT` over
  the full permission-filtered annotation set (a `DISTINCT` across several
  visibility joins). graphene-django 3.2.3 runs that `COUNT` eagerly on every
  page — including each infinite-scroll page — so at hundreds of thousands of
  rows it dominated page latency. `AnnotationQuerySet`
  (`opencontractserver/shared/QuerySets.py`) gains `with_cached_count()`, which
  casts to a `CachedCountAnnotationQuerySet` whose `COUNT(*)` is cached per
  `(user, filter)` (keyed by the compiled SQL) for
  `ANNOTATION_COUNT_CACHE_TTL_SECONDS` (60 min). The value stays **exact** and
  is stale by at most the TTL after a create/delete. Only the un-scoped resolver
  branch (`config/graphql/annotation_queries.py`) opts in; document- and
  corpus-scoped annotation counts stay live. The cached-count behaviour survives
  the queryset clones graphene makes during pagination. A cache-backend outage
  degrades gracefully to a live `COUNT` rather than breaking the browse page, and
  an unconfigured TTL bypasses the cache entirely instead of caching
  indefinitely.
- **Trimmed unused fields from `GET_ANNOTATIONS_FOR_CARDS`**
  (`frontend/src/graphql/queries.ts`): `linkUrl` and `annotationLabel.labelType`
  are never read by the annotation card (`getAnnotationLabelType` keys off
  `annotationType`), so they are no longer fetched.
