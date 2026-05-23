import { useState, useCallback, useRef, useEffect } from "react";
import { routingLogger } from "../../../../utils/routingLogger";
import {
  ZOOM_MIN,
  ZOOM_MAX,
} from "../../../../assets/configurations/constants";

/** Calculate distance between two touch points (pure helper, no closure deps). */
function getTouchDistance(touches: TouchList): number {
  if (touches.length < 2) return 0;
  const dx = touches[0].clientX - touches[1].clientX;
  const dy = touches[0].clientY - touches[1].clientY;
  return Math.sqrt(dx * dx + dy * dy);
}

interface UseZoomManagerParams {
  zoomLevel: number;
  setZoomLevel: (zoom: number) => void;
  activeLayer: "knowledge" | "document";
  showRightPanel: boolean;
  isMobile: boolean;
  mode: string;
  customWidth: number | undefined;
  getPanelWidthPercentage: () => number;
}

interface UseZoomManagerReturn {
  /** Whether the zoom indicator overlay is visible */
  showZoomIndicator: boolean;
  /** Whether auto-zoom on sidebar open/close is enabled */
  autoZoomEnabled: boolean;
  setAutoZoomEnabled: (enabled: boolean) => void;
  /** Show zoom level feedback overlay temporarily */
  showZoomFeedback: () => void;
  /** Wheel zoom handler (Ctrl/Cmd + scroll) */
  handleWheelZoom: (event: WheelEvent) => void;
  /** Keyboard zoom handler (Ctrl/Cmd + +/-/0) */
  handleKeyboardZoom: (event: KeyboardEvent) => void;
  /** Touch start handler for pinch zoom */
  handleTouchStart: (event: TouchEvent) => void;
  /** Touch move handler for pinch zoom */
  handleTouchMove: (event: TouchEvent) => void;
  /** Touch end handler for pinch zoom */
  handleTouchEnd: (event: TouchEvent) => void;
}

/**
 * Custom hook that encapsulates all zoom-related state and logic for the
 * DocumentKnowledgeBase component. This includes:
 * - Zoom indicator feedback overlay
 * - Keyboard zoom (Ctrl+/-/0)
 * - Mouse wheel zoom (Ctrl+scroll)
 * - Pinch-to-zoom on mobile
 * - Auto-zoom adjustment when sidebar opens/closes
 */
