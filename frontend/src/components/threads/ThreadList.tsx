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
import { CONVERSATION_TYPE } from "../../assets/configurations/constants";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  mediaQuery,
} from "./styles/discussionStyles";
import { threadSortAtom, threadFiltersAtom } from "../../atoms/threadAtoms";
import { ThreadListItem } from "./ThreadListItem";
import { ThreadSortDropdown } from "./ThreadSortDropdown";
import { ThreadFilterToggles } from "./ThreadFilterToggles";
import { CreateThreadButton } from "./CreateThreadButton";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { PlaceholderCard } from "../placeholders/PlaceholderCard";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import {
  inferDiscussionCategory,
  DiscussionCategory,
} from "./DiscussionTypeBadge";

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
  /** Search query to filter threads by title */
  searchQuery?: string;
  /** Filter for threads with/without corpus */
  hasCorpus?: boolean;
  /** Filter for threads with/without document */
  hasDocument?: boolean;
  /** Filter by discussion category */
  categoryFilter?: DiscussionCategory | "all";
}

const ThreadListContainer = styled.div<{ $embedded?: boolean }>`
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: ${(props) => (props.$embedded ? "16px 24px" : "32px 24px")};
  max-width: ${(props) => (props.$embedded ? "100%" : "900px")};
  margin: 0 auto;
  width: 100%;
  background: #fafafa;

  @media (max-width: 768px) {
    padding: ${(props) => (props.$embedded ? "12px 16px" : "24px 16px")};
    gap: 16px;
  }

  ${mediaQuery.mobile} {
    padding: 16px;
    gap: 12px;
  }
`;

const ThreadGrid = styled.div`
  display: flex;
  flex-direction: column;
  gap: 16px;

  ${mediaQuery.mobile} {
    gap: 12px;
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
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 24px;
  font-weight: 400;
  color: #0f766e;
  margin: 0;

  ${mediaQuery.mobile} {
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

  ${mediaQuery.mobile} {
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
  searchQuery,
  hasCorpus,
  hasDocument,
  categoryFilter = "all",
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
      conversationType: CONVERSATION_TYPE.THREAD,
      limit: 20,
      title_Contains: searchQuery || undefined,
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

    // Apply corpus/document context filters
    if (hasCorpus === true) {
      threads = threads.filter((t) => t?.chatWithCorpus != null);
    } else if (hasCorpus === false) {
      threads = threads.filter((t) => t?.chatWithCorpus == null);
    }
    if (hasDocument === true) {
      threads = threads.filter((t) => t?.chatWithDocument != null);
    } else if (hasDocument === false) {
      threads = threads.filter((t) => t?.chatWithDocument == null);
    }

    // Apply filters
    if (!filters.showLocked) {
      threads = threads.filter((t) => !t?.isLocked);
    }
    if (!filters.showDeleted) {
      threads = threads.filter((t) => !t?.deletedAt);
    }

    // Apply category filter
    if (categoryFilter !== "all") {
      threads = threads.filter((t) => {
        const category = inferDiscussionCategory(
          t?.title || "",
          t?.description
        );
        return category === categoryFilter;
      });
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
          // Per-thread upvote aggregation requires a backend resolver.
          // Using message count as a proxy for activity until then.
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
  }, [data, sortBy, filters, hasCorpus, hasDocument, categoryFilter]);

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
