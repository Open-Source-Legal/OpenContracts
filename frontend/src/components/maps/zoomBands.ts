/** Client-side zoom-band selection for geographic annotation pins (issue #1820). */
import {
  GeoLabelType,
  GEO_LABEL_TYPE_CITY,
  GEO_LABEL_TYPE_COUNTRY,
  GEO_LABEL_TYPE_STATE,
  MAP_ZOOM_CITY_MIN,
  MAP_ZOOM_STATE_MIN,
} from "../../assets/configurations/constants";

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
