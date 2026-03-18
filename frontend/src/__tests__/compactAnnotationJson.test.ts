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
  CompactAnnotationJson,
} from "../utils/compactAnnotationJson";
import { COMPACT_JSON_MAX_RANGE_SPAN } from "../assets/configurations/constants";
import {
  MultipageAnnotationJson,
  SpanAnnotationJson,
} from "../components/types";

// ── encodeTokenRanges ──────────────────────────────────────────

describe("encodeTokenRanges", () => {
  it("returns empty string for empty array", () => {
    expect(encodeTokenRanges([])).toBe("");
  });

  it("encodes a single item", () => {
    expect(encodeTokenRanges([42])).toBe("42");
  });

  it("encodes a consecutive range", () => {
    expect(encodeTokenRanges([1, 2, 3, 4, 5])).toBe("1-5");
  });

  it("encodes multiple disjoint ranges and singletons", () => {
    expect(encodeTokenRanges([1, 2, 3, 5, 7, 8, 9])).toBe("1-3,5,7-9");
  });

  it("handles already-sorted input identically", () => {
    const sorted = [10, 11, 12, 20, 21];
    expect(encodeTokenRanges(sorted)).toBe("10-12,20-21");
  });

  it("sorts unsorted input before encoding", () => {
    expect(encodeTokenRanges([9, 7, 8, 1, 3, 2, 5])).toBe("1-3,5,7-9");
  });

  it("handles two separate singletons", () => {
    expect(encodeTokenRanges([10, 20])).toBe("10,20");
  });

  it("handles all singletons (no consecutive indices)", () => {
    expect(encodeTokenRanges([1, 3, 5, 7])).toBe("1,3,5,7");
  });
});

// ── decodeTokenRanges ──────────────────────────────────────────

describe("decodeTokenRanges", () => {
  it("returns empty array for empty string", () => {
    expect(decodeTokenRanges("")).toEqual([]);
  });

  it("decodes a single number", () => {
    expect(decodeTokenRanges("42")).toEqual([42]);
  });

  it("decodes a range", () => {
    expect(decodeTokenRanges("1-5")).toEqual([1, 2, 3, 4, 5]);
  });

  it("decodes multiple ranges and singletons", () => {
    expect(decodeTokenRanges("1-3,5,7-9")).toEqual([1, 2, 3, 5, 7, 8, 9]);
  });

  it("skips malformed non-numeric parts", () => {
    // "abc" is not a number, so parseInt returns NaN and it is skipped
    expect(decodeTokenRanges("abc")).toEqual([]);
  });

  it("skips malformed range parts", () => {
    // "a-b" produces NaN on both sides, so the range is skipped
    expect(decodeTokenRanges("a-b")).toEqual([]);
  });

  it("skips ranges that exceed COMPACT_JSON_MAX_RANGE_SPAN", () => {
    const oversized = `0-${COMPACT_JSON_MAX_RANGE_SPAN + 1}`;
    expect(decodeTokenRanges(oversized)).toEqual([]);
  });

  it("accepts ranges exactly at COMPACT_JSON_MAX_RANGE_SPAN", () => {
    const maxRange = `0-${COMPACT_JSON_MAX_RANGE_SPAN}`;
    const result = decodeTokenRanges(maxRange);
    expect(result).toHaveLength(COMPACT_JSON_MAX_RANGE_SPAN + 1);
    expect(result[0]).toBe(0);
    expect(result[result.length - 1]).toBe(COMPACT_JSON_MAX_RANGE_SPAN);
  });

  it("skips inverted ranges (end < start)", () => {
    // end - start < 0 triggers the guard
    expect(decodeTokenRanges("5-3")).toEqual([]);
  });

  it("mixes valid and invalid parts, keeping only valid ones", () => {
    expect(decodeTokenRanges("1-3,abc,7")).toEqual([1, 2, 3, 7]);
  });
});

// ── Roundtrip ──────────────────────────────────────────────────

describe("encodeTokenRanges / decodeTokenRanges roundtrip", () => {
  const cases: number[][] = [
    [],
    [0],
    [100],
    [1, 2, 3],
    [1, 2, 3, 5, 7, 8, 9],
    [10, 20, 30],
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    [5, 3, 1, 2, 4], // unsorted
  ];

  for (const input of cases) {
    const sorted = [...input].sort((a, b) => a - b);
    it(`roundtrips [${input.join(",")}]`, () => {
      expect(decodeTokenRanges(encodeTokenRanges(input))).toEqual(sorted);
    });
  }
});

// ── isCompactFormat ────────────────────────────────────────────

