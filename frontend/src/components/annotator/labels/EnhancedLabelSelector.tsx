import React, {
  useState,
  useMemo,
  useEffect,
  useRef,
  useCallback,
} from "react";
import { createPortal } from "react-dom";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  MOBILE_ANNOTATION_TOOLS_BOTTOM,
  Z_INDEX,
} from "../../../assets/configurations/constants";
import {
  Tag,
  FileText,
  Plus,
  X,
  Tags,
  Search,
  AlertCircle,
  Lock,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation } from "@apollo/client";
import { isPdfFileType, isSpanBasedFileType } from "../../../utils/files";
import { visualViewportAwareBottom } from "../../../utils/layout";
import { toast } from "react-toastify";
import {
  AnnotationLabelType,
  LabelType,
  LabelSetType,
  CorpusType,
} from "../../../types/graphql-api";
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
import {
  SMART_LABEL_SEARCH_OR_CREATE,
  SmartLabelSearchOrCreateInputs,
  SmartLabelSearchOrCreateOutputs,
} from "../../../graphql/mutations";

interface EnhancedLabelSelectorProps {
  activeSpanLabel: AnnotationLabelType | null;
  setActiveLabel: (label: AnnotationLabelType | undefined) => void;
  sidebarWidth: string;
  labels?: AnnotationLabelType[];
  showRightPanel?: boolean;
  panelOffset?: number;
  hideControls?: boolean;
  readOnly?: boolean;
}

const MOBILE_ANNOTATION_TOOLS_Z_INDEX = Z_INDEX.MOBILE_ANNOTATION_TOOLS;
const ANNOTATION_LABEL_MODAL_Z_INDEX = Z_INDEX.MOBILE_ANNOTATION_LABEL_MODAL;

