import { describe, test, expect } from "vitest";
import { isCompactPawlsFormat, expandPawlsPages } from "../compactPawls";

describe("isCompactPawlsFormat", () => {
  test("returns true for valid v2 structure", () => {
    expect(isCompactPawlsFormat({ v: 2, p: [] })).toBe(true);
  });

  test("returns false for v1 list", () => {
    expect(isCompactPawlsFormat([])).toBe(false);
  });

  test("returns false for wrong version", () => {
    expect(isCompactPawlsFormat({ v: 1, p: [] })).toBe(false);
  });

  test("returns false for null/undefined", () => {
    expect(isCompactPawlsFormat(null)).toBe(false);
    expect(isCompactPawlsFormat(undefined)).toBe(false);
  });

  test("returns false for missing p key", () => {
    expect(isCompactPawlsFormat({ v: 2 })).toBe(false);
  });
});

describe("expandPawlsPages", () => {
  test("returns empty array for null/undefined", () => {
    expect(expandPawlsPages(null)).toEqual([]);
    expect(expandPawlsPages(undefined)).toEqual([]);
  });

  test("passes through v1 list unchanged", () => {
    const v1 = [
      {
        page: { width: 612, height: 792, index: 0 },
        tokens: [{ x: 72, y: 720, width: 41, height: 12, text: "Hello" }],
      },
    ];
    expect(expandPawlsPages(v1)).toBe(v1);
  });

  test("expands v2 compact to v1 format", () => {
    const v2 = {
      v: 2,
      p: [
        {
          w: 612,
          h: 792,
          t: [[72, 720, 41, 12, "Hello"]],
        },
      ],
    };

    const result = expandPawlsPages(v2);
    expect(result).toHaveLength(1);
    expect(result[0].page).toEqual({ width: 612, height: 792, index: 0 });
    expect(result[0].tokens).toHaveLength(1);
    expect(result[0].tokens[0]).toEqual({
      x: 72,
      y: 720,
      width: 41,
      height: 12,
      text: "Hello",
    });
  });

  test("expands image tokens with all metadata including base64_data", () => {
    const v2 = {
      v: 2,
      p: [
        {
          w: 612,
          h: 792,
          t: [
            [
              50,
              100,
              200,
              300,
              "",
              {
                p: "path/img.jpg",
                b64: "iVBORw0KGgoAAAANSUhEUg==",
                f: "jpeg",
                ch: "hash123",
                ow: 800,
                oh: 600,
                it: "embedded",
              },
            ],
          ],
        },
      ],
    };

    const result = expandPawlsPages(v2);
    const tok = result[0].tokens[0];
    expect(tok.is_image).toBe(true);
    expect(tok.image_path).toBe("path/img.jpg");
    expect(tok.base64_data).toBe("iVBORw0KGgoAAAANSUhEUg==");
    expect(tok.format).toBe("jpeg");
    expect(tok.content_hash).toBe("hash123");
    expect(tok.original_width).toBe(800);
    expect(tok.original_height).toBe(600);
    expect(tok.image_type).toBe("embedded");
  });

  test("skips malformed tokens", () => {
    const v2 = {
      v: 2,
      p: [
        {
          w: 100,
          h: 100,
          t: [
            [1, 2, 3], // too short
            [72, 720, 41, 12, "valid"],
          ],
        },
      ],
    };

    const result = expandPawlsPages(v2);
    expect(result[0].tokens).toHaveLength(1);
    expect(result[0].tokens[0].text).toBe("valid");
  });

  test("handles multi-page documents with correct index", () => {
    const v2 = {
      v: 2,
      p: [
        { w: 612, h: 792, t: [[10, 20, 30, 40, "page0"]] },
        { w: 800, h: 1200, t: [[50, 60, 70, 80, "page1"]] },
      ],
    };

    const result = expandPawlsPages(v2);
    expect(result).toHaveLength(2);
    expect(result[0].page.index).toBe(0);
    expect(result[1].page.index).toBe(1);
    expect(result[1].page.width).toBe(800);
    expect(result[1].tokens[0].text).toBe("page1");
  });

  test("returns empty array for unrecognized format", () => {
    expect(expandPawlsPages({ random: "data" })).toEqual([]);
  });

  test("handles empty pages", () => {
    const v2 = { v: 2, p: [{ w: 612, h: 792, t: [] }] };
    const result = expandPawlsPages(v2);
    expect(result).toHaveLength(1);
    expect(result[0].tokens).toEqual([]);
  });
});