describe("isCompactFormat", () => {
  it("returns true for v2 data", () => {
    const v2: CompactAnnotationJson = {
      v: 2,
      p: { "0": { b: [10, 20, 30, 40], t: "1-3" } },
    };
    expect(isCompactFormat(v2)).toBe(true);
  });

  it("returns false for v1 data", () => {
    const v1: Record<string, unknown> = {
      "0": {
        bounds: { top: 10, left: 20, right: 30, bottom: 40 },
        tokensJsons: [{ pageIndex: 0, tokenIndex: 1 }],
        rawText: "hello",
      },
    };
    expect(isCompactFormat(v1)).toBe(false);
  });

  it("returns false for null (guarded by null check)", () => {
    // The function signature requires a non-null object, but the runtime
    // guard handles null gracefully.
    expect(isCompactFormat(null as unknown as Record<string, unknown>)).toBe(
      false
    );
  });

  it("returns false when v is present but p is missing", () => {
    expect(isCompactFormat({ v: 2 } as unknown as CompactAnnotationJson)).toBe(
      false
    );
  });

  it("returns false when v is not 2", () => {
    expect(
      isCompactFormat({ v: 1, p: {} } as unknown as Record<string, unknown>)
    ).toBe(false);
  });
});

// ── isSpanFormat ───────────────────────────────────────────────

describe("isSpanFormat", () => {
  it("returns true for a valid span with start and end", () => {
    expect(isSpanFormat({ start: 0, end: 10 })).toBe(true);
  });

  it("returns true for a valid span with start, end, and text", () => {
    expect(isSpanFormat({ start: 0, end: 10, text: "hello" })).toBe(true);
  });

  it("returns true when extra keys are present", () => {
    expect(isSpanFormat({ start: 0, end: 10, extra: true })).toBe(true);
  });

  it("returns false for non-objects", () => {
    expect(isSpanFormat(null as unknown as Record<string, unknown>)).toBe(
      false
    );
    expect(isSpanFormat(undefined as unknown as Record<string, unknown>)).toBe(
      false
    );
  });

  it("returns false when start is missing", () => {
    expect(isSpanFormat({ end: 10 } as Record<string, unknown>)).toBe(false);
  });

  it("returns false when end is missing", () => {
    expect(isSpanFormat({ start: 0 } as Record<string, unknown>)).toBe(false);
  });
});

// ── compactAnnotationJson (v1 -> v2) ──────────────────────────

describe("compactAnnotationJson", () => {
  it("converts v1 single-page annotation to v2", () => {
    const v1: MultipageAnnotationJson = {
      0: {
        bounds: { top: 10, left: 20, right: 30, bottom: 40 },
        tokensJsons: [
          { pageIndex: 0, tokenIndex: 1 },
          { pageIndex: 0, tokenIndex: 2 },
          { pageIndex: 0, tokenIndex: 3 },
        ],
        rawText: "hello world",
      },
    };

    const result = compactAnnotationJson(v1);

    expect(result.v).toBe(2);
    expect(result.p["0"].b).toEqual([10, 20, 30, 40]);
    expect(result.p["0"].t).toBe("1-3");
  });

  it("converts v1 multi-page annotation to v2", () => {
    const v1: MultipageAnnotationJson = {
      0: {
        bounds: { top: 1, left: 2, right: 3, bottom: 4 },
        tokensJsons: [{ pageIndex: 0, tokenIndex: 5 }],
        rawText: "page 0",
      },
      1: {
        bounds: { top: 10, left: 20, right: 30, bottom: 40 },
        tokensJsons: [
          { pageIndex: 1, tokenIndex: 10 },
          { pageIndex: 1, tokenIndex: 11 },
        ],
        rawText: "page 1",
      },
    };

    const result = compactAnnotationJson(v1);

    expect(result.v).toBe(2);
    expect(Object.keys(result.p)).toHaveLength(2);
    expect(result.p["0"].b).toEqual([1, 2, 3, 4]);
    expect(result.p["0"].t).toBe("5");
    expect(result.p["1"].b).toEqual([10, 20, 30, 40]);
    expect(result.p["1"].t).toBe("10-11");
  });

  it("handles missing bounds gracefully (defaults to zeros)", () => {
    const v1 = {
      0: {
        tokensJsons: [{ pageIndex: 0, tokenIndex: 0 }],
        rawText: "",
      },
    } as unknown as MultipageAnnotationJson;

    const result = compactAnnotationJson(v1);
    expect(result.p["0"].b).toEqual([0, 0, 0, 0]);
  });

  it("handles missing tokensJsons gracefully (defaults to empty string)", () => {
    const v1 = {
      0: {
        bounds: { top: 1, left: 2, right: 3, bottom: 4 },
        rawText: "",
      },
    } as unknown as MultipageAnnotationJson;

    const result = compactAnnotationJson(v1);
    expect(result.p["0"].t).toBe("");
  });
});

