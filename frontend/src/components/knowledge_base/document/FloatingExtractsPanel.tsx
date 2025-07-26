import React, { useState, useEffect } from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { X, Minimize2, Database, ArrowLeft } from "lucide-react";
import ExtractTraySelector from "../../analyses/ExtractTraySelector";
import { SingleDocumentExtractResults } from "../../annotator/sidebar/SingleDocumentExtractResults";
import {
  ExtractType,
  ColumnType,
  DatacellType,
} from "../../../types/graphql-api";
import {
  useAnalysisSelection,
  useAnalysisManager,
} from "../../annotator/hooks/AnalysisHooks";

interface FloatingExtractsPanelProps {
  visible: boolean;
  extracts: ExtractType[];
  onClose: () => void;
  panelOffset?: number;
  initiallyExpanded?: boolean;
  readOnly?: boolean;
}

const FloatingContainer = styled(motion.div)<{
  $isExpanded: boolean;
  $panelOffset?: number;
}>`
  position: fixed;
  top: 50%;
  right: ${(props) => {
    const baseOffset = props.$panelOffset ? props.$panelOffset + 32 : 32;
    // Keep extracts panel offset from analyses panel (5rem = 80px)
    return `${baseOffset + 80}px`;
  }};
  transform: translateY(-50%);
  z-index: 2001;
  width: ${(props) => (props.$isExpanded ? "500px" : "64px")};
  height: ${(props) => (props.$isExpanded ? "80vh" : "64px")};
  max-height: 900px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  @media (max-width: 768px) {
    right: 1rem;
    top: 40%;
    width: ${(props) => (props.$isExpanded ? "calc(100vw - 2rem)" : "56px")};
    height: ${(props) => (props.$isExpanded ? "50vh" : "56px")};
  }
`;

const CollapsedButton = styled(motion.button)`
  width: 64px;
  height: 64px;
  border-radius: 20px;
  background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 8px 32px rgba(139, 92, 246, 0.3);
  position: relative;
  overflow: hidden;

  &::before {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(
      circle at 30% 30%,
      rgba(255, 255, 255, 0.3),
      transparent
    );
  }

  svg {
    color: white;
    width: 28px;
    height: 28px;
    position: relative;
    z-index: 1;
  }

  &:hover {
    box-shadow: 0 12px 40px rgba(139, 92, 246, 0.4);
  }
`;

const ExpandedPanel = styled(motion.div)`
  width: 100%;
  height: 100%;
  background: white;
  border-radius: 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  border: 1px solid rgba(226, 232, 240, 0.8);
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const Header = styled.div`
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(180deg, #fafbfc 0%, rgba(250, 251, 252, 0) 100%);
`;

const Title = styled.h3`
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 0.75rem;

  svg {
    color: #8b5cf6;
  }
`;

const Actions = styled.div`
  display: flex;
  gap: 0.5rem;
`;

const ActionButton = styled(motion.button)`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;

  svg {
    width: 18px;
    height: 18px;
    color: #64748b;
  }

  &:hover {
    background: #f8fafc;
    border-color: #cbd5e1;

    svg {
      color: #475569;
    }
  }
`;

const Content = styled.div`
  flex: 1;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: column;
`;

const Badge = styled.span`
  position: absolute;
  top: -8px;
  right: -8px;
  background: #8b5cf6;
  color: white;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(139, 92, 246, 0.3);
`;

const BackBar = styled.div`
  padding: 1rem 1.5rem;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  gap: 1rem;
`;

const BackButton = styled(motion.button)`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  color: #64748b;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  svg {
    width: 16px;
    height: 16px;
  }

  &:hover {
    background: #f8fafc;
    color: #475569;
    border-color: #cbd5e1;
  }
`;

const ExtractTitle = styled.div`
  flex: 1;
  font-weight: 600;
  color: #1e293b;
`;

export const FloatingExtractsPanel: React.FC<FloatingExtractsPanelProps> = ({
  visible,
  extracts,
  onClose,
  panelOffset = 0,
  initiallyExpanded = false,
  readOnly = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(initiallyExpanded);
  const [showBadge, setShowBadge] = useState(false);
  const { selectedExtract } = useAnalysisSelection();
  const { dataCells, columns, onSelectExtract } = useAnalysisManager();

  useEffect(() => {
    // Show badge for new extracts when collapsed
    if (!isExpanded && extracts.length > 0) {
      setShowBadge(true);
      const timer = setTimeout(() => setShowBadge(false), 5000);
      return () => clearTimeout(timer);
    }
  }, [extracts.length, isExpanded]);

  // Auto-expand when becoming visible, collapse when hidden
  useEffect(() => {
    if (visible) {
      setIsExpanded(true);
    } else {
      // Reset to collapsed state when hidden
      setIsExpanded(false);
    }
  }, [visible]);

  if (!visible) return null;

  return (
    <FloatingContainer $isExpanded={isExpanded} $panelOffset={panelOffset}>
      <AnimatePresence>
        {!isExpanded ? (
          <CollapsedButton
            key="collapsed"
            onClick={() => setIsExpanded(true)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
          >
            <Database />
            {showBadge && extracts.length > 0 && (
              <Badge>{extracts.length}</Badge>
            )}
          </CollapsedButton>
        ) : (
          <ExpandedPanel
            key="expanded"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
          >
            <Header>
              <Title>
                <Database size={20} />
                Document Extracts
              </Title>
              <Actions>
                <ActionButton
                  onClick={() => setIsExpanded(false)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  title="Minimize"
                >
                  <Minimize2 />
                </ActionButton>
                <ActionButton
                  onClick={onClose}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  title="Close"
                >
                  <X />
                </ActionButton>
              </Actions>
            </Header>
            <Content>
              {selectedExtract ? (
                <>
                  <BackBar>
                    <BackButton
                      onClick={() => onSelectExtract(null)}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <ArrowLeft />
                      Back to Extracts
                    </BackButton>
                    <ExtractTitle>{selectedExtract.name}</ExtractTitle>
                  </BackBar>
                  <div style={{ flex: 1, overflow: "hidden" }}>
                    <SingleDocumentExtractResults
                      datacells={dataCells}
                      columns={columns}
                    />
                  </div>
                </>
              ) : (
                <ExtractTraySelector read_only={readOnly} extracts={extracts} />
              )}
            </Content>
          </ExpandedPanel>
        )}
      </AnimatePresence>
    </FloatingContainer>
  );
};
