import React, { useState, useEffect, memo } from "react";
import styled, { css } from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import {
  Settings,
  Eye,
  BarChart3,
  Database,
  Plus,
  Columns,
  Maximize2,
  X,
} from "lucide-react";
import { useCorpusState } from "../../annotator/context/CorpusAtom";
import {
  useDocumentPermissions,
  useDocumentState,
} from "../../annotator/context/DocumentAtom";
import { showSelectCorpusAnalyzerOrFieldsetModal } from "../../../graphql/cache";
import { PermissionTypes } from "../../types";
import { AnnotationControls } from "../../annotator/controls/AnnotationControls";
import { ToggleSwitch } from "../../widgets/ToggleSwitch";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { visualViewportAwareBottom } from "../../../utils/layout";
import {
  DESKTOP_FLOATING_CONTROLS_BOTTOM,
  MOBILE_FLOATING_CONTROLS_BOTTOM,
} from "../../../assets/configurations/constants";
import { SidebarTab } from "./styled/SidebarTabs";

/**
 * Vertical container for the floating document controls.
 *
 * Three positioning modes:
 * - `$bare=true`     → no positioning of its own; the parent (the unified
 *   `RightEdgeRail` in DesktopDocumentLayout, panel-closed case) stacks the
 *   action buttons directly below the navigation tabs in one coherent rail.
 * - panel open       → bottom-right with `$panelOffset` so the cluster
 *   clears the open right panel.
 * - panel closed and not bare → legacy bottom-right placement (kept for
 *   mobile and for the standalone component test wrapper).
 */
const ControlsContainer = styled(motion.div)<{
  $panelOffset?: number;
  $bare?: boolean;
}>`
  ${(props) =>
    props.$bare
      ? `
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 6px;
  `
      : `
    position: fixed;
    bottom: ${DESKTOP_FLOATING_CONTROLS_BOTTOM};
    right: ${props.$panelOffset ? `${props.$panelOffset + 32}px` : "2rem"};
    z-index: 2001;
    display: flex;
    flex-direction: column-reverse;
    align-items: flex-end;
    gap: 0.75rem;
    transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    @media (max-width: 768px) {
      right: 1rem;
      bottom: ${visualViewportAwareBottom(MOBILE_FLOATING_CONTROLS_BOTTOM)};
    }
  `}
`;

// Action button (extracts/analyses/create/settings/width). Extends SidebarTab so it shares the same pill shape/footprint as the navigation tabs; $accent tints the icon to preserve lightweight per-action color cues (analyses=amber, extracts=violet, create=green) without heavy colored circles.
const ActionButton = styled(SidebarTab)`
  /* Expanded state (settings / width menu open) rotates the icon. */
  &[data-expanded="true"] svg {
    transform: rotate(45deg);
  }
`;

/*
 * Popover anchored to a button inside ControlsContainer. Two positioning
 * modes, mirroring the container's two flex directions:
 *
 * - Non-bare (bottom-right floating cluster): ControlsContainer uses
 *   `flex-direction: column-reverse`, so the trigger (Settings or Width)
 *   sits at the BOTTOM of the stack. The popover anchors with
 *   `bottom: calc(56px + 1rem)` so it floats directly above that trigger.
 *
 * - Bare (unified RightEdgeRail, panel closed): ControlsContainer uses
 *   `flex-direction: column`, so the Settings trigger sits at the TOP of the
 *   stack (just below the RailDivider). The popover anchors to the LEFT of
 *   the rail with `right: calc(100% + 8px); top: 0;` so it appears beside
 *   Settings rather than far above it (the previous behavior, which left
 *   the popover floating high above the trigger because the bottom anchor
 *   was measured from the BOTTOM of the column = past the other action
 *   buttons).
 */
const ControlPanel = styled(motion.div)<{ $bare?: boolean }>`
  position: absolute;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  border: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 1rem;
  min-width: 240px;

  ${(props) =>
    props.$bare
      ? css`
          right: calc(100% + 8px);
          top: 0;
        `
      : css`
          right: 0;
          bottom: calc(56px + 1rem); /* button height + gap */

          @media (max-width: 768px) {
            bottom: calc(40px + 1rem); /* smaller mobile button height */
          }
        `}
`;

