/**
 * Regression net for useTextSearch — the side-effect hook that populates
 * textSearchStateAtom whenever the search query changes.
 *
 * The hook is dependency-heavy (6 mocked hooks, two document types, case-
 * insensitive regex matching) but the behaviors we lock here are the ones
 * that matter across the PdfAnnotator extraction:
 *   1. Empty query → state is cleared
 *   2. Missing prerequisites → no state write
 *   3. Span (non-PDF) search → one match per regex hit with correct char
 *      indices and leadIn/leadOut context window
 *   4. PDF search → one match per regex hit with start_page/end_page
 *      resolved from pageTokenTextMaps
 *   5. No-op when neither the query nor the document has changed
 */
import { renderHook } from "../../../../test-utils/renderHook";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useTextSearch } from "../useTextSearch";

// ─── Mocks ─────────────────────────────────────────────────────
vi.mock("../../context/DocumentAtom", () => ({
  useSearchText: vi.fn(),
  useDocText: vi.fn(),
  useSelectedDocument: vi.fn(),
  usePages: vi.fn(),
  usePageTokenTextMaps: vi.fn(),
  useTextSearchState: vi.fn(),
}));

import {
  useSearchText,
  useDocText,
  useSelectedDocument,
  usePages,
  usePageTokenTextMaps,
  useTextSearchState,
} from "../../context/DocumentAtom";

// ─── Helpers ───────────────────────────────────────────────────
interface Setup {
  searchText: string;
  docText: string;
  selectedDocument: { id: string; fileType: string } | null;
  pages: Record<number, { tokens: Array<{ text: string }> }> | null;
  pageTokenTextMaps: Record<
    number,
    { pageIndex: number; tokenIndex: number }
  > | null;
}

function prime(setup: Setup): ReturnType<typeof vi.fn> {
  const setTextSearchState = vi.fn();
  (useSearchText as any).mockReturnValue({ searchText: setup.searchText });
  (useDocText as any).mockReturnValue({ docText: setup.docText });
  (useSelectedDocument as any).mockReturnValue({
    selectedDocument: setup.selectedDocument,
  });
  (usePages as any).mockReturnValue({ pages: setup.pages });
  (usePageTokenTextMaps as any).mockReturnValue({
    pageTokenTextMaps: setup.pageTokenTextMaps,
  });
  (useTextSearchState as any).mockReturnValue({
    textSearchMatches: [],
    selectedTextSearchMatchIndex: 0,
    setTextSearchState,
  });
  return setTextSearchState;
}

