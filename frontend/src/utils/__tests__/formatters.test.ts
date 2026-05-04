import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  formatFileSize,
  formatRelativeTime,
  formatCompactRelativeTime,
  getInitials,
  formatShortDate,
  formatSettingLabel,
  formatCellValue,
  stripMarkdown,
} from "../formatters";
import { EXTRACT_GRID_CELL_TRUNCATE_LENGTH } from "../../assets/configurations/constants";

describe("formatters", () => {
  describe("formatFileSize", () => {
    it("returns empty string for null/undefined", () => {
      expect(formatFileSize(null)).toBe("");
      expect(formatFileSize(undefined)).toBe("");
    });

    it("formats bytes below 1 KB", () => {
      expect(formatFileSize(0)).toBe("0 B");
      expect(formatFileSize(512)).toBe("512 B");
      expect(formatFileSize(1023)).toBe("1023 B");
    });

    it("formats kilobytes with one decimal", () => {
      expect(formatFileSize(1024)).toBe("1.0 KB");
      expect(formatFileSize(1536)).toBe("1.5 KB");
    });

    it("formats megabytes with one decimal", () => {
      expect(formatFileSize(1024 * 1024)).toBe("1.0 MB");
      expect(formatFileSize(Math.round(2.3 * 1024 * 1024))).toBe("2.3 MB");
    });
  });

  describe("formatRelativeTime", () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-01-15T12:00:00Z"));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("returns empty string for missing or invalid input", () => {
      expect(formatRelativeTime(null)).toBe("");
      expect(formatRelativeTime(undefined)).toBe("");
      expect(formatRelativeTime("")).toBe("");
      expect(formatRelativeTime("not a date")).toBe("");
    });

    it("returns 'Just now' when under an hour", () => {
      expect(formatRelativeTime("2026-01-15T11:30:00Z")).toBe("Just now");
    });

    it("returns hours ago when within a day", () => {
      expect(formatRelativeTime("2026-01-15T07:00:00Z")).toBe("5 hours ago");
    });

    it("returns days ago when within a week", () => {
      expect(formatRelativeTime("2026-01-12T12:00:00Z")).toBe("3 days ago");
    });

    it("falls back to localeDateString beyond a week", () => {
      const result = formatRelativeTime("2025-12-01T12:00:00Z");
      // toLocaleDateString output varies between environments — just assert non-empty
      expect(result.length).toBeGreaterThan(0);
      expect(result).not.toBe("Just now");
    });
  });

  describe("formatCompactRelativeTime", () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-01-15T12:00:00Z"));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("returns empty string for missing or invalid input", () => {
      expect(formatCompactRelativeTime(null)).toBe("");
      expect(formatCompactRelativeTime(undefined)).toBe("");
      expect(formatCompactRelativeTime("")).toBe("");
      expect(formatCompactRelativeTime("nope")).toBe("");
    });

    it("returns 'Just now' for very recent timestamps", () => {
      expect(formatCompactRelativeTime("2026-01-15T11:59:50Z")).toBe(
        "Just now"
      );
    });

    it("returns minutes format for under an hour", () => {
      expect(formatCompactRelativeTime("2026-01-15T11:45:00Z")).toBe("15m ago");
    });

    it("returns hours format for under a day", () => {
      expect(formatCompactRelativeTime("2026-01-15T09:00:00Z")).toBe("3h ago");
    });

    it("returns days format for under a month", () => {
      expect(formatCompactRelativeTime("2026-01-10T12:00:00Z")).toBe("5d ago");
    });

    it("falls back to locale date for over a month", () => {
      const result = formatCompactRelativeTime("2025-10-01T12:00:00Z");
      expect(result.length).toBeGreaterThan(0);
      expect(result).not.toMatch(/ago$/);
    });
  });

  describe("getInitials", () => {
    it("defaults to 'U' when name is missing", () => {
      expect(getInitials()).toBe("U");
      expect(getInitials(null)).toBe("U");
      expect(getInitials("")).toBe("U");
    });

    it("takes first letter before @ for emails", () => {
      expect(getInitials("jane@example.com")).toBe("J");
    });

    it("takes first two initials for multi-word names", () => {
      expect(getInitials("Jane Doe")).toBe("JD");
      expect(getInitials("alice bob carol")).toBe("AB");
    });

    it("handles single-word names", () => {
      expect(getInitials("alice")).toBe("A");
    });
  });

  describe("formatShortDate", () => {
    it("returns empty string on bad input", () => {
      expect(formatShortDate(null)).toBe("");
      expect(formatShortDate(undefined)).toBe("");
      expect(formatShortDate("")).toBe("");
      expect(formatShortDate("garbage")).toBe("");
    });

    it("returns a non-empty formatted string for valid input", () => {
      const result = formatShortDate("2023-10-05T00:00:00Z");
      expect(result.length).toBeGreaterThan(0);
    });
  });

  describe("formatSettingLabel", () => {
    it("uses description when provided", () => {
      expect(formatSettingLabel("api_key", "API Token")).toBe("API Token");
    });

    it("trims description whitespace", () => {
      expect(formatSettingLabel("x", "  Label  ")).toBe("Label");
    });

    it("falls back to title-cased snake_case name", () => {
      expect(formatSettingLabel("api_key")).toBe("Api Key");
      expect(formatSettingLabel("max_retries", "")).toBe("Max Retries");
      expect(formatSettingLabel("single")).toBe("Single");
    });

    it("ignores whitespace-only description", () => {
      expect(formatSettingLabel("retry_count", "   ")).toBe("Retry Count");
    });
  });

  describe("formatCellValue", () => {
    it("returns em-dash for null/undefined", () => {
      expect(formatCellValue(null)).toBe("\u2014");
      expect(formatCellValue(undefined)).toBe("\u2014");
    });

    it("returns 'Yes'/'No' for booleans", () => {
      expect(formatCellValue(true)).toBe("Yes");
      expect(formatCellValue(false)).toBe("No");
    });

    it("stringifies numbers and strings", () => {
      expect(formatCellValue(42)).toBe("42");
      expect(formatCellValue("hello")).toBe("hello");
    });

    it("JSON-encodes small objects", () => {
      expect(formatCellValue({ a: 1 })).toBe('{"a":1}');
    });

    it("truncates large objects with an ellipsis", () => {
      const big: Record<string, string> = {};
      // Ensure serialized length exceeds the truncation threshold.
      for (let i = 0; i < EXTRACT_GRID_CELL_TRUNCATE_LENGTH; i++) {
        big[`k${i}`] = `v${i}`;
      }
      const result = formatCellValue(big);
      expect(result.endsWith("\u2026")).toBe(true);
      expect(result.length).toBe(EXTRACT_GRID_CELL_TRUNCATE_LENGTH + 1);
    });
  });

  describe("stripMarkdown", () => {
    it("returns empty string for null/undefined/empty", () => {
      expect(stripMarkdown(null)).toBe("");
      expect(stripMarkdown(undefined)).toBe("");
      expect(stripMarkdown("")).toBe("");
    });

    it("strips emphasis markers", () => {
      expect(stripMarkdown("This is **bold** and *italic*")).toBe(
        "This is bold and italic"
      );
      expect(stripMarkdown("__bold__ __also bold__ _ital_")).toBe(
        "bold also bold ital"
      );
    });

    it("strips inline and fenced code", () => {
      expect(stripMarkdown("Use `foo()` to fly")).toBe("Use foo() to fly");
      expect(stripMarkdown("before\n```\ncode\nblock\n```\nafter")).toBe(
        "before after"
      );
    });

    it("strips links and images down to label/alt text", () => {
      expect(stripMarkdown("see [the docs](https://x.test) please")).toBe(
        "see the docs please"
      );
      expect(stripMarkdown("![alt](http://x/y.png)")).toBe("alt");
    });

    it("strips ATX headers, blockquotes, and list markers", () => {
      expect(stripMarkdown("# Header\nbody")).toBe("Header body");
      expect(stripMarkdown("> a quote")).toBe("a quote");
      expect(stripMarkdown("- item one\n- item two")).toBe("item one item two");
      expect(stripMarkdown("1. first\n2. second")).toBe("first second");
    });

    it("strips raw HTML tags and entities", () => {
      expect(stripMarkdown("<p>hello <b>world</b></p>")).toBe("hello world");
      expect(stripMarkdown("a &amp; b")).toBe("a b");
    });

    it("collapses whitespace", () => {
      expect(stripMarkdown("  too   many\n\nspaces  ")).toBe("too many spaces");
    });
  });
});
