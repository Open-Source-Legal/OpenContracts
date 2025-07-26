import React, { useState } from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import {
  Settings,
  Square,
  Layers,
  User,
  Eye,
  EyeOff,
  BarChart3,
  Database,
  Plus,
} from "lucide-react";
import { Checkbox, CheckboxProps } from "semantic-ui-react";
import { useAnnotationDisplay } from "../../annotator/context/UISettingsAtom";
import { useCorpusState } from "../../annotator/context/CorpusAtom";
import { showSelectCorpusAnalyzerOrFieldsetModal } from "../../../graphql/cache";
import { PermissionTypes } from "../../types";

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
  border: 2px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;

  svg {
    width: 24px;
    height: 24px;
    color: ${(props) => (props.$color ? "white" : "#64748b")};
    transition: transform 0.3s ease;
  }

  &:hover {
    border-color: ${(props) => props.$color || "#3b82f6"};
    box-shadow: 0 6px 20px
      ${(props) =>
        props.$color ? `${props.$color}30` : "rgba(59, 130, 246, 0.15)"};

    svg {
      color: ${(props) => (props.$color ? "white" : "#3b82f6")};
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
  border: 1px solid #e2e8f0;
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
    background: #f8fafc;
  }

  &:not(:last-child) {
    margin-bottom: 0.5rem;
  }
`;

const ControlLabel = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: #1e293b;

  svg {
    width: 18px;
    height: 18px;
    color: #64748b;
  }
`;

const PanelHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-bottom: 1px solid #f1f5f9;
  margin-bottom: 0.75rem;
  font-weight: 600;
  font-size: 0.9375rem;
  color: #1e293b;

  svg {
    width: 20px;
    height: 20px;
    color: #3b82f6;
  }
`;

const StyledCheckbox = styled(Checkbox)`
  &&& {
    transform: scale(1.1);

    label {
      padding-left: 1.75rem !important;

      &:before {
        border-color: #e2e8f0 !important;
        border-radius: 4px !important;
      }

      &:after {
        border-radius: 2px !important;
      }
    }

    &.checked label:before {
      border-color: #3b82f6 !important;
      background: #3b82f6 !important;
    }
  }
`;

interface FloatingDocumentControlsProps {
  /** Whether to show the controls (e.g., only in document layer) */
  visible?: boolean;
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
}

export const FloatingDocumentControls: React.FC<
  FloatingDocumentControlsProps
> = ({
  visible = true,
  onAnalysesClick,
  onExtractsClick,
  analysesOpen = false,
  extractsOpen = false,
  panelOffset = 0,
  readOnly = false,
}) => {
  const [expandedSettings, setExpandedSettings] = useState(false);

  const {
    showStructural,
    setShowStructural,
    showSelectedOnly,
    setShowSelectedOnly,
    showBoundingBoxes,
    setShowBoundingBoxes,
  } = useAnnotationDisplay();

  // Get corpus permissions to check if user can create analyses
  const { selectedCorpus } = useCorpusState();
  const canCreateAnalysis =
    selectedCorpus?.myPermissions?.includes(PermissionTypes.CAN_READ) &&
    selectedCorpus?.myPermissions?.includes(PermissionTypes.CAN_UPDATE);

  if (!visible) return null;

  const handleShowSelectedChange = (checked: boolean) => {
    setShowSelectedOnly(checked);
  };

  const handleShowStructuralChange = () => {
    const newStructuralValue = !showStructural;
    setShowStructural(newStructuralValue);

    // If enabling structural view, force "show selected only" to be true
    if (newStructuralValue) {
      setShowSelectedOnly(true);
    }
  };

  const handleShowBoundingBoxesChange = (checked: boolean) => {
    setShowBoundingBoxes(checked);
  };

  return (
    <ControlsContainer $panelOffset={panelOffset}>
      <AnimatePresence>
        {expandedSettings && (
          <ControlPanel
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: 0.2 }}
          >
            <PanelHeader>
              <Eye />
              Visualization Settings
            </PanelHeader>

            <ControlItem>
              <ControlLabel>
                <User />
                Show Only Selected
              </ControlLabel>
              <StyledCheckbox
                toggle
                onChange={(
                  _e: React.FormEvent<HTMLInputElement>,
                  data: CheckboxProps
                ) => handleShowSelectedChange(data?.checked ?? false)}
                checked={showSelectedOnly}
                disabled={showStructural}
              />
            </ControlItem>

            <ControlItem>
              <ControlLabel>
                <Square />
                Show Bounding Boxes
              </ControlLabel>
              <StyledCheckbox
                toggle
                onChange={(
                  _e: React.FormEvent<HTMLInputElement>,
                  data: CheckboxProps
                ) => handleShowBoundingBoxesChange(data?.checked ?? false)}
                checked={showBoundingBoxes}
              />
            </ControlItem>

            <ControlItem>
              <ControlLabel>
                <Layers />
                Show Structural
              </ControlLabel>
              <StyledCheckbox
                toggle
                onChange={handleShowStructuralChange}
                checked={showStructural}
              />
            </ControlItem>
          </ControlPanel>
        )}
      </AnimatePresence>

      <ActionButton
        data-expanded={expandedSettings}
        onClick={() => setExpandedSettings(!expandedSettings)}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        <Settings />
      </ActionButton>

      <ActionButton
        $color="#8b5cf6"
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
        $color="#f59e0b"
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

      {/* New button: Start Analysis - only show if user has permissions and not in readOnly mode */}
      {canCreateAnalysis && !readOnly && (
        <ActionButton
          $color="#10b981"
          onClick={() => showSelectCorpusAnalyzerOrFieldsetModal(true)}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          title="Start New Analysis"
        >
          <Plus />
        </ActionButton>
      )}
    </ControlsContainer>
  );
};
