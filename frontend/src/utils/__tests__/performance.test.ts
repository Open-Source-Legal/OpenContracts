import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  performanceMonitor,
  usePerformanceTracking,
  navigationTiming,
} from "../performance";

// The PerformanceMonitor only records when NODE_ENV === "development".
// In tests NODE_ENV is "test", so we toggle the private `enabled` field
// to verify both branches without needing to mutate process.env.
const monitor = performanceMonitor as unknown as { enabled: boolean };

describe("performance utilities", () => {
  let originalEnabled: boolean;
  let debugSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    originalEnabled = monitor.enabled;
    monitor.enabled = true;
    performanceMonitor.clearMetrics();
    debugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    monitor.enabled = originalEnabled;
    performanceMonitor.clearMetrics();
    debugSpy.mockRestore();
    warnSpy.mockRestore();
  });

  describe("start/end/getMetrics", () => {
    it("records duration between start and end", () => {
      performanceMonitor.startMetric("m1", { foo: "bar" });
      performanceMonitor.endMetric("m1", { baz: "qux" });

      const metrics = performanceMonitor.getMetrics();
      expect(metrics).toHaveLength(1);
      const [m] = metrics;
      expect(m.name).toBe("m1");
      expect(m.duration).toBeGreaterThanOrEqual(0);
      expect(m.metadata).toEqual({ foo: "bar", baz: "qux" });
    });

    it("warns and is a no-op when endMetric is called without a start", () => {
      performanceMonitor.endMetric("never-started");
      expect(warnSpy).toHaveBeenCalled();
    });

    it("clearMetrics removes all records", () => {
      performanceMonitor.startMetric("a");
      performanceMonitor.endMetric("a");
      expect(performanceMonitor.getMetrics()).toHaveLength(1);
      performanceMonitor.clearMetrics();
      expect(performanceMonitor.getMetrics()).toHaveLength(0);
    });

    it("is a no-op when disabled", () => {
      monitor.enabled = false;
      performanceMonitor.startMetric("skip-me");
      performanceMonitor.endMetric("skip-me");
      expect(performanceMonitor.getMetrics()).toHaveLength(0);
    });
  });

  describe("trackAsync", () => {
    it("measures a successful operation", async () => {
      const result = await performanceMonitor.trackAsync("ok", async () => 42);
      expect(result).toBe(42);
      const [m] = performanceMonitor.getMetrics();
      expect(m.metadata).toMatchObject({ success: true });
    });

    it("records failure and rethrows", async () => {
      await expect(
        performanceMonitor.trackAsync("fail", async () => {
          throw new Error("boom");
        })
      ).rejects.toThrow("boom");

      const [m] = performanceMonitor.getMetrics();
      expect(m.metadata).toMatchObject({ success: false });
      expect(m.metadata?.error).toContain("boom");
    });
  });

  describe("usePerformanceTracking", () => {
    it("returns bound start/end/track helpers", async () => {
      const api = usePerformanceTracking("ui-load");
      api.start({ variant: "a" });
      api.end({ cached: true });

      const [m] = performanceMonitor.getMetrics();
      expect(m.name).toBe("ui-load");
      expect(m.metadata).toMatchObject({ variant: "a", cached: true });

      performanceMonitor.clearMetrics();
      const value = await api.track(async () => "done", { attempt: 1 });
      expect(value).toBe("done");
      const [tracked] = performanceMonitor.getMetrics();
      expect(tracked.metadata).toMatchObject({ attempt: 1, success: true });
    });
  });

  describe("navigationTiming", () => {
    it("tracks navigation start/complete", () => {
      navigationTiming.trackNavigation("/a", "/b");
      navigationTiming.completeNavigation(true);
      const [m] = performanceMonitor.getMetrics();
      expect(m.name).toBe("navigation");
      expect(m.metadata).toMatchObject({ from: "/a", to: "/b", success: true });
    });

    it("tracks slug resolution start/complete", () => {
      navigationTiming.trackSlugResolution("corpus", "my-corpus");
      navigationTiming.completeSlugResolution("corpus", true);
      const metrics = performanceMonitor.getMetrics();
      const slug = metrics.find((m) => m.name === "slug-resolution-corpus");
      expect(slug).toBeDefined();
      expect(slug?.metadata).toMatchObject({
        slug: "my-corpus",
        found: true,
      });
    });
  });
});
