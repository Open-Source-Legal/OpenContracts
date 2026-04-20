import { describe, it, expect } from "vitest";
import { getExtractStatus, formatExtractDate } from "../extractUtils";
import {
  EXTRACT_STATUS,
  EXTRACT_STATUS_COLORS,
} from "../../assets/configurations/constants";
import type { ExtractType } from "../../types/graphql-api";

function makeExtract(overrides: Partial<ExtractType>): ExtractType {
  return {
    id: "ext-1",
    name: "Test",
    ...overrides,
  } as ExtractType;
}

describe("extractUtils", () => {
  describe("getExtractStatus", () => {
    it("returns RUNNING when started but not finished and no error", () => {
      const info = getExtractStatus(
        makeExtract({ started: "2024-01-01", finished: null, error: null })
      );
      expect(info.label).toBe(EXTRACT_STATUS.RUNNING);
      expect(info.color).toBe(EXTRACT_STATUS_COLORS[EXTRACT_STATUS.RUNNING]);
    });

    it("returns COMPLETED when finished is truthy", () => {
      const info = getExtractStatus(
        makeExtract({
          started: "2024-01-01",
          finished: "2024-01-02",
        })
      );
      expect(info.label).toBe(EXTRACT_STATUS.COMPLETED);
    });

    it("returns FAILED when error is set and not finished", () => {
      const info = getExtractStatus(
        makeExtract({ started: null, finished: null, error: "boom" })
      );
      expect(info.label).toBe(EXTRACT_STATUS.FAILED);
    });

    it("returns NOT_STARTED when nothing is set", () => {
      const info = getExtractStatus(
        makeExtract({ started: null, finished: null, error: null })
      );
      expect(info.label).toBe(EXTRACT_STATUS.NOT_STARTED);
    });

    it("prefers COMPLETED over FAILED when both finished and error are set", () => {
      const info = getExtractStatus(
        makeExtract({
          started: "2024-01-01",
          finished: "2024-01-02",
          error: "ignored",
        })
      );
      expect(info.label).toBe(EXTRACT_STATUS.COMPLETED);
    });
  });

  describe("formatExtractDate", () => {
    it("produces a non-empty localized string", () => {
      const result = formatExtractDate("2024-01-15T12:00:00Z");
      expect(result.length).toBeGreaterThan(0);
    });
  });
});
