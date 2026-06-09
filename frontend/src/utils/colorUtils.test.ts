import { describe, it, expect } from "vitest";

import { safeCssColor } from "./colorUtils";

describe("safeCssColor", () => {
  const FALLBACK = "#4A90E2";

  it("passes through valid hex colors (3/6/8 digit)", () => {
    expect(safeCssColor("#fff", FALLBACK)).toBe("#fff");
    expect(safeCssColor("#FF0000", FALLBACK)).toBe("#FF0000");
    expect(safeCssColor("#11223344", FALLBACK)).toBe("#11223344");
  });

  it("passes through plain named colors", () => {
    expect(safeCssColor("red", FALLBACK)).toBe("red");
    expect(safeCssColor("DarkSlateGray", FALLBACK)).toBe("DarkSlateGray");
  });

  it("trims surrounding whitespace before validating", () => {
    expect(safeCssColor("  #abc  ", FALLBACK)).toBe("#abc");
  });

  it("falls back for null/undefined/empty input", () => {
    expect(safeCssColor(null, FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor(undefined, FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("", FALLBACK)).toBe(FALLBACK);
  });

  it("rejects values that could break out of the CSS property", () => {
    expect(safeCssColor("red; } body { background: url(x)", FALLBACK)).toBe(
      FALLBACK
    );
    expect(safeCssColor("#fff; } *{x:y}", FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("url(javascript:alert(1))", FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("rgb(0,0,0)", FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("#xyz", FALLBACK)).toBe(FALLBACK);
  });
});
