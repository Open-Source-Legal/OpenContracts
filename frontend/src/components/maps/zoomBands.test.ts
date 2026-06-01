import { describe, it, expect } from "vitest";
import {
  bandZoomRange,
  bboxCenter,
  coarsestBand,
  labelTypeForZoom,
} from "./zoomBands";
import type { GeographicAnnotationPin } from "./types";
import {
  GEO_LABEL_TYPE_CITY,
  GEO_LABEL_TYPE_COUNTRY,
  GEO_LABEL_TYPE_STATE,
  MAP_FIT_MAX_ZOOM,
  MAP_MIN_ZOOM,
  MAP_ZOOM_CITY_MIN,
  MAP_ZOOM_STATE_MIN,
} from "../../assets/configurations/constants";

const pin = (
  labelType: GeographicAnnotationPin["labelType"],
  canonicalName = labelType
): GeographicAnnotationPin => ({
  canonicalName,
  labelType,
  lat: 0,
  lng: 0,
  documentCount: 1,
  sampleDocumentIds: [],
});

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

describe("bandZoomRange", () => {
  it("maps each band to the expected inclusive [min, max]", () => {
    expect(bandZoomRange(GEO_LABEL_TYPE_COUNTRY)).toEqual([
      MAP_MIN_ZOOM,
      MAP_ZOOM_STATE_MIN - 1,
    ]);
    expect(bandZoomRange(GEO_LABEL_TYPE_STATE)).toEqual([
      MAP_ZOOM_STATE_MIN,
      MAP_ZOOM_CITY_MIN - 1,
    ]);
    expect(bandZoomRange(GEO_LABEL_TYPE_CITY)).toEqual([
      MAP_ZOOM_CITY_MIN,
      MAP_FIT_MAX_ZOOM,
    ]);
  });

  it("stays inside its own band for every zoom in the range (focus/fit invariant)", () => {
    for (const band of [
      GEO_LABEL_TYPE_COUNTRY,
      GEO_LABEL_TYPE_STATE,
      GEO_LABEL_TYPE_CITY,
    ] as const) {
      const [min, max] = bandZoomRange(band);
      for (let z = min; z <= max; z++) {
        expect(labelTypeForZoom(z)).toBe(band);
      }
    }
  });
});

describe("coarsestBand", () => {
  it("returns null for an empty pin set", () => {
    expect(coarsestBand([])).toBeNull();
  });

  it("prefers country, then state, then city", () => {
    expect(coarsestBand([pin("city"), pin("state"), pin("country")])).toBe(
      GEO_LABEL_TYPE_COUNTRY
    );
    expect(coarsestBand([pin("city"), pin("state")])).toBe(
      GEO_LABEL_TYPE_STATE
    );
    expect(coarsestBand([pin("city")])).toBe(GEO_LABEL_TYPE_CITY);
  });
});
