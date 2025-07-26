import React, { useState, useEffect } from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import {
  Minimize2,
  Maximize2,
  BookOpen,
  Layers,
  ArrowLeftFromLine,
} from "lucide-react";
import { SummaryVersionStack } from "./SummaryVersionStack";
import { useSummaryVersions } from "./hooks/useSummaryVersions";
import { useSummaryAnimation } from "./hooks/useSummaryAnimation";
import { SafeMarkdown } from "../../markdown/SafeMarkdown";

interface FloatingSummaryPreviewProps {
  documentId: string;
  corpusId: string;
  documentTitle: string;
  isVisible?: boolean;
  onSwitchToKnowledge?: (content?: string) => void;
  onBackToDocument?: () => void;
  isInKnowledgeLayer?: boolean;
  readOnly?: boolean;
}

const FloatingContainer = styled(motion.div)`
  position: fixed;
  bottom: 2.5rem;
  left: 2.5rem;
  z-index: 100002;
  overflow: visible;

  @media (max-width: 768px) {
    bottom: 1.5rem;
    left: 1.5rem;
  }

  @media (max-width: 480px) {
    bottom: 1rem;
    left: 1rem;
  }
`;

const BaseButton = styled(motion.button)`
  width: 72px;
  height: 72px;
  border-radius: 24px;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.08), 0 2px 16px rgba(0, 0, 0, 0.04),
    inset 0 1px 2px rgba(255, 255, 255, 0.6);
  position: relative;
  overflow: visible;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &::before {
    content: "";
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(
      circle,
      rgba(59, 130, 246, 0.15) 0%,
      transparent 70%
    );
    opacity: 0;
    transition: opacity 0.3s ease;
    animation: pulse 3s ease-in-out infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      transform: scale(0.8);
      opacity: 0;
    }
    50% {
      transform: scale(1.2);
      opacity: 0.3;
    }
  }

  &:hover::before {
    opacity: 1;
  }

  &:hover {
    transform: translateY(-3px) scale(1.02);
    box-shadow: 0 20px 60px rgba(59, 130, 246, 0.2),
      0 4px 24px rgba(0, 0, 0, 0.06), inset 0 1px 3px rgba(255, 255, 255, 0.8);
    border-color: rgba(147, 197, 253, 0.5);
  }

  &:active {
    transform: translateY(-1px) scale(0.98);
  }
`;

const CollapsedButton = styled(BaseButton)`
  overflow: visible;
`;

const BackButton = styled(BaseButton)`
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15),
    0 0 8px 4px rgba(59, 130, 246, 0.35), 0 8px 24px rgba(59, 130, 246, 0.25),
    inset 0 1px 2px rgba(255, 255, 255, 0.6);

  &:hover {
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2),
      0 0 12px 6px rgba(59, 130, 246, 0.5), 0 12px 30px rgba(59, 130, 246, 0.3),
      inset 0 1px 3px rgba(255, 255, 255, 0.8);
  }
`;

const IconWrapper = styled(motion.div)`
  color: #3b82f6;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  z-index: 1;
`;

const IconLabel = styled.span`
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
`;

const VersionBadge = styled(motion.div)`
  position: absolute;
  top: -8px;
  right: -8px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  padding: 5px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4), 0 2px 4px rgba(0, 0, 0, 0.15),
    0 0 0 1px rgba(255, 255, 255, 0.2);
  min-width: 24px;
  text-align: center;
  z-index: 10;
  border: 1px solid rgba(255, 255, 255, 0.2);
`;

const Tooltip = styled(motion.div)`
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  background: rgba(30, 41, 59, 0.95);
  color: white;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);

  &::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-top-color: rgba(30, 41, 59, 0.95);
  }
`;

