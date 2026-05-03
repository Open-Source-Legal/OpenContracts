import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react-hooks";
import { authToken } from "../../graphql/cache";
import {
  WS_AUTH_SUBPROTOCOL,
  WS_CLOSE_PERMISSION_DENIED,
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
});
