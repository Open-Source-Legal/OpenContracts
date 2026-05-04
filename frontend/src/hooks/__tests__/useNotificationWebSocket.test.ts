/**
 * Behavioural coverage for useNotificationWebSocket. The companion file
 * `useNotificationWebSocket.auth.test.ts` is a no-token-in-URL regression
 * suite; this file covers the message-routing, heartbeat, sendPing, and
 * connection-state transitions that the regression suite skips.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act, cleanup } from "../../test-utils/renderHook";
import { authToken } from "../../graphql/cache";
import { useNotificationWebSocket } from "../useNotificationWebSocket";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  protocols: string | string[] | undefined;
  readyState = 0;
  onopen: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  sent: string[] = [];

  static OPEN = 1;
  static CLOSED = 3;

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols;
    MockWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close(code = 1000) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason: "", wasClean: true } as CloseEvent);
  }
  _open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({} as Event);
  }
  _serverSend(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  // @ts-expect-error - global override
  globalThis.WebSocket = MockWebSocket;
  // useNotificationWebSocket sets `requireAuth: true` on useWebSocketAuth,
  // which short-circuits the connect effect when authToken is empty.
  // Seed a non-empty token so the hook is allowed to open a socket; tests
  // that need to assert the no-token gate set `authToken("")` explicitly.
  authToken("test-token");
});
afterEach(() => {
  cleanup();
  authToken("");
});

describe("useNotificationWebSocket", () => {
  it("respects enabled=false (no socket opened)", () => {
    const { result } = renderHook(() =>
      useNotificationWebSocket({ enabled: false })
    );
    expect(MockWebSocket.instances.length).toBe(0);
    expect(result.current.connectionState).toBe("disconnected");
  });

  it("does not open a socket while authToken is empty (requireAuth gate)", () => {
    // Override the beforeEach seed to simulate the App-mount-before-login
    // window. Notifications are per-user; opening a token-less socket would
    // get rejected 4000 by the consumer and put the hook into terminal
    // auth-failure state for the rest of the session.
    authToken("");
    const { result, rerender } = renderHook(() => useNotificationWebSocket());
    expect(MockWebSocket.instances.length).toBe(0);
    expect(result.current.connectionState).toBe("disconnected");

    // Once the token lands, the connect effect should re-run and open.
    act(() => {
      authToken("late-arriving-token");
    });
    rerender();
    expect(MockWebSocket.instances.length).toBe(1);
  });

  it("opens a socket when enabled and reports connecting until AUTH_OK", () => {
    const { result } = renderHook(() => useNotificationWebSocket());
    expect(MockWebSocket.instances.length).toBe(1);
    act(() => MockWebSocket.instances[0]._open());
    expect(result.current.connectionState).toBe("connecting");
  });

  it("transitions to 'connected' once the auth handshake succeeds", () => {
    authToken("t");
    const { result } = renderHook(() => useNotificationWebSocket());
    act(() => {
      MockWebSocket.instances[0]._open();
      MockWebSocket.instances[0]._serverSend({
        type: "AUTH_OK",
        user_id: 1,
        anonymous: false,
        refreshed: false,
      });
    });
    expect(result.current.connectionState).toBe("connected");
  });

  it("captures sessionId from the CONNECTED frame", () => {
    const { result } = renderHook(() => useNotificationWebSocket());
    act(() => MockWebSocket.instances[0]._open());
    act(() =>
      MockWebSocket.instances[0]._serverSend({
        type: "CONNECTED",
        session_id: "sess-1",
      })
    );
    expect(result.current.sessionId).toBe("sess-1");
  });

  it("appends NOTIFICATION_CREATED frames to recentNotifications and fires callback", () => {
    const onCreated = vi.fn();
    const { result } = renderHook(() =>
      useNotificationWebSocket({ onNotificationCreated: onCreated })
    );
    act(() => MockWebSocket.instances[0]._open());
    act(() =>
      MockWebSocket.instances[0]._serverSend({
        type: "NOTIFICATION_CREATED",
        notificationId: "n-1",
        notificationType: "BADGE",
        createdAt: "2025-01-01T00:00:00Z",
        isRead: false,
        data: { badgeName: "First Reply" },
      })
    );
    expect(result.current.recentNotifications).toHaveLength(1);
    expect(result.current.recentNotifications[0]).toMatchObject({
      id: "n-1",
      notificationType: "BADGE",
      data: { badgeName: "First Reply" },
    });
    expect(onCreated).toHaveBeenCalledTimes(1);
  });

  it("ignores NOTIFICATION_CREATED frames missing required fields", () => {
    const onCreated = vi.fn();
    const { result } = renderHook(() =>
      useNotificationWebSocket({ onNotificationCreated: onCreated })
    );
    act(() => MockWebSocket.instances[0]._open());
    act(() =>
      MockWebSocket.instances[0]._serverSend({
        type: "NOTIFICATION_CREATED",
        // No notificationId / notificationType.
      })
    );
    expect(result.current.recentNotifications).toHaveLength(0);
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("forwards NOTIFICATION_UPDATED to onNotificationUpdated", () => {
    const onUpdated = vi.fn();
    renderHook(() =>
      useNotificationWebSocket({ onNotificationUpdated: onUpdated })
    );
    act(() => MockWebSocket.instances[0]._open());
    act(() =>
      MockWebSocket.instances[0]._serverSend({
        type: "NOTIFICATION_UPDATED",
        notificationId: "n-1",
        isRead: true,
      })
    );
    expect(onUpdated).toHaveBeenCalledWith("n-1", true);
  });

  it("forwards NOTIFICATION_DELETED to onNotificationDeleted", () => {
    const onDeleted = vi.fn();
    renderHook(() =>
      useNotificationWebSocket({ onNotificationDeleted: onDeleted })
    );
    act(() => MockWebSocket.instances[0]._open());
    act(() =>
      MockWebSocket.instances[0]._serverSend({
        type: "NOTIFICATION_DELETED",
        notificationId: "n-1",
      })
    );
    expect(onDeleted).toHaveBeenCalledWith("n-1");
  });

  it("ignores pong / heartbeat_ack frames silently", () => {
    const onCreated = vi.fn();
    renderHook(() =>
      useNotificationWebSocket({ onNotificationCreated: onCreated })
    );
    act(() => MockWebSocket.instances[0]._open());
    act(() => MockWebSocket.instances[0]._serverSend({ type: "pong" }));
    act(() =>
      MockWebSocket.instances[0]._serverSend({ type: "heartbeat_ack" })
    );
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("logs and recovers from malformed JSON frames", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      renderHook(() => useNotificationWebSocket());
      act(() => MockWebSocket.instances[0]._open());
      act(() => {
        MockWebSocket.instances[0].onmessage?.({
          data: "not-json",
        } as MessageEvent);
      });
      expect(errSpy).toHaveBeenCalled();
    } finally {
      errSpy.mockRestore();
    }
  });

  it("clearRecent empties recentNotifications", () => {
    const { result } = renderHook(() => useNotificationWebSocket());
    act(() => MockWebSocket.instances[0]._open());
    act(() =>
      MockWebSocket.instances[0]._serverSend({
        type: "NOTIFICATION_CREATED",
        notificationId: "n-1",
        notificationType: "BADGE",
      })
    );
    expect(result.current.recentNotifications).toHaveLength(1);
    act(() => {
      result.current.clearRecent();
    });
    expect(result.current.recentNotifications).toHaveLength(0);
  });

  it("sendPing pushes a ping frame onto the socket", () => {
    const { result } = renderHook(() => useNotificationWebSocket());
    act(() => MockWebSocket.instances[0]._open());
    act(() => {
      result.current.sendPing();
    });
    const ws = MockWebSocket.instances[0];
    expect(ws.sent.some((s) => JSON.parse(s).type === "ping")).toBe(true);
  });

  it("starts a heartbeat interval on open and clears it on close", () => {
    vi.useFakeTimers();
    try {
      renderHook(() => useNotificationWebSocket({ heartbeatInterval: 1000 }));
      act(() => MockWebSocket.instances[0]._open());
      const sentBefore = MockWebSocket.instances[0].sent.length;
      act(() => {
        vi.advanceTimersByTime(2500);
      });
      const sentAfter = MockWebSocket.instances[0].sent.length;
      expect(sentAfter - sentBefore).toBeGreaterThanOrEqual(2);
      // Now close. Subsequent ticks must not enqueue more frames.
      act(() => {
        MockWebSocket.instances[0].close();
      });
      const sentAfterClose = MockWebSocket.instances[0].sent.length;
      act(() => {
        vi.advanceTimersByTime(2500);
      });
      // After close the heartbeat interval is cleared. Note that in some
      // close-code branches the hook still triggers a reconnect, which
      // would create a new MockWebSocket whose ping frames count against
      // its own .sent[]. Asserting on the closed socket is the precise
      // statement we want.
      expect(MockWebSocket.instances[0].sent.length).toBe(sentAfterClose);
    } finally {
      vi.useRealTimers();
    }
  });

  it("reconnect() forces a new socket", () => {
    const { result } = renderHook(() => useNotificationWebSocket());
    expect(MockWebSocket.instances.length).toBe(1);
    act(() => {
      result.current.reconnect();
    });
    expect(MockWebSocket.instances.length).toBe(2);
  });

  it("transitions to disconnected after the socket closes", () => {
    const { result } = renderHook(() => useNotificationWebSocket());
    act(() => MockWebSocket.instances[0]._open());
    act(() => MockWebSocket.instances[0].close());
    expect(result.current.connectionState).toBe("disconnected");
    expect(result.current.sessionId).toBeNull();
  });
});
