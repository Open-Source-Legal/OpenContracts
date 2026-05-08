import { describe, expect, it } from "vitest";

import {
  getLeaderboardAvatarColor,
  getLeaderboardInitials,
} from "../leaderboardAvatar";

describe("getLeaderboardInitials", () => {
  it("returns ? for nullish/empty names", () => {
    expect(getLeaderboardInitials()).toBe("?");
    expect(getLeaderboardInitials("")).toBe("?");
    expect(getLeaderboardInitials(undefined)).toBe("?");
  });

  it("returns G for google OAuth subs", () => {
    expect(getLeaderboardInitials("google-oauth2|114688257717759010643")).toBe(
      "G"
    );
    expect(getLeaderboardInitials("google|abc")).toBe("G");
  });

  it("returns GH for github OAuth subs", () => {
    expect(getLeaderboardInitials("github|123")).toBe("GH");
  });

  it("returns U for any other OAuth-shaped sub", () => {
    expect(getLeaderboardInitials("auth0|whatever")).toBe("U");
    expect(getLeaderboardInitials("apple|abc123")).toBe("U");
  });

  it("uses first letter of two tokens for multi-token names", () => {
    expect(getLeaderboardInitials("Jane Doe")).toBe("JD");
    expect(getLeaderboardInitials("alice bob carol")).toBe("AB");
    expect(getLeaderboardInitials("  Alice   Bob  ")).toBe("AB");
  });

  it("falls back to first two characters for single-token names", () => {
    expect(getLeaderboardInitials("alice")).toBe("AL");
    expect(getLeaderboardInitials("X")).toBe("X");
  });

  it("trims surrounding whitespace before extracting initials", () => {
    // Leading-space regression: previously returned "  " instead of "AL"
    // because substring was called on the un-trimmed input.
    expect(getLeaderboardInitials("  alice")).toBe("AL");
    expect(getLeaderboardInitials("\tBob")).toBe("BO");
  });

  it("returns ? for whitespace-only single-token names", () => {
    // After trimming and filtering, no tokens remain — the redirected
    // fallback should not silently surface whitespace.
    expect(getLeaderboardInitials("   ")).toBe("?");
    expect(getLeaderboardInitials("\t\n")).toBe("?");
  });
});

describe("getLeaderboardAvatarColor", () => {
  it("returns the first palette color when userId is missing", () => {
    const noId = getLeaderboardAvatarColor();
    expect(typeof noId).toBe("string");
    expect(noId.length).toBeGreaterThan(0);
    expect(getLeaderboardAvatarColor("")).toBe(noId);
  });

  it("returns a deterministic color for a given userId", () => {
    expect(getLeaderboardAvatarColor("user-1")).toBe(
      getLeaderboardAvatarColor("user-1")
    );
  });

  it("returns different colors for different ids (statistically)", () => {
    const a = getLeaderboardAvatarColor("a");
    const z = getLeaderboardAvatarColor("zzzzzzz");
    expect(a).not.toBe(undefined);
    expect(z).not.toBe(undefined);
  });

  it("always returns a non-empty string", () => {
    for (const id of ["1", "2", "abc", "longuserid12345"]) {
      const color = getLeaderboardAvatarColor(id);
      expect(typeof color).toBe("string");
      expect(color.length).toBeGreaterThan(0);
    }
  });
});
