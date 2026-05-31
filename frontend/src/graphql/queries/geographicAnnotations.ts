import { gql } from "@apollo/client";
import { GeographicAnnotationPin, MapBBox } from "../../components/maps/types";

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
  labelTypes: string[];
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
