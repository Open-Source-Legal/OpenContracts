/**
 * useResearchCompletionNotification - Listen for deep-research job completion
 * via WebSocket.
 *
 * Mirrors useExtractCompletionNotification: listens for the terminal
 * RESEARCH_REPORT_* notifications and fires a callback when the watched
 * report reaches a terminal state. Used by ResearchReportDetail to refetch
 * and stop polling the moment a run finishes (the backend does not emit
 * per-step progress events in v1, so the detail view polls while running and
 * relies on this hook for the prompt terminal flip).
 */

import { useCallback, useRef, useEffect, useMemo } from "react";
import {
  useNotificationWebSocket,
  NotificationUpdate,
  NotificationType,
} from "./useNotificationWebSocket";
import { getNumericIdFromGlobalId } from "../utils/idValidation";

const TERMINAL_RESEARCH_TYPES: NotificationType[] = [
  "RESEARCH_REPORT_COMPLETE",
  "RESEARCH_REPORT_FAILED",
  "RESEARCH_REPORT_CANCELLED",
];

export interface UseResearchCompletionNotificationOptions {
  /** The global ID of the research report to watch */
  reportId: string | null;
  /** Callback when the report reaches a terminal state */
  onComplete: () => void;
  /** Whether the hook is enabled (default: true) */
  enabled?: boolean;
}

export function useResearchCompletionNotification(
  options: UseResearchCompletionNotificationOptions
) {
  const { reportId, onComplete, enabled = true } = options;

  // Ref to track the callback to avoid reconnection on callback changes
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  // Decode the numeric PK once (notification.data.report_id is a raw PK).
  // Memoised because it feeds the handleNotificationCreated useCallback deps.
  const numericId = useMemo<number | null>(() => {
    try {
      return reportId ? getNumericIdFromGlobalId(reportId) : null;
    } catch {
      return null; // Invalid ID format
    }
  }, [reportId]);

  const handleNotificationCreated = useCallback(
    (notification: NotificationUpdate) => {
      if (!TERMINAL_RESEARCH_TYPES.includes(notification.notificationType)) {
        return;
      }
      const notificationReportId = notification.data?.report_id;
      if (
        numericId !== null &&
        notificationReportId !== undefined &&
        Number(notificationReportId) === numericId
      ) {
        onCompleteRef.current();
      }
    },
    [numericId]
  );

  const { connectionState } = useNotificationWebSocket({
    onNotificationCreated: handleNotificationCreated,
    enabled: enabled && numericId !== null,
  });

  return {
    connectionState,
  };
}

export default useResearchCompletionNotification;
