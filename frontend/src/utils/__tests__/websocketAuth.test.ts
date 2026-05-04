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

  it("parses AUTH_FAILED frames", () => {
    const m = parseAuthMessage(
      JSON.stringify({ type: "AUTH_FAILED", reason: "EXPIRED" })
    );
    expect(m).toEqual({ type: "AUTH_FAILED", reason: "EXPIRED" });
  });

  it("parses AUTH_REFRESH_REQUIRED frames", () => {
    const m = parseAuthMessage(
      JSON.stringify({ type: "AUTH_REFRESH_REQUIRED", grace_seconds: 30 })
    );
    expect(m).toEqual({ type: "AUTH_REFRESH_REQUIRED", grace_seconds: 30 });
  });

  it("returns null for non-AUTH frames", () => {
    expect(
      parseAuthMessage(JSON.stringify({ type: "ASYNC_CONTENT" }))
    ).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseAuthMessage("not json")).toBeNull();
  });

  it("returns null for non-object JSON (number, string, array)", () => {
    expect(parseAuthMessage(JSON.stringify(42))).toBeNull();
    expect(parseAuthMessage(JSON.stringify("hello"))).toBeNull();
    expect(parseAuthMessage(JSON.stringify([1, 2, 3]))).toBeNull();
  });

  it("returns null when type field is missing or not a string", () => {
    expect(parseAuthMessage(JSON.stringify({ payload: "x" }))).toBeNull();
    expect(parseAuthMessage(JSON.stringify({ type: 99 }))).toBeNull();
  });
});
