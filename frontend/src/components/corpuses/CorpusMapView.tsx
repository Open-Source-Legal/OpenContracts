import React, { useCallback, useMemo } from "react";
import { useLazyQuery, useQuery, useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import styled from "styled-components";
import { ArrowLeft, Compass, MapPin } from "lucide-react";

import { CorpusType } from "../../types/graphql-api";
import { corpusMapPin } from "../../graphql/cache";
import {
  getDocumentUrl,
  updateCorpusMapPinParam,
} from "../../utils/navigationUtils";
import { pluralizePlaces } from "../../utils/formatters";
import { AnnotationMap } from "../maps/AnnotationMap";
import { GeographicAnnotationPin } from "../maps/types";
import {
  corpusGeoInitialVariables,
  GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS,
  GetGeographicAnnotationsForCorpusInput,
  GetGeographicAnnotationsForCorpusOutput,
} from "../../graphql/queries/geographicAnnotations";
import {
  GET_DOCUMENT_BY_ID_FOR_REDIRECT,
  GetDocumentByIdForRedirectInput,
  GetDocumentByIdForRedirectOutput,
} from "../../graphql/queries";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { CORPUS_BREAKPOINTS, CORPUS_RADII } from "./styles/corpusDesignTokens";
import {
  BackButton,
  DetailsContainer,
  DetailsHeader,
  DetailsPage,
  DetailsTitle,
  DetailsTitleRow,
  DetailsTitleSection,
  MetadataItem,
} from "./CorpusHome/styles";

// Area that holds the map (or the loading/empty/error placeholder). Fills the
// page below the header; the map needs an explicit height, so height="100%"
// resolves against this flex child.
const MapBody = styled.div`
  flex: 1;
  min-height: 0;
  display: flex;
  padding: 1.5rem 2.5rem 2rem;

  @media (max-width: ${CORPUS_BREAKPOINTS.tablet}px) {
    padding: 0.75rem;
  }
`;

const Placeholder = styled.div`
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  text-align: center;
  padding: 2rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${CORPUS_RADII.lg};
  background: ${OS_LEGAL_COLORS.surfaceHover};
`;

const PlaceholderIcon = styled.div`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: ${CORPUS_RADII.full};
  background: ${OS_LEGAL_COLORS.surface};
  color: ${OS_LEGAL_COLORS.textSecondary};
  box-shadow: inset 0 0 0 1px ${OS_LEGAL_COLORS.border};
`;

const PlaceholderTitle = styled.h3`
  margin: 0;
  font-size: 1.0625rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const PlaceholderBody = styled.p`
  margin: 0;
  max-width: 30rem;
  font-size: 0.875rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const AgentHint = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.accent};

  svg {
    width: 14px;
    height: 14px;
  }
