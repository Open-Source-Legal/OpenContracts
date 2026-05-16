/**
 * Unit tests for chatUtils helpers extracted during the ChatTray decomposition
 * (PR #1639). Covers the new `adjustTextareaHeight` DOM helper plus the
 * existing `calculateMessageStats` / `getMessageCountColor` utilities that
 * lacked direct coverage.
 */

import { describe, it, expect } from "vitest";
import {
  adjustTextareaHeight,
  calculateMessageStats,
  getMessageCountColor,
} from "../chatUtils";
import { MESSAGE_COUNT_COLORS } from "../../../../../assets/configurations/constants";

describe("adjustTextareaHeight", () => {
  it("no-ops when the textarea is null (typical ref-not-mounted case)", () => {
    // Should not throw.
    expect(() => adjustTextareaHeight(null)).not.toThrow();
  });

  it("clamps scrollHeight to the default 200px cap", () => {
    const textarea = document.createElement("textarea");
    // jsdom does not lay out, so scrollHeight is 0 by default. Stub it.
    Object.defineProperty(textarea, "scrollHeight", {
      configurable: true,
      get: () => 350,
    });

    adjustTextareaHeight(textarea);

    expect(textarea.style.height).toBe("200px");
  });

  it("uses the actual scrollHeight when below the cap", () => {
    const textarea = document.createElement("textarea");
    Object.defineProperty(textarea, "scrollHeight", {
      configurable: true,
      get: () => 64,
    });

    adjustTextareaHeight(textarea);

    expect(textarea.style.height).toBe("64px");
  });

  it("honours a custom maxHeight override", () => {
    const textarea = document.createElement("textarea");
    Object.defineProperty(textarea, "scrollHeight", {
      configurable: true,
      get: () => 999,
    });

    adjustTextareaHeight(textarea, 100);

    expect(textarea.style.height).toBe("100px");
  });
});

describe("calculateMessageStats", () => {
  it("returns zeros for an empty conversation list", () => {
    expect(calculateMessageStats([])).toEqual({
      max: 0,
      min: 0,
      mean: 0,
      stdDev: 0,
    });
  });

  it("treats missing chatMessages or totalCount as zero", () => {
    const stats = calculateMessageStats([
      { chatMessages: { totalCount: 4 } },
      { chatMessages: null },
      {},
    ]);

    expect(stats.max).toBe(4);
    expect(stats.min).toBe(0);
    expect(stats.mean).toBeCloseTo(4 / 3, 5);
    expect(stats.stdDev).toBeGreaterThan(0);
  });

  it("computes max/min/mean/stdDev correctly for a known set", () => {
    // Values: 2, 4, 4, 4, 5, 5, 7, 9 → mean 5, stdDev 2
    const stats = calculateMessageStats(
      [2, 4, 4, 4, 5, 5, 7, 9].map((n) => ({ chatMessages: { totalCount: n } }))
    );
    expect(stats.max).toBe(9);
    expect(stats.min).toBe(2);
    expect(stats.mean).toBeCloseTo(5, 5);
    expect(stats.stdDev).toBeCloseTo(2, 5);
  });
});

describe("getMessageCountColor", () => {
  const baseStats = { max: 10, min: 0, mean: 5, stdDev: 2 };

  it("returns the zero-state style when count is 0", () => {
    const style = getMessageCountColor(0, baseStats);
    expect(style.background).toContain(
      MESSAGE_COUNT_COLORS.ZERO_GRADIENT_START
    );
    expect(style.background).toContain(MESSAGE_COUNT_COLORS.ZERO_GRADIENT_END);
    expect(style.opacity).toBe(MESSAGE_COUNT_COLORS.ZERO_OPACITY);
    expect(style.textColor).toBe(MESSAGE_COUNT_COLORS.ZERO_TEXT);
  });

  it("falls back to stdDev=1 when stats.stdDev is 0 (single-conv corpus)", () => {
    const flatStats = { max: 5, min: 5, mean: 5, stdDev: 0 };
    // Should not throw / divide by zero.
    const style = getMessageCountColor(5, flatStats);
    expect(style.background).toContain("linear-gradient");
    expect(style.opacity).toBeGreaterThan(0);
  });

  it("returns the light text variant for high-intensity scores", () => {
    // count well above mean → intensity > threshold → LIGHT_TEXT
    const style = getMessageCountColor(50, baseStats);
    expect(style.textColor).toBe(MESSAGE_COUNT_COLORS.LIGHT_TEXT);
  });

  it("returns the dark text variant for low-intensity scores", () => {
    // count well below mean → intensity < threshold → DARK_TEXT
    const style = getMessageCountColor(1, baseStats);
    expect(style.textColor).toBe(MESSAGE_COUNT_COLORS.DARK_TEXT);
  });
});
