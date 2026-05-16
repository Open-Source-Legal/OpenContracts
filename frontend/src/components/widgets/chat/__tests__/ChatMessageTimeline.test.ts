/**
 * Unit tests for ``getAgentSlugFromTimelineEntry``.
 *
 * The helper drives the rich-mention agent delegation chip rendering in
 * ``getTimelineTitle``. Two branches matter:
 *   1. The explicit ``agentSlug`` (forwarded by the backend StreamRelay
 *      on ASYNC_THOUGHT frames).
 *   2. The regex fallback that extracts ``snake_slug`` from the
 *      ``delegate_to_<snake_slug>`` tool name persisted on the
 *      conductor's ``ChatMessage.data.timeline`` snapshot.
 *
 * Pinning both branches keeps the chip from silently regressing if the
 * backend ever changes the timeline persistence shape (e.g. moves the
 * agent metadata into a dedicated field) or if the tool naming
 * convention changes.
 */

import { describe, it, expect } from "vitest";

import { getAgentSlugFromTimelineEntry } from "../ChatMessageTimeline";
import type { TimelineEntry } from "../types";

describe("getAgentSlugFromTimelineEntry", () => {
  it("returns the explicit agentSlug when present (live stream branch)", () => {
    const entry: TimelineEntry = {
      type: "tool_call",
      tool: "delegate_to_research_bot",
      agentSlug: "research-bot",
      agentId: "ag-1",
    };
    expect(getAgentSlugFromTimelineEntry(entry)).toBe("research-bot");
  });

  it("falls back to parsing the delegate_to_<slug> tool name (rehydrated branch)", () => {
    // Persisted timeline snapshots (ChatMessage.data.timeline) drop the
    // agent_slug field today — only the tool name survives.
    const entry: TimelineEntry = {
      type: "tool_call",
      tool: "delegate_to_research_bot",
    };
    expect(getAgentSlugFromTimelineEntry(entry)).toBe("research_bot");
  });

  it("returns undefined for non-delegation tool calls", () => {
    const entry: TimelineEntry = {
      type: "tool_call",
      tool: "search_corpus",
    };
    expect(getAgentSlugFromTimelineEntry(entry)).toBeUndefined();
  });

  it("returns undefined for thought entries with no tool", () => {
    const entry: TimelineEntry = {
      type: "thought",
      text: "Analyzing...",
    };
    expect(getAgentSlugFromTimelineEntry(entry)).toBeUndefined();
  });

  it("prefers explicit agentSlug even if tool name would parse differently", () => {
    // Belt-and-suspenders: backend may emit a canonical kebab-case slug
    // even though the tool name was generated from snake_case. The
    // explicit slug always wins.
    const entry: TimelineEntry = {
      type: "tool_call",
      tool: "delegate_to_some_other_name",
      agentSlug: "canonical-slug",
    };
    expect(getAgentSlugFromTimelineEntry(entry)).toBe("canonical-slug");
  });
});
