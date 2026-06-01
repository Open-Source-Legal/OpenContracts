import React, { useMemo } from "react";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import { MapPin } from "lucide-react";

import {
  corpusGeoInitialVariables,
  GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS,
  GetGeographicAnnotationsForCorpusInput,
  GetGeographicAnnotationsForCorpusOutput,
} from "../../../graphql/queries/geographicAnnotations";
import { pluralizePlaces } from "../../../utils/formatters";
import {
  CORPUS_COLORS,
  CORPUS_FONT_SIZES,
  CORPUS_RADII,
  CORPUS_TRANSITIONS,
} from "../styles/corpusDesignTokens";

const ToggleButton = styled.button<{ $hasPlaces: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  border-radius: ${CORPUS_RADII.full};
  border: 1px solid
    ${(p) =>
      p.$hasPlaces ? CORPUS_COLORS.teal[200] : CORPUS_COLORS.slate[200]};
  background: ${(p) =>
    p.$hasPlaces ? CORPUS_COLORS.teal[50] : CORPUS_COLORS.slate[100]};
  color: ${(p) =>
    p.$hasPlaces ? CORPUS_COLORS.teal[700] : CORPUS_COLORS.slate[400]};
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: border-color ${CORPUS_TRANSITIONS.fast},
    background ${CORPUS_TRANSITIONS.fast}, color ${CORPUS_TRANSITIONS.fast};

  svg {
    width: ${CORPUS_FONT_SIZES.sm};
    height: ${CORPUS_FONT_SIZES.sm};
  }

  &:hover {
    border-color: ${(p) =>
      p.$hasPlaces ? CORPUS_COLORS.teal[300] : CORPUS_COLORS.slate[300]};
    color: ${(p) =>
      p.$hasPlaces ? CORPUS_COLORS.teal[800] : CORPUS_COLORS.slate[600]};
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 2px;
  }
`;

const CountLabel = styled.span<{ $hasPlaces: boolean }>`
  color: ${(p) =>
    p.$hasPlaces ? CORPUS_COLORS.teal[600] : CORPUS_COLORS.slate[400]};
`;

export interface CorpusMapToggleProps {
  /** The corpus whose place count is shown on the badge. */
  corpusId: string;
  /** Open the map view. */
  onClick: () => void;
  /** Test ID for the component. */
  testId?: string;
}

/**
 * Corpus Home map entry toggle (#1821).
 *
 * A compact pill in the landing top bar that opens the map view, badged with
 * the place count ("Map · 12 places"). Muted ("greyed-out") when the corpus has
 * no geographic annotations, but still clickable so users reach the empty-state
 * guidance on how to populate the map.
 *
 * Reuses `corpusGeoInitialVariables`, so this count query shares an Apollo cache
 * entry with CorpusMapView — the badge warms the map's data and opening the map
 * costs no extra fetch. cache-first because the passive badge only needs a
 * count, and errorPolicy "all" keeps a load failure from surfacing an error on
 * the landing page (the badge just stays muted).
 */
export const CorpusMapToggle: React.FC<CorpusMapToggleProps> = ({
  corpusId,
  onClick,
  testId = "corpus-map-toggle",
}) => {
  const variables = useMemo(
    () => corpusGeoInitialVariables(corpusId),
    [corpusId]
  );

  const { data } = useQuery<
    GetGeographicAnnotationsForCorpusOutput,
    GetGeographicAnnotationsForCorpusInput
  >(GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS, {
    variables,
    fetchPolicy: "cache-first",
    errorPolicy: "all",
  });

  // Show the count only once resolved so the badge doesn't flash "0 places"
  // before the data arrives.
  const loaded = data !== undefined;
  const placeCount = data?.geographicAnnotationsForCorpus?.length ?? 0;
  const hasPlaces = placeCount > 0;

  return (
    <ToggleButton
      type="button"
      $hasPlaces={hasPlaces}
      onClick={onClick}
      data-testid={testId}
      aria-label={
        hasPlaces
          ? `Open map — ${pluralizePlaces(placeCount)}`
          : "Open map — no places tagged yet"
      }
      title={
        hasPlaces
          ? `View ${pluralizePlaces(placeCount)} on the map`
          : "No places tagged yet — open to learn how to add them"
      }
    >
      <MapPin aria-hidden="true" />
      Map
      {loaded && (
        <CountLabel $hasPlaces={hasPlaces}>
          · {pluralizePlaces(placeCount)}
        </CountLabel>
      )}
    </ToggleButton>
  );
};

export default CorpusMapToggle;
