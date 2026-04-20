import { describe, it, expect } from "vitest";
import {
  encodeTextBlock,
  decodeTextBlock,
  textBlockFromSpan,
  textBlockFromMultipageJson,
  textBlockFromTokensByPage,
  textBlockToTokenIds,
  textBlockToBounds,
  TextSpanBlock,
  PdfTokenBlock,
} from "./textBlockEncoding";
import type { MultipageAnnotationJson } from "../components/types";

describe("textBlockEncoding", () => {
  // ───────────────────────────────────────────────────────────────
  // Span encoding / decoding
  // ───────────────────────────────────────────────────────────────

  describe("encodeTextBlock (span)", () => {
    it("encodes a simple span block", () => {
      const block: TextSpanBlock = { type: "span", start: 100, end: 500 };
      expect(encodeTextBlock(block)).toBe("s100-500");
    });

    it("encodes a zero-start span", () => {
      const block: TextSpanBlock = { type: "span", start: 0, end: 10 };
      expect(encodeTextBlock(block)).toBe("s0-10");
    });

    it("encodes a zero-length span (caret-at-position reference)", () => {
      const block: TextSpanBlock = { type: "span", start: 42, end: 42 };
      expect(encodeTextBlock(block)).toBe("s42-42");
    });
  });

  describe("decodeTextBlock (span)", () => {
    it("decodes a valid span string", () => {
      const result = decodeTextBlock("s100-500");
      expect(result).toEqual({ type: "span", start: 100, end: 500 });
    });

    it("decodes a zero-start span", () => {
      const result = decodeTextBlock("s0-10");
      expect(result).toEqual({ type: "span", start: 0, end: 10 });
    });

    it("returns null for malformed span", () => {
      expect(decodeTextBlock("s100")).toBeNull();
      expect(decodeTextBlock("s-100")).toBeNull();
      expect(decodeTextBlock("sabc-def")).toBeNull();
    });

    it("returns null for inverted span (start > end)", () => {
      expect(decodeTextBlock("s500-100")).toBeNull();
    });
  });

  describe("span roundtrip", () => {
    it("encode → decode produces identical block", () => {
      const original: TextSpanBlock = { type: "span", start: 42, end: 999 };
      const encoded = encodeTextBlock(original);
      const decoded = decodeTextBlock(encoded);
      expect(decoded).toEqual(original);
    });
  });

  // ───────────────────────────────────────────────────────────────
  // PDF token encoding / decoding
  // ───────────────────────────────────────────────────────────────

  describe("encodeTextBlock (pdf)", () => {
    it("encodes a single-page pdf block", () => {
      const block: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [1, 2, 3, 5, 7, 8, 9] },
      };
      expect(encodeTextBlock(block)).toBe("p0:1-3,5,7-9");
    });

    it("encodes a multi-page pdf block", () => {
      const block: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [10, 11, 12], 2: [0, 1] },
      };
      const encoded = encodeTextBlock(block);
      // Pages are encoded in iteration order; both segments should appear
      expect(encoded).toContain("p0:10-12");
      expect(encoded).toContain("p2:0-1");
      expect(encoded).toContain(";");
    });

    it("skips pages with empty token arrays", () => {
      const block: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [], 1: [5] },
      };
      expect(encodeTextBlock(block)).toBe("p1:5");
    });

    it("sorts unordered tokens before collapsing into ranges", () => {
      const block: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [5, 1, 3, 2, 4] },
      };
      expect(encodeTextBlock(block)).toBe("p0:1-5");
    });
  });

  describe("decodeTextBlock (pdf)", () => {
    it("decodes a single-page pdf string", () => {
      const result = decodeTextBlock("p0:1-3,5,7-9");
      expect(result).toEqual({
        type: "pdf",
        tokensByPage: { 0: [1, 2, 3, 5, 7, 8, 9] },
      });
    });

    it("decodes a multi-page pdf string", () => {
      const result = decodeTextBlock("p0:10-12;p2:0-1");
      expect(result).toEqual({
        type: "pdf",
        tokensByPage: {
          0: [10, 11, 12],
          2: [0, 1],
        },
      });
    });

    it("returns null for empty pdf token set", () => {
      // "p0:" has no valid ranges → empty page → null
      expect(decodeTextBlock("p0:")).toBeNull();
    });

    it("skips malformed segments but keeps valid ones in a mixed string", () => {
      expect(decodeTextBlock("p0:1-3;garbage;p1:5")).toEqual({
        type: "pdf",
        tokensByPage: { 0: [1, 2, 3], 1: [5] },
      });
    });
  });

  describe("pdf roundtrip", () => {
    it("encode → decode preserves tokens", () => {
      const original: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [1, 2, 3, 5], 1: [10, 20, 21, 22] },
      };
      const encoded = encodeTextBlock(original);
      const decoded = decodeTextBlock(encoded);
      expect(decoded).toEqual(original);
    });

    it("handles single-token pages", () => {
      const original: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 3: [42] },
      };
      const encoded = encodeTextBlock(original);
      const decoded = decodeTextBlock(encoded);
      expect(decoded).toEqual(original);
    });
  });

  // ───────────────────────────────────────────────────────────────
  // Edge cases and error handling
  // ───────────────────────────────────────────────────────────────

  describe("decodeTextBlock edge cases", () => {
    it("returns null for empty string", () => {
      expect(decodeTextBlock("")).toBeNull();
    });

    it("returns null for unknown prefix", () => {
      expect(decodeTextBlock("x100-200")).toBeNull();
      expect(decodeTextBlock("abc")).toBeNull();
    });

    it("rejects range spans exceeding MAX_RANGE_SPAN (10 000)", () => {
      // A range of 0-20000 would produce 20001 elements → should be skipped
      const result = decodeTextBlock("p0:0-20000");
      expect(result).toBeNull(); // no valid tokens → null
    });

    it("accepts range spans within MAX_RANGE_SPAN", () => {
      const result = decodeTextBlock("p0:0-100");
      expect(result).not.toBeNull();
      expect(result!.type).toBe("pdf");
      const pdfBlock = result as PdfTokenBlock;
      expect(pdfBlock.tokensByPage[0]).toHaveLength(101);
    });

    it("caps cumulative tokens across pages at MAX_TOTAL_TOKENS (50 000)", () => {
      // Build 10 page segments of 9999 tokens each = 99990 total, exceeding cap
      const segments = Array.from(
        { length: 10 },
        (_, i) => `p${i}:0-9998`
      ).join(";");
      const result = decodeTextBlock(segments);
      expect(result).not.toBeNull();
      const pdfBlock = result as PdfTokenBlock;
      // Should have stopped adding pages once cumulative count exceeded 50 000
      const totalTokens = Object.values(pdfBlock.tokensByPage).reduce(
        (sum, arr) => sum + arr.length,
        0
      );
      expect(totalTokens).toBeLessThanOrEqual(50_000);
      // Should have fewer than 10 pages (some were dropped)
      expect(Object.keys(pdfBlock.tokensByPage).length).toBeLessThan(10);
    });
  });

  // ───────────────────────────────────────────────────────────────
  // Helper functions
  // ───────────────────────────────────────────────────────────────

  describe("textBlockFromSpan", () => {
    it("creates a TextSpanBlock", () => {
      expect(textBlockFromSpan(10, 50)).toEqual({
        type: "span",
        start: 10,
        end: 50,
      });
    });
  });

  describe("textBlockFromMultipageJson", () => {
    it("extracts token indices per page from a MultipageAnnotationJson", () => {
      const json: MultipageAnnotationJson = {
        0: {
          bounds: { top: 0, bottom: 10, left: 0, right: 10 },
          rawText: "hello",
          tokensJsons: [
            { pageIndex: 0, tokenIndex: 5 },
            { pageIndex: 0, tokenIndex: 6 },
            { pageIndex: 0, tokenIndex: 7 },
          ],
        },
        2: {
          bounds: { top: 0, bottom: 10, left: 0, right: 10 },
          rawText: "world",
          tokensJsons: [{ pageIndex: 2, tokenIndex: 0 }],
        },
      };
      expect(textBlockFromMultipageJson(json)).toEqual({
        type: "pdf",
        tokensByPage: { 0: [5, 6, 7], 2: [0] },
      });
    });

    it("omits pages that have no tokensJsons entries", () => {
      const json: MultipageAnnotationJson = {
        0: {
          bounds: { top: 0, bottom: 10, left: 0, right: 10 },
          rawText: "",
          tokensJsons: [],
        },
      };
      expect(textBlockFromMultipageJson(json)).toEqual({
        type: "pdf",
        tokensByPage: {},
      });
    });
  });

  describe("textBlockFromTokensByPage", () => {
    it("converts TokenId arrays to PdfTokenBlock", () => {
      const input = {
        0: [
          { pageIndex: 0, tokenIndex: 5 },
          { pageIndex: 0, tokenIndex: 6 },
        ],
        2: [{ pageIndex: 2, tokenIndex: 0 }],
      };
      const result = textBlockFromTokensByPage(input);
      expect(result).toEqual({
        type: "pdf",
        tokensByPage: { 0: [5, 6], 2: [0] },
      });
    });

    it("skips empty token arrays", () => {
      const input = {
        0: [] as { pageIndex: number; tokenIndex: number }[],
        1: [{ pageIndex: 1, tokenIndex: 3 }],
      };
      const result = textBlockFromTokensByPage(input);
      expect(result.tokensByPage[0]).toBeUndefined();
      expect(result.tokensByPage[1]).toEqual([3]);
    });
  });

  describe("textBlockToTokenIds", () => {
    it("converts PdfTokenBlock back to TokenId arrays", () => {
      const block: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [5, 6], 2: [0] },
      };
      const result = textBlockToTokenIds(block);
      expect(result[0]).toEqual([
        { pageIndex: 0, tokenIndex: 5 },
        { pageIndex: 0, tokenIndex: 6 },
      ]);
      expect(result[2]).toEqual([{ pageIndex: 2, tokenIndex: 0 }]);
    });
  });

  describe("textBlockToBounds", () => {
    it("computes bounding box from token geometry", () => {
      const block: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [0, 1] },
      };
      const pageTokens = {
        0: [
          { x: 10, y: 20, width: 30, height: 10 },
          { x: 50, y: 20, width: 20, height: 10 },
        ],
      };
      const result = textBlockToBounds(block, pageTokens);
      expect(result[0]).toEqual({
        top: 20,
        left: 10,
        bottom: 30,
        right: 70,
      });
    });

    it("skips pages without token data", () => {
      const block: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [0], 1: [0] },
      };
      const pageTokens = {
        0: [{ x: 0, y: 0, width: 10, height: 10 }],
        // Page 1 has no token data
      };
      const result = textBlockToBounds(block, pageTokens);
      expect(result[0]).toBeDefined();
      expect(result[1]).toBeUndefined();
    });

    it("skips out-of-range token indices", () => {
      const block: PdfTokenBlock = {
        type: "pdf",
        tokensByPage: { 0: [999] },
      };
      const pageTokens = {
        0: [{ x: 0, y: 0, width: 10, height: 10 }],
      };
      const result = textBlockToBounds(block, pageTokens);
      // Token 999 doesn't exist → no valid bounds
      expect(result[0]).toBeUndefined();
    });
  });
});
