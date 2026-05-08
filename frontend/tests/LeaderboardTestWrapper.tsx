import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { Leaderboard } from "../src/components/community/Leaderboard";
import {
  GET_LEADERBOARD,
  GET_COMMUNITY_STATS,
} from "../src/graphql/queries/leaderboard/queries";

const defaultLeaderboardMock: MockedResponse = {
  request: { query: GET_LEADERBOARD },
  variableMatcher: () => true,
  result: {
    data: {
      leaderboard: {
        metric: "BADGES",
        scope: "ALL_TIME",
        corpusId: null,
        totalUsers: 100,
        currentUserRank: 5,
        entries: [
          {
            rank: 1,
            score: 50,
            badgeCount: 50,
            messageCount: 200,
            threadCount: 30,
            annotationCount: 500,
            reputation: 1500,
            isRisingStar: true,
            user: {
              id: "user-1",
              displayName: "top_user",
              slug: "top-user",
              isProfilePublic: true,
            },
          },
          {
            rank: 2,
            score: 35,
            badgeCount: 35,
            messageCount: 150,
            threadCount: 20,
            annotationCount: 300,
            reputation: 1200,
            isRisingStar: false,
            user: {
              id: "user-2",
              displayName: "second_user",
              slug: "second-user",
              isProfilePublic: true,
            },
          },
        ],
      },
    },
  },
};

const defaultCommunityStatsMock: MockedResponse = {
  request: { query: GET_COMMUNITY_STATS },
  variableMatcher: () => true,
  result: {
    data: {
      communityStats: {
        totalUsers: 100,
        totalMessages: 500,
        totalThreads: 50,
        totalAnnotations: 2000,
        totalBadgesAwarded: 75,
        messagesThisWeek: 30,
        messagesThisMonth: 120,
        activeUsersThisWeek: 25,
        activeUsersThisMonth: 60,
        badgeDistribution: [],
      },
    },
  },
};

interface WrapperProps {
  corpusId?: string;
  mocks?: MockedResponse[];
}

export const LeaderboardTestWrapper: React.FC<WrapperProps> = ({
  corpusId,
  mocks,
}) => {
  const allMocks = mocks ?? [
    defaultLeaderboardMock,
    { ...defaultLeaderboardMock },
    { ...defaultLeaderboardMock },
    defaultCommunityStatsMock,
    { ...defaultCommunityStatsMock },
    { ...defaultCommunityStatsMock },
  ];

  return (
    <MockedProvider mocks={allMocks} addTypename={false}>
      <MemoryRouter>
        <div style={{ padding: 24, maxWidth: 1200 }}>
          <Leaderboard corpusId={corpusId} />
        </div>
      </MemoryRouter>
    </MockedProvider>
  );
};

export { defaultLeaderboardMock, defaultCommunityStatsMock };
