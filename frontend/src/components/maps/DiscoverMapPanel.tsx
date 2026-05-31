import React, { useCallback, useMemo, useState } from "react";
import { useLazyQuery, useQuery } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { useDebouncedCallback } from "use-debounce";
import { AnnotationMap } from "./AnnotationMap";
import { GeographicAnnotationPin, MapBBox } from "./types";
import {
  GeographicAnnotationsInput,
  GetGlobalGeographicAnnotationsOutput,
  GET_GLOBAL_GEOGRAPHIC_ANNOTATIONS,
} from "../../graphql/queries/geographicAnnotations";
import {
  GET_DOCUMENT_BY_ID_FOR_REDIRECT,
  GetDocumentByIdForRedirectInput,
  GetDocumentByIdForRedirectOutput,
} from "../../graphql/queries";
import { buildCanonicalPath } from "../../utils/navigationUtils";
import {
  GEO_LABEL_TYPES,
  MAP_BBOX_REFETCH_DEBOUNCE_MS,
} from "../../assets/configurations/constants";

export interface DiscoverMapView {
  center: [number, number];
  zoom: number;
}

interface DiscoverMapPanelProps {
  /** Initial viewport (typically restored from the URL by the parent view). */
  initialView: DiscoverMapView;
  /** Called (debounced) when the user pans/zooms, so the parent can persist it. */
  onViewChange?: (view: DiscoverMapView) => void;
}

/**
 * Discover "Map" tab body. Feeds the reusable {@link AnnotationMap} with
 * cross-corpus geographic pins from `globalGeographicAnnotations`.
 *
 * Discover-specific concerns live here (not in AnnotationMap): the choice of
 * GraphQL query, debounced bbox refetches, and bubbling viewport changes up to
 * the parent view for URL persistence. Permission filtering is server-side.
 *
 * The component fetches no more than necessary: only the pin fields the map
 * renders, only the all-label-types set (the client picks the band by zoom),
 * and it refetches only when the user actually pans/zooms (debounced 300ms).
 */
export const DiscoverMapPanel: React.FC<DiscoverMapPanelProps> = ({
  initialView,
  onViewChange,
}) => {
  // Query variables update only on (debounced) pan/zoom. Seed with a
  // whole-world bbox (null) so pins appear on first paint.
  const [variables, setVariables] = useState<GeographicAnnotationsInput>({
    bbox: null,
    zoom: initialView.zoom,
    labelTypes: [...GEO_LABEL_TYPES],
  });

  const { data, loading } = useQuery<
    GetGlobalGeographicAnnotationsOutput,
    GeographicAnnotationsInput
  >(GET_GLOBAL_GEOGRAPHIC_ANNOTATIONS, {
    variables,
    fetchPolicy: "cache-and-network",
  });

  const pins: GeographicAnnotationPin[] = useMemo(
    () => data?.globalGeographicAnnotations ?? [],
    [data]
  );

  const navigate = useNavigate();
  // A pin carries only its sample documents' Relay global ids (the backend
  // deliberately ships no slugs). To open one we resolve the id to its
  // canonical slug URL the same way CentralRouteManager's id fallback does,
  // then navigate. The lookup runs only when a document is actually opened,
  // and ``document(id:)`` is permission-filtered server-side.
  const [resolveDocumentById] = useLazyQuery<
    GetDocumentByIdForRedirectOutput,
    GetDocumentByIdForRedirectInput
  >(GET_DOCUMENT_BY_ID_FOR_REDIRECT, { fetchPolicy: "cache-first" });

  const handleSelectDocument = useCallback(
    async (documentId: string) => {
      const { data: docData } = await resolveDocumentById({
        variables: { id: documentId },
      });
      const document = docData?.document;
      if (!document) {
        return;
      }
      // Cast mirrors CentralRouteManager's id-redirect call: the lightweight
      // redirect query is a structural subset of DocumentType, and
      // buildCanonicalPath only reads slug/creator fields.
      const path = buildCanonicalPath(document as any, document.corpus as any);
      if (path) {
        navigate(path);
      }
    },
    [navigate, resolveDocumentById]
  );

  // Debounce both the network refetch and the URL-persistence callback so a
  // continuous drag fires at most one of each per settle.
  const handleBoundsChange = useDebouncedCallback(
    (bbox: MapBBox, zoom: number) => {
      setVariables({ bbox, zoom, labelTypes: [...GEO_LABEL_TYPES] });
      // The longitude midpoint must handle antimeridian-crossing viewports
      // (west > east, e.g. west=170/east=-170 whose true centre is 180/-180).
      // A plain average would yield 0 (the prime meridian) and persist a wrong
      // deep-link; the backend BBox already wraps, so the URL must agree.
      const midLng =
        bbox.west <= bbox.east
          ? (bbox.west + bbox.east) / 2
          : (((bbox.west + bbox.east + 360) / 2 + 180) % 360) - 180;
      onViewChange?.({
        center: [(bbox.south + bbox.north) / 2, midLng],
        zoom,
      });
    },
    MAP_BBOX_REFETCH_DEBOUNCE_MS
  );

  return (
    <AnnotationMap
      pins={pins}
      loading={loading}
      center={initialView.center}
      zoom={initialView.zoom}
      onBoundsChange={handleBoundsChange}
      onSelectDocument={handleSelectDocument}
    />
  );
};

export default DiscoverMapPanel;