export function useZoomManager({
  zoomLevel,
  setZoomLevel,
  activeLayer,
  showRightPanel,
  isMobile,
  mode,
  customWidth,
  getPanelWidthPercentage,
}: UseZoomManagerParams): UseZoomManagerReturn {
  // Zoom indicator state
  const [showZoomIndicator, setShowZoomIndicator] = useState(false);
  const zoomIndicatorTimer = useRef<NodeJS.Timeout>();

  // Ref to always access the latest zoomLevel without stale closures
  const zoomLevelRef = useRef<number>(zoomLevel);
  zoomLevelRef.current = zoomLevel;

  // Auto-zoom state
  const [autoZoomEnabled, setAutoZoomEnabled] = useState<boolean>(true);
  const baseZoomRef = useRef<number>(zoomLevel);
  const isAdjustingZoomRef = useRef<boolean>(false);
  const justToggledAutoZoomRef = useRef<boolean>(false);

  // Pinch zoom state
  const [isPinching, setIsPinching] = useState(false);
  const [initialPinchDistance, setInitialPinchDistance] = useState<
    number | null
  >(null);
  const [lastPinchZoom, setLastPinchZoom] = useState<number | null>(null);

  // Track previous auto-zoom state to detect when user toggles it
  const prevAutoZoomEnabledRef = useRef<boolean>(autoZoomEnabled);

  // Show zoom indicator feedback
  const showZoomFeedback = useCallback(() => {
    setShowZoomIndicator(true);

    // Clear existing timer
    if (zoomIndicatorTimer.current) {
      clearTimeout(zoomIndicatorTimer.current);
    }

    // Hide after 1.5 seconds
    zoomIndicatorTimer.current = setTimeout(() => {
      setShowZoomIndicator(false);
    }, 1500);
  }, []);

  // Browser zoom event handlers
  // These use zoomLevelRef to read the latest value without re-creating the
  // callback (and re-attaching the event listener) on every zoom change.
  const handleWheelZoom = useCallback(
    (event: WheelEvent) => {
      // Only handle if in document layer and Ctrl/Cmd is pressed
      if (activeLayer !== "document" || (!event.ctrlKey && !event.metaKey)) {
        return;
      }

      // Prevent default browser zoom
      event.preventDefault();

      // Calculate zoom delta (normalize across browsers)
      const delta = event.deltaY > 0 ? -0.1 : 0.1;
      setZoomLevel(
        Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoomLevelRef.current + delta))
      );
      showZoomFeedback();
    },
    [activeLayer, setZoomLevel, showZoomFeedback]
  );

  const handleKeyboardZoom = useCallback(
    (event: KeyboardEvent) => {
      // Only handle if in document layer
      if (activeLayer !== "document") return;

      // Check for Ctrl/Cmd modifier
      if (!event.ctrlKey && !event.metaKey) return;

      let handled = false;

      switch (event.key) {
        case "+":
        case "=": // Handle both + and = (same key without shift)
          event.preventDefault();
          setZoomLevel(Math.min(zoomLevelRef.current + 0.1, ZOOM_MAX));
          handled = true;
          break;
        case "-":
        case "_": // Handle both - and _ (same key without shift)
          event.preventDefault();
          setZoomLevel(Math.max(zoomLevelRef.current - 0.1, ZOOM_MIN));
          handled = true;
          break;
        case "0":
          event.preventDefault();
          setZoomLevel(1); // Reset to 100%
          handled = true;
          break;
      }

      if (handled) {
        showZoomFeedback();
      }
    },
    [activeLayer, setZoomLevel, showZoomFeedback]
  );

  // Handle touch start for pinch zoom
  const handleTouchStart = useCallback(
    (event: TouchEvent) => {
      // Only handle if in document layer and using two fingers
      if (activeLayer !== "document" || event.touches.length !== 2) {
        return;
      }

      // Initialize pinch zoom
      const distance = getTouchDistance(event.touches);
      setIsPinching(true);
      setInitialPinchDistance(distance);
      setLastPinchZoom(zoomLevel);

      // Prevent default to avoid scrolling
      event.preventDefault();
    },
    [activeLayer, zoomLevel]
  );

  // Handle touch move for pinch zoom
  const handleTouchMove = useCallback(
    (event: TouchEvent) => {
      // Only handle if we're pinching with two fingers
      if (
        !isPinching ||
        event.touches.length !== 2 ||
        !initialPinchDistance ||
        lastPinchZoom === null
      ) {
        return;
      }

      // Calculate new zoom based on pinch distance
      const currentDistance = getTouchDistance(event.touches);
      const scale = currentDistance / initialPinchDistance;

      // Apply zoom with limits
      const newZoom = Math.max(
        ZOOM_MIN,
        Math.min(ZOOM_MAX, lastPinchZoom * scale)
      );
      setZoomLevel(newZoom);

      // Show zoom feedback
      showZoomFeedback();

      // Prevent default to avoid scrolling
      event.preventDefault();
    },
    [
      isPinching,
      initialPinchDistance,
      lastPinchZoom,
      setZoomLevel,
      showZoomFeedback,
    ]
  );

  // Handle touch end for pinch zoom
  const handleTouchEnd = useCallback((event: TouchEvent) => {
    // Reset pinch state when touches end
    if (event.touches.length < 2) {
      setIsPinching(false);
      setInitialPinchDistance(null);
      setLastPinchZoom(null);
    }
  }, []);

  // When auto-zoom is toggled ON, capture current zoom as the new base
  useEffect(() => {
    const wasDisabled = !prevAutoZoomEnabledRef.current;
    const isNowEnabled = autoZoomEnabled;

    if (wasDisabled && isNowEnabled) {
      // User just toggled auto-zoom from OFF to ON
      // Capture current zoom as the new base, don't adjust yet
      baseZoomRef.current = zoomLevel;
      justToggledAutoZoomRef.current = true;
      routingLogger.debug(
        "Auto-zoom toggled ON - setting base zoom to current:",
        zoomLevel
      );
    }

    prevAutoZoomEnabledRef.current = autoZoomEnabled;
  }, [autoZoomEnabled, zoomLevel]);

  // Automatically adjust zoom level when sidebar opens/closes to maintain proportional document width
  useEffect(() => {
    // Skip if auto-zoom is disabled
    if (!autoZoomEnabled) {
      return;
    }

    if (isMobile || activeLayer !== "document") {
      return;
    }

    // If user just toggled auto-zoom ON, skip this adjustment cycle
    if (justToggledAutoZoomRef.current) {
      justToggledAutoZoomRef.current = false;
      return;
    }

    // If we're currently auto-adjusting, skip to prevent loops
    if (isAdjustingZoomRef.current) {
      return;
    }

    const panelWidth = getPanelWidthPercentage();

    if (showRightPanel) {
      // Sidebar just opened or resized
      // If we don't have a base zoom yet, store current zoom
      if (baseZoomRef.current === zoomLevel || !baseZoomRef.current) {
        baseZoomRef.current = zoomLevel;
      }

      // Calculate adjusted zoom: reduce proportionally to viewport shrinkage
      const viewportReduction = (100 - panelWidth) / 100;
      const adjustedZoom = baseZoomRef.current * viewportReduction;

      // Clamp to valid zoom range
      const clampedZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, adjustedZoom));

      // Only update if there's a meaningful difference
      if (Math.abs(zoomLevel - clampedZoom) > 0.01) {
        isAdjustingZoomRef.current = true;
        setZoomLevel(clampedZoom);
        // Reset flag after state update completes
        setTimeout(() => {
          isAdjustingZoomRef.current = false;
        }, 0);
      }
    } else {
      // Sidebar closed - restore base zoom
      if (
        baseZoomRef.current &&
        Math.abs(zoomLevel - baseZoomRef.current) > 0.01
      ) {
        isAdjustingZoomRef.current = true;
        setZoomLevel(baseZoomRef.current);
        // Reset flag after state update completes
        setTimeout(() => {
          isAdjustingZoomRef.current = false;
        }, 0);
      }
    }
  }, [
    autoZoomEnabled,
    showRightPanel,
    mode,
    customWidth,
    isMobile,
    activeLayer,
    // NOTE: Do NOT include zoomLevel here - it causes auto-zoom to override manual zoom changes
    setZoomLevel,
    getPanelWidthPercentage,
  ]);

  // When user manually zooms while sidebar is open, update base zoom for proper restoration
  useEffect(() => {
    // Only track manual zoom changes if auto-zoom is enabled
    if (!autoZoomEnabled) {
      return;
    }

    if (
      !isMobile &&
      showRightPanel &&
      activeLayer === "document" &&
      !isAdjustingZoomRef.current
    ) {
      // User manually changed zoom while sidebar is open
      // Back-calculate what the base zoom should be
      const panelWidth = getPanelWidthPercentage();
      const viewportReduction = (100 - panelWidth) / 100;
      const backCalculatedBase = zoomLevel / viewportReduction;

      // Update base zoom so when sidebar closes, it restores to the right level
      baseZoomRef.current = Math.max(
        ZOOM_MIN,
        Math.min(ZOOM_MAX, backCalculatedBase)
      );
    } else if (!showRightPanel && !isAdjustingZoomRef.current) {
      // Sidebar is closed, keep baseZoom in sync with current zoom
      baseZoomRef.current = zoomLevel;
    }
  }, [
    autoZoomEnabled,
    zoomLevel,
    showRightPanel,
    isMobile,
    activeLayer,
    mode,
    customWidth,
    getPanelWidthPercentage,
  ]);

  // Browser zoom event handling (attach/detach listeners)
  useEffect(() => {
    // Only attach listeners if we're in document view
    if (activeLayer !== "document") return;

    // Add wheel listener with passive: false to allow preventDefault
    document.addEventListener("wheel", handleWheelZoom, { passive: false });
    document.addEventListener("keydown", handleKeyboardZoom);

    // Add touch listeners for pinch zoom with passive: false
    document.addEventListener("touchstart", handleTouchStart, {
      passive: false,
    });
    document.addEventListener("touchmove", handleTouchMove, { passive: false });
    document.addEventListener("touchend", handleTouchEnd, { passive: false });

    return () => {
      document.removeEventListener("wheel", handleWheelZoom);
      document.removeEventListener("keydown", handleKeyboardZoom);
      document.removeEventListener("touchstart", handleTouchStart);
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleTouchEnd);
    };
  }, [
    activeLayer,
    handleWheelZoom,
    handleKeyboardZoom,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  ]);

  // Cleanup zoom indicator timer on unmount
  useEffect(() => {
    return () => {
      if (zoomIndicatorTimer.current) {
        clearTimeout(zoomIndicatorTimer.current);
      }
    };
  }, []);

  return {
    showZoomIndicator,
    autoZoomEnabled,
    setAutoZoomEnabled,
    showZoomFeedback,
    handleWheelZoom,
    handleKeyboardZoom,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  };
}
