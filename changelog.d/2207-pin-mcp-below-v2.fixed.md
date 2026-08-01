- `requirements/base.txt:85` — pinned `mcp` to `>=1.28.1,<2` (was unbounded).
  Dependabot's `mcp>=2.0.0` bump (#2207) hit `pip`'s resolver as
  `resolution-too-deep`: `pydantic-ai-slim[mcp]`'s `fastmcp-slim` dependency
  caps `mcp<2.0` across its entire published range, so the unbounded pin was
  resolving to 1.x only by transitive accident. `mcp` 2.0 is also a breaking
  rewrite — `mcp.server.lowlevel.Server` drops decorator-based handler
  registration (`@mcp_server.list_resources()` etc.) in favor of `on_*=`
  constructor kwargs with a new `(ctx, params)` handler signature — which
  `opencontractserver/mcp/server.py` does not yet speak (10 registration
  sites across `create_mcp_server()` and `create_scoped_mcp_server()`), so
  forcing the bump would fail at ASGI import time, not just in CI. PR #2207
  is left open/unmerged; revisit the `mcp` 2.x migration as its own scoped
  task once `fastmcp-slim` ships v2 support.
