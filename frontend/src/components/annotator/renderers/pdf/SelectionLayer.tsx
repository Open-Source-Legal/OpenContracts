import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  BoundingBox,
  PermissionTypes,
  SinglePageAnnotationJson,
  TokenId,
} from "../../../types";

import { normalizeBounds } from "../../../../utils/transform";
import { PDFPageInfo } from "../../types/pdf";
import { AnnotationLabelType } from "../../../../types/graphql-api";
import { ServerTokenAnnotation } from "../../types/annotations";
import { SelectionBoundary } from "../../display/components/SelectionBoundary";
import { SelectionTokenGroup } from "../../display/components/SelectionTokenGroup";
import { useCorpusState } from "../../context/CorpusAtom";
import { useAnnotationSelection } from "../../context/UISettingsAtom";
import { useAtom, useAtomValue } from "jotai";
import { isCreatingAnnotationAtom } from "../../context/UISettingsAtom";
import { Copy, Tag, X, AlertCircle, Settings, Link } from "lucide-react";
import {
  SelectionActionMenu,
  ActionMenuItem,
  MenuDivider,
  ShortcutHint,
  HelpMessage,
  HelpText,
} from "../../components/SelectionActionMenu";
import { scrollContainerRefAtom } from "../../context/DocumentAtom";
import { useLocation } from "react-router-dom";
import {
  encodeTextBlock,
  textBlockFromTokensByPage,
} from "../../../../utils/textBlockEncoding";
import { clampMenuPosition } from "../../../../utils/layout";

interface SelectionLayerProps {
  pageInfo: PDFPageInfo;
  read_only: boolean;
  activeSpanLabel: AnnotationLabelType | null;
  createAnnotation: (annotation: ServerTokenAnnotation) => void;
  pageNumber: number;
}

