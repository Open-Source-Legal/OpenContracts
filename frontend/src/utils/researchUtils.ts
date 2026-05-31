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
    // CREATED is a transient pre-queue state; surface it as "Queued" (no warn).
    case JobStatus.Created:
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
      // A JobStatus value the frontend doesn't recognize (e.g. a new backend
      // state added before the frontend catches up). Surface it in dev so the
      // gap is visible rather than silently rendering an unrelated "Queued".
      // null/undefined is the legitimate "not set yet" case, so don't warn on it.
      if (status && process.env.NODE_ENV !== "production") {
        // eslint-disable-next-line no-console
        console.warn(
          `getResearchStatus: unrecognized JobStatus "${status}"; falling back to Queued.`
        );
      }
      return {
        label: RESEARCH_STATUS.QUEUED,
        color: RESEARCH_STATUS_COLORS[RESEARCH_STATUS.QUEUED],
      };
  }
}

/**
 * True for terminal states (no further progress expected).
 *
 * Only the not-yet-set case (null/undefined) and the explicitly non-terminal
 * states (Created, Queued, Running) return false. Any *unrecognized* status — e.g. a
 * new backend state shipped before the frontend catches up — is treated as
 * terminal so the detail view never polls indefinitely on a status it cannot
 * interpret. (getResearchStatus falls back to a "Queued" *label* for display,
 * but polling must key off this function, not that cosmetic fallback.)
 */
export function isTerminalResearchStatus(
  status: string | null | undefined
): boolean {
  if (status == null) return false;
  return (
    status !== JobStatus.Created &&
    status !== JobStatus.Queued &&
    status !== JobStatus.Running
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
