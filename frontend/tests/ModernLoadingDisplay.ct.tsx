/**
 * Playwright component tests for ModernLoadingDisplay.
 *
 * Pins the overlay-vs-inline rendering contract — the substantive change in
 * PR #1786 — so a future refactor can't silently revert the mobile coverage
 * fix.
 */
import { test, expect } from "./utils/coverage";
import React from "react";

import { ModernLoadingDisplay } from "../src/components/widgets/ModernLoadingDisplay";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("ModernLoadingDisplay", () => {
  test("default overlay covers the viewport (position: fixed, inset: 0)", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#0f172a",
          color: "#fff",
          padding: 24,
        }}
      >
        <p style={{ marginTop: 0 }}>
          Underlying app chrome — should NOT be visible through the overlay.
        </p>
        <ModernLoadingDisplay />
      </div>
    );

    const statusRegion = page.getByRole("status");
    await expect(statusRegion).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Loading cite")).toBeVisible();

    // The accessibility contract: live region announces busy state.
    await expect(statusRegion).toHaveAttribute("aria-live", "polite");
    await expect(statusRegion).toHaveAttribute("aria-busy", "true");

    // The overlay contract: position: fixed and pinned to all four edges so
    // the underlying app chrome is fully covered.
    const computed = await statusRegion.evaluate((el) => {
      const cs = getComputedStyle(el);
      return {
        position: cs.position,
        top: cs.top,
        left: cs.left,
        right: cs.right,
        bottom: cs.bottom,
      };
    });
    expect(computed.position).toBe("fixed");
    expect(computed.top).toBe("0px");
    expect(computed.left).toBe("0px");
    expect(computed.right).toBe("0px");
    expect(computed.bottom).toBe("0px");

    await docScreenshot(page, "widgets--modern-loading-display--overlay");

    await component.unmount();
  });

  test("inline mode renders in normal flow (position: relative, no overlay)", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <div
        style={{
          width: "480px",
          padding: 24,
          border: "1px solid #94a3b8",
          background: "#f8fafc",
        }}
      >
        <p style={{ marginTop: 0 }}>Panel content above the loader.</p>
        <ModernLoadingDisplay inline message="Loading discussion..." />
        <p style={{ marginBottom: 0 }}>Panel content below the loader.</p>
      </div>
    );

    const statusRegion = page.getByRole("status");
    await expect(statusRegion).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Loading discussion...")).toBeVisible();

    const computed = await statusRegion.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { position: cs.position, width: cs.width };
    });
    expect(computed.position).toBe("relative");

    // Inline mode stays inside its parent — the surrounding panel content
    // must still be visible (not covered by an overlay).
    await expect(
      page.getByText("Panel content above the loader.")
    ).toBeVisible();
    await expect(
      page.getByText("Panel content below the loader.")
    ).toBeVisible();

    await docScreenshot(page, "widgets--modern-loading-display--inline");

    await component.unmount();
  });
});
