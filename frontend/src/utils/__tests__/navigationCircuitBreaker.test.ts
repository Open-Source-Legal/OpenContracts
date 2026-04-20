import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { navigationCircuitBreaker } from "../navigationCircuitBreaker";

describe("navigationCircuitBreaker", () => {
  let alertSpy: ReturnType<typeof vi.spyOn>;
  let errorSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    navigationCircuitBreaker.reset();
    alertSpy = vi
      .spyOn(window, "alert")
      .mockImplementation(() => undefined as any);
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    navigationCircuitBreaker.reset();
    alertSpy.mockRestore();
    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it("records navigation events and allows them under the limit", () => {
    expect(navigationCircuitBreaker.recordNavigation("/a", "test")).toBe(true);
    expect(navigationCircuitBreaker.recordNavigation("/b", "test")).toBe(true);

    const status = navigationCircuitBreaker.getStatus();
    expect(status.tripped).toBe(false);
    expect(status.eventCount).toBe(2);
    expect(status.events[0].url).toBe("/a");
  });

  it("trips on loop threshold (same URL repeated)", () => {
    navigationCircuitBreaker.recordNavigation("/loop", "test");
    navigationCircuitBreaker.recordNavigation("/loop", "test");
    // Third hit on same URL should trip the breaker.
    const result = navigationCircuitBreaker.recordNavigation("/loop", "test");
    expect(result).toBe(false);
    expect(navigationCircuitBreaker.getStatus().tripped).toBe(true);
    expect(alertSpy).toHaveBeenCalled();
  });

  it("trips when too many navigations occur in the window", () => {
    // 6 unique URLs in window — exceeds MAX_NAVIGATIONS (5).
    const results = [
      navigationCircuitBreaker.recordNavigation("/a", "t"),
      navigationCircuitBreaker.recordNavigation("/b", "t"),
      navigationCircuitBreaker.recordNavigation("/c", "t"),
      navigationCircuitBreaker.recordNavigation("/d", "t"),
      navigationCircuitBreaker.recordNavigation("/e", "t"),
      navigationCircuitBreaker.recordNavigation("/f", "t"),
    ];
    expect(results.slice(0, 5).every((r) => r === true)).toBe(true);
    expect(results[5]).toBe(false);
    expect(navigationCircuitBreaker.getStatus().tripped).toBe(true);
  });

  it("trips on ping-pong between two URLs", () => {
    navigationCircuitBreaker.recordNavigation("/x", "t");
    navigationCircuitBreaker.recordNavigation("/y", "t");
    navigationCircuitBreaker.recordNavigation("/x", "t");
    const result = navigationCircuitBreaker.recordNavigation("/y", "t");
    // Either loop threshold (2 x "/x" in last four with /y twice hits
    // LOOP_THRESHOLD=3? no, we only have 2 /x. So the ping-pong path trips here)
    expect(result).toBe(false);
    expect(navigationCircuitBreaker.getStatus().tripped).toBe(true);
  });

  it("blocks further navigations once tripped", () => {
    // Trip via loop
    navigationCircuitBreaker.recordNavigation("/z", "t");
    navigationCircuitBreaker.recordNavigation("/z", "t");
    navigationCircuitBreaker.recordNavigation("/z", "t");
    expect(navigationCircuitBreaker.getStatus().tripped).toBe(true);

    const result = navigationCircuitBreaker.recordNavigation("/new", "test");
    expect(result).toBe(false);
  });

  it("drops events that fall outside the 3-second window", () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
      navigationCircuitBreaker.recordNavigation("/stale", "t");

      // Jump past WINDOW_MS (3000)
      vi.setSystemTime(new Date("2026-01-01T00:00:05Z"));
      navigationCircuitBreaker.recordNavigation("/fresh", "t");

      const status = navigationCircuitBreaker.getStatus();
      // Only the fresh event survives.
      expect(status.eventCount).toBe(1);
      expect(status.events[0].url).toBe("/fresh");
    } finally {
      vi.useRealTimers();
    }
  });

  it("reset clears history and untrips", () => {
    navigationCircuitBreaker.recordNavigation("/r", "t");
    navigationCircuitBreaker.recordNavigation("/r", "t");
    navigationCircuitBreaker.recordNavigation("/r", "t");
    expect(navigationCircuitBreaker.getStatus().tripped).toBe(true);

    navigationCircuitBreaker.reset();
    const status = navigationCircuitBreaker.getStatus();
    expect(status.tripped).toBe(false);
    expect(status.eventCount).toBe(0);
  });

  it("is exposed on window for debugging", () => {
    expect((window as any).navigationCircuitBreaker).toBe(
      navigationCircuitBreaker
    );
  });
});
