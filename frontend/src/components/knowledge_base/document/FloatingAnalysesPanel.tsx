import React, { useState, useEffect } from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { X, BarChart3, Grid3x3, List, Search } from "lucide-react";
import AnalysisTraySelector from "../../analyses/AnalysisTraySelector";
import { AnalysisType } from "../../../types/graphql-api";

interface FloatingAnalysesPanelProps {
  visible: boolean;
  analyses: AnalysisType[];
  onClose: () => void;
  panelOffset?: number;
  readOnly?: boolean;
}

const FloatingContainer = styled(motion.div)<{ $panelOffset?: number }>`
  position: fixed;
  top: 50%;
  right: ${(props) => {
    const baseOffset = props.$panelOffset ? props.$panelOffset + 32 : 32;
    return `${baseOffset + 80}px`;
  }};
  transform: translateY(-50%);
  z-index: 2001;
  width: 480px;
  height: 80vh;
  max-height: 900px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  @media (max-width: 1400px) {
    width: 420px;
  }

  @media (max-width: 768px) {
    right: 1rem;
    width: calc(100vw - 2rem);
    height: 70vh;
    max-height: 600px;
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
  padding: 1.5rem 1.75rem;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(180deg, #fafbfc 0%, rgba(250, 251, 252, 0) 100%);
  flex-shrink: 0;
`;

const Title = styled.h3`
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 0.75rem;

  svg {
    color: #f59e0b;
  }
`;

const HeaderControls = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

const ViewToggle = styled.div`
  display: flex;
  background: #f1f5f9;
  border-radius: 10px;
  padding: 0.25rem;
  gap: 0.25rem;
`;

const ViewButton = styled(motion.button)<{ $active: boolean }>`
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  border: none;
  background: ${(props) => (props.$active ? "white" : "transparent")};
  color: ${(props) => (props.$active ? "#0f172a" : "#64748b")};
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: 500;
  font-size: 0.875rem;
  transition: all 0.2s ease;
  box-shadow: ${(props) =>
    props.$active ? "0 2px 4px rgba(0, 0, 0, 0.05)" : "none"};

  svg {
    width: 16px;
    height: 16px;
  }

  &:hover:not(:disabled) {
    color: ${(props) => (props.$active ? "#0f172a" : "#475569")};
  }
`;

const ActionButton = styled(motion.button)`
  width: 36px;
  height: 36px;
  border-radius: 10px;
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

const SearchBar = styled.div`
  padding: 1rem 1.75rem;
  border-bottom: 1px solid #f1f5f9;
  background: #fafbfc;

  input {
    width: 100%;
    padding: 0.75rem 1rem 0.75rem 2.75rem;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    font-size: 0.9375rem;
    background: white;
    transition: all 0.2s ease;

    &:focus {
      outline: none;
      border-color: #f59e0b;
      box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.1);
    }

    &::placeholder {
      color: #94a3b8;
    }
  }

  position: relative;

  svg {
    position: absolute;
    left: 2rem;
    top: 50%;
    transform: translateY(-50%);
    width: 18px;
    height: 18px;
    color: #94a3b8;
  }
`;

const Content = styled.div`
  flex: 1;
  overflow: hidden;
  position: relative;
  background: #fafbfc;
`;

const StatsBar = styled.div`
  padding: 1rem 1.75rem;
  background: linear-gradient(180deg, #f8fafc 0%, #fafbfc 100%);
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  gap: 2rem;
  font-size: 0.875rem;
  color: #64748b;
`;

const Stat = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;

  strong {
    color: #0f172a;
    font-weight: 600;
  }
`;

const Badge = styled.span`
  position: absolute;
  top: -8px;
  right: -8px;
  background: #ef4444;
  color: white;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
`;

// Enhanced styled wrapper for the AnalysisTraySelector
const AnalysisSelectorWrapper = styled.div<{
  $viewMode: "compact" | "expanded";
}>`
  height: 100%;
  overflow: hidden;

  /* Override the default styles to support compact mode */
  ${(props) =>
    props.$viewMode === "compact" &&
    `
    .analysis-card {
      padding: 1rem !important;
      margin-bottom: 0.75rem !important;
      
      .analysis-header {
        margin: -1rem -1rem 0.75rem -1rem !important;
        padding: 1rem !important;
      }
      
      .timestamps {
        display: none !important;
      }
      
      .description-container {
        display: none !important;
      }
      
      .annotations-section {
        margin-top: 0.75rem !important;
        padding-top: 0.75rem !important;
      }
      
      .analyzer-description-header {
        display: none !important;
      }
    }
  `}
`;

export const FloatingAnalysesPanel: React.FC<FloatingAnalysesPanelProps> = ({
  visible,
  analyses,
  onClose,
  panelOffset = 0,
  readOnly = false,
}) => {
  const [viewMode, setViewMode] = useState<"compact" | "expanded">("expanded");
  const [searchTerm, setSearchTerm] = useState("");

  // Calculate stats
  const totalAnnotations = analyses.reduce(
    (sum, analysis) => sum + (analysis.annotations?.totalCount || 0),
    0
  );

  const completedAnalyses = analyses.filter(
    (analysis) => analysis.analysisCompleted
  ).length;

  if (!visible) return null;

  return (
    <FloatingContainer $panelOffset={panelOffset}>
      <ExpandedPanel
        key="expanded"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
      >
        <Header>
          <Title>
            <BarChart3 size={24} />
            Document Analyses
            {analyses.length > 0 && <Badge>{analyses.length}</Badge>}
          </Title>
          <HeaderControls>
            <ViewToggle>
              <ViewButton
                $active={viewMode === "compact"}
                onClick={() => setViewMode("compact")}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                title="Compact view"
              >
                <Grid3x3 />
                Compact
              </ViewButton>
              <ViewButton
                $active={viewMode === "expanded"}
                onClick={() => setViewMode("expanded")}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                title="Expanded view"
              >
                <List />
                Expanded
              </ViewButton>
            </ViewToggle>
            <ActionButton
              onClick={onClose}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              title="Close"
            >
              <X />
            </ActionButton>
          </HeaderControls>
        </Header>

        {analyses.length > 3 && (
          <SearchBar>
            <Search />
            <input
              type="text"
              placeholder="Search analyses..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </SearchBar>
        )}

        {analyses.length > 0 && (
          <StatsBar>
            <Stat>
              <strong>{analyses.length}</strong> analyses
            </Stat>
            <Stat>
              <strong>{completedAnalyses}</strong> completed
            </Stat>
            <Stat>
              <strong>{totalAnnotations}</strong> annotations
            </Stat>
          </StatsBar>
        )}

        <Content>
          <AnalysisSelectorWrapper $viewMode={viewMode}>
            <AnalysisTraySelector
              read_only={readOnly}
              analyses={analyses}
              viewMode={viewMode}
              searchTerm={searchTerm}
            />
          </AnalysisSelectorWrapper>
        </Content>
      </ExpandedPanel>
    </FloatingContainer>
  );
};
