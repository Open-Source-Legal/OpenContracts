import { describe, it, expect } from "vitest";
import { arraysEqualUnordered, arraysEqualOrdered } from "../arrayUtils";

describe("arrayUtils", () => {
  describe("arraysEqualUnordered", () => {
    it("returns true for empty arrays", () => {
      expect(arraysEqualUnordered([], [])).toBe(true);
    });

    it("returns true when elements match regardless of order", () => {
      expect(arraysEqualUnordered(["a", "b", "c"], ["c", "a", "b"])).toBe(true);
    });

    it("returns false when lengths differ", () => {
      expect(arraysEqualUnordered(["a"], ["a", "b"])).toBe(false);
    });

    it("returns false when elements differ", () => {
      expect(arraysEqualUnordered(["a", "b"], ["a", "c"])).toBe(false);
    });

    it("treats duplicates by position after sort", () => {
      expect(arraysEqualUnordered(["a", "a", "b"], ["a", "b", "b"])).toBe(
        false
      );
      expect(arraysEqualUnordered(["a", "a", "b"], ["b", "a", "a"])).toBe(true);
    });
  });

  describe("arraysEqualOrdered", () => {
    it("returns true for identical arrays", () => {
      expect(arraysEqualOrdered(["a", "b"], ["a", "b"])).toBe(true);
    });

    it("returns false when order differs", () => {
      expect(arraysEqualOrdered(["a", "b"], ["b", "a"])).toBe(false);
    });

    it("returns false when lengths differ", () => {
      expect(arraysEqualOrdered([], ["a"])).toBe(false);
    });

    it("returns true for two empty arrays", () => {
      expect(arraysEqualOrdered([], [])).toBe(true);
    });
  });
});
