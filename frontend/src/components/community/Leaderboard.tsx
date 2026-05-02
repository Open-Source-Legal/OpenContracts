import React, { useState } from "react";
import { useQuery } from "@apollo/client";
import { Dropdown, StatBlock, StatGrid, Table } from "@os-legal/ui";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import {
  Trophy,
  Medal,
  TrendingUp,
  MessageSquare,
  Target,
  Star,
  Users,
  User,
} from "lucide-react";
import { ErrorMessage, InfoMessage, LoadingState } from "../widgets/feedback";
import {
  GET_LEADERBOARD,
  GET_COMMUNITY_STATS,
} from "../../graphql/queries/leaderboard/queries";
import {
  LeaderboardMetric,
  LeaderboardScope,
  Leaderboard as LeaderboardType,
  CommunityStats as CommunityStatsType,
  LeaderboardEntry,
} from "../../types/leaderboard";
import { Badge } from "../badges/Badge";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

// File-local rank palette. Centralised here so the three RankBadge ternaries
// stay readable and the values are easy to update in one place. These are
// intentionally not in OS_LEGAL_COLORS because they are leaderboard-specific.
const RANK_COLORS = {
  gold: { bg: "#fef3c7", border: "#fde68a", text: "#b45309" },
  silver: {
    bg: OS_LEGAL_COLORS.surfaceLight,
    border: OS_LEGAL_COLORS.border,
    text: OS_LEGAL_COLORS.textTertiary,
  },
  bronze: { bg: "#fed7aa", border: "#fdba74", text: "#9a3412" },
} as const;

// File-local "rising star" tag palette (orange/amber tints).
const RISING_STAR_COLORS = {
  bg: "#fff7ed",
  border: "#fed7aa",
  text: "#c2410c",
} as const;

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS - Aligned with CorpusListView / OS Legal design system
// ═══════════════════════════════════════════════════════════════════════════════

const PageContainer = styled.div`
  height: 100%;
  background: ${OS_LEGAL_COLORS.background};
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  overflow-y: auto;
  overflow-x: hidden;
`;

const ContentContainer = styled.div`
  max-width: 900px;
  margin: 0 auto;
  padding: 48px 24px 80px;

  @media (max-width: 768px) {
    padding: 32px 16px 60px;
  }
`;

const HeroSection = styled.section`
  margin-bottom: 32px;
`;

const HeroTitle = styled.h1`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 42px;
  font-weight: 400;
  line-height: 1.2;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 16px;

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
  margin: 0 0 32px;
  max-width: 600px;
`;

const StatsContainer = styled.div`
  margin-bottom: 48px;
  padding: 32px 0;

  /*
   * StatBlock's default value font-size is already 36px on the md breakpoint
   * (see .oc-stat-block__value in @os-legal/ui), and drops to 28px only at
   * <= 480px. We tighten the breakpoint so it shrinks at <= 768px instead,
   * targeting the documented BEM class so we're not coupled to a test ID.
   */
  @media (max-width: 768px) {
    padding: 24px 0;

    .oc-stat-block__value {
      font-size: 28px;
    }
  }
`;

const SectionContainer = styled.section`
  margin-bottom: 48px;
`;

const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 16px;
  flex-wrap: wrap;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
`;

const SectionTitle = styled.h2`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 24px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.accent};
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
`;

const FilterBar = styled.div`
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;

  @media (max-width: 768px) {
    width: 100%;
  }
`;

const ContentCard = styled.div`
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
  overflow: hidden;
`;

const CardBody = styled.div`
  padding: 24px;

  @media (max-width: 768px) {
    padding: 16px;
  }
`;

const RankInfoBanner = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  margin: 0 24px 16px;
  background: ${OS_LEGAL_COLORS.accentSurface};
  border: 1px solid ${OS_LEGAL_COLORS.accentMedium};
  border-radius: 10px;
  color: ${OS_LEGAL_COLORS.accent};
  font-size: 14px;

  strong {
    color: ${OS_LEGAL_COLORS.accent};
    font-weight: 600;
  }

  @media (max-width: 768px) {
    margin: 0 16px 16px;
  }
`;

