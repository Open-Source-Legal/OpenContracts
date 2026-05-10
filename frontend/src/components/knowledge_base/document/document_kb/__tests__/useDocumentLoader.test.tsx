/**
 * Unit tests for `useDocumentLoader` — the hook that owns every async fetch
 * and side-effect needed to populate the DocumentKnowledgeBase view.
 *
 * Covered behaviors:
 * - When `authReady` is false, no Apollo fetch fires and `viewState`
 *   stays at LOADING. (Auth-gated entry path.)
 * - When the document-only query resolves with a usable text document,
 *   `viewState` transitions to LOADED via the cached-text fetch helper.
 * - When the document-only query returns null `data.document`,
 *   `viewState` flips to ERROR and no body fetch is attempted.
 * - `threadCount` reflects the conversations query response.
 *
 * The PDF / DOCX branches are deliberately out of scope here — they pull
 * in pdfjs-dist and DOCX WASM, which would balloon the test for marginal
 * coverage. The TXT branch exercises the same loading-state state machine.
 */

import * as React from "react";
import type { ReactNode } from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";

import { renderHook } from "../../../../../test-utils/renderHook";
import { useDocumentLoader } from "../useDocumentLoader";
import { ViewState } from "../../../../types";
import {
  GET_CONVERSATIONS,
  GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
  GET_DOCUMENT_WITH_STRUCTURE,
  GET_DOCUMENT_ANNOTATIONS_ONLY,
} from "../../../../../graphql/queries";

// ---------- Module mocks ----------

vi.mock("react-toastify", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

const getDocumentRawTextMock = vi.fn();
const getCachedPDFUrlMock = vi.fn();
const getDocxBytesMock = vi.fn();
const getPawlsLayerMock = vi.fn();

vi.mock("../../../../annotator/api/cachedRest", () => ({
  getDocumentRawText: (...args: unknown[]) => getDocumentRawTextMock(...args),
  getCachedPDFUrl: (...args: unknown[]) => getCachedPDFUrlMock(...args),
  getDocxBytes: (...args: unknown[]) => getDocxBytesMock(...args),
  getPawlsLayer: (...args: unknown[]) => getPawlsLayerMock(...args),
}));

vi.mock("pdfjs-dist", () => ({
  // The text branch never reaches getDocument, so a stub that throws if
  // called is enough to surface accidental PDF-path coverage.
  getDocument: () => {
    throw new Error("getDocument should not be called in text-only tests");
  },
}));

// ---------- Wrapper ----------

interface WrapperOptions {
  mocks: MockedResponse[];
}

const buildWrapper = ({ mocks }: WrapperOptions) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter>
        <Provider>
          <MockedProvider mocks={mocks} addTypename={false}>
            <>{children}</>
          </MockedProvider>
        </Provider>
      </MemoryRouter>
    );
  };

// ---------- Fixtures ----------

const baseParams = {
  documentId: "doc-1",
  authReady: true,
  zoomLevel: 1,
  setProgress: vi.fn(),
  selectedAnalysisId: null,
  selectedExtractId: null,
};

const conversationsMock = (
  documentId: string,
  totalCount: number
): MockedResponse => ({
  request: {
    query: GET_CONVERSATIONS,
    variables: { documentId, conversationType: "THREAD", limit: 1 },
  },
  result: {
    data: {
      conversations: {
        edges: [],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        totalCount,
      },
    },
  },
});

const documentOnlyMock = (
  documentId: string,
  override?: { document?: unknown }
): MockedResponse => ({
  request: {
    query: GET_DOCUMENT_WITH_STRUCTURE,
    variables: { documentId },
  },
  result: {
    data:
      override && "document" in override
        ? { document: override.document }
        : {
            document: {
              id: documentId,
              title: "Doc",
              fileType: "application/txt",
              creator: { id: "u-1", email: "u@e.com" },
              created: "2026-05-09T00:00:00Z",
              pdfFile: null,
              pdfFileHash: null,
              txtExtractFile: "https://example.test/doc.txt",
              pawlsParseFile: null,
              myPermissions: ["CAN_READ"],
              allRelationships: [],
              allNotes: [],
              pathRecords: { edges: [] },
            },
          },
  },
});

// ---------- Tests ----------