// ── expandAnnotationJson (v2 -> v1) ───────────────────────────

describe("expandAnnotationJson", () => {
  it("expands a v2 annotation back to v1", () => {
    const v2: CompactAnnotationJson = {
      v: 2,
      p: {
        "0": { b: [10, 20, 30, 40], t: "1-3" },
      },
    };

    const result = expandAnnotationJson(v2, "hello");
    // Should NOT be compact format anymore
    expect(isCompactFormat(result as Record<string, unknown>)).toBe(false);

    const page = (result as MultipageAnnotationJson)[0 as unknown as number];
    expect(page.bounds).toEqual({
      top: 10,
      left: 20,
      right: 30,
      bottom: 40,
    });
    expect(page.tokensJsons).toEqual([
      { pageIndex: 0, tokenIndex: 1 },
      { pageIndex: 0, tokenIndex: 2 },
      { pageIndex: 0, tokenIndex: 3 },
    ]);
    expect(page.rawText).toBe("hello");
  });

  it("passes through v1 data unchanged", () => {
    const v1: MultipageAnnotationJson = {
      0: {
        bounds: { top: 1, left: 2, right: 3, bottom: 4 },
        tokensJsons: [{ pageIndex: 0, tokenIndex: 5 }],
        rawText: "test",
      },
    };

    const result = expandAnnotationJson(v1);
    expect(result).toBe(v1); // Same reference — no transformation
  });

  it("passes through span annotations unchanged", () => {
    const span: SpanAnnotationJson = { start: 0, end: 10 };
    const result = expandAnnotationJson(span);
    expect(result).toBe(span);
  });

  it("handles null/falsy input gracefully", () => {
    const result = expandAnnotationJson(
      null as unknown as MultipageAnnotationJson
    );
    expect(result).toBeNull();
  });

  it("uses empty string as default rawText", () => {
    const v2: CompactAnnotationJson = {
      v: 2,
      p: { "0": { b: [0, 0, 0, 0], t: "5" } },
    };

    const result = expandAnnotationJson(v2);
    const page = (result as MultipageAnnotationJson)[0 as unknown as number];
    expect(page.rawText).toBe("");
  });

  it("expands multi-page v2 annotations", () => {
    const v2: CompactAnnotationJson = {
      v: 2,
      p: {
        "0": { b: [1, 2, 3, 4], t: "0" },
        "3": { b: [10, 20, 30, 40], t: "10-12" },
      },
    };

    const result = expandAnnotationJson(v2, "text") as MultipageAnnotationJson;
    const page0 = result[0 as unknown as number];
    const page3 = result[3 as unknown as number];

    expect(page0.tokensJsons).toEqual([{ pageIndex: 0, tokenIndex: 0 }]);
    expect(page3.tokensJsons).toEqual([
      { pageIndex: 3, tokenIndex: 10 },
      { pageIndex: 3, tokenIndex: 11 },
      { pageIndex: 3, tokenIndex: 12 },
    ]);
  });
});

// ── Full v1 -> v2 -> v1 roundtrip ─────────────────────────────

describe("compactAnnotationJson / expandAnnotationJson roundtrip", () => {
  it("roundtrips a single-page annotation", () => {
    const v1: MultipageAnnotationJson = {
      0: {
        bounds: { top: 10, left: 20, right: 30, bottom: 40 },
        tokensJsons: [
          { pageIndex: 0, tokenIndex: 1 },
          { pageIndex: 0, tokenIndex: 2 },
          { pageIndex: 0, tokenIndex: 3 },
          { pageIndex: 0, tokenIndex: 5 },
        ],
        rawText: "hello",
      },
    };

    const compacted = compactAnnotationJson(v1);
    const expanded = expandAnnotationJson(
      compacted,
      "hello"
    ) as MultipageAnnotationJson;

    const page = expanded[0 as unknown as number];
    expect(page.bounds).toEqual(v1[0].bounds);
    expect(page.tokensJsons).toEqual(v1[0].tokensJsons);
    expect(page.rawText).toBe(v1[0].rawText);
  });
});

// ── iterPageAnnotations (format-agnostic accessor) ────────────

