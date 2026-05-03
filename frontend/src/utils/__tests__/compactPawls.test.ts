import { describe, test, expect } from "vitest";
import { decodeV2Pawls, isV2WirePawls } from "../compactPawls";

describe("isV2WirePawls", () => {
  test("returns true for valid v2 envelope", () => {
    expect(isV2WirePawls({ v: 2, p: [] })).toBe(true);
  });

  test("returns false for v1 list", () => {
    expect(isV2WirePawls([])).toBe(false);
  });

  test("returns false for wrong version", () => {
    expect(isV2WirePawls({ v: 1, p: [] })).toBe(false);
  });

  test("returns false for null/undefined", () => {
    expect(isV2WirePawls(null)).toBe(false);
    expect(isV2WirePawls(undefined)).toBe(false);
  });

  test("returns false for missing p key", () => {
    expect(isV2WirePawls({ v: 2 })).toBe(false);
  });
});

describe("decodeV2Pawls — null/empty inputs", () => {
  test("returns empty array for null/undefined", () => {
    expect(decodeV2Pawls(null)).toEqual([]);
    expect(decodeV2Pawls(undefined)).toEqual([]);
  });

  test("throws on garbage non-null input", () => {
    expect(() => decodeV2Pawls({ random: "data" })).toThrow(/Invalid PAWLs/);
    expect(() => decodeV2Pawls("hello")).toThrow(/Invalid PAWLs/);
    expect(() => decodeV2Pawls(42)).toThrow(/Invalid PAWLs/);
  });
});

describe("decodeV2Pawls — v2 wire input", () => {
  test("expands v2 compact to canonical CompactPage[]", () => {
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

    const result = decodeV2Pawls(v2);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      index: 0,
      width: 612,
      height: 792,
    });
    expect(result[0].tokens).toHaveLength(1);
    expect(result[0].tokens[0]).toEqual({
      x: 72,
      y: 720,
      width: 41,
      height: 12,
      text: "Hello",
      isImage: false,
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

    const result = decodeV2Pawls(v2);
    const tok = result[0].tokens[0];
    expect(tok.isImage).toBe(true);
    expect(tok.imageMeta).toEqual({
      p: "path/img.jpg",
      b64: "iVBORw0KGgoAAAANSUhEUg==",
      f: "jpeg",
      ch: "hash123",
      ow: 800,
      oh: 600,
      it: "embedded",
    });
  });

  test("skips malformed v2 tokens", () => {
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

    const result = decodeV2Pawls(v2);
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

    const result = decodeV2Pawls(v2);
    expect(result).toHaveLength(2);
    expect(result[0].index).toBe(0);
    expect(result[1].index).toBe(1);
    expect(result[1].width).toBe(800);
    expect(result[1].tokens[0].text).toBe("page1");
  });

  test("handles empty pages", () => {
    const v2 = { v: 2, p: [{ w: 612, h: 792, t: [] }] };
    const result = decodeV2Pawls(v2);
    expect(result).toHaveLength(1);
    expect(result[0].tokens).toEqual([]);
  });
});