`;

export interface CorpusMapViewProps {
  /** The corpus whose geographic annotations are plotted. */
  corpus: CorpusType;
  /** Return to the corpus landing view. */
  onBack: () => void;
  /** Test ID for the component. */
  testId?: string;
}

/**
 * CorpusMapView — per-corpus geographic map (issue #1821).
 *
 * Wraps the reusable {@link AnnotationMap} (#1820) with the corpus-scoped
 * `geographicAnnotationsForCorpus` query (#1819). Corpus-specific concerns live
 * here, not in AnnotationMap: the choice of query, deep-link focus, and
 * resolving a pin's sample documents to their canonical URLs.
 *
 * Performance: corpus pin sets are bounded (server-aggregated + deduplicated),
 * so this fetches the whole corpus once (no per-pan refetch like the global
 * Discover map) and selects only the lightweight pin fields. The variables are
 * shared with the Corpus Home map-toggle badge via `corpusGeoInitialVariables`,
 * so the badge's fetch warms this view's cache and opening the map costs no
 * extra round-trip.
 *
 * Permissions: `geographicAnnotationsForCorpus` already filters to documents
 * visible to the user under MIN(document, corpus) server-side, and the
 * sample-document links resolve through the permission-filtered `document(id:)`
 * resolver — the pin panel can only reveal corpus documents the user may see.
 */
export const CorpusMapView: React.FC<CorpusMapViewProps> = ({
  corpus,
  onBack,
  testId = "corpus-map",
}) => {
  const location = useLocation();
  const navigate = useNavigate();

  // Deep-linked place (?pin=) is URL-driven via CentralRouteManager → reactive
  // var; the map selects + flies to it once the matching pin loads.
  const focusPinName = useReactiveVar(corpusMapPin);

  const variables = useMemo(
    () => corpusGeoInitialVariables(corpus.id),
    [corpus.id]
  );

  const { data, loading, error } = useQuery<
    GetGeographicAnnotationsForCorpusOutput,
    GetGeographicAnnotationsForCorpusInput
  >(GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS, {
    variables,
    fetchPolicy: "cache-and-network",
  });

  const pins: GeographicAnnotationPin[] = useMemo(
    () => data?.geographicAnnotationsForCorpus ?? [],
    [data]
  );

  // A pin carries only its sample documents' Relay global ids. Resolve one to
  // its canonical slug URL on demand (the lookup is permission-filtered) and
  // navigate — mirrors DiscoverMapPanel's id→URL fallback.
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
        const resolvedDoc = docData?.document;
        if (!resolvedDoc) {
          return;
        }
        const url = getDocumentUrl(resolvedDoc, resolvedDoc.corpus);
        if (url !== "#") {
          navigate(url);
        }
      } catch (err) {
        // A network/GraphQL failure shouldn't become an unhandled rejection —
        // the click simply doesn't navigate.
        console.error("Failed to resolve document for map navigation:", err);
      }
    },
    [navigate, resolveDocumentById]
  );

  // Reflect the selected place into the URL so the map is shareable and
  // survives refresh; the reactive var round-trip re-focuses the map.
  const handlePinClick = useCallback(
    (pin: GeographicAnnotationPin) => {
      updateCorpusMapPinParam(location, navigate, pin.canonicalName);
    },
    [location, navigate]
  );

  const placeCountLabel =
    loading && pins.length === 0 ? "Loading…" : pluralizePlaces(pins.length);

  const renderBody = () => {
    // Stale-but-present pins win over the error state by design: with
    // `cache-and-network`, a background refresh failure should keep the last
    // good map on screen rather than blanking it to an error placeholder. The
    // explicit `error` branch below only fires when there is nothing to show.
    if (pins.length > 0) {
      return (
        <AnnotationMap
          pins={pins}
          loading={loading}
          fitToPins
          focusPinName={focusPinName}
          onPinClick={handlePinClick}
          onSelectDocument={handleSelectDocument}
          height="100%"
        />
      );
    }

    if (loading) {
      return (
        <Placeholder
          role="status"
          aria-live="polite"
          data-testid={`${testId}-loading`}
        >
          <PlaceholderIcon>
            <MapPin aria-hidden="true" />
          </PlaceholderIcon>
          <PlaceholderTitle>Loading places…</PlaceholderTitle>
        </Placeholder>
      );
    }

    if (error) {
      return (
        <Placeholder role="alert" data-testid={`${testId}-error`}>
          <PlaceholderIcon>
            <MapPin aria-hidden="true" />
          </PlaceholderIcon>
          <PlaceholderTitle>Could not load the map</PlaceholderTitle>
          <PlaceholderBody>
            Something went wrong fetching this corpus&rsquo;s places. Try
            reloading the page.
          </PlaceholderBody>
        </Placeholder>
      );
    }

    // No geographic annotations yet — point the user at the agent that creates
    // them (Location Tagger, #TBD-PR4) so they know how to populate the map.
    return (
      <Placeholder data-testid={`${testId}-empty`}>
        <PlaceholderIcon>
          <MapPin aria-hidden="true" />
        </PlaceholderIcon>
        <PlaceholderTitle>No places on the map yet</PlaceholderTitle>
        <PlaceholderBody>
          This corpus has no geographic annotations to plot. Run the{" "}
          <AgentHint>
            <Compass aria-hidden="true" />
            Location Tagger
          </AgentHint>{" "}
          agent on the corpus to extract place references from your documents
          and they&rsquo;ll appear here.
        </PlaceholderBody>
      </Placeholder>
    );
  };

  return (
    <DetailsContainer data-testid={testId}>
      <DetailsPage>
        <DetailsHeader>
          <BackButton
            onClick={onBack}
            data-testid={`${testId}-back`}
            whileTap={{ scale: 0.97 }}
          >
            <ArrowLeft aria-hidden="true" />
            Overview
          </BackButton>
          <DetailsTitleRow>
            <DetailsTitleSection>
              <DetailsTitle>Map</DetailsTitle>
              <MetadataItem data-testid={`${testId}-count`}>
                <MapPin aria-hidden="true" />
                <span>{placeCountLabel}</span>
              </MetadataItem>
            </DetailsTitleSection>
          </DetailsTitleRow>
        </DetailsHeader>
        <MapBody>{renderBody()}</MapBody>
      </DetailsPage>
    </DetailsContainer>
  );
};

export default CorpusMapView;
