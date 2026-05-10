/**
 * ActivitySection Component
 *
 * Displays recent discussions in a compact activity feed format.
 * Uses the ActivityFeed component from @os-legal/ui.
 *
 * Note: Section header is now provided by parent (DiscoveryLanding)
 * to match the Storybook design pattern.
 */
import React from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { ActivityFeed } from "@os-legal/ui";
import type { ActivityItemData } from "@os-legal/ui";
import { GetRecentDiscussionsOutput } from "../../graphql/landing-queries";
import { getCorpusThreadUrl } from "../../utils/navigationUtils";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { getCreatorDisplay, getCreatorInitials } from "../../utils/userDisplay";

interface ActivitySectionProps {
  discussions: GetRecentDiscussionsOutput["conversations"]["edges"] | null;
  loading?: boolean;
  totalCount?: number;
}

const FeedWrapper = styled.div`
  background: white;
  border-radius: 16px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
`;

const SkeletonFeed = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

const SkeletonItem = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};

  &:last-child {
    border-bottom: none;
  }
`;

const SkeletonAvatar = styled.div`
  width: 40px;
  height: 40px;
  background: linear-gradient(
    90deg,
    ${OS_LEGAL_COLORS.border} 25%,
    ${OS_LEGAL_COLORS.surfaceLight} 50%,
    ${OS_LEGAL_COLORS.border} 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 50%;
  flex-shrink: 0;

  @keyframes shimmer {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }
`;

const SkeletonContent = styled.div`
  flex: 1;
`;

const SkeletonLine = styled.div<{ $width?: string; $height?: string }>`
  width: ${(props) => props.$width || "100%"};
  height: ${(props) => props.$height || "12px"};
  background: linear-gradient(
    90deg,
    ${OS_LEGAL_COLORS.border} 25%,
    ${OS_LEGAL_COLORS.surfaceLight} 50%,
    ${OS_LEGAL_COLORS.border} 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
  margin-bottom: 0.5rem;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 3rem 2rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

/**
 * Formats a relative time string from an ISO date string
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 30) {
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } else if (diffDays > 0) {
    return `${diffDays}d ago`;
  } else if (diffHours > 0) {
    return `${diffHours}h ago`;
  } else if (diffMins > 0) {
    return `${diffMins}m ago`;
  } else {
    return "Just now";
  }
}

/**
 * Gets consistent avatar color for a user based on their ID
 */
function getAvatarColor(userId?: string): string {
  const colors = [
    OS_LEGAL_COLORS.primaryBlue,
    OS_LEGAL_COLORS.greenMedium,
    OS_LEGAL_COLORS.folderIcon,
    OS_LEGAL_COLORS.dangerBorderHover,
    "#8B5CF6",
    "#EC4899",
  ];
  if (!userId) return colors[0];
  const hash = userId.split("").reduce((a, b) => a + b.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

export const ActivitySection: React.FC<ActivitySectionProps> = ({
  discussions,
  loading,
  totalCount,
}) => {
  const navigate = useNavigate();

  const handleViewAll = () => {
    navigate("/discussions");
  };

  // Transform discussions to activity items
  const activityItems: ActivityItemData[] =
    discussions?.map(({ node: discussion }) => {
      // Generate target URL for the discussion
      let targetUrl = "#";
      const corpus = discussion.chatWithCorpus;
      if (corpus) {
        // Corpus-scoped thread → link to full corpus thread view
        targetUrl = getCorpusThreadUrl(corpus, discussion.id);
      } else {
        // General discussion (no corpus) → link to global discussions page
        targetUrl = "/discussions";
      }

      return {
        id: discussion.id,
        name: getCreatorDisplay(discussion.creator),
        initials: getCreatorInitials(discussion.creator),
        action: "started discussion",
        target: discussion.title || "Untitled Discussion",
        targetUrl: targetUrl !== "#" ? targetUrl : undefined,
        time: formatRelativeTime(discussion.updatedAt),
        avatarColor: getAvatarColor(discussion.creator?.id),
      };
    }) || [];

  if (loading) {
    return (
      <FeedWrapper>
        <SkeletonFeed>
          {[1, 2, 3, 4, 5].map((i) => (
            <SkeletonItem key={i}>
              <SkeletonAvatar />
              <SkeletonContent>
                <SkeletonLine $width="70%" $height="14px" />
                <SkeletonLine $width="40%" $height="10px" />
              </SkeletonContent>
            </SkeletonItem>
          ))}
        </SkeletonFeed>
      </FeedWrapper>
    );
  }

  // Filter out any null nodes
  const validDiscussions = discussions?.filter((edge) => edge?.node) || [];

  if (validDiscussions.length === 0) {
    return (
      <FeedWrapper>
        <EmptyState>
          <p>No recent activity yet. Be the first to start a discussion!</p>
        </EmptyState>
      </FeedWrapper>
    );
  }

  return (
    <FeedWrapper>
      <ActivityFeed
        items={activityItems}
        dividers={true}
        viewAllText="View all discussions"
        onViewAll={handleViewAll}
      />
    </FeedWrapper>
  );
};
