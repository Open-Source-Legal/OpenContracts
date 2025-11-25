import { useQuery } from "@apollo/client";
import { useMemo } from "react";
import { GET_USER_BADGES } from "../graphql/queries";
import { UserBadgeType } from "../types/graphql-api";

interface UseMessageBadgesResult {
  badgesByUser: Map<string, UserBadgeType[]>;
  loading: boolean;
  error: Error | undefined;
}

/**
 * Hook to fetch user badges for message creators
 * Returns a map of user IDs to their badges for efficient lookup
 *
 * @param userIds - Array of user IDs to fetch badges for
 * @param corpusId - Optional corpus ID to filter corpus-specific badges
 * @param maxBadgesPerUser - Maximum number of badges to fetch per user (default: 5)
 */
export function useMessageBadges(
  userIds: string[],
  corpusId?: string | null,
  maxBadgesPerUser: number = 5
): UseMessageBadgesResult {
  // Only fetch if we have user IDs
  const skip = userIds.length === 0;

  const { data, loading, error } = useQuery(GET_USER_BADGES, {
    variables: {
      corpusId: corpusId || undefined,
      limit: userIds.length * maxBadgesPerUser, // Fetch up to maxBadgesPerUser per user
    },
    skip,
    fetchPolicy: "cache-first", // Use cache to avoid redundant fetches
  });

  // Build a map of user ID → badges for efficient lookup
  const badgesByUser = useMemo(() => {
    const map = new Map<string, UserBadgeType[]>();

    if (!data?.userBadges?.edges) {
      return map;
    }

    // Group badges by user
    data.userBadges.edges.forEach((edge: any) => {
      if (!edge?.node) return;

      const userBadge: UserBadgeType = edge.node;
      const userId = userBadge.user.id;

      // Only include badges for users in our list
      if (userIds.includes(userId)) {
        if (!map.has(userId)) {
          map.set(userId, []);
        }

        const userBadges = map.get(userId)!;

        // Limit badges per user
        if (userBadges.length < maxBadgesPerUser) {
          userBadges.push(userBadge);
        }
      }
    });

    return map;
  }, [data, userIds, maxBadgesPerUser]);

  return {
    badgesByUser,
    loading,
    error: error as Error | undefined,
  };
}
