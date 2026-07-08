- **GraphQL layer migrated from graphene / graphene-django to strawberry-graphql** with a
  machine-verified guarantee of zero query-shape changes:
  - The full graphene SDL was captured at migration time as the golden contract
    (`config/graphql/schema.graphql`, 10.6k lines) and
    `opencontractserver/tests/test_schema_parity.py` structurally compares the served
    strawberry schema against it — every type, field, argument name/type, nullability
    wrapper, interface, enum member, and printed default must match exactly.
  - New shared runtime in `config/graphql/core/`: relay global IDs + `Node` interface with
    graphene wire format (`base64("TypeName:pk")`), `CountableConnection`/`PdfPageAwareConnection`
    factories, a faithful port of graphene-django's connection resolution (arrayconnection
    cursors, `RELAY_CONNECTION_MAX_LIMIT=100`, the 1-based `offset`→`after` conversion),
    django-filter FilterSet argument mapping incl. `GlobalIDFilter` global-ID decoding,
    `GenericScalar`/`JSONString`/`BigInt` scalars, permission-annotation resolvers
    (`myPermissions`/`isPublished`/`objectSharedWith`), DRF-serializer mutation bases, and
    auth decorators with graphql_jwt-compatible error messages.
  - Auth middlewares replaced: `graphql_jwt.middleware.JSONWebTokenMiddleware` and the
    API-key graphene middleware are gone; per-request authentication now happens once in
    `config/graphql/views.py::GraphQLView.get_context` via the standard
    `AUTHENTICATION_BACKENDS` chain (JWT / Auth0 / API-key / session). The
    `tokenAuth`/`verifyToken`/`refreshToken` mutations are strawberry-native ports
    (`config/graphql/jwt_auth.py`, `config/graphql/user_mutations.py`) preserving
    long-running refresh-token laziness; `django-graphql-jwt` remains only as a JWT
    signing/backend utility library.
  - Security hardening preserved: `DepthLimitValidationRule` + `DisableIntrospection`
    (production) now attach via strawberry's `AddValidationRules` extension, which APPENDS
    to the full graphql-core spec rule set (the graphene-era replace-the-rules trap is
    structurally impossible). The GCS file-URL pre-warm middleware became
    `config/graphql/file_url_prewarm.py::FileUrlPrewarmExtension`.
  - The per-resolver `PermissionAnnotatingMiddleware` was folded into the permission
    resolvers themselves (`config/graphql/core/permissions.py`) with the same per-request
    memoisation contract (`info.context.permission_annotations`).
  - Test suite kept its substantive cases: `graphene.test.Client` was replaced by the
    drop-in `config/graphql/testing.py::Client` (same result dict shape), plus a
    `GraphQLTestCase` port for endpoint-level tests; `schema.execute(...)` calls became
    `schema.execute_sync(...)`.
  - `graphene-django` removed from requirements/`INSTALLED_APPS`; `strawberry-graphql`
    added; the `GRAPHENE` settings block deleted.
