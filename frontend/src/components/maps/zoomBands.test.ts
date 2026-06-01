import { describe, it, expect } from "vitest";
import { labelTypeForZoom, bboxCenter } from "./zoomBands";
import {
  GEO_LABEL_TYPE_CITY,
  GEO_LABEL_TYPE_COUNTRY,
  GEO_LABEL_TYPE_STATE,
  MAP_ZOOM_CITY_MIN,
  MAP_ZOOM_STATE_MIN,
} from "../../assets/configurations/constants";

describe("labelTypeForZoom", () => {
  it("returns country below the state threshold", () => {
    expect(labelTypeForZoom(0)).toBe(GEO_LABEL_TYPE_COUNTRY);
    expect(labelTypeForZoom(MAP_ZOOM_STATE_MIN - 1)).toBe(
      GEO_LABEL_TYPE_COUNTRY
    );
  });

  it("returns state from the state threshold up to (not incl.) the city threshold", () => {
    expect(labelTypeForZoom(MAP_ZOOM_STATE_MIN)).toBe(GEO_LABEL_TYPE_STATE);
    expect(labelTypeForZoom(MAP_ZOOM_CITY_MIN - 1)).toBe(GEO_LABEL_TYPE_STATE);
  });

  it("returns city at and above the city threshold", () => {
    expect(labelTypeForZoom(MAP_ZOOM_CITY_MIN)).toBe(GEO_LABEL_TYPE_CITY);
    expect(labelTypeForZoom(MAP_ZOOM_CITY_MIN + 5)).toBe(GEO_LABEL_TYPE_CITY);
  });
});

describe("bboxCenter", () => {
  it("averages a normal (non-wrapping) bbox", () => {
    expect(bboxCenter({ south: 0, west: 10, north: 20, east: 30 })).toEqual([
      10, 20,
    ]);
  });

  it("handles an antimeridian-crossing bbox (west > east) → ±180", () => {
    const [lat, lng] = bboxCenter({
      south: -10,
      west: 170,
      north: 10,
      east: -170,
    });
    expect(lat).toBe(0);
    expect(Math.abs(lng)).toBe(180);
  });

  it("handles an asymmetric antimeridian crossing", () => {
    // west=150 / east=-120 spans 90° across the antimeridian; centre ≈ -165.
    const [, lng] = bboxCenter({
      south: 0,
      west: 150,
      north: 0,
      east: -120,
    });
    expect(lng).toBeCloseTo(-165, 6);
  });
});
