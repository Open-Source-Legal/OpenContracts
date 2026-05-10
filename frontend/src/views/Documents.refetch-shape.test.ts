/**
 * Source-level regression for the Documents view refetch storm.
 *
 * History (PR #1517 / #1512 cousin): the Documents view used to fire ~7
 * GET_DOCUMENTS network requests on every visit to ``/documents``:
 *
 *   - one from ``useQuery`` itself, plus
 *   - six redundant ``useEffect(() => refetchDocuments())`` hooks watching
 *     ``current_user``, ``location``, ``document_search_term``,
 *     ``filtered_to_label_id``, ``filtered_to_labelset_id``,
 *     ``filtered_to_corpus``, all of which fired on mount, plus
 *   - ``nextFetchPolicy: "network-only"`` forcing every refetch to skip the
 *     cache.
 *
 * The bug is invisible to ``MockedProvider`` because Apollo's default query
 * deduplication merges concurrent in-flight queries into a single request
 * before they reach ``MockLink`` — a behavioral counter on a CT mock cannot
 * distinguish 1 from 7. We therefore pin the structural fix at the source
 * level here. Each assertion below maps to one of the offending shapes.
 *
 * If a future change re-introduces any of these shapes, this test fails
 * loudly with a pointer to the offending pattern.
 */
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const DOCUMENTS_TSX = readFileSync(join(HERE, "Documents.tsx"), "utf8");

describe("Documents view refetch shape (regression)", () => {
  it("does not use nextFetchPolicy: 'network-only'", () => {
    // ``"network-only"`` (with either single or double quotes) on the
    // useQuery options forces every refetch to bypass the Apollo cache.
    // Combined with the deleted refetch storm this produced one network
    // round trip per parent re-render; without the storm it still wastes a
    // round trip on every legitimate refetch.
    const NETWORK_ONLY_RE = /nextFetchPolicy\s*:\s*["']network-only["']/;
    expect(
      NETWORK_ONLY_RE.test(DOCUMENTS_TSX),
      "Documents.tsx must not set nextFetchPolicy: 'network-only' — " +
        "it forces refetches to skip the cache. See PR notes in the file."
    ).toBe(false);
  });

  it("does not call refetchDocuments() from any useEffect block", () => {
    // The original bug had six ``useEffect(() => { refetchDocuments(); }, [...])``
    // hooks that all fired on mount. Any *new* such pattern re-introduces
    // the storm. The ``onCompleted`` callback inside DELETE_MULTIPLE_DOCUMENTS
    // and the "Try Again" button onClick are legitimate refetch sites and
    // are not matched by this regex (they are not inside a ``useEffect``).
    const USE_EFFECT_REFETCH_RE =
      /useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*\brefetchDocuments\s*\(/s;
    expect(
      USE_EFFECT_REFETCH_RE.test(DOCUMENTS_TSX),
      "Documents.tsx must not call refetchDocuments() from a useEffect — " +
        "Apollo's useQuery already refetches when its variables change. " +
        "If you need a refetch trigger, add the value to documentVariables " +
        "instead. See the comment block above the useQuery call."
    ).toBe(false);
  });

  it("imports the slim GET_DOCUMENTS_FOR_LIST query, not the heavy GET_DOCUMENTS", () => {
    // The list view should use the focused query that omits the kitchen
    // sink (``versionCount`` N+1, ``canViewHistory`` per-row permission
    // checks, four file-URL fields, ``doc_label_annotations``, etc.). The
    // shared ``GET_DOCUMENTS`` is fine for callers that legitimately need
    // those fields (modals, corpus tabs, metadata workflow).
    expect(DOCUMENTS_TSX).toMatch(/\bGET_DOCUMENTS_FOR_LIST\b/);
    // Catch a stray import of the heavy query alongside the slim one.
    // We allow the substring to appear in comments or as part of
    // GET_DOCUMENTS_FOR_LIST; what we forbid is a top-level import.
    const HEAVY_IMPORT_RE =
      /\bimport\s*\{[^}]*\bGET_DOCUMENTS\b(?!_FOR_LIST)[^}]*\}\s*from\s*["']\.\.\/graphql\/queries["']/s;
    expect(
      HEAVY_IMPORT_RE.test(DOCUMENTS_TSX),
      "Documents.tsx must not import the heavy GET_DOCUMENTS query — " +
        "use GET_DOCUMENTS_FOR_LIST for the list view."
    ).toBe(false);
  });

  it("passes an explicit page-size limit on the initial query", () => {
    // Without an explicit ``first:`` (frontend variable: ``limit``), the
    // connection's default cap (RELAY_CONNECTION_MAX_LIMIT = 100) was
    // serving the first page, so the very first paint was charged for 100
    // fully-resolved DocumentType rows even though paged loads downstream
    // were 20 rows each.
    expect(DOCUMENTS_TSX).toMatch(/\bDOCUMENTS_PAGE_SIZE\b/);
    expect(DOCUMENTS_TSX).toMatch(/limit\s*:\s*DOCUMENTS_PAGE_SIZE/);
  });
});
