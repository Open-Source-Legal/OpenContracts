import React from "react";
import { useQuery } from "@apollo/client";
import { Icon, Loader, Message, SemanticICONS } from "semantic-ui-react";
import styled from "styled-components";
import CountUp from "react-countup";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { format, subDays } from "date-fns";
import {
  GET_CORPUS_ENGAGEMENT_METRICS,
  GetCorpusEngagementMetricsOutput,
  GetCorpusEngagementMetricsInput,
  CorpusEngagementMetrics,
} from "../../graphql/queries";
import { MOBILE_VIEW_BREAKPOINT } from "../../assets/configurations/constants";
import useWindowDimensions from "../hooks/WindowDimensionHook";

interface CorpusEngagementDashboardProps {
  corpusId: string;
}

const StatisticWithAnimation = ({
  value,
  label,
  icon,
  color,
}: {
  value: number;
  label: string;
  icon: SemanticICONS;
  color?: string;
}) => {
  return (
    <StatisticWrapper>
      <StatisticIcon name={icon} style={{ color: color || "#4a90e2" }} />
      <StatisticContent>
        <StatisticValue>
          <CountUp end={value} duration={1.5} />
        </StatisticValue>
        <StatisticLabel>{label}</StatisticLabel>
      </StatisticContent>
    </StatisticWrapper>
  );
};

export const CorpusEngagementDashboard: React.FC<
  CorpusEngagementDashboardProps