export const EnhancedLabelSelector: React.FC<EnhancedLabelSelectorProps> = ({
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

  // State
  const [isExpanded, setIsExpanded] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [showCreateLabelModal, setShowCreateLabelModal] = useState(false);
  const [showCreateLabelsetModal, setShowCreateLabelsetModal] = useState(false);
  const [newLabelText, setNewLabelText] = useState("");
  const [newLabelColor, setNewLabelColor] = useState<string>(
    OS_LEGAL_COLORS.primaryBlueHover
  );
  const [newLabelDescription, setNewLabelDescription] = useState("");
  const [newLabelsetTitle, setNewLabelsetTitle] = useState("");
  const [newLabelsetDescription, setNewLabelsetDescription] = useState("");
  const [showNoLabelsMessage, setShowNoLabelsMessage] = useState(false);

  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Hooks
  const { selectedDocument } = useSelectedDocument();
  const {
    humanSpanLabels,
    humanTokenLabels,
    docTypeLabels,
    canUpdateCorpus,
    selectedCorpus,
    setCorpus,
  } = useCorpusState();
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

  // GraphQL Mutations
  const [smartLabelSearchOrCreate] = useMutation<
    SmartLabelSearchOrCreateOutputs,
    SmartLabelSearchOrCreateInputs
  >(SMART_LABEL_SEARCH_OR_CREATE, {
    update: (cache, { data }) => {
      // Update the cache to include new labels
      if (data?.smartLabelSearchOrCreate?.labels) {
        const newLabels = data.smartLabelSearchOrCreate.labels;
        // The cache will automatically update based on the mutation response
        // This triggers a re-render of components using the updated data
      }
    },
  });

  // Determine label type based on document type
  const getLabelType = useCallback(() => {
    if (isSpanBasedFileType(selectedDocument?.fileType))
      return LabelType.SpanLabel;
    if (isPdfFileType(selectedDocument?.fileType)) return LabelType.TokenLabel;
    return LabelType.SpanLabel; // Default
  }, [selectedDocument?.fileType]);

  // Compute available labels
  const filteredLabelChoices = useMemo<AnnotationLabelType[]>(() => {
    let availableLabels: AnnotationLabelType[] = [];

    if (isSpanBasedFileType(selectedDocument?.fileType)) {
      availableLabels = [...humanSpanLabels];
    } else if (isPdfFileType(selectedDocument?.fileType)) {
      availableLabels = [...humanTokenLabels];
    }

    // Filter by search term
    if (searchTerm) {
      availableLabels = availableLabels.filter((label) =>
        label.text?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Exclude active label
    return activeSpanLabel
      ? availableLabels.filter((label) => label.id !== activeSpanLabel.id)
      : availableLabels;
  }, [
    humanSpanLabels,
    humanTokenLabels,
    selectedDocument?.fileType,
    activeSpanLabel,
    searchTerm,
  ]);

  const annotationLabelOptions =
    labels && labels.length > 0 ? labels : filteredLabelChoices;

  // Filter doc labels
  const existingDocLabels = useMemo(() => {
    return doc_annotations.map((annotation) => annotation.annotationLabel.id);
  }, [doc_annotations]);

  const filteredDocLabelChoices = useMemo(() => {
    return docTypeLabels.filter(
      (label) => !existingDocLabels.includes(label.id)
    );
  }, [docTypeLabels, existingDocLabels]);

  // Check if corpus has a labelset
  const hasLabelset = Boolean(selectedCorpus?.labelSet);

  // Handle creating a new label (with optional labelset creation)
  const handleCreateLabel = async (includeNewLabelset: boolean = false) => {
    if (!newLabelText.trim()) {
      toast.error("Please enter a label name");
      return;
    }

    if (!hasLabelset && !includeNewLabelset) {
      // Redirect to labelset creation modal
      setShowCreateLabelModal(false);
      setShowCreateLabelsetModal(true);
      return;
    }

    try {
      const result = await smartLabelSearchOrCreate({
        variables: {
          corpusId: selectedCorpus?.id!,
          searchTerm: newLabelText,
          labelType: getLabelType(),
          color: newLabelColor,
          description: newLabelDescription,
          createIfNotFound: true,
          labelsetTitle: includeNewLabelset
            ? newLabelsetTitle || `${selectedCorpus?.title} Labels`
            : undefined,
          labelsetDescription: includeNewLabelset
            ? newLabelsetDescription
            : undefined,
        },
      });

      if (result.data?.smartLabelSearchOrCreate?.ok) {
        const { labels, labelsetCreated, labelCreated } =
          result.data.smartLabelSearchOrCreate;

        if (labels && labels.length > 0) {
          const newLabel = labels[0];

          // Update the corpus state with the new label
          if (labelCreated || labelsetCreated) {
            const labelType = getLabelType();

            // Add the new label to the appropriate label list in corpus state
            if (labelType === LabelType.SpanLabel) {
              setCorpus({
                humanSpanLabels: [...humanSpanLabels, newLabel],
                spanLabels: [
                  ...(selectedCorpus?.labelSet?.allAnnotationLabels || []),
                  newLabel,
                ],
              });
            } else if (labelType === LabelType.TokenLabel) {
              setCorpus({
                humanTokenLabels: [...humanTokenLabels, newLabel],
              });
            }

            // If a labelset was created, update the corpus to reflect it
            if (labelsetCreated && selectedCorpus) {
              const newLabelset = result.data.smartLabelSearchOrCreate.labelset;
              if (newLabelset) {
                setCorpus({
                  selectedCorpus: {
                    ...selectedCorpus,
                    labelSet: newLabelset,
                  } as CorpusType,
                });
              }
            }
          }

          // Set the active label
          setActiveLabel(newLabel);

          // Show appropriate success message
          if (labelsetCreated && labelCreated) {
            toast.success(`Created labelset and label "${newLabelText}"`);
          } else if (labelCreated) {
            toast.success(`Created label "${newLabelText}"`);
          } else {
            toast.info(`Selected existing label "${newLabelText}"`);
          }

          // Close modals and reset
          setShowCreateLabelModal(false);
          setShowCreateLabelsetModal(false);
          setNewLabelText("");
          setNewLabelDescription("");
          setNewLabelsetTitle("");
          setNewLabelsetDescription("");
          setIsExpanded(false);
        }
      } else {
        toast.error(
          result.data?.smartLabelSearchOrCreate?.message ||
            "Failed to create label"
        );
      }
    } catch (error) {
      console.error("Error creating label:", error);
      toast.error("Failed to create label");
    }
  };

  // Handle doc type label toggle
  const handleDocLabelToggle = useCallback(
    (label: AnnotationLabelType) => {
      const existingAnnotation = doc_annotations.find(
        (ann) => ann.annotationLabel.id === label.id
      );

      if (existingAnnotation) {
        deleteDocTypeAnnotation(existingAnnotation.id);
      } else {
        createDocTypeAnnotation(label);
      }
    },
    [doc_annotations, createDocTypeAnnotation, deleteDocTypeAnnotation]
  );

  // Mouse handlers
  const handleMouseEnter = (): void => {
    if (isMobile || isReadOnlyMode) return;
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setIsExpanded(true);
  };

  const handleMouseLeave = (): void => {
    if (isMobile || isReadOnlyMode) return;
    timeoutRef.current = setTimeout(() => {
      setIsExpanded(false);
      setSearchTerm("");
    }, 300);
  };

  const handleSelectorClick = (): void => {
    if (isReadOnlyMode) return;
    if (!isMobile) return;
    setIsExpanded(!isExpanded);
  };

  // Check for no labels condition and show message
  useEffect(() => {
    if (!hasLabelset && isExpanded && !readOnly) {
      setShowNoLabelsMessage(true);
    }
  }, [hasLabelset, isExpanded, readOnly]);

  // Hide controls when needed - but show in read-only mode for tests
  if (hideControls && !readOnly) return null;

  // Calculate position based on panel offset
  const calculatePosition = () => {
    if (isMobile) {
      return { $bottom: "1rem", $right: "1rem" };
    }
    return {
      $bottom: "2.5rem",
      $right: panelOffset > 0 ? `${panelOffset + 24}px` : "1.5rem",
    };
  };

  const annotationControls = (
    <>
      <StyledEnhancedSelector
        {...calculatePosition()}
        $isExpanded={isExpanded}
        $isReadOnly={isReadOnlyMode}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={handleSelectorClick}
        ref={componentRef}
        data-testid="annotation-tools"
        title={
          isReadOnlyMode
            ? "Annotation tools are disabled in read-only mode"
            : undefined
        }
      >
        <motion.div
          className="selector-button"
          data-testid="label-selector-toggle-button"
          animate={{
            scale: activeSpanLabel && !isReadOnlyMode ? 1.05 : 1,
            boxShadow:
              activeSpanLabel && !isReadOnlyMode
                ? "0 8px 32px rgba(26, 117, 188, 0.15)"
                : "0 4px 24px rgba(0, 0, 0, 0.08)",
          }}
        >
          <Tag className="tag-icon" size={24} />
          {isReadOnlyMode && <Lock className="lock-icon" size={14} />}
          {activeSpanLabel && (
            <motion.div
              className="active-label-display"
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: "auto" }}
            >
              <span
                className="color-dot"
                style={{
                  backgroundColor:
                    activeSpanLabel.color || OS_LEGAL_COLORS.primaryBlueHover,
                }}
              />
              <span>{activeSpanLabel.text}</span>
              <button
                className="clear-button"
                onClick={(e) => {
                  e.stopPropagation();
                  setActiveLabel(undefined);
                  if (isMobile) setIsExpanded(false);
                }}
                disabled={isReadOnlyMode}
              >
                ×
              </button>
            </motion.div>
          )}
        </motion.div>

        <AnimatePresence>
          {isExpanded && (
            <motion.div
              className="labels-menu"
              data-testid="label-selector-dropdown"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
            >
              {/* Search input */}
              <div className="search-container">
                <Search size={16} className="search-icon" />
                <input
                  type="text"
                  placeholder="Search or create label..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="search-input"
                  autoFocus={!isMobile}
                />
              </div>

              {/* Show message if no labelset exists */}
              {!hasLabelset && !readOnly && (
                <div className="no-labelset-message">
                  <AlertCircle size={16} />
                  <span>No labelset configured</span>
                  <button
                    className="create-labelset-link"
                    onClick={() => {
                      setNewLabelText(searchTerm);
                      setShowCreateLabelsetModal(true);
                      setIsExpanded(false);
                    }}
                  >
                    Create one
                  </button>
                </div>
              )}

              {/* Annotation Labels */}
              {hasLabelset && (
                <>
                  <div className="label-section">
                    <div className="section-title">Annotation Labels</div>
                    {annotationLabelOptions.length > 0 ? (
                      annotationLabelOptions.map((label) => (
                        <button
                          key={label.id}
                          onClick={() => {
                            setActiveLabel(label);
                            setIsExpanded(false);
                            setSearchTerm("");
                          }}
                          className={`label-option ${
                            activeSpanLabel?.id === label.id ? "active" : ""
                          }`}
                        >
                          <span
                            className="color-dot"
                            style={{
                              backgroundColor:
                                label.color || OS_LEGAL_COLORS.primaryBlueHover,
                            }}
                          />
                          {label.text}
                        </button>
                      ))
                    ) : searchTerm ? (
                      <button
                        className="create-label-button"
                        onClick={() => {
                          setNewLabelText(searchTerm);
                          setShowCreateLabelModal(true);
                          setIsExpanded(false);
                        }}
                      >
                        <Plus size={16} />
                        Create "{searchTerm}"
                      </button>
                    ) : (
                      <div className="empty-state">No labels available</div>
                    )}
                  </div>

                  {/* Document Labels */}
                  {filteredDocLabelChoices.length > 0 && (
                    <div className="label-section">
                      <div className="section-title">Document Labels</div>
                      {filteredDocLabelChoices.map((label) => {
                        const isApplied = existingDocLabels.includes(label.id);
                        return (
                          <button
                            key={label.id}
                            onClick={() => handleDocLabelToggle(label)}
                            className={`label-option ${
                              isApplied ? "active" : ""
                            }`}
                          >
                            <FileText
                              size={16}
                              className="doc-icon"
                              style={{ color: label.color || "#6b7280" }}
                            />
                            {label.text}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </StyledEnhancedSelector>

      {/* Create Label Modal */}
      {showCreateLabelModal && (
        <ModalOverlay onClick={() => setShowCreateLabelModal(false)}>
          <ModalContainer
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            onClick={(e) => e.stopPropagation()}
          >
            <ModalHeader>
              <ModalTitle>Create New Label</ModalTitle>
              <ModalSubtitle>
                Add a new label to annotate text in your documents
              </ModalSubtitle>
              <CloseButton
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setShowCreateLabelModal(false)}
              >
                <X />
              </CloseButton>
            </ModalHeader>
            <ModalBody>
              <StyledForm>
                <FormSection>
                  <Label>
                    Label Name <span className="required">*</span>
                  </Label>
                  <StyledInput
                    value={newLabelText}
                    onChange={(e) => setNewLabelText(e.target.value)}
                    placeholder="Enter a descriptive label name"
                    autoFocus
                  />
                </FormSection>
                <FormSection>
                  <Label>Color</Label>
                  <ColorPickerWrapper>
                    <ColorPreview color={newLabelColor}>
                      <ColorSwatch color={newLabelColor} />
                      <span>{newLabelColor}</span>
                    </ColorPreview>
                    <StyledColorInput
                      type="color"
                      value={newLabelColor}
                      onChange={(e) => setNewLabelColor(e.target.value)}
                    />
                  </ColorPickerWrapper>
                  <HelperText>
                    Choose a color to visually distinguish this label
                  </HelperText>
                </FormSection>
                <FormSection>
                  <Label>Description</Label>
                  <StyledTextarea
                    value={newLabelDescription}
                    onChange={(e) => setNewLabelDescription(e.target.value)}
                    placeholder="Optional: Describe when to use this label"
                    rows={3}
                  />
                </FormSection>
              </StyledForm>
            </ModalBody>
            <ModalFooter>
              <FooterInfo>
                Labels help organize and categorize your annotations
              </FooterInfo>
              <ButtonGroup>
                <StyledButton
                  $variant="secondary"
                  onClick={() => setShowCreateLabelModal(false)}
                >
                  Cancel
                </StyledButton>
                <StyledButton
                  $variant="primary"
                  onClick={() => handleCreateLabel(false)}
                  disabled={!newLabelText.trim()}
                >
                  Create Label
                </StyledButton>
              </ButtonGroup>
            </ModalFooter>
          </ModalContainer>
        </ModalOverlay>
      )}

      {/* Create Labelset Modal */}
      {showCreateLabelsetModal && (
        <ModalOverlay onClick={() => setShowCreateLabelsetModal(false)}>
          <ModalContainer
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            onClick={(e) => e.stopPropagation()}
          >
            <ModalHeader>
              <ModalTitle>Create Labelset & Label</ModalTitle>
              <ModalSubtitle>
                Set up a new labelset for this corpus and add your first label
              </ModalSubtitle>
              <CloseButton
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setShowCreateLabelsetModal(false)}
              >
                <X />
              </CloseButton>
            </ModalHeader>
            <ModalBody>
              <InfoMessage>
                <AlertCircle size={20} />
                <div>
                  <strong>No labelset exists for this corpus</strong>
                  <p>
                    Create a labelset to organize your labels, then add your
                    label to it.
                  </p>
                </div>
              </InfoMessage>

              <StyledForm>
                <SectionDivider>
                  <SectionTitle>Labelset Configuration</SectionTitle>
                </SectionDivider>

                <FormSection>
                  <Label>
                    Labelset Name <span className="required">*</span>
                  </Label>
                  <StyledInput
                    value={newLabelsetTitle}
                    onChange={(e) => setNewLabelsetTitle(e.target.value)}
                    placeholder="e.g., Contract Analysis Labels"
                    autoFocus
                  />
                  <HelperText>
                    Give your labelset a clear, descriptive name
                  </HelperText>
                </FormSection>

                <FormSection>
                  <Label>Labelset Description</Label>
                  <StyledTextarea
                    value={newLabelsetDescription}
                    onChange={(e) => setNewLabelsetDescription(e.target.value)}
                    placeholder="Optional: Describe the purpose of this labelset"
                    rows={2}
                  />
                </FormSection>

                <SectionDivider>
                  <SectionTitle>Initial Label</SectionTitle>
                </SectionDivider>

                <FormSection>
                  <Label>
                    Label Name <span className="required">*</span>
                  </Label>
                  <StyledInput
                    value={newLabelText}
                    onChange={(e) => setNewLabelText(e.target.value)}
                    placeholder="Enter your first label name"
                  />
                </FormSection>

                <FormSection>
                  <Label>Label Color</Label>
                  <ColorPickerWrapper>
                    <ColorPreview color={newLabelColor}>
                      <ColorSwatch color={newLabelColor} />
                      <span>{newLabelColor}</span>
                    </ColorPreview>
                    <StyledColorInput
                      type="color"
                      value={newLabelColor}
                      onChange={(e) => setNewLabelColor(e.target.value)}
                    />
                  </ColorPickerWrapper>
                </FormSection>

                <FormSection>
                  <Label>Label Description</Label>
                  <StyledTextarea
                    value={newLabelDescription}
                    onChange={(e) => setNewLabelDescription(e.target.value)}
                    placeholder="Optional: Describe when to use this label"
                    rows={2}
                  />
                </FormSection>
              </StyledForm>
            </ModalBody>
            <ModalFooter>
              <FooterInfo>
                This will create both the labelset and your first label
              </FooterInfo>
              <ButtonGroup>
                <StyledButton
                  $variant="secondary"
                  onClick={() => setShowCreateLabelsetModal(false)}
                >
                  Cancel
                </StyledButton>
                <StyledButton
                  $variant="primary"
                  onClick={() => handleCreateLabel(true)}
                  disabled={!newLabelText.trim()}
                >
                  Create Labelset & Label
                </StyledButton>
              </ButtonGroup>
            </ModalFooter>
          </ModalContainer>
        </ModalOverlay>
      )}
    </>
  );

  if (isMobile) {
    return createPortal(annotationControls, document.body);
  }

  return annotationControls;
};

interface StyledEnhancedSelectorProps {
  $isExpanded: boolean;
  $isReadOnly: boolean;
  $bottom: string;
  $right: string;
}

const StyledEnhancedSelector = styled.div<StyledEnhancedSelectorProps>`
  position: fixed;
  bottom: ${(props) => props.$bottom};
  right: ${(props) => props.$right};
  z-index: 1000;
  transition: all 0.3s cubic-bezier(0.19, 1, 0.22, 1);
  opacity: ${(props) => (props.$isReadOnly ? 0.6 : 1)};
  filter: ${(props) => (props.$isReadOnly ? "grayscale(0.3)" : "none")};

  @media (max-width: 768px) {
    bottom: ${visualViewportAwareBottom(MOBILE_ANNOTATION_TOOLS_BOTTOM)};
    right: 1rem;
    z-index: ${MOBILE_ANNOTATION_TOOLS_Z_INDEX};
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
    flex-shrink: 0;
    cursor: ${(props) => (props.$isReadOnly ? "not-allowed" : "pointer")};
    position: relative;
    transition: all 0.3s cubic-bezier(0.19, 1, 0.22, 1);

    .tag-icon {
      color: ${(props) =>
        props.$isReadOnly
          ? OS_LEGAL_COLORS.textMuted
          : OS_LEGAL_COLORS.primaryBlueHover};
      stroke-width: 2.2;
      transition: all 0.3s;
    }

    .lock-icon {
      position: absolute;
      top: 8px;
      right: 8px;
      color: #6b7280;
      background: rgba(255, 255, 255, 0.9);
      border-radius: 50%;
      padding: 2px;
    }

    &:hover {
      transform: ${(props) =>
        props.$isReadOnly ? "none" : "translateY(-2px)"};
    }
  }

  .active-label-display {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    color: ${OS_LEGAL_COLORS.textTertiary};

    .color-dot {
      width: 8px;
      height: 8px;
      border-radius: 4px;
      flex-shrink: 0;
    }

    .clear-button {
      background: none;
      border: none;
      color: ${OS_LEGAL_COLORS.textSecondary};
      font-size: 1.2rem;
      width: 20px;
      height: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      margin-left: 4px;
      border-radius: 50%;
      cursor: pointer;
      transition: all 0.2s;

      &:hover:not(:disabled) {
        background: rgba(0, 0, 0, 0.05);
        color: ${OS_LEGAL_COLORS.dangerBorderHover};
      }

      &:disabled {
        cursor: not-allowed;
        opacity: 0.5;
      }
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
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-width: 280px;
    max-width: 320px;
    max-height: 400px;
    overflow-y: auto;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.12);
    border: 1px solid rgba(200, 200, 200, 0.8);

    .search-container {
      position: relative;
      display: flex;
      align-items: center;
      padding: 0.5rem;
      background: rgba(248, 249, 250, 0.8);
      border-radius: 8px;
      border: 1px solid rgba(200, 200, 200, 0.5);

      .search-icon {
        position: absolute;
        left: 12px;
        color: ${OS_LEGAL_COLORS.textSecondary};
        pointer-events: none;
      }

      .search-input {
        flex: 1;
        border: none;
        background: transparent;
        padding: 0.25rem 0.5rem 0.25rem 2rem;
        font-size: 0.875rem;
        outline: none;
        color: ${OS_LEGAL_COLORS.textPrimary};

        &::placeholder {
          color: ${OS_LEGAL_COLORS.textMuted};
        }
      }
    }

    .no-labelset-message {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.75rem;
      background: rgba(254, 243, 199, 0.5);
      border: 1px solid rgba(251, 191, 36, 0.3);
      border-radius: 8px;
      font-size: 0.875rem;
      color: #92400e;

      svg {
        flex-shrink: 0;
        color: #f59e0b;
      }

      .create-labelset-link {
        margin-left: auto;
        background: none;
        border: none;
        color: #1a75bc;
        font-weight: 600;
        cursor: pointer;
        text-decoration: underline;
        font-size: 0.875rem;

        &:hover {
          color: #1557a0;
        }
      }
    }

    .label-section {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;

      .section-title {
        font-size: 0.75rem;
        font-weight: 600;
        color: ${OS_LEGAL_COLORS.textSecondary};
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 0 0.5rem;
      }
    }

    button {
      border: none;
      background: transparent;
      padding: 0.75rem 1rem;
      cursor: pointer;
      border-radius: 10px;
      font-size: 0.875rem;
      font-weight: 500;
      color: ${OS_LEGAL_COLORS.textTertiary};
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
        flex-shrink: 0;
      }

      .doc-icon {
        flex-shrink: 0;
      }

      &:hover {
        background: rgba(0, 0, 0, 0.03);
        color: ${OS_LEGAL_COLORS.textPrimary};

        .color-dot {
          transform: scale(1.2);
        }
      }

      &.active {
        color: #1a75bc;
        font-weight: 600;
        background: rgba(26, 117, 188, 0.08);

        .color-dot {
          transform: scale(1.3);
        }
      }

      &.create-label-button {
        background: rgba(26, 117, 188, 0.08);
        color: #1a75bc;
        font-weight: 600;

        &:hover {
          background: rgba(26, 117, 188, 0.12);
        }
      }
    }

    .empty-state {
      padding: 0.75rem 1rem;
      color: ${OS_LEGAL_COLORS.textSecondary};
      font-size: 0.875rem;
      text-align: center;
      font-style: italic;
    }
  }
`;

// Modal Styled Components
const ModalOverlay = styled.div`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: ${ANNOTATION_LABEL_MODAL_Z_INDEX};
  padding: 2rem;
`;

const ModalContainer = styled(motion.div)`
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1),
    0 10px 10px -5px rgba(0, 0, 0, 0.04);
  width: 100%;
  max-width: 560px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;

  @media (max-width: 768px) {
    max-width: 100%;
    max-height: 100vh;
    border-radius: 0;
  }
`;

const ModalHeader = styled.div`
  padding: 2rem 2.5rem 1.75rem;
  border-bottom: 1px solid #e5e7eb;
  position: relative;
  background: linear-gradient(
    to bottom,
    #fbfcfd 0%,
    ${OS_LEGAL_COLORS.gray50} 100%
  );
`;

const ModalTitle = styled.h2`
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
`;

const ModalSubtitle = styled.p`
  margin: 0.625rem 0 0;
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.5;
  max-width: 85%;
`;

const CloseButton = styled(motion.button)`
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: none;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);

  svg {
    width: 20px;
    height: 20px;
    color: #6b7280;
  }

  &:hover {
    background: #f3f4f6;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);

    svg {
      color: #374151;
    }
  }
`;

const ModalBody = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 2rem 2.5rem 2.5rem;
  background: white;

  @media (max-width: 768px) {
    padding: 1.5rem;
  }
`;

const StyledForm = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
`;

const FormSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
`;

const Label = styled.label`
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  letter-spacing: 0.025em;

  .required {
    color: ${OS_LEGAL_COLORS.danger};
    font-weight: 400;
  }
`;

const StyledInput = styled.input`
  width: 100%;
  padding: 0.75rem 1rem;
  font-size: 0.9375rem;
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  transition: all 0.2s ease;
  background: #ffffff;
  color: #0f172a;

  &:hover:not(:focus) {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    background: #fafbfc;
  }

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12);
    background: #ffffff;
  }

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const StyledTextarea = styled.textarea`
  width: 100%;
  padding: 0.75rem 1rem;
  font-size: 0.9375rem;
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  transition: all 0.2s ease;
  background: #ffffff;
  color: #0f172a;
  resize: vertical;
  font-family: inherit;
  line-height: 1.5;

  &:hover:not(:focus) {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    background: #fafbfc;
  }

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12);
    background: #ffffff;
  }

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const ColorPickerWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
`;

const ColorPreview = styled.div<{ color: string }>`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 1rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textTertiary};
  font-weight: 500;
  min-width: 140px;
`;

const ColorSwatch = styled.div<{ color: string }>`
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background-color: ${(props) => props.color};
  border: 2px solid white;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.1);
`;

const StyledColorInput = styled.input`
  width: 48px;
  height: 48px;
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  cursor: pointer;
  background: white;
  padding: 4px;

  &::-webkit-color-swatch-wrapper {
    padding: 0;
  }

  &::-webkit-color-swatch {
    border: none;
    border-radius: 6px;
  }

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12);
  }
`;

const HelperText = styled.p`
  margin: 0.25rem 0 0;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.5;
`;

const InfoMessage = styled.div`
  display: flex;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  background: ${OS_LEGAL_COLORS.blueSurface};
  border: 1.5px solid ${OS_LEGAL_COLORS.blueBorder};
  border-radius: 10px;
  margin-bottom: 1.75rem;
  color: ${OS_LEGAL_COLORS.blueDark};

  svg {
    flex-shrink: 0;
    margin-top: 0.125rem;
  }

  div {
    flex: 1;
  }

  strong {
    display: block;
    font-weight: 600;
    font-size: 0.9375rem;
    margin-bottom: 0.25rem;
  }

  p {
    margin: 0;
    font-size: 0.875rem;
    color: ${OS_LEGAL_COLORS.blueDark};
    opacity: 0.9;
  }
`;

const SectionDivider = styled.div`
  position: relative;
  margin: 0.5rem 0;
`;

const SectionTitle = styled.h3`
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: white;
  display: inline-block;
  padding-right: 0.75rem;
  position: relative;

  &::after {
    content: "";
    position: absolute;
    top: 50%;
    left: 100%;
    width: 500px;
    height: 1px;
    background: ${OS_LEGAL_COLORS.border};
  }
`;

const ModalFooter = styled.div`
  padding: 1.5rem 2.5rem 1.75rem;
  border-top: 1px solid #e5e7eb;
  background: linear-gradient(
    to top,
    #fbfcfd 0%,
    ${OS_LEGAL_COLORS.gray50} 100%
  );
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;

  @media (max-width: 640px) {
    flex-direction: column-reverse;
    padding: 1.25rem 1.5rem;
  }
`;

const FooterInfo = styled.div`
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: flex;
  align-items: center;
  gap: 0.5rem;

  @media (max-width: 640px) {
    text-align: center;
  }
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 0.75rem;

  @media (max-width: 640px) {
    width: 100%;
    flex-direction: column-reverse;
  }
`;

const StyledButton = styled(motion.button)<{
  $variant?: "primary" | "secondary";
}>`
  padding: 0.625rem 1.25rem;
  border-radius: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  min-width: 100px;
  height: 40px;

  ${(props) =>
    props.$variant === "primary"
      ? `
    background: ${OS_LEGAL_COLORS.primaryBlue};
    color: white;
    border: 1.5px solid ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);

    &:hover:not(:disabled) {
      background: ${OS_LEGAL_COLORS.primaryBlueHover};
      border-color: ${OS_LEGAL_COLORS.primaryBlueHover};
      box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.1);
      transform: translateY(-0.5px);
    }

    &:active:not(:disabled) {
      transform: translateY(0);
      box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }

    &:disabled {
      background: ${OS_LEGAL_COLORS.textMuted};
      border-color: ${OS_LEGAL_COLORS.textMuted};
      cursor: not-allowed;
      opacity: 1;
    }
  `
      : `
    background: white;
    color: ${OS_LEGAL_COLORS.textTertiary};
    border: 1.5px solid ${OS_LEGAL_COLORS.border};
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);

    &:hover:not(:disabled) {
      background: ${OS_LEGAL_COLORS.surfaceHover};
      border-color: ${OS_LEGAL_COLORS.borderHover};
      color: #334155;
      transform: translateY(-0.5px);
    }

    &:active:not(:disabled) {
      transform: translateY(0);
    }
  `}

  @media (max-width: 640px) {
    width: 100%;
  }
`;

export default EnhancedLabelSelector;
