/**
 * Coverage tests for get_websockets URL builders. The shared no-token-in-URL
 * regression suite lives in
 * `src/hooks/__tests__/useNotificationWebSocket.auth.test.ts`; this file
 * exercises the env-var resolution branches and protocol normalisation that
 * the regression suite skips.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

const RELOAD = async () => {
  vi.resetModules();
  return import("../get_websockets");
};

describe("get_websockets — env var resolution + base URL normalisation", () => {
  let originalProcessEnv: NodeJS.ProcessEnv;

  beforeEach(() => {
    originalProcessEnv = { ...process.env };
    delete process.env.VITE_WS_URL;
    delete process.env.REACT_APP_WS_URL;
    delete process.env.VITE_API_URL;
    delete process.env.REACT_APP_API_URL;
  });

  afterEach(() => {
    process.env = originalProcessEnv;
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("uses window.location protocol/host fallback (https → wss)", async () => {
    vi.stubGlobal("window", {
      location: { protocol: "https:", host: "example.com" },
    });
    vi.stubGlobal("import.meta", { env: {} });
    const { getNotificationUpdatesWebSocket } = await RELOAD();
    expect(getNotificationUpdatesWebSocket()).toBe(
      "wss://example.com/ws/notification-updates/"
    );
  });

  it("uses ws:// for non-https locations", async () => {
    vi.stubGlobal("window", {
      location: { protocol: "http:", host: "localhost:3000" },
    });
    vi.stubGlobal("import.meta", { env: {} });
    const { getThreadUpdatesWebSocket } = await RELOAD();
    expect(getThreadUpdatesWebSocket("Q29udjox")).toBe(
      "ws://localhost:3000/ws/thread-updates/?conversation_id=Q29udjox"
    );
  });

  it("prefers VITE_WS_URL over location and strips trailing slashes", async () => {
    vi.stubGlobal("window", {
      location: { protocol: "https:", host: "ignored.example" },
    });
    vi.stubGlobal("import.meta", { env: {} });
    process.env.VITE_WS_URL = "wss://api.example//";
    const { getNotificationUpdatesWebSocket } = await RELOAD();
    expect(getNotificationUpdatesWebSocket()).toBe(
      "wss://api.example/ws/notification-updates/"
    );
  });

  it("converts http(s):// → ws(s):// when env var carries http base", async () => {
    vi.stubGlobal("window", {
      location: { protocol: "https:", host: "ignored.example" },
    });
    vi.stubGlobal("import.meta", { env: {} });
    process.env.VITE_API_URL = "https://api.example";
    const { getNotificationUpdatesWebSocket } = await RELOAD();
    expect(getNotificationUpdatesWebSocket()).toBe(
      "wss://api.example/ws/notification-updates/"
    );
  });

  it("falls back to process.env when import.meta.env is empty", async () => {
    vi.stubGlobal("window", {
      location: { protocol: "https:", host: "ignored.example" },
    });
    vi.stubGlobal("import.meta", { env: {} });
    process.env.REACT_APP_WS_URL = "ws://process-env-host";
    const { getNotificationUpdatesWebSocket } = await RELOAD();
    expect(getNotificationUpdatesWebSocket()).toBe(
      "ws://process-env-host/ws/notification-updates/"
    );
  });

  it("getUnifiedAgentWebSocket emits no query string when no context fields", async () => {
    vi.stubGlobal("window", {
      location: { protocol: "https:", host: "example.com" },
    });
    vi.stubGlobal("import.meta", { env: {} });
    const { getUnifiedAgentWebSocket } = await RELOAD();
    const url = getUnifiedAgentWebSocket({});
    expect(url).toBe("wss://example.com/ws/agent-chat/");
  });

  it("getUnifiedAgentWebSocket includes all four context fields when provided", async () => {
    vi.stubGlobal("window", {
      location: { protocol: "https:", host: "example.com" },
    });
    vi.stubGlobal("import.meta", { env: {} });
    const { getUnifiedAgentWebSocket } = await RELOAD();
    const url = getUnifiedAgentWebSocket({
      corpusId: "c",
      documentId: "d",
      agentId: "a",
      conversationId: "v",
    });
    expect(url).toContain("corpus_id=c");
    expect(url).toContain("document_id=d");
    expect(url).toContain("agent_id=a");
    expect(url).toContain("conversation_id=v");
    expect(url).not.toContain("token");
  });
});

describe("get_websockets — getWebSocketUrl wrapper (document utils)", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { protocol: "https:", host: "example.com" },
    });
    vi.stubGlobal("import.meta", { env: {} });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("delegates to getUnifiedAgentWebSocket without ever including a token", async () => {
    vi.resetModules();
    const { getWebSocketUrl } = await import(
      "../../knowledge_base/document/utils"
    );
    const url = getWebSocketUrl("doc-1", "conv-1", "corpus-1");
    expect(url).toContain("document_id=doc-1");
    expect(url).toContain("conversation_id=conv-1");
    expect(url).toContain("corpus_id=corpus-1");
    expect(url).not.toContain("token");
  });

  it("works with only required documentId", async () => {
    vi.resetModules();
    const { getWebSocketUrl } = await import(
      "../../knowledge_base/document/utils"
    );
    const url = getWebSocketUrl("doc-only");
    expect(url).toContain("document_id=doc-only");
    expect(url).not.toContain("conversation_id");
    expect(url).not.toContain("corpus_id");
  });
});