const RankBadge = styled.div<{ $rank: number }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  font-weight: 600;
  font-size: 14px;
  background: ${(props) => {
    if (props.$rank === 1) return RANK_COLORS.gold.bg;
    if (props.$rank === 2) return RANK_COLORS.silver.bg;
    if (props.$rank === 3) return RANK_COLORS.bronze.bg;
    return OS_LEGAL_COLORS.surfaceLight;
  }};
  color: ${(props) => {
    if (props.$rank === 1) return RANK_COLORS.gold.text;
    if (props.$rank === 2) return RANK_COLORS.silver.text;
    if (props.$rank === 3) return RANK_COLORS.bronze.text;
    return OS_LEGAL_COLORS.textSecondary;
  }};
  border: 1px solid
    ${(props) => {
      if (props.$rank === 1) return RANK_COLORS.gold.border;
      if (props.$rank === 2) return RANK_COLORS.silver.border;
      if (props.$rank === 3) return RANK_COLORS.bronze.border;
      return OS_LEGAL_COLORS.border;
    }};
`;

const UserRow = styled(Table.Row)<{ $isCurrentUser?: boolean }>`
  cursor: pointer;
  transition: background-color 0.15s ease;

  ${(props) =>
    props.$isCurrentUser &&
    `
    background-color: ${OS_LEGAL_COLORS.accentSurface} !important;
    font-weight: 600;
  `}

  &:hover {
    background-color: ${OS_LEGAL_COLORS.surfaceHover} !important;
  }
`;

const UsernameCell = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const RisingStarTag = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 600;
  background: ${RISING_STAR_COLORS.bg};
  border: 1px solid ${RISING_STAR_COLORS.border};
  border-radius: 999px;
  color: ${RISING_STAR_COLORS.text};
  letter-spacing: 0.02em;
`;

const ScoreCell = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const DetailsCell = styled.div`
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const TableWrapper = styled.div`
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
`;

const BadgeGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
`;

const BadgeCard = styled.div`
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  min-width: 0;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  }
`;

const BadgeMeta = styled.div`
  width: 100%;
  min-width: 0;
`;

const BadgeName = styled.div`
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin-bottom: 4px;
  overflow-wrap: anywhere;
`;

const BadgeStats = styled.div`
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const EmptyStateBox = styled.div`
  padding: 48px 24px;
  text-align: center;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

interface LeaderboardProps {
  corpusId?: string;
}

