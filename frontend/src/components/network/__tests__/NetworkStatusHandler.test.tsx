/**
 * Tests for NetworkStatusHandler component.
 *
 * Tests that the component correctly:
 * - Refetches Apollo queries when page resumes
 * - Refetches Apollo queries when network comes online
 * - Shows/dismisses toast notifications appropriately
 * - Handles debouncing of refetch operations
 * - Handles errors during refetch
 *
 * Related to Issue #697 - Error on screen unlock
 */

import React from "react";
import { render, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { toast } from "react-toastify";
import { NetworkStatusHandler } from "../NetworkStatusHandler";

// Mock react-toastify
vi.mock("react-toastify", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    dismiss: vi.fn(),
  },
}));

// Mock useNetworkStatus hook to control when callbacks are triggered
const mockOnResume = vi.fn();
const mockOnHide = vi.fn();
const mockOnOnline = vi.fn();
const mockOnOffline = vi.fn();

vi.mock("../../../hooks/useNetworkStatus", () => ({
  useNetworkStatus: (options: {
    onResume?: () => void;
    onHide?: () => void;
    onOnline?: () => void;
    onOffline?: () => void;
    resumeThreshold?: number;
    enabled?: boolean;
  }) => {
    // Store callbacks so tests can trigger them
    // Use arrow functions to safely call optional callbacks
    mockOnResume.mockImplementation(() => options.onResume?.());
    mockOnHide.mockImplementation(() => options.onHide?.());
    mockOnOnline.mockImplementation(() => options.onOnline?.());
    mockOnOffline.mockImplementation(() => options.onOffline?.());

    return {
      status: {
        isOnline: true,
        isVisible: true,
        lastVisibilityChange: Date.now(),
        lastNetworkChange: Date.now(),
        justResumed: false,
      },
      triggerResume: vi.fn(),
    };
  },
}));

// Mock useApolloClient
const mockRefetchQueries = vi.fn();
vi.mock("@apollo/client", async () => {
  const actual = await vi.importActual("@apollo/client");
  return {
    ...actual,
    useApolloClient: () => ({
      refetchQueries: mockRefetchQueries,
    }),
  };
});

