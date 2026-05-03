import { describe, it, expect, vi } from "vitest";
import { PDFPageInfo } from "../pdf";
import { CompactToken, BoundingBox } from "../../../types";
import { LabelType } from "../../../../types/graphql-api";

/**
 * Minimal PDFPageProxy stub for tests that only need pageNumber.
 */
function makeFakePageProxy(pageNumber: number) {
  return {
    pageNumber,
    getViewport: vi.fn(({ scale }: { scale: number }) => ({
      width: 612 * scale,
      height: 792 * scale,
    })),
  } as any;
}

function makeToken(
  x: number,
  y: number,
  width: number,
  height: number,
  text: string,
  extra: Partial<CompactToken> = {}
): CompactToken {
  return { x, y, width, height, text, isImage: false, ...extra };
}

const PAGE_BOUNDS: BoundingBox = {
  left: 0,
  top: 0,
  right: 612,
  bottom: 792,
};

const FULL_PAGE_SELECTION: BoundingBox = {
  left: 0,
  top: 0,
  right: 612,
  bottom: 792,
};

describe("PDFPageInfo", () => {
  describe("phantom / degenerate token filtering", () => {
    it("excludes empty-text page-spanning tokens from getPageAnnotationJson", () => {
      const realToken = makeToken(100, 200, 50, 10, "Hello");
      const phantomToken = makeToken(0, 0, 612, 792, "");

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [realToken, phantomToken],
        1,
        PAGE_BOUNDS
      );

      const result = pageInfo.getPageAnnotationJson([FULL_PAGE_SELECTION]);

      expect(result.tokensJsons).toHaveLength(1);
      expect(result.tokensJsons[0].tokenIndex).toBe(0);
      expect(result.rawText).toContain("Hello");
      expect(result.bounds.left).toBeGreaterThan(0);
      expect(result.bounds.right).toBeLessThan(612);
    });

    it("excludes page-spanning image tokens (Docling page captures)", () => {
      const realToken = makeToken(100, 200, 50, 10, "Text");
      // Docling emits full-page image tokens with isImage=true
      const pageImage = makeToken(0, 0, 612, 792, "", {
        isImage: true,
        imageMeta: { p: "/page_capture.jpg" },
      });

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [realToken, pageImage],
        1,
        PAGE_BOUNDS
      );

      const result = pageInfo.getPageAnnotationJson([FULL_PAGE_SELECTION]);

      expect(result.tokensJsons).toHaveLength(1);
      expect(result.tokensJsons[0].tokenIndex).toBe(0);
      // Bounds should wrap only the real token
      expect(result.bounds.right).toBeLessThan(612);
    });

    it("excludes page-spanning tokens from getAnnotationForBounds", () => {
      const realToken = makeToken(100, 200, 50, 10, "World");
      const phantomToken = makeToken(0, 0, 612, 792, "", {
        isImage: true,
      });

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [realToken, phantomToken],
        1,
        PAGE_BOUNDS
      );

      const result = pageInfo.getAnnotationForBounds(FULL_PAGE_SELECTION, {
        id: "label-1",
        text: "Test",
        color: "#FF0000",
        icon: "tag",
        description: "",
        labelType: LabelType.TokenLabel,
        readonly: false,
      });

      expect(result).not.toBeNull();
      expect(result?.tokens).toHaveLength(1);
      expect(result?.tokens?.[0].tokenIndex).toBe(0);
    });

    it("excludes page-spanning tokens from getBoundsForTokens", () => {
      const realToken = makeToken(100, 200, 50, 10, "Real");
      const phantomToken = makeToken(0, 0, 612, 792, "", {
        isImage: true,
      });

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [realToken, phantomToken],
        1,
        PAGE_BOUNDS
      );

      const selectedTokens = [
        { pageIndex: 0, tokenIndex: 0 },
        { pageIndex: 0, tokenIndex: 1 }, // phantom
      ];

      const bounds = pageInfo.getBoundsForTokens(selectedTokens);

      expect(bounds).toBeDefined();
      expect(bounds!.left).toBeGreaterThan(0);
      expect(bounds!.right).toBeLessThan(612);
    });

    it("includes normal-sized image tokens with empty text", () => {
      const imageToken = makeToken(50, 50, 200, 150, "", {
        isImage: true,
        imageMeta: { p: "/test.png" },
      });

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [imageToken],
        1,
        PAGE_BOUNDS
      );

      const result = pageInfo.getPageAnnotationJson([FULL_PAGE_SELECTION]);

      expect(result.tokensJsons).toHaveLength(1);
      expect(result.tokensJsons[0].tokenIndex).toBe(0);
    });

    it("excludes whitespace-only text tokens that span the page", () => {
      const realToken = makeToken(100, 200, 50, 10, "Text");
      const whitespaceToken = makeToken(0, 0, 612, 792, "   ");

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [realToken, whitespaceToken],
        1,
        PAGE_BOUNDS
      );

      const result = pageInfo.getPageAnnotationJson([FULL_PAGE_SELECTION]);

      expect(result.tokensJsons).toHaveLength(1);
      expect(result.tokensJsons[0].tokenIndex).toBe(0);
    });

    it("excludes empty-text non-image tokens even if small", () => {
      const realToken = makeToken(100, 200, 50, 10, "Text");
      const emptySmall = makeToken(50, 50, 20, 10, "");

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [realToken, emptySmall],
        1,
        PAGE_BOUNDS
      );

      const result = pageInfo.getPageAnnotationJson([FULL_PAGE_SELECTION]);

      expect(result.tokensJsons).toHaveLength(1);
      expect(result.tokensJsons[0].tokenIndex).toBe(0);
    });
  });

  describe("getPageAnnotationJson", () => {
    it("returns empty result when no tokens overlap selection", () => {
      const token = makeToken(100, 200, 50, 10, "Hello");

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [token],
        1,
        PAGE_BOUNDS
      );

      const selection: BoundingBox = {
        left: 500,
        top: 500,
        right: 600,
        bottom: 600,
      };

      const result = pageInfo.getPageAnnotationJson([selection]);

      expect(result.tokensJsons).toHaveLength(0);
      expect(result.rawText).toBe("");
    });

    it("correctly computes bounds from overlapping tokens", () => {
      const token1 = makeToken(100, 200, 50, 10, "Hello");
      const token2 = makeToken(160, 200, 50, 10, "World");

      const pageInfo = new PDFPageInfo(
        makeFakePageProxy(1),
        [token1, token2],
        1,
        PAGE_BOUNDS
      );

      const selection: BoundingBox = {
        left: 90,
        top: 190,
        right: 220,
        bottom: 220,
      };

      const result = pageInfo.getPageAnnotationJson([selection]);

      expect(result.tokensJsons).toHaveLength(2);
      // spanningBound adds 3px padding
      expect(result.bounds.left).toBe(100 - 3);
      expect(result.bounds.top).toBe(200 - 3);
      expect(result.bounds.right).toBe(210 + 3);
      expect(result.bounds.bottom).toBe(210 + 3);
    });
  });
});
