- Review follow-ups to the graphene→strawberry migration:
  - `config/graphql/core/mutations.py`: `drf_mutation`/`drf_deletion` now pass
    `group="mutate"` to `graphql_ratelimit`. The decorator was applied to a
    `lambda`, so it derived the rate-limit cache group from `func.__name__`
    (`"<lambda>"`), splitting the ~9 DRF-routed mutations (`updateAnnotation`,
    `deleteNote`, `createCorpus`, `updateCorpus`, `deleteCorpusAction`,
    `updateDocument`, `deleteDocument`, `deleteExport`, `deleteExtract`) into a
    separate write bucket and roughly doubling a user's combined write budget.
    They now share the single `"mutate"` fixed-window counter, matching the
    graphene baseline and every hand-ported mutation.
  - `config/graphql/core/relay.py::get_node_from_global_id`: the `entry.get_node`
    hook path is now wrapped in the same `(ValueError, TypeError, OverflowError)`
    guard the default queryset path already had, so a malformed pk reaching an
    `int(pk)` hook (e.g. `researchReport(id: base64("ResearchReportType:xyz"))`)
    returns the unified IDOR-safe not-found instead of surfacing a raw
    `ValueError`.
  - `opencontractserver/tests/test_security_hardening.py`: added
    `TestServedSchemaExecutesValidationRules`, which drives a too-deep query and
    an introspection query through `schema.execute_sync` (the real
    `AddValidationRules` extension path). The pre-existing depth/introspection
    tests only call graphql-core's `validate(..., validation_rules)` against the
    exported list, so they would keep passing even if `AddValidationRules` were
    dropped from the schema's `extensions` (depth-limiting / prod
    introspection-blocking silently disabled on the endpoint). This closes that
    coverage gap.
  - `config/settings/base.py`: removed the dead `ALLOW_GRAPHQL_DEBUG` setting —
    its only consumer, `graphene_django.debug.DjangoDebugMiddleware`, was deleted
    with the graphene stack.
  - Corrected the stale relay/`MessageType` note in
    `config/graphql/core/relay.py` and `docs/architecture/graphql_strawberry_migration.md`,
    which described singular node resolution as unfiltered-by-pk for
    `MessageType`/`chatMessage`; the migration's own IDOR fix registered a
    permission-aware `get_node` hook, and the doc now documents the
    `resolve_visible_fk` FK-traversal path as well.
