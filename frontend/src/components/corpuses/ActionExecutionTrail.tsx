import React, { useState, useCallback, useRef, useEffect } from "react";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { Dropdown, Spinner } from "@os-legal/ui";
import { AlertTriangle, History, RefreshCw } from "lucide-react";
import { ActionExecutionRow } from "./ActionExecutionRow";
import {
  GET_CORPUS_ACTION_EXECUTIONS,
  GET_CORPUS_ACTIONS,
  GetCorpusActionExecutionsInput,
  GetCorpusActionExecutionsOutput,
  GetCorpusActionsInput,
  GetCorpusActionsOutput,
} from "../../graphql/queries";

interface ActionExecutionTrailProps {
  corpusId: string;
}

const TrailContainer = styled.div`
  width: 100%;
`;

const FiltersRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;

  @media (max-width: 768px) {
    gap: 8px;
  }

  @media (max-width: 480px) {
    flex-direction: column;
    align-items: stretch;
  }
`;

const FilterGroup = styled.div`
  min-width: 130px;

  @media (max-width: 480px) {
    min-width: 100%;
  }
`;

const ResultsInfo = styled.div`
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.8rem;
  margin-left: auto;

  @media (max-width: 480px) {
    margin-left: 0;
    margin-top: 4px;
  }
`;

const ExecutionsList = styled.div`
  margin-top: 8px;
  max-height: 500px;
  overflow-y: auto;
  padding-right: 4px;

  /* Subtle scrollbar styling */
  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-track {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    border-radius: 3px;
  }
  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 3px;
  }
  &::-webkit-scrollbar-thumb:hover {
    background: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const LoadingMore = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-size: 0.8rem;
  gap: 8px;
`;

const ScrollSentinel = styled.div`
  height: 1px;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 40px 20px;
  color: ${OS_LEGAL_COLORS.textMuted};

  .empty-icon {
    font-size: 2rem;
    margin-bottom: 12px;
    opacity: 0.4;
  }

  .empty-title {
    font-size: 0.95rem;
    font-weight: 500;
    color: ${OS_LEGAL_COLORS.textSecondary};
    margin-bottom: 4px;
  }

  .empty-description {
    font-size: 0.85rem;
  }
`;

const LoadingContainer = styled.div`
  text-align: center;
  padding: 40px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const ErrorState = styled.div`
  text-align: center;
  padding: 40px 20px;
  color: ${OS_LEGAL_COLORS.danger};

  .error-icon {
    font-size: 2rem;
    margin-bottom: 12px;
    opacity: 0.7;
  }

  .error-title {
    font-size: 0.95rem;
    font-weight: 500;
    color: ${OS_LEGAL_COLORS.dangerText};
    margin-bottom: 4px;
  }

  .error-description {
    font-size: 0.85rem;
    color: ${OS_LEGAL_COLORS.dangerHover};
  }
`;

const RetryButton = styled.button`
  margin-top: 16px;
  padding: 8px 16px;
  background: ${OS_LEGAL_COLORS.danger};
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.2s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.dangerHover};
  }

  &:focus {
    outline: 2px solid ${OS_LEGAL_COLORS.danger};
    outline-offset: 2px;
  }
`;

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "queued", label: "Queued" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
];

const TYPE_OPTIONS = [
  { value: "", label: "All Types" },
  { value: "fieldset", label: "Fieldset" },
  { value: "analyzer", label: "Analyzer" },
  { value: "agent", label: "Agent" },
];

const TIME_RANGE_OPTIONS = [
  { value: "", label: "All Time" },
  { value: "1", label: "Last Hour" },
  { value: "24", label: "Last 24 Hours" },
  { value: "168", label: "Last 7 Days" },
  { value: "720", label: "Last 30 Days" },
];

const PAGE_SIZE = 25;

/**
 * ActionExecutionTrail - Displays corpus action execution history
 *
 * Features:
 * - Compact row-based view with expand for details
 * - Filtering by status, type, action, time range
 * - Pagination with load more
 * - Responsive layout
 *
 * Routing Compliance:
 * - Uses getDocumentUrl utility
 * - Never sets reactive vars directly
 */
