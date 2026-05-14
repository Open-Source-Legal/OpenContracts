/**
 * Vitest hook coverage for `useChatStreamHandlers`.
 *
 * Built to lift codecov patch coverage for the new stream-handler bundle
 * extracted in PR #1639. Exercises every public branch:
 *   - updateMessageApprovalStatus (with/without pending match)
 *   - appendStreamingTokenToChat (no-token, append, new message, auto-scroll)
 *   - appendThoughtToMessage (compaction / tool_call / tool_result / new msg)
 *   - finalizeStreamingResponse (matched id, fallback-to-last-assistant, empty list)
 *   - handleCompleteMessage (missing-id warn, new message, in-place update)
 *   - mergeSourcesIntoMessage (empty guard, new msg, existing msg de-dupe)
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook } from "../../../../../test-utils/renderHook";
import {
  useChatStreamHandlers,
  UseChatStreamHandlersParams,
} from "../useChatStreamHandlers";
import type { ChatMessageProps } from "../../../../widgets/chat/ChatMessage";
import type {
  ChatMessage,
  ChatSourceState,
} from "../../../../annotator/context/ChatSourceAtom";
import type {
  CompactionNotice,
  WebSocketSources,
} from "../../../../chat/types";
import type { PendingApproval } from "../ApprovalOverlay";

interface HarnessState {
  chat: ChatMessageProps[];
  serverMessages: ChatMessageProps[];
  chatSource: ChatSourceState;
  compaction: CompactionNotice | null;
  pendingApproval: PendingApproval | null;
}

/**
 * Build a fresh harness object that mimics the React state surface ChatTray
 * passes into the hook. We materialise actual setState dispatchers so the
 * hook receives stable refs and useCallback deps don't churn between calls.
 */
function buildHarness(initial?: Partial<HarnessState>) {
  const state: HarnessState = {
    chat: [],
    serverMessages: [],
    chatSource: {
      messages: [],
      selectedMessageId: null,
      selectedSourceIndex: null,
    },
    compaction: null,
    pendingApproval: null,
    ...initial,
  };

  const setChat: UseChatStreamHandlersParams["setChat"] = (updater) => {
    state.chat =
      typeof updater === "function"
        ? (updater as (p: ChatMessageProps[]) => ChatMessageProps[])(state.chat)
        : updater;
  };
  const setServerMessages: UseChatStreamHandlersParams["setServerMessages"] = (
    updater
  ) => {
    state.serverMessages =
      typeof updater === "function"
        ? (updater as (p: ChatMessageProps[]) => ChatMessageProps[])(
            state.serverMessages
          )
        : updater;
  };
  const setChatSourceState: UseChatStreamHandlersParams["setChatSourceState"] =
    (updater) => {
      state.chatSource =
        typeof updater === "function"
          ? (updater as (p: ChatSourceState) => ChatSourceState)(
              state.chatSource
            )
          : updater;
    };
  const setCompactionNotice: UseChatStreamHandlersParams["setCompactionNotice"] =
    (updater) => {
      state.compaction =
        typeof updater === "function"
          ? (
              updater as (p: CompactionNotice | null) => CompactionNotice | null
            )(state.compaction)
          : updater;
    };
  const setPendingApproval: UseChatStreamHandlersParams["setPendingApproval"] =
    (updater) => {
      state.pendingApproval =
        typeof updater === "function"
          ? (updater as (p: PendingApproval | null) => PendingApproval | null)(
              state.pendingApproval
            )
          : updater;
    };

  // jsdom DIV that supports the scroll math the hook reads.
  const container = document.createElement("div");
  Object.defineProperty(container, "scrollTop", {
    configurable: true,
    writable: true,
    value: 0,
  });
  Object.defineProperty(container, "scrollHeight", {
    configurable: true,
    writable: true,
    value: 1000,
  });
  Object.defineProperty(container, "clientHeight", {
    configurable: true,
    writable: true,
    value: 500,
  });
  container.scrollTo = vi.fn();
  const messagesContainerRef = {
    current: container,
  } as React.RefObject<HTMLDivElement>;

  const params: UseChatStreamHandlersParams = {
    setChat,
    setServerMessages,
    setChatSourceState,
    setCompactionNotice,
    setPendingApproval,
    messagesContainerRef,
  };

  return { state, params, container };
}

function setupHook(initial?: Partial<HarnessState>) {
  const harness = buildHarness(initial);
  const { result } = renderHook(() => useChatStreamHandlers(harness.params));
  return { ...harness, result };
}