describe("decodeV2Pawls — v1 wire input (legacy tolerance)", () => {
  test("decodes v1 wire format into canonical v2-shape objects", () => {
    const v1 = [
      {
        page: { width: 612, height: 792, index: 0 },
        tokens: [{ x: 72, y: 720, width: 41, height: 12, text: "Hello" }],
      },
    ];

    const result = decodeV2Pawls(v1);
    expect(result).toHaveLength(1);
    // Output is v2-canonical: flat width/height, no nested `page` object,
    // tokens carry isImage (camelCase) instead of is_image (snake_case).
    expect(result[0]).toEqual({
      index: 0,
      width: 612,
      height: 792,
      tokens: [
        {
          x: 72,
          y: 720,
          width: 41,
          height: 12,
          text: "Hello",
          isImage: false,
        },
      ],
    });
  });

  test("decodes v1 image tokens by remapping snake_case to imageMeta short keys", () => {
    const v1 = [
      {
        page: { width: 612, height: 792, index: 0 },
        tokens: [
          {
            x: 50,
            y: 100,
            width: 200,
            height: 300,
            text: "",
            is_image: true,
            image_path: "path/img.jpg",
            base64_data: "iVBORw0KGgo=",
            format: "jpeg",
            content_hash: "hash123",
            original_width: 800,
            original_height: 600,
            image_type: "embedded",
          },
        ],
      },
    ];

    const result = decodeV2Pawls(v1);
    const tok = result[0].tokens[0];
    expect(tok.isImage).toBe(true);
    expect(tok.imageMeta).toEqual({
      p: "path/img.jpg",
      b64: "iVBORw0KGgo=",
      f: "jpeg",
      ch: "hash123",
      ow: 800,
      oh: 600,
      it: "embedded",
    });
  });

  test("v1 empty array decodes to empty result", () => {
    expect(decodeV2Pawls([])).toEqual([]);
  });

  test("v1 page falls back to array index when index field missing", () => {
    const v1 = [
      { page: { width: 612, height: 792 }, tokens: [] },
      { page: { width: 612, height: 792 }, tokens: [] },
    ];
    const result = decodeV2Pawls(v1);
    expect(result[0].index).toBe(0);
    expect(result[1].index).toBe(1);
  });

  test("v1 page rejects non-object entries", () => {
    expect(() => decodeV2Pawls(["not an object"])).toThrow(
      /Invalid v1 PAWLs page/
    );
    expect(() => decodeV2Pawls([null])).toThrow(/Invalid v1 PAWLs page/);
  });

  test("v1 page tolerates missing/non-numeric width/height with 0 fallback", () => {
    const v1 = [
      // No `page` key at all -> fallback to {width:0, height:0}
      { tokens: [] },
      // `page` exists but width/height are non-numeric -> 0 fallback
      { page: { width: "wide", height: null }, tokens: [] },
    ];
    const result = decodeV2Pawls(v1);
    expect(result[0]).toMatchObject({ index: 0, width: 0, height: 0 });
    expect(result[1]).toMatchObject({ index: 1, width: 0, height: 0 });
  });

  test("v1 token with non-object entries are skipped", () => {
    const v1 = [
      {
        page: { width: 100, height: 100 },
        tokens: [
          // Skipped - not an object
          "garbage",
          null,
          // Skipped - missing required numeric fields
          { x: "wrong", y: 1, width: 1, height: 1, text: "" },
          { x: 1 },
          // Kept
          { x: 1, y: 2, width: 3, height: 4, text: "Real" },
        ],
      },
    ];
    const result = decodeV2Pawls(v1);
    expect(result[0].tokens).toHaveLength(1);
    expect(result[0].tokens[0].text).toBe("Real");
  });

  test("v1 token with non-string text falls back to empty string", () => {
    const v1 = [
      {
        page: { width: 100, height: 100 },
        tokens: [{ x: 1, y: 2, width: 3, height: 4 }],
      },
    ];
    const result = decodeV2Pawls(v1);
    expect(result[0].tokens[0].text).toBe("");
    expect(result[0].tokens[0].isImage).toBe(false);
  });

  test("v1 image token with no metadata fields produces empty imageMeta", () => {
    const v1 = [
      {
        page: { width: 100, height: 100 },
        tokens: [
          {
            x: 1,
            y: 2,
            width: 3,
            height: 4,
            text: "",
            is_image: true,
            // no image_path / format / etc.
          },
        ],
      },
    ];
    const result = decodeV2Pawls(v1);
    expect(result[0].tokens[0].isImage).toBe(true);
    expect(result[0].tokens[0].imageMeta).toEqual({});
  });

  test("v1 page with non-array tokens yields empty token list", () => {
    const v1 = [
      { page: { width: 100, height: 100 }, tokens: undefined },
      { page: { width: 100, height: 100 }, tokens: "not an array" },
    ];
    const result = decodeV2Pawls(v1);
    expect(result[0].tokens).toEqual([]);
    expect(result[1].tokens).toEqual([]);
  });
});

describe("decodeV2Pawls — v2 wire edge cases", () => {
  test("v2 page with non-array tokens yields empty token list", () => {
    const v2 = { v: 2, p: [{ w: 100, h: 100 }] }; // no `t`
    const result = decodeV2Pawls(v2);
    expect(result[0].tokens).toEqual([]);
  });

  test("v2 page falls back to width/height 0 when w/h missing", () => {
    const v2 = { v: 2, p: [{ t: [] }] };
    const result = decodeV2Pawls(v2);
    expect(result[0]).toMatchObject({ index: 0, width: 0, height: 0 });
  });

  test("v2 token with non-array entry is skipped", () => {
    const v2 = {
      v: 2,
      p: [
        {
          w: 100,
          h: 100,
          t: ["garbage", [1, 2, 3, 4, "ok"]],
        },
      ],
    };
    const result = decodeV2Pawls(v2);
    expect(result[0].tokens).toHaveLength(1);
    expect(result[0].tokens[0].text).toBe("ok");
  });
});