export const ActionExecutionTrail: React.FC<ActionExecutionTrailProps> = ({
  corpusId,
}) => {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [actionFilter, setActionFilter] = useState<string>("");
  const [timeRangeHours, setTimeRangeHours] = useState<string>("");

  const sinceDateTime = timeRangeHours
    ? new Date(
        Date.now() - parseInt(timeRangeHours) * 60 * 60 * 1000
      ).toISOString()
    : undefined;

  // Fetch actions for filter dropdown
  const { data: actionsData } = useQuery<
    GetCorpusActionsOutput,
    GetCorpusActionsInput
  >(GET_CORPUS_ACTIONS, {
    variables: { corpusId },
    fetchPolicy: "cache-first",
  });

  const actionOptions = [
    { value: "", label: "All Actions" },
    ...(actionsData?.corpusActions?.edges?.map(({ node }) => ({
      value: node.id,
      label: node.name,
    })) || []),
  ];

  // Fetch executions
  const {
    data: executionsData,
    loading: executionsLoading,
    error: executionsError,
    fetchMore,
    refetch,
  } = useQuery<GetCorpusActionExecutionsOutput, GetCorpusActionExecutionsInput>(
    GET_CORPUS_ACTION_EXECUTIONS,
    {
      variables: {
        corpusId,
        corpusActionId: actionFilter || undefined,
        status: statusFilter || undefined,
        actionType: typeFilter || undefined,
        since: sinceDateTime,
        first: PAGE_SIZE,
      },
      fetchPolicy: "cache-and-network",
      notifyOnNetworkStatusChange: true,
    }
  );

  const executions = executionsData?.corpusActionExecutions?.edges || [];
  const hasMore = executionsData?.corpusActionExecutions?.pageInfo?.hasNextPage;
  const totalCount = executionsData?.corpusActionExecutions?.totalCount || 0;

  // Infinite scroll sentinel ref
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadingMoreRef = useRef(false);

  const handleLoadMore = useCallback(() => {
    if (
      !executionsData?.corpusActionExecutions?.pageInfo?.hasNextPage ||
      loadingMoreRef.current
    )
      return;

    loadingMoreRef.current = true;
    fetchMore({
      variables: {
        after: executionsData.corpusActionExecutions.pageInfo.endCursor,
      },
      updateQuery: (prev, { fetchMoreResult }) => {
        loadingMoreRef.current = false;
        if (!fetchMoreResult) return prev;
        return {
          corpusActionExecutions: {
            ...fetchMoreResult.corpusActionExecutions,
            edges: [
              ...prev.corpusActionExecutions.edges,
              ...fetchMoreResult.corpusActionExecutions.edges,
            ],
          },
        };
      },
    });
  }, [executionsData, fetchMore]);

  // Infinite scroll observer
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !executionsLoading) {
          handleLoadMore();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, executionsLoading, handleLoadMore]);

  return (
    <TrailContainer>
      <FiltersRow role="search" aria-label="Filter action executions">
        <FilterGroup>
          <Dropdown
            mode="select"
            fluid
            options={STATUS_OPTIONS}
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as string)}
            aria-label="Filter by status"
            placeholder="Status"
            clearable={false}
          />
        </FilterGroup>

        <FilterGroup>
          <Dropdown
            mode="select"
            fluid
            options={TYPE_OPTIONS}
            value={typeFilter}
            onChange={(value) => setTypeFilter(value as string)}
            aria-label="Filter by type"
            placeholder="Type"
            clearable={false}
          />
        </FilterGroup>

        <FilterGroup>
          <Dropdown
            mode="select"
            fluid
            options={actionOptions}
            value={actionFilter}
            onChange={(value) => setActionFilter(value as string)}
            aria-label="Filter by action"
            placeholder="Action"
            clearable={false}
          />
        </FilterGroup>

        <FilterGroup>
          <Dropdown
            mode="select"
            fluid
            options={TIME_RANGE_OPTIONS}
            value={timeRangeHours}
            onChange={(value) => setTimeRangeHours(value as string)}
            aria-label="Filter by time"
            placeholder="Time"
            clearable={false}
          />
        </FilterGroup>

        {totalCount > 0 && (
          <ResultsInfo role="status">
            {executions.length} of {totalCount}
          </ResultsInfo>
        )}
      </FiltersRow>

      {/* Loading State */}
      {executionsLoading && executions.length === 0 && !executionsError && (
        <LoadingContainer role="status">
          <Spinner size="sm" />
          <p style={{ marginTop: "12px" }}>Loading executions...</p>
        </LoadingContainer>
      )}

      {/* Error State */}
      {executionsError && (
        <ErrorState role="alert">
          <AlertTriangle size={32} className="error-icon" />
          <div className="error-title">Error Loading Executions</div>
          <div className="error-description">
            Unable to load execution history. Please try again later.
          </div>
          <RetryButton onClick={() => refetch()} aria-label="Retry loading">
            <RefreshCw size={14} />
            Retry
          </RetryButton>
        </ErrorState>
      )}

      {/* Empty State */}
      {!executionsLoading && !executionsError && executions.length === 0 && (
        <EmptyState role="status">
          <History size={32} className="empty-icon" />
          <div className="empty-title">No Executions Found</div>
          <div className="empty-description">
            {statusFilter || typeFilter || actionFilter || timeRangeHours
              ? "Try adjusting your filters."
              : "Executions will appear when documents are processed."}
          </div>
        </EmptyState>
      )}

      {/* Executions List with infinite scroll */}
      {!executionsError && executions.length > 0 && (
        <ExecutionsList role="list" aria-label="Action executions">
          {executions.map(({ node }) => (
            <ActionExecutionRow key={node.id} execution={node} />
          ))}

          {/* Infinite scroll sentinel */}
          <ScrollSentinel ref={sentinelRef} />

          {/* Loading more indicator */}
          {executionsLoading && executions.length > 0 && (
            <LoadingMore>
              <Spinner size="sm" />
              Loading more...
            </LoadingMore>
          )}
        </ExecutionsList>
      )}
    </TrailContainer>
  );
};
