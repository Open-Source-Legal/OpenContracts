/**
 * Vitest hook coverage for `useChatAgentMessageHandler`.
 *
 * Built to lift codecov patch coverage for the WebSocket message dispatcher
 * extracted in PR #1639. Exercises every branch of the 10+ ASYNC/SYNC switch
 * plus the approval-decision side-channel and the malformed-JSON guard.
 *
 * We feed `streamHandlers` as a bundle of `vi.fn()` mocks so we can assert
 * exactly which downstream handler each frame routes to, mirroring how
 * `ChatTray.tsx` wires `useChatStreamHandlers` into the dispatcher.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "../../../../../test-utils/renderHook";
import {
  useChatAgentMessageHandler,
  UseChatAgentMessageHandlerParams,
} from "../useChatAgentMessageHandler";
import type { UseChatStreamHandlersReturn } from "../useChatStreamHandlers";
import type { ChatMessageProps } from "../../../../widgets/chat/ChatMessage";
import type {
  CompactionNotice,
  ContextStatus,
  WebSocketSources,
} from "../../../../chat/types";
import type { PendingApproval } from "../../../../chat/types";

interface Harness {
  chat: ChatMessageProps[];
  serverMessages: ChatMessageProps[];
  pendingApproval: PendingApproval | null;
  showApprovalModal: boolean;
  wsError: string | null;
  contextStatus: ContextStatus | null;
  compaction: CompactionNotice | null;
}

function buildHarness(
  initial?: Partial<Harness & { pendingApproval: PendingApproval | null }>
) {
  const harness: Harness = {
    chat: [],
    serverMessages: [],
    pendingApproval: null,
    showApprovalModal: false,
    wsError: null,
    contextStatus: null,
    compaction: null,
    ...initial,
  };

  /**
   * Build a React.Dispatch<SetStateAction<T>>-shaped setter that writes through
   * to a single field on the harness. Centralises the function-vs-value branch
   * so each per-field setter stays a one-liner without a free-form `any`.
   */
  function makeSetter<K extends keyof Harness>(
    key: K
  ): React.Dispatch<React.SetStateAction<Harness[K]>> {
    return (updater) => {
      const prev = harness[key];
      const next =
        typeof updater === "function"
          ? (updater as (p: Harness[K]) => Harness[K])(prev)
          : updater;
      harness[key] = next;
    };
  }

  const setChat = makeSetter("chat");
  const setServerMessages = makeSetter("serverMessages");
  const setPendingApproval = makeSetter("pendingApproval");
  const setShowApprovalModal = makeSetter("showApprovalModal");
  const setWsError = makeSetter("wsError");
  const setContextStatus = makeSetter("contextStatus");
  const setCompactionNotice = makeSetter("compaction");

  const streamHandlers: UseChatStreamHandlersReturn = {
    updateMessageApprovalStatus: vi.fn(),
    appendStreamingTokenToChat: vi.fn().mockReturnValue("m-id"),
    appendThoughtToMessage: vi.fn(),
    mergeSourcesIntoMessage: vi.fn(),
    finalizeStreamingResponse: vi.fn(),
    handleCompleteMessage: vi.fn(),
  };

  // pendingApprovalRef must be readable as `.current` inside the dispatcher.
  // Stored as a mutable ref-shaped object so the test can override `.current`
  // without going through React state.
  const pendingApprovalRef: React.MutableRefObject<PendingApproval | null> = {
    current: harness.pendingApproval,
  };

  const params: UseChatAgentMessageHandlerParams = {
    pendingApprovalRef,
    setPendingApproval,
    setShowApprovalModal,
    setWsError,
    setChat,
    setServerMessages,
    setContextStatus,
    setCompactionNotice,
    streamHandlers,
  };

  // Allow the test to mutate the ref independently of the harness object.
  const updateRef = (next: PendingApproval | null) => {
    pendingApprovalRef.current = next;
    harness.pendingApproval = next;
  };

  return { harness, params, streamHandlers, pendingApprovalRef, updateRef };
}

function setupHook(initial?: Parameters<typeof buildHarness>[0]) {
  const h = buildHarness(initial);
  const { result } = renderHook(() => useChatAgentMessageHandler(h.params));
  return { ...h, result };
}