const ExpandedContainer = styled(motion.div)<{ $isPiP?: boolean }>`
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(20px) saturate(180%);
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.12), 0 12px 24px rgba(0, 0, 0, 0.06),
    inset 0 1px 2px rgba(255, 255, 255, 0.8);
  padding: ${(props) => (props.$isPiP ? "1.5rem" : "1.25rem 1rem 0.75rem")};
  width: ${(props) => (props.$isPiP ? "clamp(400px, 30vw, 500px)" : "420px")};
  ${(props) =>
    props.$isPiP &&
    `
    max-height: min(600px, 80vh);
    display: flex;
    flex-direction: column;
  `}

  @media (max-width: 768px) {
    width: ${(props) =>
      props.$isPiP ? "calc(100vw - 3rem)" : "min(380px, calc(100vw - 3rem))"};
  }

  @media (max-width: 480px) {
    width: calc(100vw - 3rem);
    padding: ${(props) => (props.$isPiP ? "1.25rem" : "1rem 0.75rem 0.5rem")};
  }
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid rgba(226, 232, 240, 0.4);
  gap: 1rem;
  min-height: 42px;
  position: relative;

  &::after {
    content: "";
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 1px;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(59, 130, 246, 0.2),
      transparent
    );
    animation: shimmer 3s ease-in-out infinite;
  }

  @keyframes shimmer {
    0%,
    100% {
      transform: translateX(-100%);
    }
    50% {
      transform: translateX(100%);
    }
  }

  @media (max-width: 480px) {
    flex-wrap: wrap;
    gap: 0.75rem;
  }
`;

const Title = styled.h3`
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 0.5rem;

  svg {
    width: 18px;
    height: 18px;
    color: #3b82f6;
  }

  @media (max-width: 480px) {
    font-size: 0.875rem;

    svg {
      width: 16px;
      height: 16px;
    }
  }
`;

const ActionButtons = styled.div`
  display: flex;
  gap: 0.375rem;
  align-items: center;

  @media (max-width: 480px) {
    gap: 0.25rem;
    flex-wrap: wrap;
  }
`;

const ActionButton = styled(motion.button)`
  padding: 0.5rem 0.875rem;
  border-radius: 12px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.8);
  color: #64748b;
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04),
    inset 0 1px 2px rgba(255, 255, 255, 0.6);
  white-space: nowrap;
  position: relative;
  overflow: hidden;

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.4),
      transparent
    );
    transition: left 0.5s ease;
  }

  &:hover {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    color: #3b82f6;
    border-color: rgba(147, 197, 253, 0.3);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1),
      inset 0 1px 3px rgba(255, 255, 255, 0.8);

    &::before {
      left: 100%;
    }
  }

  &:active {
    transform: translateY(0);
  }

  svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    transition: transform 0.2s ease;
  }

  &:hover svg {
    transform: scale(1.1);
  }

  @media (max-width: 480px) {
    font-size: 0.75rem;
    padding: 0.4rem 0.7rem;

    svg {
      width: 14px;
      height: 14px;
    }
  }
`;

const ViewFullButton = styled(ActionButton)`
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  border-color: transparent;
  position: relative;

  &::after {
    content: "";
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(
      circle,
      rgba(255, 255, 255, 0.1) 0%,
      transparent 70%
    );
    animation: pulse 2s ease-in-out infinite;
    pointer-events: none;
  }

  @keyframes pulse {
    0%,
    100% {
      transform: scale(0.8);
      opacity: 0;
    }
    50% {
      transform: scale(1.2);
      opacity: 1;
    }
  }

  &:hover {
    background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
    border-color: transparent;
    color: white;
    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.3),
      inset 0 1px 3px rgba(255, 255, 255, 0.2);

    svg {
      transform: scale(1.2) rotate(5deg);
    }
  }
`;

const MinimizeButton = styled(ActionButton)`
  padding: 0.5rem;
  background: rgba(255, 255, 255, 0.6);

  &:hover {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    color: #d97706;
    border-color: rgba(251, 191, 36, 0.3);

    svg {
      transform: rotate(-90deg) scale(1.1);
    }
  }
`;

