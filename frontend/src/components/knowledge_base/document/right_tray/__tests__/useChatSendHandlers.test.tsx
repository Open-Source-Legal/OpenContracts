/**
 * Vitest hook coverage for `useChatSendHandlers`.
 *
 * Built to lift codecov patch coverage for the new send-handler bundle
 * extracted in PR #1639. Exercises every branch in:
 *   - sendMessageOverSocket (empty / not-ready / locked / success / failure paths)
 *   - sendApprovalDecision (no-pending / success / failure / wsSend false)
 *   - sendTextImmediately (delegates to shared sendTextOverSocket)
 * Plus the debounce / 300 ms lock release.
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "../../../../../test-utils/renderHook";
import {
  useChatSendHandlers,
  UseChatSendHandlersParams,
} from "../useChatSendHandlers";
import type { ChatMessageProps } from "../../../../widgets/chat/ChatMessage";
import type { PendingApproval } from "../ApprovalOverlay";

interface Harness {
  chat: ChatMessageProps[];
  newMessage: string;
  wsError: string | null;
  showApprovalModal: boolean;
  pendingApproval: PendingApproval | null;
  approvalUpdates: Array<{ id: string; status: "approved" | "rejected" }>;
}

type MockWsSend = ReturnType<typeof vi.fn<(payload: string) => boolean>>;

function buildHarness(
  overrides?: Partial<Harness & { wsReady: boolean; wsSend: MockWsSend }>
) {
  const harness: Harness = {
    chat: [],
    newMessage: "",
    wsError: null,
    showApprovalModal: false,
    pendingApproval: null,
    approvalUpdates: [],
    ...overrides,
  };

  const setChat: UseChatSendHandlersParams["setChat"] = (updater) => {
    harness.chat =
      typeof updater === "function"
        ? (updater as (p: ChatMessageProps[]) => ChatMessageProps[])(
            harness.chat
          )
        : updater;
  };
  const setNewMessage: UseChatSendHandlersParams["setNewMessage"] = (
    updater
  ) => {
    harness.newMessage =
      typeof updater === "function"
        ? (updater as (p: string) => string)(harness.newMessage)
        : updater;
  };
  const setWsError: UseChatSendHandlersParams["setWsError"] = (updater) => {
    harness.wsError =
      typeof updater === "function"
        ? (updater as (p: string | null) => string | null)(harness.wsError)
        : updater;
  };
  const setShowApprovalModal: UseChatSendHandlersParams["setShowApprovalModal"] =
    (updater) => {
      harness.showApprovalModal =
        typeof updater === "function"
          ? (updater as (p: boolean) => boolean)(harness.showApprovalModal)
          : updater;
    };
  const setPendingApproval: UseChatSendHandlersParams["setPendingApproval"] = (
    updater
  ) => {
    harness.pendingApproval =
      typeof updater === "function"
        ? (updater as (p: PendingApproval | null) => PendingApproval | null)(
            harness.pendingApproval
          )
        : updater;
  };

  const sendingLockRef = { current: false };

  const wsSend: MockWsSend = overrides?.wsSend ?? vi.fn(() => true);

  const updateMessageApprovalStatus = vi.fn(
    (id: string, status: "approved" | "rejected") => {
      harness.approvalUpdates.push({ id, status });
    }
  );

  const params: UseChatSendHandlersParams = {
    wsSend,
    wsReady: overrides?.wsReady ?? true,
    userEmail: "tester@example.com",
    newMessage: harness.newMessage,
    pendingApproval: harness.pendingApproval,
    sendingLockRef,
    setChat,
    setNewMessage,
    setWsError,
    setShowApprovalModal,
    setPendingApproval,
    updateMessageApprovalStatus,
  };

  return {
    harness,
    params,
    sendingLockRef,
    wsSend,
    updateMessageApprovalStatus,
  };
}

function setupHook(opts?: Parameters<typeof buildHarness>[0]) {
  const h = buildHarness(opts);
  // Render the hook with `initialProps` so we can swap params on rerender to
  // simulate state-driven prop updates (e.g. `newMessage` changing).
  const { result, rerender } = renderHook(
    (p: UseChatSendHandlersParams) => useChatSendHandlers(p),
    { initialProps: h.params }
  );
  return { ...h, result, rerender };
}

describe("useChatSendHandlers — sendMessageOverSocket", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("no-ops when the trimmed message is empty", () => {
    const { result, wsSend, harness } = setupHook({ newMessage: "   " });
    act(() => result.current.sendMessageOverSocket());
    expect(wsSend).not.toHaveBeenCalled();
    expect(harness.chat).toHaveLength(0);
  });

  it("no-ops when wsReady is false (and warns to console)", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result, wsSend } = setupHook({
      newMessage: "hi",
      wsReady: false,
    });

    act(() => result.current.sendMessageOverSocket());

    expect(wsSend).not.toHaveBeenCalled();
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("no-ops when the sendingLock is already held", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result, wsSend, sendingLockRef } = setupHook({ newMessage: "hi" });
    sendingLockRef.current = true;

    act(() => result.current.sendMessageOverSocket());

    expect(wsSend).not.toHaveBeenCalled();
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("happy path: sends WS payload, appends user chat entry, clears input, releases lock after 300 ms", () => {
    vi.useFakeTimers();
    const { result, harness, wsSend, sendingLockRef } = setupHook({
      newMessage: "Hello there",
    });

    act(() => result.current.sendMessageOverSocket());

    expect(wsSend).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(wsSend.mock.calls[0][0]);
    expect(payload).toEqual({ query: "Hello there" });
    expect(harness.chat).toHaveLength(1);
    expect(harness.chat[0]).toMatchObject({
      user: "tester@example.com",
      content: "Hello there",
      isAssistant: false,
      isComplete: false,
    });
    expect(harness.newMessage).toBe("");
    expect(harness.wsError).toBeNull();

    // Lock is still held until 300 ms passes.
    expect(sendingLockRef.current).toBe(true);
    vi.advanceTimersByTime(300);
    expect(sendingLockRef.current).toBe(false);

    vi.useRealTimers();
  });

  it("sets wsError and skips chat append when wsSend returns false", () => {
    const wsSend = vi.fn(() => false);
    const { result, harness } = setupHook({ newMessage: "hi", wsSend });

    act(() => result.current.sendMessageOverSocket());

    expect(harness.wsError).toMatch(/Failed to send/i);
    expect(harness.chat).toHaveLength(0);
  });

  it("captures thrown errors and surfaces them via wsError", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const wsSend = vi.fn(() => {
      throw new Error("ws boom");
    });
    const { result, harness } = setupHook({ newMessage: "hi", wsSend });

    act(() => result.current.sendMessageOverSocket());

    expect(harness.wsError).toMatch(/Failed to send/i);
    expect(harness.chat).toHaveLength(0);
    errSpy.mockRestore();
  });

  it("uses the literal 'You' fallback when userEmail is empty", () => {
    const wsSend = vi.fn(() => true);
    const h = buildHarness({ newMessage: "hi", wsSend });
    h.params.userEmail = undefined;
    const { result } = renderHook(
      (p: UseChatSendHandlersParams) => useChatSendHandlers(p),
      {
        initialProps: h.params,
      }
    );
    act(() => result.current.sendMessageOverSocket());
    expect(h.harness.chat[0].user).toBe("You");
  });
});

describe("useChatSendHandlers — sendApprovalDecision", () => {
  it("warns and no-ops when there is no pending approval", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result, wsSend, updateMessageApprovalStatus } = setupHook();

    act(() => result.current.sendApprovalDecision(true));

    expect(wsSend).not.toHaveBeenCalled();
    expect(updateMessageApprovalStatus).not.toHaveBeenCalled();
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("warns and no-ops when wsReady is false", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result, wsSend } = setupHook({
      pendingApproval: {
        messageId: "m1",
        toolCall: { name: "t", arguments: {} },
      },
      wsReady: false,
    });
    act(() => result.current.sendApprovalDecision(true));
    expect(wsSend).not.toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("sends approval payload, calls updateMessageApprovalStatus with 'approved', and clears state", () => {
    const { result, wsSend, harness, updateMessageApprovalStatus } = setupHook({
      pendingApproval: {
        messageId: "m-approve",
        toolCall: { name: "t", arguments: {} },
      },
      showApprovalModal: true,
    });

    act(() => result.current.sendApprovalDecision(true));

    expect(wsSend).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(wsSend.mock.calls[0][0]);
    expect(payload).toEqual({
      approval_decision: true,
      llm_message_id: "m-approve",
    });
    expect(updateMessageApprovalStatus).toHaveBeenCalledWith(
      "m-approve",
      "approved"
    );
    expect(harness.showApprovalModal).toBe(false);
    expect(harness.pendingApproval).toBeNull();
    expect(harness.wsError).toBeNull();
  });

  it("passes 'rejected' through to updateMessageApprovalStatus when approved=false", () => {
    const { result, updateMessageApprovalStatus } = setupHook({
      pendingApproval: {
        messageId: "m-reject",
        toolCall: { name: "t", arguments: {} },
      },
    });
    act(() => result.current.sendApprovalDecision(false));
    expect(updateMessageApprovalStatus).toHaveBeenCalledWith(
      "m-reject",
      "rejected"
    );
  });

  it("re-opens the modal and sets wsError when wsSend returns false", () => {
    const wsSend = vi.fn(() => false);
    const { result, harness, updateMessageApprovalStatus } = setupHook({
      pendingApproval: {
        messageId: "m1",
        toolCall: { name: "t", arguments: {} },
      },
      wsSend,
    });

    act(() => result.current.sendApprovalDecision(true));

    expect(harness.wsError).toMatch(/Failed to send approval/i);
    expect(harness.showApprovalModal).toBe(true);
    expect(updateMessageApprovalStatus).not.toHaveBeenCalled();
  });

  it("captures thrown errors and re-opens the modal", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const wsSend = vi.fn(() => {
      throw new Error("boom");
    });
    const { result, harness } = setupHook({
      pendingApproval: {
        messageId: "m1",
        toolCall: { name: "t", arguments: {} },
      },
      wsSend,
    });
    act(() => result.current.sendApprovalDecision(true));
    expect(harness.wsError).toMatch(/Failed to send approval/i);
    expect(harness.showApprovalModal).toBe(true);
    errSpy.mockRestore();
  });
});

describe("useChatSendHandlers — sendTextImmediately", () => {
  it("forwards trimmed text through the shared send pipeline without touching `newMessage`", () => {
    // Seed a non-empty newMessage so the invariant "sendTextImmediately must
    // NOT clear newMessage" is a meaningful assertion (the default `""` would
    // make the equality check vacuous).
    const { result, harness, wsSend } = setupHook({
      newMessage: "draft typed by the user",
    });
    act(() => result.current.sendTextImmediately("  hello world  "));
    expect(wsSend).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(wsSend.mock.calls[0][0]);
    expect(payload).toEqual({ query: "hello world" });
    expect(harness.chat).toHaveLength(1);
    // sendTextImmediately must NOT clear `newMessage` (it bypasses the input).
    expect(harness.newMessage).toBe("draft typed by the user");
  });

  it("no-ops when text is empty after trim", () => {
    const { result, wsSend } = setupHook();
    act(() => result.current.sendTextImmediately("   "));
    expect(wsSend).not.toHaveBeenCalled();
  });
});