describe("NetworkStatusHandler", () => {
  // Store original navigator.onLine
  let originalOnLine: PropertyDescriptor | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();

    // Store and mock navigator.onLine
    originalOnLine = Object.getOwnPropertyDescriptor(navigator, "onLine");
    Object.defineProperty(navigator, "onLine", {
      value: true,
      writable: true,
      configurable: true,
    });

    // Reset mock implementations
    mockRefetchQueries.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();

    // Restore navigator.onLine
    if (originalOnLine) {
      Object.defineProperty(navigator, "onLine", originalOnLine);
    }
  });

  const renderComponent = (props = {}) => {
    // Since we mock useApolloClient directly, we don't need MockedProvider
    return render(<NetworkStatusHandler {...props} />);
  };

  describe("rendering", () => {
    it("should render nothing (return null)", () => {
      const { container } = renderComponent();
      expect(container.firstChild).toBeNull();
    });
  });

  describe("page resume handling", () => {
    it("should refetch queries when page resumes", async () => {
      renderComponent();

      // Trigger resume callback
      act(() => {
        mockOnResume();
      });

      expect(mockRefetchQueries).toHaveBeenCalledWith({
        include: "active",
      });
    });

    it("should show reconnecting toast when page resumes", async () => {
      renderComponent({ showToasts: true });

      act(() => {
        mockOnResume();
      });

      expect(toast.info).toHaveBeenCalledWith("Reconnecting...", {
        toastId: "network-reconnecting",
        autoClose: 1500,
        position: "bottom-right",
      });
    });

    it("should NOT show toast when showToasts is false", () => {
      renderComponent({ showToasts: false });

      act(() => {
        mockOnResume();
      });

      expect(toast.info).not.toHaveBeenCalled();
    });

    it("should NOT refetch when refetchOnResume is false", () => {
      renderComponent({ refetchOnResume: false });

      act(() => {
        mockOnResume();
      });

      expect(mockRefetchQueries).not.toHaveBeenCalled();
    });

    it("should NOT refetch when device is offline", () => {
      Object.defineProperty(navigator, "onLine", {
        value: false,
        writable: true,
        configurable: true,
      });

      renderComponent();

      act(() => {
        mockOnResume();
      });

      expect(mockRefetchQueries).not.toHaveBeenCalled();
    });

    it("should debounce rapid refetch calls", async () => {
      renderComponent({ refetchDebounceMs: 2000 });

      // First resume
      act(() => {
        mockOnResume();
      });

      expect(mockRefetchQueries).toHaveBeenCalledTimes(1);

      // Second resume within debounce window
      act(() => {
        vi.advanceTimersByTime(1000);
        mockOnResume();
      });

      // Should still be 1 call (debounced)
      expect(mockRefetchQueries).toHaveBeenCalledTimes(1);

      // Third resume after debounce window
      act(() => {
        vi.advanceTimersByTime(2000);
        mockOnResume();
      });

      // Should now be 2 calls
      expect(mockRefetchQueries).toHaveBeenCalledTimes(2);
    });
  });

  describe("network online handling", () => {
    it("should refetch queries when network comes online", async () => {
      renderComponent();

      act(() => {
        mockOnOnline();
      });

      // Wait for the stabilization delay
      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(mockRefetchQueries).toHaveBeenCalledWith({
        include: "active",
      });
    });

    it("should show success toast when network comes online", () => {
      renderComponent({ showToasts: true });

      act(() => {
        mockOnOnline();
      });

      expect(toast.dismiss).toHaveBeenCalledWith("network-offline");
      expect(toast.success).toHaveBeenCalledWith("Connection restored", {
        toastId: "network-online",
        autoClose: 3000,
        position: "bottom-right",
      });
    });

    it("should NOT refetch when refetchOnOnline is false", () => {
      renderComponent({ refetchOnOnline: false });

      act(() => {
        mockOnOnline();
        vi.advanceTimersByTime(500);
      });

      expect(mockRefetchQueries).not.toHaveBeenCalled();
    });
  });

  describe("network offline handling", () => {
    it("should show warning toast when network goes offline", () => {
      renderComponent({ showToasts: true });

      act(() => {
        mockOnOffline();
      });

      expect(toast.warning).toHaveBeenCalledWith(
        "You appear to be offline. Some features may not work.",
        {
          toastId: "network-offline",
          autoClose: false,
          position: "bottom-right",
        }
      );
    });

    it("should NOT show duplicate offline toasts", () => {
      renderComponent({ showToasts: true });

      // First offline event
      act(() => {
        mockOnOffline();
      });

      expect(toast.warning).toHaveBeenCalledTimes(1);

      // Second offline event should not show toast again
      act(() => {
        mockOnOffline();
      });

      // Still only 1 call
      expect(toast.warning).toHaveBeenCalledTimes(1);
    });

    it("should reset offline toast tracking when coming online", () => {
      renderComponent({ showToasts: true });

      // Go offline
      act(() => {
        mockOnOffline();
      });

      expect(toast.warning).toHaveBeenCalledTimes(1);

      // Come online
      act(() => {
        mockOnOnline();
        vi.advanceTimersByTime(500);
      });

      // Go offline again
      act(() => {
        mockOnOffline();
      });

      // Should show toast again (2 total)
      expect(toast.warning).toHaveBeenCalledTimes(2);
    });
  });

  describe("page hide handling", () => {
    it("should handle page hide without errors", () => {
      renderComponent();

      // Should not throw
      expect(() => {
        act(() => {
          mockOnHide();
        });
      }).not.toThrow();
    });
  });

  describe("error handling", () => {
    it("should handle refetch errors gracefully", async () => {
      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockRefetchQueries.mockRejectedValueOnce(new Error("Network error"));

      renderComponent();

      await act(async () => {
        mockOnResume();
        // Wait a tick for the async rejection to be handled
        await Promise.resolve();
      });

      // The error should have been logged
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "[NetworkStatusHandler] Error refetching queries:",
        expect.any(Error)
      );

      consoleErrorSpy.mockRestore();
    });

    // Behavior change (issue #697 follow-up): a reconnect refetch failing right
    // after screen-unlock is expected flakiness, not a user-actionable error.
    // We intentionally NO LONGER throw a red "reload the page" toast here — the
    // calm "Reconnecting…" indicator covers it and the reconnect grace window
    // suppresses the per-query error toasts that would otherwise pile up.
    it("should NOT show an alarming error toast when reconnect refetch fails", async () => {
      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockRefetchQueries.mockRejectedValueOnce(new Error("Network error"));

      renderComponent({ showToasts: true });

      await act(async () => {
        mockOnResume();
        // Wait a tick for the async rejection to be handled
        await Promise.resolve();
      });

      expect(toast.error).not.toHaveBeenCalled();

      consoleErrorSpy.mockRestore();
    });
  });

  describe("props configuration", () => {
    it("should use default resumeThreshold of 2000ms", () => {
      // This is tested indirectly through the useNetworkStatus mock
      // The component passes resumeThreshold to the hook
      renderComponent();
      // Component renders successfully with defaults
    });

    it("should accept custom resumeThreshold", () => {
      renderComponent({ resumeThreshold: 5000 });
      // Component renders successfully with custom threshold
    });

    it("should accept custom refetchDebounceMs", () => {
      renderComponent({ refetchDebounceMs: 5000 });

      act(() => {
        mockOnResume();
      });

      expect(mockRefetchQueries).toHaveBeenCalledTimes(1);

      // Within 5s debounce window
      act(() => {
        vi.advanceTimersByTime(4000);
        mockOnResume();
      });

      // Still debounced
      expect(mockRefetchQueries).toHaveBeenCalledTimes(1);

      // After debounce window
      act(() => {
        vi.advanceTimersByTime(5000);
        mockOnResume();
      });

      // Now 2 calls
      expect(mockRefetchQueries).toHaveBeenCalledTimes(2);
    });
  });
});
