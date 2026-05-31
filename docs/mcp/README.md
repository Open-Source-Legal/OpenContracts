# OpenContracts MCP Server

## TL;DR

OpenContracts exposes a read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for AI assistants to access **public** corpuses, documents, annotations, and discussion threads.

**Endpoints**:
- **Global** (all public corpuses, anonymous): `POST /mcp/` or `GET /mcp/`
- **Authenticated** (public + your private resources): `POST /mcp/me/` or `GET /mcp/me/`
- **Corpus-Scoped** (single corpus): `POST /mcp/corpus/{corpus_slug}/` or `GET /mcp/corpus/{corpus_slug}/`
- **SSE** (deprecated): `GET /sse/`, `POST /sse/messages/`

**Scope**: `/mcp/` and `/mcp/corpus/...` expose public resources to anonymous
callers; `/mcp/me/` requires sign-in and additionally exposes private resources
the authenticated user owns or is shared on. A valid `Authorization: Bearer
<JWT>` is honored on *any* endpoint.

**Auth**: Optional on `/mcp/` (anonymous = public only). Required on `/mcp/me/`,
which returns `401 + WWW-Authenticate` to unauthenticated callers so interactive
clients (Claude web/desktop, ChatGPT) start the OAuth 2.1 sign-in flow. See
[Authentication](#authentication) below.

### Claude Desktop Quick Start

**Global Access** (all public corpuses):

Add to `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "opencontracts": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-instance.com/mcp/"
      ]
    }
  }
}
```

**Corpus-Scoped Access** (single corpus - shareable link):

```json
{
  "mcpServers": {
    "my-legal-corpus": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-instance.com/mcp/corpus/my-corpus-slug/"
      ]
    }
  }
}
```

> **Tip**: Corpus-scoped links are ideal for sharing with collaborators. They provide focused access to a specific corpus without needing to know the corpus slug.

---

## Available Tools

### Global Endpoint (`/mcp/`)

| Tool | Description |
|------|-------------|
| `list_public_corpuses` | List all public corpuses (paginated, searchable) |
| `list_documents` | List documents in a corpus (requires `corpus_slug`) |
| `get_document_text` | Get full extracted text from a document |
| `list_annotations` | List annotations on a document (filter by page/label) |
| `search_corpus` | Semantic vector search within a corpus |
| `list_threads` | List discussion threads in a corpus |
| `get_thread_messages` | Get messages in a thread (flat or hierarchical) |

### Corpus-Scoped Endpoint (`/mcp/corpus/{corpus_slug}/`)

When using a corpus-scoped endpoint, tools are simplified - no `corpus_slug` parameter needed:

| Tool | Description |
|------|-------------|
| `get_corpus_info` | Get detailed info about the scoped corpus (replaces `list_public_corpuses`) |
| `list_documents` | List documents (no `corpus_slug` needed) |
| `get_document_text` | Get document text (only `document_slug` needed) |
| `list_annotations` | List annotations (only `document_slug` needed) |
| `search_corpus` | Semantic search (only `query` needed) |
| `list_threads` | List threads (no `corpus_slug` needed) |
| `get_thread_messages` | Get messages (only `thread_id` needed) |

## Available Resources

Resources use URI patterns for direct access:

| URI Pattern | Description |
|-------------|-------------|
| `corpus://{corpus_slug}` | Corpus metadata and document list |
| `document://{corpus_slug}/{document_slug}` | Document with extracted text |
| `annotation://{corpus_slug}/{document_slug}/{annotation_id}` | Specific annotation |
| `thread://{corpus_slug}/threads/{thread_id}` | Thread with messages |

---

## Transport Options

### Streamable HTTP - Global (Recommended)

The primary transport, introduced in MCP spec 2025-03-26. Stateless mode - each request is independent.

```bash
# Test with curl
curl -X POST https://your-instance.com/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

### Streamable HTTP - Corpus-Scoped (Shareable Links)

Scoped endpoints provide access to a single corpus. Perfect for sharing with collaborators:

```bash
# Get corpus info (no corpus_slug needed in arguments)
curl -X POST https://your-instance.com/mcp/corpus/my-corpus-slug/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_corpus_info", "arguments": {}}, "id": 1}'

# Search within the scoped corpus
curl -X POST https://your-instance.com/mcp/corpus/my-corpus-slug/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "search_corpus", "arguments": {"query": "indemnification clause"}}, "id": 2}'
```

### SSE (Deprecated, Backward Compatible)

For older MCP clients that use the deprecated SSE transport (pre-2025-03-26 spec):

```bash
# SSE connection (GET) - establishes SSE stream
curl https://your-instance.com/sse/

# Messages endpoint (POST) - send messages to the server
curl -X POST https://your-instance.com/sse/messages/?session_id=<id> \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

### stdio (CLI)

For local development or direct integration:

```bash
cd /path/to/OpenContracts
python -m opencontractserver.mcp.server
```

---

## Example Usage

### List Public Corpuses

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "list_public_corpuses",
    "arguments": {"limit": 10}
  },
  "id": 1
}
```

### Semantic Search

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_corpus",
    "arguments": {
      "corpus_slug": "my-corpus",
      "query": "indemnification clause",
      "limit": 5
    }
  },
  "id": 2
}
```

### Read Resource

```json
{
  "jsonrpc": "2.0",
  "method": "resources/read",
  "params": {
    "uri": "document://my-corpus/contract-2024"
  },
  "id": 3
}
```

---

## Architecture