describe("useDocumentLoader", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // `network-only` fetches log noisy "Type policy missing" warnings via
    // console.error — silence them so test output is readable.
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(console, "log").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("skips the Apollo queries while authReady is false", () => {
    const { result, unmount } = renderHook(
      () =>
        useDocumentLoader({
          ...baseParams,
          authReady: false,
          documentId: "doc-1",
        }),
      {
        wrapper: buildWrapper({
          mocks: [
            // No mocks needed — both queries should be skipped. Provide an
            // unrelated conversations mock so MockedProvider stays quiet.
            conversationsMock("doc-1", 0),
          ],
        }),
      }
    );

    expect(result.current.viewState).toBe(ViewState.LOADING);
    expect(result.current.loading).toBe(false);
    expect(result.current.combinedData).toBeUndefined();
    expect(getDocumentRawTextMock).not.toHaveBeenCalled();

    unmount();
  });

  it("transitions viewState to LOADED for a text document via document-only path", async () => {
    getDocumentRawTextMock.mockResolvedValue("hello text body");

    const { result, waitFor, unmount } = renderHook(
      () => useDocumentLoader({ ...baseParams, corpusId: undefined }),
      {
        wrapper: buildWrapper({
          mocks: [documentOnlyMock("doc-1"), conversationsMock("doc-1", 0)],
        }),
      }
    );

    expect(result.current.viewState).toBe(ViewState.LOADING);

    await waitFor(() => result.current.viewState === ViewState.LOADED, {
      timeout: 3000,
    });

    expect(getDocumentRawTextMock).toHaveBeenCalledWith(
      "https://example.test/doc.txt"
    );
    expect(getCachedPDFUrlMock).not.toHaveBeenCalled();

    unmount();
  });

  it("flips viewState to ERROR when the query returns a null document", async () => {
    const { result, waitFor, unmount } = renderHook(
      () => useDocumentLoader({ ...baseParams, corpusId: undefined }),
      {
        wrapper: buildWrapper({
          mocks: [
            documentOnlyMock("doc-1", { document: null }),
            conversationsMock("doc-1", 0),
          ],
        }),
      }
    );

    await waitFor(() => result.current.viewState === ViewState.ERROR, {
      timeout: 3000,
    });

    expect(getDocumentRawTextMock).not.toHaveBeenCalled();

    unmount();
  });

  it("exposes threadCount from the conversations query result", async () => {
    getDocumentRawTextMock.mockResolvedValue("body");

    const { result, waitFor, unmount } = renderHook(
      () => useDocumentLoader({ ...baseParams, corpusId: undefined }),
      {
        wrapper: buildWrapper({
          mocks: [documentOnlyMock("doc-1"), conversationsMock("doc-1", 7)],
        }),
      }
    );

    await waitFor(() => result.current.threadCount === 7, { timeout: 3000 });

    expect(result.current.threadCount).toBe(7);

    unmount();
  });

  it("skips the corpus-context query when no corpusId is supplied", async () => {
    const corpusQuerySpy = vi.fn();
    const corpusContextMock: MockedResponse = {
      request: {
        query: GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
        variables: {
          documentId: "doc-1",
          corpusId: "corpus-1",
          analysisId: undefined,
        },
      },
      // Tracking newData so we can assert it was never called.
      newData: () => {
        corpusQuerySpy();
        return { data: { document: null, corpus: null } };
      },
    };

    getDocumentRawTextMock.mockResolvedValue("body");

    const { unmount, waitFor, result } = renderHook(
      () => useDocumentLoader({ ...baseParams, corpusId: undefined }),
      {
        wrapper: buildWrapper({
          mocks: [
            corpusContextMock,
            documentOnlyMock("doc-1"),
            conversationsMock("doc-1", 0),
          ],
        }),
      }
    );

    await waitFor(() => result.current.viewState === ViewState.LOADED, {
      timeout: 3000,
    });

    expect(corpusQuerySpy).not.toHaveBeenCalled();

    unmount();
  });

  it("does not refetch annotations-only when no corpusId is bound", async () => {
    const annotationsOnlySpy = vi.fn();
    const annotationsOnlyMock: MockedResponse = {
      request: {
        query: GET_DOCUMENT_ANNOTATIONS_ONLY,
        variables: { documentId: "doc-1", corpusId: "", analysisId: null },
      },
      newData: () => {
        annotationsOnlySpy();
        return {
          data: {
            document: { id: "doc-1", allAnnotations: [], allRelationships: [] },
          },
        };
      },
    };

    getDocumentRawTextMock.mockResolvedValue("body");

    const { unmount, waitFor, result } = renderHook(
      () => useDocumentLoader({ ...baseParams, corpusId: undefined }),
      {
        wrapper: buildWrapper({
          mocks: [
            documentOnlyMock("doc-1"),
            annotationsOnlyMock,
            conversationsMock("doc-1", 0),
          ],
        }),
      }
    );

    await waitFor(() => result.current.viewState === ViewState.LOADED, {
      timeout: 3000,
    });

    expect(annotationsOnlySpy).not.toHaveBeenCalled();

    unmount();
  });

  it("does not toast or transition viewState when the TXT body load resolves after unmount", async () => {
    // Hold the text fetch open so we can unmount before it resolves and
    // assert that the cancellation guard prevents a setState-after-unmount.
    let resolveText!: (txt: string) => void;
    const pendingText = new Promise<string>((resolve) => {
      resolveText = resolve;
    });
    getDocumentRawTextMock.mockReturnValue(pendingText);

    const { toast } = await import("react-toastify");

    const { result, unmount } = renderHook(
      () => useDocumentLoader({ ...baseParams, corpusId: undefined }),
      {
        wrapper: buildWrapper({
          mocks: [documentOnlyMock("doc-1"), conversationsMock("doc-1", 0)],
        }),
      }
    );

    // Wait one tick so the document-only query resolves and the TXT body
    // fetch has actually been kicked off (mock function called).
    await new Promise((r) => setTimeout(r, 0));
    expect(getDocumentRawTextMock).toHaveBeenCalled();

    // Unmount BEFORE the body promise settles. The body load's
    // ``cancelled`` flag (added by the unmount-cancellation fix) should
    // suppress both the LOADED setViewState and any error toast when the
    // late resolution lands.
    unmount();
    resolveText("late body");
    await new Promise((r) => setTimeout(r, 10));

    // ``result.current`` is the final live snapshot from before unmount,
    // so it must NOT have advanced to LOADED — proving setViewState was
    // never called for this stale resolution.
    expect(result.current.viewState).toBe(ViewState.LOADING);
    expect(toast.error).not.toHaveBeenCalled();
  });
});