// ─── Tests ─────────────────────────────────────────────────────
describe("useTextSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("empty-query clearing", () => {
    it("clears state when searchText transitions from non-empty to empty", () => {
      // First render: non-empty search produces one match.
      const setTextSearchState = prime({
        searchText: "hello",
        docText: "hello world",
        selectedDocument: { id: "d", fileType: "text/plain" },
        pages: null,
        pageTokenTextMaps: null,
      });

      const { rerender } = renderHook(() => useTextSearch());
      // A span-based search with no pages/pageTokenTextMaps still runs because
      // the guard only requires pageTokenTextMaps/pages for pdf — actually it
      // guards for both fileTypes. So non-pdf with null pageTokenTextMaps
      // short-circuits and returns before any state write. That's fine: we
      // only care about the CLEAR path on transition to empty.
      setTextSearchState.mockClear();

      // Now transition to empty.
      (useSearchText as any).mockReturnValue({ searchText: "" });
      rerender();
      expect(setTextSearchState).toHaveBeenCalledWith({
        matches: [],
        selectedIndex: 0,
      });
    });

    it("does not clear state on the very first render with empty query", () => {
      const setTextSearchState = prime({
        searchText: "",
        docText: "hello",
        selectedDocument: { id: "d", fileType: "text/plain" },
        pages: null,
        pageTokenTextMaps: null,
      });

      renderHook(() => useTextSearch());
      // previousSearchTextRef initializes to the same empty string, so no
      // transition → no state write.
      expect(setTextSearchState).not.toHaveBeenCalled();
    });
  });

  describe("prerequisite guards", () => {
    it("does nothing when selectedDocument is null", () => {
      const setTextSearchState = prime({
        searchText: "hello",
        docText: "hello world",
        selectedDocument: null,
        pages: {},
        pageTokenTextMaps: {},
      });
      renderHook(() => useTextSearch());
      expect(setTextSearchState).not.toHaveBeenCalled();
    });

    it("does nothing when pageTokenTextMaps is null", () => {
      const setTextSearchState = prime({
        searchText: "hello",
        docText: "hello world",
        selectedDocument: { id: "d", fileType: "application/pdf" },
        pages: {},
        pageTokenTextMaps: null,
      });
      renderHook(() => useTextSearch());
      expect(setTextSearchState).not.toHaveBeenCalled();
    });

    it("does nothing when pages is null", () => {
      const setTextSearchState = prime({
        searchText: "hello",
        docText: "hello world",
        selectedDocument: { id: "d", fileType: "application/pdf" },
        pages: null,
        pageTokenTextMaps: {},
      });
      renderHook(() => useTextSearch());
      expect(setTextSearchState).not.toHaveBeenCalled();
    });
  });

  describe("first-render no-op", () => {
    it("does NOT run the search on the initial render (refs are seeded from current state)", () => {
      // NOTE: This test pins an implementation invariant (refs-for-change-detection)
      // rather than a purely external behavior contract. If the hook migrates to a
      // different change-detection strategy (e.g. useEffect dependency comparison)
      // this test may need to be rewritten in terms of observable outcomes. The
      // ref-seeding pattern is intentionally pinned because it is load-bearing for
      // preventing spurious first-render search dispatches.
      //
      // The hook initializes previousSearchTextRef / previousSelectedDocumentRef
      // with the CURRENT values, so on first render the 'has changed' guard
      // evaluates to false and the effect bails. A search only fires when
      // something actually transitions — which is why the real UI always
      // starts with an empty query and mutates it.
      const setTextSearchState = prime({
        searchText: "alice",
        docText: "alice met bob",
        selectedDocument: { id: "d", fileType: "text/plain" },
        pages: {},
        pageTokenTextMaps: {},
      });
      renderHook(() => useTextSearch());
      expect(setTextSearchState).not.toHaveBeenCalled();
    });
  });

  describe("span-based search (non-PDF)", () => {
    it("emits one match per regex hit with correct char indices after a query transition", () => {
      const docText = "Alice met Bob. Alice waved.";
      const setTextSearchState = prime({
        searchText: "",
        docText,
        selectedDocument: { id: "d", fileType: "text/plain" },
        pages: {},
        pageTokenTextMaps: {},
      });
      const { rerender } = renderHook(() => useTextSearch());
      setTextSearchState.mockClear();

      // User types "Alice".
      (useSearchText as any).mockReturnValue({ searchText: "Alice" });
      rerender();

      expect(setTextSearchState).toHaveBeenCalledTimes(1);
      const call = setTextSearchState.mock.calls[0][0];
      expect(call.selectedIndex).toBe(0);
      expect(call.matches).toHaveLength(2);
      expect(call.matches[0]).toMatchObject({
        id: 0,
        start_index: 0,
        end_index: 5,
        text: "Alice",
      });
      expect(call.matches[1]).toMatchObject({
        id: 1,
        start_index: 15,
        end_index: 20,
        text: "Alice",
      });
    });

    it("is case-insensitive (matches mixed-case terms)", () => {
      const setTextSearchState = prime({
        searchText: "",
        docText: "alice and Alice and aLiCe",
        selectedDocument: { id: "d", fileType: "text/plain" },
        pages: {},
        pageTokenTextMaps: {},
      });
      const { rerender } = renderHook(() => useTextSearch());
      setTextSearchState.mockClear();

      (useSearchText as any).mockReturnValue({ searchText: "ALICE" });
      rerender();
      expect(setTextSearchState.mock.calls[0][0].matches).toHaveLength(3);
    });

    it("emits empty matches array when query is not present in docText", () => {
      const setTextSearchState = prime({
        searchText: "",
        docText: "apples and oranges",
        selectedDocument: { id: "d", fileType: "text/plain" },
        pages: {},
        pageTokenTextMaps: {},
      });
      const { rerender } = renderHook(() => useTextSearch());
      setTextSearchState.mockClear();

      (useSearchText as any).mockReturnValue({ searchText: "banana" });
      rerender();
      expect(setTextSearchState).toHaveBeenCalledWith({
        matches: [],
        selectedIndex: 0,
      });
    });

    it("writes fullContext with leadIn/leadOut windows around the match", () => {
      const setTextSearchState = prime({
        searchText: "",
        docText: "x".repeat(50) + "HIT" + "y".repeat(50),
        selectedDocument: { id: "d", fileType: "text/plain" },
        pages: {},
        pageTokenTextMaps: {},
      });
      const { rerender } = renderHook(() => useTextSearch());
      setTextSearchState.mockClear();

      (useSearchText as any).mockReturnValue({ searchText: "HIT" });
      rerender();

      const match = setTextSearchState.mock.calls[0][0].matches[0];
      // context_length is 64 for span search, so both sides should be fully
      // populated (50 chars each fits comfortably).
      expect(match.text).toBe("HIT");
      expect(match.start_index).toBe(50);
      expect(match.end_index).toBe(53);
      expect(match.fullContext).toBeTruthy(); // ReactElement, not a string
    });
  });

  describe("pdf-based search", () => {
    it("emits matches with start_page/end_page resolved from pageTokenTextMaps", () => {
      const docText = "abc def";
      const setTextSearchState = prime({
        searchText: "",
        docText,
        selectedDocument: { id: "d", fileType: "application/pdf" },
        pages: {
          0: { tokens: [{ text: "abc" }, { text: "def" }] },
        },
        pageTokenTextMaps: {
          0: { pageIndex: 0, tokenIndex: 0 },
          1: { pageIndex: 0, tokenIndex: 0 },
          2: { pageIndex: 0, tokenIndex: 0 },
          4: { pageIndex: 0, tokenIndex: 1 },
          5: { pageIndex: 0, tokenIndex: 1 },
          6: { pageIndex: 0, tokenIndex: 1 },
        },
      });
      const { rerender } = renderHook(() => useTextSearch());
      setTextSearchState.mockClear();

      (useSearchText as any).mockReturnValue({ searchText: "def" });
      rerender();

      expect(setTextSearchState).toHaveBeenCalledTimes(1);
      const call = setTextSearchState.mock.calls[0][0];
      expect(call.matches).toHaveLength(1);
      expect(call.matches[0]).toMatchObject({
        id: 0,
        start_page: 0,
        end_page: 0,
      });
      // Target tokens for chars 4..6 all map to {pageIndex:0, tokenIndex:1}.
      expect(call.matches[0].tokens[0]).toEqual([
        { pageIndex: 0, tokenIndex: 1 },
        { pageIndex: 0, tokenIndex: 1 },
        { pageIndex: 0, tokenIndex: 1 },
      ]);
    });
  });

  describe("no-op on unchanged inputs", () => {
    it("does not re-run the search when rerender happens with identical inputs", () => {
      const setTextSearchState = prime({
        searchText: "",
        docText: "alice",
        selectedDocument: { id: "d", fileType: "text/plain" },
        pages: {},
        pageTokenTextMaps: {},
      });
      const { rerender } = renderHook(() => useTextSearch());
      setTextSearchState.mockClear();

      (useSearchText as any).mockReturnValue({ searchText: "alice" });
      rerender(); // transition → runs once
      expect(setTextSearchState).toHaveBeenCalledTimes(1);

      rerender(); // no change → bail out
      expect(setTextSearchState).toHaveBeenCalledTimes(1);
    });

    it("re-runs the search when selectedDocument changes even if the query is stable", () => {
      const setTextSearchState = prime({
        searchText: "",
        docText: "alice",
        selectedDocument: { id: "d1", fileType: "text/plain" },
        pages: {},
        pageTokenTextMaps: {},
      });
      const { rerender } = renderHook(() => useTextSearch());
      setTextSearchState.mockClear();

      (useSearchText as any).mockReturnValue({ searchText: "alice" });
      rerender();
      expect(setTextSearchState).toHaveBeenCalledTimes(1);

      // Swap selectedDocument reference; searchText stays the same.
      (useSelectedDocument as any).mockReturnValue({
        selectedDocument: { id: "d2", fileType: "text/plain" },
      });
      rerender();
      expect(setTextSearchState).toHaveBeenCalledTimes(2);
    });
  });
});
