/** Client-side zoom-band selection for geographic annotation pins (issue #1820). */
import {
  GeoLabelType,
  GEO_LABEL_TYPE_CITY,
  GEO_LABEL_TYPE_COUNTRY,
  GEO_LABEL_TYPE_STATE,
  MAP_FIT_MAX_ZOOM,
  MAP_MIN_ZOOM,
  MAP_ZOOM_CITY_MIN,
  MAP_ZOOM_STATE_MIN,
} from "../../assets/configurations/constants";
import { GeographicAnnotationPin, MapBBox } from "./types";

// Show one band per zoom (country out → state mid → city in) so the map stays readable.
export const labelTypeForZoom = (zoom: number): GeoLabelType => {
  if (zoom >= MAP_ZOOM_CITY_MIN) {
    return GEO_LABEL_TYPE_CITY;
  }
  if (zoom >= MAP_ZOOM_STATE_MIN) {
    return GEO_LABEL_TYPE_STATE;
  }
  return GEO_LABEL_TYPE_COUNTRY;
};

// Centre of a bbox as [lat, lng]. The longitude midpoint must handle
// antimeridian-crossing viewports (west > east, e.g. west=170/east=-170 whose
// true centre is ±180); a plain average would yield 0 (the prime meridian).
export const bboxCenter = (bbox: MapBBox): [number, number] => {
  const lat = (bbox.south + bbox.north) / 2;
  const lng =
    bbox.west <= bbox.east
      ? (bbox.west + bbox.east) / 2
      : (((bbox.west + bbox.east + 360) / 2 + 180) % 360) - 180;
  return [lat, lng];
};

// Inclusive [min, max] zoom within which a band's pins are the ones shown by
// labelTypeForZoom. The corpus map's auto-fit/focus (#1821) clamp into this so
// the framed zoom always keeps the intended band visible; the open-ended city
// band is capped at MAP_FIT_MAX_ZOOM so a single city doesn't zoom to street
// level. The state/country ceilings are one below the next band's floor.
export const bandZoomRange = (band: GeoLabelType): [number, number] => {
  if (band === GEO_LABEL_TYPE_CITY) {
    return [MAP_ZOOM_CITY_MIN, MAP_FIT_MAX_ZOOM];
  }
  if (band === GEO_LABEL_TYPE_STATE) {
    return [MAP_ZOOM_STATE_MIN, MAP_ZOOM_CITY_MIN - 1];
  }
  return [MAP_MIN_ZOOM, MAP_ZOOM_STATE_MIN - 1];
};

// The coarsest band present in a pin set (country → state → city), or null when
// empty. Auto-fit frames this band so the first paint always shows pins even
// when finer bands would be empty at the fitted zoom.
export const coarsestBand = (
  pins: GeographicAnnotationPin[]
): GeoLabelType | null => {
  if (pins.some((pin) => pin.labelType === GEO_LABEL_TYPE_COUNTRY)) {
    return GEO_LABEL_TYPE_COUNTRY;
  }
  if (pins.some((pin) => pin.labelType === GEO_LABEL_TYPE_STATE)) {
    return GEO_LABEL_TYPE_STATE;
  }
  if (pins.some((pin) => pin.labelType === GEO_LABEL_TYPE_CITY)) {
    return GEO_LABEL_TYPE_CITY;
  }
  return null;
};