const ControlItem = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem;
  border-radius: 8px;
  transition: background 0.2s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  &:not(:last-child) {
    margin-bottom: 0.5rem;
  }
`;

const ControlLabel = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }
`;

const Divider = styled.div`
  height: 1px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  margin: 0.5rem 0;
`;

const PanelHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.surfaceLight};
  margin-bottom: 0.75rem;
  font-weight: 600;
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    width: 20px;
    height: 20px;
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const PanelHeaderTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
`;

const CloseButton = styled(motion.button)`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;

  svg {
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${OS_LEGAL_COLORS.borderHover};

    svg {
      color: ${OS_LEGAL_COLORS.textTertiary};
    }
  }

  &:active {
    transform: scale(0.95);
  }
`;

const WidthMenuItem = styled(motion.button)<{ $isActive: boolean }>`
  width: 100%;
  padding: 0.75rem 1rem;
  border: none;
  background: ${(props) =>
    props.$isActive
      ? "linear-gradient(135deg, rgba(66, 153, 225, 0.08), rgba(66, 153, 225, 0.05))"
      : "transparent"};
  color: ${(props) =>
    props.$isActive
      ? OS_LEGAL_COLORS.primaryBlue
      : OS_LEGAL_COLORS.textSecondary};
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  text-align: left;
  display: flex;
  align-items: center;
  justify-content: space-between;
  white-space: nowrap;
  position: relative;
  overflow: hidden;

  /* Subtle left accent for active state */
  &::before {
    content: "";
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 2px;
    height: ${(props) => (props.$isActive ? "60%" : "0")};
    background: ${OS_LEGAL_COLORS.primaryBlue};
    border-radius: 1px;
    transition: height 0.2s ease;
  }

  &:hover {
    background: ${(props) =>
      props.$isActive
        ? "linear-gradient(135deg, rgba(66, 153, 225, 0.12), rgba(66, 153, 225, 0.08))"
        : "rgba(0, 0, 0, 0.02)"};
    color: ${(props) =>
      props.$isActive
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.textTertiary};
    transform: translateX(2px);
  }

  &:active {
    transform: translateX(2px) scale(0.98);
  }

  .percentage {
    font-size: 0.75rem;
    opacity: 0.6;
    font-weight: 400;
  }
