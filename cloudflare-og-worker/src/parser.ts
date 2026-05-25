/**
 * URL route parser for cite deep-links
 *
 * Parses URL pathnames to extract entity information for OG metadata fetching.
 * Supports all deep-link patterns defined in docs/architecture/deep-linking.md
 */

import type { EntityType, ParsedRoute } from "./types";

/**
 * Route pattern definitions
 * Order matters - more specific patterns should be checked first
 */
const ROUTE_PATTERNS: Array<{
  pattern: RegExp;
  type: EntityType;
  extract: (match: RegExpMatchArray) => Partial<ParsedRoute>;
}> = [
  // Thread: /c/{userSlug}/{corpusSlug}/discussions/{threadId}
  {
    pattern: /^\/c\/([^\/]+)\/([^\/]+)\/discussions\/([^\/]+)$/,
    type: "thread",
    extract: (match) => ({
      userSlug: match[1],
      corpusSlug: match[2],
      threadId: match[3],
    }),
  },

  // Corpus: /c/{userSlug}/{corpusSlug}
  {
    pattern: /^\/c\/([^\/]+)\/([^\/]+)$/,
    type: "corpus",
    extract: (match) => ({
      userSlug: match[1],
      corpusSlug: match[2],
    }),
  },

  // Document in corpus: /d/{userSlug}/{corpusSlug}/{documentSlug}
  {
    pattern: /^\/d\/([^\/]+)\/([^\/]+)\/([^\/]+)$/,
    type: "document_in_corpus",
    extract: (match) => ({
      userSlug: match[1],
      corpusSlug: match[2],
      documentSlug: match[3],
    }),
  },

  // Standalone document: /d/{userSlug}/{documentSlug}
  {
    pattern: /^\/d\/([^\/]+)\/([^\/]+)$/,
    type: "document",
    extract: (match) => ({
      userSlug: match[1],
      documentSlug: match[2],
    }),
  },

  // Extract: /e/{userSlug}/{extractId}
  {
    pattern: /^\/e\/([^\/]+)\/([^\/]+)$/,
    type: "extract",
    extract: (match) => ({
      userSlug: match[1],
      extractId: match[2],
    }),
  },
];

/**
 * Parse a URL pathname to extract deep-link route information
 *
 * @param pathname - The URL pathname (e.g., "/c/john/legal-contracts")
 * @returns Parsed route information or null if not a recognized deep-link
 *
 * @example
 * parseRoute('/c/john/legal-contracts')
 * // { type: 'corpus', userSlug: 'john', corpusSlug: 'legal-contracts' }
 *
 * @example
 * parseRoute('/d/john/legal-contracts/my-document')
 * // { type: 'document_in_corpus', userSlug: 'john', corpusSlug: 'legal-contracts', documentSlug: 'my-document' }
 */
export function parseRoute(pathname: string): ParsedRoute | null {
  // Normalize pathname: remove trailing slash, handle encoded characters
  let normalizedPath: string;
  try {
    normalizedPath = decodeURIComponent(pathname.replace(/\/$/, ""));
  } catch {
    // decodeURIComponent throws on malformed URLs (e.g., invalid percent encoding)
    // Return null to trigger fallback behavior
    return null;
  }

  for (const { pattern, type, extract } of ROUTE_PATTERNS) {
    const match = normalizedPath.match(pattern);
    if (match) {
      return {
        type,
        userSlug: "", // Will be overwritten by extract
        ...extract(match),
      } as ParsedRoute;
    }
  }

  return null;
}

/**
 * Check if a pathname matches any deep-link pattern
 *
 * @param pathname - The URL pathname to check
 * @returns true if the pathname is a deep-link URL
 */
export function isDeepLinkUrl(pathname: string): boolean {
  return parseRoute(pathname) !== null;
}

/**
 * Build a canonical URL from parsed route information
 *
 * @param route - Parsed route information
 * @param baseUrl - Base URL of the site
 * @returns Canonical URL string
 */
export function buildCanonicalUrl(route: ParsedRoute, baseUrl: string): string {
  const base = baseUrl.replace(/\/$/, "");

  switch (route.type) {
    case "corpus":
      return `${base}/c/${route.userSlug}/${route.corpusSlug}`;

    case "thread":
      return `${base}/c/${route.userSlug}/${route.corpusSlug}/discussions/${route.threadId}`;

    case "document":
      return `${base}/d/${route.userSlug}/${route.documentSlug}`;

    case "document_in_corpus":
      return `${base}/d/${route.userSlug}/${route.corpusSlug}/${route.documentSlug}`;

    case "extract":
      return `${base}/e/${route.userSlug}/${route.extractId}`;

    default:
      return base;
  }
}

/**
 * Get a human-readable type label for an entity type
 *
 * @param type - Entity type
 * @returns Human-readable label
 */
export function getEntityTypeLabel(type: EntityType): string {
  const labels: Record<EntityType, string> = {
    corpus: "Corpus",
    document: "Document",
    document_in_corpus: "Document",
    thread: "Discussion",
    extract: "Data Extract",
  };
  return labels[type] || "Resource";
}
