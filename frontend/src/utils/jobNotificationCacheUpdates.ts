import { ApolloCache } from "@apollo/client";
import type { NotificationType } from "../hooks/useNotificationWebSocket";
import { toGlobalId } from "./idValidation";

/**
 * Cache update utilities for job completion notifications.
 *
 * When WebSocket notifications arrive indicating job completion, these functions
 * update the Apollo cache to reflect the new state without requiring a refetch.
 *
 * Issue #624: Real-time cache updates for job completion notifications.
 */

interface JobNotificationData {
  // Document processed
  document_id?: number;
  // Extract complete
  extract_id?: number;
  // Analysis complete/failed
  analysis_id?: number;
  // Export complete
  export_id?: number;
  // Research report terminal (report_id arrives as a stringified PK)
  report_id?: number | string;
  status?: string;
}

/**
 * Update cache when a document finishes processing.
 * Sets backendLock to false.
 */
function updateDocumentProcessed(
  cache: ApolloCache<unknown>,
  data: JobNotificationData
): void {
  if (!data.document_id) return;

  const globalId = toGlobalId("DocumentType", data.document_id);
  const cacheId = cache.identify({ __typename: "DocumentType", id: globalId });

  if (cacheId) {
    cache.modify({
      id: cacheId,
      fields: {
        backendLock: () => false,
      },
      broadcast: true,
    });
  }
}

/**
 * Update cache when an extract completes.
 * Sets finished timestamp.
 */
function updateExtractComplete(
  cache: ApolloCache<unknown>,
  data: JobNotificationData
): void {
  if (!data.extract_id) return;

  const globalId = toGlobalId("ExtractType", data.extract_id);
  const cacheId = cache.identify({ __typename: "ExtractType", id: globalId });

  if (cacheId) {
    cache.modify({
      id: cacheId,
      fields: {
        finished: () => new Date().toISOString(),
      },
      broadcast: true,
    });
  }
}

/**
 * Update cache when an analysis completes successfully.
 * Sets status to COMPLETED and analysisCompleted timestamp.
 */
function updateAnalysisComplete(
  cache: ApolloCache<unknown>,
  data: JobNotificationData
): void {
  if (!data.analysis_id) return;

  const globalId = toGlobalId("AnalysisType", data.analysis_id);
  const cacheId = cache.identify({ __typename: "AnalysisType", id: globalId });

  if (cacheId) {
    cache.modify({
      id: cacheId,
      fields: {
        status: () => "COMPLETED",
        analysisCompleted: () => new Date().toISOString(),
      },
      broadcast: true,
    });
  }
}

/**
 * Update cache when an analysis fails.
 * Sets status to FAILED.
 */
function updateAnalysisFailed(
  cache: ApolloCache<unknown>,
  data: JobNotificationData
): void {
  if (!data.analysis_id) return;

  const globalId = toGlobalId("AnalysisType", data.analysis_id);
  const cacheId = cache.identify({ __typename: "AnalysisType", id: globalId });

  if (cacheId) {
    cache.modify({
      id: cacheId,
      fields: {
        status: () => "FAILED",
      },
      broadcast: true,
    });
  }
}

/**
 * Update cache when an export completes.
 * Sets backendLock to false and finished timestamp.
 */
function updateExportComplete(
  cache: ApolloCache<unknown>,
  data: JobNotificationData
): void {
  if (!data.export_id) return;

  const globalId = toGlobalId("UserExportType", data.export_id);
  const cacheId = cache.identify({
    __typename: "UserExportType",
    id: globalId,
  });

  if (cacheId) {
    cache.modify({
      id: cacheId,
      fields: {
        backendLock: () => false,
        finished: () => new Date().toISOString(),
      },
      broadcast: true,
    });
  }
}

/**
 * Update cache when a research report reaches a terminal state.
 * Writes the terminal status (and a completedAt timestamp) so any cached
 * list/detail flips without a manual refetch.
 */
function updateResearchReportTerminal(
  cache: ApolloCache<unknown>,
  data: JobNotificationData,
  fallbackStatus: string
): void {
  if (data.report_id == null) return;

  const globalId = toGlobalId("ResearchReportType", data.report_id);
  const cacheId = cache.identify({
    __typename: "ResearchReportType",
    id: globalId,
  });

  if (cacheId) {
    const nextStatus = data.status || fallbackStatus;
    cache.modify({
      id: cacheId,
      fields: {
        status: () => nextStatus,
        completedAt: (existing) => existing ?? new Date().toISOString(),
      },
      broadcast: true,
    });
  }
}

/**
 * Main function to update cache based on notification type.
 * Returns true if cache was updated, false otherwise.
 */
export function updateCacheForJobNotification(
  cache: ApolloCache<unknown>,
  notificationType: NotificationType,
  data: Record<string, unknown>
): boolean {
  const jobData = data as JobNotificationData;

  switch (notificationType) {
    case "DOCUMENT_PROCESSED":
      updateDocumentProcessed(cache, jobData);
      return !!jobData.document_id;

    case "EXTRACT_COMPLETE":
      updateExtractComplete(cache, jobData);
      return !!jobData.extract_id;

    case "ANALYSIS_COMPLETE":
      updateAnalysisComplete(cache, jobData);
      return !!jobData.analysis_id;

    case "ANALYSIS_FAILED":
      updateAnalysisFailed(cache, jobData);
      return !!jobData.analysis_id;

    case "EXPORT_COMPLETE":
      updateExportComplete(cache, jobData);
      return !!jobData.export_id;

    case "RESEARCH_REPORT_COMPLETE":
      updateResearchReportTerminal(cache, jobData, "COMPLETED");
      return jobData.report_id != null;

    case "RESEARCH_REPORT_FAILED":
      updateResearchReportTerminal(cache, jobData, "FAILED");
      return jobData.report_id != null;

    case "RESEARCH_REPORT_CANCELLED":
      updateResearchReportTerminal(cache, jobData, "CANCELLED");
      return jobData.report_id != null;

    default:
      return false;
  }
}
