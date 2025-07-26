import React, { useState, useMemo, useEffect, useRef } from "react";
import styled from "styled-components";
import { Tag, FileText, Plus, X, Tags } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { AnnotationLabelType, LabelType } from "../../../types/graphql-api";
import { PermissionTypes } from "../../types";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { useCorpusState } from "../context/CorpusAtom";
import { useSelectedDocument } from "../context/DocumentAtom";
import { DocTypeAnnotation } from "../types/annotations";
import {
  useAddDocTypeAnnotation,
  useDeleteDocTypeAnnotation,
  usePdfAnnotations,
} from "../hooks/AnnotationHooks";
import { useReactiveVar } from "@apollo/client";
import { selectedAnalysis, selectedExtract } from "../../../graphql/cache";

interface UnifiedLabelSelectorProps {
  activeSpanLabel: AnnotationLabelType | null;
  setActiveLabel: (label: AnnotationLabelType | undefined) => void;
  sidebarWidth: string;
  labels?: AnnotationLabelType[];
  showRightPanel?: boolean;
  panelOffset?: number;
  hideControls?: boolean;
  readOnly?: boolean;
}

export const UnifiedLabelSelector: React.FC<UnifiedLabelSelectorProps> = ({
  activeSpanLabel,
  setActiveLabel,
  sidebarWidth,
  labels,
  showRightPanel,
  panelOffset = 0,
  hideControls = false,
  readOnly = false,
}) => {
  const { width } = useWindowDimensions();
  const isMobile = width <= 768;
  const componentRef = useRef<HTMLDivElement>(null);

  // State and hooks
  const [isExpanded, setIsExpanded] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const { selectedDocument } = useSelectedDocument();
  const { humanSpanLabels, humanTokenLabels, docTypeLabels, canUpdateCorpus } =
    useCorpusState();
  const { pdfAnnotations } = usePdfAnnotations();
  const deleteDocTypeAnnotation = useDeleteDocTypeAnnotation();
  const createDocTypeAnnotation = useAddDocTypeAnnotation();

  const selected_extract = useReactiveVar(selectedExtract);
  const selected_analysis = useReactiveVar(selectedAnalysis);
  const isReadOnlyMode =
    readOnly ||
    Boolean(selected_analysis) ||
    Boolean(selected_extract) ||
    !canUpdateCorpus;

  const doc_annotations = pdfAnnotations.docTypes;

  // Compute annotation label choices based on document type
  const filteredLabelChoices = useMemo<AnnotationLabelType[]>(() => {
    const isTextFile = selectedDocument?.fileType?.startsWith("text/") ?? false;
    const isPdfFile = selectedDocument?.fileType === "application/pdf";
    let availableLabels: AnnotationLabelType[] = [];

    if (isTextFile) {
      availableLabels = [...humanSpanLabels];
    } else if (isPdfFile) {
      availableLabels = [...humanTokenLabels];
    }

    return activeSpanLabel
      ? availableLabels.filter((label) => label.id !== activeSpanLabel.id)
      : availableLabels;
  }, [
    humanSpanLabels,
    humanTokenLabels,
    selectedDocument?.fileType,
    activeSpanLabel,
  ]);

  const annotationLabelOptions =
    labels && labels.length > 0 ? labels : filteredLabelChoices;

  // Filter out already applied doc labels
  const existingDocLabels = useMemo(() => {
    return doc_annotations.map((annotation) => annotation.annotationLabel.id);
  }, [doc_annotations]);

  const filteredDocLabelChoices = useMemo(() => {
    return docTypeLabels.filter(
      (label) => !existingDocLabels.includes(label.id)
    );
  }, [docTypeLabels, existingDocLabels]);

  // Event handlers
  const handleMouseEnter = (): void => {
    if (isMobile) return;
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setIsExpanded(true);
  };

  const handleMouseLeave = (): void => {
    if (isMobile) return;
    timeoutRef.current = setTimeout(() => setIsExpanded(false), 300);
  };

  const handleSelectorClick = (): void => {
    if (!isMobile) return;
    setIsExpanded(!isExpanded);
  };

  const handleAddDocType = (label: AnnotationLabelType) => {
    try {
      createDocTypeAnnotation(label);
    } catch (error) {
      console.error("Error creating doc type annotation:", error);
    }
  };

  const handleDeleteDocType = (doc_type_annotation: DocTypeAnnotation) => {
    try {
      deleteDocTypeAnnotation(doc_type_annotation.id);
    } catch (error) {
      console.error("Error deleting doc type annotation:", error);
    }
  };

  // Effects
  useEffect(() => {
    if (isMobile && !activeSpanLabel && doc_annotations.length === 0) {
      setIsExpanded(false);
    }
  }, [activeSpanLabel, doc_annotations.length, isMobile]);

  useEffect(() => {
    if (!isMobile) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        componentRef.current &&
        !componentRef.current.contains(event.target as Node)
      ) {
        setIsExpanded(false);
      }
    };

    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, [isMobile]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  // Calculate total active labels
  const totalActiveLabels = (activeSpanLabel ? 1 : 0) + doc_annotations.length;

  // Hide controls if requested
  if (hideControls) return null;

  return (
    <StyledUnifiedSelector
      ref={componentRef}
      isExpanded={isExpanded}
      sidebarWidth={sidebarWidth}
      showRightPanel={showRightPanel}
      panelOffset={panelOffset}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleSelectorClick}
    >
      <motion.div
        className="selector-button"
        data-testid="label-selector-toggle-button"
        animate={{
          scale: totalActiveLabels > 0 ? 1.05 : 1,
          boxShadow:
            totalActiveLabels > 0
              ? "0 8px 32px rgba(26, 117, 188, 0.15)"
              : "0 4px 24px rgba(0, 0, 0, 0.08)",
        }}
      >
        <Tags className="main-icon" size={24} />

        {totalActiveLabels > 0 && (
          <motion.div
            className="active-labels-preview"
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: "auto" }}
          >
            {activeSpanLabel && (
              <div className="label-chip annotation-label">
                <span
                  className="color-dot"
                  style={{
                    backgroundColor: activeSpanLabel.color || "#1a75bc",
                  }}
                />
                <span className="label-text">{activeSpanLabel.text}</span>
                <button
                  className="clear-button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveLabel(undefined);
                  }}
                >
                  ×
                </button>
              </div>
            )}
            {doc_annotations.length > 0 && (
              <div className="doc-labels-count">
                <FileText size={14} />
                <span>{doc_annotations.length}</span>
              </div>
            )}
          </motion.div>
        )}

        {totalActiveLabels > 0 && (
          <motion.div
            className="active-indicator"
            layoutId="activeLabels"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
          />
        )}
      </motion.div>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            className="labels-menu"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
          >
            {/* Annotation Labels Section */}
            <div className="menu-section">
              <div className="section-header">
                <Tag size={14} />
                <span>Annotation Label</span>
              </div>

              {activeSpanLabel && (
                <div className="active-section">
                  <div className="label-chip active">
                    <span
                      className="color-dot"
                      style={{
                        backgroundColor: activeSpanLabel.color || "#1a75bc",
                      }}
                    />
                    <span>{activeSpanLabel.text}</span>
                    {!isReadOnlyMode && (
                      <button
                        className="clear-button"
                        onClick={() => setActiveLabel(undefined)}
                      >
                        ×
                      </button>
                    )}
                  </div>
                </div>
              )}

              <div className="available-section">
                {annotationLabelOptions.length > 0 ? (
                  annotationLabelOptions.map((label) => (
                    <button
                      key={label.id}
                      onClick={() => !isReadOnlyMode && setActiveLabel(label)}
                      className="label-option"
                      disabled={isReadOnlyMode}
                      style={{
                        cursor: isReadOnlyMode ? "not-allowed" : "pointer",
                        opacity: isReadOnlyMode ? 0.5 : 1,
                      }}
                    >
                      <span
                        className="color-dot"
                        style={{ backgroundColor: label.color || "#1a75bc" }}
                      />
                      {label.text}
                    </button>
                  ))
                ) : (
                  <div className="empty-state">
                    {activeSpanLabel
                      ? "No other labels available"
                      : "No labels available for this document type"}
                  </div>
                )}
              </div>
            </div>

            <div className="menu-divider" />

            {/* Document Labels Section */}
            <div className="menu-section">
              <div className="section-header">
                <FileText size={14} />
                <span>Document Labels</span>
              </div>

              {doc_annotations.length > 0 && (
                <div className="active-section">
                  {doc_annotations.map((annotation) => (
                    <div key={annotation.id} className="label-chip">
                      <span
                        className="color-dot"
                        style={{
                          backgroundColor:
                            annotation.annotationLabel.color || "#1a75bc",
                        }}
                      />
                      <span>{annotation.annotationLabel.text}</span>
                      {!isReadOnlyMode &&
                        annotation.myPermissions.includes(
                          PermissionTypes.CAN_REMOVE
                        ) && (
                          <button
                            className="clear-button"
                            onClick={() => handleDeleteDocType(annotation)}
                          >
                            ×
                          </button>
                        )}
                    </div>
                  ))}
                </div>
              )}

              {!isReadOnlyMode && filteredDocLabelChoices.length > 0 ? (
                <div className="available-section">
                  {filteredDocLabelChoices.map((label) => (
                    <button
                      key={label.id}
                      className="label-option"
                      onClick={() => handleAddDocType(label)}
                    >
                      <Plus size={12} />
                      <span
                        className="color-dot"
                        style={{ backgroundColor: label.color || "#1a75bc" }}
                      />
                      <span>{label.text}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  {isReadOnlyMode
                    ? "Read-only mode"
                    : doc_annotations.length === 0
                    ? "No document labels assigned"
                    : "All labels assigned"}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </StyledUnifiedSelector>
  );
};

interface StyledSelectorProps {
  isExpanded: boolean;
  sidebarWidth: string;
  showRightPanel?: boolean;
  panelOffset?: number;
}

const StyledUnifiedSelector = styled.div<StyledSelectorProps>`
  position: fixed;
  bottom: 2rem;
  right: ${(props) =>
    props.panelOffset ? `${props.panelOffset + 24}px` : "1.5rem"};
  z-index: 100000;
  transition: right 0.3s cubic-bezier(0.19, 1, 0.22, 1);

  @media (max-width: 768px) {
    position: fixed;
    bottom: 1rem;
    right: 1rem;

    .selector-button {
      min-width: 40px !important;
      height: 40px !important;
      padding: 0 12px !important;
    }

    .main-icon {
      width: 20px !important;
      height: 20px !important;
    }

    .labels-menu {
      bottom: calc(100% + 8px) !important;
      max-width: 90vw !important;
      max-height: 70vh !important;
    }
  }

  .selector-button {
    min-width: 48px;
    height: 48px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(200, 200, 200, 0.8);
    display: flex;
    align-items: center;
    padding: 0 16px;
    gap: 12px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.19, 1, 0.22, 1);

    .main-icon {
      color: #1a75bc;
      stroke-width: 2.2;
      flex-shrink: 0;
    }

    .active-labels-preview {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .label-chip {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.875rem;
      font-weight: 500;
      color: #475569;

      .color-dot {
        width: 8px;
        height: 8px;
        border-radius: 4px;
        flex-shrink: 0;
      }

      .label-text {
        max-width: 150px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    .doc-labels-count {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 4px 8px;
      background: rgba(26, 117, 188, 0.1);
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 600;
      color: #1a75bc;
    }

    .clear-button {
      background: none;
      border: none;
      color: #64748b;
      font-size: 1.2rem;
      width: 20px;
      height: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      border-radius: 50%;
      cursor: pointer;
      transition: all 0.2s;
      flex-shrink: 0;

      &:hover {
        background: rgba(0, 0, 0, 0.05);
        color: #ef4444;
      }
    }

    .active-indicator {
      position: absolute;
      top: -4px;
      right: -4px;
      width: 12px;
      height: 12px;
      border-radius: 6px;
      background: #1a75bc;
      border: 2px solid white;
    }

    &:hover {
      transform: translateY(-2px);
    }
  }

  .labels-menu {
    position: absolute;
    bottom: calc(100% + 12px);
    right: 0;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(12px);
    border-radius: 14px;
    padding: 0.75rem;
    min-width: 280px;
    max-width: 400px;
    max-height: 500px;
    overflow-y: auto;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.12);
    border: 1px solid rgba(200, 200, 200, 0.8);

    .menu-section {
      &:not(:last-child) {
        margin-bottom: 0.75rem;
      }
    }

    .section-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      font-size: 0.75rem;
      text-transform: uppercase;
      color: #64748b;
      font-weight: 600;
      letter-spacing: 0.5px;
    }

    .menu-divider {
      height: 1px;
      background: rgba(200, 200, 200, 0.3);
      margin: 0.75rem 0;
    }

    .active-section,
    .available-section {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 0 8px;
    }

    .label-chip {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      background: rgba(26, 117, 188, 0.08);
      border-radius: 8px;
      font-size: 0.875rem;
      color: #1e293b;
      font-weight: 500;

      &.active {
        background: rgba(26, 117, 188, 0.12);
      }

      .color-dot {
        width: 8px;
        height: 8px;
        border-radius: 4px;
        flex-shrink: 0;
      }

      .clear-button {
        margin-left: auto;
        background: none;
        border: none;
        padding: 4px;
        color: #64748b;
        cursor: pointer;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;

        &:hover {
          background: rgba(0, 0, 0, 0.05);
          color: #ef4444;
        }
      }
    }

    .label-option {
      border: none;
      background: transparent;
      padding: 0.75rem 1rem;
      cursor: pointer;
      border-radius: 10px;
      font-size: 0.875rem;
      font-weight: 500;
      color: #475569;
      display: flex;
      align-items: center;
      gap: 0.75rem;
      position: relative;
      transition: all 0.2s;
      text-align: left;

      .color-dot {
        width: 8px;
        height: 8px;
        border-radius: 4px;
        transition: all 0.2s;
      }

      &:hover {
        background: rgba(0, 0, 0, 0.03);
        color: #1e293b;

        .color-dot {
          transform: scale(1.2);
        }
      }
    }

    .empty-state {
      padding: 0.75rem 1rem;
      color: #64748b;
      font-size: 0.875rem;
      text-align: center;
      font-style: italic;
    }
  }
`;

export default UnifiedLabelSelector;
