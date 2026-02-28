import { describe, it, expect, vi } from "vitest";
import {
  buildQueryParams,
  getCorpusUrl,
  getDocumentUrl,
  navigateToCorpus,
  navigateToDocument,
  isCanonicalPath,
  parseRoute,
  parseQueryParam,
  buildCanonicalPath,
  QueryParams,
  updateTabParam,
  updateThreadParam,
  updateMessageParam,
  navigateToThreadWithMessage,
  clearThreadSelection,
} from "../navigationUtils";
import { CorpusType, DocumentType } from "../../types/graphql-api";

describe("buildQueryParams()", () => {
  it("should build query string with single annotation", () => {
    const params: QueryParams = { annotationIds: ["123"] };
    expect(buildQueryParams(params)).toBe("?ann=123");
  });

  it("should build query string with multiple annotations", () => {
    const params: QueryParams = { annotationIds: ["123", "456", "789"] };
    // URLSearchParams encodes commas as %2C
    expect(buildQueryParams(params)).toBe("?ann=123%2C456%2C789");
  });

  it("should build query string with single analysis", () => {
    const params: QueryParams = { analysisIds: ["123"] };
    expect(buildQueryParams(params)).toBe("?analysis=123");
  });

  it("should build query string with multiple analyses", () => {
    const params: QueryParams = { analysisIds: ["123", "456"] };
    expect(buildQueryParams(params)).toBe("?analysis=123%2C456");
  });

  it("should build query string with single extract", () => {
    const params: QueryParams = { extractIds: ["456"] };
    expect(buildQueryParams(params)).toBe("?extract=456");
  });

  it("should build query string with multiple extracts", () => {
    const params: QueryParams = { extractIds: ["456", "789"] };
    expect(buildQueryParams(params)).toBe("?extract=456%2C789");
  });

  it("should combine all parameter types", () => {
    const params: QueryParams = {
      annotationIds: ["1", "2"],
      analysisIds: ["3"],
      extractIds: ["4", "5"],
    };
    const result = buildQueryParams(params);
    expect(result).toContain("ann=1%2C2");
    expect(result).toContain("analysis=3");
    expect(result).toContain("extract=4%2C5");
  });

  it("should return empty string for empty params", () => {
    expect(buildQueryParams({})).toBe("");
  });

  it("should return empty string for empty arrays", () => {
    const params: QueryParams = {
      annotationIds: [],
      analysisIds: [],
      extractIds: [],
    };
    expect(buildQueryParams(params)).toBe("");
  });

  it("should ignore undefined params", () => {
    const params: QueryParams = {
      annotationIds: ["123"],
      analysisIds: undefined,
      extractIds: ["456"],
    };
    const result = buildQueryParams(params);
    expect(result).toContain("ann=123");
    expect(result).toContain("extract=456");
    expect(result).not.toContain("analysis");
  });

  it("should include textBlock when set to a string", () => {
    const params: QueryParams = { textBlock: "s100-200" };
    expect(buildQueryParams(params)).toBe("?tb=s100-200");
  });

  it("should not include tb param when textBlock is null", () => {
    const params: QueryParams = { textBlock: null };
    expect(buildQueryParams(params)).toBe("");
  });

  it("should not include tb param when textBlock is undefined", () => {
    const params: QueryParams = { textBlock: undefined };
    expect(buildQueryParams(params)).toBe("");
  });

  it("should combine textBlock with other params", () => {
    const params: QueryParams = {
      annotationIds: ["123"],
      textBlock: "p0:45-65",
    };
    const result = buildQueryParams(params);
    expect(result).toContain("ann=123");
    expect(result).toContain("tb=p0%3A45-65");
  });
});

