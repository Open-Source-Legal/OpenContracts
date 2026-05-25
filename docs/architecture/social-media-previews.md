# Social Media Link Previews with Cloudflare Workers

This document describes how to implement rich social media previews (Open Graph / Twitter Cards) for cite deep-links using Cloudflare Workers.

## Status in this repo

This architecture is **already implemented** in this repository:

- **Cloudflare Worker**: `cloudflare-og-worker/` (entry: `cloudflare-og-worker/src/index.ts`)
- **Public (no-auth) GraphQL fields**: `config/graphql/queries.py` + `config/graphql/og_metadata_types.py`

Important note for dev tooling:

- **`schema.graphql` may be stale** relative to the running backend schema. If you rely on `schema.graphql` (e.g., for codegen), regenerate it after GraphQL changes (see [Generating GraphQL Schema Files](../walkthrough/advanced/generate-graphql-schema-files.md)).

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Implementation](#implementation)
4. [Backend Changes](#backend-changes)
5. [Deployment](#deployment)
6. [Testing](#testing)

---

## Overview

### Problem

When users share cite deep-links on social media (Twitter/X, LinkedIn, Slack, Discord, etc.), the social media crawlers cannot execute JavaScript. Since cite is a React SPA, crawlers see only the generic `index.html` with no entity-specific metadata.

**Current state** (without this feature):
```
Shared link: https://cite.opensource.legal/c/john/legal-contracts
Preview: "cite" with generic description
```

**Desired state** (with this feature):
```
Shared link: https://cite.opensource.legal/c/john/legal-contracts
Preview:
  Title: "Legal Contracts Collection"
  Description: "A curated collection of 45 legal contracts with ML-extracted clauses"
  Image: [Corpus thumbnail or branded preview image]
```

### Solution

Deploy a Cloudflare Worker at the edge that:
1. Detects social media crawler user agents
2. Parses the deep-link URL to identify the entity type
3. Fetches metadata for PUBLIC entities from the GraphQL API
4. Returns HTML with proper Open Graph meta tags
5. Passes all other requests through to the origin (SPA)

---

## Architecture

### Request Flow

```
                                 ┌────────────────────────────────────┐
                                 │                                    │
   Social Media Crawler          │         Cloudflare Worker          │
   (Twitterbot, etc.)            │                                    │
         │                       │  1. Check User-Agent               │
         │                       │  2. Parse URL → Entity Type        │
         │                       │  3. Fetch OG Metadata (GraphQL)    │
         │                       │  4. Return HTML with OG tags       │
         │                       │                                    │
         ▼                       └────────────────────────────────────┘
┌─────────────────┐                          │
│   DNS/Proxy     │──────────────────────────┤
│  (Cloudflare)   │                          │
└─────────────────┘                          │
         │                                   │
         │  Regular User                     │
         │  (Browser)                        │
         ▼                                   ▼
┌─────────────────┐              ┌─────────────────────────────────┐
│   React SPA     │              │   Django Backend (GraphQL)     │
│   (Frontend)    │              │   /graphql - og*Metadata queries │
└─────────────────┘              └─────────────────────────────────┘
```

### URL Patterns Handled

| Pattern | Entity Type | Example |
|---------|-------------|---------|
| `/c/{userSlug}/{corpusSlug}` | Corpus | `/c/john/legal-contracts` |
| `/c/{userSlug}/{corpusSlug}/discussions/{threadId}` | Thread | `/c/john/legal-contracts/discussions/abc123` |
| `/d/{userSlug}/{documentSlug}` | Document (standalone) | `/d/jane/my-document` |
| `/d/{userSlug}/{corpusSlug}/{documentSlug}` | Document (in corpus) | `/d/john/legal-contracts/2024-deal` |
| `/e/{userSlug}/{extractId}` | Extract | `/e/john/RXh0cmFjdFR5cGU6MTIz` |

### Social Media Crawlers Detected

```typescript
const SOCIAL_CRAWLERS = [
  // Social Media
  'twitterbot',            // Twitter/X
  'facebookexternalhit',   // Facebook
  'facebookcatalog',       // Facebook Commerce
  'linkedinbot',           // LinkedIn
  'slackbot',              // Slack
  'slackbot-linkexpanding',
  'discordbot',            // Discord
  'whatsapp',              // WhatsApp
  'telegrambot',           // Telegram

  // Google/Android RCS - Critical for Android messaging
  'googlemessages',        // Google Messages app (Android default SMS/RCS)
  'google-pagerenderer',   // Google's page rendering service for RCS previews
  'developers.google.com/+/web/snippet', // Google snippet fetcher

  // Apple/iOS
  'applebot',              // Apple (iMessage, Siri, Safari)

  // Other Messaging/Preview Services
  'pinterest',             // Pinterest
  'redditbot',             // Reddit
  'embedly',               // Embed.ly
  'bluesky',               // BlueSky social
  'cardyb',                // BlueSky's preview bot

  // Generic preview patterns (catch edge cases)
  'link preview',          // Generic link preview services
  'url preview',           // URL preview services
  'snippet',               // Snippet fetchers

  // Optional: search engines (only enable intentionally)
  // 'googlebot',
  // 'bingbot',
];
```

---

## Implementation

### Project Structure

```
cloudflare-og-worker/
├── src/
│   ├── index.ts          # Main worker entry
│   ├── crawler.ts        # Crawler detection
│   ├── parser.ts         # URL route parsing
│   ├── metadata.ts       # GraphQL metadata fetching
│   ├── html.ts           # OG HTML generation
│   └── types.ts          # TypeScript interfaces
├── wrangler.toml         # Cloudflare configuration
├── package.json
└── tsconfig.json
```

### Core Worker Implementation

In this repository, the authoritative implementation is:
- `cloudflare-og-worker/src/index.ts`
- `cloudflare-og-worker/src/crawler.ts`
- `cloudflare-og-worker/src/parser.ts`
- `cloudflare-og-worker/src/metadata.ts`
- `cloudflare-og-worker/src/html.ts`
- `cloudflare-og-worker/src/types.ts`

The code below is **illustrative** and may drift from the repo over time.

```typescript
// src/index.ts
import { isSocialMediaCrawler } from './crawler';
import { parseRoute } from './parser';
import { fetchOGMetadata } from './metadata';
import { generateOGHtml } from './html';

export interface Env {
  API_URL: string;
  SITE_URL: string;
  OG_IMAGE_BASE: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userAgent = request.headers.get('user-agent') || '';

    // Only intercept for social media crawlers
    if (!isSocialMediaCrawler(userAgent)) {
      // Pass through to origin (React SPA)
      return fetch(request);
    }

    // Parse the URL to identify entity type
    const route = parseRoute(url.pathname);
    if (!route) {
      // Not a recognized deep-link URL.
      // In this repository’s worker, we return a generic OG page for common static pages
      // (so crawlers still get useful metadata) and otherwise fall back to origin.
      if (isStaticPage(url.pathname)) {
        return generateGenericResponse(url, env);
      }
      return fetch(request);
    }

    try {
      // Fetch metadata from backend API
      const metadata = await fetchOGMetadata(route, env);

      if (!metadata) {
        // Entity not found or not public, return generic preview
        return generateGenericResponse(url, env);
      }

      // Generate and return OG HTML
      const html = generateOGHtml(metadata, url.href, env);
      return new Response(html, {
        headers: {
          'Content-Type': 'text/html;charset=UTF-8',
          'Cache-Control': 'public, max-age=3600', // Cache for 1 hour
        },
      });
    } catch (error) {
      console.error('OG Worker error:', error);
      // For crawlers, prefer returning a generic OG response over passing through,
      // since the SPA origin typically won’t include entity-specific metadata.
      return generateGenericResponse(url, env);
    }
  },
};

function isStaticPage(pathname: string): boolean {
  const staticPages = [
    '/',
    '/about',
    '/features',
    '/pricing',
    '/docs',
    '/login',
    '/signup',
    '/register',
  ];
  return staticPages.includes(pathname) || pathname.startsWith('/docs/');
}

function generateGenericResponse(url: URL, env: Env): Response {
  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>cite — the citation layer for agentic workflows</title>
  <meta property="og:title" content="cite — the citation layer for agentic workflows">
  <meta property="og:description" content="cite turns a repository of documents into an open citation graph that humans and AI agents can read, reason over, and contribute back to.">
  <meta property="og:image" content="${env.OG_IMAGE_BASE}/default-og.png">
  <meta property="og:url" content="${url.href}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="cite">
  <meta name="twitter:card" content="summary_large_image">
  <meta http-equiv="refresh" content="0;url=${url.href}">
</head>
<body>
  <p>Redirecting...</p>
</body>
</html>`;

  return new Response(html, {
    headers: {
      'Content-Type': 'text/html;charset=UTF-8',
      'Cache-Control': 'public, max-age=86400', // Cache for 24 hours
    },
  });
}
```

### Crawler Detection

```typescript
// src/crawler.ts
const SOCIAL_CRAWLERS = [
  'twitterbot',
  'facebookexternalhit',
  'facebookcatalog',
  'linkedinbot',
  'slackbot',
  'slackbot-linkexpanding',
  'discordbot',
  'whatsapp',
  'telegrambot',
  'pinterest',
  'applebot',
  'redditbot',
  'embedly',
  // Optional: include search engines for SEO
  // 'googlebot',
  // 'bingbot',
];

export function isSocialMediaCrawler(userAgent: string): boolean {
  const ua = userAgent.toLowerCase();
  return SOCIAL_CRAWLERS.some(crawler => ua.includes(crawler));
}

// For debugging: check if it's any known bot
export function isKnownBot(userAgent: string): boolean {
  const ua = userAgent.toLowerCase();
  return ua.includes('bot') ||
         ua.includes('crawler') ||
         ua.includes('spider') ||
         ua.includes('preview');
}
```

### URL Route Parser

```typescript
// src/parser.ts
export type EntityType = 'corpus' | 'document' | 'document_in_corpus' | 'extract' | 'thread';

export interface ParsedRoute {
  type: EntityType;
  userSlug: string;
  corpusSlug?: string;
  documentSlug?: string;
  extractId?: string;
  threadId?: string;
}

export function parseRoute(pathname: string): ParsedRoute | null {
  // Remove trailing slash
  const path = pathname.replace(/\/$/, '');

  // Thread: /c/{userSlug}/{corpusSlug}/discussions/{threadId}
  const threadMatch = path.match(/^\/c\/([^\/]+)\/([^\/]+)\/discussions\/([^\/]+)$/);
  if (threadMatch) {
    return {
      type: 'thread',
      userSlug: threadMatch[1],
      corpusSlug: threadMatch[2],
      threadId: threadMatch[3],
    };
  }

  // Corpus: /c/{userSlug}/{corpusSlug}
  const corpusMatch = path.match(/^\/c\/([^\/]+)\/([^\/]+)$/);
  if (corpusMatch) {
    return {
      type: 'corpus',
      userSlug: corpusMatch[1],
      corpusSlug: corpusMatch[2],
    };
  }

  // Document in corpus: /d/{userSlug}/{corpusSlug}/{documentSlug}
  const docInCorpusMatch = path.match(/^\/d\/([^\/]+)\/([^\/]+)\/([^\/]+)$/);
  if (docInCorpusMatch) {
    return {
      type: 'document_in_corpus',
      userSlug: docInCorpusMatch[1],
      corpusSlug: docInCorpusMatch[2],
      documentSlug: docInCorpusMatch[3],
    };
  }

  // Standalone document: /d/{userSlug}/{documentSlug}
  const docMatch = path.match(/^\/d\/([^\/]+)\/([^\/]+)$/);
  if (docMatch) {
    return {
      type: 'document',
      userSlug: docMatch[1],
      documentSlug: docMatch[2],
    };
  }

  // Extract: /e/{userSlug}/{extractId}
  const extractMatch = path.match(/^\/e\/([^\/]+)\/([^\/]+)$/);
  if (extractMatch) {
    return {
      type: 'extract',
      userSlug: extractMatch[1],
      extractId: extractMatch[2],
    };
  }

  return null;
}
```

### GraphQL Metadata Fetching

```typescript
// src/metadata.ts
import { ParsedRoute, EntityType } from './parser';
import { Env } from './index';

export interface OGMetadata {
  title: string;
  description: string;
  image: string | null;
  type: EntityType;
  entityName: string;
  creatorName: string;
  documentCount?: number;
}

export async function fetchOGMetadata(
  route: ParsedRoute,
  env: Env
): Promise<OGMetadata | null> {
  const query = buildQuery(route);
  if (!query) return null;

  const response = await fetch(`${env.API_URL}/graphql`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify({ query, variables: buildVariables(route) }),
  });

  if (!response.ok) {
    console.error('GraphQL request failed:', response.status);
    return null;
  }

  const json = await response.json() as GraphQLResponse;
  return extractMetadata(route.type, json.data, env);
}

interface GraphQLResponse {
  data: Record<string, any>;
  errors?: Array<{ message: string }>;
}

function buildQuery(route: ParsedRoute): string | null {
  switch (route.type) {
    case 'corpus':
      return `
        query OGCorpus($userSlug: String!, $corpusSlug: String!) {
          ogCorpusMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug) {
            title
            description
            iconUrl
            documentCount
            creatorName
            isPublic
          }
        }
      `;

    case 'document':
      return `
        query OGDocument($userSlug: String!, $documentSlug: String!) {
          ogDocumentMetadata(userSlug: $userSlug, documentSlug: $documentSlug) {
            title
            description
            iconUrl
            creatorName
            isPublic
          }
        }
      `;

    case 'document_in_corpus':
      return `
        query OGDocumentInCorpus($userSlug: String!, $corpusSlug: String!, $documentSlug: String!) {
          ogDocumentInCorpusMetadata(
            userSlug: $userSlug,
            corpusSlug: $corpusSlug,
            documentSlug: $documentSlug
          ) {
            title
            description
            iconUrl
            corpusTitle
            creatorName
            isPublic
          }
        }
      `;

    case 'thread':
      return `
        query OGThread($userSlug: String!, $corpusSlug: String!, $threadId: String!) {
          ogThreadMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug, threadId: $threadId) {
            title
            corpusTitle
            messageCount
            creatorName
            isPublic
          }
        }
      `;

    case 'extract':
      return `
        query OGExtract($extractId: String!) {
          ogExtractMetadata(extractId: $extractId) {
            name
            corpusTitle
            fieldsetName
            creatorName
            isPublic
          }
        }
      `;

    default:
      return null;
  }
}

function buildVariables(route: ParsedRoute): Record<string, string> {
  const vars: Record<string, string> = {};

  if (route.userSlug) vars.userSlug = route.userSlug;
  if (route.corpusSlug) vars.corpusSlug = route.corpusSlug;
  if (route.documentSlug) vars.documentSlug = route.documentSlug;
  if (route.extractId) vars.extractId = route.extractId;
  if (route.threadId) vars.threadId = route.threadId;

  return vars;
}

function extractMetadata(
  type: EntityType,
  data: Record<string, any>,
  env: Env
): OGMetadata | null {
  const queryMap: Record<EntityType, string> = {
    corpus: 'ogCorpusMetadata',
    document: 'ogDocumentMetadata',
    document_in_corpus: 'ogDocumentInCorpusMetadata',
    thread: 'ogThreadMetadata',
    extract: 'ogExtractMetadata',
  };

  const entity = data[queryMap[type]];
  if (!entity || !entity.isPublic) {
    return null;
  }

  // Build metadata based on entity type
  switch (type) {
    case 'corpus':
      return {
        title: entity.title,
        description: entity.description || `A corpus with ${entity.documentCount} documents`,
        image: entity.iconUrl || `${env.OG_IMAGE_BASE}/corpus-og.png`,
        type,
        entityName: entity.title,
        creatorName: entity.creatorName,
        documentCount: entity.documentCount,
      };

    case 'document':
    case 'document_in_corpus':
      return {
        title: entity.title,
        description: entity.description ||
          (entity.corpusTitle ? `Document in ${entity.corpusTitle}` : 'Document on cite.opensource.legal'),
        image: entity.iconUrl || `${env.OG_IMAGE_BASE}/document-og.png`,
        type,
        entityName: entity.title,
        creatorName: entity.creatorName,
      };

    case 'thread':
      return {
        title: entity.title || 'Discussion',
        description: `Discussion in ${entity.corpusTitle} with ${entity.messageCount} messages`,
        image: `${env.OG_IMAGE_BASE}/discussion-og.png`,
        type,
        entityName: entity.title || 'Discussion',
        creatorName: entity.creatorName,
      };

    case 'extract':
      return {
        title: entity.name,
        description: `Data extraction using ${entity.fieldsetName} on ${entity.corpusTitle}`,
        image: `${env.OG_IMAGE_BASE}/extract-og.png`,
        type,
        entityName: entity.name,
        creatorName: entity.creatorName,
      };

    default:
      return null;
  }
}
```

### OG HTML Generation

```typescript
// src/html.ts
import { OGMetadata } from './metadata';
import { Env } from './index';

export function generateOGHtml(
  metadata: OGMetadata,
  canonicalUrl: string,
  env: Env
): string {
  const title = escapeHtml(metadata.title);
  const description = escapeHtml(truncate(metadata.description, 200));
  const image = metadata.image || `${env.OG_IMAGE_BASE}/default-og.png`;
  const siteName = 'cite';

  // Entity type badge for title
  const typeLabel = getTypeLabel(metadata.type);
  const fullTitle = typeLabel ? `${title} | ${typeLabel}` : title;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${fullTitle}</title>

  <!-- Open Graph / Facebook -->
  <meta property="og:type" content="website">
  <meta property="og:url" content="${canonicalUrl}">
  <meta property="og:title" content="${fullTitle}">
  <meta property="og:description" content="${description}">
  <meta property="og:image" content="${image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:site_name" content="${siteName}">

  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:url" content="${canonicalUrl}">
  <meta name="twitter:title" content="${fullTitle}">
  <meta name="twitter:description" content="${description}">
  <meta name="twitter:image" content="${image}">

  <!-- Additional metadata -->
  <meta name="author" content="${escapeHtml(metadata.creatorName)}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="${canonicalUrl}">

  <!-- Redirect to actual page (for users who follow the meta refresh) -->
  <meta http-equiv="refresh" content="0;url=${canonicalUrl}">

  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      margin: 0;
      background: #f5f5f5;
    }
    .redirect {
      text-align: center;
      padding: 2rem;
    }
    a {
      color: #2563eb;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="redirect">
    <p>Redirecting to <a href="${canonicalUrl}">${fullTitle}</a>...</p>
    <noscript>
      <p>Click <a href="${canonicalUrl}">here</a> if you are not redirected.</p>
    </noscript>
  </div>
</body>
</html>`;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + '...';
}

function getTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    corpus: 'Corpus',
    document: 'Document',
    document_in_corpus: 'Document',
    thread: 'Discussion',
    extract: 'Data Extract',
  };
  return labels[type] || '';
}
```

### Types

```typescript
// src/types.ts
export interface Env {
  API_URL: string;
  SITE_URL: string;
  OG_IMAGE_BASE: string;
}

export type EntityType = 'corpus' | 'document' | 'document_in_corpus' | 'extract' | 'thread';

export interface ParsedRoute {
  type: EntityType;
  userSlug: string;
  corpusSlug?: string;
  documentSlug?: string;
  extractId?: string;
  threadId?: string;
}

export interface OGMetadata {
  title: string;
  description: string;
  image: string | null;
  type: EntityType;
  entityName: string;
  creatorName: string;
  documentCount?: number;
}
```

---

## Backend Changes

In this repository, the backend OG metadata fields and types are already implemented:

- `config/graphql/og_metadata_types.py`
- `config/graphql/queries.py` (look for the “OG METADATA RESOLVERS (PUBLIC - NO AUTH)” section)

If you update/extend these fields, remember to regenerate the checked-in `schema.graphql` if your workflow depends on it:

```bash
docker compose -f local.yml run django python manage.py graphql_schema --schema config.graphql.schema.schema --out schema.graphql
```

### New GraphQL Queries

The OG metadata queries are implemented in the backend:
- **Types**: [`config/graphql/og_metadata_types.py`](../../config/graphql/og_metadata_types.py)
- **Resolvers**: [`config/graphql/queries.py`](../../config/graphql/queries.py) (search for "OG METADATA RESOLVERS")

Key characteristics:
1. Only return data for public entities (`is_public=True`)
2. Don't require authentication
3. Return minimal data needed for OG tags
4. Use `corpus.document_count()` (via `DocumentPath`) instead of the deprecated `corpus.documents` M2M
5. Use `corpus.get_documents().filter(...)` for document lookups instead of `corpus.documents.get(...)`

> **Note**: The `corpus.documents` ManyToMany relationship has been removed (see issue #835). All document lookups now use `DocumentPath` as the single source of truth.

---

## Deployment

### Wrangler Configuration

```toml
# cloudflare-og-worker/wrangler.toml
name = "cite-og"
main = "src/index.ts"
compatibility_date = "2024-12-01"

# Environment variables
[vars]
SITE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
OG_IMAGE_BASE = "http://localhost:3000/static/og-images"

# Production environment
[env.production]
vars = { SITE_URL = "https://cite.opensource.legal", API_URL = "https://cite.opensource.legal", OG_IMAGE_BASE = "https://cite.opensource.legal/static/og-images" }

# Routes for production - uncomment and configure with your domain
# routes = [
#   { pattern = "cite.opensource.legal/c/*", zone_name = "opensource.legal" },
#   { pattern = "cite.opensource.legal/d/*", zone_name = "opensource.legal" },
#   { pattern = "cite.opensource.legal/e/*", zone_name = "opensource.legal" },
# ]

# Staging environment
[env.staging]
vars = { SITE_URL = "https://staging.cite.opensource.legal", API_URL = "https://staging.cite.opensource.legal", OG_IMAGE_BASE = "https://staging.cite.opensource.legal/static/og-images" }

# routes = [
#   { pattern = "staging.cite.opensource.legal/c/*", zone_name = "opensource.legal" },
#   { pattern = "staging.cite.opensource.legal/d/*", zone_name = "opensource.legal" },
#   { pattern = "staging.cite.opensource.legal/e/*", zone_name = "opensource.legal" },
# ]

# Development (local)
[env.dev]
vars = { API_URL = "http://localhost:8000" }
```

### package.json

```json
{
  "name": "cite-og-worker",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy",
    "deploy:staging": "wrangler deploy --env staging",
    "deploy:production": "wrangler deploy --env production"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20241127.0",
    "typescript": "^5.3.0",
    "wrangler": "^3.91.0"
  }
}
```

### tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "types": ["@cloudflare/workers-types"],
    "lib": ["ES2022"]
  },
  "include": ["src/**/*"]
}
```

### Deployment Steps

In this repository, the worker project already exists under `cloudflare-og-worker/`.

1. **Install dependencies**
   ```bash
   cd cloudflare-og-worker
   npm install
   ```

2. **Configure DNS**
   - In Cloudflare Dashboard, ensure domain is proxied (orange cloud)
   - Worker routes will intercept matching paths (configure `routes` in `wrangler.toml`)

3. **Deploy**
   ```bash
   # Login to Cloudflare
   npx wrangler login

   # Deploy to production
   npm run deploy:production
   ```

6. **Create OG Images**
   - Create static OG images at `/static/og-images/`:
     - `default-og.png` (1200x630) - Generic cite branding
     - `corpus-og.png` (1200x630) - Corpus icon
     - `document-og.png` (1200x630) - Document icon
     - `discussion-og.png` (1200x630) - Discussion icon
     - `extract-og.png` (1200x630) - Extract icon

---

## Testing

### Local Testing

```bash
# Run worker locally
cd cloudflare-og-worker
npm run dev

# Test with curl (simulating Twitter bot)
curl -H "User-Agent: Twitterbot/1.0" http://localhost:8787/c/john/legal-contracts

# Test regular request (should pass through)
curl http://localhost:8787/c/john/legal-contracts
```

### Validate OG Tags

Use online validators:
- [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/)
- [Twitter Card Validator](https://cards-dev.twitter.com/validator)
- [LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/)
- [OpenGraph.xyz](https://www.opengraph.xyz/)

### Integration Tests

```typescript
// tests/worker.test.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { unstable_dev } from 'wrangler';

describe('OG Worker', () => {
  let worker: any;

  beforeAll(async () => {
    worker = await unstable_dev('src/index.ts', {
      experimental: { disableExperimentalWarning: true },
    });
  });

  it('returns OG HTML for Twitterbot on corpus URL', async () => {
    const resp = await worker.fetch('/c/john/test-corpus', {
      headers: { 'User-Agent': 'Twitterbot/1.0' },
    });

    const html = await resp.text();
    expect(html).toContain('og:title');
    expect(html).toContain('twitter:card');
  });

  it('passes through for regular browser', async () => {
    const resp = await worker.fetch('/c/john/test-corpus', {
      headers: { 'User-Agent': 'Mozilla/5.0' },
    });

    // Should pass through to origin (will fail without origin)
    expect(resp.status).not.toBe(200);
  });

  it('returns generic OG for non-deep-link URLs', async () => {
    const resp = await worker.fetch('/about', {
      headers: { 'User-Agent': 'Twitterbot/1.0' },
    });

    // In this repository’s worker, common static pages return a generic OG page for crawlers
    expect(resp.status).toBe(200);
    const html = await resp.text();
    expect(html).toContain('og:title');
    expect(html).toContain('twitter:card');
  });
});
```

---

## Caching Strategy

### Worker-Level Caching

The worker sets `Cache-Control` headers:
- Successful OG responses: `max-age=3600` (1 hour)
- Generic responses: `max-age=86400` (24 hours)

### Cloudflare Cache

Configure cache rules in Cloudflare Dashboard:
1. Create Page Rule for `/c/*`, `/d/*`, `/e/*`
2. Set Edge Cache TTL based on bot detection
3. Consider cache-tags for invalidation

### Cache Invalidation

When entity metadata changes:
1. Use Cloudflare API to purge specific URLs
2. Or use cache-tags with `purge_cache()` in Django signals

```python
# Optional: Django signal to invalidate cache on update
from django.db.models.signals import post_save
from django.dispatch import receiver
import requests

@receiver(post_save, sender=Corpus)
def invalidate_og_cache(sender, instance, **kwargs):
    if instance.is_public:
        purge_url = f"https://cite.opensource.legal/c/{instance.creator.slug}/{instance.slug}"
        # Call Cloudflare API to purge this URL
        # requests.post(cloudflare_api_url, ...)
```

---

## Security Considerations

1. **Public Data Only**: OG queries only return data for `is_public=True` entities
2. **No Auth Required**: OG endpoints are intentionally unauthenticated
3. **Input Sanitization**: All output is HTML-escaped
4. **Rate Limiting**: Cloudflare automatically rate-limits
5. **No Sensitive Data**: Only title, description, and public URLs returned

---

## Future Enhancements

1. **Dynamic OG Images**: Generate preview images with entity titles using Cloudflare Images or Workers-based image generation
2. **Annotation Previews**: For annotation deep-links, show highlighted text
3. **Analytics**: Track social referrals via UTM parameters
4. **Schema.org Markup**: Add JSON-LD structured data for better SEO

---

## Related Documentation

- [Deep-Linking Architecture](./deep-linking.md)
- [Routing System](../frontend/routing_system.md)
- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)
- [Open Graph Protocol](https://ogp.me/)
- [Twitter Cards](https://developer.twitter.com/en/docs/twitter-for-websites/cards/overview/abouts-cards)

---

## Sources

- [Implementing Link Previews with Cloudflare Pages & Functions](https://formfunction.medium.com/implementing-link-previews-with-cloudflare-pages-functions-a47e02a662af)
- [Cloudflare HTMLRewriter API](https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/)
- [Cloudflare Workers Routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)
- [Cloudflare SPA Routing](https://developers.cloudflare.com/workers/static-assets/routing/single-page-application/)
- [Cloudflare Verified Bots](https://developers.cloudflare.com/bots/concepts/bot/verified-bots/)
- [GitHub: cloudflare-pages-social-preview](https://github.com/pew/cloudflare-pages-social-preview)
- [GitHub: OpenGraphTagBuilder](https://github.com/Recorder-moe/OpenGraphTagBuilder)