// New component for PiP content preview
const PiPContentPreview = styled.div`
  flex: 1;
  overflow-y: auto;
  margin-top: 1rem;
  padding: 1rem;
  background: rgba(248, 250, 252, 0.6);
  border-radius: 16px;
  border: 1px solid rgba(226, 232, 240, 0.4);
  max-height: 400px;

  @media (max-width: 480px) {
    padding: 0.75rem;
    margin-top: 0.75rem;
  }

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: rgba(226, 232, 240, 0.2);
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.5);
    border-radius: 3px;

    &:hover {
      background: rgba(148, 163, 184, 0.7);
    }
  }

  /* Markdown styling */
  font-size: 0.875rem;
  line-height: 1.6;
  color: #334155;

  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    margin-top: 1rem;
    margin-bottom: 0.5rem;
    color: #1e293b;
  }

  h1 {
    font-size: 1.25rem;
  }
  h2 {
    font-size: 1.125rem;
  }
  h3 {
    font-size: 1rem;
  }

  p {
    margin-bottom: 0.75rem;
  }

  ul,
  ol {
    margin-bottom: 0.75rem;
    padding-left: 1.5rem;
  }

  code {
    background: rgba(226, 232, 240, 0.5);
    padding: 0.125rem 0.25rem;
    border-radius: 4px;
    font-size: 0.8125rem;
  }

  pre {
    background: rgba(30, 41, 59, 0.05);
    padding: 0.75rem;
    border-radius: 8px;
    overflow-x: auto;
    margin-bottom: 0.75rem;
  }

  blockquote {
    border-left: 3px solid rgba(59, 130, 246, 0.5);
    padding-left: 1rem;
    margin: 0.75rem 0;
    font-style: italic;
    color: #64748b;
  }
`;

const StackWrapper = styled.div`
  position: relative;
  width: 100%;
  height: 240px;
  overflow: visible;
`;

