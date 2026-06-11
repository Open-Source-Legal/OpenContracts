/**
 * Deterministic layout helpers shared by the corpus-intelligence graph
 * glimpses (``DocumentGraphGlimpse``, ``GovernanceGraphGlimpse``). Both render
 * d3-force layouts as static SVG, so the layout must be reproducible for a
 * given input: positions are seeded without ``Math.random`` and the simulation
 * is stepped synchronously for a fixed number of ticks (no animation loop) —
 * cheap at glimpse scale and friendly to screenshot-based tests.
 */

// Park–Miller "minimal standard" LCG parameters: multiplier 7^5 over the
// Mersenne prime modulus 2^31 − 1. Algorithm-intrinsic, not tunables.
const LCG_MULTIPLIER = 16807;
const LCG_MODULUS = 2147483647;

/**
 * A tiny deterministic stand-in for ``Math.random``: returns a generator
 * yielding floats in [0, 1) that are fully determined by ``seed``.
 */
export function createSeededRandom(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * LCG_MULTIPLIER) % LCG_MODULUS;
    return (state - 1) / (LCG_MODULUS - 1);
  };
}

/**
 * Step a stopped d3-force simulation synchronously through its alpha
 * schedule. Callers must have called ``.stop()`` on the simulation first so
 * d3 never schedules its own animation frames.
 */
export function runSimulationTicks(
  simulation: { tick: () => void },
  ticks: number
): void {
  for (let i = 0; i < ticks; i += 1) {
    simulation.tick();
  }
}
