/**
 * Unit tests for ChatMessage utility functions.
 *
 * Tests the tool call extraction and formatting logic used by the
 * ToolUsageIndicator component.
 */

import { describe, it, expect } from "vitest";

import { TOOL_UNKNOWN_LABEL } from "../../../../assets/configurations/constants";
import {
  extractToolCalls,
  formatToolName,
  TimelineEntry,
} from "../ChatMessage";

describe("extractToolCalls", () => {
  it("returns empty array for timeline with no tool calls", () => {
    const timeline: TimelineEntry[] = [
      { type: "thought", text: "Analyzing..." },
      { type: "status", msg: "run_finished" },
    ];
    expect(extractToolCalls(timeline)).toEqual([]);
  });

  it("extracts a single tool call with matching result", () => {
    const timeline: TimelineEntry[] = [
      {
        type: "tool_call",
        tool: "similarity_search",
        args: { query: "payment" },
      },
      {
        type: "tool_result",
        tool: "similarity_search",
        result: "Found 3 annotations",
      },
    ];
    const result = extractToolCalls(timeline);
    expect(result).toHaveLength(1);
    expect(result[0].tool).toBe("similarity_search");
    expect(result[0].args).toEqual({ query: "payment" });
    expect(result[0].result).toBe("Found 3 annotations");
  });

  it("handles tool call without a matching result", () => {
    const timeline: TimelineEntry[] = [
      { type: "tool_call", tool: "my_tool", args: { x: 1 } },
      { type: "status", msg: "run_finished" },
    ];
    const result = extractToolCalls(timeline);
    expect(result).toHaveLength(1);
    expect(result[0].tool).toBe("my_tool");
    expect(result[0].result).toBeUndefined();
  });

  it("correctly pairs duplicate calls to the same tool", () => {
    const timeline: TimelineEntry[] = [
      {
        type: "tool_call",
        tool: "similarity_search",
        args: { query: "first" },
      },
      {
        type: "tool_result",
        tool: "similarity_search",
        result: "Result 1",
      },
      {
        type: "tool_call",
        tool: "similarity_search",
        args: { query: "second" },
      },
      {
        type: "tool_result",
        tool: "similarity_search",
        result: "Result 2",
      },
    ];
    const result = extractToolCalls(timeline);
    expect(result).toHaveLength(2);
    expect(result[0].args).toEqual({ query: "first" });
    expect(result[0].result).toBe("Result 1");
    expect(result[1].args).toEqual({ query: "second" });
    expect(result[1].result).toBe("Result 2");
  });

  it("uses TOOL_UNKNOWN_LABEL when tool name is missing", () => {
    const timeline: TimelineEntry[] = [{ type: "tool_call" }];
    const result = extractToolCalls(timeline);
    expect(result).toHaveLength(1);
    expect(result[0].tool).toBe(TOOL_UNKNOWN_LABEL);
  });

  it("assigns unique stable IDs to each tool call", () => {
    const timeline: TimelineEntry[] = [
      { type: "tool_call", tool: "tool_a" },
      { type: "tool_call", tool: "tool_a" },
      { type: "tool_call", tool: "tool_b" },
    ];
    const result = extractToolCalls(timeline);
    const ids = result.map((c) => c.id);
    expect(new Set(ids).size).toBe(3);
  });

  it("skips non-tool timeline entries", () => {
    const timeline: TimelineEntry[] = [
      { type: "thought", text: "thinking..." },
      { type: "tool_call", tool: "search", args: { q: "x" } },
      { type: "sources", count: 5 },
      { type: "tool_result", tool: "search", result: "done" },
      { type: "content", text: "answer here" },
    ];
    const result = extractToolCalls(timeline);
    expect(result).toHaveLength(1);
    expect(result[0].tool).toBe("search");
    expect(result[0].result).toBe("done");
  });

  it("handles multiple different tools in sequence", () => {
    const timeline: TimelineEntry[] = [
      { type: "tool_call", tool: "search", args: { q: "a" } },
      { type: "tool_result", tool: "search", result: "Found 2" },
      { type: "tool_call", tool: "ask_document", args: { doc: 1 } },
      { type: "tool_result", tool: "ask_document", result: "Answer text" },
    ];
    const result = extractToolCalls(timeline);
    expect(result).toHaveLength(2);
    expect(result[0].tool).toBe("search");
    expect(result[1].tool).toBe("ask_document");
    expect(result[1].result).toBe("Answer text");
  });
});

describe("formatToolName", () => {
  it("converts snake_case to Title Case", () => {
    expect(formatToolName("similarity_search")).toBe("Similarity Search");
  });

  it("handles single word", () => {
    expect(formatToolName("search")).toBe("Search");
  });

  it("handles multiple underscores", () => {
    expect(formatToolName("search_exact_text")).toBe("Search Exact Text");
  });

  it("handles empty string", () => {
    expect(formatToolName("")).toBe("");
  });
});
