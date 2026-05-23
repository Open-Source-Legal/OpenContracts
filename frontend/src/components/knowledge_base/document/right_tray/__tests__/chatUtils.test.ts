/**
 * Unit tests for chatUtils helpers extracted during the ChatTray decomposition
 * (PR #1639). Covers the `adjustTextareaHeight` DOM helper.
 */

import { describe, it, expect } from "vitest";
import { adjustTextareaHeight } from "../chatUtils";

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
