/**
 * Unit tests for ``buildTimelineEntryFromAsyncThought`` /
 * ``deriveTimelineEntryType``.
 *
 * The helpers replace ~22 lines of duplicated mapping logic in
 * ``ChatTray.appendThoughtToMessage`` and
 * ``CorpusChat.appendThoughtToMessage``. Pinning the projection ensures
 * any future field added to the ASYNC_THOUGHT payload (e.g. tool_call_id
 * echo) lands on both chat surfaces by default.
 */

import { describe, it, expect } from "vitest";

import type { MessageData } from "../../../chat/types";
import {
  buildTimelineEntryFromAsyncThought,
  deriveTimelineEntryType,
} from "../timelineEntryFactory";

describe("deriveTimelineEntryType", () => {
  it("returns 'compaction' when the frame carries a compaction notice", () => {
    const data: MessageData["data"] = {
      message_id: "1",
      compaction: {
        tokens_before: 5000,
        tokens_after: 1500,
        context_window: 8000,
      },
    };
    expect(deriveTimelineEntryType(data)).toBe("compaction");
  });

  it("returns 'tool_call' when tool_name + args are both present", () => {
    expect(
      deriveTimelineEntryType({
        tool_name: "search",
        args: { q: "x" },
      })
    ).toBe("tool_call");
  });

  it("returns 'tool_result' when tool_name is present without args", () => {
    expect(deriveTimelineEntryType({ tool_name: "search" })).toBe(
      "tool_result"
    );
  });

  it("defaults to 'thought' for plain frames", () => {
    expect(deriveTimelineEntryType({ message_id: "1" })).toBe("thought");
    expect(deriveTimelineEntryType(undefined)).toBe("thought");
  });
});

describe("buildTimelineEntryFromAsyncThought", () => {
  it("forwards agent attribution metadata when present", () => {
    const entry = buildTimelineEntryFromAsyncThought("Delegating", {
      message_id: "m1",
      tool_name: "delegate_to_research_bot",
      args: { prompt: "x" },
      agent_id: "ag-1",
      agent_slug: "research-bot",
    });
    expect(entry).toEqual({
      type: "tool_call",
      text: "Delegating",
      tool: "delegate_to_research_bot",
      args: { prompt: "x" },
      result: undefined,
      agentId: "ag-1",
      agentSlug: "research-bot",
    });
  });

  it("omits agent attribution when the frame is a plain thought", () => {
    const entry = buildTimelineEntryFromAsyncThought("Analyzing...", {
      message_id: "m1",
    });
    expect(entry).toEqual({
      type: "thought",
      text: "Analyzing...",
      tool: undefined,
      args: undefined,
      result: undefined,
      agentId: undefined,
      agentSlug: undefined,
    });
  });

  it("honors a caller-supplied entryType override (compaction side-effect path)", () => {
    // CorpusChat / ChatTray derive the type once to gate side-effects
    // (compaction notice banner) then pass it through to the factory so
    // both code paths agree on the row type.
    const entry = buildTimelineEntryFromAsyncThought(
      "Compacted",
      {
        message_id: "m1",
        compaction: {
          tokens_before: 5000,
          tokens_after: 1500,
          context_window: 8000,
        },
      },
      "compaction"
    );
    expect(entry.type).toBe("compaction");
    expect(entry.text).toBe("Compacted");
  });
});
