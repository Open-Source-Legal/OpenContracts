import React, { useMemo } from "react";
import styled from "styled-components";
import { useQuery } from "@apollo/client";
import { useAtom } from "jotai";
import {
  GET_CONVERSATIONS,
  GetConversationsInputs,
  GetConversationsOutputs,
} from "../../graphql/queries";
import { ConversationType } from "../../types/graphql-api";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";
import { threadSortAtom, threadFiltersAtom } from "../../atoms/threadAtoms";
import { ThreadListItem } from "./ThreadListItem";
import { ThreadSortDropdown } from "./ThreadSortDropdown";
import { ThreadFilterToggles } from "./ThreadFilterToggles";
import { CreateThreadButton } from "./CreateThreadButton";
import { calculateThreadUpvotes, getLastActivityTime } from "./utils";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { PlaceholderCard } from "../placeholders/PlaceholderCard";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";

interface ThreadListProps {
  corpusId?: string;
  documentId?: string;
  embedded?: boolean;
  /** Show create button (requires corpusId) */
  showCreateButton?: boolean;
  /** Show moderator filters (deleted threads) */
  showModeratorFilters?: boolean;
  /** Optional callback when thread is clicked (overrides default navigation) */
  onThreadClick?: (threadId: string) => void;
}

const ThreadListContainer = styled.div<{ $embedded?: boolean }>`
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: ${(props) => (props.$embedded ? "1rem" : "1.5rem")};
  max-width: ${(props) => (props.$embedded ? "100%" : "1200px")};
  margin: 0 auto;
  width: 100%;

  @media (max-width: 768px) {
    padding: ${(props) => (props.$embedded ? "0.75rem" : "1rem")};
    gap: 0.75rem;
  }

  @media (max-width: 480px) {
    padding: 0.75rem;
    gap: 0.625rem;
  }
`;

const ThreadGrid = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;

  @media (max-width: 480px) {
    gap: 0.5rem;
  }
`;

const ThreadListHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  gap: 0.75rem;

  @media (max-width: 768px) {
    margin-bottom: 0.75rem;
  }
`;

const Title = styled.h2`
  font-size: 24px;
  font-weight: 700;
  color: ${color.N10};
  margin: 0;

  @media (max-width: 640px) {
    font-size: 20px;
  }
`;

const HeaderActions = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;

  @media (max-width: 900px) {
    gap: 0.75rem;
  }

  @media (max-width: 640px) {
    flex-direction: column;
    align-items: stretch;
    width: 100%;
    gap: 0.5rem;
  }
`;

/**
 * Thread list component
 * Displays list of discussion threads with sorting, filtering, and pagination
 */
export function ThreadList({
  corpusId,
  documentId,
  embedded = false,
  showCreateButton = true,
  showModeratorFilters = false,
  onThreadClick,
}: ThreadListProps) {
  const [sortBy] = useAtom(threadSortAtom);
  const [filters] = useAtom(threadFiltersAtom);

  // Fetch threads
  const { data, loading, error, refetch, fetchMore } = useQuery<
    GetConversationsOutputs,
    GetConversationsInputs
  >(GET_CONVERSATIONS, {
    variables: {
      corpusId,
      documentId,
      conversationType: "THREAD",
      limit: 20,
    },
    // Refetch every 30 seconds for new threads
    pollInterval: 30000,
    fetchPolicy: "cache-and-network",
  });

  // Process and sort threads
  const processedThreads = useMemo(() => {
    let threads =
      data?.conversations?.edges
        ?.map((e) => e?.node)
        .filter((node): node is NonNullable<typeof node> => node != null) || [];

    // Apply filters
    if (!filters.showLocked) {
      threads = threads.filter((t) => !t?.isLocked);
    }
    if (!filters.showDeleted) {
      threads = threads.filter((t) => !t?.deletedAt);
    }

    // Apply sort
    threads = [...threads].sort((a, b) => {
      // Pinned threads always first (if not sorting by pinned)
      if (sortBy !== "pinned") {
        if (a?.isPinned && !b?.isPinned) return -1;
        if (!a?.isPinned && b?.isPinned) return 1;
      }

      switch (sortBy) {
        case "newest":
          return (
            new Date(b?.createdAt || 0).getTime() -
            new Date(a?.createdAt || 0).getTime()
          );

        case "active": {
          // Sort by most recent update
          const aTime = new Date(a?.updatedAt || a?.createdAt || 0).getTime();
          const bTime = new Date(b?.updatedAt || b?.createdAt || 0).getTime();
          return bTime - aTime;
        }

        case "upvoted": {
          // TODO: Calculate total upvotes from messages when available
          // For now, fall back to message count as proxy for activity
          const aCount = a?.chatMessages?.totalCount || 0;
          const bCount = b?.chatMessages?.totalCount || 0;
          return bCount - aCount;
        }

        case "pinned":
        default: {
          // Pinned first, then by creation date
          if (a?.isPinned && !b?.isPinned) return -1;
          if (!a?.isPinned && b?.isPinned) return 1;
          return (
            new Date(b?.createdAt || 0).getTime() -
            new Date(a?.createdAt || 0).getTime()
          );
        }
      }
    });

    return threads;
  }, [data, sortBy, filters]);

  // Handle load more for pagination
  const handleLoadMore = () => {
    if (data?.conversations?.pageInfo?.hasNextPage && fetchMore) {
      fetchMore({
        variables: {
          cursor: data.conversations.pageInfo.endCursor,
        },
      });
    }
  };

  // Loading state
  if (loading && !data) {
    return (
      <ThreadListContainer $embedded={embedded}>
        <ModernLoadingDisplay
          type="default"
          message="Loading discussions..."
          size="medium"
        />
      </ThreadListContainer>
    );
  }

  // Error state
  if (error) {
    return (
      <ThreadListContainer $embedded={embedded}>
        <ModernErrorDisplay
          type="generic"
          error={error.message}
          onRetry={() => refetch()}
        />
      </ThreadListContainer>
    );
  }

  // Empty state
  if (processedThreads.length === 0) {
    return (
      <ThreadListContainer $embedded={embedded}>
        {!embedded && (
          <ThreadListHeader>
            <Title>Discussions</Title>
            {showCreateButton && corpusId && (
              <CreateThreadButton corpusId={corpusId} />
            )}
          </ThreadListHeader>
        )}
        <PlaceholderCard
          title="No Discussions Yet"
          description={
            corpusId
              ? "Start the conversation by creating the first discussion thread."
              : "There are no discussions in this document yet."
          }
          compact
        />
      </ThreadListContainer>
    );
  }

  // Render thread list
  return (
    <ThreadListContainer $embedded={embedded}>
      {!embedded && (
        <ThreadListHeader>
          <Title>Discussions</Title>
          <HeaderActions>
            <ThreadSortDropdown />
            <ThreadFilterToggles showModeratorFilters={showModeratorFilters} />
            {showCreateButton && corpusId && (
              <CreateThreadButton corpusId={corpusId} />
            )}
          </HeaderActions>
        </ThreadListHeader>
      )}

      <ThreadGrid role="list" aria-label="Discussion threads">
        {processedThreads.map((thread) => (
          <ThreadListItem
            key={thread.id}
            thread={thread}
            corpusId={corpusId}
            compact={embedded}
            onThreadClick={onThreadClick}
          />
        ))}
      </ThreadGrid>

      {/* Infinite scroll trigger */}
      {data?.conversations?.pageInfo?.hasNextPage && (
        <FetchMoreOnVisible fetchNextPage={handleLoadMore} />
      )}
    </ThreadListContainer>
  );
}
