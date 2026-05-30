/**
 * Shared utility functions for deep-research report components.
 *
 * Used by ResearchReportDetail, ResearchReportListCard, and Corpus
 * ResearchReportCards to display status, progress, and metadata. Mirrors
 * the per-feature util pattern established by extractUtils.ts.
 */

import { JobStatus } from "../types/graphql-api";
import {
  RESEARCH_STATUS,
  RESEARCH_STATUS_COLORS,
  ResearchStatusLabel,
} from "../assets/configurations/constants";

export type ResearchStatusColor =
  (typeof RESEARCH_STATUS_COLORS)[keyof typeof RESEARCH_STATUS_COLORS];

export interface ResearchStatusInfo {
  label: ResearchStatusLabel;
  color: ResearchStatusColor;
}

/** Map a backend JobStatus value to a display label + chip color. */
export function getResearchStatus(
  status: string | null | undefined
): ResearchStatusInfo {
  switch (status) {
    case JobStatus.Queued:
      return {
        label: RESEARCH_STATUS.QUEUED,
        color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.QUEUED],
      };
    case JobStatus.Running:
      return {
        label: RESEARCH_STATUS.RUNNING,
        color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.RUNNING],
      };
    case JobStatus.Completed:
      return {
        label: RESEARCH_STATUS.COMPLETED,
        color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.COMPLETED],
      };
    case JobStatus.Failed:
      return {
        label: RESEARCH_STATUS.FAILED,
        color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.FAILED],
      };
    case JobStatus.Cancelled:
      return {
        label: RESEARCH_STATUS.CANCELLED,
        color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.CANCELLED],
      };
    default:
      return {
        label: RESEARCH_STATUS.QUEUED,
        color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.QUEUED],
      };
  }
}

/** True for terminal states (no further progress expected). */
export function isTerminalResearchStatus(
  status: string | null | undefined
): boolean {
  return (
    status === JobStatus.Completed ||
    status === JobStatus.Failed ||
    status === JobStatus.Cancelled
  );
}

/** Format an ISO date string to e.g. "Jan 15, 2024". */
export function formatResearchDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** Format a duration in seconds to a compact "Xm Ys" / "Ys" string. */
export function formatResearchDuration(
  seconds: number | null | undefined
): string | null {
  if (seconds == null || Number.isNaN(seconds)) return null;
  const total = Math.max(0, Math.round(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}
