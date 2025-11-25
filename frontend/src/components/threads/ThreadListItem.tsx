import React from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { MessageCircle, ThumbsUp, User } from "lucide-react";
import { ConversationType } from "../../types/graphql-api";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";
import { ThreadBadge } from "./ThreadBadge";
import { RelativeTime } from "./RelativeTime";
import { getCorpusThreadUrl } from "../../utils/navigationUtils";

interface ThreadListItemProps {
  thread: ConversationType;
  corpusId?: string;
  compact?: boolean;
  /** Optional callback when thread is clicked (overrides default navigation) */
  onThreadClick?: (threadId: string) => void;
}

const ThreadCard = styled.div<{ $isPinned?: boolean; $isDeleted?: boolean }>`
  background: ${color.N2};
  border: 1px solid ${color.N4};
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.2s;

  ${(props) =>
    props.$isPinned &&
    `
    border-left: 4px solid ${color.B5};
    background: ${color.B1};
  `}

  ${(props) =>
    props.$isDeleted &&
    `
    opacity: 0.6;
    background: ${color.N3};
  `}

  &:hover {
    border-color: ${color.B5};
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    transform: translateY(-1px);
  }

  @media (max-width: 640px) {
    padding: 0.875rem;
  }
`;

const BadgeRow = styled.div`
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
`;

const ThreadTitle = styled.h3`
  font-size: 18px;
  font-weight: 600;
  color: ${color.N10};
  margin: 0 0 0.375rem 0;
  line-height: 1.4;

  @media (max-width: 640px) {
    font-size: 16px;
  }
`;

const ThreadDescription = styled.p`
  font-size: 14px;
  color: ${color.N7};
  margin: 0 0 1rem 0;
  line-height: 1.5;

  /* Truncate to 2 lines */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const ThreadMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  font-size: 13px;
  color: ${color.N6};
  flex-wrap: wrap;

  @media (max-width: 640px) {
    gap: 0.5rem;
    font-size: 12px;
  }
`;

const MetaItem = styled.span`
  display: flex;
  align-items: center;
  gap: 4px;
`;

const Separator = styled.span`
  color: ${color.N5};

  @media (max-width: 640px) {
    display: none;
  }
`;

/**
 * Individual thread card in list view
 */
export function ThreadListItem({
  thread,
  corpusId,
  compact = false,
  onThreadClick,
}: ThreadListItemProps) {
  const navigate = useNavigate();

  const handleClick = () => {
    // Use callback if provided, otherwise use default navigation
    if (onThreadClick) {
      onThreadClick(thread.id);
    } else {
      // Use the corpus from thread's chatWithCorpus (has full data with slug)
      const corpus = thread.chatWithCorpus;
      if (corpus) {
        // Use navigation utility for proper slug-based URL
        const url = getCorpusThreadUrl(corpus, thread.id);
        if (url !== "#") {
          navigate(url);
        } else {
          console.warn(
            "[ThreadListItem] Cannot navigate - corpus missing slug data",
            corpus
          );
        }
      } else {
        console.warn(
          "[ThreadListItem] Cannot navigate - thread has no corpus",
          thread
        );
      }
    }
  };

  const messageCount = thread.chatMessages?.totalCount || 0;
  const isDeleted = !!thread.deletedAt;

  return (
    <ThreadCard
      $isPinned={thread.isPinned}
      $isDeleted={isDeleted}
      onClick={handleClick}
      role="article"
      aria-label={`Thread: ${thread.title}`}
    >
      {/* Badges */}
      {(thread.isPinned || thread.isLocked || isDeleted) && (
        <BadgeRow>
          {thread.isPinned && <ThreadBadge type="pinned" compact={compact} />}
          {thread.isLocked && <ThreadBadge type="locked" compact={compact} />}
          {isDeleted && <ThreadBadge type="deleted" compact={compact} />}
        </BadgeRow>
      )}

      {/* Title */}
      <ThreadTitle>{thread.title || "Untitled Discussion"}</ThreadTitle>

      {/* Description */}
      {thread.description && !compact && (
        <ThreadDescription>{thread.description}</ThreadDescription>
      )}

      {/* Metadata */}
      <ThreadMeta>
        <MetaItem>
          <User size={14} />
          <span>{thread.creator?.username || thread.creator?.email}</span>
        </MetaItem>

        <Separator>•</Separator>

        <MetaItem>
          <RelativeTime date={thread.createdAt} />
        </MetaItem>

        <Separator>•</Separator>

        <MetaItem>
          <MessageCircle size={14} />
          <span>
            {messageCount} {messageCount === 1 ? "reply" : "replies"}
          </span>
        </MetaItem>

        {/* TODO: Add upvote count when available */}
        {/* <Separator>•</Separator>
        <MetaItem>
          <ThumbsUp size={14} />
          <span>{totalUpvotes}</span>
        </MetaItem> */}
      </ThreadMeta>
    </ThreadCard>
  );
}
