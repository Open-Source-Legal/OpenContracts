# Discovery System

The discovery system serves internet-facing endpoints that tell search engines, AI crawlers, and MCP clients what your OpenContracts instance is and what it exposes. It lives in [`opencontractserver/discovery/`](https://github.com/Open-Source-Legal/OpenContracts/tree/main/opencontractserver/discovery) and is wired in via the project's URL routing.

> **Operator note**: These endpoints are public by default. They only return data that is visible to anonymous users (`Corpus.objects.visible_to_user(AnonymousUser())` etc.), but you should still review what your public corpuses contain before exposing the instance to the internet.

## Endpoints

| Path | What it returns | Standard / use case |
|---|---|---|
| `/robots.txt` | Standard `robots.txt` directives | Search engine crawler policy |
| `/llms.txt` | Compact, LLM-friendly site description | [llms.txt](https://llmstxt.org) — an emerging standard that lets AI agents understand a site's content without scraping HTML |
| `/llms-full.txt` | Longer, full-content variant of `/llms.txt` | Same standard, larger payload |
| `/sitemap.xml` | XML sitemap of public corpuses and documents | Search engines, AI crawlers |
| `/.well-known/mcp.json` | MCP server manifest describing the corpus tools available via `/mcp` | [Model Context Protocol](https://modelcontextprotocol.io) discovery — used by Claude, Cursor, and other MCP-aware tools to find your server |
| `/api/search/` | RESTful search across public corpuses and documents | AI agents and external integrators that don't want to use GraphQL |

All endpoints are cacheable (`@cache_page(DISCOVERY_CACHE_SECONDS)`) and rate-limited per IP. The rate limit value is sourced from `opencontractserver.mcp.config.RATE_LIMIT_REQUESTS` (default 100 requests/minute per IP) and is exposed in the responses as a human-readable hint.

## What the endpoints expose

The endpoints serve **only public data**:

- `Corpus.objects.visible_to_user(AnonymousUser())` — corpuses with `is_public=True`
- `Document.objects.visible_to_user(AnonymousUser())` (via `DocumentPath` joins to the public corpus set) — current-version documents in public corpuses
- Corpus and document titles, slugs, descriptions, and aggregate counts (e.g., `active_document_count`)

User identities, private documents, private annotations, and conversation contents are **never** included.

## Constants

Tunable constants live in `opencontractserver/constants/discovery.py`:

| Constant | Purpose |
|---|---|
| `DISCOVERY_CACHE_SECONDS` | HTTP cache TTL for all discovery responses |
| `MAX_PUBLIC_CORPUSES` | Cap on the number of corpuses surfaced in `sitemap.xml` and `llms*.txt` |
| `MAX_SEARCH_RESULTS` | Cap on `/api/search/` result count |

## Telemetry

Each discovery endpoint hit fires a `discovery_endpoint_served` PostHog event (handled by `config.telemetry.record_event`) with the endpoint name and the requesting user-agent. This is useful for understanding which AI crawlers are actually using your instance.

To opt out, leave `REACT_APP_POSTHOG_API_KEY` unset and the backend will no-op the event call.

## Customisation

To customise the discovery content, edit the view functions in `opencontractserver/discovery/views.py`:

- `robots_txt` — `User-agent` rules, sitemap URL.
- `llms_txt` / `llms_full_txt` — site description, public corpus listing format.
- `sitemap_xml` — what gets included in the XML sitemap.
- `well_known_mcp` — MCP server manifest (server URL, transport, tool list summary).
- `search_api` — search query semantics, result shape.

Markdown content fed into the `llms*.txt` endpoints is sanitised with `_sanitize_markdown_title` to prevent markdown injection via crafted corpus titles.

## Disabling discovery

To remove the discovery endpoints entirely, drop the `opencontractserver.discovery` URL include from your project's URL configuration. Note that `/.well-known/mcp.json` is the canonical advertise-the-MCP-server endpoint; AI tools that follow the standard will look for it.

## Related

- [MCP Server](../mcp/README.md) — what `/.well-known/mcp.json` actually advertises.
- [Telemetry – Backend](../telemetry/Backend.md) — `record_event` and PostHog setup.
