import React from "react";
import { test, expect } from "./utils/coverage";
import { SelectionInfo } from "../src/components/annotator/display/components/Containers";
import { docScreenshot } from "./utils/docScreenshot";

/**
 * Regression coverage for the white-line artifact fix.
 *
 * `SelectionInfo` is the absolutely-positioned annotation label "tab" that sits
 * just above the top edge of a highlight and spans the full annotation width.
 * When the bounding box is hidden (`$showBoundingBox === false`) its background
 * must be fully transparent. Previously it fell back to an opaque white
 * (`rgba(255, 255, 255, 0.9)`), painting a full-width white bar across the top
 * of every highlight even when labels were turned off.
 */
test.describe("SelectionInfo background", () => {
  const bounds = { left: 0, right: 240 };
  const color = "rgb(120, 80, 200)";

  test("is transparent when the bounding box is hidden", async ({
    mount,
    page,
  }) => {
    await mount(
      <div style={{ position: "relative", marginTop: 80, marginLeft: 40 }}>
        <SelectionInfo
          data-testid="selection-info"
          $bounds={bounds}
          $color={color}
          $showBoundingBox={false}
        >
          label
        </SelectionInfo>
      </div>
    );

    const el = page.getByTestId("selection-info");
    await expect(el).toBeVisible();

    // The fix: transparent fallback, not opaque white, so no white bar shows.
    const background = await el.evaluate(
      (node) => getComputedStyle(node).backgroundColor
    );
    expect(background).toBe("rgba(0, 0, 0, 0)");

    await docScreenshot(page, "annotator--selection-info--bounding-box-hidden");
  });

  test("uses the annotation color when the bounding box is shown", async ({
    mount,
    page,
  }) => {
    await mount(
      <div style={{ position: "relative", marginTop: 80, marginLeft: 40 }}>
        <SelectionInfo
          data-testid="selection-info"
          $bounds={bounds}
          $color={color}
          $showBoundingBox={true}
        >
          label
        </SelectionInfo>
      </div>
    );

    const el = page.getByTestId("selection-info");
    await expect(el).toBeVisible();

    const background = await el.evaluate(
      (node) => getComputedStyle(node).backgroundColor
    );
    expect(background).toBe(color);

    await docScreenshot(page, "annotator--selection-info--bounding-box-shown");
  });
});
