import React, { useState, useEffect, memo } from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import {
  Settings,
  Eye,
  BarChart3,
  Database,
  Plus,
  Columns,
  Maximize2,
  Sparkles,
  X,
  BookOpen,
} from "lucide-react";
import { useCorpusState } from "../../annotator/context/CorpusAtom";
import {
  useDocumentPermissions,
  useDocumentState,
} from "../../annotator/context/DocumentAtom";
import {
  showSelectCorpusAnalyzerOrFieldsetModal,
  openedCorpus,
} from "../../../graphql/cache";
import { PermissionTypes } from "../../types";
import { AnnotationControls } from "../../annotator/controls/AnnotationControls";
import { ToggleSwitch } from "../../widgets/ToggleSwitch";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

const ControlsContainer = styled(motion.div)<{ $panelOffset?: number }>`
  position: fixed;
  bottom: calc(
    2rem + 48px + max(10px, 2rem)
  ); /* UnifiedLabelSelector height (48px) + gap (2rem min 10px) */
  right: ${(props) =>
    props.$panelOffset ? `${props.$panelOffset + 32}px` : "2rem"};
  z-index: 2001;
  display: flex;
  flex-direction: column-reverse;
  align-items: flex-end;
  gap: 0.75rem;
  transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  @media (max-width: 768px) {
    right: 1rem;
    bottom: calc(
      1rem + 40px + max(10px, 2rem)
    ); /* Smaller button size on mobile */
  }
`;

const ActionButton = styled(motion.button)<{ $color?: string }>`
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: ${(props) => props.$color || "white"};
  border: 2px solid ${OS_LEGAL_COLORS.border};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;

  svg {
    width: 24px;
    height: 24px;
    color: ${(props) =>
      props.$color ? "white" : OS_LEGAL_COLORS.textSecondary};
    transition: transform 0.3s ease;
  }

  &:hover {
    border-color: ${(props) => props.$color || OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 6px 20px
      ${(props) =>
        props.$color ? `${props.$color}30` : "rgba(59, 130, 246, 0.15)"};

    svg {
      color: ${(props) =>
        props.$color ? "white" : OS_LEGAL_COLORS.primaryBlue};
    }
  }

  &[data-expanded="true"] svg {
    transform: rotate(45deg);
  }
`;

const ControlPanel = styled(motion.div)`
  position: absolute;
  right: 0;
  /* Place the panel just above the button stack */
  bottom: calc(56px + 1rem); /* button height + gap */
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  border: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 1rem;
  min-width: 240px;

  @media (max-width: 768px) {
    bottom: calc(40px + 1rem); /* smaller mobile button height */
  }
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

/* Mobile Speed Dial Components */
const SpeedDialContainer = styled.div`
  position: fixed;
  bottom: calc(
    1rem + 40px + max(10px, 2rem)
  ); /* Above label selector on mobile */
  right: 1rem;
  z-index: 2001;
`;

const SpeedDialBackdrop = styled(motion.div)`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.2);
  z-index: 2000;
  backdrop-filter: blur(2px);
`;

const MainFAB = styled(motion.button)<{ $expanded: boolean }>`
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(102, 126, 234, 0.4);
  position: relative;
  z-index: 2002;

  svg {
    width: 24px;
    height: 24px;
    color: white;
    transition: transform 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55);
    transform: ${(props) =>
      props.$expanded ? "rotate(180deg) scale(1.1)" : "rotate(0deg) scale(1)"};
  }

  &:active {
    transform: scale(0.95);
  }
`;

const OrbitButton = styled(motion.button)<{ $color?: string }>`
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: ${(props) => props.$color || "white"};
  border: 2px solid ${OS_LEGAL_COLORS.border};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  position: absolute;
  bottom: 0;
  right: 0;

  svg {
    width: 20px;
    height: 20px;
    color: ${(props) =>
      props.$color ? "white" : OS_LEGAL_COLORS.textSecondary};
  }

  &:active {
    transform: scale(0.9);
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
  /** Callback when summary button is clicked */
  onSummaryClick?: () => void;
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
  /** Whether to use mobile speed dial layout */
  isMobile?: boolean;
  /**
   * When true, hides document-tool FABs (analyses, extracts, create-analysis)
   * to declutter the area around the right tray's chat input. The panel-width
   * control is kept since it's directly relevant to the open panel.
   */
  hideDocumentTools?: boolean;
}

