- **Reverted the v3 product name from `cite` back to OpenContracts and
  repositioned the README around the platform's programmable surfaces.** The
  `cite` rename correlated with a sharp drop in project interest; `cite` is
  effectively un-searchable (a high-frequency English/academic word) and the
  rename forfeited the project's accrued search, backlink, and star/fork equity.
  `OpenContracts` reclaims that equity and is consistent with the unchanged
  `opencontractserver` backend module. `README.md` now leads builder-first —
  concrete capability plus a runnable agent snippet above the fold and a new
  "Build on it" section covering the Python agent API
  (`opencontractserver/llms/api.py`), the MCP server (`/mcp/`), structured
  extraction, the pluggable pipeline, and GraphQL/REST. Also reverted the product
  name across the landing content packs
  (`frontend/src/config/landingContent/default.json`, `publicRecord.json`) and
  the user-visible app chrome: the browser tab `<title>` / SEO + OpenGraph +
  JSON-LD (`frontend/index.html`, `components/seo/MetaTags.tsx`), the PWA manifest
  (`frontend/public/manifest.json`), the nav/footer "About" link
  (`overflowMenuItems.ts`, `layout/Footer.tsx`) and footer tagline, the
  auth/loading messages (`auth/AuthGate.tsx`, `widgets/ModernLoadingDisplay.tsx`),
  and the cookie banner (`cookies/CookieConsent.tsx`) — with the affected
  component tests updated in lockstep. Removed the `cite`-era "Domain Migration"
  README section and switched the README brand mark to the name-neutral
  `docs/assets/images/brand/icon_mark.svg`. Copy/branding only — no API, schema,
  data, or behavioral changes. (The `CiteMark` / `CiteWordmark` brand components
  and the `[cite]` wordmark/lockup SVG assets are intentionally left for a
  separate design pass; the verb "cite" and the `@cite` CAML directive are
  unchanged.)
