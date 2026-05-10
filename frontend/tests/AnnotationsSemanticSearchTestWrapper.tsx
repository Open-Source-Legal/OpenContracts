/**
 * Test wrapper for Annotations semantic search component tests.
 *
 * Provides:
 * - MockedProvider with wildcard link for flexible query matching
 * - Proper cache configuration
 * - React Router context
 * - Authentication state setup (synchronous, before render)
 */
import React, { useEffect } from "react";
import { MockedProvider, MockLink } from "@apollo/client/testing";
import { ApolloLink, Observable } from "@apollo/client";
import { MemoryRouter } from "react-router-dom";
import { GraphQLError } from "graphql";
import { Annotations } from "../src/views/Annotations";
import {
  GET_ANNOTATIONS_FOR_CARDS,
  SEMANTIC_SEARCH_ANNOTATIONS,
  GET_CORPUS_LABELSET_AND_LABELS,
} from "../src/graphql/queries";
import { createTestCache } from "./testUtils";
import {
  annotationContentSearchTerm,
  authStatusVar,
  authToken,
  userObj,
  filterToCorpus,
  filterToLabelsetId,
  filterToLabelId,
  openedCorpus,
  filterToStructuralAnnotations,
  selectedAnnotationIds,
} from "../src/graphql/cache";

interface SemanticSearchResult {
  annotation: any;
  similarityScore: number;
  document: any;
  corpus: any;
}

interface AnnotationsSemanticSearchTestWrapperProps {
  /** Results to return for semantic search queries */
  semanticSearchResults?: SemanticSearchResult[];
  /** Annotations to return for browse mode (GET_ANNOTATIONS) */
  browseAnnotations?: any[];
  /** Simulate a search error with this message */
  simulateSearchError?: string;
  /** Simulate delay in search response (ms) */
  simulateSearchDelay?: number;
  /** Optional corpus ID for filtering */
  corpusId?: string;
  /** Pre-seed structural-annotation filter (drives the EXCLUDE/ONLY branches
   *  of ``annotation_variables``). */
  initialStructuralFilter?: "INCLUDE" | "EXCLUDE" | "ONLY";
  /** Pre-seed labelset id (drives the ``usesLabelFromLabelsetId`` branch). */
  initialLabelsetId?: string;
  /** Pre-seed label id (drives the ``annotationLabelId`` branch). */
  initialLabelId?: string;
  /** Pre-seed filter-to-corpus (drives the ``corpusId`` branch and the
   *  ``corpus_scope_id`` derivation). */
  initialFilterCorpus?: { id: string; title?: string } | null;
  /** Pre-seed annotation content search term (drives the
   *  ``rawText_Contains`` branch of ``annotation_variables``). */
  initialContentSearchTerm?: string;
  /** Pre-seed openedCorpus to exercise the ``corpus_scope_id`` fallback when
   *  no explicit filter-to-corpus is set. */
  initialOpenedCorpus?: { id: string; title?: string } | null;
}

/**
 * Inner component that handles reactive var cleanup on unmount.
 */
const InnerWrapper: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  useEffect(() => {
    // Cleanup on unmount
    return () => {
      filterToCorpus(null);
      filterToLabelsetId("");
      filterToLabelId("");
      openedCorpus(null);
      annotationContentSearchTerm("");
      filterToStructuralAnnotations("INCLUDE");
      selectedAnnotationIds([]);
    };
  }, []);

  return <>{children}</>;
};

/**
 * Creates a wildcard ApolloLink that responds to queries regardless of variables.
 * This approach is more flexible than exact mock matching and handles:
 * - Repeated queries (Apollo MockLink consumes mocks on first use)
 * - Variable variations (different filter combinations)
 * - Refetches triggered by reactive var changes
 */
