/**
 * Shared types for the reusable {@link AnnotationMap} component (issue #1820).
 *
 * These mirror the backend `GeographicAnnotationPinType` GraphQL shape
 * (see config/graphql/annotation_queries.py) so the component can be reused by
 * any caller (Discover #1820, Corpus Home #1821) that fetches geographic pins.
 */

/** A clustered geographic annotation pin, matching the GraphQL pin type. */
export interface GeographicAnnotationPin {
  /** Canonical place name, e.g. "France" / "California". */
  canonicalName: string;
  /**
   * Place granularity as the lowercase literal "country" / "state" / "city"
   * (the value the backend returns — NOT the OC_* annotation-label text).
   */
  labelType: string;
  /** Latitude in WGS84. */
  lat: number;
  /** Longitude in WGS84. */
  lng: number;
  /** Number of distinct documents referencing this place. */
  documentCount: number;
  /** Relay global ids of up to N sample documents (DocumentType). */
  sampleDocumentIds: string[];
}

/** Geographic bounding box in WGS84 decimal degrees. */
export interface MapBBox {
  south: number;
  west: number;
  north: number;
  east: number;
}

/** Props for the reusable {@link AnnotationMap} component. */
export interface AnnotationMapProps {
  /** Pins to render. The map filters them by the current zoom band. */
  pins: GeographicAnnotationPin[];
  /** Whether pin data is currently loading (shows a non-blocking overlay). */
  loading?: boolean;
  /** Fired (after Leaflet moveend/zoomend) with the new viewport. */
  onBoundsChange?: (bbox: MapBBox, zoom: number) => void;
  /** Fired when a pin is selected (click or keyboard). */
  onPinClick?: (pin: GeographicAnnotationPin) => void;
  /** Initial map centre [lat, lng]. */
  center?: [number, number];
  /** Initial map zoom. */
  zoom?: number;
  /** CSS height for the map container (Leaflet needs an explicit height). */
  height?: string;
  /** Optional extra class name on the outer wrapper. */
  className?: string;
}
