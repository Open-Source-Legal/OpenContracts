import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearLocalAuthSession,
  loadLocalAuthSession,
  loadLocalAuthSessionUser,
  LOCAL_AUTH_SESSION_TTL_MS,
  saveLocalAuthSession,
} from "./localAuthSession";

describe("localAuthSession", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("restores a token for up to 24 hours", () => {
    vi.setSystemTime(new Date("2026-08-30T08:00:00Z"));
    saveLocalAuthSession("jwt-token");

    vi.setSystemTime(
      new Date(Date.now() + LOCAL_AUTH_SESSION_TTL_MS - 1)
    );
    expect(loadLocalAuthSession()).toBe("jwt-token");
  });

  it("restores the local user's display identity", () => {
    const user = { id: "1", username: "admin", isSuperuser: true };
    saveLocalAuthSession("jwt-token", user);

    expect(loadLocalAuthSessionUser()).toEqual(user);
  });

  it("removes an expired token", () => {
    vi.setSystemTime(new Date("2026-08-30T08:00:00Z"));
    saveLocalAuthSession("jwt-token");

    vi.setSystemTime(new Date(Date.now() + LOCAL_AUTH_SESSION_TTL_MS));
    expect(loadLocalAuthSession()).toBeNull();
  });

  it("clears a saved session on logout", () => {
    saveLocalAuthSession("jwt-token");
    clearLocalAuthSession();
    expect(loadLocalAuthSession()).toBeNull();
  });
});
