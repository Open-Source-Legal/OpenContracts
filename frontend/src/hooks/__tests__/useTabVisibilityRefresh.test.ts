import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { cleanup, renderHook } from "../../test-utils/renderHook";
import { useTabVisibilityRefresh } from "../useTabVisibilityRefresh";

describe("useTabVisibilityRefresh", () => {
  let originalVisibility: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalVisibility = Object.getOwnPropertyDescriptor(
      document,
      "visibilityState"
    );
    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    cleanup();
    if (originalVisibility) {
      Object.defineProperty(document, "visibilityState", originalVisibility);
    }
  });

  const fireVisibility = (state: "visible" | "hidden") => {
    Object.defineProperty(document, "visibilityState", {
      value: state,
      writable: true,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  };

  it("invokes each refresh fn when the page becomes visible", () => {
    const a = vi.fn().mockResolvedValue(undefined);
    const b = vi.fn().mockResolvedValue(undefined);

    renderHook(() => useTabVisibilityRefresh([a, b]));

    fireVisibility("visible");

    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });

  it("does not invoke refresh fns when the page goes hidden", () => {
    const fn = vi.fn();
    renderHook(() => useTabVisibilityRefresh([fn]));

    fireVisibility("hidden");

    expect(fn).not.toHaveBeenCalled();
  });

  it("logs promise rejections via console.error and does not propagate", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const failing = vi.fn().mockRejectedValue(new Error("boom"));
    renderHook(() => useTabVisibilityRefresh([failing]));

    fireVisibility("visible");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(failing).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining("refresh promise rejected"),
      expect.any(Error)
    );
    errorSpy.mockRestore();
  });

  it("logs synchronous exceptions via console.error and continues with the next fn", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const synchronousThrower = vi.fn(() => {
      throw new Error("sync boom");
    });
    const followup = vi.fn();
    renderHook(() => useTabVisibilityRefresh([synchronousThrower, followup]));

    fireVisibility("visible");

    expect(synchronousThrower).toHaveBeenCalledTimes(1);
    expect(followup).toHaveBeenCalledTimes(1);
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining("refresh threw synchronously"),
      expect.any(Error)
    );
    errorSpy.mockRestore();
  });

  it("removes the listener on unmount", () => {
    const fn = vi.fn();
    const { unmount } = renderHook(() => useTabVisibilityRefresh([fn]));

    unmount();
    fireVisibility("visible");

    expect(fn).not.toHaveBeenCalled();
  });

  it("supports synchronous refresh fns (non-Promise return)", () => {
    const sync = vi.fn(() => 42);
    renderHook(() => useTabVisibilityRefresh([sync]));

    fireVisibility("visible");

    expect(sync).toHaveBeenCalledTimes(1);
  });

  it("calls the latest refresh fns even when the caller passes inline arrays", () => {
    const first = vi.fn();
    const second = vi.fn();

    const { rerender } = renderHook(
      ({ fns }: { fns: Array<() => void> }) => useTabVisibilityRefresh(fns),
      { initialProps: { fns: [first] } }
    );

    rerender({ fns: [second] });
    fireVisibility("visible");

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});
