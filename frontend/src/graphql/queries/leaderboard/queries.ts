import { gql } from "@apollo/client";

/**
 * GraphQL queries for leaderboard and community stats.
 *
 * Issue: #613 - Create leaderboard and community stats dashboard
 * Epic: #572 - Social Features Epic
 */

export const GET_LEADERBOARD = gql`
  query GetLeaderboard(
    $metric: LeaderboardMetricEnum!
    $scope: LeaderboardScopeEnum
    $corpusId: ID
    $limit: Int
  ) {
    leaderboard(
      metric: $metric
      scope: $scope
      corpusId: $corpusId
      limit: $limit
    ) {
      metric
      scope
      corpusId
      totalUsers
      currentUserRank
      entries {
        rank
        score
        badgeCount
        messageCount
        threadCount
        annotationCount
        reputation
        isRisingStar
        user {
          id
          username
          email
          slug
          isProfilePublic
        }
      }
    }
  }
`;

export const GET_COMMUNITY_STATS = gql`
  query GetCommunityStats($corpusId: ID) {
    communityStats(corpusId: $corpusId) {
      totalUsers
      totalMessages
      totalThreads
      totalAnnotations
      totalBadgesAwarded
      messagesThisWeek
      messagesThisMonth
      activeUsersThisWeek
      activeUsersThisMonth
      badgeDistribution {
        awardCount
        uniqueRecipients
        badge {
          id
          name
          description
          icon
          color
        }
      }
    }
  }
`;