`;

interface FloatingDocumentControlsProps {
  /** Whether to show the controls (e.g., only in document layer) */
  visible?: boolean;
  /** Whether the right panel is currently shown */
  showRightPanel?: boolean;
  /** Callback when analyses button is clicked */
  onAnalysesClick?: () => void;
  /** Callback when extracts button is clicked */
  onExtractsClick?: () => void;
  /** Whether analyses panel is open */
  analysesOpen?: boolean;
  /** Whether extracts panel is open */
  extractsOpen?: boolean;
  /** Offset to apply when sliding panel is open */
  panelOffset?: number;
  /** When true, hide create/edit functionality */
  readOnly?: boolean;
  /** Current panel width mode */
  panelWidthMode?: "quarter" | "half" | "full";
  /** Callback when panel width changes */
  onPanelWidthChange?: (mode: "quarter" | "half" | "full") => void;
  /** Whether auto-zoom is enabled */
  autoZoomEnabled?: boolean;
  /** Callback when auto-zoom toggle changes */
  onAutoZoomChange?: (enabled: boolean) => void;
  /**
   * When true, hides document-tool FABs (analyses, extracts, create-analysis)
   * to declutter the area around the right tray's chat input. The panel-width
   * control is kept since it's directly relevant to the open panel.
   */
  hideDocumentTools?: boolean;
  /**
   * When true, render without the legacy bottom-right fixed positioning so a
   * parent container (the unified `RightEdgeRail` in DesktopDocumentLayout)
   * can stack these action buttons directly below the navigation tabs as one
   * coherent vertical rail. Overlay popovers (settings, panel-width menu)
   * still position relative to this container.
   */
  bareContainer?: boolean;
}

export const FloatingDocumentControls: React.FC<FloatingDocumentControlsProps> =
  memo(
    ({
      visible = true,
      showRightPanel = false,
      onAnalysesClick,
      onExtractsClick,
      analysesOpen = false,
      extractsOpen = false,
      panelOffset = 0,
      readOnly = false,
      panelWidthMode = "half",
      onPanelWidthChange,
      autoZoomEnabled = true,
      onAutoZoomChange,
      hideDocumentTools = false,
      bareContainer = false,
    }) => {
      const [expandedSettings, setExpandedSettings] = useState(false);
      const [expandedWidthMenu, setExpandedWidthMenu] = useState(false);

      // Get document permissions to check if user can create analyses (not corpus permissions!)
      const { permissions: documentPermissions, setPermissions } =
        useDocumentPermissions();
      const { activeDocument } = useDocumentState();
      const { selectedCorpus } = useCorpusState(); // Still need corpus for context/logging

      // Sync permissions from document state when it loads/changes
      useEffect(() => {
        if (activeDocument?.myPermissions) {
          setPermissions(activeDocument.myPermissions);
        }
      }, [activeDocument, setPermissions]);

      const hasReadPermission = documentPermissions?.includes(
        PermissionTypes.CAN_READ
      );
      const hasUpdatePermission = documentPermissions?.includes(
        PermissionTypes.CAN_UPDATE
      );
      const canCreateAnalysis = hasReadPermission && hasUpdatePermission;

      // Close settings panel when right panel opens
      useEffect(() => {
        if (showRightPanel && expandedSettings) {
          setExpandedSettings(false);
        }
      }, [showRightPanel]); // Remove expandedSettings from deps to avoid closure issues

      // Close width menu when right panel opens
      useEffect(() => {
        if (showRightPanel && expandedWidthMenu) {
          setExpandedWidthMenu(false);
        }
      }, [showRightPanel]);

      // Add logging for early return
      if (!visible) {
        return null;
      }

      // Desktop Layout
      return (
        <ControlsContainer $panelOffset={panelOffset} $bare={bareContainer}>
          <AnimatePresence>
            {expandedWidthMenu && showRightPanel && (
              // No `$bare` here: the width menu is gated on `showRightPanel`
              // and the unified rail (bare mode) only renders when the panel
              // is closed, so this branch is unreachable when bareContainer
              // is true. Omitting the prop keeps the non-bare anchor —
              // bottom-right above the trigger — which is what the open-panel
              // layout expects.
              <ControlPanel
                data-testid="width-menu-panel"
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.2 }}
              >
                <PanelHeader>
                  <Columns />
                  Panel Width
                </PanelHeader>
                <WidthMenuItem
                  $isActive={panelWidthMode === "quarter"}
                  onClick={() => {
                    onPanelWidthChange?.("quarter");
                    setExpandedWidthMenu(false);
                  }}
                  whileTap={{ scale: 0.98 }}
                >
                  Compact
                  <span className="percentage">25%</span>
                </WidthMenuItem>
                <WidthMenuItem
                  $isActive={panelWidthMode === "half"}
                  onClick={() => {
                    onPanelWidthChange?.("half");
                    setExpandedWidthMenu(false);
                  }}
                  whileTap={{ scale: 0.98 }}
                >
                  Standard
                  <span className="percentage">50%</span>
                </WidthMenuItem>
                <WidthMenuItem
                  $isActive={panelWidthMode === "full"}
                  onClick={() => {
                    onPanelWidthChange?.("full");
                    setExpandedWidthMenu(false);
                  }}
                  whileTap={{ scale: 0.98 }}
                >
                  Wide
                  <span className="percentage">90%</span>
                </WidthMenuItem>
              </ControlPanel>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {expandedSettings && (
              <ControlPanel
                $bare={bareContainer}
                data-testid="settings-panel"
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.2 }}
              >
                <PanelHeader>
                  <PanelHeaderTitle>
                    <Eye />
                    Annotation Filters
                  </PanelHeaderTitle>
                  <CloseButton
                    onClick={() => setExpandedSettings(false)}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    aria-label="Close annotation filters"
                    data-testid="close-settings-button"
                  >
                    <X />
                  </CloseButton>
                </PanelHeader>
                <AnnotationControls
                  variant="floating"
                  showLabelFilters
                  compact
                />

                <Divider />

                <ControlItem>
                  <ControlLabel>
                    <Maximize2 />
                    Auto-Zoom Sidebar
                  </ControlLabel>
                  <ToggleSwitch>
                    <input
                      type="checkbox"
                      aria-label="Auto-Zoom Sidebar"
                      checked={autoZoomEnabled}
                      onChange={() => onAutoZoomChange?.(!autoZoomEnabled)}
                    />
                    <span />
                  </ToggleSwitch>
                </ControlItem>
              </ControlPanel>
            )}
          </AnimatePresence>

          {/* Width control button - only show when right panel is open */}
          {showRightPanel && (
            <ActionButton
              $isActive={expandedWidthMenu}
              $panelOpen={false}
              data-expanded={expandedWidthMenu}
              data-testid="width-button"
              data-tooltip="Panel width"
              aria-label="Panel width"
              aria-expanded={expandedWidthMenu}
              onClick={() => setExpandedWidthMenu(!expandedWidthMenu)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Columns />
            </ActionButton>
          )}

          {/* Only show Settings button when right panel is closed */}
          {!showRightPanel && (
            <ActionButton
              $isActive={expandedSettings}
              $panelOpen={false}
              data-expanded={expandedSettings}
              data-testid="settings-button"
              data-tooltip="Annotation filters"
              aria-label="Annotation filters"
              aria-expanded={expandedSettings}
              onClick={() => setExpandedSettings(!expandedSettings)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Settings />
            </ActionButton>
          )}

          {!hideDocumentTools && (
            <>
              <ActionButton
                $isActive={extractsOpen}
                $panelOpen={false}
                $accent="#8b5cf6"
                data-testid="extracts-button"
                data-tooltip="View extracts"
                aria-label="View extracts"
                aria-pressed={extractsOpen}
                onClick={() => {
                  /*
                   * Ensure exclusivity: if the analyses panel is open we close it before
                   * toggling the extracts panel open, and vice-versa. This guarantees
                   * that both panels are never visible at the same time.
                   */
                  if (!extractsOpen) {
                    // Opening extracts – make sure analyses panel is closed first
                    if (analysesOpen && onAnalysesClick) {
                      onAnalysesClick();
                    }
                  }
                  if (onExtractsClick) onExtractsClick();
                }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <Database />
              </ActionButton>

              <ActionButton
                $isActive={analysesOpen}
                $panelOpen={false}
                $accent={OS_LEGAL_COLORS.folderIcon}
                data-testid="analyses-button"
                data-tooltip="View analyses"
                aria-label="View analyses"
                aria-pressed={analysesOpen}
                onClick={() => {
                  /*
                   * Mirror logic for analyses button.
                   */
                  if (!analysesOpen) {
                    // Opening analyses – close extracts first if open
                    if (extractsOpen && onExtractsClick) {
                      onExtractsClick();
                    }
                  }
                  if (onAnalysesClick) onAnalysesClick();
                }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <BarChart3 />
              </ActionButton>

              {canCreateAnalysis && !readOnly && selectedCorpus && (
                <ActionButton
                  $isActive={false}
                  $panelOpen={false}
                  $accent={OS_LEGAL_COLORS.greenMedium}
                  data-testid="create-analysis-button"
                  data-tooltip="Start new analysis"
                  aria-label="Start new analysis"
                  onClick={() => showSelectCorpusAnalyzerOrFieldsetModal(true)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <Plus />
                </ActionButton>
              )}
            </>
          )}
        </ControlsContainer>
      );
    }
  );

FloatingDocumentControls.displayName = "FloatingDocumentControls";
