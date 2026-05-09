/**
 * Shared types for the chat widget files.
 *
 * Lives in its own module so sibling files (`ChatMessage.styles.ts`,
 * `ChatMessageTimeline.tsx`) can pull the type without re-creating the
 * `ChatMessage.tsx` ↔ `ChatMessage.styles.ts` circular import that arose
 * when `TimelineEntry` was originally defined in `ChatMessage.tsx`.
 */

/**
 * One entry in the agent's reasoning timeline. Drives the rendering of
 * thoughts, content chunks, tool calls/results, sources, status updates
 * and compaction notes.
 */
export interface TimelineEntry {
  type:
    | "thought"
    | "content"
    | "tool_call"
    | "tool_result"
    | "sources"
    | "status"
    | "compaction";
  text?: string;
  tool?: string;
  args?: Record<string, unknown>;
  result?: string;
  count?: number;
  metadata?: Record<string, unknown>;
  msg?: string;
}