```
┌─────────────────┐                    ┌──────────────────────────────────────────────┐
│  MCP Client     │                    │  ASGI Router                                 │
│  (Claude, etc)  │◄──────────────────►│  /mcp/* or /mcp/corpus/{slug}/* or /sse/*   │
└─────────────────┘   JSON-RPC 2.0     └──────────┬───────────────────────────────────┘
                                                  │
                      ┌───────────────────────────┼───────────────────────────────────────────────┐
                      │                           │                           │                   │
           ┌──────────▼───────────┐    ┌──────────▼───────────┐    ┌──────────▼───────────┐    ┌──▼─────────────────┐
           │  StreamableHTTP      │    │  Corpus-Scoped HTTP  │    │  SSE Transport       │    │  stdio Transport   │
           │  /mcp (global)       │    │  /mcp/corpus/{slug}/ │    │  /sse (deprecated)   │    │  (CLI only)        │
           └──────────┬───────────┘    └──────────┬───────────┘    └──────────┬───────────┘    └──────────┬─────────┘
                      │                           │                           │                           │
                      │                           │                           │                           │
           ┌──────────▼───────────┐    ┌──────────▼───────────┐              │                           │
           │  Global MCP Server   │    │  Scoped MCP Server   │              │                           │
           │  - 7 tools           │    │  - 7 tools (scoped)  │              │                           │
           │  - 4 resources       │    │  - 4 resources       │              │                           │
           │  - All corpuses      │    │  - Single corpus     │              │                           │
           └──────────┬───────────┘    └──────────┬───────────┘              │                           │
                      │                           │                           │                           │
                      └───────────────────────────┼───────────────────────────┼───────────────────────────┘
                                                  │
                                       ┌──────────▼───────────┐
                                       │  Django ORM          │
                                       │  visible_to_user()   │
                                       │  (AnonymousUser)     │
                                       └──────────────────────┘
```

### Scoped vs Global Endpoints

| Aspect | Global (`/mcp/`) | Corpus-Scoped (`/mcp/corpus/{slug}/`) |
|--------|------------------|---------------------------------------|
| **Use Case** | Discover and explore all public corpuses | Share focused access to specific corpus |
| **Tool Parameters** | Requires `corpus_slug` for most tools | `corpus_slug` auto-injected |
| **Server Instance** | Single global server | One server per corpus (cached) |
| **Shareable** | Yes, but requires knowing corpus slug | Yes, link contains the corpus |

**Key files**:
- `opencontractserver/mcp/server.py` - Server setup, ASGI app, URI parsing, transport handlers
- `opencontractserver/mcp/tools.py` - Tool implementations
- `opencontractserver/mcp/resources.py` - Resource handlers
- `opencontractserver/mcp/formatters.py` - Response formatters
- `config/asgi.py` - HTTP routing (`/mcp/*` and `/sse/*` → MCP app)
- `compose/production/traefik/traefik.yml` - Production routing (Traefik)

---

## Authentication

The server accepts an OAuth 2.1 / JWT **Bearer** token on the standard
`Authorization` header and validates it through the same pipeline as the rest of
the app (`config/jwt_utils.py` → Auth0 RS256/JWKS when `USE_AUTH0=True`,
otherwise the local `graphql_jwt` HS256 token).

- **`/mcp/` (and `/mcp/corpus/...`)** — auth is *optional*. No token ⇒ anonymous
  (public resources only). A valid token ⇒ that user's private resources are
  also visible.
- **`/mcp/me/`** — auth is *required*. An unauthenticated request gets `401`
  with a `WWW-Authenticate: Bearer resource_metadata="…"` header (RFC 6750 /
  RFC 9728). Interactive MCP clients follow that pointer to
  `/.well-known/oauth-protected-resource[/mcp/me]`, discover the authorization
  server (Auth0), and run Authorization-Code + PKCE — no preconfigured token
  needed. **Register `/mcp/me/` as the server URL in Claude web/desktop or
  ChatGPT to get the "Connect / Sign in" prompt.**

### Discovery endpoints

| URL | Purpose |
|-----|---------|
| `/.well-known/mcp.json` | Lists the MCP servers (incl. `cite-authenticated` when Auth0 is on) |
| `/.well-known/oauth-protected-resource` | RFC 9728 metadata for the canonical `/mcp` resource |
| `/.well-known/oauth-protected-resource/mcp/me` | RFC 9728 path-based metadata for the authed resource |

### Auth0 configuration notes

For the interactive flow to complete end-to-end, the access token Auth0 issues
must validate here:

- The Auth0 **API Identifier (audience)** must equal `AUTH0_API_AUDIENCE` — the
  server validates `aud` on every token. Map the advertised resource to that API
  so the RFC 8707 `resource`/`audience` the client sends yields a JWT (not an
  opaque token).
- Enable **Dynamic Client Registration** on the tenant — Claude/ChatGPT register
  themselves on the fly (RFC 7591).
- Set `MCP_PUBLIC_BASE_URL` (e.g. `https://contracts.opensource.legal`) so the
  challenge advertises a trusted absolute URL rather than one derived from the
  request `Host` (MCP bypasses `ALLOWED_HOSTS`).
- Browser clients / the MCP Inspector additionally need the calling origin in
  `MCP_CORS_ALLOWED_ORIGINS` (defaults to Claude, ChatGPT, and the Inspector).

## Security Model

- **Read-mostly**: the only write tool (`create_thread_message`) enforces
  authentication and per-resource permissions inside the tool body
- **Permission-filtered**: anonymous callers resolve through `AnonymousUser`;
  authenticated callers see only resources they own or are shared on
- **Slug-based**: All identifiers are URL-safe slugs (no internal IDs exposed)
- **Bearer auth**: optional on `/mcp/`, required on `/mcp/me/` (see above)

---

## Limitations

- No streaming of large documents (text returned in full)
- Semantic search requires corpus to have embeddings configured
- Interactive OAuth sign-in requires `USE_AUTH0=True`; without it, `/mcp/me/`
  still accepts a bearer token but cannot advertise an interactive login
