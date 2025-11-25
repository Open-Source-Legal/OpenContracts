import React from "react";
import styled from "styled-components";
import { ApolloError } from "@apollo/client";
import { ConversationSearchResult } from "../../graphql/queries";
import { ThreadListItem } from "../threads/ThreadListItem";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { PlaceholderCard } from "../placeholders/PlaceholderCard";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import { color } from "../../theme/colors";

interface SearchResultsProps {
  results: ConversationSearchResult[];
  query: string;
  loading: boolean;
  error?: ApolloError;
  onLoadMore?: () => void;
  hasNextPage?: boolean;
  totalCount?: number;
  className?: string;
}

const ResultsContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

const ResultsHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid ${color.N4};
  margin-bottom: 0.5rem;
`;

const ResultCount = styled.div`
  font-size: 0.875rem;
  color: ${color.N7};
  font-weight: 500;

  strong {
    color: ${color.N10};
    font-weight: 600;
  }
`;

const ResultsList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;

  @media (max-width: 480px) {
    gap: 0.5rem;
  }
`;

/**
 * Search results component
 * Displays search results with loading, error, and empty states
 * Uses ThreadListItem for rendering individual results
 */
export function SearchResults({
  results,
  query,
  loading,
  error,
  onLoadMore,
  hasNextPage = false,
  totalCount,
  className,
}: SearchResultsProps) {
  // Loading state (initial)
  if (loading && results.length === 0) {
    return (
      <ResultsContainer className={className}>
        <ModernLoadingDisplay
          type="default"
          message="Searching discussions..."
          size="medium"
        />
      </ResultsContainer>
    );
  }

  // Error state
  if (error) {
    return (
      <ResultsContainer className={className}>
        <ModernErrorDisplay type="generic" error={error.message} />
      </ResultsContainer>
    );
  }

  // Empty state (no query)
  if (!query || query.trim().length === 0) {
    return (
      <ResultsContainer className={className}>
        <PlaceholderCard
          title="Start Searching"
          description="Enter a search query to find discussions across corpuses and documents."
          compact
        />
      </ResultsContainer>
    );
  }

  // Empty state (no results)
  if (results.length === 0) {
    return (
      <ResultsContainer className={className}>
        <PlaceholderCard
          title="No Results Found"
          description={`No discussions found matching "${query}". Try different keywords or filters.`}
          compact
        />
      </ResultsContainer>
    );
  }

  // Results found
  return (
    <ResultsContainer className={className}>
      {totalCount !== undefined && (
        <ResultsHeader>
          <ResultCount>
            Found <strong>{totalCount}</strong>{" "}
            {totalCount === 1 ? "result" : "results"} for "{query}"
          </ResultCount>
        </ResultsHeader>
      )}

      <ResultsList role="list" aria-label="Search results">
        {results.map((thread) => (
          <ThreadListItem
            key={thread.id}
            thread={thread as any}
            corpusId={thread.chatWithCorpus?.id}
          />
        ))}
      </ResultsList>

      {/* Infinite scroll trigger */}
      {hasNextPage && onLoadMore && (
        <FetchMoreOnVisible fetchNextPage={onLoadMore} />
      )}

      {/* Loading indicator for pagination */}
      {loading && results.length > 0 && (
        <ModernLoadingDisplay
          type="default"
          message="Loading more results..."
          size="small"
        />
      )}
    </ResultsContainer>
  );
}
