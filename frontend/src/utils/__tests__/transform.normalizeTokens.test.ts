import { describe, it, expect, vi } from "vitest";
import { normalizeTokensToPdfViewport, resolvePageTokens } from "../transform";
import { CompactPage, CompactToken } from "../../components/types";

describe("normalizeTokensToPdfViewport", () => {
  const makeCompactPage = (
    pageWidth: number,
    pageHeight: number,
    tokens: CompactToken[]
  ): CompactPage => ({
    index: 0,
    width: pageWidth,
    height: pageHeight,
    tokens,
  });

  const sampleTokens: CompactToken[] = [
    { x: 100, y: 200, width: 50, height: 10, text: "hello", isImage: false },
    { x: 300, y: 400, width: 80, height: 12, text: "world", isImage: false },
  ];

  it("returns original tokens when dimensions match within epsilon", () => {
    const pageData = makeCompactPage(612, 792, sampleTokens);
    const result = normalizeTokensToPdfViewport(pageData, 612, 792);
    // Should return the exact same array reference (no copy)
    expect(result).toBe(sampleTokens);
  });

  it("returns original tokens when dimensions differ by less than 0.5", () => {
    const pageData = makeCompactPage(612, 792, sampleTokens);
    const result = normalizeTokensToPdfViewport(pageData, 612.3, 792.4);
    expect(result).toBe(sampleTokens);
  });

  it("rescales tokens when PAWLs width differs from viewport", () => {
    // PAWLs reports 612x792 but PDF.js viewport is 595x842
    const pageData = makeCompactPage(612, 792, sampleTokens);
    const result = normalizeTokensToPdfViewport(pageData, 595, 842);

    const scaleX = 595 / 612;
    const scaleY = 842 / 792;

    expect(result).toHaveLength(2);
    expect(result[0].x).toBeCloseTo(100 * scaleX);
    expect(result[0].y).toBeCloseTo(200 * scaleY);
    expect(result[0].width).toBeCloseTo(50 * scaleX);
    expect(result[0].height).toBeCloseTo(10 * scaleY);
    expect(result[0].text).toBe("hello");

    expect(result[1].x).toBeCloseTo(300 * scaleX);
    expect(result[1].y).toBeCloseTo(400 * scaleY);
    expect(result[1].width).toBeCloseTo(80 * scaleX);
    expect(result[1].height).toBeCloseTo(12 * scaleY);
    expect(result[1].text).toBe("world");
  });

  it("preserves image token fields during rescaling", () => {
    const imageTokens: CompactToken[] = [
      {
        x: 50,
        y: 100,
        width: 200,
        height: 150,
        text: "",
        isImage: true,
        imageMeta: {
          p: "/images/fig1.jpg",
          f: "jpeg",
          ow: 1024,
          oh: 768,
        },
      },
    ];
    const pageData = makeCompactPage(612, 792, imageTokens);
    const result = normalizeTokensToPdfViewport(pageData, 600, 800);

    const scaleX = 600 / 612;
    const scaleY = 800 / 792;

    expect(result[0].x).toBeCloseTo(50 * scaleX);
    expect(result[0].y).toBeCloseTo(100 * scaleY);
    expect(result[0].width).toBeCloseTo(200 * scaleX);
    expect(result[0].height).toBeCloseTo(150 * scaleY);
    expect(result[0].isImage).toBe(true);
    expect(result[0].imageMeta?.p).toBe("/images/fig1.jpg");
    expect(result[0].imageMeta?.f).toBe("jpeg");
    // ow/oh are image pixel dimensions, not PDF coordinates — they must
    // NOT be rescaled.
    expect(result[0].imageMeta?.ow).toBe(1024);
    expect(result[0].imageMeta?.oh).toBe(768);
  });

  it("returns tokens as-is when PAWLs page dimensions are zero", () => {
    const pageData = makeCompactPage(0, 0, sampleTokens);
    const result = normalizeTokensToPdfViewport(pageData, 612, 792);
    // Cannot rescale with zero dimensions — return original tokens untouched
    expect(result).toBe(sampleTokens);
  });

  it("returns tokens as-is when only one PAWLs dimension is zero", () => {
    const pageData = makeCompactPage(612, 0, sampleTokens);
    const result = normalizeTokensToPdfViewport(pageData, 612, 792);
    expect(result).toBe(sampleTokens);
  });

  it("returns tokens as-is when viewport width is zero", () => {
    const pageData = makeCompactPage(612, 792, sampleTokens);
    const result = normalizeTokensToPdfViewport(pageData, 0, 792);
    expect(result).toBe(sampleTokens);
  });

  it("returns tokens as-is when viewport height is zero", () => {
    const pageData = makeCompactPage(612, 792, sampleTokens);
    const result = normalizeTokensToPdfViewport(pageData, 612, 0);
    expect(result).toBe(sampleTokens);
  });

  it("handles empty token arrays", () => {
    const pageData = makeCompactPage(612, 792, []);
    const result = normalizeTokensToPdfViewport(pageData, 595, 842);
    expect(result).toHaveLength(0);
  });
});