export const FloatingDocumentControls: React.FC<FloatingDocumentControlsProps> =
  memo(
    ({
      visible = true,
      showRightPanel = false,
      onAnalysesClick,
      onExtractsClick,
      onSummaryClick,
      analysesOpen = false,
      extractsOpen = false,
      panelOffset = 0,
      readOnly = false,
      panelWidthMode = "half",
      onPanelWidthChange,
      autoZoomEnabled = true,
      onAutoZoomChange,
      isMobile = false,
      hideDocumentTools = false,
    }) => {
      const [expandedSettings, setExpandedSettings] = useState(false);
      const [expandedWidthMenu, setExpandedWidthMenu] = useState(false);
      const [speedDialExpanded, setSpeedDialExpanded] = useState(false);

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

      // Helper function to calculate orbital positions for mobile speed dial
      // Arranges buttons in an arc above the main FAB
      const getOrbitPosition = (index: number, total: number) => {
        const radius = 100; // Distance from center in pixels
        const arcAngle = 90; // Total arc span in degrees
        const startAngle = 180 - arcAngle / 2; // Start from upper-left

        // Calculate angle for this button in the arc
        const angle = startAngle + (arcAngle / (total - 1)) * index;
        const radian = (angle * Math.PI) / 180;

        return {
          x: Math.cos(radian) * radius,
          y: Math.sin(radian) * radius,
        };
      };

      // Mobile Speed Dial Rendering
      if (isMobile) {
        // Collect all buttons that should appear in the speed dial
        const speedDialButtons: Array<{
          icon: JSX.Element;
          color?: string;
          onClick: () => void;
          title: string;
          testId: string;
        }> = [];

        // Settings button
        speedDialButtons.push({
          icon: <Settings />,
          onClick: () => {
            setExpandedSettings(!expandedSettings);
            setSpeedDialExpanded(false);
          },
          title: "Annotation Filters",
          testId: "settings-button",
        });

        // Summary button (if callback provided)
        if (onSummaryClick) {
          speedDialButtons.push({
            icon: <BookOpen />,
            color: OS_LEGAL_COLORS.primaryBlue,
            onClick: () => {
              onSummaryClick();
              setSpeedDialExpanded(false);
            },
            title: "View Summary",
            testId: "summary-button",
          });
        }

        // Analyses button
        if (!hideDocumentTools) {
          speedDialButtons.push({
            icon: <BarChart3 />,
            color: OS_LEGAL_COLORS.folderIcon,
            onClick: () => {
              if (!analysesOpen && extractsOpen && onExtractsClick) {
                onExtractsClick();
              }
              if (onAnalysesClick) onAnalysesClick();
              setSpeedDialExpanded(false);
            },
            title: "View Analyses",
            testId: "analyses-button",
          });
        }

        // Extracts button
        if (!hideDocumentTools) {
          speedDialButtons.push({
            icon: <Database />,
            color: "#8b5cf6",
            onClick: () => {
              if (!extractsOpen && analysesOpen && onAnalysesClick) {
                onAnalysesClick();
              }
              if (onExtractsClick) onExtractsClick();
              setSpeedDialExpanded(false);
            },
            title: "View Extracts",
            testId: "extracts-button",
          });
        }

        // Create analysis button (if user has permissions)
        if (
          !hideDocumentTools &&
          canCreateAnalysis &&
          !readOnly &&
          selectedCorpus
        ) {
          speedDialButtons.push({
            icon: <Plus />,
            color: OS_LEGAL_COLORS.greenMedium,
            onClick: () => {
              if (selectedCorpus) {
                showSelectCorpusAnalyzerOrFieldsetModal(true);
              }
              setSpeedDialExpanded(false);
            },
            title: "Start New Analysis",
            testId: "create-analysis-button",
          });
        }

        return (
          <>
            {/* Backdrop - closes speed dial when tapped */}
            <AnimatePresence>
              {speedDialExpanded && (
                <SpeedDialBackdrop
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  onClick={() => setSpeedDialExpanded(false)}
                />
              )}
            </AnimatePresence>

            {/* Settings panel - show outside speed dial container */}
            <AnimatePresence>
              {expandedSettings && (
                <ControlPanel
                  data-testid="settings-panel"
                  initial={{ opacity: 0, scale: 0.95, y: 10 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: 10 }}
                  transition={{ duration: 0.2 }}
                  style={{
                    position: "fixed",
                    bottom: "calc(1rem + 56px + 1rem)",
                    right: "1rem",
                    zIndex: 2003,
                  }}
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
                      title="Close"
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

            {/* Speed Dial Container */}
            <SpeedDialContainer>
              {/* Orbital Buttons */}
              <AnimatePresence>
                {speedDialExpanded &&
                  speedDialButtons.map((button, index) => {
                    const position = getOrbitPosition(
                      index,
                      speedDialButtons.length
                    );
                    return (
                      <OrbitButton
                        key={button.testId}
                        $color={button.color}
                        data-testid={button.testId}
                        onClick={button.onClick}
                        title={button.title}
                        initial={{
                          opacity: 0,
                          scale: 0,
                          x: 0,
                          y: 0,
                        }}
                        animate={{
                          opacity: 1,
                          scale: 1,
                          x: position.x,
                          y: position.y,
                        }}
                        exit={{
                          opacity: 0,
                          scale: 0,
                          x: 0,
                          y: 0,
                        }}
                        transition={{
                          type: "spring",
                          stiffness: 500,
                          damping: 30,
                          delay: index * 0.03, // Stagger animation
                        }}
                      >
                        {button.icon}
                      </OrbitButton>
                    );
                  })}
              </AnimatePresence>

              {/* Main FAB */}
              <MainFAB
                $expanded={speedDialExpanded}
                onClick={() => setSpeedDialExpanded(!speedDialExpanded)}
                data-testid="speed-dial-main-fab"
                whileTap={{ scale: 0.9 }}
              >
                <Sparkles />
              </MainFAB>
            </SpeedDialContainer>
          </>
        );
      }

      // Desktop Layout (original implementation)
      return (
        <ControlsContainer $panelOffset={panelOffset}>
          <AnimatePresence>
            {expandedWidthMenu && showRightPanel && (
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
                    title="Close"
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
              data-expanded={expandedWidthMenu}
              data-testid="width-button"
              onClick={() => setExpandedWidthMenu(!expandedWidthMenu)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              title="Panel Width"
            >
              <Columns />
            </ActionButton>
          )}

          {/* Only show Settings button when right panel is closed */}
          {!showRightPanel && (
            <ActionButton
              data-expanded={expandedSettings}
              data-testid="settings-button"
              onClick={() => setExpandedSettings(!expandedSettings)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              title="Annotation Filters"
            >
              <Settings />
            </ActionButton>
          )}

          {!hideDocumentTools && (
            <>
              <ActionButton
                $color="#8b5cf6"
                data-testid="extracts-button"
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
                title="View Extracts"
              >
                <Database />
              </ActionButton>

              <ActionButton
                $color={OS_LEGAL_COLORS.folderIcon}
                data-testid="analyses-button"
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
                title="View Analyses"
              >
                <BarChart3 />
              </ActionButton>

              {canCreateAnalysis && !readOnly && selectedCorpus && (
                <ActionButton
                  $color={OS_LEGAL_COLORS.greenMedium}
                  data-testid="create-analysis-button"
                  onClick={() => showSelectCorpusAnalyzerOrFieldsetModal(true)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  title="Start New Analysis"
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
