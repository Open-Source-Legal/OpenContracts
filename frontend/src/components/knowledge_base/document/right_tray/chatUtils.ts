/**
 * Pure utility functions / DOM helpers for the chat UI.
 * These have no React dependencies and operate on plain DOM nodes.
 */

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
