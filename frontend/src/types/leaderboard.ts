/**
 * TypeScript types for leaderboard and community stats.
 *
 * Issue: #613 - Create leaderboard and community stats dashboard
 * Epic: #572 - Social Features Epic
 */

export enum LeaderboardMetric {
  BADGES = "BADGES",
  MESSAGES = "MESSAGES",
  THREADS = "THREADS",
  ANNOTATIONS = "ANNOTATIONS",
  REPUTATION = "REPUTATION",
}

export enum LeaderboardScope {
  ALL_TIME = "ALL_TIME",
  MONTHLY = "MONTHLY",
  WEEKLY = "WEEKLY",
}

export interface LeaderboardUser {
  id: string;
  username: string;
  email?: string;
  slug: string;
  isProfilePublic: boolean;
}

export interface LeaderboardEntry {
  rank: number;
  score: number;
  badgeCount?: number;
  messageCount?: number;
  threadCount?: number;
  annotationCount?: number;
  reputation?: number;
  isRisingStar?: boolean;
  user: LeaderboardUser;
}

export interface Leaderboard {
  metric: LeaderboardMetric;
  scope: LeaderboardScope;
  corpusId?: string;
  totalUsers: number;
  currentUserRank?: number | null;
  entries: LeaderboardEntry[];
}

export interface BadgeDistribution {
  awardCount: number;
  uniqueRecipients: number;
  badge: {
    id: string;
    name: string;
    description: string;
    icon: string;
    color: string;
  };
}

export interface CommunityStats {
  totalUsers: number;
  totalMessages: number;
  totalThreads: number;
  totalAnnotations: number;
  totalBadgesAwarded: number;
  messagesThisWeek: number;
  messagesThisMonth: number;
  activeUsersThisWeek: number;
  activeUsersThisMonth: number;
  badgeDistribution: BadgeDistribution[];
}
