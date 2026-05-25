# cite Social Media Preview Worker

Cloudflare Worker that intercepts social media crawler requests and returns rich Open Graph / Twitter Card metadata for cite.opensource.legal deep-links.

## Why This Exists

When someone shares a cite.opensource.legal link on Twitter, LinkedIn, Slack, Discord, or other social platforms, the platform's crawler fetches the URL to generate a preview. Since cite is a React SPA, crawlers (which don't execute JavaScript) would only see generic metadata.

This worker sits at the edge and:
1. Detects social media crawler user agents
2. Fetches entity metadata from the backend API
3. Returns HTML with proper OG/Twitter meta tags
4. Passes regular browser requests through to the SPA

## Quick Start

### Prerequisites

- Node.js 18+
- Cloudflare account (free tier works)
- cite backend running with the OG metadata GraphQL queries

### Local Development

```bash
# Install dependencies
npm install

# Run locally (uses wrangler dev server)
npm run dev
```

Test with curl:
```bash
# Simulate Twitter bot
curl -H "User-Agent: Twitterbot/1.0" http://localhost:8787/c/john/my-corpus

# Regular browser (should pass through)
curl http://localhost:8787/c/john/my-corpus
```

### Deploy to Cloudflare

```bash
# Login to Cloudflare (first time only)
npx wrangler login

# Deploy to production
npm run deploy:production
```

## Configuration

### Environment Variables (wrangler.toml)

| Variable | Description | Default |
|----------|-------------|---------|
| `SITE_URL` | Base URL of the cite site | `http://localhost:3000` |
| `API_URL` | Backend API URL for GraphQL | `http://localhost:8000` |
| `OG_IMAGE_BASE` | Base URL for static OG images | `{SITE_URL}/static/og-images` |

### Routes

Configure routes in `wrangler.toml` to match your domain. The production
config covers both the canonical `cite.opensource.legal` domain and the
legacy `contracts.opensource.legal` domain (kept alive during the 90-day
grace period) so deep-links shared on social media get rich previews
regardless of which domain the link points at:

```toml
[env.production]
routes = [
  { pattern = "cite.opensource.legal/c/*", zone_name = "opensource.legal" },
  { pattern = "cite.opensource.legal/d/*", zone_name = "opensource.legal" },
  { pattern = "cite.opensource.legal/e/*", zone_name = "opensource.legal" },
  { pattern = "contracts.opensource.legal/c/*", zone_name = "opensource.legal" },
  { pattern = "contracts.opensource.legal/d/*", zone_name = "opensource.legal" },
  { pattern = "contracts.opensource.legal/e/*", zone_name = "opensource.legal" },
]
```

## Project Structure

```
src/
├── index.ts      # Main worker entry - request handling
├── crawler.ts    # Social media crawler detection
├── parser.ts     # URL route parsing for deep-links
├── metadata.ts   # GraphQL metadata fetching
├── html.ts       # OG HTML generation
└── types.ts      # TypeScript interfaces
```

## Supported Deep-Link Patterns

| Pattern | Entity | Example |
|---------|--------|---------|
| `/c/{user}/{corpus}` | Corpus | `/c/john/legal-contracts` |
| `/c/{user}/{corpus}/discussions/{threadId}` | Thread | `/c/john/contracts/discussions/abc123` |
| `/d/{user}/{document}` | Document | `/d/jane/my-document` |
| `/d/{user}/{corpus}/{document}` | Document in Corpus | `/d/john/contracts/2024-deal` |
| `/e/{user}/{extractId}` | Extract | `/e/john/RXh0cmFjdFR5cGU6MTIz` |

## Detected Crawlers

- Twitter/X (`Twitterbot`)
- Facebook (`facebookexternalhit`)
- LinkedIn (`LinkedInBot`)
- Slack (`Slackbot`)
- Discord (`Discordbot`)
- WhatsApp
- Telegram (`TelegramBot`)
- Pinterest
- Apple (`Applebot`)
- Reddit (`Redditbot`)

## OG Images

Create static preview images at `{OG_IMAGE_BASE}/`:

- `default-og.png` (1200x630) - Generic cite branding
- `corpus-og.png` (1200x630) - Corpus icon
- `document-og.png` (1200x630) - Document icon
- `discussion-og.png` (1200x630) - Discussion icon
- `extract-og.png` (1200x630) - Extract icon

## Testing OG Tags

Use these validators after deployment:

- [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/)
- [Twitter Card Validator](https://cards-dev.twitter.com/validator)
- [LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/)
- [OpenGraph.xyz](https://www.opengraph.xyz/)

## Backend Requirements

The worker requires these GraphQL queries on the backend:

- `ogCorpusMetadata(userSlug, corpusSlug)`
- `ogDocumentMetadata(userSlug, documentSlug)`
- `ogDocumentInCorpusMetadata(userSlug, corpusSlug, documentSlug)`
- `ogThreadMetadata(userSlug, corpusSlug, threadId)`
- `ogExtractMetadata(extractId)`

These are implemented in `config/graphql/queries.py` and only return data for public entities (`is_public=True`).

## Caching

- Successful OG responses: Cached 1 hour (`Cache-Control: max-age=3600`)
- Generic fallback responses: Cached 24 hours (`Cache-Control: max-age=86400`)

Cloudflare will cache at the edge. To invalidate, use the Cloudflare API or dashboard.

## Documentation

- [Full Architecture Guide](../docs/architecture/social-media-previews.md)
- [Deep-Linking System](../docs/architecture/deep-linking.md)
- [Cloudflare Workers Docs](https://developers.cloudflare.com/workers/)

## Troubleshooting

### Worker not intercepting requests

1. Ensure routes are correctly configured in `wrangler.toml`
2. Check that your domain is proxied through Cloudflare (orange cloud in DNS)
3. Verify routes are deployed: `npx wrangler route list`

### OG tags not showing in validators

1. Check worker logs: `npx wrangler tail`
2. Verify the entity is public (`is_public=True`)
3. Test the GraphQL query directly on the backend
4. Clear Facebook/Twitter caches via their debug tools

### Images not loading

1. Ensure `OG_IMAGE_BASE` points to accessible URLs
2. Check CORS headers if images are on different domain
3. Verify image dimensions (1200x630 recommended)
