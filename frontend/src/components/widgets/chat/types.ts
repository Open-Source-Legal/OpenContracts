/**
 * Shared types for the chat widget files.
 *
 * Lives in its own module so sibling style modules (e.g.
 * `ChatMessageTimeline.styles.ts`) and component modules (e.g.
 * `ChatMessageTimeline.tsx`, `ChatMessageToolUsage.tsx`) can pull the type
 * without re-creating the `ChatMessage.tsx` ↔ styles circular import that
 * arose when `TimelineEntry` was originally defined in `ChatMessage.tsx`.
 */

/**
 * One entry in the agent's reasoning timeline. Drives the rendering of
 * thoughts, content chunks, tool calls/results, sources, status updates
 * and compaction notes.
 *
 * Rich-mention agent delegation (Task 13): when the conductor delegates a
 * turn to a sub-agent (pinned OR unpinned), the conductor's timeline
 * carries the standard ``tool_call``/``tool_result`` pair AND — when the
 * backend has resolved the underlying ``AgentConfiguration`` — the new
 * optional ``agentId`` / ``agentSlug`` fields. The Timeline renderer uses
 * these to surface an ``@<slug>`` chip in place of the raw
 * ``delegate_to_<slug>`` tool name so users can see WHO the conductor
 * handed off to without parsing the tool string.
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
  /**
   * Optional ``AgentConfiguration`` pk attribution for delegated tool
   * calls/results. Backend ``StreamRelay`` (delegation_tools.py) attaches
   * these to ASYNC_THOUGHT frames; the consumer also persists them on the
   * conductor's ``data.timeline`` list so they survive a page reload.
   */
  agentId?: number | string;
  /** Slug of the delegated sub-agent (e.g. ``"research-bot"``). */
  agentSlug?: string;
}
