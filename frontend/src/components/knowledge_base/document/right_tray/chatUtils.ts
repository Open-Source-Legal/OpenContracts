/**
 * Pure utility functions for chat statistics, styling, and DOM helpers.
 * These have no React dependencies and operate on plain data / DOM nodes.
 */

import { MESSAGE_COUNT_COLORS } from "../../../../assets/configurations/constants";

/**
 * Resize a textarea to fit its content, capped at `maxHeight` (default 200px).
 * No-op when the textarea ref is null.
 */
export const adjustTextareaHeight = (
  textarea: HTMLTextAreaElement | null,
  maxHeight: number = 200
): void => {
  if (!textarea) return;
  textarea.style.height = "auto";
  const newHeight = Math.min(textarea.scrollHeight, maxHeight);
  textarea.style.height = `${newHeight}px`;
};

export interface MessageStats {
  max: number;
  min: number;
  mean: number;
  stdDev: number;
}

export interface MessageCountColorStyle {
  background: string;
  opacity: number;
  textColor: string;
}

/**
 * Calculate statistical metrics (max, min, mean, stdDev) for message counts
 * across a list of conversations.
 *
 * @param conversations - Array of conversation objects with chatMessages.totalCount
 * @returns An object with max, min, mean, and stdDev fields.
 */
export const calculateMessageStats = (
  conversations: Array<{ chatMessages?: { totalCount?: number } | null }>
): MessageStats => {
  const counts = conversations.map(
    (conv) => conv?.chatMessages?.totalCount || 0
  );

  if (counts.length === 0) {
    return { max: 0, min: 0, mean: 0, stdDev: 0 };
  }

  const max = counts.reduce((a, b) => Math.max(a, b), 0);
  const min = counts.reduce((a, b) => Math.min(a, b), Infinity);
  const sum = counts.reduce((a, b) => a + b, 0);
  const mean = sum / counts.length;

  // Calculate standard deviation
  const variance =
    counts.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / counts.length;
  const stdDev = Math.sqrt(variance);

  return { max, min, mean, stdDev };
};

/**
 * Determine the background gradient, opacity, and text color for a message
 * count badge based on how the count relates to overall statistics (z-score).
 *
 * @param count - The message count for a specific conversation.
 * @param stats - Aggregate statistics from calculateMessageStats.
 * @returns A style object with background, opacity, and textColor.
 */
export const getMessageCountColor = (
  count: number,
  stats: MessageStats
): MessageCountColorStyle => {
  const C = MESSAGE_COUNT_COLORS;

  if (count === 0) {
    return {
      background: `linear-gradient(135deg, ${C.ZERO_GRADIENT_START} 0%, ${C.ZERO_GRADIENT_END} 100%)`,
      opacity: C.ZERO_OPACITY,
      textColor: C.ZERO_TEXT,
    };
  }

  // Calculate z-score
  const zScore = (count - stats.mean) / (stats.stdDev || 1);

  // Convert z-score to a 0-1 scale using sigmoid function
  const intensity = 1 / (1 + Math.exp(-zScore));

  // Create gradient based on intensity
  return {
    background: `linear-gradient(135deg,
      rgba(${C.PRIMARY_R}, ${C.PRIMARY_G}, ${C.PRIMARY_B}, ${
      C.BASE_ALPHA_START + intensity * C.INTENSITY_ALPHA_START
    }) 0%,
      rgba(${C.SECONDARY_R}, ${C.SECONDARY_G}, ${C.SECONDARY_B}, ${
      C.BASE_ALPHA_END + intensity * C.INTENSITY_ALPHA_END
    }) 100%)`,
    opacity: C.BASE_OPACITY + intensity * C.INTENSITY_OPACITY,
    textColor: intensity > C.LIGHT_TEXT_THRESHOLD ? C.LIGHT_TEXT : C.DARK_TEXT,
  };
};