const SelectionLayer = ({
  pageInfo,
  read_only,
  activeSpanLabel,
  createAnnotation,
  pageNumber,
}: SelectionLayerProps) => {
  const location = useLocation();
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useAtomValue(scrollContainerRefAtom);
  const {
    canUpdateCorpus,
    myPermissions,
    selectedCorpus,
    humanSpanLabels,
    humanTokenLabels,
  } = useCorpusState();

  const { setSelectedAnnotations } = useAnnotationSelection();
  const [, setIsCreatingAnnotation] = useAtom(isCreatingAnnotationAtom);
  const [localPageSelection, setLocalPageSelection] = useState<
    { pageNumber: number; bounds: BoundingBox } | undefined
  >();
  const [multiSelections, setMultiSelections] = useState<{
    [key: number]: BoundingBox[];
  }>({});

  // New states for selection action menu
  const [showActionMenu, setShowActionMenu] = useState(false);
  const [actionMenuPosition, setActionMenuPosition] = useState({ x: 0, y: 0 });
  const [pendingSelections, setPendingSelections] = useState<{
    [key: number]: BoundingBox[];
  }>({});

  // Long press detection for mobile
  const [longPressTimer, setLongPressTimer] = useState<NodeJS.Timeout | null>(
    null
  );
  const [isLongPressActive, setIsLongPressActive] = useState(false);
  const [touchStartPos, setTouchStartPos] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const LONG_PRESS_DURATION = 500; // 500ms for long press
  const TOUCH_MOVE_THRESHOLD = 10; // pixels of movement to cancel long press

  // Prevent new selection immediately after menu interaction
  const lastMenuInteractionTime = useRef<number>(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const MENU_INTERACTION_COOLDOWN = 300; // 300ms cooldown after menu interaction

  // Check if corpus has labelset
  const hasLabelset = Boolean(selectedCorpus?.labelSet);
  const hasLabels = humanTokenLabels.length > 0 || humanSpanLabels.length > 0;

  /**
   * Handles the creation of a multi-page annotation.
   *
   * @param selections - The current multi-selections.
   */
  const handleCreateMultiPageAnnotation = useCallback(
    async (selections: { [key: number]: BoundingBox[] }) => {
      if (
        !activeSpanLabel ||
        !selections ||
        Object.keys(selections).length === 0
      ) {
        return;
      }

      // Create annotation from multi-selections
      const pages = Object.keys(selections).map(Number);

      // Convert bounds to proper SinglePageAnnotationJson format
      const annotations: Record<number, SinglePageAnnotationJson> = {};
      let combinedRawText = "";

      for (const pageNum of pages) {
        const pageAnnotation = pageInfo.getPageAnnotationJson(
          selections[pageNum]
        );
        if (pageAnnotation) {
          annotations[pageNum] = pageAnnotation;
          combinedRawText += " " + pageAnnotation.rawText;
        }
      }

      // Create annotation object
      const annotation = new ServerTokenAnnotation(
        pages[0], // First page as the anchor
        activeSpanLabel,
        combinedRawText.trim(),
        false,
        annotations,
        [],
        false,
        false,
        false
      );

      await createAnnotation(annotation);
      setMultiSelections({});
    },
    [activeSpanLabel, createAnnotation, pageInfo]
  );

  /**
   * Handles copying selected text to clipboard.
   */
  const handleCopyText = useCallback(() => {
    const selections = pendingSelections;
    const pages = Object.keys(selections)
      .map(Number)
      .sort((a, b) => a - b);
    let combinedText = "";

    for (const pageNum of pages) {
      const pageAnnotation = pageInfo.getPageAnnotationJson(
        selections[pageNum]
      );
      if (pageAnnotation) {
        combinedText += pageAnnotation.rawText + " ";
      }
    }

    if (combinedText.trim()) {
      navigator.clipboard.writeText(combinedText.trim()).catch(() => {});
    }

    // Mark menu interaction time
    lastMenuInteractionTime.current = Date.now();

    // Clear states
    setShowActionMenu(false);
    setPendingSelections({});
    setMultiSelections({});
  }, [pendingSelections, pageInfo]);

  /**
   * Handles copying a deep link to the selected text block.
   *
   * Note: pageInfo.getPageAnnotationJson uses this page's token list to
   * resolve bounding boxes.  This is safe because each SelectionLayer
   * instance only accumulates selections for its own page — cross-page
   * selections are handled by separate SelectionLayer instances.
   */
  const handleCopyLink = useCallback(() => {
    const selections = pendingSelections;
    const pages = Object.keys(selections)
      .map(Number)
      .sort((a, b) => a - b);

    // Collect token IDs across selected pages.
    // Note: pendingSelections only contains data for this SelectionLayer's
    // page (each page gets its own SelectionLayer instance), so the `pages`
    // array always has exactly one entry.  The loop is kept for structural
    // consistency with handleCopyText and handleCreateMultiPageAnnotation.
    const tokensByPage: Record<number, TokenId[]> = {};
    for (const pageNum of pages) {
      const pageAnnotation = pageInfo.getPageAnnotationJson(
        selections[pageNum]
      );
      if (pageAnnotation && pageAnnotation.tokensJsons.length > 0) {
        tokensByPage[pageNum] = pageAnnotation.tokensJsons;
      }
    }

    if (Object.keys(tokensByPage).length > 0) {
      const block = textBlockFromTokensByPage(tokensByPage);
      const encoded = encodeTextBlock(block);
      const params = new URLSearchParams(location.search);
      params.set("tb", encoded);
      const url = `${window.location.origin}${
        location.pathname
      }?${params.toString()}`;
      navigator.clipboard.writeText(url).catch(() => {});
    }

    lastMenuInteractionTime.current = Date.now();
    setShowActionMenu(false);
    setPendingSelections({});
    setMultiSelections({});
  }, [pendingSelections, pageInfo, location]);

  /**
   * Handles applying the current label to create an annotation.
   */
  const handleApplyLabel = useCallback(() => {
    if (activeSpanLabel) {
      handleCreateMultiPageAnnotation(pendingSelections);
    }

    // Mark menu interaction time
    lastMenuInteractionTime.current = Date.now();

    setShowActionMenu(false);
    setPendingSelections({});
  }, [activeSpanLabel, pendingSelections, handleCreateMultiPageAnnotation]);

  /**
   * Handles canceling the selection without any action.
   */
  const handleCancel = useCallback(() => {
    // Mark menu interaction time
    lastMenuInteractionTime.current = Date.now();

    setShowActionMenu(false);
    setPendingSelections({});
    setMultiSelections({});
  }, []);

  /**
   * Handles the mouse up event to finalize the selection.
   */
  const handleMouseUp = useCallback(
    (event: React.MouseEvent<HTMLDivElement, MouseEvent>) => {
      if (localPageSelection) {
        const pageNum = pageNumber;

        setMultiSelections((prev) => {
          const updatedSelections = {
            ...prev,
            [pageNum]: [...(prev[pageNum] || []), localPageSelection.bounds],
          };
          setLocalPageSelection(undefined);
          setIsCreatingAnnotation(false); // Reset creating annotation state

          if (!event.shiftKey) {
            // Instead of immediately creating annotation, show action menu
            setPendingSelections(updatedSelections);
            const menuPos = clampMenuPosition(event.clientX, event.clientY);
            setActionMenuPosition(menuPos);
            setShowActionMenu(true);
          }

          return updatedSelections;
        });
      }
    },
    [localPageSelection, pageNumber, setIsCreatingAnnotation]
  );

  /**
   * Handles the mouse down event to start the selection.
   */
  const handleMouseDown = useCallback(
    (event: React.MouseEvent<HTMLDivElement, MouseEvent>) => {
      if (containerRef.current === null) {
        throw new Error("No Container");
      }

      // Don't start selection if menu is visible or in cooldown
      if (showActionMenu) {
        return;
      }

      const timeSinceMenuInteraction =
        Date.now() - lastMenuInteractionTime.current;
      if (timeSinceMenuInteraction < MENU_INTERACTION_COOLDOWN) {
        return;
      }

      // Allow selection for copying even in read-only mode
      if (!localPageSelection && event.buttons === 1) {
        setSelectedAnnotations([]); // Clear any selected annotations
        // Only set creating annotation state if we can actually create annotations
        if (!read_only && canUpdateCorpus) {
          setIsCreatingAnnotation(true);
        }
        const canvasElement = containerRef.current
          .previousSibling as HTMLCanvasElement;
        if (!canvasElement) return;

        const canvasBounds = canvasElement.getBoundingClientRect();
        const left = event.clientX - canvasBounds.left;
        const top = event.clientY - canvasBounds.top;

        setLocalPageSelection({
          pageNumber: pageNumber,
          bounds: {
            left,
            top,
            right: left,
            bottom: top,
          },
        });
      }
    },
    [
      containerRef,
      read_only,
      canUpdateCorpus,
      localPageSelection,
      pageNumber,
      pageInfo,
      setSelectedAnnotations,
      setIsCreatingAnnotation,
      showActionMenu,
    ]
  );

  /**
   * Handles touch start for mobile long press detection
   */
  const handleTouchStart = useCallback(
    (event: React.TouchEvent<HTMLDivElement>) => {
      if (containerRef.current === null) {
        throw new Error("No Container");
      }

      // Don't start a new selection if the action menu is visible
      if (showActionMenu) {
        return;
      }

      // Check if we're in the cooldown period after a menu interaction
      const timeSinceMenuInteraction =
        Date.now() - lastMenuInteractionTime.current;
      if (timeSinceMenuInteraction < MENU_INTERACTION_COOLDOWN) {
        return;
      }

      // Check if touch target is within the action menu
      const target = event.target as HTMLElement;
      if (menuRef.current && menuRef.current.contains(target)) {
        return;
      }

      // Only proceed if we're not already selecting
      if (!localPageSelection && event.touches.length === 1) {
        const touch = event.touches[0];

        // Store touch start position
        setTouchStartPos({ x: touch.clientX, y: touch.clientY });

        // Start long press timer
        const timer = setTimeout(() => {
          // Vibrate if supported (haptic feedback)
          if (navigator.vibrate) {
            navigator.vibrate(50);
          }

          setIsLongPressActive(true);
          setSelectedAnnotations([]); // Clear any selected annotations

          // Only set creating annotation state if we can actually create annotations
          if (!read_only && canUpdateCorpus) {
            setIsCreatingAnnotation(true);
          }

          const canvasElement = containerRef.current!
            .previousSibling as HTMLCanvasElement;
          if (!canvasElement) return;

          const canvasBounds = canvasElement.getBoundingClientRect();
          const left = touch.clientX - canvasBounds.left;
          const top = touch.clientY - canvasBounds.top;

          setLocalPageSelection({
            pageNumber: pageNumber,
            bounds: {
              left,
              top,
              right: left,
              bottom: top,
            },
          });
        }, LONG_PRESS_DURATION);

        setLongPressTimer(timer);
      }
    },
    [
      containerRef,
      read_only,
      canUpdateCorpus,
      localPageSelection,
      pageNumber,
      setSelectedAnnotations,
      setIsCreatingAnnotation,
      showActionMenu,
    ]
  );

  /**
   * Handles touch move - cancels long press if moved too much, or updates selection if active
   */
  const handleTouchMove = useCallback(
    (event: React.TouchEvent<HTMLDivElement>) => {
      if (event.touches.length !== 1) return;

      const touch = event.touches[0];

      // If long press hasn't activated yet, check for movement threshold
      if (longPressTimer && touchStartPos && !isLongPressActive) {
        const dx = touch.clientX - touchStartPos.x;
        const dy = touch.clientY - touchStartPos.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance > TOUCH_MOVE_THRESHOLD) {
          // Cancel long press if moved too much
          clearTimeout(longPressTimer);
          setLongPressTimer(null);
          setTouchStartPos(null);
        }
      }

      // If long press is active and we have a selection, update it
      if (isLongPressActive && localPageSelection && containerRef.current) {
        // Prevent default touch behavior (scrolling/panning) during selection
        event.preventDefault();
        event.stopPropagation();

        const canvasElement = containerRef.current
          .previousSibling as HTMLCanvasElement;
        if (!canvasElement) return;

        const canvasBounds = canvasElement.getBoundingClientRect();
        const right = touch.clientX - canvasBounds.left;
        const bottom = touch.clientY - canvasBounds.top;

        if (localPageSelection.pageNumber === pageNumber) {
          setLocalPageSelection({
            pageNumber: pageNumber,
            bounds: {
              ...localPageSelection.bounds,
              right,
              bottom,
            },
          });
        }
      }
    },
    [
      longPressTimer,
      touchStartPos,
      isLongPressActive,
      localPageSelection,
      containerRef,
      pageNumber,
    ]
  );

  /**
   * Handles touch end - finalize selection if active
   */
  const handleTouchEnd = useCallback(
    (event: React.TouchEvent<HTMLDivElement>) => {
      // Clear long press timer if still running
      if (longPressTimer) {
        clearTimeout(longPressTimer);
        setLongPressTimer(null);
      }

      // Reset touch start position
      setTouchStartPos(null);

      // If long press was active and we have a selection, finalize it
      if (isLongPressActive && localPageSelection) {
        const pageNum = pageNumber;

        setMultiSelections((prev) => {
          const updatedSelections = {
            ...prev,
            [pageNum]: [...(prev[pageNum] || []), localPageSelection.bounds],
          };
          setLocalPageSelection(undefined);
          setIsCreatingAnnotation(false);
          setIsLongPressActive(false);

          // Show action menu
          setPendingSelections(updatedSelections);
          // Use last touch position for menu
          const touch = event.changedTouches[0];
          const menuPos = clampMenuPosition(touch.clientX, touch.clientY);
          setActionMenuPosition(menuPos);
          setShowActionMenu(true);

          return updatedSelections;
        });
      } else {
        setIsLongPressActive(false);
      }
    },
    [
      longPressTimer,
      isLongPressActive,
      localPageSelection,
      pageNumber,
      setIsCreatingAnnotation,
    ]
  );

  /**
   * Handles the mouse move event to update the selection.
   */
  const handleMouseMove = useCallback(
    (event: React.MouseEvent<HTMLDivElement, MouseEvent>) => {
      if (containerRef.current === null) {
        throw new Error("No Container");
      }
      const canvasElement = containerRef.current
        .previousSibling as HTMLCanvasElement;
      if (!canvasElement) return;

      const canvasBounds = canvasElement.getBoundingClientRect();
      const right = event.clientX - canvasBounds.left;
      const bottom = event.clientY - canvasBounds.top;

      if (localPageSelection && localPageSelection.pageNumber === pageNumber) {
        setLocalPageSelection({
          pageNumber: pageNumber,
          bounds: {
            ...localPageSelection.bounds,
            right,
            bottom,
          },
        });
      }
    },
    [containerRef, localPageSelection, pageNumber, pageInfo]
  );

  /**
   * Converts bounding box selections to JSX elements.
   */
  const convertBoundsToSelections = useCallback(
    (
      selection: BoundingBox,
      activeLabel: AnnotationLabelType | null
    ): JSX.Element => {
      const annotation = activeLabel
        ? pageInfo.getAnnotationForBounds(
            normalizeBounds(selection),
            activeLabel
          )
        : null;

      const tokens = annotation && annotation.tokens ? annotation.tokens : null;

      // Random UUID is intentional — this is a transient in-progress selection,
      // not a persisted annotation, so a stable ID is unnecessary.
      return (
        <>
          <SelectionBoundary
            id={crypto.randomUUID()}
            showBoundingBox
            hidden={false}
            color={activeLabel?.color || "#0066cc"}
            bounds={selection}
            selected={false}
          />
          <SelectionTokenGroup pageInfo={pageInfo} tokens={tokens} />
        </>
      );
    },
    [pageInfo]
  );

  const pageQueuedSelections = multiSelections[pageNumber]
    ? multiSelections[pageNumber]
    : [];

  // Handle ESC key during selection
  useEffect(() => {
    const handleEscapeDuringSelection = (event: KeyboardEvent) => {
      if (event.key === "Escape" && localPageSelection) {
        event.preventDefault();
        event.stopPropagation();
        setLocalPageSelection(undefined);
        setIsCreatingAnnotation(false);
        setMultiSelections({});
        setIsLongPressActive(false);
        if (longPressTimer) {
          clearTimeout(longPressTimer);
          setLongPressTimer(null);
        }
      }
    };

    if (localPageSelection) {
      document.addEventListener("keydown", handleEscapeDuringSelection);
      return () => {
        document.removeEventListener("keydown", handleEscapeDuringSelection);
      };
    }
  }, [localPageSelection, setIsCreatingAnnotation, longPressTimer]);

  // Cleanup long press timer on unmount
  useEffect(() => {
    return () => {
      if (longPressTimer) {
        clearTimeout(longPressTimer);
      }
    };
  }, [longPressTimer]);

  // Disable scrolling on the scroll container when selection is active
  useEffect(() => {
    if (!scrollContainerRef?.current) return;

    if (isLongPressActive) {
      const container = scrollContainerRef.current;
      // Store original values
      const originalOverflow = container.style.overflow;
      const originalTouchAction = container.style.touchAction;

      // Disable scrolling
      container.style.overflow = "hidden";
      container.style.touchAction = "none";

      return () => {
        // Restore original values
        container.style.overflow = originalOverflow;
        container.style.touchAction = originalTouchAction;
      };
    }
  }, [isLongPressActive, scrollContainerRef]);

  // Handle clicks outside the action menu and keyboard shortcuts
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (
        showActionMenu &&
        (!menuRef.current || !menuRef.current.contains(target))
      ) {
        setShowActionMenu(false);
        setPendingSelections({});
        setMultiSelections({});
      }
    };

    const handleKeyPress = (event: KeyboardEvent) => {
      if (showActionMenu) {
        switch (event.key.toLowerCase()) {
          case "c":
            event.preventDefault();
            handleCopyText();
            break;
          case "l":
            event.preventDefault();
            handleCopyLink();
            break;
          case "a":
            event.preventDefault();
            if (activeSpanLabel) {
              handleApplyLabel();
            }
            break;
          case "escape":
            event.preventDefault();
            setShowActionMenu(false);
            setPendingSelections({});
            setMultiSelections({});
            break;
        }
      }
    };

    if (showActionMenu) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyPress);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
        document.removeEventListener("keydown", handleKeyPress);
      };
    }
  }, [
    showActionMenu,
    handleCopyText,
    handleCopyLink,
    handleApplyLabel,
    activeSpanLabel,
  ]);

  return (
    <div
      id="selection-layer"
      ref={containerRef}
      onMouseDown={handleMouseDown}
      onMouseMove={localPageSelection ? handleMouseMove : undefined}
      onMouseUp={handleMouseUp}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        zIndex: 1,
        touchAction: isLongPressActive ? "none" : "auto",
      }}
    >
      {localPageSelection?.pageNumber === pageNumber
        ? convertBoundsToSelections(localPageSelection.bounds, activeSpanLabel)
        : null}
      {pageQueuedSelections.length > 0
        ? pageQueuedSelections.map((selection, index) =>
            convertBoundsToSelections(selection, activeSpanLabel)
          )
        : null}
      {/* Show pending selections even without a label (for copy action) */}
      {showActionMenu &&
        pendingSelections[pageNumber] &&
        pendingSelections[pageNumber].map((selection, index) => (
          <SelectionBoundary
            key={`pending-${index}`}
            id={`pending-${index}`}
            showBoundingBox
            hidden={false}
            color="#0066cc"
            bounds={selection}
            selected={false}
          />
        ))}

      {/* Selection Action Menu */}
      {showActionMenu && (
        <SelectionActionMenu
          ref={menuRef}
          data-testid="selection-action-menu"
          onTouchStart={(e) => e.stopPropagation()}
          onTouchMove={(e) => e.stopPropagation()}
          onTouchEnd={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          style={{
            position: "fixed",
            left: `${actionMenuPosition.x}px`,
            top: `${actionMenuPosition.y}px`,
            zIndex: 1000,
          }}
        >
          <ActionMenuItem
            onClick={(e) => {
              e.stopPropagation();
              handleCopyText();
            }}
            onTouchStart={(e) => {
              e.stopPropagation();
              lastMenuInteractionTime.current = Date.now();
            }}
            data-testid="copy-text-button"
          >
            <Copy size={16} />
            <span>Copy Text</span>
            <ShortcutHint>C</ShortcutHint>
          </ActionMenuItem>

          <ActionMenuItem
            onClick={(e) => {
              e.stopPropagation();
              handleCopyLink();
            }}
            onTouchStart={(e) => {
              e.stopPropagation();
              lastMenuInteractionTime.current = Date.now();
            }}
            data-testid="copy-link-button"
          >
            <Link size={16} />
            <span>Copy Link</span>
            <ShortcutHint>L</ShortcutHint>
          </ActionMenuItem>

          {/* Show annotation option or helpful message */}
          {!read_only && canUpdateCorpus && (
            <>
              <MenuDivider />
              {activeSpanLabel ? (
                <ActionMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    handleApplyLabel();
                  }}
                  onTouchStart={(e) => {
                    e.stopPropagation();
                    lastMenuInteractionTime.current = Date.now();
                  }}
                  data-testid="apply-label-button"
                >
                  <Tag size={16} />
                  <span>Apply Label: {activeSpanLabel.text}</span>
                  <ShortcutHint>A</ShortcutHint>
                </ActionMenuItem>
              ) : !hasLabelset ? (
                <HelpMessage>
                  <AlertCircle size={16} />
                  <div>
                    <span>No labelset configured</span>
                    <HelpText>
                      Click the label selector (bottom right) to create one
                    </HelpText>
                  </div>
                </HelpMessage>
              ) : !hasLabels ? (
                <HelpMessage>
                  <AlertCircle size={16} />
                  <div>
                    <span>No labels available</span>
                    <HelpText>
                      Click the label selector to create labels
                    </HelpText>
                  </div>
                </HelpMessage>
              ) : (
                <HelpMessage>
                  <Settings size={16} />
                  <div>
                    <span>Select a label to annotate</span>
                    <HelpText>Click the label selector (bottom right)</HelpText>
                  </div>
                </HelpMessage>
              )}
            </>
          )}

          {/* Show message for read-only mode */}
          {(read_only || !canUpdateCorpus) && (
            <>
              <MenuDivider />
              <HelpMessage>
                <AlertCircle size={16} />
                <div>
                  <span>Annotation unavailable</span>
                  <HelpText>
                    {read_only
                      ? "Document is read-only"
                      : "No corpus permissions"}
                  </HelpText>
                </div>
              </HelpMessage>
            </>
          )}

          <MenuDivider />
          <ActionMenuItem
            onClick={(e) => {
              e.stopPropagation();
              handleCancel();
            }}
            onTouchStart={(e) => {
              e.stopPropagation();
              lastMenuInteractionTime.current = Date.now();
            }}
            data-testid="cancel-button"
          >
            <X size={16} />
            <span>Cancel</span>
            <ShortcutHint>ESC</ShortcutHint>
          </ActionMenuItem>
        </SelectionActionMenu>
      )}
    </div>
  );
};

export default React.memo(SelectionLayer);