const createAnnotationsWildcardLink = (
  browseAnnotations: any[],
  semanticSearchResults: SemanticSearchResult[],
  simulateSearchError?: string,
  simulateSearchDelay: number = 0
) => {
  // Build the response for GET_ANNOTATIONS
  const annotationsResponse = {
    data: {
      annotations: {
        __typename: "AnnotationTypeConnection",
        totalCount: browseAnnotations.length,
        edges: browseAnnotations.map((annotation) => ({
          __typename: "AnnotationTypeEdge",
          node: annotation,
          cursor: annotation.id,
        })),
        pageInfo: {
          __typename: "PageInfo",
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: browseAnnotations[0]?.id || null,
          endCursor:
            browseAnnotations[browseAnnotations.length - 1]?.id || null,
        },
      },
    },
  };

  // Build the response for SEMANTIC_SEARCH_ANNOTATIONS
  const semanticSearchResponse = simulateSearchError
    ? { errors: [new GraphQLError(simulateSearchError)] }
    : { data: { semanticSearch: semanticSearchResults } };

  // Build the response for GET_CORPUS_LABELSET_AND_LABELS (returns null when no corpus)
  const corpusLabelsetResponse = {
    data: {
      corpus: null,
    },
  };

  return new ApolloLink((operation) => {
    const opName = operation.operationName;
    const query = operation.query;

    console.log(`[MOCK] Processing: ${opName}`, operation.variables);

    // Match GET_ANNOTATIONS_FOR_CARDS query (any variables)
    if (
      query === GET_ANNOTATIONS_FOR_CARDS ||
      opName === "GetAnnotationsForCards"
    ) {
      console.log("[MOCK] Returning annotations response");
      return Observable.of(annotationsResponse);
    }

    // Match SEMANTIC_SEARCH_ANNOTATIONS query (any variables)
    if (
      query === SEMANTIC_SEARCH_ANNOTATIONS ||
      opName === "SemanticSearchAnnotations"
    ) {
      console.log("[MOCK] Returning semantic search response");
      if (simulateSearchDelay > 0) {
        return new Observable((observer) => {
          setTimeout(() => {
            observer.next(semanticSearchResponse);
            observer.complete();
          }, simulateSearchDelay);
        });
      }
      return Observable.of(semanticSearchResponse);
    }

    // Match GET_CORPUS_LABELSET_AND_LABELS query (any variables)
    if (
      query === GET_CORPUS_LABELSET_AND_LABELS ||
      opName === "GetCorpusLabelsetAndLabels"
    ) {
      console.log("[MOCK] Returning corpus labelset response");
      return Observable.of(corpusLabelsetResponse);
    }

    // For any unhandled queries, return null data to prevent errors
    console.log(`[MOCK] Unhandled query: ${opName}`);
    return Observable.of({ data: null });
  });
};

/**
 * Test wrapper for Annotations component with semantic search mocks.
 */
export const AnnotationsSemanticSearchTestWrapper: React.FC<
  AnnotationsSemanticSearchTestWrapperProps
> = ({
  semanticSearchResults = [],
  browseAnnotations = [],
  simulateSearchError,
  simulateSearchDelay = 0,
  initialStructuralFilter = "INCLUDE",
  initialLabelsetId = "",
  initialLabelId = "",
  initialFilterCorpus = null,
  initialContentSearchTerm = "",
  initialOpenedCorpus = null,
}) => {
  // Set up authentication state SYNCHRONOUSLY before render
  // This ensures auth is available when components first render
  authToken("test-token");
  userObj({
    id: "VXNlclR5cGU6MQ==",
    email: "test@example.com",
    username: "testuser",
  } as any);
  authStatusVar("AUTHENTICATED");

  // Initialize filter state synchronously. The pre-seed values exist so
  // tests can exercise the branches inside ``annotation_variables`` without
  // having to re-render after a reactive-var update (Apollo's variable
  // memoisation only flips when the *primitive* dep changes, so dispatching
  // a reactive-var update after mount produces the same coverage as
  // setting it up-front for branch-coverage purposes).
  filterToCorpus(initialFilterCorpus as any);
  filterToLabelsetId(initialLabelsetId);
  filterToLabelId(initialLabelId);
  openedCorpus(initialOpenedCorpus as any);
  filterToStructuralAnnotations(initialStructuralFilter);
  annotationContentSearchTerm(initialContentSearchTerm);
  selectedAnnotationIds([]);

  const link = createAnnotationsWildcardLink(
    browseAnnotations,
    semanticSearchResults,
    simulateSearchError,
    simulateSearchDelay
  );

  const cache = createTestCache();

  return (
    <MockedProvider link={link} cache={cache} addTypename={false}>
      <MemoryRouter initialEntries={["/annotations"]}>
        <InnerWrapper>
          <Annotations />
        </InnerWrapper>
      </MemoryRouter>
    </MockedProvider>
  );
};
