/**
 * Navigation utilities for consistent slug-based routing
 * Only supports new explicit route patterns with /c/, /d/, and /e/ prefixes
 */

import {
  CorpusType,
  DocumentType,
  ExtractType,
  LabelSetType,
  UserType,
} from "../types/graphql-api";

/**
 * Route parsing types
 */
export interface ParsedRoute {
  type:
    | "corpus"
    | "document"
    | "extract"
    | "thread"
    | "labelset"
    | "browse"
    | "unknown";
  userIdent?: string;
  corpusIdent?: string;
  documentIdent?: string;
  extractIdent?: string;
  threadIdent?: string;
  labelsetIdent?: string;
  browsePath?: string;
}

/**
 * Query parameter interface for URL construction
 */
export interface QueryParams {
  annotationIds?: string[];
  analysisIds?: string[];
  extractIds?: string[];
  threadId?: string | null;
  folderId?: string | null;
  tab?: string | null;
  messageId?: string | null;
  homeView?: string | null; // "about" | "toc" - corpus home view selection
  tocExpanded?: boolean; // true to expand all TOC nodes
  view?: string | null; // "landing" | "details" - corpus detail view selection
  version?: number | null; // Document version number (null = current version)
  showStructural?: boolean;
  showSelectedOnly?: boolean;
  showBoundingBoxes?: boolean;
  labelDisplay?: string; // "ALWAYS" | "ON_HOVER" | "HIDE"
  textBlock?: string | null; // compact-encoded text block reference (e.g., "s100-500" or "p0:45-65")
}

/**
 * Minimal location shape needed by update*Param utilities.
 * Accepts React Router's Location or any object with a search string.
 */
export type LocationLike = { search: string };

/**
 * Minimal navigate shape needed by update*Param utilities.
 * Accepts React Router's NavigateFunction when called with a search-only object.
 */
export type NavigateFn = (
  to: { search: string },
  options?: { replace?: boolean }
) => void;

/**
 * Parses a URL pathname into route type and identifiers
 * Supports patterns:
 * - /c/:userIdent/:corpusIdent
 * - /c/:userIdent/:corpusIdent/discussions/:threadId
 * - /d/:userIdent/:docIdent
 * - /d/:userIdent/:corpusIdent/:docIdent
 * - /e/:userIdent/:extractIdent
 * - /annotations, /extracts, /corpuses, /documents, etc.
 *
 * @param pathname - URL pathname to parse
 * @returns Parsed route object with type and identifiers
 */
export function parseRoute(pathname: string): ParsedRoute {
  const segments = pathname.split("/").filter(Boolean);

  // Thread route: /c/user/corpus/discussions/threadId
  if (
    segments[0] === "c" &&
    segments.length === 5 &&
    segments[3] === "discussions"
  ) {
    return {
      type: "thread",
      userIdent: segments[1],
      corpusIdent: segments[2],
      threadIdent: segments[4],
    };
  }

  // Corpus route: /c/user/corpus
  if (segments[0] === "c" && segments.length === 3) {
    return {
      type: "corpus",
      userIdent: segments[1],
      corpusIdent: segments[2],
    };
  }

  // Document routes
  if (segments[0] === "d") {
    // /d/user/corpus/document (4 segments)
    if (segments.length === 4) {
      return {
        type: "document",
        userIdent: segments[1],
        corpusIdent: segments[2],
        documentIdent: segments[3],
      };
    }
    // /d/user/document (3 segments)
    if (segments.length === 3) {
      return {
        type: "document",
        userIdent: segments[1],
        documentIdent: segments[2],
      };
    }
  }

  // Extract route: /e/user/extract-id
  if (segments[0] === "e" && segments.length === 3) {
    return {
      type: "extract",
      userIdent: segments[1],
      extractIdent: segments[2],
    };
  }

  // LabelSet route: /label_sets/:id (ID-based, labelsets don't have slugs)
  if (segments[0] === "label_sets" && segments.length === 2) {
    return {
      type: "labelset",
      labelsetIdent: segments[1],
    };
  }

  // Browse routes: /annotations, /extracts, /corpuses, /documents, /label_sets, /discussions
  const browseRoutes = [
    "annotations",
    "extracts",
    "corpuses",
    "documents",
    "label_sets",
    "discussions",
  ];
  if (segments.length === 1 && browseRoutes.includes(segments[0])) {
    return {
      type: "browse",
      browsePath: segments[0],
    };
  }

  return { type: "unknown" };
}

