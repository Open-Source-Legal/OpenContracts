import { describe, it, expect } from "vitest";
import {
  isValidHexColor,
  normalizeHexColor,
  hexToRgb,
  hexToRgba,
  computeAnnotationBoxShadow,
  blendColors,
} from "../colorUtils";

describe("colorUtils", () => {
  describe("isValidHexColor", () => {
    it("accepts 3-digit hex with or without hash", () => {
      expect(isValidHexColor("#fff")).toBe(true);
      expect(isValidHexColor("abc")).toBe(true);
    });

    it("accepts 6-digit hex with or without hash", () => {
      expect(isValidHexColor("#FF0000")).toBe(true);
      expect(isValidHexColor("ff00aa")).toBe(true);
    });

    it("rejects invalid strings", () => {
      expect(isValidHexColor("invalid")).toBe(false);
      expect(isValidHexColor("#gggggg")).toBe(false);
      expect(isValidHexColor("")).toBe(false);
      expect(isValidHexColor("#ff")).toBe(false);
      expect(isValidHexColor("#fffff")).toBe(false);
    });
  });

  describe("normalizeHexColor", () => {
    it("expands 3-digit to 6-digit", () => {
      expect(normalizeHexColor("#abc")).toBe("#aabbcc");
      expect(normalizeHexColor("abc")).toBe("#aabbcc");
    });

    it("passes through 6-digit unchanged (with hash prefix)", () => {
      expect(normalizeHexColor("#FF0000")).toBe("#FF0000");
      expect(normalizeHexColor("FF0000")).toBe("#FF0000");
    });
  });

  describe("hexToRgb", () => {
    it("parses 6-digit hex", () => {
      expect(hexToRgb("#FF0000")).toEqual({ r: 255, g: 0, b: 0 });
      expect(hexToRgb("00ff00")).toEqual({ r: 0, g: 255, b: 0 });
    });

    it("expands and parses 3-digit hex", () => {
      expect(hexToRgb("#F00")).toEqual({ r: 255, g: 0, b: 0 });
      expect(hexToRgb("0f0")).toEqual({ r: 0, g: 255, b: 0 });
    });
  });

  describe("hexToRgba", () => {
    it("builds rgba from valid hex", () => {
      expect(hexToRgba("#FF0000", 0.5)).toBe("rgba(255, 0, 0, 0.5)");
      expect(hexToRgba("#F00", 1)).toBe("rgba(255, 0, 0, 1)");
    });

    it("falls back to default blue when hex is null/undefined", () => {
      expect(hexToRgba(null, 0.5)).toBe("rgba(74, 144, 226, 0.5)");
      expect(hexToRgba(undefined, 0.25)).toBe("rgba(74, 144, 226, 0.25)");
    });

    it("falls back when hex is invalid", () => {
      expect(hexToRgba("not-a-color", 0.5)).toBe("rgba(74, 144, 226, 0.5)");
    });

    it("honours custom fallback color", () => {
      expect(hexToRgba(null, 1, { r: 1, g: 2, b: 3 })).toBe("rgba(1, 2, 3, 1)");
    });
  });

  describe("computeAnnotationBoxShadow", () => {
    it("produces three shadow layers for unselected", () => {
      const shadow = computeAnnotationBoxShadow(255, 0, 0, false);
      expect((shadow.match(/rgba\(/g) ?? []).length).toBe(3);
      expect(shadow).toContain("rgba(255, 0, 0");
      expect(shadow).toContain("inset");
    });

    it("produces three shadow layers for selected", () => {
      const shadow = computeAnnotationBoxShadow(0, 128, 255, true);
      expect((shadow.match(/rgba\(/g) ?? []).length).toBe(3);
      expect(shadow).toContain("rgba(0, 128, 255");
    });

    it("differs between selected and unselected states", () => {
      const unselected = computeAnnotationBoxShadow(10, 20, 30, false);
      const selected = computeAnnotationBoxShadow(10, 20, 30, true);
      expect(unselected).not.toBe(selected);
    });
  });

  describe("blendColors", () => {
    it("returns black for empty array", () => {
      expect(blendColors([])).toBe("rgb(0, 0, 0)");
    });

    it("returns the single color unchanged for single-color input", () => {
      expect(blendColors(["#abcdef"])).toBe("#abcdef");
    });

    it("averages two colors", () => {
      expect(blendColors(["#FF0000", "#0000FF"])).toBe("rgb(128, 0, 128)");
    });

    it("averages three colors, rounding", () => {
      expect(blendColors(["#FF0000", "#00FF00", "#0000FF"])).toBe(
        "rgb(85, 85, 85)"
      );
    });
  });
});
