import React, { useMemo } from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { useReactiveVar } from "@apollo/client";
import { Eye, MessageCircle } from "lucide-react";
import { ConversationType } from "../../types/graphql-api";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  CORPUS_SHADOWS,
  CORPUS_TRANSITIONS,
  mediaQuery,
} from "./styles/discussionStyles";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { ThreadBadge } from "./ThreadBadge";
import {
  DiscussionTypeBadge,
  inferDiscussionCategory,
} from "./DiscussionTypeBadge";
import { RelativeTime } from "./RelativeTime";
import { getCorpusThreadUrl } from "../../utils/navigationUtils";
import { getCreatorDisplay, getCreatorInitials } from "../../utils/userDisplay";
import { ConversationVoteButtons } from "./ConversationVoteButtons";
import { backendUserObj } from "../../graphql/cache";

interface ThreadListItemProps {
  thread: ConversationType;
  corpusId?: string;
  compact?: boolean;
  /** Optional callback when thread is clicked (overrides default navigation) */
  onThreadClick?: (threadId: string) => void;
  /** Whether this thread is currently selected/active */
  isSelected?: boolean;
}

const ThreadCard = styled.div<{
  $isPinned?: boolean;
  $isDeleted?: boolean;
  $isSelected?: boolean;
}>`
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  padding: 20px 24px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  gap: 16px;
  position: relative;

  ${(props) =>
    props.$isSelected &&
    `
    border-left: 4px solid ${OS_LEGAL_COLORS.accent};
    background: #f0fdfa;
  `}

  ${(props) =>
    props.$isPinned &&
    !props.$isSelected &&
    `
    border-left: 4px solid ${OS_LEGAL_COLORS.accent};
    background: linear-gradient(135deg, #f0fdfa 0%, #ffffff 100%);
  `}

  ${(props) =>
    props.$isDeleted &&
    `
    opacity: 0.6;
    background: ${OS_LEGAL_COLORS.surfaceHover};
  `}

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-1px);
  }

  ${mediaQuery.mobile} {
    padding: 16px;
    gap: 12px;
  }
`;

const VoteSection = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  min-width: 2.5rem;
  padding-top: 0.25rem;

  ${mediaQuery.mobile} {
    min-width: 2rem;
  }
`;

const ContentSection = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const HeaderRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
`;

const BadgeGroup = styled.div`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  flex-wrap: wrap;
`;

const TagChip = styled.span`
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  background: ${CORPUS_COLORS.slate[100]};
  border-radius: ${CORPUS_RADII.full};
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.6875rem;
  font-weight: 500;
  color: ${CORPUS_COLORS.slate[600]};
`;

const Timestamp = styled.span`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  color: ${CORPUS_COLORS.slate[400]};
  white-space: nowrap;
  flex-shrink: 0;
`;

const ThreadTitle = styled.h3`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 20px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
  line-height: 1.4;

  ${mediaQuery.mobile} {
    font-size: 18px;
  }
`;

const ThreadDescription = styled.p`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 15px;
  color: ${OS_LEGAL_COLORS.textTertiary};
  margin: 0;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;

  ${mediaQuery.mobile} {
    font-size: 14px;
    -webkit-line-clamp: 1;
  }
`;

const FooterRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 0.25rem;
  flex-wrap: wrap;

  ${mediaQuery.mobile} {
    gap: 0.5rem;
  }
`;

const AuthorSection = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const AuthorAvatar = styled.div`
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: linear-gradient(
    135deg,
    ${CORPUS_COLORS.teal[600]} 0%,
    ${CORPUS_COLORS.teal[700]} 100%
  );
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${CORPUS_COLORS.white};
  font-family: ${CORPUS_FONTS.sans};
  font-weight: 600;
  font-size: 0.625rem;
  flex-shrink: 0;

  ${mediaQuery.mobile} {
    width: 1.25rem;
    height: 1.25rem;
    font-size: 0.5625rem;
  }
`;

const AuthorInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  flex-wrap: wrap;
`;

const AuthorName = styled.span`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textTertiary};

  ${mediaQuery.mobile} {
    font-size: 13px;
  }
`;

const AuthorTime = styled.span`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  color: ${CORPUS_COLORS.slate[400]};

  ${mediaQuery.mobile} {
    font-size: 0.6875rem;
  }
`;

const StatsSection = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;

  ${mediaQuery.mobile} {
    gap: 0.75rem;
  }
`;

const StatItem = styled.span`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.8125rem;
  color: ${CORPUS_COLORS.slate[500]};

  svg {
    width: 0.875rem;
    height: 0.875rem;
    color: ${CORPUS_COLORS.slate[400]};
  }

  ${mediaQuery.mobile} {
    font-size: 0.75rem;

    svg {
      width: 0.75rem;
      height: 0.75rem;
    }
  }
`;

const ParticipantAvatars = styled.div`
  display: flex;
  align-items: center;
`;

const ParticipantAvatar = styled.div<{ $index: number }>`
  width: 1.375rem;
  height: 1.375rem;
  border-radius: 50%;
  background: ${CORPUS_COLORS.teal[100]};
  border: 2px solid ${CORPUS_COLORS.white};
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.5625rem;
  font-weight: 600;
  color: ${CORPUS_COLORS.teal[700]};
  margin-left: ${(props) => (props.$index > 0 ? "-0.5rem" : "0")};
  position: relative;
  z-index: ${(props) => 10 - props.$index};

  ${mediaQuery.mobile} {
    width: 1.25rem;
    height: 1.25rem;
    font-size: 0.5rem;
    margin-left: ${(props) => (props.$index > 0 ? "-0.375rem" : "0")};
  }
`;

const MoreParticipants = styled.span`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.6875rem;
  color: ${CORPUS_COLORS.slate[500]};
  margin-left: 0.25rem;
`;

/**
 * Extract unique participants from thread messages
 */
function getParticipants(
  thread: ConversationType
): Array<{ id: string; initials: string }> {
  const participants = new Map<string, string>();

  // Add creator
  if (thread.creator) {
    participants.set(thread.creator.id, getCreatorInitials(thread.creator));
  }

  return Array.from(participants.entries()).map(([id, initials]) => ({
    id,
    initials,
  }));
}

/**
 * Individual thread card in list view.
 * Redesigned to match GitHub Discussions-style layout with:
 * - Upvote button on left
 * - Type badges and tags
 * - Author info with avatar
 * - Stats (views, comments, participants)
 */
export const ThreadListItem = React.memo(function ThreadListItem({
  thread,
  corpusId,
  compact = false,
  onThreadClick,
  isSelected = false,
}: ThreadListItemProps) {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(backendUserObj);
  const currentUserId = currentUser?.id;

  const handleClick = (e: React.MouseEvent) => {
    // Prevent navigation if clicking the vote button
    if ((e.target as HTMLElement).closest("[data-vote-button]")) {
      return;
    }

    if (onThreadClick) {
      onThreadClick(thread.id);
    } else {
      const corpus = thread.chatWithCorpus;
      if (corpus) {
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

  // Infer discussion category from title/description
  const category = useMemo(
    () => inferDiscussionCategory(thread.title || "", thread.description),
    [thread.title, thread.description]
  );

  // Get participants for avatars
  const participants = useMemo(() => getParticipants(thread), [thread]);

  // Placeholder view count (not tracked yet in backend)
  const viewCount = 0;

  const authorName = getCreatorDisplay(thread.creator);
  const authorInitials = getCreatorInitials(thread.creator);

  return (
    <ThreadCard
      $isPinned={thread.isPinned}
      $isDeleted={isDeleted}
      $isSelected={isSelected}
      onClick={handleClick}
      role="article"
      aria-label={`Thread: ${thread.title}`}
    >
      {/* Vote Section */}
      <VoteSection>
        <ConversationVoteButtons
          conversationId={thread.id}
          upvoteCount={thread.upvoteCount || 0}
          downvoteCount={thread.downvoteCount || 0}
          userVote={thread.userVote}
          creatorId={thread.creator?.id}
          currentUserId={currentUserId}
          disabled={isDeleted || thread.isLocked}
          upvoteOnly
        />
      </VoteSection>

      {/* Content Section */}
      <ContentSection>
        {/* Header Row - Badges and Timestamp */}
        <HeaderRow>
          <BadgeGroup>
            <DiscussionTypeBadge category={category} />
            {thread.isPinned && <ThreadBadge type="pinned" compact />}
            {thread.isLocked && <ThreadBadge type="locked" compact />}
            {isDeleted && <ThreadBadge type="deleted" compact />}
          </BadgeGroup>
          <Timestamp>
            <RelativeTime date={thread.createdAt || thread.created} />
          </Timestamp>
        </HeaderRow>

        {/* Title */}
        <ThreadTitle>{thread.title || "Untitled Discussion"}</ThreadTitle>

        {/* Description */}
        {thread.description && !compact && (
          <ThreadDescription>{thread.description}</ThreadDescription>
        )}

        {/* Footer Row - Author and Stats */}
        <FooterRow>
          <AuthorSection>
            <AuthorAvatar title={authorName}>{authorInitials}</AuthorAvatar>
            <AuthorInfo>
              <AuthorName>{authorName}</AuthorName>
              <AuthorTime>
                <RelativeTime date={thread.createdAt || thread.created} />
              </AuthorTime>
            </AuthorInfo>
          </AuthorSection>

          <StatsSection>
            {viewCount > 0 && (
              <StatItem title={`${viewCount} views`}>
                <Eye />
                <span>{viewCount}</span>
              </StatItem>
            )}
            <StatItem
              title={`${messageCount} ${
                messageCount === 1 ? "reply" : "replies"
              }`}
            >
              <MessageCircle />
              <span>{messageCount}</span>
            </StatItem>
            {participants.length > 0 && (
              <ParticipantAvatars title={`${participants.length} participants`}>
                {participants.slice(0, 3).map((p, i) => (
                  <ParticipantAvatar key={p.id} $index={i}>
                    {p.initials}
                  </ParticipantAvatar>
                ))}
                {participants.length > 3 && (
                  <MoreParticipants>
                    +{participants.length - 3}
                  </MoreParticipants>
                )}
              </ParticipantAvatars>
            )}
          </StatsSection>
        </FooterRow>
      </ContentSection>
    </ThreadCard>
  );
});