describe("useChatStreamHandlers", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  describe("updateMessageApprovalStatus", () => {
    it("clears pendingApproval when ids match and stamps approval status into both arrays", () => {
      const { result, state } = setupHook({
        chat: [
          {
            messageId: "m1",
            user: "A",
            content: "x",
            timestamp: "",
            isAssistant: true,
          },
          {
            messageId: "other",
            user: "A",
            content: "y",
            timestamp: "",
            isAssistant: true,
          },
        ],
        serverMessages: [
          {
            messageId: "m1",
            user: "A",
            content: "x",
            timestamp: "",
            isAssistant: true,
          },
        ],
        pendingApproval: {
          messageId: "m1",
          toolCall: { name: "t", arguments: {} },
        },
      });

      act(() => {
        result.current.updateMessageApprovalStatus("m1", "approved");
      });

      expect(state.pendingApproval).toBeNull();
      expect(state.chat[0]).toMatchObject({
        approvalStatus: "approved",
        isComplete: true,
      });
      expect(state.chat[1].approvalStatus).toBeUndefined();
      expect(state.serverMessages[0]).toMatchObject({
        approvalStatus: "approved",
        isComplete: true,
      });
    });

    it("preserves pendingApproval when ids do not match", () => {
      const { result, state } = setupHook({
        pendingApproval: {
          messageId: "different",
          toolCall: { name: "t", arguments: {} },
        },
      });

      act(() => {
        result.current.updateMessageApprovalStatus("m1", "rejected");
      });

      expect(state.pendingApproval?.messageId).toBe("different");
    });
  });

  describe("appendStreamingTokenToChat", () => {
    it("returns empty string and is a no-op for empty token", () => {
      const { result, state, container } = setupHook();

      let returned = "z";
      act(() => {
        returned = result.current.appendStreamingTokenToChat("");
      });
      expect(returned).toBe("");
      expect(state.chat).toHaveLength(0);
      expect(container.scrollTo).not.toHaveBeenCalled();
    });

    it("appends a token to the trailing assistant message when one exists", () => {
      const { result, state } = setupHook({
        chat: [
          {
            messageId: "m_existing",
            user: "Assistant",
            content: "Hello",
            timestamp: "",
            isAssistant: true,
            isComplete: false,
          },
        ],
      });

      let id = "";
      act(() => {
        id = result.current.appendStreamingTokenToChat(" world");
      });
      expect(id).toBe("m_existing");
      expect(state.chat).toHaveLength(1);
      expect(state.chat[0].content).toBe("Hello world");
      expect(state.chat[0].isComplete).toBe(false);
    });

    it("creates a new assistant message when no streaming message is present", () => {
      const { result, state } = setupHook({
        chat: [
          // last message is the user — should not be appended to.
          {
            messageId: "u1",
            user: "U",
            content: "ask",
            timestamp: "",
            isAssistant: false,
          },
        ],
      });

      let id = "";
      act(() => {
        id = result.current.appendStreamingTokenToChat("Hi", "override-id");
      });
      expect(id).toBe("override-id");
      expect(state.chat).toHaveLength(2);
      expect(state.chat[1]).toMatchObject({
        messageId: "override-id",
        content: "Hi",
        isAssistant: true,
        isComplete: false,
      });
    });

    it("schedules an auto-scroll when the user is near the bottom of the messages pane", async () => {
      vi.useFakeTimers();
      const { result, container } = setupHook();
      Object.defineProperty(container, "scrollTop", {
        configurable: true,
        writable: true,
        value: 600,
      }); // close to (scrollHeight 1000 - clientHeight 500) - 100 = 400 → "not scrolled up"

      act(() => {
        result.current.appendStreamingTokenToChat("tok");
      });
      vi.runAllTimers();

      expect(container.scrollTo).toHaveBeenCalledWith({
        top: 1000,
        behavior: "smooth",
      });
      vi.useRealTimers();
    });

    it("skips auto-scroll when the user has scrolled up", async () => {
      vi.useFakeTimers();
      const { result, container } = setupHook();
      // scrollTop = 0 → isScrolledUp true
      Object.defineProperty(container, "scrollTop", {
        configurable: true,
        writable: true,
        value: 0,
      });

      act(() => {
        result.current.appendStreamingTokenToChat("tok");
      });
      vi.runAllTimers();

      expect(container.scrollTo).not.toHaveBeenCalled();
      vi.useRealTimers();
    });
  });

  describe("appendThoughtToMessage", () => {
    it("ignores frames without a messageId or text", () => {
      const { result, state } = setupHook();
      act(() => {
        result.current.appendThoughtToMessage("", { message_id: "m" });
        result.current.appendThoughtToMessage("text", undefined);
      });
      expect(state.chat).toHaveLength(0);
    });

    it("creates a new assistant placeholder when no matching message exists", () => {
      const { result, state } = setupHook();
      act(() => {
        result.current.appendThoughtToMessage("Thinking…", {
          message_id: "m-new",
        });
      });
      expect(state.chat).toHaveLength(1);
      expect(state.chat[0]).toMatchObject({
        messageId: "m-new",
        hasTimeline: true,
        isAssistant: true,
        isComplete: false,
      });
      expect(state.chat[0].timeline?.[0]).toMatchObject({
        type: "thought",
        text: "Thinking…",
      });
    });

    it("classifies tool_call vs tool_result based on args presence", () => {
      const { result, state } = setupHook({
        chat: [
          {
            messageId: "m-1",
            user: "Assistant",
            content: "",
            timestamp: "",
            isAssistant: true,
            timeline: [],
            hasTimeline: true,
          },
        ],
      });

      act(() => {
        result.current.appendThoughtToMessage("calling", {
          message_id: "m-1",
          tool_name: "search",
          args: { q: "x" },
        });
        result.current.appendThoughtToMessage("done", {
          message_id: "m-1",
          tool_name: "search",
        });
      });

      const tl = state.chat[0].timeline ?? [];
      expect(tl).toHaveLength(2);
      expect(tl[0]).toMatchObject({ type: "tool_call", tool: "search" });
      expect(tl[1]).toMatchObject({ type: "tool_result", tool: "search" });
    });

    it("emits a compaction timeline entry and updates compactionNotice state", () => {
      const { result, state } = setupHook();
      act(() => {
        result.current.appendThoughtToMessage("Compacted", {
          message_id: "m-c",
          compaction: {
            tokens_before: 2000,
            tokens_after: 500,
            context_window: 4000,
          },
        });
      });
      expect(state.chat[0].timeline?.[0].type).toBe("compaction");
      expect(state.compaction).toEqual({
        tokensBefore: 2000,
        tokensAfter: 500,
        contextWindow: 4000,
      });
    });
  });

  describe("handleCompleteMessage", () => {
    it("warns when called without an overrideId", () => {
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const { result } = setupHook();
      act(() => {
        result.current.handleCompleteMessage("content");
      });
      expect(warnSpy).toHaveBeenCalled();
      warnSpy.mockRestore();
    });

    it("inserts a new ChatSourceAtom message when none exists", () => {
      const { result, state } = setupHook();
      act(() => {
        result.current.handleCompleteMessage(
          "final content",
          undefined,
          "m-1",
          "2026-05-13T00:00:00Z"
        );
      });
      expect(state.chatSource.messages).toHaveLength(1);
      const m = state.chatSource.messages[0] as ChatMessage;
      expect(m.messageId).toBe("m-1");
      expect(m.content).toBe("final content");
      expect(m.timestamp).toBe("2026-05-13T00:00:00.000Z");
      expect(state.chatSource.selectedMessageId).toBeNull();
    });

    it("updates an existing ChatSourceAtom entry in place and preserves prior sources when none supplied", () => {
      const { result, state } = setupHook({
        chatSource: {
          messages: [
            {
              messageId: "m-1",
              content: "old",
              timestamp: "t0",
              sources: [
                {
                  id: "s",
                  page: 1,
                  label: "L",
                  label_id: 1,
                  annotation_id: 1,
                  rawText: "r",
                  tokensByPage: {},
                  boundsByPage: {},
                },
              ],
            } as ChatMessage,
          ],
          selectedMessageId: null,
          selectedSourceIndex: null,
        },
      });

      act(() => {
        result.current.handleCompleteMessage("new content", undefined, "m-1");
      });
      const m = state.chatSource.messages[0];
      expect(m.content).toBe("new content");
      expect(m.sources).toHaveLength(1);
      expect(m.sources[0].annotation_id).toBe(1);
    });
  });

  describe("finalizeStreamingResponse", () => {
    it("is a no-op when there are no chat messages", () => {
      const { result, state } = setupHook();
      act(() => {
        result.current.finalizeStreamingResponse("nope", undefined, undefined);
      });
      expect(state.chat).toHaveLength(0);
      expect(state.chatSource.messages).toHaveLength(0);
    });

    it("uses the overrideId match when provided", () => {
      const { result, state } = setupHook({
        chat: [
          {
            messageId: "first",
            user: "Assistant",
            content: "old",
            timestamp: "",
            isAssistant: true,
            isComplete: false,
          },
          {
            messageId: "target",
            user: "Assistant",
            content: "...",
            timestamp: "",
            isAssistant: true,
            isComplete: false,
          },
        ],
      });

      act(() => {
        result.current.finalizeStreamingResponse("final", undefined, "target");
      });

      expect(state.chat[1].content).toBe("final");
      expect(state.chat[1].isComplete).toBe(true);
      // ChatSourceAtom should have been written by the nested handleCompleteMessage call.
      expect(
        state.chatSource.messages.find((m) => m.messageId === "target")
      ).toBeTruthy();
    });

    it("falls back to the last assistant message when overrideId does not match", () => {
      const { result, state } = setupHook({
        chat: [
          {
            messageId: "u1",
            user: "U",
            content: "q",
            timestamp: "",
            isAssistant: false,
          },
          {
            messageId: "a1",
            user: "Assistant",
            content: "partial",
            timestamp: "",
            isAssistant: true,
            isComplete: false,
          },
        ],
      });

      act(() => {
        result.current.finalizeStreamingResponse(
          "final",
          undefined,
          "no-such-id"
        );
      });

      expect(state.chat[1].content).toBe("final");
      expect(state.chat[1].isComplete).toBe(true);
    });

    it("is a no-op when the chat has only user messages (no assistant to update)", () => {
      const { result, state } = setupHook({
        chat: [
          {
            messageId: "u1",
            user: "U",
            content: "q",
            timestamp: "",
            isAssistant: false,
          },
        ],
      });

      act(() => {
        result.current.finalizeStreamingResponse("final");
      });

      expect(state.chat[0].content).toBe("q");
      expect(state.chatSource.messages).toHaveLength(0);
    });
  });

  describe("mergeSourcesIntoMessage", () => {
    const sourceA: WebSocketSources = {
      page: 1,
      json: { start: 0, end: 5 },
      annotation_id: 1,
      label: "L",
      label_id: 1,
      rawText: "abc",
    };
    const sourceB: WebSocketSources = {
      page: 1,
      json: { start: 6, end: 10 },
      annotation_id: 2,
      label: "L",
      label_id: 1,
      rawText: "def",
    };

    it("is a no-op when sources are empty or overrideId is missing", () => {
      const { result, state } = setupHook();
      act(() => {
        result.current.mergeSourcesIntoMessage(undefined, "m-1");
        result.current.mergeSourcesIntoMessage([], "m-1");
        result.current.mergeSourcesIntoMessage([sourceA], undefined);
      });
      expect(state.chatSource.messages).toHaveLength(0);
    });

    it("inserts a placeholder ChatSourceAtom message when none matches", () => {
      const { result, state } = setupHook();
      act(() => {
        result.current.mergeSourcesIntoMessage([sourceA], "m-1");
      });
      expect(state.chatSource.messages).toHaveLength(1);
      expect(state.chatSource.messages[0].sources).toHaveLength(1);
      expect(state.chatSource.messages[0].sources[0].annotation_id).toBe(1);
    });

    it("de-duplicates by annotation_id when merging into an existing entry", () => {
      const { result, state } = setupHook({
        chatSource: {
          messages: [
            {
              messageId: "m-1",
              content: "",
              timestamp: "",
              sources: [
                {
                  id: "x",
                  page: 1,
                  label: "L",
                  label_id: 1,
                  annotation_id: 1,
                  rawText: "abc",
                  tokensByPage: {},
                  boundsByPage: {},
                },
              ],
            } as ChatMessage,
          ],
          selectedMessageId: null,
          selectedSourceIndex: null,
        },
        chat: [
          {
            messageId: "m-1",
            user: "Assistant",
            content: "",
            timestamp: "",
            isAssistant: true,
          },
        ],
      });

      act(() => {
        // include sourceA (already present) + sourceB (new)
        result.current.mergeSourcesIntoMessage([sourceA, sourceB], "m-1");
      });

      const msg = state.chatSource.messages.find((m) => m.messageId === "m-1");
      expect(msg?.sources).toHaveLength(2);
      const ids = msg!.sources.map((s) => s.annotation_id).sort();
      expect(ids).toEqual([1, 2]);
      // hasSources flag flipped on the chat entry
      expect(state.chat[0].hasSources).toBe(true);
    });

    it("leaves the chat array untouched when the chat side does not contain the messageId", () => {
      const { result, state } = setupHook();
      act(() => {
        result.current.mergeSourcesIntoMessage([sourceA], "m-other");
      });
      expect(state.chat).toHaveLength(0);
      expect(state.chatSource.messages).toHaveLength(1);
    });
  });
});
