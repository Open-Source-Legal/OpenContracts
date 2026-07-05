import { describe, it, expect } from "vitest";
import { appendToChain, reorderChain } from "./utils";

describe("reorderChain", () => {
  it("swaps the item at index with its next neighbor on direction=1", () => {
    expect(reorderChain(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
  });

  it("swaps the item at index with its previous neighbor on direction=-1", () => {
    expect(reorderChain(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
  });

  it("returns the SAME array reference when moving past the start", () => {
    const chain = ["a", "b"];
    expect(reorderChain(chain, 0, -1)).toBe(chain);
  });

  it("returns the SAME array reference when moving past the end", () => {
    const chain = ["a", "b"];
    expect(reorderChain(chain, 1, 1)).toBe(chain);
  });
});

describe("appendToChain", () => {
  it("appends a new className", () => {
    expect(appendToChain(["a"], "b")).toEqual(["a", "b"]);
  });

  it("returns the SAME array reference for an empty className", () => {
    const chain = ["a"];
    expect(appendToChain(chain, "")).toBe(chain);
  });

  it("returns the SAME array reference when the className is already present", () => {
    const chain = ["a", "b"];
    expect(appendToChain(chain, "b")).toBe(chain);
  });
});
