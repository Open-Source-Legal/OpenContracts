/** Client-side zoom-band selection for geographic annotation pins (issue #1820). */
import {
  GeoLabelType,
  GEO_LABEL_TYPE_CITY,
  GEO_LABEL_TYPE_COUNTRY,
  GEO_LABEL_TYPE_STATE,
  MAP_ZOOM_CITY_MIN,
  MAP_ZOOM_STATE_MIN,
} from "../../assets/configurations/constants";
import { MapBBox } from "./types";

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
