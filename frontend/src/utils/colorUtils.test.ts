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

  it("accepts rgb/rgba/hsl/hsla functional notation with numeric bodies", () => {
    // Existing annotation labels may store colors in functional notation;
    // these are safe to interpolate as long as the parens contain only
    // numerics and separators (no characters that could break out).
    expect(safeCssColor("rgb(0,0,0)", FALLBACK)).toBe("rgb(0,0,0)");
    expect(safeCssColor("rgb(255, 0, 0)", FALLBACK)).toBe("rgb(255, 0, 0)");
    expect(safeCssColor("rgba(0, 0, 0, 0.5)", FALLBACK)).toBe(
      "rgba(0, 0, 0, 0.5)"
    );
    expect(safeCssColor("rgba(0,0,0,.5)", FALLBACK)).toBe("rgba(0,0,0,.5)");
    expect(safeCssColor("hsl(210, 50%, 40%)", FALLBACK)).toBe(
      "hsl(210, 50%, 40%)"
    );
    expect(safeCssColor("hsla(210, 50%, 40%, 0.8)", FALLBACK)).toBe(
      "hsla(210, 50%, 40%, 0.8)"
    );
    // Modern slash-alpha syntax uses only allowed characters.
    expect(safeCssColor("rgb(255 0 0 / 50%)", FALLBACK)).toBe(
      "rgb(255 0 0 / 50%)"
    );
  });

  it("rejects values that could break out of the CSS property", () => {
    expect(safeCssColor("red; } body { background: url(x)", FALLBACK)).toBe(
      FALLBACK
    );
    expect(safeCssColor("#fff; } *{x:y}", FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("url(javascript:alert(1))", FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("#xyz", FALLBACK)).toBe(FALLBACK);
    // Functional-looking but carrying an injection payload — the strict
    // character class inside the parens rejects letters, ``;`` and ``{``.
    expect(safeCssColor("rgb(1); evil", FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("rgb(0,0,0); } *{x:y}", FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("expression(alert(1))", FALLBACK)).toBe(FALLBACK);
    expect(safeCssColor("rgb(url(x))", FALLBACK)).toBe(FALLBACK);
  });
});
