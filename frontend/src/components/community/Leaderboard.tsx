import React, { useState } from "react";
import { useQuery } from "@apollo/client";
import {
  Table,
  Header,
  Message,
  Dimmer,
  Loader,
  Segment,
  Icon,
  Dropdown,
  Label,
  Button,
  Grid,
  Statistic,
} from "semantic-ui-react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import {
  Trophy,
  Medal,
  TrendingUp,
  Users,
  MessageSquare,
  Target,
  Star,
} from "lucide-react";
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

const Container = styled.div`
  padding: 2em;
  max-width: 1400px;
  margin: 0 auto;
`;

const StyledSegment = styled(Segment)`
  &.ui.segment {
    border-radius: 16px;
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(226, 232, 240, 0.8);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }
`;

const LeaderboardCard = styled(Segment)`
  &.ui.segment {
    border-radius: 12px;
    background: white;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    padding: 1.5em;
    margin-bottom: 1em;
  }
`;

const StatsCard = styled.div`
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  padding: 1.5em;
  color: white;
  text-align: center;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
`;

const RankBadge = styled.div<{ $rank: number }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  font-weight: bold;
  font-size: 18px;
  background: ${(props) => {
    if (props.$rank === 1)
      return "linear-gradient(135deg, #FFD700 0%, #FFA500 100%)";
    if (props.$rank === 2)
      return "linear-gradient(135deg, #C0C0C0 0%, #A8A8A8 100%)";
    if (props.$rank === 3)
      return "linear-gradient(135deg, #CD7F32 0%, #B8860B 100%)";
    return "linear-gradient(135deg, #667eea 0%, #764ba2 100%)";
  }};
  color: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
`;

const UserRow = styled(Table.Row)<{ $isCurrentUser?: boolean }>`
  ${(props) =>
    props.$isCurrentUser &&
    `
    background-color: rgba(102, 126, 234, 0.1) !important;
    font-weight: 600;
  `}
