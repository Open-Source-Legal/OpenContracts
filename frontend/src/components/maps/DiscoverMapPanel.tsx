import React, { useCallback, useMemo, useState } from "react";
import { useLazyQuery, useQuery } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { useDebouncedCallback } from "use-debounce";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { MAP_DEFAULT_HEIGHT } from "../../assets/configurations/constants";
import { AnnotationMap } from "./AnnotationMap";
import { bboxCenter } from "./zoomBands";
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
import { getDocumentUrl } from "../../utils/navigationUtils";
import {
  GEO_LABEL_TYPES,
  MAP_BBOX_REFETCH_DEBOUNCE_MS,
} from "../../assets/configurations/constants";

export interface DiscoverMapView {
  center: [number, number];
  zoom: number;
}

const MapError = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: ${MAP_DEFAULT_HEIGHT};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  padding: 1rem;
  text-align: center;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceHover};
`;

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

  const { data, loading, error } = useQuery<
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
      try {
        const { data: docData } = await resolveDocumentById({
          variables: { id: documentId },
        });
        const document = docData?.document;
        if (!document) {
          return;
        }
        // getDocumentUrl accepts the redirect query's slug/creator shape
        // directly (a structural subset of DocumentType) and returns "#" when
        // slugs are missing, so no cast is needed.
        const url = getDocumentUrl(document, document.corpus);
        if (url !== "#") {
          navigate(url);
        }
      } catch (err) {
        // A network/GraphQL failure here should not become an unhandled
        // rejection — the pin click simply doesn't navigate.
        console.error("Failed to resolve document for map navigation:", err);
      }
    },
    [navigate, resolveDocumentById]
  );

  // Debounce both the network refetch and the URL-persistence callback so a
  // continuous drag fires at most one of each per settle.
  const handleBoundsChange = useDebouncedCallback(
    (bbox: MapBBox, zoom: number) => {
      setVariables({ bbox, zoom, labelTypes: [...GEO_LABEL_TYPES] });
      // bboxCenter handles antimeridian-crossing viewports so the persisted
      // deep-link agrees with the backend BBox wrapping (see zoomBands.ts).
      onViewChange?.({
        center: bboxCenter(bbox),
        zoom,
      });
    },
    MAP_BBOX_REFETCH_DEBOUNCE_MS
  );

  // Surface a load failure rather than a silently blank map — but only when we
  // have no cached pins to fall back on (cache-and-network can error while
  // still holding a usable prior result).
  if (error && pins.length === 0) {
    return (
      <MapError role="alert">
        Could not load map data. Try panning, zooming, or reloading.
      </MapError>
    );
  }

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
