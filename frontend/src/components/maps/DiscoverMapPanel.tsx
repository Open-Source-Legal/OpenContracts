import React, { useMemo, useState } from "react";
import { useQuery } from "@apollo/client";
import { useDebouncedCallback } from "use-debounce";
import { AnnotationMap } from "./AnnotationMap";
import { GeographicAnnotationPin, MapBBox } from "./types";
import {
  GeographicAnnotationsInput,
  GetGlobalGeographicAnnotationsOutput,
  GET_GLOBAL_GEOGRAPHIC_ANNOTATIONS,
} from "../../graphql/queries/geographicAnnotations";
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

  // Debounce both the network refetch and the URL-persistence callback so a
  // continuous drag fires at most one of each per settle.
  const handleBoundsChange = useDebouncedCallback(
    (bbox: MapBBox, zoom: number) => {
      setVariables({ bbox, zoom, labelTypes: [...GEO_LABEL_TYPES] });
      onViewChange?.({
        center: [(bbox.south + bbox.north) / 2, (bbox.west + bbox.east) / 2],
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
    />
  );
};

export default DiscoverMapPanel;
