/**
 * Integration tests for useAgentChat hook.
 *
 * These tests exercise the hook's full lifecycle through a mock WebSocket,
 * covering the previously-untested message handlers, action callbacks,
 * approval flow, and streaming reconciliation.
 *
 * Related to issue #1286 (coverage remediation).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react-hooks";
import React from "react";
import { Provider as JotaiProvider, createStore } from "jotai";
import { useAgentChat, AgentMessageData } from "../useAgentChat";
import { authToken, userObj } from "../../graphql/cache";

// ============================================================================
// Mock WebSocket
// ============================================================================

const OPEN = 1;
const CLOSED = 3;

interface MockWebSocketInstance {
  url: string;
  readyState: number;
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  send: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
  // Test helpers
  _deliver: (data: AgentMessageData | string) => void;
  _open: () => void;
  _fail: () => void;
  _serverClose: (code: number) => void;
}

let wsInstances: MockWebSocketInstance[] = [];

class MockWebSocket implements MockWebSocketInstance {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  readyState: number = 0;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = CLOSED;
    if (this.onclose) this.onclose({} as CloseEvent);
  });

  constructor(url: string) {
    this.url = url;
    wsInstances.push(this);
  }

  _open() {
    this.readyState = OPEN;
    if (this.onopen) this.onopen({} as Event);
  }

  _fail() {
    if (this.onerror) this.onerror({} as Event);
  }

  _serverClose(code: number) {
    this.readyState = CLOSED;
    if (this.onclose) this.onclose({ code } as CloseEvent);
  }

  _deliver(data: AgentMessageData | string) {
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    if (this.onmessage) {
      this.onmessage({ data: payload } as MessageEvent);
    }
  }
}

function latestSocket(): MockWebSocketInstance {
  const s = wsInstances[wsInstances.length - 1];
  if (!s) throw new Error("No WebSocket instance created");
  return s;
}

// ============================================================================
// Wrapper
// ============================================================================

function createWrapper() {
  const store = createStore();
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <JotaiProvider store={store}>{children}</JotaiProvider>;
  };
}

// ============================================================================
// Tests
// ============================================================================

describe("useAgentChat", () => {
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    wsInstances = [];
    originalWebSocket = globalThis.WebSocket;
    // @ts-expect-error - injecting mock
    globalThis.WebSocket = MockWebSocket;
    authToken("test-token");
    userObj({ email: "tester@example.com" } as any);
  });

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket;
    authToken(null as any);
    userObj(null as any);
    vi.restoreAllMocks();
  });

  describe("connection lifecycle", () => {
    it("does not open a socket without any context", () => {
      const { result } = renderHook(() => useAgentChat({ context: {} }), {
        wrapper: createWrapper(),
      });

      expect(wsInstances).toHaveLength(0);
      expect(result.current.isConnected).toBe(false);
    });

    it("opens a socket when context is provided and sets isConnected on open", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );

      expect(wsInstances).toHaveLength(1);
      expect(latestSocket().url).toContain("corpus_id=c-1");
      // PR #1502: token must NOT be in URL — auth happens via Sec-WebSocket-Protocol
      expect(latestSocket().url).not.toContain("token=");
      expect(result.current.isConnected).toBe(false);

      act(() => latestSocket()._open());

      expect(result.current.isConnected).toBe(true);
      expect(result.current.error).toBeNull();
    });

    it("surfaces auth-failure close codes via the consumer error state", () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const { result } = renderHook(
        () => useAgentChat({ context: { documentId: "d-1" } }),
        { wrapper: createWrapper() }
      );

      // Backend rejected the token (close 4002 → onAuthInvalid in the hook)
      act(() => latestSocket()._serverClose(4002));

      expect(result.current.isConnected).toBe(false);
      expect(result.current.error).toMatch(/Authentication failed/i);
      errorSpy.mockRestore();
    });

    it("closes the socket on unmount", () => {
      const { unmount } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      const socket = latestSocket();
      act(() => socket._open());

      unmount();

      expect(socket.close).toHaveBeenCalled();
    });
  });

  describe("streaming message handling", () => {
    it("handles ASYNC_START followed by ASYNC_CONTENT and ASYNC_FINISH", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_START",
          content: "Hello",
          data: { message_id: "m-1" },
        })
      );
      expect(result.current.isProcessing).toBe(true);
      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].content).toBe("Hello");
      expect(result.current.messages[0].messageId).toBe("m-1");
      expect(result.current.messages[0].isComplete).toBe(false);

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_CONTENT",
          content: " world",
          data: { message_id: "m-1" },
        })
      );
      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].content).toBe("Hello world");

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_FINISH",
          content: "Hello world.",
          data: {
            message_id: "m-1",
            context_status: {
              used_tokens: 100,
              context_window: 1000,
              was_compacted: false,
              tokens_before_compaction: 0,
            },
          },
        })
      );
      expect(result.current.isProcessing).toBe(false);
      expect(result.current.messages[0].content).toBe("Hello world.");
      expect(result.current.messages[0].isComplete).toBe(true);
      expect(result.current.contextStatus?.used_tokens).toBe(100);
    });

    it("handles SYNC_CONTENT as a single complete message", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "SYNC_CONTENT",
          content: "Instant reply",
          data: { message_id: "sync-1" },
        })
      );

      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].content).toBe("Instant reply");
      expect(result.current.messages[0].isComplete).toBe(true);
      expect(result.current.messages[0].messageId).toBe("sync-1");
    });

    it("appends timeline entries from ASYNC_THOUGHT", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_THOUGHT",
          content: "Thinking...",
          data: { message_id: "m-2" },
        })
      );
      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_THOUGHT",
          content: "Calling tool",
          data: {
            message_id: "m-2",
            tool_name: "search",
            args: { q: "hello" },
          },
        })
      );
      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_THOUGHT",
          content: "Tool result",
          data: { message_id: "m-2", tool_name: "search" },
        })
      );

      const msg = result.current.messages.find((m) => m.messageId === "m-2");
      expect(msg?.hasTimeline).toBe(true);
      expect(msg?.timeline).toHaveLength(3);
      expect(msg?.timeline?.[0].type).toBe("thought");
      expect(msg?.timeline?.[1].type).toBe("tool_call");
      expect(msg?.timeline?.[1].tool).toBe("search");
      expect(msg?.timeline?.[2].type).toBe("tool_result");
    });

    it("marks message as having sources when ASYNC_SOURCES arrives", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_START",
          content: "Thinking",
          data: { message_id: "m-src" },
        })
      );
      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_SOURCES",
          content: "",
          data: {
            message_id: "m-src",
            sources: [
              {
                page: 1,
                json: { start: 0, end: 10 },
                annotation_id: 99,
                label: "Label",
                label_id: 1,
                rawText: "text",
              },
            ],
          },
        })
      );

      const msg = result.current.messages.find((m) => m.messageId === "m-src");
      expect(msg?.hasSources).toBe(true);
    });

    it("ignores malformed JSON payloads without throwing", () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() => latestSocket()._deliver("{not valid json"));

      expect(result.current.messages).toHaveLength(0);
      expect(errorSpy).toHaveBeenCalled();
      errorSpy.mockRestore();
    });

    it("sets error and clears processing on ASYNC_ERROR", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_START",
          content: "Working",
          data: { message_id: "m-e" },
        })
      );
      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_ERROR",
          content: "",
          data: { error: "Something exploded", message_id: "m-e" },
        })
      );

      expect(result.current.error).toBe("Something exploded");
      expect(result.current.isProcessing).toBe(false);
      const msg = result.current.messages.find((m) => m.messageId === "m-e");
      expect(msg?.content).toBe("Something exploded");
      expect(msg?.isComplete).toBe(true);
    });

    it("warns on unknown message types without throwing", () => {
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      renderHook(() => useAgentChat({ context: { corpusId: "c-1" } }), {
        wrapper: createWrapper(),
      });
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          // @ts-expect-error - intentional unknown type
          type: "NEVER_SENT",
          content: "",
        })
      );

      expect(warnSpy).toHaveBeenCalled();
      warnSpy.mockRestore();
    });
  });

  describe("approval flow", () => {
    it("opens approval modal on ASYNC_APPROVAL_NEEDED and clears on ASYNC_APPROVAL_RESULT", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_START",
          content: "Working",
          data: { message_id: "m-a" },
        })
      );
      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_APPROVAL_NEEDED",
          content: "",
          data: {
            message_id: "m-a",
            pending_tool_call: {
              name: "dangerous_tool",
              arguments: { target: "x" },
              tool_call_id: "tc-1",
            },
          },
        })
      );

      expect(result.current.showApprovalModal).toBe(true);
      expect(result.current.pendingApproval?.messageId).toBe("m-a");
      expect(result.current.pendingApproval?.toolCall.name).toBe(
        "dangerous_tool"
      );
      const waiting = result.current.messages.find(
        (m) => m.messageId === "m-a"
      );
      expect(waiting?.approvalStatus).toBe("awaiting");

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_APPROVAL_RESULT",
          content: "",
          data: { message_id: "m-a", decision: "approved" },
        })
      );

      expect(result.current.pendingApproval).toBeNull();
      expect(result.current.showApprovalModal).toBe(false);
      const done = result.current.messages.find((m) => m.messageId === "m-a");
      expect(done?.approvalStatus).toBe("approved");
    });

    it("keeps processing true on ASYNC_RESUME", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_RESUME",
          content: "",
        })
      );

      expect(result.current.isProcessing).toBe(true);
    });

    it("sendApprovalDecision sends payload and updates message status", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_START",
          content: "Working",
          data: { message_id: "m-a2" },
        })
      );
      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_APPROVAL_NEEDED",
          content: "",
          data: {
            message_id: "m-a2",
            pending_tool_call: { name: "tool", arguments: {} },
          },
        })
      );

      const decisionSocket = latestSocket();

      act(() => result.current.sendApprovalDecision(true));

      const sent = decisionSocket.send.mock.calls[0]?.[0];
      expect(sent).toBeDefined();
      const parsed = JSON.parse(sent as string);
      expect(parsed.approval_decision).toBe(true);
      expect(parsed.llm_message_id).toBe("m-a2");
      expect(result.current.pendingApproval).toBeNull();
      expect(result.current.showApprovalModal).toBe(false);
      const msg = result.current.messages.find((m) => m.messageId === "m-a2");
      expect(msg?.approvalStatus).toBe("approved");
    });

    it("does not reconnect the socket when approval state changes (issue #1296)", () => {
      // Regression guard for issue #1296: prior to the fix, `pendingApproval`
      // was in the main effect's dependency array, so entering/exiting an
      // approval gate tore down the socket and created a new one mid-stream.
      // The handlers now read `pendingApproval` via a ref, so the socket must
      // stay open across approval-state transitions.
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());
      const originalSocket = latestSocket();
      const socketsBefore = wsInstances.length;

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_APPROVAL_NEEDED",
          content: "",
          data: {
            message_id: "m-b",
            pending_tool_call: { name: "tool", arguments: {} },
          },
        })
      );

      // No new socket was created and the original one was not closed.
      expect(wsInstances.length).toBe(socketsBefore);
      expect(originalSocket.close).not.toHaveBeenCalled();
      expect(result.current.isConnected).toBe(true);

      // Sending the approval decision dispatches through the same socket.
      act(() => result.current.sendApprovalDecision(true));
      expect(originalSocket.send).toHaveBeenCalledTimes(1);

      // Clearing the approval state (inside sendApprovalDecision) also must
      // not trigger a reconnect.
      expect(wsInstances.length).toBe(socketsBefore);
      expect(originalSocket.close).not.toHaveBeenCalled();
    });

    it("sendApprovalDecision no-ops without pending approval", () => {
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() => result.current.sendApprovalDecision(true));

      expect(latestSocket().send).not.toHaveBeenCalled();
      expect(warnSpy).toHaveBeenCalled();
      warnSpy.mockRestore();
    });
  });

  describe("sendMessage action", () => {
    it("appends a user message and writes to the socket", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() => result.current.sendMessage("hello there"));

      expect(result.current.messages).toHaveLength(1);
      const user = result.current.messages[0];
      expect(user.isAssistant).toBe(false);
      expect(user.content).toBe("hello there");
      expect(user.user).toBe("tester@example.com");

      const payload = JSON.parse(latestSocket().send.mock.calls[0][0]);
      expect(payload.query).toBe("hello there");
    });

    it("ignores empty or whitespace-only messages", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() => result.current.sendMessage("   "));
      act(() => result.current.sendMessage(""));

      expect(result.current.messages).toHaveLength(0);
      expect(latestSocket().send).not.toHaveBeenCalled();
    });

    it("does not send while disconnected", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      // no _open() call – still disconnected

      act(() => result.current.sendMessage("hello"));

      expect(latestSocket().send).not.toHaveBeenCalled();
      expect(result.current.messages).toHaveLength(0);
    });

    it("does not send while processing", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());

      act(() =>
        latestSocket()._deliver({
          type: "ASYNC_START",
          content: "",
          data: { message_id: "busy" },
        })
      );
      expect(result.current.isProcessing).toBe(true);

      act(() => result.current.sendMessage("should be blocked"));

      expect(latestSocket().send).not.toHaveBeenCalled();
    });

    it("reports send errors via the error state", () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      act(() => latestSocket()._open());
      latestSocket().send.mockImplementation(() => {
        throw new Error("socket boom");
      });

      act(() => result.current.sendMessage("hello"));

      expect(result.current.error).toMatch(/Failed to send message/i);
      errorSpy.mockRestore();
    });
  });

  describe("error and selection actions", () => {
    it("clearError wipes a prior error", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );
      // Trigger consumer-visible error via auth-failure close (4002)
      act(() => latestSocket()._serverClose(4002));
      expect(result.current.error).not.toBeNull();

      act(() => result.current.clearError());

      expect(result.current.error).toBeNull();
    });

    it("setSelectedMessageId updates the chat source state", () => {
      const { result } = renderHook(
        () => useAgentChat({ context: { corpusId: "c-1" } }),
        { wrapper: createWrapper() }
      );

      act(() => result.current.setSelectedMessageId("sel-1"));

      expect(result.current.selectedMessageId).toBe("sel-1");

      act(() => result.current.setSelectedMessageId(null));

      expect(result.current.selectedMessageId).toBeNull();
    });
  });
});
