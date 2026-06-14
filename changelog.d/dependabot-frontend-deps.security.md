- **Resolved open Dependabot security alerts in frontend dependency chains.**
  - `frontend`: forced `esbuild` to `>=0.28.1` via a `resolutions` entry
    (`frontend/package.json`) — Vite 7.3.x still pins `esbuild@^0.27.0`, which
    leaves the resolved version exposed to the high-severity Deno binary
    integrity RCE (`NPM_CONFIG_REGISTRY`) and the low-severity Windows dev-server
    arbitrary file read advisories. Build and `tsc` verified green on 0.28.1.
  - `frontend`: bumped `react-router-dom` to `^6.30.4` (lockfile now resolves
    `react-router@6.30.4`), patching the medium-severity protocol-relative
    same-origin open-redirect (`//`-prefixed path) advisory.
  - `cloudflare-og-worker`: added an `esbuild: ">=0.28.1"` `overrides` entry so
    the worker's transitive `esbuild` (was 0.27.3) picks up the same patch;
    typecheck and the 93 worker tests pass on 0.28.1.
