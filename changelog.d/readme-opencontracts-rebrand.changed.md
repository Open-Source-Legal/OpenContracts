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
  extraction, the pluggable pipeline, and GraphQL/REST. Also updated the landing
  content packs (`frontend/src/config/landingContent/default.json` and
  `publicRecord.json`) and switched the README brand mark to the name-neutral
  `docs/assets/images/brand/icon_mark.svg`. Removed the `cite`-era "Domain
  Migration" section. Documentation/branding only — no code, API, schema, or data
  changes. (The text-based `wordmark.svg`/`lockup.svg` still render "[cite]" and
  need a separate design pass.)
