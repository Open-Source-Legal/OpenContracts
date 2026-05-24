import { describe, expect, it } from "vitest";

import {
  FIT_WIDTH_MARGIN,
  ZOOM_MAX,
  ZOOM_MIN,
} from "../../assets/configurations/constants";
import { computeFitToWidthZoom } from "../pdfZoom";

describe("computeFitToWidthZoom", () => {
  it("returns (containerWidth - margin) / pageWidth for the typical case", () => {
    // 1280px container around a 612pt letter page → (1280-16)/612 ≈ 2.0653
    const zoom = computeFitToWidthZoom(612, 1280);
    expect(zoom).toBeCloseTo((1280 - FIT_WIDTH_MARGIN) / 612, 5);
  });

  it("reserves FIT_WIDTH_MARGIN so the rendered page is narrower than the container", () => {
    const containerWidth = 1440;
    const pageWidth = 612;
    const zoom = computeFitToWidthZoom(pageWidth, containerWidth);
    expect(zoom).not.toBeNull();
    // The rendered width must fit strictly inside the container with the margin
    // budget left over — this is what prevents horizontal overflow / horizontal
    // scrollbars at narrower laptop viewports (issue #1736).
    expect(zoom! * pageWidth).toBeLessThanOrEqual(
      containerWidth - FIT_WIDTH_MARGIN + 1e-6
    );
    expect(zoom! * pageWidth).toBeLessThan(containerWidth);
  });

  it("clamps to ZOOM_MAX for very large containers", () => {
    // Container 100x wider than the page would compute >100; cap at ZOOM_MAX.
    const zoom = computeFitToWidthZoom(612, 612 * 100);
    expect(zoom).toBe(ZOOM_MAX);
  });

  it("clamps to ZOOM_MIN for very narrow containers", () => {
    // Container narrower than the page at scale=ZOOM_MIN — should clamp up,
    // not return a sub-ZOOM_MIN value.
    const zoom = computeFitToWidthZoom(2000, 100);
    expect(zoom).toBe(ZOOM_MIN);
  });

  it("returns null when either dimension is non-positive (geometry not ready)", () => {
    expect(computeFitToWidthZoom(0, 1280)).toBeNull();
    expect(computeFitToWidthZoom(612, 0)).toBeNull();
    expect(computeFitToWidthZoom(-1, 1280)).toBeNull();
    expect(computeFitToWidthZoom(612, -1)).toBeNull();
  });

  it.each([
    { viewport: 1440, expectedZoom: (1440 - FIT_WIDTH_MARGIN) / 612 },
    { viewport: 1280, expectedZoom: (1280 - FIT_WIDTH_MARGIN) / 612 },
    { viewport: 1024, expectedZoom: (1024 - FIT_WIDTH_MARGIN) / 612 },
  ])(
    "fits a 612pt letter page within a $viewport px container with no overflow",
    ({ viewport, expectedZoom }) => {
      const zoom = computeFitToWidthZoom(612, viewport);
      expect(zoom).toBeCloseTo(expectedZoom, 5);
      // The rendered page width is strictly less than the container width —
      // the test that pins the issue #1736 acceptance criterion.
      expect(zoom! * 612).toBeLessThan(viewport);
    }
  );
});