`;

const FilterBar = styled.div`
  display: flex;
  gap: 1em;
  margin-bottom: 1.5em;
  flex-wrap: wrap;
  align-items: center;
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

  const { loading: statsLoading, data: statsData } = useQuery<{
    communityStats: CommunityStatsType;
  }>(GET_COMMUNITY_STATS, {
    variables: { corpusId },
    pollInterval: 120000, // Refresh every 2 minutes
  });

  const metricOptions = [
    {
      key: LeaderboardMetric.BADGES,
      text: "Top Badge Earners",
      value: LeaderboardMetric.BADGES,
      icon: "trophy",
    },
    {
      key: LeaderboardMetric.MESSAGES,
      text: "Most Active Contributors",
      value: LeaderboardMetric.MESSAGES,
      icon: "comment",
    },
    {
      key: LeaderboardMetric.THREADS,
      text: "Top Thread Creators",
      value: LeaderboardMetric.THREADS,
      icon: "conversation",
    },
    {
      key: LeaderboardMetric.ANNOTATIONS,
      text: "Top Annotators",
      value: LeaderboardMetric.ANNOTATIONS,
      icon: "marker",
    },
    {
      key: LeaderboardMetric.REPUTATION,
      text: "Highest Reputation",
      value: LeaderboardMetric.REPUTATION,
      icon: "star",
    },
  ];

  const scopeOptions = [
    {
      key: LeaderboardScope.ALL_TIME,
      text: "All Time",
      value: LeaderboardScope.ALL_TIME,
    },
    {
      key: LeaderboardScope.MONTHLY,
      text: "This Month",
      value: LeaderboardScope.MONTHLY,
    },
    {
      key: LeaderboardScope.WEEKLY,
      text: "This Week",
      value: LeaderboardScope.WEEKLY,
    },
  ];

  const limitOptions = [
    { key: 10, text: "Top 10", value: 10 },
    { key: 25, text: "Top 25", value: 25 },
    { key: 50, text: "Top 50", value: 50 },
    { key: 100, text: "Top 100", value: 100 },
  ];

  const getMetricIcon = (metric: LeaderboardMetric) => {
    switch (metric) {
      case LeaderboardMetric.BADGES:
        return <Trophy size={20} />;
      case LeaderboardMetric.MESSAGES:
        return <MessageSquare size={20} />;
      case LeaderboardMetric.THREADS:
        return <Users size={20} />;
      case LeaderboardMetric.ANNOTATIONS:
        return <Target size={20} />;
      case LeaderboardMetric.REPUTATION:
        return <Star size={20} />;
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
      <Container>
        <Message error>
          <Message.Header>Error Loading Leaderboard</Message.Header>
          <p>{leaderboardError.message}</p>
        </Message>
      </Container>
    );
  }

  const leaderboard = leaderboardData?.leaderboard;
  const stats = statsData?.communityStats;

  return (
    <Container>
      <Header as="h1">
        <Icon name="chart line" />
        Community Leaderboard
      </Header>

      {/* Community Stats Overview */}
      {stats && (
        <Grid columns={4} stackable style={{ marginBottom: "2em" }}>
          <Grid.Column>
            <StatsCard>
              <Statistic inverted size="small">
                <Statistic.Value>
                  {stats.totalUsers.toLocaleString()}
                </Statistic.Value>
                <Statistic.Label>Active Users</Statistic.Label>
              </Statistic>
            </StatsCard>
          </Grid.Column>
          <Grid.Column>
            <StatsCard>
              <Statistic inverted size="small">
                <Statistic.Value>
                  {stats.totalMessages.toLocaleString()}
                </Statistic.Value>
                <Statistic.Label>Messages</Statistic.Label>
              </Statistic>
            </StatsCard>
          </Grid.Column>
          <Grid.Column>
            <StatsCard>
              <Statistic inverted size="small">
                <Statistic.Value>
                  {stats.totalBadgesAwarded.toLocaleString()}
                </Statistic.Value>
                <Statistic.Label>Badges Awarded</Statistic.Label>
              </Statistic>
            </StatsCard>
          </Grid.Column>
          <Grid.Column>
            <StatsCard>
              <Statistic inverted size="small">
                <Statistic.Value>
                  {stats.activeUsersThisWeek.toLocaleString()}
                </Statistic.Value>
                <Statistic.Label>Active This Week</Statistic.Label>
              </Statistic>
            </StatsCard>
          </Grid.Column>
        </Grid>
      )}

      {/* Leaderboard Controls */}
      <LeaderboardCard>
        <FilterBar>
          <Dropdown
            selection
            options={metricOptions}
            value={metric}
            onChange={(_, data) => setMetric(data.value as LeaderboardMetric)}
            placeholder="Select Metric"
            style={{ minWidth: "250px" }}
          />
          <Dropdown
            selection
            options={scopeOptions}
            value={scope}
            onChange={(_, data) => setScope(data.value as LeaderboardScope)}
            placeholder="Select Time Period"
          />
          <Dropdown
            selection
            options={limitOptions}
            value={limit}
            onChange={(_, data) => setLimit(data.value as number)}
            placeholder="Number of Users"
          />
        </FilterBar>

        {leaderboardLoading ? (
          <Dimmer active inverted>
            <Loader inverted>Loading leaderboard...</Loader>
          </Dimmer>
        ) : leaderboard && leaderboard.entries.length > 0 ? (
          <>
            {leaderboard.currentUserRank && (
              <Message info>
                <Icon name="user" />
                Your rank: <strong>#{leaderboard.currentUserRank}</strong> out
                of {leaderboard.totalUsers} users
              </Message>
            )}

            <Table basic="very" celled selectable>
              <Table.Header>
                <Table.Row>
                  <Table.HeaderCell width={1}>Rank</Table.HeaderCell>
                  <Table.HeaderCell>User</Table.HeaderCell>
                  <Table.HeaderCell width={3}>Score</Table.HeaderCell>
                  <Table.HeaderCell width={2}>Details</Table.HeaderCell>
                </Table.Row>
              </Table.Header>

              <Table.Body>
                {leaderboard.entries.map((entry: LeaderboardEntry) => (
                  <UserRow
                    key={entry.user.id}
                    $isCurrentUser={
                      leaderboard.currentUserRank !== null &&
                      entry.rank === leaderboard.currentUserRank
                    }
                    onClick={() => handleUserClick(entry.user.slug)}
                    style={{ cursor: "pointer" }}
                  >
                    <Table.Cell>
                      <RankBadge $rank={entry.rank}>
                        {entry.rank <= 3 ? (
                          <Medal size={20} />
                        ) : (
                          <span>{entry.rank}</span>
                        )}
                      </RankBadge>
                    </Table.Cell>
                    <Table.Cell>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5em",
                        }}
                      >
                        <strong>{entry.user.username}</strong>
                        {entry.isRisingStar && (
                          <Label size="tiny" color="orange">
                            <TrendingUp
                              size={12}
                              style={{ marginRight: "4px" }}
                            />
                            Rising Star
                          </Label>
                        )}
                      </div>
                    </Table.Cell>
                    <Table.Cell>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5em",
                        }}
                      >
                        {getMetricIcon(metric)}
                        <strong>{getScoreLabel(metric, entry.score)}</strong>
                      </div>
                    </Table.Cell>
                    <Table.Cell>
                      <div style={{ fontSize: "0.9em", color: "#64748b" }}>
                        {entry.badgeCount !== undefined &&
                          `${entry.badgeCount} badges `}
                        {entry.messageCount !== undefined &&
                          `${entry.messageCount} messages `}
                        {entry.reputation !== undefined &&
                          `${entry.reputation} rep`}
                      </div>
                    </Table.Cell>
                  </UserRow>
                ))}
              </Table.Body>
            </Table>
          </>
        ) : (
          <Message info>
            <Message.Header>No Data Available</Message.Header>
            <p>
              There are no users in this leaderboard yet. Be the first to
              contribute!
            </p>
          </Message>
        )}
      </LeaderboardCard>

      {/* Badge Distribution */}
      {stats &&
        stats.badgeDistribution &&
        stats.badgeDistribution.length > 0 && (
          <StyledSegment>
            <Header as="h3">
              <Icon name="trophy" />
              Badge Distribution
            </Header>
            <Grid columns={2} stackable>
              {stats.badgeDistribution.map((dist) => (
                <Grid.Column key={dist.badge.id}>
                  <Segment>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "1em",
                      }}
                    >
                      <Badge badge={dist.badge} size="medium" />
                      <div style={{ flex: 1 }}>
                        <div>
                          <strong>{dist.badge.name}</strong>
                        </div>
                        <div style={{ fontSize: "0.9em", color: "#64748b" }}>
                          Awarded {dist.awardCount} times to{" "}
                          {dist.uniqueRecipients} users
                        </div>
                      </div>
                    </div>
                  </Segment>
                </Grid.Column>
              ))}
            </Grid>
          </StyledSegment>
        )}
    </Container>
  );
};
