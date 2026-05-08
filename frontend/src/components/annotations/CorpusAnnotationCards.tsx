import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import _ from "lodash";

import { toast } from "react-toastify";
import { useQuery, useLazyQuery, useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";

import {
  AnnotationsPanel,
  TypeFilterValue,
  SourceFilterValue,
} from "./AnnotationsPanel";

import {
  authToken,
  annotationContentSearchTerm,
  filterToLabelsetId,
  filterToLabelId,
  selectedAnalysesIds,
  filterToAnnotationType,
} from "../../graphql/cache";

import {
  GetAnnotationsInputs,
  GetAnnotationsOutputs,
  GET_ANNOTATIONS_FOR_CARDS,
  SemanticSearchInput,
  SemanticSearchOutput,
  SemanticSearchResult,
  SEMANTIC_SEARCH_ANNOTATIONS,
} from "../../graphql/queries";
import { ServerAnnotationType } from "../../types/graphql-api";
import { getDocumentUrl } from "../../utils/navigationUtils";
import { ANNOTATION_PAGINATION } from "../../assets/configurations/constants";

export const CorpusAnnotationCards = ({
  opened_corpus_id,
}: {
  opened_corpus_id: string | null;
}) => {
  /**
   * This component wraps the AnnotationsPanel component with query logic
   * for a given corpus_id. It includes source filter controls that allow
   * users to toggle between Human, AI Agent, and Structural annotations.
   * Supports semantic search when user types in the search box.
   */

  const navigate = useNavigate();
  const auth_token = useReactiveVar(authToken);
  const annotation_search_term = useReactiveVar(annotationContentSearchTerm);
  const filter_to_labelset_id = useReactiveVar(filterToLabelsetId);
  const filter_to_label_id = useReactiveVar(filterToLabelId);
  const selected_analysis_ids = useReactiveVar(selectedAnalysesIds);
  const filter_to_annotation_type = useReactiveVar(filterToAnnotationType);
  const location = useLocation();

  // Local filter state
  const [typeFilter, setTypeFilter] = useState<TypeFilterValue>("all");
  const [sourceFilter, setSourceFilter] = useState<SourceFilterValue>("all");
  const [searchValue, setSearchValue] = useState("");

  // Semantic search state
  const [semanticSearchOffset, setSemanticSearchOffset] = useState(0);
  const [semanticSearchResults, setSemanticSearchResults] = useState<
    SemanticSearchResult[]
  >([]);
  const [hasMoreSemanticResults, setHasMoreSemanticResults] = useState(true);

  // Convert array of IDs to comma-separated string for GraphQL query
  const selected_analysis_id_string = selected_analysis_ids.join(",");

  // Build query variables based on sourceFilter
  const queryVariables = useMemo(() => {
    const vars: GetAnnotationsInputs = {};

    if (opened_corpus_id) {
      vars.corpusId = opened_corpus_id;
    }

    // Source filter determines structural and agentCreated.
    // "human" = non-structural, NOT created by any agent (analysis or corpus action).
    // "agent" = non-structural, created by an analysis OR a corpus action.
    if (sourceFilter === "structural") {
      vars.structural = true;
    } else if (sourceFilter === "human") {
      vars.structural = false;
      vars.agentCreated = false;
    } else if (sourceFilter === "agent") {
      vars.structural = false;
      vars.agentCreated = true;
    } else {
      // "all" - no filters; show everything
    }

    // Apply other filters
    if (selected_analysis_id_string) {
      vars.createdByAnalysisIds = selected_analysis_id_string;
    }
    if (filter_to_annotation_type) {
      vars.annotationLabel_Type = filter_to_annotation_type;
    }
    if (filter_to_label_id) {
      vars.annotationLabelId = filter_to_label_id;
    }
    if (filter_to_labelset_id) {
      vars.usesLabelFromLabelsetId = filter_to_labelset_id;
    }
    // Note: Don't add rawText_Contains here - we use semantic search for text search

    // Always set a limit for pagination
    vars.limit = ANNOTATION_PAGINATION.PAGE_SIZE;

    return vars;
  }, [
    opened_corpus_id,
    sourceFilter,
    selected_analysis_id_string,
    filter_to_annotation_type,
    filter_to_label_id,
    filter_to_labelset_id,
  ]);

  // Regular annotations query (used when not searching)
  const {
    refetch: refetchAnnotations,
    loading: annotation_loading,
    error: annotation_error,
    data: annotation_response,
    fetchMore: fetchMoreAnnotations,
  } = useQuery<GetAnnotationsOutputs, GetAnnotationsInputs>(
    GET_ANNOTATIONS_FOR_CARDS,
    {
      fetchPolicy: "network-only",
      notifyOnNetworkStatusChange: true,
      skip: !opened_corpus_id,
      variables: queryVariables,
    }
  );

  // Semantic search query
  const [
    executeSemanticSearch,
    { loading: semanticSearchLoading, error: semanticSearchError },
  ] = useLazyQuery<SemanticSearchOutput, SemanticSearchInput>(
    SEMANTIC_SEARCH_ANNOTATIONS,
    {
      fetchPolicy: "network-only",
      notifyOnNetworkStatusChange: true,
      onCompleted: (data) => {
        if (data?.semanticSearch) {
          const newResults = data.semanticSearch;
          if (semanticSearchOffset === 0) {
            // First page - just set results (capped)
            setSemanticSearchResults(
              newResults.slice(0, ANNOTATION_PAGINATION.MAX_SEMANTIC_RESULTS)
            );
          } else {
            // Pagination - deduplicate and cap accumulated results
            setSemanticSearchResults((prev) => {
              const combined = [...prev, ...newResults];
              // Deduplicate by annotation ID to handle potential overlaps
              const unique = _.uniqBy(combined, (r) => r.annotation.id);
              // Cap at MAX_SEMANTIC_RESULTS to prevent unbounded memory usage
              return unique.slice(
                0,
                ANNOTATION_PAGINATION.MAX_SEMANTIC_RESULTS
              );
            });
          }
          // Stop fetching more if we hit the cap or got fewer results than limit
          const atCap =
            semanticSearchOffset + newResults.length >=
            ANNOTATION_PAGINATION.MAX_SEMANTIC_RESULTS;
          setHasMoreSemanticResults(
            !atCap &&
              newResults.length === ANNOTATION_PAGINATION.SEMANTIC_SEARCH_LIMIT
          );
        }
      },
    }
  );

  if (annotation_error) {
    toast.error("ERROR\nCould not fetch annotations for corpus.");
  }

  // Determine if we're in semantic search mode
  const isSemanticSearchActive = searchValue.trim().length > 0;

  // Execute semantic search with current filters
  const performSemanticSearch = useCallback(
    (query: string, offset: number = 0) => {
      if (!query.trim() || !opened_corpus_id) return;

      const variables: SemanticSearchInput = {
        query: query.trim(),
        limit: ANNOTATION_PAGINATION.SEMANTIC_SEARCH_LIMIT,
        offset,
        corpusId: opened_corpus_id,
      };

      executeSemanticSearch({ variables });
    },
    [executeSemanticSearch, opened_corpus_id]
  );

  // Debounced semantic search
  const debouncedSearch = useRef(
    _.debounce((searchTerm: string) => {
      if (searchTerm.trim()) {
        setSemanticSearchOffset(0);
        setSemanticSearchResults([]);
        setHasMoreSemanticResults(true);
        performSemanticSearch(searchTerm, 0);
      } else {
        setSemanticSearchResults([]);
        setSemanticSearchOffset(0);
        setHasMoreSemanticResults(true);
      }
    }, 500)
  );

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      debouncedSearch.current.cancel();
    };
  }, []);

  // Update debounced search when performSemanticSearch changes
  useEffect(() => {
    debouncedSearch.current = _.debounce((searchTerm: string) => {
      if (searchTerm.trim()) {
        setSemanticSearchOffset(0);
        setSemanticSearchResults([]);
        setHasMoreSemanticResults(true);
        performSemanticSearch(searchTerm, 0);
      } else {
        setSemanticSearchResults([]);
        setSemanticSearchOffset(0);
        setHasMoreSemanticResults(true);
      }
    }, 500);
  }, [performSemanticSearch]);

  // Handle fetch more for both regular and semantic search
  const handleFetchMore = useCallback(() => {
    if (isSemanticSearchActive) {
      // Semantic search pagination
      if (!semanticSearchLoading && hasMoreSemanticResults) {
        const newOffset =
          semanticSearchOffset + ANNOTATION_PAGINATION.SEMANTIC_SEARCH_LIMIT;
        setSemanticSearchOffset(newOffset);
        performSemanticSearch(searchValue, newOffset);
      }
    } else {
      // Regular annotation pagination
      if (
        !annotation_loading &&
        annotation_response?.annotations.pageInfo?.hasNextPage
      ) {
        fetchMoreAnnotations({
          variables: {
            limit: ANNOTATION_PAGINATION.PAGE_SIZE,
            cursor: annotation_response.annotations.pageInfo.endCursor,
          },
        });
      }
    }
  }, [
    isSemanticSearchActive,
    semanticSearchLoading,
    hasMoreSemanticResults,
    semanticSearchOffset,
    searchValue,
    performSemanticSearch,
    annotation_loading,
    annotation_response,
    fetchMoreAnnotations,
  ]);

  // Effects to reload data on certain changes
  useEffect(() => {
    if (auth_token && opened_corpus_id) {
      refetchAnnotations();
    }
  }, [auth_token, opened_corpus_id, refetchAnnotations]);

  useEffect(() => {
    if (filter_to_label_id && opened_corpus_id) {
      refetchAnnotations();
    }
  }, [filter_to_label_id, opened_corpus_id, refetchAnnotations]);

  useEffect(() => {
    if (opened_corpus_id) {
      refetchAnnotations();
    }
  }, [selected_analysis_ids, opened_corpus_id, refetchAnnotations]);

  useEffect(() => {
    if (opened_corpus_id && location.pathname === "/corpuses") {
      refetchAnnotations();
    }
  }, [location, opened_corpus_id, refetchAnnotations]);

  useEffect(() => {
    if (opened_corpus_id) {
      refetchAnnotations();
    }
  }, [opened_corpus_id, refetchAnnotations]);

  // Re-execute semantic search when filters change (if searching)
  useEffect(() => {
    if (searchValue.trim() && opened_corpus_id) {
      setSemanticSearchOffset(0);
      setSemanticSearchResults([]);
      setHasMoreSemanticResults(true);
      const timeoutId = setTimeout(() => {
        performSemanticSearch(searchValue, 0);
      }, 100);
      return () => clearTimeout(timeoutId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceFilter, typeFilter, opened_corpus_id]);

  // Shape data for the panel - use semantic search results when searching
  const annotation_items = useMemo(() => {
    if (isSemanticSearchActive) {
      return semanticSearchResults.map((result) => result.annotation);
    }
    const edges = annotation_response?.annotations?.edges || [];
    return edges
      .map((edge) => (edge ? edge.node : undefined))
      .filter((item): item is ServerAnnotationType => !!item);
  }, [annotation_response, isSemanticSearchActive, semanticSearchResults]);

  // Create similarity score map for semantic search results
  const similarityScoreMap = useMemo(() => {
    const map = new Map<string, number>();
    if (isSemanticSearchActive) {
      semanticSearchResults.forEach((result) => {
        map.set(result.annotation.id, result.similarityScore);
      });
    }
    return map;
  }, [isSemanticSearchActive, semanticSearchResults]);

  // Handle annotation click - navigate to document
  const handleAnnotationClick = useCallback(
    (annotation: ServerAnnotationType) => {
      if (!annotation?.document) {
        toast.error("Unable to open annotation: Document not available");
        return;
      }

      const queryParams: {
        annotationIds: string[];
        analysisIds?: string[];
      } = {
        annotationIds: [annotation.id],
      };

      if (annotation.analysis?.id) {
        queryParams.analysisIds = [annotation.analysis.id];
      }

      const url = getDocumentUrl(
        annotation.document,
        annotation.corpus ?? null,
        queryParams
      );

      if (url !== "#") {
        navigate(url);
      } else {
        toast.warning(
          "Unable to navigate: Document is missing required information"
        );
      }
    },
    [navigate]
  );

  // Handle search input change - triggers debounced semantic search
  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchValue(value);
      debouncedSearch.current(value);
    },
    [debouncedSearch]
  );

  // Handle search submit - immediate semantic search
  const handleSearchSubmit = useCallback(
    (value: string) => {
      debouncedSearch.current.cancel();
      setSearchValue(value);

      if (value.trim()) {
        setSemanticSearchOffset(0);
        setSemanticSearchResults([]);
        setHasMoreSemanticResults(true);
        performSemanticSearch(value, 0);
      } else {
        setSemanticSearchResults([]);
        setSemanticSearchOffset(0);
        setHasMoreSemanticResults(true);
      }
    },
    [performSemanticSearch, debouncedSearch]
  );

  return (
    <AnnotationsPanel
      items={annotation_items}
      loading={
        isSemanticSearchActive ? semanticSearchLoading : annotation_loading
      }
      pageInfo={annotation_response?.annotations?.pageInfo}
      typeFilter={typeFilter}
      sourceFilter={sourceFilter}
      searchValue={searchValue}
      onTypeFilterChange={setTypeFilter}
      onSourceFilterChange={setSourceFilter}
      onSearchChange={handleSearchChange}
      onSearchSubmit={handleSearchSubmit}
      onFetchMore={handleFetchMore}
      onItemClick={handleAnnotationClick}
      similarityScores={similarityScoreMap}
      searchError={semanticSearchError}
      isSemanticSearch={isSemanticSearchActive}
      style={{ minHeight: "70vh" }}
      emptyStateMessage="No annotations found in this corpus"
    />
  );
};
