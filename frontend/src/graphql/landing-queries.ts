import { gql } from "@apollo/client";
import { CorpusType, ConversationType } from "../types/graphql-api";

// ============================================================================
// Landing Page Discovery Queries
// ============================================================================

/**
 * Corpus category for organizing collections
 */
export interface CorpusCategoryNode {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  corpusCount: number;
}

export interface GetCorpusCategoriesOutput {
  corpusCategories: {
    edges: Array<{
      node: CorpusCategoryNode;
    }>;
  };
}

export const GET_CORPUS_CATEGORIES = gql`
  query GetCorpusCategories {
    corpusCategories {
      edges {
        node {
          id
          name
          description
          icon
          color
          corpusCount
        }
      }
    }
  }
`;

/**
 * Get public/trending corpuses for landing page
 * Anonymous users will only see public corpuses
 */
export interface GetTrendingCorpusesOutput {
  corpuses: {
    edges: Array<{
      node: Pick<
        CorpusType,
        | "id"
        | "slug"
        | "title"
        | "description"
        | "icon"
        | "isPublic"
        | "created"
      > & {
        creator: {
          id: string;
          username: string;
          slug: string;
        };
        documentCount?: number;
        annotationCount?: number;
        categories?: Array<{
          id: string;
          name: string;
        }>;
        engagementMetrics?: {
          totalThreads: number;
          totalMessages: number;
          uniqueContributors: number;
        } | null;
      };
    }>;
    pageInfo: {
      hasNextPage: boolean;
      endCursor: string | null;
    };
  };
}

/**
 * Get recent public discussions/threads for landing page
 */
export interface GetRecentDiscussionsOutput {
  conversations: {
    edges: Array<{
      node: Pick<
        ConversationType,
        | "id"
        | "title"
        | "description"
        | "createdAt"
        | "updatedAt"
        | "isPinned"
        | "isLocked"
      > & {
        creator: {
          id: string;
          username: string;
        };
        chatWithCorpus?: {
          id: string;
          title: string;
          slug: string;
          creator: {
            slug: string;
          };
        } | null;
      };
    }>;
    pageInfo: {
      hasNextPage: boolean;
      endCursor: string | null;
    };
    totalCount: number;
  };
}

export const GET_RECENT_DISCUSSIONS = gql`
  query GetRecentDiscussions(
    $limit: Int
    $conversationType: ConversationTypeEnum
  ) {
    conversations(first: $limit, conversationType: $conversationType) {
      edges {
        node {
          id
          title
          description
          createdAt
          updatedAt
          isPinned
          isLocked
          creator {
            id
            username
          }
          chatWithCorpus {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
      totalCount
    }
  }
`;

/**
 * Get platform-wide community statistics
 * Note: Backend CommunityStatsType doesn't have totalCorpuses/totalDocuments
 */
export interface GetCommunityStatsOutput {
  communityStats: {
    totalUsers: number;
    totalThreads: number;
    totalMessages: number;
    totalAnnotations: number;
    activeUsersThisWeek: number;
    activeUsersThisMonth: number;
  };
}

/**
 * Get global leaderboard for top contributors
 * Note: User badges are accessed via 'badges' field (returns UserBadge connection)
 */
export interface LeaderboardEntry {
  id: string;
  username: string;
  slug?: string;
  reputationGlobal?: number;
  badges?: {
    edges: Array<{
      node: {
        badge: {
          id: string;
          name: string;
          icon: string;
          color: string;
        };
      };
    }>;
  };
}

/**
 * Unified discovery query - fetches everything needed for landing page in one request
 */
export interface GetDiscoveryDataOutput {
  corpuses: GetTrendingCorpusesOutput["corpuses"];
  conversations: GetRecentDiscussionsOutput["conversations"];
  communityStats: GetCommunityStatsOutput["communityStats"];
  globalLeaderboard: LeaderboardEntry[];
}

export const GET_DISCOVERY_DATA = gql`
  query GetDiscoveryData(
    $corpusLimit: Int
    $discussionLimit: Int
    $leaderboardLimit: Int
    $conversationType: ConversationTypeEnum
  ) {
    corpuses(first: $corpusLimit) {
      edges {
        node {
          id
          slug
          title
          description
          icon
          isPublic
          created
          creator {
            id
            username
            slug
          }
          documentCount
          annotationCount
          categories {
            id
            name
          }
          engagementMetrics {
            totalThreads
            totalMessages
            uniqueContributors
          }
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
    conversations(
      first: $discussionLimit
      conversationType: $conversationType
    ) {
      edges {
        node {
          id
          title
          description
          createdAt
          updatedAt
          isPinned
          isLocked
          creator {
            id
            username
          }
          chatWithCorpus {
            id
            title
            slug
            creator {
              id
              slug
            }
          }
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
      totalCount
    }
    communityStats {
      totalUsers
      totalThreads
      totalMessages
      totalAnnotations
      activeUsersThisWeek
      activeUsersThisMonth
    }
    globalLeaderboard(limit: $leaderboardLimit) {
      id
      username
      slug
      reputationGlobal
      badges(first: 3) {
        edges {
          node {
            badge {
              id
              name
              icon
              color
            }
          }
        }
      }
    }
  }
`;