export const FloatingSummaryPreview: React.FC<FloatingSummaryPreviewProps> = ({
  documentId,
  corpusId,
  documentTitle,
  isVisible = true,
  onSwitchToKnowledge,
  onBackToDocument,
  isInKnowledgeLayer = false,
  readOnly = false,
}) => {
  const [showTooltip, setShowTooltip] = useState(false);
  const { state, setExpanded, setStackFanned, setHovered } =
    useSummaryAnimation();

  const {
    versions,
    currentVersion,
    currentContent,
    loading,
    updateSummary,
    refetch,
  } = useSummaryVersions(documentId, corpusId);

  /* ------------------------------------------------------------------ */
  /* Refresh summary versions whenever the preview is expanded           */
  /* ------------------------------------------------------------------ */
  useEffect(() => {
    if (state.isExpanded) {
      // Trigger a background refetch so the version stack is fresh.
      // Apollo will serve cached data immediately and update when the
      // network response arrives, keeping the UI snappy.
      refetch();
    }
  }, [state.isExpanded, refetch]);

  const handleVersionClick = (version: number) => {
    if (version === currentVersion) {
      if (onSwitchToKnowledge) {
        onSwitchToKnowledge(currentContent || ""); // Pass content to knowledge layer
      }
      setExpanded(false);
    } else {
      const versionData = versions.find((v) => v.version === version);
      if (versionData && versionData.snapshot) {
        if (onSwitchToKnowledge) {
          onSwitchToKnowledge(versionData.snapshot); // Pass version content to knowledge layer
        }
        setExpanded(false);
      }
    }
  };

  // In knowledge layer, allow PiP mode
  if (isInKnowledgeLayer && isVisible) {
    return (
      <>
        <AnimatePresence>
          {!state.isExpanded ? (
            <FloatingContainer
              key="collapsed-knowledge"
              initial={{ opacity: 0, scale: 0.8, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.8, y: 20 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
            >
              <BackButton
                data-testid="back-to-document-button"
                onClick={() => {
                  if (onBackToDocument) {
                    onBackToDocument();
                  }
                }}
                onMouseEnter={() => setShowTooltip(true)}
                onMouseLeave={() => setShowTooltip(false)}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <IconWrapper>
                  <ArrowLeftFromLine size={24} />
                  <IconLabel>Back</IconLabel>
                </IconWrapper>
              </BackButton>
              <AnimatePresence>
                {showTooltip && (
                  <Tooltip
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 5 }}
                    transition={{ duration: 0.15 }}
                  >
                    Back to Document
                  </Tooltip>
                )}
              </AnimatePresence>
            </FloatingContainer>
          ) : (
            <FloatingContainer
              id="floating-summary-preview-floating-container"
              key="expanded-knowledge"
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              onMouseEnter={() => {
                setHovered(true);
                // Automatically fan the stack when hovering over the expanded container
                setStackFanned(true);
              }}
              onMouseLeave={() => {
                setHovered(false);
                setStackFanned(false);
              }}
            >
              <ExpandedContainer $isPiP>
                <Header>
                  <Title>
                    <BookOpen size={18} />
                    Document Summary (Preview)
                  </Title>
                  <ActionButtons>
                    <MinimizeButton
                      data-testid="minimize-button"
                      onClick={() => setExpanded(false)}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      title="Minimize"
                    >
                      <Minimize2 />
                    </MinimizeButton>
                  </ActionButtons>
                </Header>

                {/* Add markdown preview in PiP mode */}
                {currentContent && (
                  <PiPContentPreview>
                    <SafeMarkdown>{currentContent}</SafeMarkdown>
                  </PiPContentPreview>
                )}
              </ExpandedContainer>
            </FloatingContainer>
          )}
        </AnimatePresence>
      </>
    );
  }

  if (!isVisible) return null;

  return (
    <>
      <AnimatePresence>
        {!state.isExpanded ? (
          <FloatingContainer
            key="collapsed"
            initial={{ opacity: 0, scale: 0.8, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.8, y: 20 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
          >
            <CollapsedButton
              data-testid="summary-toggle-button"
              onClick={() => setExpanded(true)}
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <IconWrapper>
                <BookOpen size={24} />
                <IconLabel>Summary</IconLabel>
              </IconWrapper>
              {currentVersion && (
                <VersionBadge
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.2, type: "spring", stiffness: 500 }}
                >
                  v{currentVersion}
                </VersionBadge>
              )}
            </CollapsedButton>
            <AnimatePresence>
              {showTooltip && (
                <Tooltip
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 5 }}
                  transition={{ duration: 0.15 }}
                >
                  View Document Summary
                </Tooltip>
              )}
            </AnimatePresence>
          </FloatingContainer>
        ) : (
          <FloatingContainer
            key="expanded"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            onMouseEnter={() => {
              setHovered(true);
              // Automatically fan the stack when hovering over the expanded container
              setStackFanned(true);
            }}
            onMouseLeave={() => {
              setHovered(false);
              setStackFanned(false);
            }}
          >
            <ExpandedContainer>
              <Header>
                <Title>
                  <BookOpen size={18} />
                  Document Summary
                </Title>
                <ActionButtons>
                  <MinimizeButton
                    data-testid="minimize-button"
                    onClick={() => setExpanded(false)}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    title="Minimize"
                  >
                    <Minimize2 />
                  </MinimizeButton>
                  <ViewFullButton
                    onClick={() => {
                      if (onSwitchToKnowledge) {
                        onSwitchToKnowledge();
                      }
                      setExpanded(false);
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    title="View Full Screen"
                  >
                    <Maximize2 />
                    Full View
                  </ViewFullButton>
                </ActionButtons>
              </Header>

              <StackWrapper>
                <SummaryVersionStack
                  versions={versions || []}
                  isExpanded={state.isExpanded}
                  isFanned={state.isStackFanned}
                  onFanToggle={() => setStackFanned(!state.isStackFanned)}
                  onVersionClick={handleVersionClick}
                  loading={loading}
                  currentContent={currentContent}
                />
              </StackWrapper>
            </ExpandedContainer>
          </FloatingContainer>
        )}
      </AnimatePresence>
    </>
  );
};
