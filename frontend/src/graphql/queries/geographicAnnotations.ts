import { gql } from "@apollo/client";
import { GeographicAnnotationPin, MapBBox } from "../../components/maps/types";
import {
  GeoLabelType,
  GEO_LABEL_TYPES,
} from "../../assets/configurations/constants";

/**
 * Geographic annotation map queries (issue #1820).
 *
 * Backed by the resolvers in config/graphql/annotation_queries.py. Only the
 * fields the map needs are selected — pins are deliberately lightweight so the
 * cross-corpus query stays cheap.
 */

// Shared selection of the pin fields the map renders.
export const GEOGRAPHIC_ANNOTATION_PIN_FRAGMENT = gql`
  fragment GeographicAnnotationPinFields on GeographicAnnotationPinType {
    canonicalName
    labelType
    lat
    lng
    documentCount
    sampleDocumentIds
  }
`;

/** Cross-corpus pins for the Discover map (permission-filtered server-side). */
export const GET_GLOBAL_GEOGRAPHIC_ANNOTATIONS = gql`
  query GetGlobalGeographicAnnotations(
    $bbox: BBoxInputType
    $zoom: Float
    $labelTypes: [String]
  ) {
    globalGeographicAnnotations(
      bbox: $bbox
      zoom: $zoom
      labelTypes: $labelTypes
    ) {
      ...GeographicAnnotationPinFields
    }
  }
  ${GEOGRAPHIC_ANNOTATION_PIN_FRAGMENT}
`;

/** Pins for a single corpus (used by Corpus Home, issue #1821). */
export const GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS = gql`
  query GetGeographicAnnotationsForCorpus(
    $corpusId: ID!
    $bbox: BBoxInputType
    $zoom: Float
    $labelTypes: [String]
  ) {
    geographicAnnotationsForCorpus(
      corpusId: $corpusId
      bbox: $bbox
      zoom: $zoom
      labelTypes: $labelTypes
    ) {
      ...GeographicAnnotationPinFields
    }
  }
  ${GEOGRAPHIC_ANNOTATION_PIN_FRAGMENT}
`;

// ---------------------------------------------------------------------------
// Typed query inputs / outputs
// ---------------------------------------------------------------------------
export interface GeographicAnnotationsInput {
  bbox: MapBBox | null;
  zoom: number | null;
  labelTypes: GeoLabelType[];
}

export interface GetGlobalGeographicAnnotationsOutput {
  globalGeographicAnnotations: GeographicAnnotationPin[];
}

export interface GetGeographicAnnotationsForCorpusInput
  extends GeographicAnnotationsInput {
  corpusId: string;
}

export interface GetGeographicAnnotationsForCorpusOutput {
  geographicAnnotationsForCorpus: GeographicAnnotationPin[];
}

/**
 * Canonical initial variables for the per-corpus pins query (#1821).
 *
 * Both the Corpus Home map-toggle count badge and the map view itself issue
 * this exact variable set (whole-corpus: no bbox, all label types, zoom
 * unset). Sharing one helper guarantees the variables match byte-for-byte so
 * the two callers share a single Apollo cache entry — the badge's fetch warms
 * the map, and opening the map costs no extra round-trip. Corpus pin sets are
 * bounded/aggregated, so unlike the global Discover map this query is issued
 * once and not refetched per pan/zoom.
 */
export const corpusGeoInitialVariables = (
  corpusId: string
): GetGeographicAnnotationsForCorpusInput => ({
  corpusId,
  bbox: null,
  zoom: null,
  labelTypes: [...GEO_LABEL_TYPES],
});
