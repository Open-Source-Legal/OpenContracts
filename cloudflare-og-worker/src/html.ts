/**
 * HTML generation for Open Graph meta tags
 *
 * Generates minimal HTML pages with proper OG/Twitter meta tags
 * for social media link previews.
 */

import type { Env, OGMetadata, LabeledData } from "./types";
import { getEntityTypeLabel } from "./parser";

/**
 * Escape HTML special characters to prevent XSS
 */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Truncate string to max length with ellipsis
 */
function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + "...";
}

/**
 * Generate Twitter labeled data meta tags (up to 2 pairs supported by Twitter)
 */
function buildTwitterLabelTags(labeledData?: LabeledData[]): string {
  if (!labeledData || labeledData.length === 0) return "";

  // Twitter supports at most label1/data1 and label2/data2
  return labeledData
    .slice(0, 2)
    .map(
      (item, i) =>
        `  <meta name="twitter:label${i + 1}" content="${escapeHtml(item.label)}">\n` +
        `  <meta name="twitter:data${i + 1}" content="${escapeHtml(item.value)}">`
    )
    .join("\n");
}

/**
 * Generate HTML with Open Graph meta tags for entity preview
 *
 * @param metadata - Entity metadata
 * @param canonicalUrl - Canonical URL for the entity
 * @param env - Worker environment bindings
 * @returns HTML string with OG meta tags
 */
export function generateOGHtml(
  metadata: OGMetadata,
  canonicalUrl: string,
  env: Env
): string {
  const title = escapeHtml(metadata.title);
  const description = escapeHtml(truncate(metadata.description, 200));
  const image = metadata.image || `${env.OG_IMAGE_BASE}/default-og.png`;
  const siteName = "cite";

  // Build full title with entity type badge
  const typeLabel = getEntityTypeLabel(metadata.type);
  const fullTitle = typeLabel ? `${title} | ${typeLabel}` : title;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${fullTitle} - ${siteName}</title>

  <!-- Open Graph / Facebook -->
  <meta property="og:type" content="website">
  <meta property="og:url" content="${escapeHtml(canonicalUrl)}">
  <meta property="og:title" content="${fullTitle}">
  <meta property="og:description" content="${description}">
  <meta property="og:image" content="${escapeHtml(image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="${fullTitle}">
  <meta property="og:site_name" content="${siteName}">
  <meta property="og:locale" content="en_US">

  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:url" content="${escapeHtml(canonicalUrl)}">
  <meta name="twitter:title" content="${fullTitle}">
  <meta name="twitter:description" content="${description}">
  <meta name="twitter:image" content="${escapeHtml(image)}">
  <meta name="twitter:image:alt" content="${fullTitle}">
${buildTwitterLabelTags(metadata.labeledData)}

  <!-- Additional SEO -->
  <meta name="description" content="${description}">
  <meta name="author" content="${escapeHtml(metadata.creatorName)}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="${escapeHtml(canonicalUrl)}">

  <!-- Redirect to actual page -->
  <meta http-equiv="refresh" content="0;url=${escapeHtml(canonicalUrl)}">

  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      margin: 0;
      padding: 1rem;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
    }
    .card {
      background: rgba(255, 255, 255, 0.95);
      color: #333;
      padding: 2rem;
      border-radius: 12px;
      max-width: 600px;
      text-align: center;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
    }
    .badge {
      display: inline-block;
      background: #667eea;
      color: #fff;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 1rem;
    }
    h1 {
      margin: 0 0 0.5rem;
      font-size: 1.5rem;
      line-height: 1.3;
    }
    .description {
      color: #666;
      margin: 0 0 1.5rem;
      line-height: 1.5;
    }
    .author {
      font-size: 0.875rem;
      color: #888;
      margin-bottom: 1rem;
    }
    a {
      display: inline-block;
      background: #667eea;
      color: #fff;
      text-decoration: none;
      padding: 0.75rem 1.5rem;
      border-radius: 8px;
      font-weight: 500;
      transition: background 0.2s, transform 0.2s;
    }
    a:hover {
      background: #5a6fd6;
      transform: translateY(-1px);
    }
    .spinner {
      margin-top: 1rem;
      font-size: 0.875rem;
      color: #888;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    .pulse {
      animation: pulse 1.5s ease-in-out infinite;
    }
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">${escapeHtml(typeLabel)}</span>
    <h1>${title}</h1>
    <p class="description">${description}</p>
    <p class="author">by ${escapeHtml(metadata.creatorName)}</p>
    <a href="${escapeHtml(canonicalUrl)}">View on cite.opensource.legal</a>
    <p class="spinner pulse">Redirecting...</p>
  </div>
  <noscript>
    <style>.spinner { display: none; }</style>
  </noscript>
</body>
</html>`;
}

/**
 * Generate generic/fallback OG HTML when entity is not found or private
 *
 * @param canonicalUrl - The requested URL
 * @param env - Worker environment bindings
 * @returns HTML string with generic OG meta tags
 */
export function generateGenericOGHtml(canonicalUrl: string, env: Env): string {
  const siteName = "cite";
  const title = "cite — the citation layer for agentic workflows";
  const description =
    "cite turns a repository of documents into an open citation graph that humans and AI agents can read, reason over, and contribute back to.";
  const image = `${env.OG_IMAGE_BASE}/default-og.png`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title}</title>

  <!-- Open Graph -->
  <meta property="og:type" content="website">
  <meta property="og:url" content="${escapeHtml(canonicalUrl)}">
  <meta property="og:title" content="${title}">
  <meta property="og:description" content="${description}">
  <meta property="og:image" content="${escapeHtml(image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:site_name" content="${siteName}">

  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${title}">
  <meta name="twitter:description" content="${description}">
  <meta name="twitter:image" content="${escapeHtml(image)}">

  <!-- Redirect -->
  <meta http-equiv="refresh" content="0;url=${escapeHtml(canonicalUrl)}">
</head>
<body>
  <p>Redirecting to <a href="${escapeHtml(canonicalUrl)}">${title}</a>...</p>
</body>
</html>`;
}
