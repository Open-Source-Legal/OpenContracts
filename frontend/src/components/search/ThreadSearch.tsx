import React, { useState, useMemo } from "react";
import styled from "styled-components";
import { useQuery } from "@apollo/client";
import { SlidersHorizontal } from "lucide-react";
import {
  SEARCH_CONVERSATIONS,
  SearchConversationsInput,
  SearchConversationsOutput,
  ConversationSearchResult,
} from "../../graphql/queries";
import { SearchBar } from "./SearchBar";
import {
  SearchFilters,
  SearchFilters as SearchFiltersType,
} from "./SearchFilters";
import { SearchResults } from "./SearchResults";
import { color } from "../../theme/colors";

interface ThreadSearchProps {
  /** Pre-filter by corpus ID */
  corpusId?: string;
  /** Pre-filter by document ID */
  documentId?: string;
  /** Optional className for styling */
  className?: string;
}

const SearchContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;

  @media (max-width: 768px) {
    gap: 1rem;
  }
`;

const SearchSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

const ControlBar = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;

  @media (max-width: 640px) {
    flex-direction: column;
    align-items: stretch;
  }
`;

const FilterToggle = styled.button<{ $isActive: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  border: 1px solid ${(props) => (props.$isActive ? color.B5 : color.N4)};
  border-radius: 6px;
  background: ${(props) => (props.$isActive ? color.B1 : color.N1)};
  color: ${(props) => (props.$isActive ? color.B8 : color.N7)};
  font-weight: 500;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: ${color.B5};
    background: ${(props) => (props.$isActive ? color.B2 : color.N2)};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const FiltersPanel = styled.div<{ $isVisible: boolean }>`
  display: ${(props) => (props.$isVisible ? "block" : "none")};
  padding: 1rem;
  background: ${color.N2};
  border: 1px solid ${color.N4};
  border-radius: 8px;
`;

/**
 * Thread search component
 * Provides a search interface for finding discussions with filters and pagination
 */
export function ThreadSearch({
  corpusId,
  documentId,
  className,
}: ThreadSearchProps) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<SearchFiltersType>({
    corpusId: corpusId || null,
    conversationType: null,
  });

  // Debounce search query (wait 300ms after user stops typing)
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // GraphQL query
  const { data, loading, error, fetchMore } = useQuery<
    SearchConversationsOutput,
    SearchConversationsInput
  >(SEARCH_CONVERSATIONS, {
    variables: {
      query: debouncedQuery,
      corpusId: filters.corpusId || undefined,
      documentId: documentId || undefined,
      conversationType: filters.conversationType || undefined,
      topK: 100, // Fetch up to 100 results from vector store
      first: 20, // Initial page size
    },
    skip: !debouncedQuery || debouncedQuery.trim().length < 2,
    fetchPolicy: "cache-and-network",
  });

  // Extract results from paginated response
  const results = useMemo<ConversationSearchResult[]>(() => {
    if (!data?.searchConversations?.edges) return [];
    return data.searchConversations.edges.map((edge) => edge.node);
  }, [data]);

  const pageInfo = data?.searchConversations?.pageInfo;
  const totalCount = data?.searchConversations?.totalCount;

  // Handle load more for pagination
  const handleLoadMore = () => {
    if (pageInfo?.hasNextPage && fetchMore) {
      fetchMore({
        variables: {
          after: pageInfo.endCursor,
        },
      });
    }
  };

  const handleSubmit = () => {
    // Force immediate search (bypass debounce)
    if (query.trim().length >= 2) {
      setDebouncedQuery(query);
    }
  };

  const hasActiveFilters = filters.conversationType !== null;

  return (
    <SearchContainer className={className}>
      <SearchSection>
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={handleSubmit}
          placeholder="Search discussions by keywords..."
          autoFocus
        />

        <ControlBar>
          <FilterToggle
            $isActive={showFilters || hasActiveFilters}
            onClick={() => setShowFilters(!showFilters)}
            type="button"
            aria-label={showFilters ? "Hide filters" : "Show filters"}
            aria-expanded={showFilters}
          >
            <SlidersHorizontal />
            <span>Filters {hasActiveFilters && "(1)"}</span>
          </FilterToggle>
        </ControlBar>

        {showFilters && (
          <FiltersPanel $isVisible={showFilters}>
            <SearchFilters
              filters={filters}
              onChange={setFilters}
              fixedCorpusId={corpusId}
            />
          </FiltersPanel>
        )}
      </SearchSection>

      <SearchResults
        results={results}
        query={debouncedQuery}
        loading={loading}
        error={error}
        onLoadMore={handleLoadMore}
        hasNextPage={pageInfo?.hasNextPage}
        totalCount={totalCount}
      />
    </SearchContainer>
  );
}
