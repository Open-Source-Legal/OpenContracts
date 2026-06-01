import { useState, useCallback, useEffect, useRef } from "react";
import { useApolloClient } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import {
  useNotificationWebSocket,
  NotificationUpdate,
  NotificationType,
} from "./useNotificationWebSocket";
import { JobNotificationToast } from "../components/notifications/JobNotificationToast";
import { updateCacheForJobNotification } from "../utils/jobNotificationCacheUpdates";

/**
 * Job-related notification types that trigger real-time toasts.
 * Issue #624: Real-time notifications for job completion.
 */
const JOB_NOTIFICATION_TYPES: NotificationType[] = [
  "DOCUMENT_PROCESSED",
  "EXTRACT_COMPLETE",
  "ANALYSIS_COMPLETE",
  "ANALYSIS_FAILED",
  "EXPORT_COMPLETE",
  // Deep-research terminal states (PROGRESS is reserved; not a completion toast)
  "RESEARCH_REPORT_COMPLETE",
  "RESEARCH_REPORT_FAILED",
  "RESEARCH_REPORT_CANCELLED",
];

/** Notification types whose toast deep-links to a /research/:slug report. */
const RESEARCH_NOTIFICATION_TYPES: NotificationType[] = [
  "RESEARCH_REPORT_COMPLETE",
  "RESEARCH_REPORT_FAILED",
  "RESEARCH_REPORT_CANCELLED",
];

export interface JobNotification {
  id: string;
  type: NotificationType;
  createdAt: string;
  data: Record<string, unknown>;
}

export interface UseJobNotificationsOptions {
  /** Whether to show toast notifications (default: true) */
  showToast?: boolean;
  /** Duration in ms to show toast (default: 5000) */
  toastDuration?: number;
  /** Whether the hook is enabled (default: true) */
  enabled?: boolean;
}

/**
 * Hook to detect job completion notifications via WebSocket and show toasts.
 *
 * Filters for job-related notification types (document processing, extracts,
 * analyses, exports) and displays toast notifications in real-time.
 *
 * Issue #624: Real-time notifications for job completion.
 */
export function useJobNotifications(options: UseJobNotificationsOptions = {}) {
  const { showToast = true, toastDuration = 5000, enabled = true } = options;

  const client = useApolloClient();
  const navigate = useNavigate();
  const [recentJobs, setRecentJobs] = useState<JobNotification[]>([]);

  // Track shown notification IDs to prevent duplicate toasts
  const shownIdsRef = useRef<Set<string>>(new Set());

  // Handle incoming job notifications
  const handleNotificationCreated = useCallback(
    (notification: NotificationUpdate) => {
      // Only process job-related notifications
      if (
        !JOB_NOTIFICATION_TYPES.includes(
          notification.notificationType as NotificationType
        )
      ) {
        return;
      }

      // Prevent duplicate toasts for same notification
      if (shownIdsRef.current.has(notification.id)) {
        return;
      }
      shownIdsRef.current.add(notification.id);

      const jobNotification: JobNotification = {
        id: notification.id,
        type: notification.notificationType as NotificationType,
        createdAt: notification.createdAt,
        data: notification.data || {},
      };

      // Update Apollo cache to reflect job completion state
      updateCacheForJobNotification(
        client.cache,
        jobNotification.type,
        jobNotification.data
      );

      // Add to recent jobs list
      setRecentJobs((prev) => [...prev.slice(-49), jobNotification]);

      // Show toast notification
      if (showToast) {
        // Research toasts deep-link to the report; the slug arrives in the
        // notification payload (research_tasks._send_completion_notification).
        const reportSlug = jobNotification.data?.report_slug as
          | string
          | undefined;
        const onClick =
          RESEARCH_NOTIFICATION_TYPES.includes(jobNotification.type) &&
          reportSlug
            ? () => navigate(`/research/${reportSlug}`)
            : undefined;

        toast(
          <JobNotificationToast
            notification={jobNotification}
            onClick={onClick}
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
    },
    [client.cache, showToast, toastDuration, navigate]
  );

  // Subscribe to WebSocket notifications
  const { connectionState } = useNotificationWebSocket({
    onNotificationCreated: handleNotificationCreated,
    enabled,
  });

  // Clear shown IDs periodically to prevent memory leak
  useEffect(() => {
    const interval = setInterval(() => {
      // Keep only last 100 IDs
      if (shownIdsRef.current.size > 100) {
        const idsArray = Array.from(shownIdsRef.current);
        shownIdsRef.current = new Set(idsArray.slice(-100));
      }
    }, 60000); // Every minute

    return () => clearInterval(interval);
  }, []);

  const clearRecentJobs = useCallback(() => {
    setRecentJobs([]);
  }, []);

  return {
    recentJobs,
    clearRecentJobs,
    connectionState,
  };
}
