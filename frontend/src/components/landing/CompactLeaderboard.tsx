/**
 * CompactLeaderboard Component
 *
 * Displays top contributors in a compact list format.
 * Uses Avatar and Chip components from @os-legal/ui.
 *
 * Note: Section header is provided by parent (DiscoveryLanding)
 * to match the Storybook design pattern.
 */
import React from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { Avatar, Chip } from "@os-legal/ui";
import { ArrowRight, Trophy } from "lucide-react";
import { LeaderboardEntry } from "../../graphql/landing-queries";
import { color } from "../../theme/colors";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  getLeaderboardAvatarColor as getAvatarColor,
  getLeaderboardInitials as getInitials,
} from "../../utils/leaderboardAvatar";
import { getCreatorDisplay } from "../../utils/userDisplay";

interface CompactLeaderboardProps {
  contributors: LeaderboardEntry[] | null;
  loading?: boolean;
}

const FeedWrapper = styled.div`
  background: white;
  border-radius: 16px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
`;

const LeaderboardList = styled.div`
  display: flex;
  flex-direction: column;
`;

const LeaderboardRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0.5rem;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.15s ease;

  &:hover {
    background-color: ${color.N2};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }
`;

const RankChip = styled.div<{ $rank: number }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;

  ${(props) =>
    props.$rank === 1
      ? `
    background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
    color: #8B4513;
  `
      : props.$rank === 2
      ? `
    background: linear-gradient(135deg, #C0C0C0 0%, #A0A0A0 100%);
    color: #4A4A4A;
  `
      : props.$rank === 3
      ? `
    background: linear-gradient(135deg, #CD7F32 0%, #B8860B 100%);
    color: white;
  `
      : `
    background: ${color.N3};
    color: ${color.N7};
  `}
`;

const UserInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 0.625rem;
  flex: 1;
  min-width: 0;
`;

const Username = styled.span`
  font-size: 0.9375rem;
  font-weight: 600;
  color: ${color.N10};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const BadgeGroup = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
`;

const UserBadge = styled.span<{ $color: string }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  font-size: 0.6875rem;
  background: ${(props) => props.$color}20;
`;

const ReputationDisplay = styled.div`
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  flex-shrink: 0;
  min-width: 48px;
`;

const ReputationValue = styled.span`
  font-size: 1rem;
  font-weight: 700;
  color: ${color.O7};
  line-height: 1.2;
`;

const ReputationLabel = styled.span`
  font-size: 0.625rem;
  font-weight: 500;
  color: ${color.N6};
  text-transform: uppercase;
  letter-spacing: 0.03em;
`;

const ViewAllButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  background: transparent;
  color: ${color.N7};
  border: 1px solid ${color.N4};
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${color.N2};
    color: ${color.N10};
    border-color: ${color.N5};
  }

  svg {
    width: 16px;
    height: 16px;
    transition: transform 0.15s ease;
  }

  &:hover svg {
    transform: translateX(2px);
  }
`;

const SkeletonList = styled.div`
  display: flex;
  flex-direction: column;
`;

const SkeletonRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0.5rem;

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }
`;

const SkeletonRank = styled.div`
  width: 28px;
  height: 28px;
  background: linear-gradient(
    90deg,
    ${OS_LEGAL_COLORS.border} 25%,
    ${OS_LEGAL_COLORS.surfaceLight} 50%,
    ${OS_LEGAL_COLORS.border} 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;
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

const SkeletonAvatar = styled.div`
  width: 32px;
  height: 32px;
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
`;

const SkeletonText = styled.div<{ $width?: string }>`
  width: ${(props) => props.$width || "100px"};
  height: 14px;
  background: linear-gradient(
    90deg,
    ${OS_LEGAL_COLORS.border} 25%,
    ${OS_LEGAL_COLORS.surfaceLight} 50%,
    ${OS_LEGAL_COLORS.border} 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
`;

const SkeletonRep = styled.div`
  width: 40px;
  height: 24px;
  background: linear-gradient(
    90deg,
    ${OS_LEGAL_COLORS.border} 25%,
    ${OS_LEGAL_COLORS.surfaceLight} 50%,
    ${OS_LEGAL_COLORS.border} 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
  margin-left: auto;
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 2rem 1rem;
  color: ${color.N6};
`;

const EmptyIcon = styled.div`
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: ${color.N2};
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 0.75rem;
  color: ${color.N5};
`;

const EmptyText = styled.p`
  font-size: 0.9375rem;
  margin: 0;
`;

export const CompactLeaderboard: React.FC<CompactLeaderboardProps> = ({
  contributors,
  loading,
}) => {
  const navigate = useNavigate();

  const handleRowClick = (contributor: LeaderboardEntry) => {
    if (contributor.slug) {
      navigate(`/users/${contributor.slug}`);
    } else {
      navigate("/leaderboard");
    }
  };

  const handleViewAll = () => {
    navigate("/leaderboard");
  };

  if (loading) {
    return (
      <FeedWrapper>
        <SkeletonList>
          {[1, 2, 3, 4, 5].map((i) => (
            <SkeletonRow key={i}>
              <SkeletonRank />
              <SkeletonAvatar />
              <SkeletonText $width="120px" />
              <SkeletonRep />
            </SkeletonRow>
          ))}
        </SkeletonList>
      </FeedWrapper>
    );
  }

  if (!contributors || contributors.length === 0) {
    return (
      <FeedWrapper>
        <EmptyState>
          <EmptyIcon>
            <Trophy size={24} />
          </EmptyIcon>
          <EmptyText>
            No contributors yet. Be the first to participate!
          </EmptyText>
        </EmptyState>
      </FeedWrapper>
    );
  }

  // Take top 5 contributors
  const topContributors = contributors.slice(0, 5);

  return (
    <FeedWrapper>
      <LeaderboardList>
        {topContributors.map((contributor, index) => {
          const rank = index + 1;
          const badges = contributor.badges?.edges?.slice(0, 3) || [];

          return (
            <LeaderboardRow
              key={contributor.id}
              onClick={() => handleRowClick(contributor)}
            >
              <RankChip $rank={rank}>{rank}</RankChip>

              <UserInfo>
                {/*
                  Avatar initials and visible username are both derived
                  from the public ``slug`` — the leaderboard is a public
                  surface that must never surface a user's chosen
                  ``displayName`` (which still falls back to the user's
                  real name for self-views). Backend already redacts
                  ``displayName`` to slug for non-self viewers, but
                  reading the slug field directly avoids any chance of
                  a stale Apollo cache entry leaking the self-view
                  rendering when a logged-in user looks at their own
                  row.
                */}
                <Avatar
                  size="sm"
                  fallback={getInitials(contributor.slug)}
                  style={{
                    backgroundColor: getAvatarColor(contributor.id),
                    color: "white",
                  }}
                />
                <Username>{getCreatorDisplay(contributor)}</Username>
              </UserInfo>

              {badges.length > 0 && (
                <BadgeGroup>
                  {badges.map(({ node: { badge } }) => (
                    <UserBadge
                      key={badge.id}
                      $color={badge.color || color.B5}
                      title={badge.name}
                    >
                      {badge.icon || "🏆"}
                    </UserBadge>
                  ))}
                </BadgeGroup>
              )}

              <ReputationDisplay>
                <ReputationValue>
                  {contributor.reputationGlobal || 0}
                </ReputationValue>
                <ReputationLabel>Rep</ReputationLabel>
              </ReputationDisplay>
            </LeaderboardRow>
          );
        })}
      </LeaderboardList>

      <ViewAllButton onClick={handleViewAll}>
        View Full Leaderboard
        <ArrowRight size={16} />
      </ViewAllButton>
    </FeedWrapper>
  );
};
