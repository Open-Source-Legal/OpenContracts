import { describe, expect, it } from "vitest";

import { createSeededRandom, runSimulationTicks } from "./graphLayout";

describe("createSeededRandom", () => {
  it("is deterministic for a given seed", () => {
    const a = createSeededRandom(42);
    const b = createSeededRandom(42);
    const seqA = Array.from({ length: 5 }, () => a());
    const seqB = Array.from({ length: 5 }, () => b());
    expect(seqA).toEqual(seqB);
  });

  it("yields floats in [0, 1) that vary across draws", () => {
    const rand = createSeededRandom(7);
    const draws = Array.from({ length: 100 }, () => rand());
    draws.forEach((v) => {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    });
    expect(new Set(draws).size).toBeGreaterThan(90);
  });

  it("different seeds give different sequences", () => {
    const a = createSeededRandom(1);
    const b = createSeededRandom(2);
    expect(Array.from({ length: 3 }, () => a())).not.toEqual(
      Array.from({ length: 3 }, () => b())
    );
  });
});

describe("runSimulationTicks", () => {
  it("calls tick exactly the requested number of times", () => {
    let calls = 0;
    runSimulationTicks({ tick: () => (calls += 1) }, 60);
    expect(calls).toBe(60);
  });
});
