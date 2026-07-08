- Closed an IDOR regression introduced by the graphene→strawberry migration:
  the singular "fetch one object by global Relay ID" query fields resolve
  through `config/graphql/core/relay.py::get_node_from_global_id`, which — when
  the target type is registered without a `get_node`/`get_queryset` hook — falls
  back to an UNFILTERED `model._default_manager.get(pk=...)`. Thirteen
  model-backed types had lost the permission filtering their graphene resolvers
  performed, letting any caller (anonymous included, for `chatMessage`) fetch
  private rows by forging `base64("<Type>:<id>")`:
  `relationship`, `annotationLabel`, `labelset`, `chatMessage`, `fieldset`,
  `column`, `datacell`, `analyzer`, `gremlinEngine`, `agent`, `badge`,
  `userexport`, `userimport`, and `assignment`. Each type now registers a
  permission-aware `get_node` hook mirroring the graphene resolver
  (`BaseService.get_or_none` / `filter_visible` / the owning service;
  `assignment` keeps its deprecated superuser-or-participant gate). Added
  `opencontractserver/tests/test_singular_node_idor.py` — a structural guard
  asserting every type resolved via `get_node_from_global_id` carries a hook
  (mechanically prevents recurrence) plus a behavioral non-owner-denied check.
- `config/graphql/views.py::GraphQLView.dispatch` now also catches DRF
  `AuthenticationFailed` (raised by `ApiKeyBackend` for a malformed/unknown/
  inactive API key when `USE_API_KEY_AUTH=True`) and returns a GraphQL-style
  `{"errors": [...]}` 200, matching the graphene middleware's behaviour instead
  of surfacing an unhandled 500 (auth now runs in `get_context`, before query
  execution's try/except).