describe("getCorpusUrl()", () => {
  const mockCorpus = {
    id: "corpus-1",
    slug: "my-corpus",
    creator: { id: "user-1", slug: "john" },
  } as CorpusType;

  describe("without query params", () => {
    it("should generate correct corpus URL", () => {
      expect(getCorpusUrl(mockCorpus)).toBe("/c/john/my-corpus");
    });

    it("should return # when corpus slug is missing", () => {
      const invalidCorpus = { ...mockCorpus, slug: "" };
      expect(getCorpusUrl(invalidCorpus as CorpusType)).toBe("#");
    });

    it("should return # when creator slug is missing", () => {
      const invalidCorpus = {
        ...mockCorpus,
        creator: { id: "user-1", slug: "" },
      };
      expect(getCorpusUrl(invalidCorpus as CorpusType)).toBe("#");
    });

    it("should return # when creator is null", () => {
      const invalidCorpus = { ...mockCorpus, creator: null };
      expect(getCorpusUrl(invalidCorpus as unknown as CorpusType)).toBe("#");
    });
  });

  describe("with query params", () => {
    it("should append single analysis param", () => {
      const url = getCorpusUrl(mockCorpus, { analysisIds: ["123"] });
      expect(url).toBe("/c/john/my-corpus?analysis=123");
    });

    it("should append single extract param", () => {
      const url = getCorpusUrl(mockCorpus, { extractIds: ["456"] });
      expect(url).toBe("/c/john/my-corpus?extract=456");
    });

    it("should append multiple params", () => {
      const url = getCorpusUrl(mockCorpus, {
        analysisIds: ["123"],
        extractIds: ["456", "789"],
      });
      expect(url).toContain("/c/john/my-corpus?");
      expect(url).toContain("analysis=123");
      expect(url).toContain("extract=456%2C789");
    });

    it("should return # even with params when slugs missing", () => {
      const invalidCorpus = { ...mockCorpus, slug: "" };
      const url = getCorpusUrl(invalidCorpus as CorpusType, {
        analysisIds: ["123"],
      });
      expect(url).toBe("#");
    });
  });
});

describe("getDocumentUrl()", () => {
  const mockDocument = {
    id: "doc-1",
    slug: "my-document",
    creator: { id: "user-1", slug: "john" },
  } as DocumentType;

  const mockCorpus = {
    id: "corpus-1",
    slug: "my-corpus",
    creator: { id: "user-1", slug: "john" },
  } as CorpusType;

  describe("without corpus context", () => {
    it("should generate standalone document URL", () => {
      expect(getDocumentUrl(mockDocument)).toBe("/d/john/my-document");
    });

    it("should return # when document slug is missing", () => {
      const invalidDoc = { ...mockDocument, slug: "" };
      expect(getDocumentUrl(invalidDoc as DocumentType)).toBe("#");
    });

    it("should return # when creator slug is missing", () => {
      const invalidDoc = {
        ...mockDocument,
        creator: { id: "user-1", slug: "" },
      };
      expect(getDocumentUrl(invalidDoc as DocumentType)).toBe("#");
    });
  });

  describe("with corpus context", () => {
    it("should generate document in corpus URL", () => {
      expect(getDocumentUrl(mockDocument, mockCorpus)).toBe(
        "/d/john/my-corpus/my-document"
      );
    });

    it("should fallback to standalone when corpus slug missing", () => {
      const invalidCorpus = { ...mockCorpus, slug: "" };
      expect(getDocumentUrl(mockDocument, invalidCorpus as CorpusType)).toBe(
        "/d/john/my-document"
      );
    });
  });

  describe("with query params", () => {
    it("should append annotation params to standalone document", () => {
      const url = getDocumentUrl(mockDocument, null, {
        annotationIds: ["123"],
      });
      expect(url).toBe("/d/john/my-document?ann=123");
    });

    it("should append multiple param types to document in corpus", () => {
      const url = getDocumentUrl(mockDocument, mockCorpus, {
        annotationIds: ["1", "2"],
        analysisIds: ["3"],
        extractIds: ["4"],
      });
      expect(url).toContain("/d/john/my-corpus/my-document?");
      expect(url).toContain("ann=1%2C2");
      expect(url).toContain("analysis=3");
      expect(url).toContain("extract=4");
    });

    it("should return # with params when slugs missing", () => {
      const invalidDoc = { ...mockDocument, slug: "" };
      const url = getDocumentUrl(invalidDoc as DocumentType, null, {
        annotationIds: ["123"],
      });
      expect(url).toBe("#");
    });
  });
});

