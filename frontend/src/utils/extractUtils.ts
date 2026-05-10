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
