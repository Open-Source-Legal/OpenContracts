### Fixed

- **`corpusStats` no longer errors on a blank corpus id.** `resolve_corpus_stats`
  (`config/graphql/corpus_queries.py`) decoded an empty/garbage global id to a
  non-numeric pk and ran `filter(id="")`, which raised `Field 'id' expected a
  number but got ''` inside the open request transaction (aborting it for
  subsequent queries — the source of cascading `current transaction is aborted`
  errors). A malformed id is now treated like a not-found / not-visible corpus
  and returns zeroed stats with no GraphQL error.
- **AnnotationLabel `myPermissions` now inherits from its LabelSet.**
  `AnnotationLabel` carries no django-guardian object-permission tables (the
  LabelSet is the permissioned entity that governs its labels), but
  `AnnotatePermissionsForReadMixin.resolve_my_permissions`
  (`config/graphql/permissioning/permission_annotator/mixins.py`) assumed every
  type exposes a `{model}userobjectpermission_set` accessor and raised
  `'AnnotationLabel' object has no attribute
  'annotationlabeluserobjectpermission_set'` (caught + error-logged) on every
  annotation-label node. `AnnotationLabelType` now resolves `my_permissions` by
  inheriting the caller's permissions across the LabelSet(s) that include the
  label (mapping `*_labelset` → `*_annotationlabel`; public/`read_only` labels
  are always readable). The generic mixin is also hardened: both
  `resolve_my_permissions` and `resolve_object_shared_with` now fall back
  cleanly (via `get_users_permissions_for_obj` / empty list) for any
  guardian-less model instead of crashing and spamming the logs.
