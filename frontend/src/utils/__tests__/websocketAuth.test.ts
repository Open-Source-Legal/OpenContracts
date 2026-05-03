import { describe, it, expect } from "vitest";
import {
  WS_AUTH_SUBPROTOCOL,
  buildAuthProtocols,
  buildAuthMessage,
  parseAuthMessage,
} from "../websocketAuth";

describe("websocketAuth helpers", () => {
  it("uses opencontracts.jwt.v1 as the subprotocol marker", () => {
    expect(WS_AUTH_SUBPROTOCOL).toBe("opencontracts.jwt.v1");
  });

  it("builds protocols array with token when present", () => {
    expect(buildAuthProtocols("abc.def.ghi")).toEqual([
      "opencontracts.jwt.v1",
      "abc.def.ghi",
    ]);
  });

  it("builds protocols array with marker only when no token", () => {
    expect(buildAuthProtocols(undefined)).toEqual(["opencontracts.jwt.v1"]);
    expect(buildAuthProtocols(null)).toEqual(["opencontracts.jwt.v1"]);
    expect(buildAuthProtocols("")).toEqual(["opencontracts.jwt.v1"]);
  });

  it("builds AUTH refresh message", () => {
    expect(buildAuthMessage("abc")).toEqual({ type: "AUTH", token: "abc" });
  });

  it("parses AUTH_OK frames", () => {
    const m = parseAuthMessage(
      JSON.stringify({ type: "AUTH_OK", user_id: 1, anonymous: false })
    );
    expect(m).toEqual({ type: "AUTH_OK", user_id: 1, anonymous: false });
  });

  it("returns null for non-AUTH frames", () => {
    expect(
      parseAuthMessage(JSON.stringify({ type: "ASYNC_CONTENT" }))
    ).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseAuthMessage("not json")).toBeNull();
  });
});
