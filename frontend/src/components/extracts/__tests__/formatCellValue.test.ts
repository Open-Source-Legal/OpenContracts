import { describe, it, expect } from "vitest";
import {
  formatCellValue,
  truncateAtCodePoint,
} from "../../../utils/formatters";

describe("truncateAtCodePoint()", () => {
  it("returns the string unchanged when within limit", () => {
    expect(truncateAtCodePoint("hello", 10)).toBe("hello");
  });

  it("truncates at code-point boundary with ellipsis", () => {
    const result = truncateAtCodePoint("a".repeat(150), 100);
    expect(result.endsWith("\u2026")).toBe(true);
    expect(Array.from(result).length).toBe(101);
  });

  it("handles emoji without splitting surrogate pairs", () => {
    const emojis = "\u{1F600}".repeat(105);
    const result = truncateAtCodePoint(emojis, 100);
    expect(result).not.toContain("\uFFFD");
    expect(result.endsWith("\u2026")).toBe(true);
    expect(Array.from(result).length).toBe(101);
  });

  it("returns unchanged when UTF-16 length exceeds limit but code-point count does not", () => {
    // 50 emoji = 50 code points but 100 UTF-16 code units
    const emojis = "\u{1F600}".repeat(50);
    expect(emojis.length).toBeGreaterThan(50);
    expect(Array.from(emojis).length).toBe(50);
    expect(truncateAtCodePoint(emojis, 50)).toBe(emojis);
  });
});

describe("formatCellValue()", () => {
  it("returns em-dash for null", () => {
    expect(formatCellValue(null)).toBe("\u2014");
  });

  it("returns em-dash for undefined", () => {
    expect(formatCellValue(undefined)).toBe("\u2014");
  });

  it('returns "Yes" for true', () => {
    expect(formatCellValue(true)).toBe("Yes");
  });

  it('returns "No" for false', () => {
    expect(formatCellValue(false)).toBe("No");
  });

  it("converts number to string", () => {
    expect(formatCellValue(42)).toBe("42");
    expect(formatCellValue(0)).toBe("0");
  });

  it("passes through short strings", () => {
    expect(formatCellValue("hello")).toBe("hello");
  });

  it("returns JSON for short objects (fast path)", () => {
    const obj = { key: "value" };
    expect(formatCellValue(obj)).toBe('{"key":"value"}');
  });

  it("truncates long JSON at code-point boundary with ellipsis", () => {
    // Build an object whose JSON representation exceeds 100 chars
    const longValue = "x".repeat(120);
    const obj = { data: longValue };
    const result = formatCellValue(obj);
    // Should end with ellipsis and be at most 101 chars (100 code points + ellipsis)
    expect(result.endsWith("\u2026")).toBe(true);
    const codePoints = Array.from(result);
    // 100 code points from the slice + 1 ellipsis = 101
    expect(codePoints.length).toBe(101);
  });

  it("handles emoji in long objects without splitting surrogate pairs", () => {
    // Each emoji is 1 code point but 2 UTF-16 code units (surrogate pair).
    // JSON wrapper `{"e":"..."}` adds 8 code points, so 95 emoji = 103 code points > 100.
    const emojis = "\u{1F600}".repeat(95);
    const obj = { e: emojis };
    const result = formatCellValue(obj);
    // Should truncate cleanly without U+FFFD replacement characters
    expect(result).not.toContain("\uFFFD");
    expect(result.endsWith("\u2026")).toBe(true);
    const codePoints = Array.from(result);
    expect(codePoints.length).toBe(101);
  });

  it("truncates long raw strings at code-point boundary with ellipsis", () => {
    const longString = "a".repeat(150);
    const result = formatCellValue(longString);
    expect(result.endsWith("\u2026")).toBe(true);
    const codePoints = Array.from(result);
    expect(codePoints.length).toBe(101);
  });

  it("handles emoji in long raw strings without splitting surrogate pairs", () => {
    const emojis = "\u{1F600}".repeat(105);
    const result = formatCellValue(emojis);
    expect(result).not.toContain("\uFFFD");
    expect(result.endsWith("\u2026")).toBe(true);
    const codePoints = Array.from(result);
    expect(codePoints.length).toBe(101);
  });

  it("does not truncate object whose JSON has >100 UTF-16 units but <=100 code points", () => {
    // Build a string of 48 emoji: JSON = {"e":"<48 emoji>"} = 7 wrapper chars + 48 code points = 55 code points
    // But 7 + 48*2 = 103 UTF-16 units (exceeds 100 in .length but not in code points)
    const emojis = "\u{1F600}".repeat(48);
    const obj = { e: emojis };
    const json = JSON.stringify(obj);
    // Verify our premise: UTF-16 length > 100 but code point count <= 100
    expect(json.length).toBeGreaterThan(100);
    expect(Array.from(json).length).toBeLessThanOrEqual(100);
    const result = formatCellValue(obj);
    // Should return the full JSON without truncation
    expect(result).toBe(json);
    expect(result.endsWith("\u2026")).toBe(false);
  });
});