/**
 * Parses a comma-separated query parameter into an array
 * @param param - Query parameter value (e.g., "1,2,3" or null)
 * @returns Array of strings, or empty array if null/empty
 */
export function parseQueryParam(param: string | null): string[] {
  if (!param) return [];
  return param.split(",").filter(Boolean);
}

/**
 * Builds canonical path from corpus/document/extract entities
 * @param document - Optional document entity
 * @param corpus - Optional corpus entity
 * @param extract - Optional extract entity
 * @returns Canonical path or empty string if entities missing
 */
export function buildCanonicalPath(
  document?: DocumentType | null,
  corpus?: CorpusType | null,
  extract?: ExtractType | null
): string {
  // Extract (ID-based since extracts don't have slugs yet)
  if (extract?.id && extract?.creator?.slug) {
    return `/e/${extract.creator.slug}/${extract.id}`;
  }

  // Document in corpus context
  if (
    document?.slug &&
    document?.creator?.slug &&
    corpus?.slug &&
    corpus?.creator?.slug
  ) {
    return `/d/${corpus.creator.slug}/${corpus.slug}/${document.slug}`;
  }

  // Standalone document
  if (document?.slug && document?.creator?.slug) {
    return `/d/${document.creator.slug}/${document.slug}`;
  }

  // Corpus only
  if (corpus?.slug && corpus?.creator?.slug) {
    return `/c/${corpus.creator.slug}/${corpus.slug}`;
  }

  return "";
}

/**
 * Builds a query string from multiple parameter arrays
 * Used for preserving state across navigation
 *
 * @example
 * buildQueryParams({ annotationIds: ["1", "2"], analysisIds: ["3"], showStructural: true })
 * // Returns: "?ann=1,2&analysis=3&structural=true"
 */