> = ({ corpusId }) => {
  const { width } = useWindowDimensions();
  const isMobile = width <= MOBILE_VIEW_BREAKPOINT;

  const { data, loading, error } = useQuery<
    GetCorpusEngagementMetricsOutput,
    GetCorpusEngagementMetricsInput
  >(GET_CORPUS_ENGAGEMENT_METRICS, {
    variables: { corpusId },
    pollInterval: 300000, // Refetch every 5 minutes
  });

  if (loading) {
    return (
      <LoadingContainer>
        <Loader active inline="centered">
          Loading engagement metrics...
        </Loader>
      </LoadingContainer>
    );
  }

  if (error) {
    return (
      <ErrorContainer>
        <Message error>
          <Message.Header>Error Loading Metrics</Message.Header>
          <p>{error.message}</p>
        </Message>
      </ErrorContainer>
    );
  }

  const metrics = data?.corpus?.engagementMetrics;

  if (!metrics) {
    return (
      <EmptyStateContainer>
        <Message info>
          <Message.Header>No Engagement Data Available</Message.Header>
          <p>
            Engagement metrics haven't been calculated for this corpus yet. They
            will be available once the background task has run.
          </p>
        </Message>
      </EmptyStateContainer>
    );
  }

  // Prepare data for the activity comparison chart
  const activityData = [
    {
      period: "Last 7 Days",
      messages: metrics.messagesLast7Days,
    },
    {
      period: "Last 30 Days",
      messages: metrics.messagesLast30Days,
    },
  ];

  const lastUpdated = metrics.lastUpdated
    ? new Date(metrics.lastUpdated)
    : new Date();

  return (
    <DashboardContainer>
      <DashboardHeader>
        <Title>
          <Icon name="chart line" />
          Engagement Analytics
        </Title>
        <LastUpdated>
          Last updated: {format(lastUpdated, "MMM d, yyyy 'at' h:mm a")}
        </LastUpdated>
      </DashboardHeader>

      <Section>
        <SectionTitle>Thread Metrics</SectionTitle>
        <StatsGrid>
          <StatisticWithAnimation
            value={metrics.totalThreads}
            label="Total Threads"
            icon="comments"
            color="#4a90e2"
          />
          <StatisticWithAnimation
            value={metrics.activeThreads}
            label="Active Threads"
            icon="comment alternate outline"
            color="#22c55e"
          />
          <StatisticWithAnimation
            value={
              metrics.avgMessagesPerThread
                ? Math.round(metrics.avgMessagesPerThread * 10) / 10
                : 0
            }
            label="Avg Msgs/Thread"
            icon="exchange"
            color="#f59e0b"
          />
        </StatsGrid>
      </Section>

      <Section>
        <SectionTitle>Message Activity</SectionTitle>
        <StatsGrid>
          <StatisticWithAnimation
            value={metrics.totalMessages}
            label="Total Messages"
            icon="envelope"
            color="#8b5cf6"
          />
          <StatisticWithAnimation
            value={metrics.messagesLast7Days}
            label="Last 7 Days"
            icon="calendar check"
            color="#10b981"
          />
          <StatisticWithAnimation
            value={metrics.messagesLast30Days}
            label="Last 30 Days"
            icon="calendar alternate outline"
            color="#3b82f6"
          />
        </StatsGrid>

        <ChartContainer>
          <ChartTitle>Message Activity Comparison</ChartTitle>
          <ResponsiveContainer width="100%" height={isMobile ? 200 : 300}>
            <BarChart data={activityData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="period" stroke="#64748b" />
              <YAxis stroke="#64748b" />
              <Tooltip
                contentStyle={{
                  background: "white",
                  border: "1px solid #e2e8f0",
                  borderRadius: "8px",
                }}
              />
              <Legend />
              <Bar
                dataKey="messages"
                fill="#4a90e2"
                name="Messages"
                radius={[8, 8, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartContainer>
      </Section>

      <Section>
        <SectionTitle>Community Engagement</SectionTitle>
        <StatsGrid>
          <StatisticWithAnimation
            value={metrics.uniqueContributors}
            label="All Contributors"
            icon="users"
            color="#ec4899"
          />
          <StatisticWithAnimation
            value={metrics.activeContributors30Days}
            label="Active (30d)"
            icon="user plus"
            color="#14b8a6"
          />
          <StatisticWithAnimation
            value={metrics.totalUpvotes}
            label="Total Upvotes"
            icon="thumbs up"
            color="#f59e0b"
          />
        </StatsGrid>
      </Section>
    </DashboardContainer>
  );
};

// Styled Components

const DashboardContainer = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 1rem 0.75rem;
  background: white;
  max-width: 1400px;
  margin: 0 auto;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 2rem;
  }
`;

const DashboardHeader = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1.5rem;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
  }
`;

const Title = styled.h2`
  font-size: 1.5rem;
  font-weight: 700;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;

  i.icon {
    color: #4a90e2;
  }

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 2rem;
  }
`;

const LastUpdated = styled.div`
  font-size: 0.875rem;
  color: #64748b;
  font-style: italic;
`;

const Section = styled.div`
  margin-bottom: 2rem;
`;

const SectionTitle = styled.h3`
  font-size: 1.125rem;
  font-weight: 600;
  color: #334155;
  margin: 0 0 1rem 0;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e2e8f0;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 1.25rem;
  }
`;

const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
  width: 100%;
  margin-bottom: 1rem;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    grid-template-columns: repeat(3, 1fr);
    gap: 1.5rem;
  }
`;

const StatisticWrapper = styled.div`
  display: flex;
  align-items: center;
  padding: 0.75rem;
  background: #f8fafc;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07);
  }

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    flex-direction: column;
    text-align: center;
    padding: 1.25rem 1rem;
  }
`;

const StatisticIcon = styled(Icon)`
  font-size: 1.75rem !important;
  margin: 0 1rem 0 0 !important;
  opacity: 0.8;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 2.5rem !important;
    margin: 0 0 0.75rem 0 !important;
  }
`;

const StatisticContent = styled.div`
  display: flex;
  flex-direction: column;
`;

const StatisticValue = styled.div`
  font-size: 1.5rem;
  font-weight: 600;
  color: #2d3748;
  line-height: 1.2;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 2.25rem;
    margin-bottom: 0.25rem;
  }
`;

const StatisticLabel = styled.div`
  font-size: 0.75rem;
  font-weight: 500;
  color: #718096;
  text-transform: uppercase;
  letter-spacing: 0.05em;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.875rem;
  }
`;

const ChartContainer = styled.div`
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 1rem;
  margin-top: 1rem;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1.5rem;
  }
`;

const ChartTitle = styled.h4`
  font-size: 1rem;
  font-weight: 600;
  color: #475569;
  margin: 0 0 1rem 0;

  @media (min-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 1.125rem;
  }
`;

const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  width: 100%;
`;

const ErrorContainer = styled.div`
  padding: 2rem;
  max-width: 600px;
  margin: 2rem auto;
`;

const EmptyStateContainer = styled.div`
  padding: 2rem;
  max-width: 600px;
  margin: 2rem auto;
`;
