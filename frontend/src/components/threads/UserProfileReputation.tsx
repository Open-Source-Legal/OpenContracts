import React from "react";
import styled from "styled-components";
import { TrendingUp, TrendingDown, Award } from "lucide-react";
import { ReputationBadge, ReputationBreakdown } from "./ReputationBadge";
import { color } from "../../theme/colors";

const Container = styled.div`
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px;
  background: ${({ theme }) => color.N1};
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 8px;
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const Title = styled.h3`
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: ${({ theme }) => color.N10};
`;

const Stats = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
`;

const StatCard = styled.div`
  padding: 16px;
  background: ${({ theme }) => color.N2};
  border-radius: 6px;
`;

const StatLabel = styled.div`
  font-size: 12px;
  color: ${({ theme }) => color.N6};
  margin-bottom: 6px;
`;

const StatValue = styled.div<{ $trend?: "up" | "down" }>`
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 24px;
  font-weight: 700;
  color: ${({ $trend, theme }) => {
    if ($trend === "up") return theme.color.success;
    if ($trend === "down") return color.R7;
    return color.N10;
  }};

  svg {
    width: 20px;
    height: 20px;
  }
`;

const BadgeList = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
`;

const Section = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
`;

const SectionTitle = styled.h4`
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: ${({ theme }) => color.N10};
`;

const ProgressBar = styled.div`
  width: 100%;
  height: 8px;
  background: ${({ theme }) => color.N3};
  border-radius: 4px;
  overflow: hidden;
`;

const ProgressFill = styled.div<{ $percentage: number }>`
  width: ${({ $percentage }) => Math.min(100, Math.max(0, $percentage))}%;
  height: 100%;
  background: ${({ theme }) => color.B5};
  transition: width 0.3s ease;
`;

const NextMilestone = styled.div`
  font-size: 12px;
  color: ${({ theme }) => color.N7};
  margin-top: 4px;
`;

export interface UserProfileReputationProps {
  /** User's global reputation */
  globalReputation: number;
  /** Breakdown of global reputation */
  globalBreakdown?: ReputationBreakdown;
  /** Total upvotes received */
  upvotesReceived: number;
  /** Total downvotes received */
  downvotesReceived: number;
  /** Number of accepted answers */
  acceptedAnswers?: number;
  /** Number of earned badges */
  badgeCount?: number;
  /** Recent reputation change (e.g., +45 this week) */
  recentChange?: number;
  /** Change period label (e.g., "this week", "this month") */
  changePeriod?: string;
  /** Next reputation milestone */
  nextMilestone?: number;
}

export function UserProfileReputation({
  globalReputation,
  globalBreakdown,
  upvotesReceived,
  downvotesReceived,
  acceptedAnswers = 0,
  badgeCount = 0,
  recentChange,
  changePeriod = "this week",
  nextMilestone,
}: UserProfileReputationProps) {
  // Calculate percentage to next milestone
  const milestoneProgress =
    nextMilestone && nextMilestone > globalReputation
      ? (globalReputation / nextMilestone) * 100
      : 100;

  const netVotes = upvotesReceived - downvotesReceived;
  const voteTrend = netVotes > 0 ? "up" : netVotes < 0 ? "down" : undefined;

  return (
    <Container>
      <Header>
        <Award size={24} />
        <Title>Reputation</Title>
      </Header>

      <BadgeList>
        <ReputationBadge
          reputation={globalReputation}
          breakdown={globalBreakdown}
          label="Global Reputation"
          size="large"
          showIcon={false}
          showTooltip={!!globalBreakdown}
        />

        {recentChange !== undefined && recentChange !== 0 && (
          <ReputationBadge
            reputation={recentChange}
            label={changePeriod}
            size="medium"
            showIcon={true}
            showTooltip={false}
          />
        )}
      </BadgeList>

      {nextMilestone && nextMilestone > globalReputation && (
        <Section>
          <SectionTitle>Progress to Next Milestone</SectionTitle>
          <ProgressBar>
            <ProgressFill $percentage={milestoneProgress} />
          </ProgressBar>
          <NextMilestone>
            {globalReputation} / {nextMilestone} (
            {Math.round(milestoneProgress)}%)
          </NextMilestone>
        </Section>
      )}

      <Stats>
        <StatCard>
          <StatLabel>Net Votes</StatLabel>
          <StatValue $trend={voteTrend}>
            {voteTrend === "up" && <TrendingUp />}
            {voteTrend === "down" && <TrendingDown />}
            {netVotes > 0 ? "+" : ""}
            {netVotes}
          </StatValue>
        </StatCard>

        <StatCard>
          <StatLabel>Upvotes Received</StatLabel>
          <StatValue $trend="up">+{upvotesReceived}</StatValue>
        </StatCard>

        <StatCard>
          <StatLabel>Downvotes Received</StatLabel>
          <StatValue $trend="down">{downvotesReceived}</StatValue>
        </StatCard>

        {acceptedAnswers > 0 && (
          <StatCard>
            <StatLabel>Accepted Answers</StatLabel>
            <StatValue>{acceptedAnswers}</StatValue>
          </StatCard>
        )}

        {badgeCount > 0 && (
          <StatCard>
            <StatLabel>Badges Earned</StatLabel>
            <StatValue>{badgeCount}</StatValue>
          </StatCard>
        )}
      </Stats>
    </Container>
  );
}
