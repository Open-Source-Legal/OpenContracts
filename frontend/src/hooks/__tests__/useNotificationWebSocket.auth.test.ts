import { describe, it, expect, beforeEach, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("window", {
    location: { protocol: "https:", host: "example.com" },
  });
  vi.stubGlobal("import.meta", { env: {} });
});

describe("getNotificationUpdatesWebSocket — no token in URL (security regression)", () => {
  it("does not include token in URL when called with no args", async () => {
    const { getNotificationUpdatesWebSocket } = await import(
      "../../components/chat/get_websockets"
    );
    const url = getNotificationUpdatesWebSocket();
    expect(url).not.toContain("token");
    expect(url).not.toContain("?");
  });
});

describe("getUnifiedAgentWebSocket — no token in URL", () => {
  it("returns URL with only context params, never token", async () => {
    const { getUnifiedAgentWebSocket } = await import(
      "../../components/chat/get_websockets"
    );
    const url = getUnifiedAgentWebSocket({ documentId: "RG9jOjE=" });
    expect(url).toContain("document_id=RG9jOjE%3D");
    expect(url).not.toContain("token");
  });
});

describe("getThreadUpdatesWebSocket — no token in URL", () => {
  it("returns URL with conversation_id only", async () => {
    const { getThreadUpdatesWebSocket } = await import(
      "../../components/chat/get_websockets"
    );
    const url = getThreadUpdatesWebSocket("Q29udjox");
    expect(url).toContain("conversation_id=Q29udjox");
    expect(url).not.toContain("token");
  });
});
