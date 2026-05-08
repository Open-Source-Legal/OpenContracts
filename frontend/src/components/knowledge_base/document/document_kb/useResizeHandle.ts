import { useCallback, useEffect, useState } from "react";
import { ChatPanelWidthMode } from "../../../annotator/context/UISettingsAtom";

interface UseResizeHandleParams {
  /** Returns the panel width as a percentage (0–100) at the moment of grab */
  getPanelWidthPercentage: () => number;
  /** Set the chat panel width mode (snaps when within `snapThresholdPct`) */
  setMode: (mode: ChatPanelWidthMode) => void;
  /** Set a custom width percentage (0–100) when not snapped */
  setCustomWidth: (width: number) => void;
}

interface UseResizeHandleReturn {
  /** Whether the user is currently dragging the resize handle */
  isDragging: boolean;
  /** Mouse-down handler to start a resize drag */
  handleResizeStart: (e: React.MouseEvent) => void;
}

/**
 * Drag-to-resize logic for the right panel. While dragging, the panel width
 * snaps to "quarter" / "half" / "full" presets if within `snapThresholdPct`,
 * otherwise it commits a custom width. Width is clamped between 15% and 95%.
 *
 * Mouse listeners are attached to `document` only while a drag is in flight
 * to avoid permanent global handlers.
 */
export function useResizeHandle({
  getPanelWidthPercentage,
  setMode,
  setCustomWidth,
}: UseResizeHandleParams): UseResizeHandleReturn {
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragStartWidth, setDragStartWidth] = useState(0);

  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      // Don't start resize if clicking on a button (e.g. minimize toggle that
      // sometimes lives on top of the handle).
      const target = e.target as HTMLElement;
      if (target.closest("button")) return;

      setIsDragging(true);
      setDragStartX(e.clientX);
      setDragStartWidth(getPanelWidthPercentage());
      e.preventDefault();
    },
    [getPanelWidthPercentage]
  );

  const handleResizeMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging) return;

      const deltaX = dragStartX - e.clientX;
      const windowWidth = window.innerWidth;
      const deltaPercentage = (deltaX / windowWidth) * 100;
      const newWidth = Math.max(
        15,
        Math.min(95, dragStartWidth + deltaPercentage)
      );

      const snapThresholdPct = 3;
      if (Math.abs(newWidth - 25) < snapThresholdPct) {
        setMode("quarter");
      } else if (Math.abs(newWidth - 50) < snapThresholdPct) {
        setMode("half");
      } else if (Math.abs(newWidth - 90) < snapThresholdPct) {
        setMode("full");
      } else {
        setCustomWidth(newWidth);
      }
    },
    [isDragging, dragStartX, dragStartWidth, setMode, setCustomWidth]
  );

  const handleResizeEnd = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    document.addEventListener("mousemove", handleResizeMove);
    document.addEventListener("mouseup", handleResizeEnd);
    return () => {
      document.removeEventListener("mousemove", handleResizeMove);
      document.removeEventListener("mouseup", handleResizeEnd);
    };
  }, [isDragging, handleResizeMove, handleResizeEnd]);

  return { isDragging, handleResizeStart };
}
