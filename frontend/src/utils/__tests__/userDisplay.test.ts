import { describe, it, expect } from "vitest";
import {
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
