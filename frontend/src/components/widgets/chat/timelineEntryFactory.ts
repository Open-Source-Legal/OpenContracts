/**
 * timelineEntryFactory
 *
 * Pure helpers for converting backend ``ASYNC_THOUGHT`` frames into a
 * ``TimelineEntry`` that the chat UI can render. Extracted from
 * ``ChatTray.tsx`` and ``CorpusChat.tsx`` because the mapping (5 fields:
 * tool / args / result / agentId / agentSlug, plus the type-discrimination
 * for ``tool_call`` vs ``tool_result`` vs ``compaction``) was duplicated
 * byte-for-byte between the two surfaces. Centralising it removes a
 * recurring drift risk every time the delegation payload grows a new
 * field.
 */

import type { MessageData } from "../../chat/types";
import type { TimelineEntry } from "./types";

/**
 * Derive the timeline entry type from the shape of an ``ASYNC_THOUGHT``
 * payload:
 *   - compaction frames produce a ``compaction`` row,
 *   - frames carrying a ``tool_name`` AND ``args`` produce a ``tool_call``,
 *   - frames carrying only ``tool_name`` (no args) produce a
 *     ``tool_result`` (the backend re-emits the tool name when it
 *     forwards the call's return value),
 *   - everything else is a generic ``thought``.
 *
 * Exported separately so callers that need the ``compaction`` discriminator
 * can fork on it without re-implementing the rule.
 */
export const deriveTimelineEntryType = (
  data: MessageData["data"] | undefined
): TimelineEntry["type"] => {
  if (data?.compaction) return "compaction";
  if (data?.tool_name && data?.args) return "tool_call";
  if (data?.tool_name && !data?.args) return "tool_result";
  return "thought";
};

/**
 * Build a ``TimelineEntry`` from an ``ASYNC_THOUGHT`` frame.
 *
 * The two consumers — ``ChatTray.appendThoughtToMessage`` and
 * ``CorpusChat.appendThoughtToMessage`` — were drifting because each
 * maintained its own copy of this mapping (Task 13 added ``agentId``/
 * ``agentSlug`` to both independently). Owning the projection in one
 * place ensures any future field (e.g. ``tool_call_id`` echo) lands on
 * both surfaces by default.
 */
export const buildTimelineEntryFromAsyncThought = (
  thoughtText: string,
  data: MessageData["data"] | undefined,
  entryType: TimelineEntry["type"] = deriveTimelineEntryType(data)
): TimelineEntry => ({
  type: entryType,
  text: thoughtText,
  tool: data?.tool_name,
  args: data?.args,
  result: data?.tool_result,
  // Rich-mention agent delegation (Task 13): when the StreamRelay tags this
  // thought with a delegated sub-agent's AgentConfiguration, surface those
  // hints so the timeline renderer can swap the raw ``delegate_to_<slug>``
  // tool name for a styled ``@<slug>`` chip.
  agentId: data?.agent_id,
  agentSlug: data?.agent_slug,
});
