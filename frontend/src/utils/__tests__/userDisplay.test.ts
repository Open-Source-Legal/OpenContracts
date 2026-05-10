import { describe, it, expect } from "vitest";
import {
  decodeRelayPk,
  getCreatorDisplay,
  getCreatorInitials,
  isOwnedBy,
} from "../userDisplay";

describe("userDisplay", () => {
  describe("getCreatorDisplay", () => {
    it("returns 'Unknown' for null creator", () => {
      expect(getCreatorDisplay(null)).toBe("Unknown");
    });

    it("returns 'Unknown' for undefined creator", () => {
      expect(getCreatorDisplay(undefined)).toBe("Unknown");
    });

    it("returns 'Unknown' when both id and slug are missing", () => {
      expect(getCreatorDisplay({})).toBe("Unknown");
    });

    it("prefers slug when present", () => {
      expect(getCreatorDisplay({ id: "42", slug: "alice-smith" })).toBe(
        "alice-smith"
      );
    });

    it("falls back to user_<id> when slug missing", () => {
      expect(getCreatorDisplay({ id: "42" })).toBe("user_42");
    });

    it("falls back to user_<id> when slug is empty string", () => {
      expect(getCreatorDisplay({ id: "42", slug: "" })).toBe("user_42");
    });

    it("falls back to user_<id> when slug is null", () => {
      expect(getCreatorDisplay({ id: "42", slug: null })).toBe("user_42");
    });

    it("decodes a Relay global ID and uses the pk suffix to match _redacted_handle", () => {
      // base64("UserType:1") === "VXNlclR5cGU6MQ==" — backend
      // _redacted_handle returns "user_1" for pk=1, so the frontend
      // fallback must too.
      expect(getCreatorDisplay({ id: "VXNlclR5cGU6MQ==" })).toBe("user_1");
    });

    it("uses last 6 chars of the pk for long Relay IDs to mirror the backend suffix", () => {
      // base64("UserType:1234567") === "VXNlclR5cGU6MTIzNDU2Nw==" — pk is
      // "1234567", suffix length is 6, so we expect "user_234567".
      expect(getCreatorDisplay({ id: "VXNlclR5cGU6MTIzNDU2Nw==" })).toBe(
        "user_234567"
      );
    });
  });

  describe("decodeRelayPk", () => {
    it("decodes a valid Relay global ID", () => {
      expect(decodeRelayPk("VXNlclR5cGU6MQ==")).toBe("1");
    });

    it("handles a multi-segment type name by splitting on the last colon", () => {
      // base64("Some:Type:99") — only the final segment is the pk.
      const id = btoa("Some:Type:99");
      expect(decodeRelayPk(id)).toBe("99");
    });

    it("returns null for an undecodable input", () => {
      // Plain numeric strings aren't base64-decodable to a "<type>:<pk>" form.
      // Either atob throws or the decoded payload has no colon — both must
      // resolve to null so callers fall back gracefully.
      expect(decodeRelayPk("42")).toBeNull();
    });

    it("returns null for null/undefined", () => {
      expect(decodeRelayPk(null)).toBeNull();
      expect(decodeRelayPk(undefined)).toBeNull();
    });

    it("returns null when the decoded payload has no colon separator", () => {
      const id = btoa("nopk");
      expect(decodeRelayPk(id)).toBeNull();
    });
  });

  describe("getCreatorInitials", () => {
    it("returns '?' for null creator", () => {
      // Unknown -> 'UN'
      expect(getCreatorInitials(null)).toBe("UN");
    });

    it("derives two-letter initials from hyphenated slug", () => {
      expect(getCreatorInitials({ slug: "alice-smith" })).toBe("AS");
    });

    it("uses first two chars when slug has only one word", () => {
      expect(getCreatorInitials({ slug: "alice" })).toBe("AL");
    });

    it("derives initials from user_<id> fallback", () => {
      // 'user_42' -> strips user_ -> '42' -> '42'
      expect(getCreatorInitials({ id: "42" })).toBe("42");
    });

    it("handles slug with multiple hyphens", () => {
      expect(getCreatorInitials({ slug: "bob-jones-the-third" })).toBe("BJ");
    });

    it("handles slug with leading/trailing hyphens", () => {
      expect(getCreatorInitials({ slug: "-alice-smith-" })).toBe("AS");
    });
  });

  describe("isOwnedBy", () => {
    it("returns false when both null", () => {
      expect(isOwnedBy(null, null)).toBe(false);
    });

    it("returns false when creator missing", () => {
      expect(isOwnedBy(null, { id: "1" })).toBe(false);
    });

    it("returns false when currentUser missing", () => {
      expect(isOwnedBy({ id: "1" }, null)).toBe(false);
    });

    it("returns false when creator id missing", () => {
      expect(isOwnedBy({ slug: "x" }, { id: "1" })).toBe(false);
    });

    it("returns false when currentUser id missing", () => {
      expect(isOwnedBy({ id: "1" }, { slug: "x" })).toBe(false);
    });

    it("returns true when ids match", () => {
      expect(isOwnedBy({ id: "1" }, { id: "1" })).toBe(true);
    });

    it("returns false when ids differ", () => {
      expect(isOwnedBy({ id: "1" }, { id: "2" })).toBe(false);
    });
  });
});
