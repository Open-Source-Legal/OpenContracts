/**
 * cite Social Media Preview Worker
 *
 * This Cloudflare Worker intercepts requests from social media crawlers
 * and returns HTML with Open Graph meta tags for rich link previews.
 *
 * For regular browser requests, the worker passes through to the origin
 * (the React SPA).
 *
 * @see docs/architecture/social-media-previews.md
 */

import type { Env } from "./types";
import { isSocialMediaCrawler, getCrawlerName } from "./crawler";
import { parseRoute, isDeepLinkUrl } from "./parser";
import { fetchOGMetadata } from "./metadata";
import { generateOGHtml, generateGenericOGHtml } from "./html";

/**
 * Pass request through to origin without re-invoking the worker.
 * Uses a header flag to prevent infinite loops in route-based deployments.
 */
async function passToOrigin(request: Request): Promise<Response> {
  // Check if already processed to prevent infinite loops
  if (request.headers.get("X-OG-Worker-Pass")) {
    // This shouldn't happen with proper Cloudflare routing, but safety first
    return new Response("Loop detected", { status: 500 });
  }

  // Create new request with pass-through header
  const headers = new Headers(request.headers);
  headers.set("X-OG-Worker-Pass", "true");

  const originRequest = new Request(request.url, {
    method: request.method,
    headers: headers,
    body: request.body,
    redirect: request.redirect,
  });

  return fetch(originRequest);
}

export default {
  /**
   * Handle incoming requests
   *
   * Flow:
   * 1. Check if request is from a social media crawler
   * 2. If not crawler, pass through to origin (React SPA)
   * 3. If crawler, check if URL is a deep-link
   * 4. If deep-link, fetch metadata and return OG HTML
   * 5. If not deep-link or private entity, return generic OG HTML
   */
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const userAgent = request.headers.get("user-agent") || "";

    // Check for pass-through header to prevent infinite loops
    if (request.headers.get("X-OG-Worker-Pass")) {
      return fetch(request);
    }

    // Log ALL requests for debugging (helps identify unknown crawlers)
    const crawlerName = getCrawlerName(userAgent);
    const isCrawler = isSocialMediaCrawler(userAgent);
    console.log(JSON.stringify({
      event: "request",
      path: url.pathname,
      userAgent: userAgent.substring(0, 200),
      isCrawler,
      crawlerName,
      timestamp: new Date().toISOString(),
    }));

    // Only intercept for social media crawlers
    if (!isSocialMediaCrawler(userAgent)) {
      // Pass through to origin (React SPA)
      return passToOrigin(request);
    }

    // Check if this is a deep-link URL we should handle
    const route = parseRoute(url.pathname);

    if (!route) {
      // Not a recognized deep-link pattern
      // Return generic OG for crawlers on non-deep-link pages
      if (isStaticPage(url.pathname)) {
        return generateGenericResponse(url, env);
      }
      // Pass through for other URLs
      return passToOrigin(request);
    }

    try {
      // Fetch metadata from backend API
      const metadata = await fetchOGMetadata(route, env);

      if (!metadata) {
        // Entity not found or not public
        // Return generic OG HTML instead of error
        console.log(`No public metadata found for ${url.pathname}`);
        return generateGenericResponse(url, env);
      }

      // Generate and return OG HTML
      const html = generateOGHtml(metadata, url.href, env);

      return new Response(html, {
        status: 200,
        headers: {
          "Content-Type": "text/html;charset=UTF-8",
          // Cache successful responses for 1 hour
          "Cache-Control": "public, max-age=3600, s-maxage=3600",
          // Allow crawlers to cache
          "X-Robots-Tag": "index, follow",
          // Indicate this is a crawler response
          "X-OG-Worker": "true",
        },
      });
    } catch (error) {
      console.error("OG Worker error:", error);

      // On error, return generic OG HTML rather than failing
      return generateGenericResponse(url, env);
    }
  },
};

/**
 * Check if the pathname is a static marketing/info page
 */
function isStaticPage(pathname: string): boolean {
  const staticPages = [
    "/",
    "/about",
    "/features",
    "/pricing",
    "/docs",
    "/login",
    "/signup",
    "/register",
  ];
  return staticPages.includes(pathname) || pathname.startsWith("/docs/");
}

/**
 * Generate a generic OG response for fallback cases
 */
function generateGenericResponse(url: URL, env: Env): Response {
  const html = generateGenericOGHtml(url.href, env);

  return new Response(html, {
    status: 200,
    headers: {
      "Content-Type": "text/html;charset=UTF-8",
      // Cache generic responses for 24 hours
      "Cache-Control": "public, max-age=86400, s-maxage=86400",
      "X-Robots-Tag": "index, follow",
      "X-OG-Worker": "true",
      "X-OG-Fallback": "true",
    },
  });
}

// Export types for testing
export type { Env };
