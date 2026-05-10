/**
 * Shared utility functions for extract-related components
 *
 * These utilities are used by ExtractDetail, ExtractListCard, and other
 * components that display extract status and metadata.
 */

import type { ExtractType } from "../types/graphql-api";
import {
  EXTRACT_STATUS,
  EXTRACT_STATUS_COLORS,
  ExtractStatus,
} from "../assets/configurations/constants";

/**
 * Extract status color type from the status colors constant
 */
export type ExtractStatusColor =
  (typeof EXTRACT_STATUS_COLORS)[keyof typeof EXTRACT_STATUS_COLORS];

export interface ExtractStatusInfo {
  label: ExtractStatus;
  color: ExtractStatusColor;
}

/**
 * Determines the status label and color for an extract based on its state
 *
 * Accepts a structural subset of ``ExtractType`` so call sites driven by
 * the slim ``ExtractListItem`` shape (no ``creator``, no ``corpus``)
 * compile without casts.
 *
 * @param extract - The extract to get status for
 * @returns Object containing the status label and color for display
 */
export function getExtractStatus(
  extract: Pick<ExtractType, "started" | "finished" | "error">
): ExtractStatusInfo {
  if (extract.started && !extract.finished && !extract.error) {
    return {
      label: EXTRACT_STATUS.RUNNING,
      color: EXTRACT_STATUS_COLORS[EXTRACT_STATUS.RUNNING],
    };
  }
  if (extract.finished) {
    return {
      label: EXTRACT_STATUS.COMPLETED,
      color: EXTRACT_STATUS_COLORS[EXTRACT_STATUS.COMPLETED],
    };
  }
  if (extract.error) {
    return {
      label: EXTRACT_STATUS.FAILED,
      color: EXTRACT_STATUS_COLORS[EXTRACT_STATUS.FAILED],
    };
  }
  return {
    label: EXTRACT_STATUS.NOT_STARTED,
    color: EXTRACT_STATUS_COLORS[EXTRACT_STATUS.NOT_STARTED],
  };
}

/**
 * Formats a date string to a human-readable format
 *
 * @param dateString - ISO date string to format
 * @returns Formatted date string (e.g., "Jan 15, 2024")
 */
export function formatExtractDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Minimum field surface ``formatExtractListStats`` reads. Mirrors the
 * shape declared in ``ExtractListCard`` so call sites driven by either
 * the slim ``ExtractListItem`` (``GET_EXTRACTS_FOR_LIST``) or the legacy
 * ``ExtractType`` (``GET_EXTRACTS``) compile without casts.
 */
export interface ExtractStatsItem {
  documentCount?: number | null;
  fullDocumentList?: ReadonlyArray<unknown> | null;
  fieldset?: {
    columnCount?: number | null;
    fullColumnList?: ReadonlyArray<unknown> | null;
  } | null;
  corpus?: { title?: string | null } | null;
}

/**
 * Build the human-readable stats line shown on an extract card —
 * ``"<n> documents [, <m> columns] [from <corpus>]"``.
 *
 * Prefers backend-provided ``documentCount`` / ``columnCount`` aggregates
 * (cheap; avoid the per-doc permission fan-out the legacy list-length
 * fallbacks pay for) and falls through to ``fullDocumentList.length`` /
 * ``fullColumnList.length`` so callers still on the heavy ``GET_EXTRACTS``
 * query keep working without extra plumbing.
 */
export function formatExtractListStats(extract: ExtractStatsItem): string[] {
  const stats: string[] = [];

  const docCount =
    extract.documentCount ?? extract.fullDocumentList?.length ?? 0;
  stats.push(`${docCount} ${docCount === 1 ? "document" : "documents"}`);

  const columnCount =
    extract.fieldset?.columnCount ??
    extract.fieldset?.fullColumnList?.length ??
    0;
  if (columnCount > 0) {
    stats.push(`${columnCount} ${columnCount === 1 ? "column" : "columns"}`);
  }

  if (extract.corpus?.title) {
    stats.push(`from ${extract.corpus.title}`);
  }

  return stats;
}