export function buildQueryParams(params: QueryParams): string {
  const searchParams = new URLSearchParams();

  // Selection state
  if (params.annotationIds?.length) {
    searchParams.set("ann", params.annotationIds.join(","));
  }
  if (params.analysisIds?.length) {
    searchParams.set("analysis", params.analysisIds.join(","));
  }
  if (params.extractIds?.length) {
    searchParams.set("extract", params.extractIds.join(","));
  }
  if (params.threadId) {
    searchParams.set("thread", params.threadId);
  }
  if (params.folderId) {
    searchParams.set("folder", params.folderId);
  }
  if (params.tab) {
    searchParams.set("tab", params.tab);
  }
  if (params.messageId) {
    searchParams.set("message", params.messageId);
  }
  if (params.homeView) {
    searchParams.set("homeView", params.homeView);
  }
  if (params.tocExpanded) {
    searchParams.set("tocExpanded", "true");
  }
  if (params.view && params.view !== "landing") {
    // Only add to URL if not default value
    searchParams.set("view", params.view);
  }
  if (params.version != null && params.version > 0) {
    searchParams.set("v", String(params.version));
  }

  // Visualization state - only add non-default values to keep URLs clean
  if (params.showStructural) {
    searchParams.set("structural", "true");
  }
  if (params.showSelectedOnly) {
    searchParams.set("selectedOnly", "true");
  }
  if (params.showBoundingBoxes) {
    searchParams.set("boundingBoxes", "true");
  }
  if (params.labelDisplay && params.labelDisplay !== "ON_HOVER") {
    // Only add if not the default
    searchParams.set("labels", params.labelDisplay);
  }

  // Text block deep link (compact-encoded reference to document text).
  // When null/undefined, the param is simply omitted (searchParams is fresh).
  if (params.textBlock) {
    searchParams.set("tb", params.textBlock);
  }

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

/**
 * Builds the URL for a corpus
 * Always uses slug-based URL with /c/ prefix
 *
 * @param corpus - Corpus object with slug and creator
 * @param queryParams - Optional query parameters for URL-driven state
 * @returns Full corpus URL with query string, or "#" if slugs missing
 */
export function getCorpusUrl(
  corpus: Pick<CorpusType, "id" | "slug"> & {
    creator?: Pick<UserType, "id" | "slug"> | null;
  },
  queryParams?: QueryParams
): string {
  // Always use slug-based URL with /c/ prefix
  // If slugs are missing, we can't generate a valid URL
  if (!corpus.slug || !corpus.creator?.slug) {
    console.warn("Cannot generate corpus URL without slugs:", corpus);
    return "#"; // Return a safe fallback that won't navigate
  }

  const basePath = `/c/${corpus.creator.slug}/${corpus.slug}`;
  const query = queryParams ? buildQueryParams(queryParams) : "";
  return basePath + query;
}

/**
 * Builds the URL for a document
 * Always uses slug-based URL with /d/ prefix
 *
 * @param document - Document object with slug and creator
 * @param corpus - Optional corpus for context (generates 3-segment URL)
 * @param queryParams - Optional query parameters for URL-driven state
 * @returns Full document URL with query string, or "#" if slugs missing
 */
export function getDocumentUrl(
  document: Pick<DocumentType, "id" | "slug"> & {
    creator?: Pick<UserType, "id" | "slug"> | null;
  },
  corpus?:
    | (Pick<CorpusType, "id" | "slug"> & {
        creator?: Pick<UserType, "id" | "slug"> | null;
      })
    | null,
  queryParams?: QueryParams
): string {
  let basePath: string;

  // If we have corpus context and all slugs, use the full URL
  if (
    corpus?.slug &&
    corpus?.creator?.slug &&
    document.slug &&
    document.creator?.slug
  ) {
    basePath = `/d/${corpus.creator.slug}/${corpus.slug}/${document.slug}`;
  }
  // Standalone document URL
  else if (document.slug && document.creator?.slug) {
    basePath = `/d/${document.creator.slug}/${document.slug}`;
  }
  // Can't generate URL without slugs
  else {
    console.warn(
      "Cannot generate document URL without slugs:",
      document,
      corpus
    );
    return "#"; // Return a safe fallback that won't navigate
  }

  const query = queryParams ? buildQueryParams(queryParams) : "";
  return basePath + query;
}

/**
 * Builds the URL for an extract
 * Uses ID-based URL with /e/ prefix (extracts don't have slugs yet)
 *
 * @param extract - Extract object with id and creator
 * @param queryParams - Optional query parameters for URL-driven state
 * @returns Full extract URL with query string, or "#" if required fields missing
 */
export function getExtractUrl(
  extract: Pick<ExtractType, "id" | "name"> & {
    creator?: Pick<UserType, "id" | "slug"> | null;
  },
  queryParams?: QueryParams
): string {
  // Extracts don't have slugs yet, so we use ID-based URLs
  if (!extract.id || !extract.creator?.slug) {
    console.warn(
      "Cannot generate extract URL without id and creator slug:",
      extract
    );
    return "#"; // Return a safe fallback that won't navigate
  }

  const basePath = `/e/${extract.creator.slug}/${extract.id}`;
  const query = queryParams ? buildQueryParams(queryParams) : "";
  return basePath + query;
}

/**
 * Builds the URL for a labelset
 * Uses ID-based URL since labelsets don't have slugs
 *
 * @param labelset - LabelSet object with id
 * @returns Full labelset URL, or "#" if id missing
 */
export function getLabelsetUrl(labelset: Pick<LabelSetType, "id">): string {
  if (!labelset.id) {
    console.warn("Cannot generate labelset URL without id:", labelset);
    return "#"; // Return a safe fallback that won't navigate
  }

  return `/label_sets/${labelset.id}`;
}

/**
 * Smart navigation function for labelsets
 * Only navigates if not already at the destination
 *
 * @param labelset - LabelSet to navigate to
 * @param navigate - React Router navigate function
 * @param currentPath - Current path to check if already at destination
 */
export function navigateToLabelset(
  labelset: Pick<LabelSetType, "id">,
  navigate: (path: string, options?: { replace?: boolean }) => void,
  currentPath?: string
) {
  const targetPath = getLabelsetUrl(labelset);

  // Don't navigate to invalid URL
  if (targetPath === "#") {
    console.error("Cannot navigate to labelset without id");
    return;
  }

  // Don't navigate if we're already there
  if (currentPath && isCanonicalPath(currentPath, targetPath)) {
    return;
  }

  // Push to history (not replace) so back button works
  navigate(targetPath);
}

/**
 * Checks if the current path matches the canonical path
 * Prevents unnecessary redirects
 */
export function isCanonicalPath(
  currentPath: string,
  canonicalPath: string
): boolean {
  // Normalize paths (remove trailing slashes, query params)
  const normalize = (path: string) => {
    const withoutQuery = path.split("?")[0];
    return withoutQuery.replace(/\/$/, "").toLowerCase();
  };

  return normalize(currentPath) === normalize(canonicalPath);
}

/**
 * Smart navigation function for corpuses
 * Only navigates if not already at the destination
 *
 * @param corpus - Corpus to navigate to
 * @param navigate - React Router navigate function
 * @param currentPath - Current path to check if already at destination
 * @param queryParams - Optional query parameters to preserve in URL
 */
export function navigateToCorpus(
  corpus: Pick<CorpusType, "id" | "slug"> & {
    creator?: Pick<UserType, "id" | "slug"> | null;
  },
  navigate: (path: string, options?: { replace?: boolean }) => void,
  currentPath?: string,
  queryParams?: QueryParams
) {
  const targetPath = getCorpusUrl(corpus, queryParams);

  // Don't navigate to invalid URL
  if (targetPath === "#") {
    console.error("Cannot navigate to corpus without slugs");
    return;
  }

  // Don't navigate if we're already there
  if (currentPath && isCanonicalPath(currentPath, targetPath)) {
    return;
  }

  // Push to history (not replace) so back button works
  navigate(targetPath);
}

/**
 * Smart navigation function for documents
 * Only navigates if not already at the destination
 *
 * @param document - Document to navigate to
 * @param corpus - Optional corpus for context (creates 3-segment URL)
 * @param navigate - React Router navigate function
 * @param currentPath - Current path to check if already at destination
 * @param queryParams - Optional query parameters to preserve in URL
 */
export function navigateToDocument(
  document: Pick<DocumentType, "id" | "slug"> & {
    creator?: Pick<UserType, "id" | "slug"> | null;
  },
  corpus:
    | (Pick<CorpusType, "id" | "slug"> & {
        creator?: Pick<UserType, "id" | "slug"> | null;
      })
    | null,
  navigate: (path: string, options?: { replace?: boolean }) => void,
  currentPath?: string,
  queryParams?: QueryParams
) {
  const targetPath = getDocumentUrl(document, corpus, queryParams);

  // Don't navigate to invalid URL
  if (targetPath === "#") {
    console.error("Cannot navigate to document without slugs");
    return;
  }

  // Don't navigate if we're already there
  if (currentPath && isCanonicalPath(currentPath, targetPath)) {
    return;
  }

  // Push to history (not replace) so back button works
  navigate(targetPath);
}

/**
 * Smart navigation function for extracts
 * Only navigates if not already at the destination
 *
 * @param extract - Extract to navigate to
 * @param navigate - React Router navigate function
 * @param currentPath - Current path to check if already at destination
 * @param queryParams - Optional query parameters to preserve in URL
 */
export function navigateToExtract(
  extract: Pick<ExtractType, "id" | "name"> & {
    creator?: Pick<UserType, "id" | "slug"> | null;
  },
  navigate: (path: string, options?: { replace?: boolean }) => void,
  currentPath?: string,
  queryParams?: QueryParams
) {
  const targetPath = getExtractUrl(extract, queryParams);

  // Don't navigate to invalid URL
  if (targetPath === "#") {
    console.error("Cannot navigate to extract without id and creator slug");
    return;
  }

  // Don't navigate if we're already there
  if (currentPath && isCanonicalPath(currentPath, targetPath)) {
    return;
  }

  // Push to history (not replace) so back button works
  navigate(targetPath);
}

/**
 * Request tracking to prevent duplicate GraphQL queries
 */
class RequestTracker {
  private pendingRequests: Map<string, Promise<any>> = new Map();

  isPending(key: string): boolean {
    return this.pendingRequests.has(key);
  }

  async trackRequest<T>(key: string, request: () => Promise<T>): Promise<T> {
    // If already pending, return the existing promise
    const pending = this.pendingRequests.get(key);
    if (pending) {
      return pending;
    }

    // Create and track new request
    const promise = request().finally(() => {
      this.pendingRequests.delete(key);
    });

    this.pendingRequests.set(key, promise);
    return promise;
  }
}

export const requestTracker = new RequestTracker();

/**
 * Build a unique key for request deduplication
 */
export function buildRequestKey(
  type: "corpus" | "document" | "extract" | "thread" | "labelset",
  userIdent?: string,
  corpusIdent?: string,
  documentIdent?: string,
  extractIdent?: string,
  threadIdent?: string,
  labelsetIdent?: string
): string {
  const parts = [
    type,
    userIdent,
    corpusIdent,
    documentIdent,
    extractIdent,
    threadIdent,
    labelsetIdent,
  ].filter(Boolean);
  return parts.join("-");
}

/**
 * SACRED UTILITY: Update annotation display settings via URL
 * Components MUST use this instead of directly setting reactive vars
 *
 * @param location - Current location from useLocation()
 * @param navigate - Navigate function from useNavigate()
 * @param settings - Display settings to update
 *
 * @example
 * updateAnnotationDisplayParams(location, navigate, {
 *   showStructural: true,
 *   showBoundingBoxes: true,
 *   labelDisplay: "ALWAYS"
 * });
 */
export function updateAnnotationDisplayParams(
  location: LocationLike,
  navigate: NavigateFn,
  settings: {
    showStructural?: boolean;
    showSelectedOnly?: boolean;
    showBoundingBoxes?: boolean;
    labelDisplay?: string;
  }
) {
  const searchParams = new URLSearchParams(location.search);

  // Update only specified params
  if (settings.showStructural !== undefined) {
    if (settings.showStructural) {
      searchParams.set("structural", "true");
    } else {
      searchParams.delete("structural");
    }
  }

  if (settings.showSelectedOnly !== undefined) {
    if (settings.showSelectedOnly) {
      searchParams.set("selectedOnly", "true");
    } else {
      searchParams.delete("selectedOnly");
    }
  }

  if (settings.showBoundingBoxes !== undefined) {
    if (settings.showBoundingBoxes) {
      searchParams.set("boundingBoxes", "true");
    } else {
      searchParams.delete("boundingBoxes");
    }
  }

  if (settings.labelDisplay !== undefined) {
    if (settings.labelDisplay !== "ON_HOVER") {
      searchParams.set("labels", settings.labelDisplay);
    } else {
      searchParams.delete("labels");
    }
  }

  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * SACRED UTILITY: Update annotation selection via URL
 * Components MUST use this instead of directly setting reactive vars
 *
 * @param location - Current location from useLocation()
 * @param navigate - Navigate function from useNavigate()
 * @param selection - Selection IDs to update
 *
 * @example
 * updateAnnotationSelectionParams(location, navigate, {
 *   annotationIds: ["123", "456"]
 * });
 */
export function updateAnnotationSelectionParams(
  location: LocationLike,
  navigate: NavigateFn,
  selection: {
    annotationIds?: string[];
    analysisIds?: string[];
    extractIds?: string[];
  }
) {
  const searchParams = new URLSearchParams(location.search);

  // Update only specified params.
  // An empty array removes the param from the URL (clears the selection).
  if (selection.annotationIds !== undefined) {
    if (selection.annotationIds.length > 0) {
      searchParams.set("ann", selection.annotationIds.join(","));
    } else {
      searchParams.delete("ann");
    }
  }

  if (selection.analysisIds !== undefined) {
    if (selection.analysisIds.length > 0) {
      searchParams.set("analysis", selection.analysisIds.join(","));
    } else {
      searchParams.delete("analysis");
    }
  }

  if (selection.extractIds !== undefined) {
    if (selection.extractIds.length > 0) {
      searchParams.set("extract", selection.extractIds.join(","));
    } else {
      searchParams.delete("extract");
    }
  }

  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * SACRED UTILITY: Clear all annotation selection via URL
 * Use this for cleanup on unmount
 *
 * @param location - Current location from useLocation()
 * @param navigate - Navigate function from useNavigate()
 */
export function clearAnnotationSelection(
  location: { search: string },
  navigate: (to: { search: string }, options?: { replace?: boolean }) => void
) {
  updateAnnotationSelectionParams(location, navigate, {
    annotationIds: [],
    analysisIds: [],
    extractIds: [],
  });
}

// ═══════════════════════════════════════════════════════════════
// Thread/Discussion Navigation Utilities
// ═══════════════════════════════════════════════════════════════

/**
 * Generate corpus thread URL for full-page view
 * @param corpus - Corpus object with creator and slug
 * @param threadId - Thread/conversation ID
 * @returns Full URL path for corpus thread view, or "#" if slugs missing
 * @example
 * getCorpusThreadUrl({ creator: { slug: "john" }, slug: "legal-docs" }, "thread-123")
 * // Returns: "/c/john/legal-docs/discussions/thread-123"
 */
export function getCorpusThreadUrl(
  corpus: {
    creator?: { slug?: string | null } | null;
    slug?: string | null;
  },
  threadId: string
): string {
  if (!corpus.creator?.slug || !corpus.slug) {
    console.warn("Corpus missing slug data:", corpus);
    return "#";
  }
  return `/c/${corpus.creator.slug}/${corpus.slug}/discussions/${threadId}`;
}

/**
 * Navigate to corpus thread (full page)
 * @param corpus - Corpus object with creator and slug
 * @param threadId - Thread/conversation ID
 * @param navigate - React Router navigate function
 * @param currentPath - Current pathname to avoid redundant navigation
 */
export function navigateToCorpusThread(
  corpus: {
    creator?: { slug?: string | null } | null;
    slug?: string | null;
  },
  threadId: string,
  navigate: (path: string) => void,
  currentPath: string
) {
  const url = getCorpusThreadUrl(corpus, threadId);
  if (url !== "#" && currentPath !== url) {
    navigate(url);
  }
}

/**
 * Navigate to document thread (sidebar via query param)
 * Used for document-scoped threads that open in sidebars rather than full-page views
 * @param threadId - Thread/conversation ID
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 */
export function navigateToDocumentThread(
  threadId: string,
  location: { search: string },
  navigate: (to: { search: string }, options?: { replace?: boolean }) => void
) {
  const searchParams = new URLSearchParams(location.search);
  searchParams.set("thread", threadId);
  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * Clear thread selection from URL
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 */
export function clearThreadSelection(
  location: { search: string },
  navigate: (to: { search: string }, options?: { replace?: boolean }) => void
) {
  const searchParams = new URLSearchParams(location.search);
  searchParams.delete("thread");
  searchParams.delete("message"); // Also clear message when clearing thread
  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * Update tab selection in URL
 * Used for deep-linking to specific tabs in corpus or document views.
 * Pushes a new history entry so browser back/forward navigates between tabs.
 * Also clears tab-specific params (thread, message) when switching tabs to
 * prevent stale state from persisting across tab changes.
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 * @param tabId - Tab identifier (e.g., "discussions", "documents", "chat", "feed")
 *                Pass null to clear tab and use default
 */
export function updateTabParam(
  location: LocationLike,
  navigate: NavigateFn,
  tabId: string | null
) {
  const searchParams = new URLSearchParams(location.search);
  if (tabId) {
    searchParams.set("tab", tabId);
  } else {
    searchParams.delete("tab");
  }
  // Clear tab-specific params to prevent stale state across tabs
  searchParams.delete("thread");
  searchParams.delete("message");
  // Replace (not push) so tab switches don't accumulate history entries
  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * Update thread selection in URL
 * Used for deep-linking to a specific thread in corpus discussions.
 * By default pushes a new history entry so browser back/forward navigates
 * between thread list and thread detail views. Pass `{ replace: true }` to
 * replace the current entry instead (useful for "back to list" actions).
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 * @param threadId - Thread identifier, or null to clear and return to list
 * @param options - Optional navigation options (e.g., `{ replace: true }`)
 */
export function updateThreadParam(
  location: LocationLike,
  navigate: NavigateFn,
  threadId: string | null,
  options?: { replace?: boolean }
) {
  const searchParams = new URLSearchParams(location.search);
  if (threadId) {
    searchParams.set("thread", threadId);
  } else {
    searchParams.delete("thread");
    searchParams.delete("message"); // Also clear message when clearing thread
  }
  // Default: push so browser back returns to the thread list
  const searchString = { search: searchParams.toString() };
  if (options) {
    navigate(searchString, options);
  } else {
    navigate(searchString);
  }
}

/**
 * Update corpus home view selection in URL
 * Used for deep-linking to specific view (about/summary vs table of contents) on corpus home
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 * @param homeView - View identifier ("about" or "toc")
 *                   Pass null to clear and use default (about)
 */
export function updateHomeViewParam(
  location: LocationLike,
  navigate: NavigateFn,
  homeView: "about" | "toc" | null
) {
  const searchParams = new URLSearchParams(location.search);
  if (homeView && homeView !== "about") {
    // Only add to URL if not default value
    searchParams.set("homeView", homeView);
  } else {
    searchParams.delete("homeView");
  }
  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * Update TOC expand all state in URL
 * Used for deep-linking to a fully expanded Table of Contents view
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 * @param expanded - Whether all TOC nodes should be expanded
 *                   Pass false to clear and use default (collapsed)
 */
export function updateTocExpandedParam(
  location: LocationLike,
  navigate: NavigateFn,
  expanded: boolean
) {
  const searchParams = new URLSearchParams(location.search);
  if (expanded) {
    searchParams.set("tocExpanded", "true");
  } else {
    searchParams.delete("tocExpanded");
  }
  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * Update corpus detail view selection in URL
 * Used for switching between landing view and details view on corpus home.
 * Pushes a new history entry so browser back/forward navigates between views.
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 * @param view - View identifier ("landing" or "details")
 *               Pass "landing" or null to clear and use default (landing)
 */
export function updateDetailViewParam(
  location: LocationLike,
  navigate: NavigateFn,
  view: "landing" | "details" | null
) {
  const searchParams = new URLSearchParams(location.search);
  if (view && view !== "landing") {
    // Only add to URL if not default value
    searchParams.set("view", view);
  } else {
    searchParams.delete("view");
  }
  // Push (not replace) so browser back returns to the previous view
  navigate({ search: searchParams.toString() });
}

/**
 * Update message selection in URL for thread deep-linking
 * Used to link directly to a specific message within a thread
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 * @param messageId - Message identifier, or null to clear
 */
export function updateMessageParam(
  location: LocationLike,
  navigate: NavigateFn,
  messageId: string | null
) {
  const searchParams = new URLSearchParams(location.search);
  if (messageId) {
    searchParams.set("message", messageId);
  } else {
    searchParams.delete("message");
  }
  navigate({ search: searchParams.toString() }, { replace: true });
}

/**
 * Navigate to thread with optional message deep-link
 * @param location - React Router location object
 * @param navigate - React Router navigate function
 * @param threadId - Thread/conversation ID
 * @param messageId - Optional message ID to highlight
 */
export function navigateToThreadWithMessage(
  location: LocationLike,
  navigate: NavigateFn,
  threadId: string,
  messageId?: string
) {
  const searchParams = new URLSearchParams(location.search);
  searchParams.set("thread", threadId);
  if (messageId) {
    searchParams.set("message", messageId);
  }
  navigate({ search: searchParams.toString() }, { replace: true });
}

// ═══════════════════════════════════════════════════════════════
// Simplified Document Click Handler for Relationship Views
// ═══════════════════════════════════════════════════════════════

/**
 * Minimal document interface for relationship views
 * Used by DocumentTableOfContents and CorpusDocumentRelationships
 */
export interface RelationshipDocumentInfo {
  id: string;
  title: string;
  slug?: string | null;
  creator?: { slug?: string | null } | null;
}

/**
 * Navigate to a document from relationship views (Table of Contents, Relationships tab)
 * Uses the currently opened corpus context from the reactive variable.
 *
 * @param document - Document info from relationship query
 * @param corpus - Corpus to use for context (with creator slug info)
 * @param navigate - React Router navigate function
 * @param currentPath - Current pathname for dedup check
 */
export function navigateToRelationshipDocument(
  document: RelationshipDocumentInfo,
  corpus: {
    id?: string;
    slug?: string | null;
    creator?: { slug?: string | null } | null;
  } | null,
  navigate: (path: string, options?: { replace?: boolean }) => void,
  currentPath?: string
) {
  if (!corpus) {
    console.warn("Cannot navigate to document - no corpus context");
    return;
  }

  // Build the document object with creator info
  // If document has its own creator, use that; otherwise inherit from corpus
  // Convert null to undefined for type compatibility
  // Note: navigateToDocument only uses creator.slug for URL building
  const docForNav: Parameters<typeof navigateToDocument>[0] = {
    id: document.id,
    slug: document.slug ?? undefined,
    creator: document.creator?.slug
      ? { id: "", slug: document.creator.slug }
      : corpus.creator?.slug
      ? { id: "", slug: corpus.creator.slug }
      : undefined,
  };

  const corpusForNav: Parameters<typeof navigateToDocument>[1] = {
    id: corpus.id ?? "",
    slug: corpus.slug ?? undefined,
    creator: corpus.creator?.slug
      ? { id: "", slug: corpus.creator.slug }
      : undefined,
  };

  navigateToDocument(docForNav, corpusForNav, navigate, currentPath);
}

// ═══════════════════════════════════════════════════════════════
// Text Block Deep Link Navigation Utilities
// ═══════════════════════════════════════════════════════════════

/**
 * SACRED UTILITY: Update text block deep link via URL
 * Components MUST use this instead of directly setting reactive vars
 *
 * @param location - Current location from useLocation()
 * @param navigate - Navigate function from useNavigate()
 * @param textBlock - Compact-encoded text block string, or null to clear
 */
export function updateTextBlockParam(
  location: LocationLike,
  navigate: NavigateFn,
  textBlock: string | null
) {
  const searchParams = new URLSearchParams(location.search);
  if (textBlock) {
    searchParams.set("tb", textBlock);
  } else {
    searchParams.delete("tb");
  }
  navigate({ search: searchParams.toString() }, { replace: true });
}