describe("resolvePageTokens", () => {
  const makeCompactPage = (
    pageWidth: number,
    pageHeight: number,
    tokens: CompactToken[]
  ): CompactPage => ({
    index: 0,
    width: pageWidth,
    height: pageHeight,
    tokens,
  });

  const sampleTokens: CompactToken[] = [
    { x: 100, y: 200, width: 50, height: 10, text: "hello", isImage: false },
  ];

  it("returns [] and warns when pawlsData is null", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const result = resolvePageTokens(null, 0, 612, 792, 1);
    expect(result).toEqual([]);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("PAWLS data index out of bounds")
    );
    warnSpy.mockRestore();
  });

  it("returns [] and warns when pawlsData is undefined", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const result = resolvePageTokens(undefined, 0, 612, 792, 1);
    expect(result).toEqual([]);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("PAWLS data index out of bounds")
    );
    warnSpy.mockRestore();
  });

  it("returns [] and warns when pageIndex is out of bounds", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const pages = [makeCompactPage(612, 792, sampleTokens)];
    const result = resolvePageTokens(pages, 5, 612, 792, 6);
    expect(result).toEqual([]);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("Index: 5, Length: 1")
    );
    warnSpy.mockRestore();
  });

  it("returns [] and logs error when tokens is not an array", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const badPage = {
      index: 0,
      width: 612,
      height: 792,
      tokens: "not-an-array" as unknown as CompactToken[],
    };
    const result = resolvePageTokens([badPage], 0, 612, 792, 1);
    expect(result).toEqual([]);
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining("CRITICAL - pageData.tokens is not an array")
    );
    errorSpy.mockRestore();
  });

  it("returns [] when pageData is falsy (sparse array)", () => {
    const sparsePages: CompactPage[] = [];
    sparsePages[2] = makeCompactPage(612, 792, sampleTokens);
    const result = resolvePageTokens(sparsePages, 0, 612, 792, 1);
    expect(result).toEqual([]);
  });

  it("returns [] when pageData.tokens is undefined", () => {
    const noTokensPage = {
      index: 0,
      width: 612,
      height: 792,
    } as unknown as CompactPage;
    const result = resolvePageTokens([noTokensPage], 0, 612, 792, 1);
    expect(result).toEqual([]);
  });

  it("delegates to normalizeTokensToPdfViewport on valid data", () => {
    const pages = [makeCompactPage(612, 792, sampleTokens)];
    // Same dimensions → should return original tokens reference
    const result = resolvePageTokens(pages, 0, 612, 792, 1);
    expect(result).toBe(sampleTokens);
  });

  it("returns rescaled tokens when viewport differs", () => {
    const pages = [makeCompactPage(612, 792, sampleTokens)];
    const result = resolvePageTokens(pages, 0, 595, 842, 1);
    const scaleX = 595 / 612;
    const scaleY = 842 / 792;
    expect(result).toHaveLength(1);
    expect(result[0].x).toBeCloseTo(100 * scaleX);
    expect(result[0].y).toBeCloseTo(200 * scaleY);
  });
});