export const Leaderboard: React.FC<LeaderboardProps> = ({ corpusId }) => {
  const navigate = useNavigate();
  const [metric, setMetric] = useState<LeaderboardMetric>(
    LeaderboardMetric.BADGES
  );
  const [scope, setScope] = useState<LeaderboardScope>(
    LeaderboardScope.ALL_TIME
  );
  const [limit, setLimit] = useState(25);

  const {
    loading: leaderboardLoading,
    error: leaderboardError,
    data: leaderboardData,
  } = useQuery<{ leaderboard: LeaderboardType }>(GET_LEADERBOARD, {
    variables: {
      metric,
      scope,
      corpusId,
      limit,
    },
    pollInterval: 60000, // Refresh every minute
  });

  const { data: statsData } = useQuery<{
    communityStats: CommunityStatsType;
  }>(GET_COMMUNITY_STATS, {
    variables: { corpusId },
    pollInterval: 120000, // Refresh every 2 minutes
  });

  const metricOptions = [
    { value: LeaderboardMetric.BADGES, label: "Top Badge Earners" },
    { value: LeaderboardMetric.MESSAGES, label: "Most Active Contributors" },
    { value: LeaderboardMetric.THREADS, label: "Top Thread Creators" },
    { value: LeaderboardMetric.ANNOTATIONS, label: "Top Annotators" },
    { value: LeaderboardMetric.REPUTATION, label: "Highest Reputation" },
  ];

  const scopeOptions = [
    { value: LeaderboardScope.ALL_TIME, label: "All Time" },
    { value: LeaderboardScope.MONTHLY, label: "This Month" },
    { value: LeaderboardScope.WEEKLY, label: "This Week" },
  ];

  const limitOptions = [
    { value: 10, label: "Top 10" },
    { value: 25, label: "Top 25" },
    { value: 50, label: "Top 50" },
    { value: 100, label: "Top 100" },
  ];

  const getMetricIcon = (metric: LeaderboardMetric) => {
    switch (metric) {
      case LeaderboardMetric.BADGES:
        return <Trophy size={16} />;
      case LeaderboardMetric.MESSAGES:
        return <MessageSquare size={16} />;
      case LeaderboardMetric.THREADS:
        return <Users size={16} />;
      case LeaderboardMetric.ANNOTATIONS:
        return <Target size={16} />;
      case LeaderboardMetric.REPUTATION:
        return <Star size={16} />;
    }
  };

  const getScoreLabel = (metric: LeaderboardMetric, score: number) => {
    switch (metric) {
      case LeaderboardMetric.BADGES:
        return `${score} ${score === 1 ? "badge" : "badges"}`;
      case LeaderboardMetric.MESSAGES:
        return `${score} ${score === 1 ? "message" : "messages"}`;
      case LeaderboardMetric.THREADS:
        return `${score} ${score === 1 ? "thread" : "threads"}`;
      case LeaderboardMetric.ANNOTATIONS:
        return `${score} ${score === 1 ? "annotation" : "annotations"}`;
      case LeaderboardMetric.REPUTATION:
        return `${score} reputation`;
    }
  };

  const handleUserClick = (userSlug: string) => {
    navigate(`/users/${userSlug}`);
  };

  if (leaderboardError) {
    return (
      <PageContainer>
        <ContentContainer>
          <ErrorMessage title="Error Loading Leaderboard">
            {leaderboardError.message}
          </ErrorMessage>
        </ContentContainer>
      </PageContainer>
    );
  }

  const leaderboard = leaderboardData?.leaderboard;
  const stats = statsData?.communityStats;

  return (
    <PageContainer>
      <ContentContainer>
        {/* Hero */}
        <HeroSection>
          <HeroTitle>
            Community <span>Leaderboard</span>
          </HeroTitle>
          <HeroSubtitle>
            Celebrate top contributors and track community engagement across
            badges, messages, and annotations.
          </HeroSubtitle>
        </HeroSection>

        {/* Stats */}
        {stats && (
          <StatsContainer>
            <StatGrid columns={2}>
              <StatBlock
                value={stats.totalUsers.toLocaleString()}
                label="Active Users"
                sublabel="in the community"
              />
              <StatBlock
                value={stats.totalMessages.toLocaleString()}
                label="Messages"
                sublabel="shared so far"
              />
              <StatBlock
                value={stats.totalBadgesAwarded.toLocaleString()}
                label="Badges Awarded"
                sublabel="for contributions"
              />
              <StatBlock
                value={stats.activeUsersThisWeek.toLocaleString()}
                label="Active This Week"
                sublabel="recent contributors"
              />
            </StatGrid>
          </StatsContainer>
        )}

        {/* Top Contributors */}
        <SectionContainer>
          <SectionHeader>
            <SectionTitle>
              <TrendingUp size={20} />
              Top Contributors
            </SectionTitle>
            <FilterBar>
              <Dropdown
                mode="select"
                options={metricOptions}
                value={metric}
                onChange={(value) => setMetric(value as LeaderboardMetric)}
                placeholder="Select Metric"
                clearable={false}
                style={{ minWidth: "220px" }}
              />
              <Dropdown
                mode="select"
                options={scopeOptions}
                value={scope}
                onChange={(value) => setScope(value as LeaderboardScope)}
                placeholder="Select Time Period"
                clearable={false}
              />
              <Dropdown<number>
                mode="select"
                options={limitOptions}
                value={limit}
                onChange={(value) => setLimit(value as number)}
                placeholder="Number of Users"
                clearable={false}
              />
            </FilterBar>
          </SectionHeader>

          <ContentCard>
            {leaderboardLoading ? (
              <CardBody>
                <LoadingState message="Loading leaderboard..." />
              </CardBody>
            ) : leaderboard && leaderboard.entries.length > 0 ? (
              <>
                {leaderboard.currentUserRank && (
                  <RankInfoBanner>
                    <User size={16} />
                    <span>
                      Your rank: <strong>#{leaderboard.currentUserRank}</strong>{" "}
                      out of {leaderboard.totalUsers} users
                    </span>
                  </RankInfoBanner>
                )}

                <TableWrapper>
                  <Table variant="minimal">
                    <Table.Head>
                      <Table.Row>
                        <Table.HeadCell style={{ width: "80px" }}>
                          Rank
                        </Table.HeadCell>
                        <Table.HeadCell>User</Table.HeadCell>
                        <Table.HeadCell style={{ width: "180px" }}>
                          Score
                        </Table.HeadCell>
                        <Table.HeadCell>Details</Table.HeadCell>
                      </Table.Row>
                    </Table.Head>

                    <Table.Body>
                      {leaderboard.entries.map((entry: LeaderboardEntry) => (
                        <UserRow
                          key={entry.user.id}
                          $isCurrentUser={
                            leaderboard.currentUserRank !== null &&
                            entry.rank === leaderboard.currentUserRank
                          }
                          onClick={() => handleUserClick(entry.user.slug)}
                        >
                          <Table.Cell>
                            <RankBadge $rank={entry.rank}>
                              {entry.rank <= 3 ? (
                                <Medal size={18} />
                              ) : (
                                <span>{entry.rank}</span>
                              )}
                            </RankBadge>
                          </Table.Cell>
                          <Table.Cell>
                            <UsernameCell>
                              <strong>{entry.user.username}</strong>
                              {entry.isRisingStar && (
                                <RisingStarTag>
                                  <TrendingUp size={12} />
                                  Rising Star
                                </RisingStarTag>
                              )}
                            </UsernameCell>
                          </Table.Cell>
                          <Table.Cell>
                            <ScoreCell>
                              {getMetricIcon(metric)}
                              <strong>
                                {getScoreLabel(metric, entry.score)}
                              </strong>
                            </ScoreCell>
                          </Table.Cell>
                          <Table.Cell>
                            <DetailsCell>
                              {entry.badgeCount !== undefined &&
                                `${entry.badgeCount} badges `}
                              {entry.messageCount !== undefined &&
                                `${entry.messageCount} messages `}
                              {entry.reputation !== undefined &&
                                `${entry.reputation} rep`}
                            </DetailsCell>
                          </Table.Cell>
                        </UserRow>
                      ))}
                    </Table.Body>
                  </Table>
                </TableWrapper>
              </>
            ) : (
              <EmptyStateBox>
                <InfoMessage title="No Data Available">
                  There are no users in this leaderboard yet. Be the first to
                  contribute!
                </InfoMessage>
              </EmptyStateBox>
            )}
          </ContentCard>
        </SectionContainer>

        {/* Badge Distribution */}
        {stats &&
          stats.badgeDistribution &&
          stats.badgeDistribution.length > 0 && (
            <SectionContainer>
              <SectionHeader>
                <SectionTitle>
                  <Trophy size={20} />
                  Badge Distribution
                </SectionTitle>
              </SectionHeader>
              <BadgeGrid>
                {stats.badgeDistribution.map((dist) => (
                  <BadgeCard key={dist.badge.id}>
                    <Badge badge={dist.badge} size="medium" />
                    <BadgeMeta>
                      <BadgeName>{dist.badge.name}</BadgeName>
                      <BadgeStats>
                        Awarded {dist.awardCount} times to{" "}
                        {dist.uniqueRecipients} users
                      </BadgeStats>
                    </BadgeMeta>
                  </BadgeCard>
                ))}
              </BadgeGrid>
            </SectionContainer>
          )}
      </ContentContainer>
    </PageContainer>
  );
};
