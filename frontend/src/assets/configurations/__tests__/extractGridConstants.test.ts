import { describe, it, expect } from "vitest";
import {
  EXTRACT_GRID_CELL_TRUNCATE_LENGTH,
  EXTRACT_GRID_EMBED_MAX_ROWS,
  EXTRACT_GRID_EMBED_MAX_COLS,
  EXTRACT_GRID_EMBED_MAX_CELLS,
} from "../constants";

describe("Extract grid constants", () => {
  it("EXTRACT_GRID_CELL_TRUNCATE_LENGTH should be a positive integer", () => {
    expect(EXTRACT_GRID_CELL_TRUNCATE_LENGTH).toBeGreaterThan(0);
    expect(Number.isInteger(EXTRACT_GRID_CELL_TRUNCATE_LENGTH)).toBe(true);
  });

  it("EXTRACT_GRID_EMBED_MAX_ROWS should be a positive integer", () => {
    expect(EXTRACT_GRID_EMBED_MAX_ROWS).toBeGreaterThan(0);
    expect(Number.isInteger(EXTRACT_GRID_EMBED_MAX_ROWS)).toBe(true);
  });

  it("EXTRACT_GRID_EMBED_MAX_COLS should be a positive integer", () => {
    expect(EXTRACT_GRID_EMBED_MAX_COLS).toBeGreaterThan(0);
    expect(Number.isInteger(EXTRACT_GRID_EMBED_MAX_COLS)).toBe(true);
  });

  it("EXTRACT_GRID_EMBED_MAX_CELLS should equal (MAX_ROWS + 1) * MAX_COLS", () => {
    // The +1 allows the too-many-rows guard to fire while still bounding
    // the worst-case payload. This formula is documented in constants.ts.
    const expected =
      (EXTRACT_GRID_EMBED_MAX_ROWS + 1) * EXTRACT_GRID_EMBED_MAX_COLS;
    expect(EXTRACT_GRID_EMBED_MAX_CELLS).toBe(expected);
  });

  it("EXTRACT_GRID_EMBED_MAX_CELLS should stay below backend cap of 10_000", () => {
    // The backend enforces MAX_DATACELL_FIRST = 10_000 in
    // opencontractserver/constants/annotations.py. The frontend value must
    // stay below this to avoid silently truncated results.
    expect(EXTRACT_GRID_EMBED_MAX_CELLS).toBeLessThan(10_000);
  });
});
