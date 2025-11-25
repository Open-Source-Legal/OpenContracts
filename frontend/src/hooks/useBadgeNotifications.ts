import { useEffect, useRef, useState } from "react";
import { useQuery } from "@apollo/client";
import { GET_NOTIFICATIONS, NotificationNode } from "../graphql/queries";

export interface BadgeNotification {
  id: string;
  badgeId: string;
  badgeName: string;
  badgeDescription: string;
  badgeIcon: string;
  badgeColor: string;
  isAutoAwarded: boolean;
  awardedAt: string;
  awardedBy?: {
    id: string;
    username: string;
  };
}

/**
 * Hook to detect new badge award notifications.
 * Polls for BADGE notification types and returns newly awarded badges.
 */
export function useBadgeNotifications(pollInterval: number = 30000) {
  const [newBadges, setNewBadges] = useState<BadgeNotification[]>([]);
  const previousBadgeIds = useRef<Set<string>>(new Set());
  const isInitialLoad = useRef(true);

  const { data, startPolling, stopPolling } = useQuery(GET_NOTIFICATIONS, {
    variables: {
      notificationType: "BADGE",
      limit: 20,
    },
    fetchPolicy: "cache-and-network",
  });

  useEffect(() => {
    if (pollInterval > 0) {
      startPolling(pollInterval);
      return () => stopPolling();
    }
  }, [pollInterval, startPolling, stopPolling]);

  useEffect(() => {
    if (!data?.notifications?.edges) {
      return;
    }

    const badgeNotifications: BadgeNotification[] = [];
    const currentBadgeIds = new Set<string>();

    data.notifications.edges.forEach((edge: { node: NotificationNode }) => {
      const notification = edge.node;

      // Skip if not a badge notification
      if (notification.notificationType !== "BADGE") {
        return;
      }

      const badgeId = notification.data?.badge_id;
      if (!badgeId) {
        return;
      }

      currentBadgeIds.add(notification.id);

      // If this is a new badge notification (not seen before)
      if (!previousBadgeIds.current.has(notification.id)) {
        badgeNotifications.push({
          id: notification.id,
          badgeId: badgeId,
          badgeName: notification.data?.badge_name || "Badge",
          badgeDescription: notification.data?.badge_description || "",
          badgeIcon: notification.data?.badge_icon || "Award",
          badgeColor: notification.data?.badge_color || "#05313d",
          isAutoAwarded: notification.data?.is_auto_awarded || false,
          awardedAt: notification.createdAt,
          awardedBy: notification.actor
            ? {
                id: notification.actor.id,
                username: notification.actor.username,
              }
            : undefined,
        });
      }
    });

    // Skip notifications on initial load to prevent showing old badges
    if (isInitialLoad.current) {
      isInitialLoad.current = false;
      previousBadgeIds.current = currentBadgeIds;
      return;
    }

    // Update the set of seen badge notification IDs
    previousBadgeIds.current = currentBadgeIds;

    // If we found new badges, emit them
    if (badgeNotifications.length > 0) {
      setNewBadges(badgeNotifications);
    }
  }, [data]);

  const clearNewBadges = () => {
    setNewBadges([]);
  };

  return {
    newBadges,
    clearNewBadges,
  };
}
