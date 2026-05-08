/**
 * Tests for useNetworkStatus hook.
 *
 * Tests visibility change detection, network status changes, and threshold behavior.
 *
 * Related to Issue #697 - Error on screen unlock
 */

import { renderHook, act } from "../../test-utils/renderHook";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useNetworkStatus } from "../useNetworkStatus";

describe("useNetworkStatus", () => {
  // Store original values
  let originalVisibilityState: PropertyDescriptor | undefined;
  let originalOnLine: PropertyDescriptor | undefined;

  beforeEach(() => {
    vi.useFakeTimers();

    // Store original property descriptors
    originalVisibilityState = Object.getOwnPropertyDescriptor(
      document,
      "visibilityState"
    );
    originalOnLine = Object.getOwnPropertyDescriptor(navigator, "onLine");

    // Set initial state
    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      writable: true,
      configurable: true,
    });
    Object.defineProperty(navigator, "onLine", {
      value: true,
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();

    // Restore original property descriptors
    if (originalVisibilityState) {
      Object.defineProperty(
        document,
        "visibilityState",
        originalVisibilityState
      );
    }
    if (originalOnLine) {
      Object.defineProperty(navigator, "onLine", originalOnLine);
    }
  });

  describe("initial state", () => {
    it("should return correct initial status", () => {
      const { result } = renderHook(() => useNetworkStatus());

      expect(result.current.status.isOnline).toBe(true);
      expect(result.current.status.isVisible).toBe(true);
      expect(result.current.status.justResumed).toBe(false);
    });

    it("should reflect offline state when navigator.onLine is false", () => {
      Object.defineProperty(navigator, "onLine", {
        value: false,
        writable: true,
        configurable: true,
      });

      const { result } = renderHook(() => useNetworkStatus());

      expect(result.current.status.isOnline).toBe(false);
    });

    it("should reflect hidden state when document is not visible", () => {
      Object.defineProperty(document, "visibilityState", {
        value: "hidden",
        writable: true,
        configurable: true,
      });

      const { result } = renderHook(() => useNetworkStatus());

      expect(result.current.status.isVisible).toBe(false);
    });
  });

  describe("visibility change handling", () => {
    it("should call onHide when page becomes hidden", () => {
      const onHide = vi.fn();
      renderHook(() => useNetworkStatus({ onHide }));

      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      expect(onHide).toHaveBeenCalledTimes(1);
    });

    it("should call onResume when page becomes visible after threshold", () => {
      const onResume = vi.fn();
      renderHook(() => useNetworkStatus({ onResume, resumeThreshold: 1000 }));

      // Hide the page
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      // Advance time past threshold
      act(() => {
        vi.advanceTimersByTime(1500);
      });

      // Show the page
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      expect(onResume).toHaveBeenCalledTimes(1);
    });

    it("should NOT call onResume when hidden duration is below threshold", () => {
      const onResume = vi.fn();
      renderHook(() => useNetworkStatus({ onResume, resumeThreshold: 1000 }));

      // Hide the page
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      // Advance time but stay below threshold
      act(() => {
        vi.advanceTimersByTime(500);
      });

      // Show the page
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      expect(onResume).not.toHaveBeenCalled();
    });

    it("should update isVisible status on visibility change", () => {
      const { result } = renderHook(() => useNetworkStatus());

      expect(result.current.status.isVisible).toBe(true);

      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      expect(result.current.status.isVisible).toBe(false);

      act(() => {
        vi.advanceTimersByTime(1500);
      });

      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      expect(result.current.status.isVisible).toBe(true);
    });

    it("should set justResumed to true temporarily after resume", async () => {
      const { result } = renderHook(() =>
        useNetworkStatus({ resumeThreshold: 1000 })
      );

      // Hide the page
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      // Advance time past threshold
      act(() => {
        vi.advanceTimersByTime(1500);
      });

      // Show the page
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      expect(result.current.status.justResumed).toBe(true);

      // Wait for justResumed to be cleared
      act(() => {
        vi.advanceTimersByTime(200);
      });

      expect(result.current.status.justResumed).toBe(false);
    });
  });

  describe("network status handling", () => {
    it("should call onOnline when network comes online", () => {
      const onOnline = vi.fn();
      renderHook(() => useNetworkStatus({ onOnline }));

      act(() => {
        window.dispatchEvent(new Event("online"));
      });

      expect(onOnline).toHaveBeenCalledTimes(1);
    });

    it("should call onOffline when network goes offline", () => {
      const onOffline = vi.fn();
      renderHook(() => useNetworkStatus({ onOffline }));

      act(() => {
        window.dispatchEvent(new Event("offline"));
      });

      expect(onOffline).toHaveBeenCalledTimes(1);
    });

    it("should update isOnline status on network change", () => {
      const { result } = renderHook(() => useNetworkStatus());

      expect(result.current.status.isOnline).toBe(true);

      act(() => {
        Object.defineProperty(navigator, "onLine", {
          value: false,
          writable: true,
          configurable: true,
        });
        window.dispatchEvent(new Event("offline"));
      });

      expect(result.current.status.isOnline).toBe(false);

      act(() => {
        Object.defineProperty(navigator, "onLine", {
          value: true,
          writable: true,
          configurable: true,
        });
        window.dispatchEvent(new Event("online"));
      });

      expect(result.current.status.isOnline).toBe(true);
    });
  });

  describe("enabled option", () => {
    it("should not set up listeners when disabled", () => {
      const onResume = vi.fn();
      const onOnline = vi.fn();

      renderHook(() =>
        useNetworkStatus({ onResume, onOnline, enabled: false })
      );

      // Hide then show page
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      act(() => {
        window.dispatchEvent(new Event("online"));
      });

      expect(onResume).not.toHaveBeenCalled();
      expect(onOnline).not.toHaveBeenCalled();
    });
  });

  describe("triggerResume", () => {
    it("should manually trigger onResume callback", () => {
      const onResume = vi.fn();
      const { result } = renderHook(() => useNetworkStatus({ onResume }));

      act(() => {
        result.current.triggerResume();
      });

      expect(onResume).toHaveBeenCalledTimes(1);
    });

    it("should set justResumed to true temporarily", () => {
      const { result } = renderHook(() => useNetworkStatus());

      act(() => {
        result.current.triggerResume();
      });

      expect(result.current.status.justResumed).toBe(true);

      act(() => {
        vi.advanceTimersByTime(200);
      });

      expect(result.current.status.justResumed).toBe(false);
    });
  });

  describe("cleanup", () => {
    it("should remove event listeners on unmount", () => {
      const removeEventListenerSpy = vi.spyOn(document, "removeEventListener");
      const windowRemoveEventListenerSpy = vi.spyOn(
        window,
        "removeEventListener"
      );

      const { unmount } = renderHook(() => useNetworkStatus());

      unmount();

      expect(removeEventListenerSpy).toHaveBeenCalledWith(
        "visibilitychange",
        expect.any(Function)
      );
      expect(windowRemoveEventListenerSpy).toHaveBeenCalledWith(
        "online",
        expect.any(Function)
      );
      expect(windowRemoveEventListenerSpy).toHaveBeenCalledWith(
        "offline",
        expect.any(Function)
      );

      removeEventListenerSpy.mockRestore();
      windowRemoveEventListenerSpy.mockRestore();
    });
  });

  describe("rapid visibility changes", () => {
    it("should handle rapid hide/show cycles correctly", () => {
      const onResume = vi.fn();
      const onHide = vi.fn();
      const { result } = renderHook(() =>
        useNetworkStatus({ onResume, onHide, resumeThreshold: 1000 })
      );

      // Simulate rapid screen lock/unlock/lock/unlock cycle
      // First hide
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(onHide).toHaveBeenCalledTimes(1);
      expect(result.current.status.isVisible).toBe(false);

      // Quick show (within threshold - should NOT trigger resume)
      act(() => {
        vi.advanceTimersByTime(200);
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(onResume).not.toHaveBeenCalled();
      expect(result.current.status.isVisible).toBe(true);

      // Second hide
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(onHide).toHaveBeenCalledTimes(2);

      // Quick show again (within threshold)
      act(() => {
        vi.advanceTimersByTime(300);
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(onResume).not.toHaveBeenCalled();

      // Third hide, then long delay (over threshold)
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(onHide).toHaveBeenCalledTimes(3);

      act(() => {
        vi.advanceTimersByTime(1500); // Over threshold
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      // NOW onResume should be called
      expect(onResume).toHaveBeenCalledTimes(1);
      expect(result.current.status.justResumed).toBe(true);
    });

    it("should properly clean up justResumed timeouts on rapid changes", () => {
      const { result } = renderHook(() =>
        useNetworkStatus({ resumeThreshold: 500 })
      );

      // First cycle - hide long enough to trigger resume
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      act(() => {
        vi.advanceTimersByTime(600);
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      expect(result.current.status.justResumed).toBe(true);

      // Immediately hide again before justResumed timeout clears
      act(() => {
        vi.advanceTimersByTime(50); // Less than JUST_RESUMED_CLEAR_DELAY (100ms)
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });

      // justResumed should be cleared when hiding
      expect(result.current.status.justResumed).toBe(false);
      expect(result.current.status.isVisible).toBe(false);

      // Wait past the original timeout - should not cause issues
      act(() => {
        vi.advanceTimersByTime(200);
      });

      // State should remain stable
      expect(result.current.status.isVisible).toBe(false);
    });

    it("should handle simultaneous visibility and network changes", () => {
      const onResume = vi.fn();
      const onOnline = vi.fn();
      const onOffline = vi.fn();

      renderHook(() =>
        useNetworkStatus({
          onResume,
          onOnline,
          onOffline,
          resumeThreshold: 1000,
        })
      );

      // Hide page and go offline simultaneously
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "hidden",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
        window.dispatchEvent(new Event("offline"));
      });

      expect(onOffline).toHaveBeenCalledTimes(1);

      // Wait past threshold
      act(() => {
        vi.advanceTimersByTime(1500);
      });

      // Come online and show page simultaneously
      act(() => {
        Object.defineProperty(document, "visibilityState", {
          value: "visible",
          writable: true,
          configurable: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
        window.dispatchEvent(new Event("online"));
      });

      expect(onResume).toHaveBeenCalledTimes(1);
      expect(onOnline).toHaveBeenCalledTimes(1);
    });
  });
});
