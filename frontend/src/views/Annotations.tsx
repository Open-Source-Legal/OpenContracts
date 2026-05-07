import React, {
  useEffect,
  useRef,
  useState,
  useMemo,
  useCallback,
} from "react";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import _ from "lodash";

import { useQuery, useLazyQuery, useReactiveVar } from "@apollo/client";
import { FilterTabs } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import { FileText, AlignLeft, User, ChevronDown, PenLine } from "lucide-react";

import {
  authToken,
  annotationContentSearchTerm,
  filterToLabelsetId,
  openedCorpus,
  filterToCorpus,
  filterToLabelId,
  filterToStructuralAnnotations,
} from "../graphql/cache";
import {
  GetAnnotationsInputs,
  GetAnnotationsOutputs,
  GetCorpusLabelsetAndLabelsInputs,
  GetCorpusLabelsetAndLabelsOutputs,
  GET_ANNOTATIONS_FOR_CARDS,
  GET_CORPUS_LABELSET_AND_LABELS,
  SemanticSearchInput,
  SemanticSearchOutput,
  SemanticSearchResult,
  SEMANTIC_SEARCH_ANNOTATIONS,
} from "../graphql/queries";
import { ServerAnnotationType } from "../types/graphql-api";
import { getDocumentUrl } from "../utils/navigationUtils";
import {
  AnnotationsPanel,
  TypeFilterValue,
  SourceFilterValue,
} from "../components/annotations/AnnotationsPanel";
import {
  getAnnotationSource,
  getAnnotationLabelType,
} from "../components/annotations/ModernAnnotationCard";

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface LooseObject {
  [key: string]: any;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

const PageContainer = styled.div`
  height: 100%;
  background: ${OS_LEGAL_COLORS.background};
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  overflow-y: auto;
  overflow-x: hidden;
`;

const ContentContainer = styled.main`
  max-width: 1200px;
  margin: 0 auto;
  padding: 48px 24px 80px;

  @media (max-width: 768px) {
    padding: 32px 16px 60px;
  }
`;

const HeroSection = styled.section`
  margin-bottom: 40px;
`;

const HeroHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 32px;

  @media (max-width: 768px) {
    flex-direction: column;
  }
`;

const HeroTitle = styled.h1`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 42px;
  font-weight: 400;
  line-height: 1.2;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 12px;

  span {
    color: ${OS_LEGAL_COLORS.accent};
  }

  @media (max-width: 768px) {
    font-size: 32px;
  }
`;

const HeroSubtitle = styled.p`
  font-size: 17px;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0;
  max-width: 500px;
`;

const StatsContainer = styled.div`
  margin-bottom: 32px;
  padding: 20px 24px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
`;

const StatsRow = styled.div`
  display: flex;
  align-items: center;
  gap: 32px;
  flex-wrap: wrap;

  @media (max-width: 768px) {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }
`;

const StatItem = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;

  @media (max-width: 768px) {
    padding: 12px;
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-radius: 8px;
  }
`;

const StatIcon = styled.div`
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${OS_LEGAL_COLORS.successSurface};
  border-radius: 10px;
  color: ${OS_LEGAL_COLORS.accent};
`;

const StatContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const StatValue = styled.div`
  font-size: 24px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  line-height: 1;
`;

const StatLabel = styled.div`
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const StatDivider = styled.div`
  width: 1px;
  height: 40px;
  background: ${OS_LEGAL_COLORS.border};

  @media (max-width: 768px) {
    display: none;
  }
`;

const AdvancedFiltersToggle = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
`;

const FilterDropdown = styled.button<{ $active?: boolean }>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 500;
  color: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textSecondary};
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.successSurface : "white"};
  border: 1px solid
    ${(props) =>
      props.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover {
    border-color: ${(props) =>
      props.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.borderHover};
    color: ${(props) =>
      props.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textPrimary};
  }
`;

const AdvancedFiltersContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px;
  margin-bottom: 16px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
`;

const FilterWidgetWrapper = styled.div`
  flex: 1;
  min-width: 200px;
  max-width: 300px;

  @media (max-width: 768px) {
    min-width: 100%;
    max-width: none;
  }
`;

const PanelWrapper = styled.div`
  /* Override AnnotationsPanel's internal padding since we handle layout here */
  > div {
    padding: 0;
    background: transparent;
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// FILTER COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

import { FilterToStructuralAnnotationsSelector } from "../components/widgets/model-filters/FilterStructuralAnnotations";
import { FilterToLabelsetSelector } from "../components/widgets/model-filters/FilterToLabelsetSelector";
import { FilterToCorpusSelector } from "../components/widgets/model-filters/FilterToCorpusSelector";
import { FilterToLabelSelector } from "../components/widgets/model-filters/FilterToLabelSelector";
import { LabelType } from "../types/graphql-api";

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

const SEMANTIC_SEARCH_LIMIT = 20;

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export const Annotations = () => {
  const navigate = useNavigate();

  // Reactive vars for existing filtering
  const annotation_search_term = useReactiveVar(annotationContentSearchTerm);
  const filter_to_labelset_id = useReactiveVar(filterToLabelsetId);
  const filtered_to_corpus = useReactiveVar(filterToCorpus);
  const filter_to_label_id = useReactiveVar(filterToLabelId);
  const opened_corpus = useReactiveVar(openedCorpus);
  const auth_token = useReactiveVar(authToken);
  const exclude_structural_annotations = useReactiveVar(
    filterToStructuralAnnotations
  );

  // Local state for filters
  const [typeFilter, setTypeFilter] = useState<TypeFilterValue>("all");
  const [sourceFilter, setSourceFilter] = useState<SourceFilterValue>("all");
  const [searchValue, setSearchValue] = useState("");
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);

  // Semantic search state
  const [semanticSearchOffset, setSemanticSearchOffset] = useState(0);
  const [semanticSearchResults, setSemanticSearchResults] = useState<
    SemanticSearchResult[]
  >([]);
  const [hasMoreSemanticResults, setHasMoreSemanticResults] = useState(true);

  // Number of annotations to load per page
  const ANNOTATIONS_PAGE_SIZE = 20;

  // Build query variables
  let annotation_variables: LooseObject = {
    label_Type: "TEXT_LABEL",
    limit: ANNOTATIONS_PAGE_SIZE,
  };

  if (exclude_structural_annotations === "EXCLUDE") {
    annotation_variables["structural"] = false;
  } else if (exclude_structural_annotations === "ONLY") {
    annotation_variables["structural"] = true;
  }

  if (annotation_search_term) {
    annotation_variables["rawText_Contains"] = annotation_search_term;
  }
  if (filter_to_labelset_id) {
    annotation_variables["usesLabelFromLabelsetId"] = filter_to_labelset_id;
  }
  if (filtered_to_corpus) {
    annotation_variables["corpusId"] = filtered_to_corpus.id;
  }
  if (filter_to_label_id) {
    annotation_variables["annotationLabelId"] = filter_to_label_id;
  }

  // GraphQL queries
  const {
    refetch: refetch_annotations,
    loading: annotation_loading,
    data: annotation_data,
    fetchMore: fetchMoreAnnotations,
  } = useQuery<GetAnnotationsOutputs, GetAnnotationsInputs>(
    GET_ANNOTATIONS_FOR_CARDS,
    {
      variables: annotation_variables,
      notifyOnNetworkStatusChange: true,
    }
  );

  const { refetch: refetch_corpus } = useQuery<
    GetCorpusLabelsetAndLabelsOutputs,
    GetCorpusLabelsetAndLabelsInputs
  >(GET_CORPUS_LABELSET_AND_LABELS, {
    variables: {
      corpusId: filtered_to_corpus?.id || opened_corpus?.id || "",
    },
    skip: !filtered_to_corpus?.id && !opened_corpus?.id,
    notifyOnNetworkStatusChange: true,
  });

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
            setSemanticSearchResults(newResults);
          } else {
            setSemanticSearchResults((prev) => [...prev, ...newResults]);
          }
          setHasMoreSemanticResults(
            newResults.length === SEMANTIC_SEARCH_LIMIT
          );
        }
      },
    }
  );

  // Determine if we're in semantic search mode
  const isSemanticSearchActive = searchValue.trim().length > 0;

  // Consolidated effect for refetching annotations on filter changes
  useEffect(() => {
    refetch_annotations();
  }, [
    filter_to_label_id,
    filter_to_labelset_id,
    filtered_to_corpus,
    annotation_search_term,
    exclude_structural_annotations,
    auth_token,
    refetch_annotations,
  ]);

  useEffect(() => {
    if (opened_corpus) {
      refetch_annotations();
      refetch_corpus();
    }
  }, [opened_corpus, refetch_annotations, refetch_corpus]);

  // Sync source filter with structural annotations reactive var
  useEffect(() => {
    if (sourceFilter === "structural") {
      filterToStructuralAnnotations("ONLY");
    } else if (sourceFilter === "human" || sourceFilter === "agent") {
      filterToStructuralAnnotations("EXCLUDE");
    } else {
      filterToStructuralAnnotations("INCLUDE");
    }
  }, [sourceFilter]);

  // Re-execute semantic search when filters change
  useEffect(() => {
    if (searchValue.trim()) {
      setSemanticSearchOffset(0);
      setSemanticSearchResults([]);
      setHasMoreSemanticResults(true);
      const timeoutId = setTimeout(() => {
        performSemanticSearch(searchValue, 0);
      }, 100);
      return () => clearTimeout(timeoutId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered_to_corpus?.id, sourceFilter, typeFilter]);

  // Get raw items from query
  const rawItems: ServerAnnotationType[] = useMemo(() => {
    if (isSemanticSearchActive) {
      return semanticSearchResults.map((result) => result.annotation);
    }
    if (annotation_data?.annotations) {
      return annotation_data.annotations.edges.map((edge) => edge.node);
    }
    return [];
  }, [annotation_data, isSemanticSearchActive, semanticSearchResults]);

  // Create similarity score map
  const similarityScoreMap = useMemo(() => {
    const map = new Map<string, number>();
    if (isSemanticSearchActive) {
      semanticSearchResults.forEach((result) => {
        map.set(result.annotation.id, result.similarityScore);
      });
    }
    return map;
  }, [isSemanticSearchActive, semanticSearchResults]);

  // Calculate stats
  // NOTE: total comes from the server-side totalCount and is accurate.
  // The breakdown counts (docLabels/textLabels/humanAnnotated) are derived
  // from the items currently loaded into the client (initial page +
  // anything fetched via infinite scroll). With totals in the tens of
  // thousands these are necessarily partial; the labels below disclose
  // this so the tiles aren't misread as "0 doc labels exist" when they
  // really mean "0 in the loaded batch" (issue #1560).
  const stats = useMemo(() => {
    const total = annotation_data?.annotations?.totalCount ?? rawItems.length;
    const loadedCount = rawItems.length;
    const isPartial = total > loadedCount;
    const docLabels = rawItems.filter(
      (item) => getAnnotationLabelType(item) === "doc"
    ).length;
    const textLabels = rawItems.filter(
      (item) => getAnnotationLabelType(item) === "text"
    ).length;
    const humanAnnotated = rawItems.filter(
      (item) => getAnnotationSource(item) === "human"
    ).length;

    return {
      total,
      loadedCount,
      isPartial,
      docLabels,
      textLabels,
      humanAnnotated,
    };
  }, [rawItems, annotation_data?.annotations?.totalCount]);

  const partialBreakdownTooltip = stats.isPartial
    ? `Counted from ${stats.loadedCount.toLocaleString()} of ${stats.total.toLocaleString()} loaded so far. Scroll to load more.`
    : undefined;
  const partialBreakdownSuffix = stats.isPartial ? " (in view)" : "";

  // Execute semantic search with current filters
  const performSemanticSearch = useCallback(
    (query: string, offset: number = 0) => {
      if (!query.trim()) return;

      const variables: SemanticSearchInput = {
        query: query.trim(),
        limit: SEMANTIC_SEARCH_LIMIT,
        offset,
      };

      if (filtered_to_corpus?.id) {
        variables.corpusId = filtered_to_corpus.id;
      }

      executeSemanticSearch({ variables });
    },
    [executeSemanticSearch, filtered_to_corpus]
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

  useEffect(() => {
    return () => {
      debouncedSearch.current.cancel();
    };
  }, []);

  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchValue(value);
      debouncedSearch.current(value);
    },
    [debouncedSearch]
  );

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

  // Handle infinite scroll
  const handleFetchMore = useCallback(() => {
    if (isSemanticSearchActive) {
      if (!semanticSearchLoading && hasMoreSemanticResults) {
        const newOffset = semanticSearchOffset + SEMANTIC_SEARCH_LIMIT;
        setSemanticSearchOffset(newOffset);
        performSemanticSearch(searchValue, newOffset);
      }
    } else {
      const pageInfo = annotation_data?.annotations?.pageInfo;
      if (!annotation_loading && pageInfo?.hasNextPage) {
        fetchMoreAnnotations({
          variables: {
            limit: ANNOTATIONS_PAGE_SIZE,
            cursor: pageInfo.endCursor,
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
    annotation_data,
    fetchMoreAnnotations,
  ]);

  // Handle annotation click
  const handleAnnotationClick = useCallback(
    (annotation: ServerAnnotationType) => {
      try {
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
      } catch (error) {
        console.error("Error navigating to annotation:", error);
        toast.error("An error occurred while opening the annotation");
      }
    },
    [navigate]
  );

  return (
    <PageContainer>
      <ContentContainer>
        {/* Hero Section */}
        <HeroSection>
          <HeroHeader>
            <div>
              <HeroTitle>
                Browse <span>annotations</span>
              </HeroTitle>
              <HeroSubtitle>
                Explore and discover annotations across your documents. Filter
                by type, source, or visibility.
              </HeroSubtitle>
            </div>
          </HeroHeader>
        </HeroSection>

        {/* Stats Bar */}
        <StatsContainer>
          <StatsRow>
            <StatItem>
              <StatIcon>
                <PenLine size={20} />
              </StatIcon>
              <StatContent>
                <StatValue>{stats.total.toLocaleString()}</StatValue>
                <StatLabel>Total Annotations</StatLabel>
              </StatContent>
            </StatItem>
            <StatDivider />
            <StatItem title={partialBreakdownTooltip}>
              <StatIcon>
                <FileText size={20} />
              </StatIcon>
              <StatContent>
                <StatValue>{stats.docLabels}</StatValue>
                <StatLabel>Doc Labels{partialBreakdownSuffix}</StatLabel>
              </StatContent>
            </StatItem>
            <StatDivider />
            <StatItem title={partialBreakdownTooltip}>
              <StatIcon>
                <AlignLeft size={20} />
              </StatIcon>
              <StatContent>
                <StatValue>{stats.textLabels}</StatValue>
                <StatLabel>Text Labels{partialBreakdownSuffix}</StatLabel>
              </StatContent>
            </StatItem>
            <StatDivider />
            <StatItem title={partialBreakdownTooltip}>
              <StatIcon>
                <User size={20} />
              </StatIcon>
              <StatContent>
                <StatValue>{stats.humanAnnotated}</StatValue>
                <StatLabel>Human Annotated{partialBreakdownSuffix}</StatLabel>
              </StatContent>
            </StatItem>
          </StatsRow>
        </StatsContainer>

        {/* Advanced Filters Toggle */}
        <AdvancedFiltersToggle>
          <FilterDropdown
            $active={showAdvancedFilters}
            onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
          >
            Advanced Filters
            <ChevronDown size={14} />
          </FilterDropdown>
        </AdvancedFiltersToggle>

        {/* Advanced Filters (collapsible) */}
        {showAdvancedFilters && (
          <AdvancedFiltersContainer>
            <FilterWidgetWrapper>
              <FilterToLabelsetSelector
                fixed_labelset_id={
                  filtered_to_corpus?.labelSet?.id
                    ? filtered_to_corpus.labelSet.id
                    : undefined
                }
              />
            </FilterWidgetWrapper>
            <FilterWidgetWrapper>
              <FilterToCorpusSelector
                uses_labelset_id={filter_to_labelset_id}
              />
            </FilterWidgetWrapper>
            {(filter_to_labelset_id || filtered_to_corpus?.labelSet?.id) && (
              <FilterWidgetWrapper>
                <FilterToLabelSelector
                  label_type={LabelType.TokenLabel}
                  only_labels_for_labelset_id={
                    filter_to_labelset_id
                      ? filter_to_labelset_id
                      : filtered_to_corpus?.labelSet?.id
                      ? filtered_to_corpus.labelSet.id
                      : undefined
                  }
                />
              </FilterWidgetWrapper>
            )}
          </AdvancedFiltersContainer>
        )}

        {/* Annotations Panel */}
        <PanelWrapper>
          <AnnotationsPanel
            items={rawItems}
            loading={
              isSemanticSearchActive
                ? semanticSearchLoading
                : annotation_loading
            }
            pageInfo={annotation_data?.annotations?.pageInfo}
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
          />
        </PanelWrapper>
      </ContentContainer>
    </PageContainer>
  );
};

export default Annotations;
