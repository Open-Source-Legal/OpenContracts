import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act, cleanup } from "../../test-utils/renderHook";
import { authToken } from "../../graphql/cache";
import {
  WS_AUTH_SUBPROTOCOL,
  WS_CLOSE_PERMISSION_DENIED,
  WS_CLOSE_TOKEN_EXPIRED,
  WS_CLOSE_TOKEN_INVALID,
  WS_CLOSE_UNAUTHENTICATED,
} from "../../utils/websocketAuth";
import { useWebSocketAuth } from "../useWebSocketAuth";

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
  _serverSend(text: string) {
    this.onmessage?.({ data: text } as MessageEvent);
  }
  _serverClose(code: number) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code } as CloseEvent);
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  // @ts-expect-error - global override
  globalThis.WebSocket = MockWebSocket;
  authToken("");
});
afterEach(() => {
  // Unmount any hooks before resetting the reactive var so their
  // `useReactiveVar` listeners can't fire setState on a torn-down tree.
  cleanup();
  authToken("");
});

describe("useWebSocketAuth", () => {
  it("connects with [marker, token] when token present", () => {
    authToken("token-1");
    renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    const ws = MockWebSocket.instances[0];
    expect(ws.protocols).toEqual([WS_AUTH_SUBPROTOCOL, "token-1"]);
  });

  it("connects with [marker] only when token absent", () => {
    authToken("");
    renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    const ws = MockWebSocket.instances[0];
    expect(ws.protocols).toEqual([WS_AUTH_SUBPROTOCOL]);
  });

  it("becomes isConnected on open", () => {
    const { result } = renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() => MockWebSocket.instances[0]._open());
    expect(result.current.isConnected).toBe(true);
  });

  it("becomes isAuthenticated on AUTH_OK", () => {
    authToken("t");
    const { result } = renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() => {
      MockWebSocket.instances[0]._open();
      MockWebSocket.instances[0]._serverSend(
        JSON.stringify({
          type: "AUTH_OK",
          user_id: 1,
          anonymous: false,
          refreshed: false,
        })
      );
    });
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("sends AUTH frame on token change without reconnect", () => {
    authToken("t1");
    renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() => MockWebSocket.instances[0]._open());

    act(() => {
      authToken("t2");
    });
    const ws = MockWebSocket.instances[0];
    expect(MockWebSocket.instances.length).toBe(1);
    const lastSent = JSON.parse(ws.sent[ws.sent.length - 1]);
    expect(lastSent).toEqual({ type: "AUTH", token: "t2" });
  });

  it("answers AUTH_REFRESH_REQUIRED with current token", () => {
    authToken("current");
    renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() => MockWebSocket.instances[0]._open());

    act(() =>
      MockWebSocket.instances[0]._serverSend(
        JSON.stringify({ type: "AUTH_REFRESH_REQUIRED", grace_seconds: 30 })
      )
    );
    const ws = MockWebSocket.instances[0];
    const lastSent = JSON.parse(ws.sent[ws.sent.length - 1]);
    expect(lastSent).toEqual({ type: "AUTH", token: "current" });
  });

  it("does not auto-reconnect on close 4003 (PERMISSION_DENIED)", () => {
    authToken("t");
    renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() =>
      MockWebSocket.instances[0]._serverClose(WS_CLOSE_PERMISSION_DENIED)
    );
    expect(MockWebSocket.instances.length).toBe(1);
  });

  it("does not auto-reconnect on close 1000 (normal)", () => {
    authToken("t");
    renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() => MockWebSocket.instances[0]._serverClose(1000));
    expect(MockWebSocket.instances.length).toBe(1);
  });

  // Auth-failure family: reconnecting would just be rejected the same way,
  // so the hook must surface the failure once and stop spawning new sockets.
  for (const [label, code] of [
    ["4000 (UNAUTHENTICATED)", WS_CLOSE_UNAUTHENTICATED],
    ["4001 (TOKEN_EXPIRED)", WS_CLOSE_TOKEN_EXPIRED],
    ["4002 (TOKEN_INVALID)", WS_CLOSE_TOKEN_INVALID],
  ] as const) {
    it(`fires onAuthInvalid and does not reconnect on close ${label}`, () => {
      authToken("t");
      const onAuthInvalid = vi.fn();
      renderHook(() => useWebSocketAuth({ url: "ws://x/", onAuthInvalid }));
      act(() => MockWebSocket.instances[0]._serverClose(code));
      expect(onAuthInvalid).toHaveBeenCalledTimes(1);
      expect(MockWebSocket.instances.length).toBe(1);
    });
  }

  it("does not open a socket when enabled=false", () => {
    authToken("t");
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useWebSocketAuth({ url: "ws://x/", enabled }),
      { enabled: false }
    );
    expect(MockWebSocket.instances.length).toBe(0);
    expect(result.current.isConnected).toBe(false);
    expect(result.current.isAuthenticated).toBe(false);
    rerender({ enabled: true });
    expect(MockWebSocket.instances.length).toBe(1);
  });

  it("send() returns false when socket is not OPEN, true when it is", () => {
    authToken("t");
    const { result } = renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    expect(result.current.send("payload-pre-open")).toBe(false);
    act(() => MockWebSocket.instances[0]._open());
    expect(result.current.send("payload-after-open")).toBe(true);
    expect(MockWebSocket.instances[0].sent).toContain("payload-after-open");
  });

  it("AUTH_FAILED frame clears isAuthenticated and surfaces lastError", () => {
    authToken("t");
    const { result } = renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() => {
      MockWebSocket.instances[0]._open();
      MockWebSocket.instances[0]._serverSend(
        JSON.stringify({ type: "AUTH_OK", user_id: 1, anonymous: false })
      );
    });
    expect(result.current.isAuthenticated).toBe(true);
    act(() =>
      MockWebSocket.instances[0]._serverSend(
        JSON.stringify({ type: "AUTH_FAILED", reason: "PERMISSION_REVOKED" })
      )
    );
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.lastError).toBe("AUTH_FAILED: PERMISSION_REVOKED");
  });

  it("ws.onerror sets a transport-error message", () => {
    authToken("t");
    const { result } = renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() => {
      MockWebSocket.instances[0].onerror?.({} as Event);
    });
    expect(result.current.lastError).toBe("WebSocket transport error");
  });

  it("forwards non-auth frames to the onMessage callback", () => {
    authToken("t");
    const onMessage = vi.fn();
    renderHook(() => useWebSocketAuth({ url: "ws://x/", onMessage }));
    act(() => MockWebSocket.instances[0]._open());
    act(() =>
      MockWebSocket.instances[0]._serverSend(
        JSON.stringify({ type: "ASYNC_CONTENT", payload: "hello" })
      )
    );
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage.mock.calls[0][0].data).toContain("ASYNC_CONTENT");
  });

  it("does not echo AUTH frames back as onMessage", () => {
    authToken("t");
    const onMessage = vi.fn();
    renderHook(() => useWebSocketAuth({ url: "ws://x/", onMessage }));
    act(() => MockWebSocket.instances[0]._open());
    act(() =>
      MockWebSocket.instances[0]._serverSend(
        JSON.stringify({ type: "AUTH_OK", user_id: 1, anonymous: false })
      )
    );
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("auto-reconnects with exponential backoff on non-auth close", () => {
    vi.useFakeTimers();
    try {
      authToken("t");
      renderHook(() =>
        useWebSocketAuth({ url: "ws://x/", reconnectDelayMs: 100 })
      );
      // First non-auth close (e.g. 1006 abnormal closure) → reconnect after 100ms.
      act(() => MockWebSocket.instances[0]._serverClose(1006));
      expect(MockWebSocket.instances.length).toBe(1);
      act(() => {
        vi.advanceTimersByTime(100);
      });
      expect(MockWebSocket.instances.length).toBe(2);
      // Second close → failureCount=2, delay = 100 * 2^1 = 200ms.
      act(() => MockWebSocket.instances[1]._serverClose(1006));
      act(() => {
        vi.advanceTimersByTime(199);
      });
      expect(MockWebSocket.instances.length).toBe(2);
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(MockWebSocket.instances.length).toBe(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("uses 4x base delay on close 4029 (RATE_LIMITED)", () => {
    vi.useFakeTimers();
    try {
      authToken("t");
      renderHook(() =>
        useWebSocketAuth({ url: "ws://x/", reconnectDelayMs: 50 })
      );
      act(() => MockWebSocket.instances[0]._serverClose(4029));
      // 4x base = 200ms; 199ms must not have spawned yet.
      act(() => {
        vi.advanceTimersByTime(199);
      });
      expect(MockWebSocket.instances.length).toBe(1);
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(MockWebSocket.instances.length).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("reconnect() forces a new socket without changing reconnect counters", () => {
    authToken("t");
    const { result } = renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    expect(MockWebSocket.instances.length).toBe(1);
    act(() => {
      result.current.reconnect();
    });
    expect(MockWebSocket.instances.length).toBe(2);
  });

  it("does not send AUTH frame when token is empty", () => {
    authToken("t1");
    renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    act(() => MockWebSocket.instances[0]._open());
    const sentBefore = MockWebSocket.instances[0].sent.length;
    act(() => {
      authToken("");
    });
    // No AUTH frame should be queued for an empty token.
    expect(MockWebSocket.instances[0].sent.length).toBe(sentBefore);
  });

  it("closes the socket on unmount with code 1000", () => {
    authToken("t");
    const { unmount } = renderHook(() => useWebSocketAuth({ url: "ws://x/" }));
    const closeSpy = vi.spyOn(MockWebSocket.instances[0], "close");
    unmount();
    expect(closeSpy).toHaveBeenCalledWith(1000, "hook unmount");
  });
});
