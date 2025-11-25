import { useState, useEffect, useCallback } from "react";
import { toast } from "react-toastify";
import { BadgeNotification } from "./useBadgeNotifications";
import { BadgeToast } from "../components/badges/BadgeToast";

export interface BadgeCelebrationState {
  showModal: boolean;
  currentBadge: BadgeNotification | null;
  badgeQueue: BadgeNotification[];
}

export interface UseBadgeCelebrationOptions {
  /** Whether to show toast notifications (default: true) */
  showToast?: boolean;
  /** Whether to show celebration modal for significant badges (default: true) */
  showModal?: boolean;
  /** Duration in ms to show toast (default: 5000) */
  toastDuration?: number;
  /** Delay in ms between showing multiple badges (default: 500) */
  queueDelay?: number;
}

/**
 * Hook to manage badge celebration state and queueing.
 * Handles showing toast notifications and celebration modals for badge awards.
 */
export function useBadgeCelebration(
  newBadges: BadgeNotification[],
  options: UseBadgeCelebrationOptions = {}
) {
  const {
    showToast = true,
    showModal = true,
    toastDuration = 5000,
    queueDelay = 500,
  } = options;

  const [state, setState] = useState<BadgeCelebrationState>({
    showModal: false,
    currentBadge: null,
    badgeQueue: [],
  });

  const [shownBadgeIds] = useState<Set<string>>(new Set());

  // Process badge queue
  useEffect(() => {
    if (newBadges.length === 0) {
      return;
    }

    // Filter out badges we've already shown
    const unseenBadges = newBadges.filter(
      (badge) => !shownBadgeIds.has(badge.id)
    );

    if (unseenBadges.length === 0) {
      return;
    }

    // Mark badges as shown
    unseenBadges.forEach((badge) => shownBadgeIds.add(badge.id));

    // Add to queue
    setState((prev) => ({
      ...prev,
      badgeQueue: [...prev.badgeQueue, ...unseenBadges],
    }));
  }, [newBadges, shownBadgeIds]);

  // Process queue
  useEffect(() => {
    if (state.badgeQueue.length === 0 || state.showModal) {
      return;
    }

    const processNext = () => {
      const [nextBadge, ...remainingQueue] = state.badgeQueue;

      // Show toast notification
      if (showToast) {
        toast(
          <BadgeToast
            badgeName={nextBadge.badgeName}
            badgeIcon={nextBadge.badgeIcon}
            badgeColor={nextBadge.badgeColor}
            isAutoAwarded={nextBadge.isAutoAwarded}
            awardedBy={nextBadge.awardedBy}
          />,
          {
            autoClose: toastDuration,
            closeButton: true,
            position: "top-right",
            hideProgressBar: false,
            pauseOnHover: true,
          }
        );
      }

      // Show modal for significant badges (auto-awarded or first badge)
      if (
        showModal &&
        (nextBadge.isAutoAwarded || state.badgeQueue.length === 1)
      ) {
        setState({
          showModal: true,
          currentBadge: nextBadge,
          badgeQueue: remainingQueue,
        });
      } else {
        // Just update the queue
        setState((prev) => ({
          ...prev,
          badgeQueue: remainingQueue,
        }));
      }
    };

    // Add delay between processing badges to avoid overwhelming the user
    const timer = setTimeout(processNext, queueDelay);
    return () => clearTimeout(timer);
  }, [
    state.badgeQueue,
    state.showModal,
    showToast,
    showModal,
    toastDuration,
    queueDelay,
  ]);

  const closeModal = useCallback(() => {
    setState((prev) => ({
      ...prev,
      showModal: false,
      currentBadge: null,
    }));
  }, []);

  const dismissAll = useCallback(() => {
    setState({
      showModal: false,
      currentBadge: null,
      badgeQueue: [],
    });
  }, []);

  return {
    showModal: state.showModal,
    currentBadge: state.currentBadge,
    queueLength: state.badgeQueue.length,
    closeModal,
    dismissAll,
  };
}
