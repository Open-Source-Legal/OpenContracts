/**
 * Client-side zoom-band selection for geographic annotation pins (issue #1820).
 *
 * The backend returns pins for *all* label types; the client shows exactly one
 * band based on the current Leaflet zoom so the map stays readable:
 *   - country when zoomed out
 *   - state   at medium zoom
 *   - city    when zoomed in
 *
 * Thresholds live in constants.ts (no magic numbers).
 */
import {
  GEO_LABEL_TYPE_CITY,
  GEO_LABEL_TYPE_COUNTRY,
  GEO_LABEL_TYPE_STATE,
  MAP_ZOOM_CITY_MIN,
  MAP_ZOOM_STATE_MIN,
} from "../../assets/configurations/constants";

/**
 * Return the geographic label type to display at the given Leaflet zoom.
 * The returned literal matches the backend pin `labelType` values.
 */
export const labelTypeForZoom = (zoom: number): string => {
  if (zoom >= MAP_ZOOM_CITY_MIN) {
    return GEO_LABEL_TYPE_CITY;
  }
  if (zoom >= MAP_ZOOM_STATE_MIN) {
    return GEO_LABEL_TYPE_STATE;
  }
  return GEO_LABEL_TYPE_COUNTRY;
};
