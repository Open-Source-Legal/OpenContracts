import { describe, it, expect } from "vitest";
import {
  getExtractStatus,
  formatExtractDate,
  formatExtractListStats,
} from "../extractUtils";
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

  describe("formatExtractListStats", () => {
    it("uses backend ``documentCount`` aggregate when present", () => {
      const stats = formatExtractListStats({ documentCount: 5 });
      expect(stats[0]).toBe("5 documents");
    });

    it("singularises ``document`` when count is exactly 1", () => {
      const stats = formatExtractListStats({ documentCount: 1 });
      expect(stats[0]).toBe("1 document");
    });

    it("falls back to ``fullDocumentList.length`` when ``documentCount`` is unset", () => {
      const stats = formatExtractListStats({
        fullDocumentList: [{}, {}, {}],
      });
      expect(stats[0]).toBe("3 documents");
    });

    it("treats ``documentCount: null`` (server null) as missing and falls through", () => {
      const stats = formatExtractListStats({
        documentCount: null,
        fullDocumentList: [{}],
      });
      expect(stats[0]).toBe("1 document");
    });

    it("emits ``0 documents`` when neither aggregate nor list is supplied", () => {
      expect(formatExtractListStats({})[0]).toBe("0 documents");
    });

    it("appends the column line only when columnCount > 0", () => {
      expect(
        formatExtractListStats({
          documentCount: 1,
          fieldset: { columnCount: 0 },
        })
      ).toEqual(["1 document"]);
      expect(
        formatExtractListStats({
          documentCount: 1,
          fieldset: { columnCount: 4 },
        })
      ).toEqual(["1 document", "4 columns"]);
    });

    it("falls back to ``fullColumnList.length`` for the column count", () => {
      const stats = formatExtractListStats({
        documentCount: 0,
        fieldset: { fullColumnList: [{}, {}] },
      });
      expect(stats).toContain("2 columns");
    });

    it("singularises ``column`` when count is exactly 1", () => {
      const stats = formatExtractListStats({
        documentCount: 0,
        fieldset: { columnCount: 1 },
      });
      expect(stats).toContain("1 column");
    });

    it("appends the corpus line when ``corpus.title`` is non-empty", () => {
      const stats = formatExtractListStats({
        documentCount: 1,
        corpus: { title: "Contracts" },
      });
      expect(stats).toContain("from Contracts");
    });

    it("omits the corpus line when corpus is null or untitled", () => {
      expect(
        formatExtractListStats({ documentCount: 1, corpus: null })
      ).toEqual(["1 document"]);
      expect(
        formatExtractListStats({ documentCount: 1, corpus: { title: "" } })
      ).toEqual(["1 document"]);
    });
  });
});
