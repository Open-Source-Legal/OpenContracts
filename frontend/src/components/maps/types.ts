/**
 * Shared types for the reusable {@link AnnotationMap} component (issue #1820).
 *
 * These mirror the backend `GeographicAnnotationPinType` GraphQL shape
 * (see config/graphql/annotation_queries.py) so the component can be reused by
 * any caller (Discover #1820, Corpus Home #1821) that fetches geographic pins.
 */

import { GeoLabelType } from "../../assets/configurations/constants";

/** A clustered geographic annotation pin, matching the GraphQL pin type. */
export interface GeographicAnnotationPin {
  /** Canonical place name, e.g. "France" / "California". */
  canonicalName: string;
  /**
   * Place granularity as the lowercase literal "country" / "state" / "city"
   * (the value the backend returns — NOT the OC_* annotation-label text).
   */
  labelType: GeoLabelType;
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
  /**
   * Fired when the user activates one of a pin's sample-document links,
   * receiving the document's Relay global id. The map is route-agnostic: the
   * caller resolves the id to a destination (e.g. the canonical document URL),
   * so the same component serves Discover (#1820) and Corpus Home (#1821).
   * Sample-document links render only when this handler is supplied.
   */
  onSelectDocument?: (documentId: string) => void;
  /** Initial map centre [lat, lng]. */
  center?: [number, number];
  /** Initial map zoom. */
  zoom?: number;
  /** CSS height for the map container (Leaflet needs an explicit height). */
  height?: string;
  /** Optional extra class name on the outer wrapper. */
  className?: string;
  /**
   * When true, imperatively frame the map to the bounds of the pin set on first
   * load (the coarsest band present, so the initial paint always shows pins).
   * Opt-in for callers like Corpus Home (#1821) that open on a region rather
   * than the whole world; Discover leaves it off and keeps its mount viewport.
   * `center`/`zoom` are mount-only in react-leaflet, so this is the supported
   * way to (re)frame an already-mounted map.
   */
  fitToPins?: boolean;
  /**
   * Canonical name of a pin to focus (deep-link support, e.g. Corpus Home's
   * `?pin=Paris`). When a pin with this name is present in `pins`, the map
   * selects it (opening the side panel) and flies to it at a zoom that keeps
   * its band visible. Applied once per distinct name, after which user
   * interaction takes over; takes precedence over `fitToPins`. Resolving is
   * deferred until the named pin appears, so it works when `pins` load async.
   */
  focusPinName?: string | null;
}
