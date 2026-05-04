import { useState, useCallback } from "react";
import {
  useNotificationWebSocket,
  NotificationUpdate,
} from "./useNotificationWebSocket";

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
 * Hook to detect new badge award notifications via WebSocket.
 *
 * Replaces polling-based implementation with real-time WebSocket updates.
 * Maintains the same interface for backward compatibility.
 *
 * Issue #637: Migrate badge notifications from polling to WebSocket
 */
export function useBadgeNotifications() {
  const [newBadges, setNewBadges] = useState<BadgeNotification[]>([]);

  // Convert notification update to badge notification
  const handleNotificationCreated = useCallback(
    (notification: NotificationUpdate) => {
      // Only process BADGE notifications
      if (notification.notificationType !== "BADGE") {
        return;
      }

      const badgeId = notification.data?.badge_id;
      if (!badgeId) {
        console.warn(
          "[useBadgeNotifications] Badge notification missing badge_id:",
          notification
        );
        return;
      }

      const badgeNotification: BadgeNotification = {
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
      };

      // Add to newBadges array
      setNewBadges((prev) => [...prev, badgeNotification]);
    },
    []
  );

  // Subscribe to WebSocket notifications
  const { connectionState } = useNotificationWebSocket({
    onNotificationCreated: handleNotificationCreated,
    enabled: true,
  });

  const clearNewBadges = useCallback(() => {
    setNewBadges([]);
  }, []);

  return {
    newBadges,
    clearNewBadges,
    connectionState, // Export connection state for debugging/UI feedback
  };
}
