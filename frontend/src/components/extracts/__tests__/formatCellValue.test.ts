import { describe, expect, it } from "vitest";

import { EXTRACT_GRID_CELL_TRUNCATE_LENGTH } from "../../../assets/configurations/constants";
import { formatCellValue } from "../../../utils/formatters";

describe("formatCellValue", () => {
  it("returns em-dash for null", () => {
    expect(formatCellValue(null)).toBe("\u2014");
  });

  it("returns em-dash for undefined", () => {
    expect(formatCellValue(undefined)).toBe("\u2014");
  });

  it('returns "Yes" for true', () => {
    expect(formatCellValue(true)).toBe("Yes");
  });

  it('returns "No" for false', () => {
    expect(formatCellValue(false)).toBe("No");
  });

  it("returns stringified number", () => {
    expect(formatCellValue(42)).toBe("42");
    expect(formatCellValue(0)).toBe("0");
  });

  it("returns plain string as-is", () => {
    expect(formatCellValue("hello")).toBe("hello");
  });

  it("returns JSON for short objects", () => {
    const obj = { key: "val" };
    expect(formatCellValue(obj)).toBe(JSON.stringify(obj));
  });

  it("truncates JSON for objects exceeding the truncation length", () => {
    const longObj: Record<string, string> = {};
    for (let i = 0; i < 50; i++) {
      longObj[`key${i}`] = `value-${i}-padding`;
    }
    const json = JSON.stringify(longObj);
    // Precondition: the generated JSON is indeed longer than the limit.
    expect(json.length).toBeGreaterThan(EXTRACT_GRID_CELL_TRUNCATE_LENGTH);

    const result = formatCellValue(longObj);
    expect(result.length).toBe(EXTRACT_GRID_CELL_TRUNCATE_LENGTH + 1); // +1 for ellipsis char
    expect(result.endsWith("\u2026")).toBe(true);
  });
});