function deliver(handler: (e: MessageEvent) => void, payload: unknown) {
  // wrap in act so setState calls flush synchronously.
  act(() => handler({ data: JSON.stringify(payload) } as MessageEvent));
}

describe("useChatAgentMessageHandler", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });
  afterEach(() => vi.restoreAllMocks());

  it("logs and swallows malformed JSON payloads", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result } = setupHook();
    act(() => result.current({ data: "{ not valid json" } as MessageEvent));
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });

  it("ignores falsy parsed payloads (e.g. literal null)", () => {
    const { result, streamHandlers } = setupHook();
    deliver(result.current, null);
    expect(streamHandlers.appendStreamingTokenToChat).not.toHaveBeenCalled();
  });

  it("ASYNC_START → appendStreamingTokenToChat with message id", () => {
    const { result, streamHandlers } = setupHook();
    deliver(result.current, {
      type: "ASYNC_START",
      content: "Hello",
      data: { message_id: "m1" },
    });
    expect(streamHandlers.appendStreamingTokenToChat).toHaveBeenCalledWith(
      "Hello",
      "m1"
    );
  });

  it("ASYNC_CONTENT clears pendingApproval and stamps 'approved' when it matches", () => {
    const { result, streamHandlers, harness, updateRef } = setupHook();
    updateRef({ messageId: "m1", toolCall: { name: "t", arguments: {} } });

    deliver(result.current, {
      type: "ASYNC_CONTENT",
      content: " world",
      data: { message_id: "m1" },
    });

    expect(streamHandlers.appendStreamingTokenToChat).toHaveBeenCalledWith(
      " world",
      "m1"
    );
    expect(harness.pendingApproval).toBeNull();
    expect(streamHandlers.updateMessageApprovalStatus).toHaveBeenCalledWith(
      "m1",
      "approved"
    );
  });

  it("ASYNC_CONTENT does NOT touch approval state when ids differ", () => {
    const { result, streamHandlers, updateRef } = setupHook();
    updateRef({ messageId: "other", toolCall: { name: "t", arguments: {} } });

    deliver(result.current, {
      type: "ASYNC_CONTENT",
      content: "x",
      data: { message_id: "m1" },
    });

    // approval_decision side-channel is not set on this frame, so no call
    expect(streamHandlers.updateMessageApprovalStatus).not.toHaveBeenCalled();
  });

  it("approval_decision side-channel on any frame routes through updateMessageApprovalStatus", () => {
    const { result, streamHandlers } = setupHook();
    deliver(result.current, {
      type: "ASYNC_THOUGHT",
      content: "thinking",
      data: { message_id: "m1", approval_decision: "rejected" },
    });
    expect(streamHandlers.updateMessageApprovalStatus).toHaveBeenCalledWith(
      "m1",
      "rejected"
    );
  });

  it("ASYNC_THOUGHT → appendThoughtToMessage", () => {
    const { result, streamHandlers } = setupHook();
    deliver(result.current, {
      type: "ASYNC_THOUGHT",
      content: "reasoning",
      data: { message_id: "m1" },
    });
    expect(streamHandlers.appendThoughtToMessage).toHaveBeenCalledWith(
      "reasoning",
      { message_id: "m1" }
    );
  });

  it("ASYNC_SOURCES → mergeSourcesIntoMessage", () => {
    const { result, streamHandlers } = setupHook();
    const sources: WebSocketSources[] = [
      {
        page: 1,
        json: { start: 0, end: 4 },
        annotation_id: 1,
        label: "L",
        label_id: 1,
        rawText: "abcd",
      },
    ];
    deliver(result.current, {
      type: "ASYNC_SOURCES",
      content: "",
      data: { message_id: "m1", sources },
    });
    expect(streamHandlers.mergeSourcesIntoMessage).toHaveBeenCalledWith(
      sources,
      "m1"
    );
  });

  describe("ASYNC_APPROVAL_NEEDED", () => {
    it("opens modal, sets pendingApproval, and stamps 'awaiting' on chat + server arrays", () => {
      const { result, harness } = setupHook({
        chat: [
          {
            messageId: "m1",
            user: "Assistant",
            content: "",
            timestamp: "",
            isAssistant: true,
          },
        ],
        serverMessages: [
          {
            messageId: "m1",
            user: "Assistant",
            content: "",
            timestamp: "",
            isAssistant: true,
          },
        ],
      });
      const toolCall = {
        name: "dangerous_tool",
        arguments: { target: "x" },
        tool_call_id: "tc-1",
      };

      deliver(result.current, {
        type: "ASYNC_APPROVAL_NEEDED",
        content: "",
        data: { message_id: "m1", pending_tool_call: toolCall },
      });

      expect(harness.pendingApproval).toEqual({
        messageId: "m1",
        toolCall,
        // ``requesting_agent`` was not provided in the frame, so the
        // handler defaults the field to ``null`` (rich-mention
        // delegation contract — see useChatAgentMessageHandler.ts).
        requestingAgent: null,
      });
      expect(harness.showApprovalModal).toBe(true);
      expect(harness.chat[0].approvalStatus).toBe("awaiting");
      expect(harness.serverMessages[0].approvalStatus).toBe("awaiting");
    });

    it("is a no-op when pending_tool_call is missing", () => {
      const { result, harness } = setupHook();
      deliver(result.current, {
        type: "ASYNC_APPROVAL_NEEDED",
        content: "",
        data: { message_id: "m1" },
      });
      expect(harness.pendingApproval).toBeNull();
      expect(harness.showApprovalModal).toBe(false);
    });
  });

  describe("ASYNC_APPROVAL_RESULT", () => {
    it("clears approval state and stamps decision when ids match", () => {
      const { result, harness, streamHandlers, updateRef } = setupHook();
      updateRef({ messageId: "m1", toolCall: { name: "t", arguments: {} } });
      harness.showApprovalModal = true;

      deliver(result.current, {
        type: "ASYNC_APPROVAL_RESULT",
        content: "",
        data: { message_id: "m1", decision: "approved" },
      });

      expect(harness.pendingApproval).toBeNull();
      expect(harness.showApprovalModal).toBe(false);
      expect(streamHandlers.updateMessageApprovalStatus).toHaveBeenCalledWith(
        "m1",
        "approved"
      );
    });

    it("ignores ASYNC_APPROVAL_RESULT when ids do not match", () => {
      const { result, harness, updateRef } = setupHook();
      updateRef({ messageId: "other", toolCall: { name: "t", arguments: {} } });
      deliver(result.current, {
        type: "ASYNC_APPROVAL_RESULT",
        content: "",
        data: { message_id: "m1", decision: "approved" },
      });
      expect(harness.pendingApproval?.messageId).toBe("other");
    });
  });

  it("ASYNC_RESUME is a no-op (does not throw or call handlers)", () => {
    const { result, streamHandlers, harness } = setupHook();
    deliver(result.current, { type: "ASYNC_RESUME", content: "" });
    expect(streamHandlers.appendStreamingTokenToChat).not.toHaveBeenCalled();
    expect(harness.pendingApproval).toBeNull();
  });

  describe("ASYNC_FINISH", () => {
    it("finalizes, clears compactionNotice, persists contextStatus, and clears approval if ids match", () => {
      const { result, harness, streamHandlers, updateRef } = setupHook({
        compaction: {
          tokensBefore: 1,
          tokensAfter: 2,
          contextWindow: 3,
        },
      });
      updateRef({ messageId: "m1", toolCall: { name: "t", arguments: {} } });

      const ctx: ContextStatus = {
        used_tokens: 100,
        context_window: 1000,
        was_compacted: false,
        tokens_before_compaction: 0,
      };

      deliver(result.current, {
        type: "ASYNC_FINISH",
        content: "Done.",
        data: {
          message_id: "m1",
          sources: [],
          timeline: [],
          context_status: ctx,
          approval_decision: "approved",
        },
      });

      // finalizeStreamingResponse intentionally does NOT receive the
      // timeline array — ChatSourceAtom doesn't persist timelines, so
      // dropping the arg keeps the seam free of no-op parameters.
      expect(streamHandlers.finalizeStreamingResponse).toHaveBeenCalledWith(
        "Done.",
        [],
        "m1"
      );
      expect(harness.compaction).toBeNull();
      expect(harness.contextStatus).toEqual(ctx);
      expect(harness.pendingApproval).toBeNull();
      expect(streamHandlers.updateMessageApprovalStatus).toHaveBeenCalledWith(
        "m1",
        "approved"
      );
    });

    it("skips contextStatus / approval branches when those fields are missing", () => {
      const { result, harness, streamHandlers } = setupHook();
      deliver(result.current, {
        type: "ASYNC_FINISH",
        content: "Done",
        data: { message_id: "m1" },
      });
      expect(streamHandlers.finalizeStreamingResponse).toHaveBeenCalled();
      expect(harness.contextStatus).toBeNull();
      // No pending approval was set, so updateMessageApprovalStatus must not be called
      // from this branch (and approval_decision was absent).
      expect(streamHandlers.updateMessageApprovalStatus).not.toHaveBeenCalled();
    });
  });

  it("ASYNC_ERROR sets wsError and finalizes with the error as the assistant content", () => {
    const { result, harness, streamHandlers } = setupHook();
    deliver(result.current, {
      type: "ASYNC_ERROR",
      content: "",
      data: { error: "Boom", message_id: "m1" },
    });
    expect(harness.wsError).toBe("Boom");
    expect(streamHandlers.finalizeStreamingResponse).toHaveBeenCalledWith(
      "Boom",
      [],
      "m1"
    );
  });

  it("ASYNC_ERROR falls back to a default error string when none is provided", () => {
    const { result, harness, streamHandlers } = setupHook();
    deliver(result.current, {
      type: "ASYNC_ERROR",
      content: "",
      data: { message_id: "m1" },
    });
    expect(harness.wsError).toBe("Agent error");
    expect(streamHandlers.finalizeStreamingResponse).toHaveBeenCalledWith(
      "An unknown error occurred.",
      [],
      "m1"
    );
  });

  describe("SYNC_CONTENT", () => {
    it("appends a complete assistant message and routes through handleCompleteMessage with sources", () => {
      const { result, harness, streamHandlers } = setupHook();
      const sources: WebSocketSources[] = [
        {
          page: 1,
          json: { start: 0, end: 1 },
          annotation_id: 1,
          label: "L",
          label_id: 1,
          rawText: "a",
        },
      ];
      const timeline = [{ type: "thought" as const, text: "step" }];

      deliver(result.current, {
        type: "SYNC_CONTENT",
        content: "Instant reply",
        data: { message_id: "s1", sources, timeline },
      });

      expect(harness.chat).toHaveLength(1);
      expect(harness.chat[0]).toMatchObject({
        messageId: "s1",
        content: "Instant reply",
        isAssistant: true,
        isComplete: true,
      });
      // handleCompleteMessage intentionally does NOT receive timeline data —
      // ChatSourceAtom doesn't persist it; the chat array carries timelines
      // via the SYNC_CONTENT append above.
      expect(streamHandlers.handleCompleteMessage).toHaveBeenCalledWith(
        "Instant reply",
        sources,
        "s1"
      );
    });

    it("passes undefined when sources are not an array", () => {
      const { result, streamHandlers } = setupHook();
      deliver(result.current, {
        type: "SYNC_CONTENT",
        content: "hi",
        data: { message_id: "s2", sources: "nope", timeline: "nope" },
      });
      expect(streamHandlers.handleCompleteMessage).toHaveBeenCalledWith(
        "hi",
        undefined,
        "s2"
      );
    });

    it("generates a synthetic message id when none is provided", () => {
      const { result, harness } = setupHook();
      deliver(result.current, {
        type: "SYNC_CONTENT",
        content: "hi",
        data: {},
      });
      expect(harness.chat).toHaveLength(1);
      expect(harness.chat[0].messageId).toMatch(/^asst_/);
    });
  });

  it("warns on unknown message types without throwing", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result } = setupHook();
    deliver(result.current, { type: "NEVER_SENT", content: "" });
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });
});