describe("iterPageAnnotations", () => {
  it("reads v1 single page", () => {
    const v1: MultipageAnnotationJson = {
      0: {
        bounds: { top: 10, left: 20, right: 30, bottom: 40 },
        tokensJsons: [
          { pageIndex: 0, tokenIndex: 1 },
          { pageIndex: 0, tokenIndex: 2 },
          { pageIndex: 0, tokenIndex: 5 },
        ],
        rawText: "hello",
      },
    };
    const pages = iterPageAnnotations(v1, "fallback");
    expect(pages).toHaveLength(1);
    expect(pages[0].pageIndex).toBe(0);
    expect(pages[0].bounds).toEqual({
      top: 10,
      left: 20,
      right: 30,
      bottom: 40,
    });
    expect(pages[0].tokenIndices).toEqual([1, 2, 5]);
    // v1 per-page rawText takes precedence
    expect(pages[0].rawText).toBe("hello");
  });

  it("reads v2 single page", () => {
    const v2: CompactAnnotationJson = {
      v: 2,
      p: { "0": { b: [10, 20, 30, 40], t: "1-2,5" } },
    };
    const pages = iterPageAnnotations(v2, "hello");
    expect(pages).toHaveLength(1);
    expect(pages[0].pageIndex).toBe(0);
    expect(pages[0].bounds).toEqual({
      top: 10,
      left: 20,
      right: 30,
      bottom: 40,
    });
    expect(pages[0].tokenIndices).toEqual([1, 2, 5]);
    expect(pages[0].rawText).toBe("hello");
  });

  it("v1 and v2 produce identical results", () => {
    const v1: MultipageAnnotationJson = {
      0: {
        bounds: { top: 10, left: 20, right: 30, bottom: 40 },
        tokensJsons: [
          { pageIndex: 0, tokenIndex: 1 },
          { pageIndex: 0, tokenIndex: 2 },
          { pageIndex: 0, tokenIndex: 3 },
        ],
        rawText: "hello",
      },
    };
    const v2 = compactAnnotationJson(v1);
    const pagesV1 = iterPageAnnotations(v1);
    const pagesV2 = iterPageAnnotations(v2, "hello");

    expect(pagesV1).toHaveLength(pagesV2.length);
    for (let i = 0; i < pagesV1.length; i++) {
      expect(pagesV1[i].pageIndex).toBe(pagesV2[i].pageIndex);
      expect(pagesV1[i].bounds).toEqual(pagesV2[i].bounds);
      expect(pagesV1[i].tokenIndices).toEqual(pagesV2[i].tokenIndices);
      expect(pagesV1[i].rawText).toBe(pagesV2[i].rawText);
    }
  });

  it("span annotations return empty", () => {
    expect(iterPageAnnotations({ start: 0, end: 100 })).toEqual([]);
  });

  it("null/undefined return empty", () => {
    expect(iterPageAnnotations(null)).toEqual([]);
    expect(iterPageAnnotations(undefined)).toEqual([]);
  });

  it("empty object returns empty", () => {
    expect(iterPageAnnotations({})).toEqual([]);
  });

  it("multi-page v2", () => {
    const v2: CompactAnnotationJson = {
      v: 2,
      p: {
        "0": { b: [0, 0, 0, 0], t: "1-3" },
        "5": { b: [1, 1, 1, 1], t: "10,20" },
      },
    };
    const pages = iterPageAnnotations(v2, "text");
    expect(pages).toHaveLength(2);
    expect(pages[0].pageIndex).toBe(0);
    expect(pages[0].tokenIndices).toEqual([1, 2, 3]);
    expect(pages[1].pageIndex).toBe(5);
    expect(pages[1].tokenIndices).toEqual([10, 20]);
  });
});

// ── hasAnyTokens ──────────────────────────────────────────────

describe("hasAnyTokens", () => {
  it("returns true for v1 with tokens", () => {
    const v1: MultipageAnnotationJson = {
      0: {
        bounds: { top: 0, left: 0, right: 0, bottom: 0 },
        tokensJsons: [{ pageIndex: 0, tokenIndex: 1 }],
        rawText: "",
      },
    };
    expect(hasAnyTokens(v1)).toBe(true);
  });

  it("returns true for v2 with tokens", () => {
    const v2: CompactAnnotationJson = {
      v: 2,
      p: { "0": { b: [0, 0, 0, 0], t: "1-3" } },
    };
    expect(hasAnyTokens(v2)).toBe(true);
  });

  it("returns false for v1 with empty tokens", () => {
    const v1: MultipageAnnotationJson = {
      0: {
        bounds: { top: 0, left: 0, right: 0, bottom: 0 },
        tokensJsons: [],
        rawText: "",
      },
    };
    expect(hasAnyTokens(v1)).toBe(false);
  });

  it("returns false for v2 with empty tokens", () => {
    const v2: CompactAnnotationJson = {
      v: 2,
      p: { "0": { b: [0, 0, 0, 0], t: "" } },
    };
    expect(hasAnyTokens(v2)).toBe(false);
  });

  it("returns true for span annotations", () => {
    expect(hasAnyTokens({ start: 0, end: 100 })).toBe(true);
  });

  it("returns false for null", () => {
    expect(hasAnyTokens(null)).toBe(false);
  });

  it("returns false for empty object", () => {
    expect(hasAnyTokens({})).toBe(false);
  });
});