describe("isCanonicalPath()", () => {
  it("should return true for exact matches", () => {
    expect(isCanonicalPath("/c/john/corpus", "/c/john/corpus")).toBe(true);
  });

  it("should ignore trailing slashes", () => {
    expect(isCanonicalPath("/c/john/corpus/", "/c/john/corpus")).toBe(true);
    expect(isCanonicalPath("/c/john/corpus", "/c/john/corpus/")).toBe(true);
  });

  it("should ignore query parameters", () => {
    expect(
      isCanonicalPath("/c/john/corpus?analysis=123", "/c/john/corpus")
    ).toBe(true);
  });

  it("should be case-insensitive", () => {
    expect(isCanonicalPath("/c/John/Corpus", "/c/john/corpus")).toBe(true);
  });

  it("should return false for different paths", () => {
    expect(isCanonicalPath("/c/john/corpus1", "/c/john/corpus2")).toBe(false);
  });
});

describe("navigateToCorpus()", () => {
  const mockCorpus = {
    id: "corpus-1",
    slug: "my-corpus",
    creator: { id: "user-1", slug: "john" },
  } as CorpusType;

  it("should call navigate with correct URL", () => {
    const mockNavigate = vi.fn();
    navigateToCorpus(mockCorpus, mockNavigate);
    expect(mockNavigate).toHaveBeenCalledWith("/c/john/my-corpus");
  });

  it("should append query params when provided", () => {
    const mockNavigate = vi.fn();
    navigateToCorpus(mockCorpus, mockNavigate, undefined, {
      analysisIds: ["123"],
      extractIds: ["456"],
    });
    const calledUrl = mockNavigate.mock.calls[0][0];
    expect(calledUrl).toContain("/c/john/my-corpus?");
    expect(calledUrl).toContain("analysis=123");
    expect(calledUrl).toContain("extract=456");
  });

  it("should not navigate when already at destination", () => {
    const mockNavigate = vi.fn();
    const currentPath = "/c/john/my-corpus";
    navigateToCorpus(mockCorpus, mockNavigate, currentPath);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("should not navigate when corpus has no slug", () => {
    const mockNavigate = vi.fn();
    const invalidCorpus = { ...mockCorpus, slug: "" };
    navigateToCorpus(invalidCorpus as CorpusType, mockNavigate);
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

describe("navigateToDocument()", () => {
  const mockDocument = {
    id: "doc-1",
    slug: "my-document",
    creator: { id: "user-1", slug: "john" },
  } as DocumentType;

  const mockCorpus = {
    id: "corpus-1",
    slug: "my-corpus",
    creator: { id: "user-1", slug: "john" },
  } as CorpusType;

  it("should navigate to standalone document", () => {
    const mockNavigate = vi.fn();
    navigateToDocument(mockDocument, null, mockNavigate);
    expect(mockNavigate).toHaveBeenCalledWith("/d/john/my-document");
  });

  it("should navigate to document in corpus", () => {
    const mockNavigate = vi.fn();
    navigateToDocument(mockDocument, mockCorpus, mockNavigate);
    expect(mockNavigate).toHaveBeenCalledWith("/d/john/my-corpus/my-document");
  });

  it("should append query params", () => {
    const mockNavigate = vi.fn();
    navigateToDocument(mockDocument, mockCorpus, mockNavigate, undefined, {
      annotationIds: ["1", "2"],
      analysisIds: ["3"],
      extractIds: ["4"],
    });
    const calledUrl = mockNavigate.mock.calls[0][0];
    expect(calledUrl).toContain("/d/john/my-corpus/my-document?");
    expect(calledUrl).toContain("ann=1%2C2");
    expect(calledUrl).toContain("analysis=3");
    expect(calledUrl).toContain("extract=4");
  });

  it("should not navigate when already at destination", () => {
    const mockNavigate = vi.fn();
    const currentPath = "/d/john/my-document";
    navigateToDocument(mockDocument, null, mockNavigate, currentPath);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("should not navigate when document has no slug", () => {
    const mockNavigate = vi.fn();
    const invalidDoc = { ...mockDocument, slug: "" };
    navigateToDocument(invalidDoc as DocumentType, null, mockNavigate);
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

describe("Real-world URL scenarios", () => {
  const corpus = {
    id: "1",
    slug: "legal-corpus",
    creator: { id: "1", slug: "john-lawyer" },
  } as CorpusType;

  const document = {
    id: "2",
    slug: "contract-2024",
    creator: { id: "1", slug: "john-lawyer" },
  } as DocumentType;

  it("should handle corpus with analysis and extract", () => {
    const url = getCorpusUrl(corpus, {
      analysisIds: ["5678"],
      extractIds: ["9012"],
    });
    expect(url).toBe("/c/john-lawyer/legal-corpus?analysis=5678&extract=9012");
  });

  it("should handle document with all params", () => {
    const url = getDocumentUrl(document, corpus, {
      annotationIds: ["1234", "5678"],
      analysisIds: ["9012"],
      extractIds: ["3456"],
    });
    expect(url).toContain("/d/john-lawyer/legal-corpus/contract-2024?");
    expect(url).toContain("ann=1234%2C5678");
    expect(url).toContain("analysis=9012");
    expect(url).toContain("extract=3456");
  });

  it("should handle standalone document with analysis", () => {
    const url = getDocumentUrl(document, null, {
      analysisIds: ["7890"],
    });
    expect(url).toBe("/d/john-lawyer/contract-2024?analysis=7890");
  });

  it("should preserve params during navigation", () => {
    const mockNavigate = vi.fn();
    navigateToDocument(document, corpus, mockNavigate, undefined, {
      annotationIds: ["123"],
      analysisIds: ["456"],
      extractIds: ["789"],
    });

    const navigatedUrl = mockNavigate.mock.calls[0][0];
    // Single IDs don't get encoded
    expect(navigatedUrl).toContain("ann=123");
    expect(navigatedUrl).toContain("analysis=456");
    expect(navigatedUrl).toContain("extract=789");
  });
});

describe("parseRoute()", () => {
  describe("corpus routes", () => {
    it("should parse corpus route", () => {
      const result = parseRoute("/c/john/my-corpus");
      expect(result).toEqual({
        type: "corpus",
        userIdent: "john",
        corpusIdent: "my-corpus",
      });
    });

    it("should handle corpus route with trailing slash", () => {
      const result = parseRoute("/c/john/my-corpus/");
      expect(result).toEqual({
        type: "corpus",
        userIdent: "john",
        corpusIdent: "my-corpus",
      });
    });
  });

  describe("document routes", () => {
    it("should parse standalone document route", () => {
      const result = parseRoute("/d/john/my-document");
      expect(result).toEqual({
        type: "document",
        userIdent: "john",
        documentIdent: "my-document",
      });
    });

    it("should parse document in corpus route", () => {
      const result = parseRoute("/d/john/my-corpus/my-document");
      expect(result).toEqual({
        type: "document",
        userIdent: "john",
        corpusIdent: "my-corpus",
        documentIdent: "my-document",
      });
    });

    it("should handle document route with trailing slash", () => {
      const result = parseRoute("/d/john/my-corpus/my-document/");
      expect(result).toEqual({
        type: "document",
        userIdent: "john",
        corpusIdent: "my-corpus",
        documentIdent: "my-document",
      });
    });
  });

  describe("browse routes", () => {
    it("should parse annotations route", () => {
      const result = parseRoute("/annotations");
      expect(result).toEqual({
        type: "browse",
        browsePath: "annotations",
      });
    });

    it("should parse extracts route", () => {
      const result = parseRoute("/extracts");
      expect(result).toEqual({
        type: "browse",
        browsePath: "extracts",
      });
    });

    it("should parse corpuses route", () => {
      const result = parseRoute("/corpuses");
      expect(result).toEqual({
        type: "browse",
        browsePath: "corpuses",
      });
    });

    it("should parse documents route", () => {
      const result = parseRoute("/documents");
      expect(result).toEqual({
        type: "browse",
        browsePath: "documents",
      });
    });

    it("should parse label_sets route", () => {
      const result = parseRoute("/label_sets");
      expect(result).toEqual({
        type: "browse",
        browsePath: "label_sets",
      });
    });

    it("should parse discussions route", () => {
      const result = parseRoute("/discussions");
      expect(result).toEqual({
        type: "browse",
        browsePath: "discussions",
      });
    });
  });

  describe("invalid routes", () => {
    it("should return unknown for invalid pattern", () => {
      const result = parseRoute("/invalid/route");
      expect(result).toEqual({ type: "unknown" });
    });

    it("should return unknown for empty path", () => {
      const result = parseRoute("");
      expect(result).toEqual({ type: "unknown" });
    });

    it("should return unknown for root path", () => {
      const result = parseRoute("/");
      expect(result).toEqual({ type: "unknown" });
    });

    it("should return unknown for incomplete corpus route", () => {
      const result = parseRoute("/c/john");
      expect(result).toEqual({ type: "unknown" });
    });

    it("should return unknown for incomplete document route", () => {
      const result = parseRoute("/d/john");
      expect(result).toEqual({ type: "unknown" });
    });
  });
});

describe("parseQueryParam()", () => {
  it("should parse single value", () => {
    expect(parseQueryParam("123")).toEqual(["123"]);
  });

  it("should parse comma-separated values", () => {
    expect(parseQueryParam("123,456,789")).toEqual(["123", "456", "789"]);
  });

  it("should filter empty values", () => {
    expect(parseQueryParam("123,,456,,")).toEqual(["123", "456"]);
  });

  it("should return empty array for null", () => {
    expect(parseQueryParam(null)).toEqual([]);
  });

  it("should return empty array for empty string", () => {
    expect(parseQueryParam("")).toEqual([]);
  });

  it("should handle values with special characters", () => {
    expect(parseQueryParam("abc-123,def_456")).toEqual(["abc-123", "def_456"]);
  });
});

describe("buildCanonicalPath()", () => {
  const mockDocument = {
    id: "doc-1",
    slug: "my-document",
    creator: { id: "user-1", slug: "john" },
  } as DocumentType;

  const mockCorpus = {
    id: "corpus-1",
    slug: "my-corpus",
    creator: { id: "user-1", slug: "john" },
  } as CorpusType;

  it("should build document in corpus path", () => {
    const path = buildCanonicalPath(mockDocument, mockCorpus);
    expect(path).toBe("/d/john/my-corpus/my-document");
  });

  it("should build standalone document path", () => {
    const path = buildCanonicalPath(mockDocument, null);
    expect(path).toBe("/d/john/my-document");
  });

  it("should build standalone document path when corpus missing slug", () => {
    const invalidCorpus = { ...mockCorpus, slug: "" };
    const path = buildCanonicalPath(mockDocument, invalidCorpus as CorpusType);
    expect(path).toBe("/d/john/my-document");
  });

  it("should build corpus-only path", () => {
    const path = buildCanonicalPath(null, mockCorpus);
    expect(path).toBe("/c/john/my-corpus");
  });

  it("should fallback to corpus path when document missing slug", () => {
    const invalidDoc = { ...mockDocument, slug: "" };
    const path = buildCanonicalPath(invalidDoc as DocumentType, mockCorpus);
    expect(path).toBe("/c/john/my-corpus"); // Falls back to corpus if document invalid
  });

  it("should return empty string when document missing creator slug", () => {
    const invalidDoc = {
      ...mockDocument,
      creator: { id: "user-1", slug: "" },
    };
    const path = buildCanonicalPath(invalidDoc as DocumentType, null);
    expect(path).toBe("");
  });

  it("should return empty string when corpus missing slug", () => {
    const invalidCorpus = { ...mockCorpus, slug: "" };
    const path = buildCanonicalPath(null, invalidCorpus as CorpusType);
    expect(path).toBe("");
  });

  it("should return empty string when corpus missing creator slug", () => {
    const invalidCorpus = {
      ...mockCorpus,
      creator: { id: "user-1", slug: "" },
    };
    const path = buildCanonicalPath(null, invalidCorpus as CorpusType);
    expect(path).toBe("");
  });

  it("should return empty string when both entities null", () => {
    const path = buildCanonicalPath(null, null);
    expect(path).toBe("");
  });
});

describe("buildQueryParams() with tab and message", () => {
  it("should include tab parameter", () => {
    const params: QueryParams = { tab: "discussions" };
    expect(buildQueryParams(params)).toBe("?tab=discussions");
  });

  it("should include message parameter", () => {
    const params: QueryParams = { messageId: "msg-123" };
    expect(buildQueryParams(params)).toBe("?message=msg-123");
  });

  it("should include both tab and message parameters", () => {
    const params: QueryParams = { tab: "discussions", messageId: "msg-456" };
    const result = buildQueryParams(params);
    expect(result).toContain("tab=discussions");
    expect(result).toContain("message=msg-456");
  });

  it("should combine tab with existing params", () => {
    const params: QueryParams = {
      annotationIds: ["123"],
      tab: "documents",
    };
    const result = buildQueryParams(params);
    expect(result).toContain("ann=123");
    expect(result).toContain("tab=documents");
  });

  it("should combine message with thread param", () => {
    const params: QueryParams = {
      threadId: "thread-1",
      messageId: "msg-789",
    };
    const result = buildQueryParams(params);
    expect(result).toContain("thread=thread-1");
    expect(result).toContain("message=msg-789");
  });

  it("should not include tab when null", () => {
    const params: QueryParams = { tab: null, annotationIds: ["123"] };
    const result = buildQueryParams(params);
    expect(result).toBe("?ann=123");
    expect(result).not.toContain("tab");
  });

  it("should not include message when null", () => {
    const params: QueryParams = { messageId: null, threadId: "thread-1" };
    const result = buildQueryParams(params);
    expect(result).toBe("?thread=thread-1");
    expect(result).not.toContain("message");
  });
});

describe("updateTabParam()", () => {
  it("should set tab parameter and replace (not push) history", () => {
    const mockNavigate = vi.fn();
    const location = { search: "" };

    updateTabParam(location, mockNavigate, "discussions");

    // Should replace so tab switches don't accumulate history entries
    expect(mockNavigate).toHaveBeenCalledWith(
      { search: "tab=discussions" },
      { replace: true }
    );
  });

  it("should preserve non-tab-specific parameters when adding tab", () => {
    const mockNavigate = vi.fn();
    const location = { search: "ann=123&analysis=456" };

    updateTabParam(location, mockNavigate, "documents");

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("ann=123");
    expect(calledWith).toContain("analysis=456");
    expect(calledWith).toContain("tab=documents");
  });

  it("should remove tab parameter when null", () => {
    const mockNavigate = vi.fn();
    const location = { search: "tab=discussions&ann=123" };

    updateTabParam(location, mockNavigate, null);

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("ann=123");
    expect(calledWith).not.toContain("tab");
  });

  it("should update existing tab parameter", () => {
    const mockNavigate = vi.fn();
    const location = { search: "tab=discussions" };

    updateTabParam(location, mockNavigate, "documents");

    expect(mockNavigate).toHaveBeenCalledWith(
      { search: "tab=documents" },
      { replace: true }
    );
  });

  it("should clear thread param when switching tabs", () => {
    const mockNavigate = vi.fn();
    const location = { search: "tab=discussions&thread=thread-123" };

    updateTabParam(location, mockNavigate, "documents");

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("tab=documents");
    expect(calledWith).not.toContain("thread");
  });

  it("should clear message param when switching tabs", () => {
    const mockNavigate = vi.fn();
    const location = {
      search: "tab=discussions&thread=t-1&message=msg-1",
    };

    updateTabParam(location, mockNavigate, "documents");

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("tab=documents");
    expect(calledWith).not.toContain("thread");
    expect(calledWith).not.toContain("message");
  });

  it("should clear thread and message even when going to home (null)", () => {
    const mockNavigate = vi.fn();
    const location = {
      search: "tab=discussions&thread=t-1&message=msg-1&ann=123",
    };

    updateTabParam(location, mockNavigate, null);

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("ann=123");
    expect(calledWith).not.toContain("tab");
    expect(calledWith).not.toContain("thread");
    expect(calledWith).not.toContain("message");
  });
});

describe("updateThreadParam()", () => {
  it("should set thread parameter when threadId provided", () => {
    const mockNavigate = vi.fn();
    const location = { search: "tab=discussions" };

    updateThreadParam(location, mockNavigate, "thread-123");

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("tab=discussions");
    expect(calledWith).toContain("thread=thread-123");
  });

  it("should push history entry (not replace)", () => {
    const mockNavigate = vi.fn();
    const location = { search: "" };

    updateThreadParam(location, mockNavigate, "thread-1");

    // Should push, not replace
    expect(mockNavigate).toHaveBeenCalledWith({ search: "thread=thread-1" });
    expect(mockNavigate.mock.calls[0]).toHaveLength(1);
  });

  it("should clear thread and message params when threadId is null", () => {
    const mockNavigate = vi.fn();
    const location = {
      search: "tab=discussions&thread=thread-1&message=msg-1",
    };

    updateThreadParam(location, mockNavigate, null);

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("tab=discussions");
    expect(calledWith).not.toContain("thread");
    expect(calledWith).not.toContain("message");
  });

  it("should preserve unrelated params", () => {
    const mockNavigate = vi.fn();
    const location = { search: "tab=discussions&ann=123&analysis=456" };

    updateThreadParam(location, mockNavigate, "thread-789");

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("tab=discussions");
    expect(calledWith).toContain("ann=123");
    expect(calledWith).toContain("analysis=456");
    expect(calledWith).toContain("thread=thread-789");
  });

  it("should update existing thread parameter", () => {
    const mockNavigate = vi.fn();
    const location = { search: "thread=old-thread" };

    updateThreadParam(location, mockNavigate, "new-thread");

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("thread=new-thread");
    expect(calledWith).not.toContain("old-thread");
  });
});

describe("updateMessageParam()", () => {
  it("should set message parameter", () => {
    const mockNavigate = vi.fn();
    const location = { search: "" };

    updateMessageParam(location, mockNavigate, "msg-123");

    expect(mockNavigate).toHaveBeenCalledWith(
      { search: "message=msg-123" },
      { replace: true }
    );
  });

  it("should preserve existing parameters when adding message", () => {
    const mockNavigate = vi.fn();
    const location = { search: "thread=thread-1&ann=456" };

    updateMessageParam(location, mockNavigate, "msg-789");

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("thread=thread-1");
    expect(calledWith).toContain("ann=456");
    expect(calledWith).toContain("message=msg-789");
  });

  it("should remove message parameter when null", () => {
    const mockNavigate = vi.fn();
    const location = { search: "message=msg-123&thread=thread-1" };

    updateMessageParam(location, mockNavigate, null);

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("thread=thread-1");
    expect(calledWith).not.toContain("message");
  });
});

describe("navigateToThreadWithMessage()", () => {
  it("should set thread parameter", () => {
    const mockNavigate = vi.fn();
    const location = { search: "" };

    navigateToThreadWithMessage(location, mockNavigate, "thread-123");

    expect(mockNavigate).toHaveBeenCalledWith(
      { search: "thread=thread-123" },
      { replace: true }
    );
  });

  it("should set both thread and message parameters", () => {
    const mockNavigate = vi.fn();
    const location = { search: "" };

    navigateToThreadWithMessage(
      location,
      mockNavigate,
      "thread-123",
      "msg-456"
    );

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("thread=thread-123");
    expect(calledWith).toContain("message=msg-456");
  });

  it("should preserve existing parameters", () => {
    const mockNavigate = vi.fn();
    const location = { search: "ann=123&tab=discussions" };

    navigateToThreadWithMessage(
      location,
      mockNavigate,
      "thread-789",
      "msg-abc"
    );

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("ann=123");
    expect(calledWith).toContain("tab=discussions");
    expect(calledWith).toContain("thread=thread-789");
    expect(calledWith).toContain("message=msg-abc");
  });

  it("should not include message when not provided", () => {
    const mockNavigate = vi.fn();
    const location = { search: "tab=discussions" };

    navigateToThreadWithMessage(location, mockNavigate, "thread-456");

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).toContain("thread=thread-456");
    expect(calledWith).not.toContain("message");
  });
});

describe("clearThreadSelection()", () => {
  it("should remove thread parameter", () => {
    const mockNavigate = vi.fn();
    const location = { search: "thread=thread-123&ann=456" };

    clearThreadSelection(location, mockNavigate);

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).not.toContain("thread");
    expect(calledWith).toContain("ann=456");
  });

  it("should remove both thread and message parameters", () => {
    const mockNavigate = vi.fn();
    const location = { search: "thread=thread-123&message=msg-456&ann=789" };

    clearThreadSelection(location, mockNavigate);

    const calledWith = mockNavigate.mock.calls[0][0].search;
    expect(calledWith).not.toContain("thread");
    expect(calledWith).not.toContain("message");
    expect(calledWith).toContain("ann=789");
  });

  it("should handle empty search gracefully", () => {
    const mockNavigate = vi.fn();
    const location = { search: "" };

    clearThreadSelection(location, mockNavigate);

    expect(mockNavigate).toHaveBeenCalledWith(
      { search: "" },
      { replace: true }
    );
  });
});
