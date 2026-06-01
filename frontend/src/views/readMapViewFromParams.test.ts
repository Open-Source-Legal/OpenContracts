import { describe, it, expect } from "vitest";
import { readMapViewFromParams } from "./DiscoverSearchResults";
import {
  MAP_DEFAULT_CENTER,
  MAP_DEFAULT_ZOOM,
  MAP_LAT_PARAM,
  MAP_LNG_PARAM,
  MAP_ZOOM_PARAM,
} from "../assets/configurations/constants";

const params = (entries: Record<string, string>): URLSearchParams =>
  new URLSearchParams(entries);

describe("readMapViewFromParams", () => {
  it("reads a fully-specified viewport from the URL", () => {
    const view = readMapViewFromParams(
      params({
        [MAP_LAT_PARAM]: "40.5",
        [MAP_LNG_PARAM]: "-73.2",
        [MAP_ZOOM_PARAM]: "7",
      })
    );
    expect(view).toEqual({ center: [40.5, -73.2], zoom: 7 });
  });

  it("falls back to defaults when no params are present", () => {
    const view = readMapViewFromParams(params({}));
    expect(view).toEqual({
      center: [...MAP_DEFAULT_CENTER],
      zoom: MAP_DEFAULT_ZOOM,
    });
  });

  it("falls back to defaults when only some params are present", () => {
    const view = readMapViewFromParams(
      params({ [MAP_LAT_PARAM]: "40.5", [MAP_LNG_PARAM]: "-73.2" })
    );
    expect(view).toEqual({
      center: [...MAP_DEFAULT_CENTER],
      zoom: MAP_DEFAULT_ZOOM,
    });
  });

  it("falls back to defaults when a param is non-numeric", () => {
    const view = readMapViewFromParams(
      params({
        [MAP_LAT_PARAM]: "abc",
        [MAP_LNG_PARAM]: "-73.2",
        [MAP_ZOOM_PARAM]: "7",
      })
    );
    expect(view).toEqual({
      center: [...MAP_DEFAULT_CENTER],
      zoom: MAP_DEFAULT_ZOOM,
    });
  });

  it("returns a fresh mutable copy of the default center", () => {
    const view = readMapViewFromParams(params({}));
    expect(view.center).not.toBe(MAP_DEFAULT_CENTER);
    expect(view.center).toEqual([...MAP_DEFAULT_CENTER]);
  });
});
