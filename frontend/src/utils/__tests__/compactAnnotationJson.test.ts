import { describe, it, expect } from "vitest";
import {
  encodeTokenRanges,
  decodeTokenRanges,
  isCompactFormat,
  isSpanFormat,
  compactAnnotationJson,
  expandAnnotationJson,
  iterPageAnnotations,
  hasAnyTokens,
} from "../compactAnnotationJson";

describe("compactAnnotationJson", () => {
  describe("encodeTokenRanges / decodeTokenRanges", () => {
    it("round-trips a mixture of singletons and ranges", () => {
      const tokens = [1, 2, 3, 5, 7, 8, 9];
      const encoded = encodeTokenRanges(tokens);
      expect(encoded).toBe("1-3,5,7-9");
      expect(decodeTokenRanges(encoded)).toEqual(tokens);
    });

    it("dedupes, sorts, and drops negatives", () => {
      expect(encodeTokenRanges([3, 1, 2, 2, -1])).toBe("1-3");
    });

    it("returns empty strings/arrays for empty inputs", () => {
      expect(encodeTokenRanges([])).toBe("");
      expect(decodeTokenRanges("")).toEqual([]);
    });

    it("handles single-token ranges", () => {
      expect(encodeTokenRanges([5])).toBe("5");
      expect(decodeTokenRanges("5")).toEqual([5]);
    });

    it("skips malformed range segments", () => {
      // "abc" → NaN parts → skipped; "3" survives.
      expect(decodeTokenRanges("abc,3,foo-bar")).toEqual([3]);
    });
  });

  describe("isCompactFormat", () => {
    it("detects v2 objects", () => {
      expect(isCompactFormat({ v: 2, p: {} })).toBe(true);
    });

    it("rejects v1 and malformed shapes", () => {
      expect(isCompactFormat({})).toBe(false);
      expect(isCompactFormat({ v: 2 } as any)).toBe(false);
      expect(isCompactFormat({ v: 1, p: {} } as any)).toBe(false);
    });
  });

  describe("isSpanFormat", () => {
    it("detects numeric start/end pairs", () => {
      expect(isSpanFormat({ start: 0, end: 5 })).toBe(true);
    });

    it("tolerates extra fields", () => {
      expect(isSpanFormat({ start: 0, end: 5, confidence: 0.9 } as any)).toBe(
        true
      );
    });

    it("rejects missing or non-numeric fields", () => {
      expect(isSpanFormat({} as any)).toBe(false);
      expect(isSpanFormat({ start: "0", end: "5" } as any)).toBe(false);
    });
  });

  describe("compactAnnotationJson / expandAnnotationJson", () => {
    const v1 = {
      "0": {
        bounds: { top: 1, left: 2, right: 3, bottom: 4 },
        tokensJsons: [
          { pageIndex: 0, tokenIndex: 5 },
          { pageIndex: 0, tokenIndex: 6 },
        ],
        rawText: "hello",
      },
    };

    it("compacts a v1 doc and expand round-trips", () => {
      const compact = compactAnnotationJson(v1 as any);
      expect(compact.v).toBe(2);
      expect(compact.p["0"].b).toEqual([1, 2, 3, 4]);
      expect(compact.p["0"].t).toBe("5-6");

      const v1Again = expandAnnotationJson(compact, "hello") as any;
      expect(v1Again["0"].bounds).toEqual(v1["0"].bounds);
      expect(v1Again["0"].tokensJsons).toEqual(v1["0"].tokensJsons);
      expect(v1Again["0"].rawText).toBe("hello");
    });

    it("passes span annotations through unchanged", () => {
      const span = { start: 0, end: 10 };
      expect(expandAnnotationJson(span as any)).toBe(span);
    });

    it("returns v1 input unchanged", () => {
      expect(expandAnnotationJson(v1 as any)).toBe(v1);
    });

    it("passes null/undefined through", () => {
      expect(expandAnnotationJson(null)).toBeNull();
      expect(expandAnnotationJson(undefined)).toBeUndefined();
    });

    it("fills missing bounds with zeros", () => {
      const compact = { v: 2 as const, p: { "0": { b: [] as any, t: "1" } } };
      const expanded = expandAnnotationJson(compact, "") as any;
      expect(expanded["0"].bounds).toEqual({
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
      });
    });
  });

  describe("iterPageAnnotations", () => {
    it("yields empty array for span annotations", () => {
      expect(iterPageAnnotations({ start: 0, end: 3 }, "text")).toEqual([]);
    });

    it("yields empty array for falsy inputs", () => {
      expect(iterPageAnnotations(null)).toEqual([]);
      expect(iterPageAnnotations("string" as any)).toEqual([]);
    });

    it("iterates v2 compact pages", () => {
      const pages = iterPageAnnotations(
        { v: 2, p: { "3": { b: [1, 2, 3, 4], t: "1,5-6" } } },
        "raw"
      );
      expect(pages).toHaveLength(1);
      expect(pages[0].pageIndex).toBe(3);
      expect(pages[0].bounds).toEqual({ top: 1, left: 2, right: 3, bottom: 4 });
      expect(pages[0].tokenIndices).toEqual([1, 5, 6]);
      expect(pages[0].rawText).toBe("raw");
    });

    it("iterates v1 legacy pages", () => {
      const pages = iterPageAnnotations(
        {
          "0": {
            bounds: { top: 1, left: 2, right: 3, bottom: 4 },
            tokensJsons: [{ pageIndex: 0, tokenIndex: 7 }],
            rawText: "per-page-text",
          },
        },
        "fallback"
      );
      expect(pages).toHaveLength(1);
      expect(pages[0].pageIndex).toBe(0);
      expect(pages[0].tokenIndices).toEqual([7]);
      expect(pages[0].rawText).toBe("per-page-text");
    });
  });

  describe("hasAnyTokens", () => {
    it("returns true for span annotations", () => {
      expect(hasAnyTokens({ start: 0, end: 5 })).toBe(true);
    });

    it("returns true when any page has tokens", () => {
      expect(
        hasAnyTokens({ v: 2, p: { "0": { b: [0, 0, 0, 0], t: "1" } } })
      ).toBe(true);
    });

    it("returns false for empty multipage annotations", () => {
      expect(hasAnyTokens({ v: 2, p: {} })).toBe(false);
    });

    it("returns false for invalid inputs", () => {
      expect(hasAnyTokens(null)).toBe(false);
      expect(hasAnyTokens("text" as any)).toBe(false);
    });
  });
});
