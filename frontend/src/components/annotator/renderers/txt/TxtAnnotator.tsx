/**
 * TxtAnnotator Component
 *
 * Renders text along with highlights for:
 * 1. Annotations (ServerSpanAnnotation).
 * 2. Search results, with a distinct highlight color to indicate matches.
 * 3. Chat sources, highlighted differently, also supporting a selected state.
 *
 * Overlapping highlights (e.g., a span that is both a search result and an annotation)
 * produce a multi-color linear gradient. We also show annotation labels upon hover.
 *
 * Once the user makes a selection, a new annotation is created (if allowed).
 *
 * The component smoothly scrolls to newly selected or updated annotations, chat sources,
 * or search result matches (if the user has made a selection).
 */

import React, { useState, useRef, useCallback, useEffect } from "react";
import styled, { keyframes, css } from "styled-components";
import { Modal, Button, Dropdown } from "semantic-ui-react";

import { AnnotationLabelType } from "../../../../types/graphql-api";
import { ServerSpanAnnotation } from "../../types/annotations";
import { PermissionTypes, TextSearchSpanResult } from "../../../types";
import { Label, LabelContainer, PaperContainer } from "./StyledComponents";
import RadialButtonCloud, { CloudButtonItem } from "./RadialButtonCloud";
import { hexToRgba } from "./utils";

/**
 * Shape of an individual text chunk used to render text spans.
 */
interface TextSpan {
  start: number;
  end: number;
  text: string;
  annotations: ServerSpanAnnotation[];
  isSearchResult?: boolean;
  isSelectedSearchResult?: boolean;
  isChatSource?: boolean;
  isSelectedChatSource: boolean;
  sourceId?: string;
}

/**
 * Props for the TxtAnnotator component.
 */
interface TxtAnnotatorProps {
  /** The raw text to annotate. */
  text: string;
  /** Array of existing annotations over the text. */
  annotations: ServerSpanAnnotation[];
  /** Array of search-result-based highlights. */
  searchResults: TextSearchSpanResult[];
  /** Callback to build and return a new annotation from user-selected text. */
  getSpan: (span: {
    start: number;
    end: number;
    text: string;
  }) => ServerSpanAnnotation;
  /** Array of visible label types, used to filter out hidden annotations. */
  visibleLabels: AnnotationLabelType[] | null;
  /** All available label types, for editing annotation labels. */
  availableLabels: AnnotationLabelType[];
  /** The currently selected annotation label type, unused here but available. */
  selectedLabelTypeId: string | null;
  /** Read-only mode disables annotation editing. */
  read_only: boolean;
  /** Indicates background data is loading. */
  data_loading?: boolean;
  /** Optional loading message. */
  loading_message?: string;
  /** Whether user can add new annotations. */
  allowInput: boolean;
  /** Zoom level (unused, but retained for future scaling logic). */
  zoom_level: number;
  /** Creates a new annotation in upstream data. */
  createAnnotation: (added_annotation_obj: ServerSpanAnnotation) => void;
  /** Updates an existing annotation in upstream data. */
  updateAnnotation: (updated_annotation: ServerSpanAnnotation) => void;
  /** Approves an annotation if permitted. */
  approveAnnotation?: (annot_id: string, comment?: string) => void;
  /** Rejects an annotation if permitted. */
  rejectAnnotation?: (annot_id: string, comment?: string) => void;
  /** Deletes an annotation. */
  deleteAnnotation: (annotation_id: string) => void;
  /** Maximum height of the scrollable container, if desired. */
  maxHeight?: string;
  /** Maximum width of the scrollable container, if desired. */
  maxWidth?: string;
  /** Array of selected annotation IDs for highlighting and scrolling. */
  selectedAnnotations: string[];
  /** Callback to set the array of selected annotation IDs. */
  setSelectedAnnotations: (annotations: string[]) => void;
  /** Whether structural annotations should be shown or hidden. */
  showStructuralAnnotations: boolean;
  /** Which search result index is currently "selected." */
  selectedSearchResultIndex?: number;
  /** Array of chat source highlight boundaries. */
  chatSources?: {
    start_index: number;
    end_index: number;
    sourceId: string;
    messageId: string;
  }[];
  /** Currently selected chat source ID, if any. */
  selectedChatSourceId?: string;
}

/** Used in the label rendering code to describe each label's bounding box. */
interface LabelRenderData {
  annotation: ServerSpanAnnotation;
  x: number;
  y: number;
  width: number;
  height: number;
  labelIndex: number;
}

/* Keyframes for glowing animations. */
const glowGreen = keyframes`
  0% {
    box-shadow: 0 0 5px rgba(0, 255, 0, 0.8);
  }
  50% {
    box-shadow: 0 0 15px rgba(0, 255, 0, 0.8);
  }
  100% {
    box-shadow: 0 0 5px rgba(0, 255, 0, 0.8);
  }
`;

const glowRed = keyframes`
  0% {
    box-shadow: 0 0 5px rgba(255, 0, 0, 0.8);
  }
  50% {
    box-shadow: 0 0 15px rgba(255, 0, 0, 0.8);
  }
  100% {
    box-shadow: 0 0 5px rgba(255, 0, 0, 0.8);
  }
`;

const AnnotatedSpan = styled.span<{
  approved?: boolean;
  rejected?: boolean;
  hasBorder?: boolean;
  borderColor?: string;
  zIndex?: number;
}>`
  position: relative;
  cursor: text;
  user-select: text;
  white-space: pre-wrap;

  ${(props) =>
    props.approved &&
    css`
      animation: ${glowGreen} 2s infinite;
      border: 1px solid green;
      border-radius: 2px;
    `}

  ${(props) =>
    props.rejected &&
    css`
      animation: ${glowRed} 2s infinite;
      border: 1px solid red;
      border-radius: 2px;
    `}

  ${(props) =>
    props.hasBorder &&
    css`
      border: 2px dashed ${props.borderColor || "#000"};
      border-radius: 4px;
    `}

  z-index: ${(props) => props.zIndex || 1};
`;

const ChatSourceIcon = styled.div<{ isSelected: boolean }>`
  position: absolute;
  left: -32px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${(props) =>
    props.isSelected ? "rgba(92, 124, 157, 0.25)" : "rgba(92, 124, 157, 0.15)"};
  border-radius: 50%;
  transition: all 0.2s ease;

  &::before {
    content: "";
    position: absolute;
    right: -8px;
    top: 50%;
    height: 2px;
    width: 8px;
    background: ${(props) =>
      props.isSelected
        ? "rgba(92, 124, 157, 0.25)"
        : "rgba(92, 124, 157, 0.15)"};
    transform: translateY(-50%);
  }

  &:hover {
    background: rgba(92, 124, 157, 0.35);
    transform: translateY(-50%) scale(1.1);

    &::before {
      background: rgba(92, 124, 157, 0.35);
    }
  }

  svg {
    width: 16px;
    height: 16px;
    fill: rgba(92, 124, 157, ${(props) => (props.isSelected ? "0.9" : "0.7")});
    transition: fill 0.2s ease;
  }

  &:hover svg {
    fill: rgba(92, 124, 157, 1);
  }
`;

/**
 * Convert a local selection offset to the global offset based on
 * an array of text spans. Each <span> is matched by data-span-index.
 *
 * @param node - The DOM node (anchor/focus).
 * @param localOffset - The local offset in the node.
 * @param spans - The array of text chunks.
 * @returns The global offset in the overall text, or null if not found.
 */
function getGlobalOffsetFromNode(
  node: Node | null,
  localOffset: number,
  spans: TextSpan[]
): number | null {
  if (!node) return null;

  let element: HTMLElement | null =
    node instanceof HTMLElement ? node : node.parentElement;
  while (element && !element.hasAttribute("data-span-index")) {
    element = element.parentElement;
  }
  if (!element) return null;

  const spanIndexAttr = element.getAttribute("data-span-index");
  if (!spanIndexAttr) return null;

  const spanIndex = parseInt(spanIndexAttr, 10);
  if (isNaN(spanIndex) || !spans[spanIndex]) return null;

  const spanInfo = spans[spanIndex];
  return spanInfo.start + localOffset;
}

/**
 * Builds a combined background style from multiple highlight layers.
 * If one or more highlight layers exist, they are merged with linear gradient.
 *
 * @param highlightColors - Array of color values for each layer.
 * @returns A style object with background styling covering the highlights.
 */
function buildCombinedBackgroundStyle(
  highlightColors: string[]
): React.CSSProperties {
  if (highlightColors.length === 0) {
    return {};
  } else if (highlightColors.length === 1) {
    return {
      backgroundColor: highlightColors[0],
    };
  } else {
    // Combine them into a linear gradient to show multiple highlights.
    return {
      backgroundImage: `linear-gradient(to right, ${highlightColors.join(
        ", "
      )})`,
    };
  }
}

const TxtAnnotator: React.FC<TxtAnnotatorProps> = ({
  text,
  annotations,
  searchResults,
  getSpan,
  visibleLabels,
  availableLabels,
  read_only,
  allowInput,
  createAnnotation,
  updateAnnotation,
  approveAnnotation,
  rejectAnnotation,
  deleteAnnotation,
  maxHeight,
  maxWidth,
  selectedAnnotations,
  setSelectedAnnotations,
  showStructuralAnnotations,
  selectedSearchResultIndex,
  chatSources = [],
  selectedChatSourceId,
}) => {
  const [hoveredSpanIndex, setHoveredSpanIndex] = useState<number | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [annotationToEdit, setAnnotationToEdit] =
    useState<ServerSpanAnnotation | null>(null);
  const [labelsToRender, setLabelsToRender] = useState<LabelRenderData[]>([]);
  const [spans, setSpans] = useState<TextSpan[]>([]);

  const containerRef = useRef<HTMLDivElement>(null);
  const hideLabelsTimeout = useRef<NodeJS.Timeout | null>(null);

  /**
   * Handle mouse enter on a specific span index.
   */
  const handleMouseEnter = useCallback((index: number) => {
    if (hideLabelsTimeout.current) {
      clearTimeout(hideLabelsTimeout.current);
      hideLabelsTimeout.current = null;
    }
    setHoveredSpanIndex(index);
  }, []);

  /**
   * Handle mouse leave from a specific span index, with a delayed hide of labels.
   */
  const handleMouseLeave = useCallback(() => {
    hideLabelsTimeout.current = setTimeout(() => {
      setHoveredSpanIndex(null);
    }, 1000);
  }, []);

  /**
   * Cancel label hiding when hovering over a label element.
   */
  const handleLabelMouseEnter = useCallback(() => {
    if (hideLabelsTimeout.current) {
      clearTimeout(hideLabelsTimeout.current);
      hideLabelsTimeout.current = null;
    }
  }, []);

  /**
   * Trigger label hiding when leaving the label area completely.
   */
  const handleLabelMouseLeave = useCallback(() => {
    hideLabelsTimeout.current = setTimeout(() => {
      setHoveredSpanIndex(null);
    }, 2000);
  }, []);

  /**
   * Handle clicking on a label - toggle selected annotation or clear it.
   */
  const handleLabelClick = useCallback(
    (annotation: ServerSpanAnnotation) => {
      if (selectedAnnotations.includes(annotation.id)) {
        setSelectedAnnotations([]);
      } else {
        setSelectedAnnotations([annotation.id]);
      }
    },
    [selectedAnnotations, setSelectedAnnotations]
  );

  /**
   * Build spans from text, annotation boundaries, search results, and chat source boundaries.
   * Also filter out invisible labels if visibleLabels is provided.
   */
  useEffect(() => {
    // helper to check if a label is visible
    const isLabelVisible = (labelText: string) => {
      if (visibleLabels === null) return true; // no filtering
      return visibleLabels.some((label) => label.text === labelText);
    };

    const validAnnotations = annotations
      .filter(
        (ann) =>
          ann.annotationLabel?.text && isLabelVisible(ann.annotationLabel.text)
      )
      .sort((a, b) => a.json.start - b.json.start);

    const newSpans: TextSpan[] = [];
    const boundaries = new Set<number>();

    // collect annotation boundaries
    validAnnotations.forEach((ann) => {
      boundaries.add(ann.json.start);
      boundaries.add(ann.json.end);
    });
    // collect search results
    searchResults.forEach((sr) => {
      boundaries.add(sr.start_index);
      boundaries.add(sr.end_index);
    });
    // collect chat sources
    chatSources.forEach((cs) => {
      boundaries.add(cs.start_index);
      boundaries.add(cs.end_index);
    });

    boundaries.add(0);
    boundaries.add(text.length);
    const sortedBoundaries = Array.from(boundaries).sort((a, b) => a - b);

    for (let i = 0; i < sortedBoundaries.length - 1; i++) {
      const spanStart = sortedBoundaries[i];
      const spanEnd = sortedBoundaries[i + 1];
      if (spanEnd <= spanStart) continue;

      const sliceText = text.slice(spanStart, spanEnd);
      const spanAnnotations = validAnnotations.filter(
        (ann) => ann.json.start < spanEnd && ann.json.end > spanStart
      );

      // check search highlight info
      const matchedSearchResult = searchResults.find(
        (sr) => sr.start_index <= spanStart && sr.end_index >= spanEnd
      );
      const isSearchResult = Boolean(matchedSearchResult);
      const isSelectedSearchResult =
        isSearchResult &&
        selectedSearchResultIndex !== undefined &&
        searchResults[selectedSearchResultIndex]?.start_index <= spanStart &&
        searchResults[selectedSearchResultIndex]?.end_index >= spanEnd;

      // check chat source info
      const matchingChatSource = chatSources.find(
        (cs) => cs.start_index <= spanStart && cs.end_index >= spanEnd
      );
      const isChatSource = Boolean(matchingChatSource);
      const isSelectedChatSource =
        isChatSource &&
        selectedChatSourceId &&
        matchingChatSource?.sourceId === selectedChatSourceId;

      const spanObj: TextSpan = {
        start: spanStart,
        end: spanEnd,
        text: sliceText,
        annotations: spanAnnotations,
        isSearchResult,
        isSelectedSearchResult: isSelectedSearchResult || false,
        isChatSource: isChatSource || false,
        isSelectedChatSource: isSelectedChatSource || false,
        sourceId: matchingChatSource?.sourceId,
      };

      newSpans.push(spanObj);
    }
    setSpans(newSpans);
  }, [
    annotations,
    text,
    visibleLabels,
    searchResults,
    chatSources,
    selectedSearchResultIndex,
    selectedChatSourceId,
  ]);

  /**
   * Calculate label positions for any hovered or selected annotations.
   */
  useEffect(() => {
    const calculateLabelPositions = () => {
      if (hoveredSpanIndex === null) {
        setLabelsToRender([]);
        return;
      }

      const hoveredSpan = spans[hoveredSpanIndex];
      if (!hoveredSpan) return;

      // If there is a user selection, only show the hovered labels if selected
      const annToRender =
        selectedAnnotations.length > 0
          ? hoveredSpan.annotations.filter((ann) =>
              selectedAnnotations.includes(ann.id)
            )
          : hoveredSpan.annotations;

      // Possibly filter out structural if not shown, unless it's selected
      const finalAnnotations = annToRender.filter(
        (ann) =>
          showStructuralAnnotations ||
          !ann.structural ||
          selectedAnnotations.includes(ann.id)
      );

      if (finalAnnotations.length === 0) {
        setLabelsToRender([]);
        return;
      }

      const containerElement = containerRef.current;
      const spanElement = containerElement?.querySelector(
        `span[data-span-index="${hoveredSpanIndex}"]`
      ) as HTMLElement;

      if (!containerElement || !spanElement) {
        return;
      }

      const containerRect = containerElement.getBoundingClientRect();
      const spanRect = spanElement.getBoundingClientRect();
      const scrollLeft = containerElement.scrollLeft;
      const scrollTop = containerElement.scrollTop;

      // get line rects for the text node
      const range = document.createRange();
      range.selectNodeContents(spanElement);
      const rects = range.getClientRects();

      // find rect nearest the vertical middle
      const remainderY = spanRect.top + spanRect.height / 2;
      let nearestRect = rects[0];
      let minDist = Infinity;

      for (let i = 0; i < rects.length; i++) {
        const r = rects[i];
        const rMid = r.top + r.height / 2;
        const distance = Math.abs(remainderY - rMid);
        if (distance < minDist) {
          minDist = distance;
          nearestRect = r;
        }
      }

      const baseX = nearestRect.right - containerRect.left + scrollLeft + 8; // offset
      const baseY = nearestRect.top - containerRect.top + scrollTop;
      const labelGap = 4;
      const labelHeight = 28;

      const newPositions: LabelRenderData[] = finalAnnotations.map(
        (annotation, index) => ({
          annotation,
          x: baseX,
          y: baseY + (labelHeight + labelGap) * index,
          width: 100,
          height: labelHeight,
          labelIndex: index,
        })
      );
      setLabelsToRender(newPositions);
    };

    calculateLabelPositions();
  }, [hoveredSpanIndex, spans, selectedAnnotations, showStructuralAnnotations]);

  /**
   * Auto-scroll to the earliest selected annotation when selectedAnnotations changes.
   */
  useEffect(() => {
    if (selectedAnnotations.length === 0) return;

    const selectedAnns = annotations.filter((ann) =>
      selectedAnnotations.includes(ann.id)
    );
    if (selectedAnns.length === 0) return;

    const earliest = selectedAnns.reduce((acc, ann) =>
      ann.json.start < acc.json.start ? ann : acc
    );

    const targetIndex = spans.findIndex(
      (span) =>
        earliest.json.start >= span.start && earliest.json.start < span.end
    );
    if (targetIndex < 0) return;

    const containerElement = containerRef.current;
    if (!containerElement) return;

    const targetEl = containerElement.querySelector(
      `span[data-span-index="${targetIndex}"]`
    ) as HTMLElement | null;

    if (!targetEl) return;

    const containerRect = containerElement.getBoundingClientRect();
    const targetRect = targetEl.getBoundingClientRect();

    containerElement.scrollTo({
      top:
        targetRect.top -
        containerRect.top +
        containerElement.scrollTop -
        containerRect.height / 2 +
        targetRect.height / 2,
      left:
        targetRect.left -
        containerRect.left +
        containerElement.scrollLeft -
        containerRect.width / 2 +
        targetRect.width / 2,
      behavior: "smooth",
    });
  }, [selectedAnnotations, annotations, spans]);

  /**
   * Auto-scroll to the selected chat source when selectedChatSourceId changes.
   * Instead of searching by isSelectedChatSource, we directly match the sourceId
   * to ensure we always find the right span.
   */
  useEffect(() => {
    console.log("selectedChatSourceId changed to ", selectedChatSourceId);

    if (!selectedChatSourceId) return;
    const containerElement = containerRef.current;
    if (!containerElement) return;

    // Find the first span whose sourceId matches the selectedChatSourceId
    const targetIndex = spans.findIndex(
      (s) => s.sourceId === selectedChatSourceId
    );
    if (targetIndex === -1) return;

    const targetEl = containerElement.querySelector(
      `span[data-span-index="${targetIndex}"]`
    ) as HTMLElement | null;
    if (!targetEl) return;

    const containerRect = containerElement.getBoundingClientRect();
    const targetRect = targetEl.getBoundingClientRect();

    containerElement.scrollTo({
      top:
        targetRect.top -
        containerRect.top +
        containerElement.scrollTop -
        containerRect.height / 2 +
        targetRect.height / 2,
      left: 0,
      behavior: "smooth",
    });
  }, [selectedChatSourceId, spans]);

  /**
   * Handle a mouse-up event to create a new annotation from selection, if any.
   */
  const handleMouseUp = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!allowInput || read_only) return;

    const selection = document.getSelection();
    if (!selection || selection.toString().length === 0) {
      return;
    }

    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;
    const anchorGlobalOffset = getGlobalOffsetFromNode(
      anchorNode,
      selection.anchorOffset,
      spans
    );
    const focusGlobalOffset = getGlobalOffsetFromNode(
      focusNode,
      selection.focusOffset,
      spans
    );

    if (anchorGlobalOffset === null || focusGlobalOffset === null) {
      return;
    }

    const start = Math.min(anchorGlobalOffset, focusGlobalOffset);
    const end = Math.max(anchorGlobalOffset, focusGlobalOffset);
    const selectedText = text.slice(start, end);

    if (selectedText.length > 0) {
      const newAnnotation = getSpan({ start, end, text: selectedText });
      createAnnotation(newAnnotation);
    }
  };

  return (
    <>
      <PaperContainer
        ref={containerRef}
        id="txt-annotator-txt-container"
        data-testid="txt-annotator"
        style={{
          maxHeight: maxHeight || "auto",
          maxWidth: maxWidth || "auto",
          overflow: "auto",
          position: "relative",
        }}
        onClick={() => setSelectedAnnotations([])}
        onMouseUp={handleMouseUp}
      >
        {spans.map((span, index) => {
          const {
            annotations: spanAnnotations,
            isSearchResult,
            isSelectedSearchResult,
            isChatSource,
            isSelectedChatSource,
            text: spanText,
          } = span;

          // Determine which of these spanAnnotations are relevant for highlighting,
          // respecting structural toggles.
          const usedAnn =
            selectedAnnotations.length > 0
              ? spanAnnotations.filter((ann) =>
                  selectedAnnotations.includes(ann.id)
                )
              : spanAnnotations;

          const finalAnnotations = usedAnn.filter(
            (ann) =>
              showStructuralAnnotations ||
              !ann.structural ||
              selectedAnnotations.includes(ann.id)
          );

          // Evaluate approval/rejected status.
          const approved = finalAnnotations.some((ann) => ann.approved);
          const rejected = finalAnnotations.some((ann) => ann.rejected);

          // Build highlight layers.
          const highlightColors: string[] = [];

          // If we have annotation-based highlights
          if (finalAnnotations.length > 0) {
            if (finalAnnotations.length === 1) {
              const color = finalAnnotations[0].annotationLabel.color;
              highlightColors.push(hexToRgba(color ?? "#cccccc", 0.3));
            } else {
              // multiple annotation colors
              const colors = finalAnnotations.map((ann) =>
                hexToRgba(ann.annotationLabel.color ?? "#cccccc", 0.3)
              );
              highlightColors.push(...colors);
            }
          }

          // If we have a search highlight
          if (isSearchResult) {
            highlightColors.push(
              isSelectedSearchResult ? "#FFFF00" : "#FFFF99"
            );
          }

          // If we have a chat source highlight
          if (isChatSource) {
            highlightColors.push(isSelectedChatSource ? "#A8FFA8" : "#D2FFD2");
          }

          // Merge them into a single span style
          const backgroundStyle = buildCombinedBackgroundStyle(highlightColors);

          // Display a border on hover if there's at least one relevant annotation.
          const hasBorder =
            hoveredSpanIndex === index && finalAnnotations.length > 0;
          const borderColor =
            finalAnnotations[0]?.annotationLabel?.color || "#000";

          return (
            <AnnotatedSpan
              key={index}
              data-span-index={index}
              data-testid={
                finalAnnotations.length > 0
                  ? `annotated-span-${index}`
                  : undefined
              }
              onMouseEnter={() => handleMouseEnter(index)}
              onMouseLeave={handleMouseLeave}
              approved={approved}
              rejected={rejected}
              hasBorder={hasBorder}
              borderColor={borderColor}
              style={{
                ...backgroundStyle,
                position: "relative",
                paddingLeft: isChatSource ? "4px" : undefined,
              }}
            >
              {isChatSource && (
                <ChatSourceIcon isSelected={isSelectedChatSource || false}>
                  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
                  </svg>
                </ChatSourceIcon>
              )}
              {spanText}
            </AnnotatedSpan>
          );
        })}

        {labelsToRender.map(
          ({ annotation, x, y, width, height, labelIndex }) => {
            // Build a radial menu with possible actions
            const actions: CloudButtonItem[] = [];

            if (
              !annotation.structural &&
              annotation.myPermissions.includes(PermissionTypes.CAN_UPDATE)
            ) {
              actions.push({
                name: "edit",
                color: "#a3a3a3",
                tooltip: "Edit Annotation",
                onClick: () => {
                  setAnnotationToEdit(annotation);
                  setEditModalOpen(true);
                },
              });
            }

            if (
              !annotation.structural &&
              annotation.myPermissions.includes(PermissionTypes.CAN_REMOVE)
            ) {
              actions.push({
                name: "trash",
                color: "#d3d3d3",
                tooltip: "Delete Annotation",
                onClick: () => {
                  deleteAnnotation(annotation.id);
                },
              });
            }

            if (approveAnnotation) {
              actions.push({
                name: "thumbs up",
                color: "#b3b3b3",
                tooltip: "Approve Annotation",
                onClick: () => {
                  approveAnnotation(annotation.id);
                },
              });
            }

            if (rejectAnnotation) {
              actions.push({
                name: "thumbs down",
                color: "#c3c3c3",
                tooltip: "Reject Annotation",
                onClick: () => {
                  rejectAnnotation(annotation.id);
                },
              });
            }

            return (
              <LabelContainer
                key={`${annotation.id}-${labelIndex}`}
                data-testid={`annotation-label-container-${annotation.id}`}
                style={{
                  position: "absolute",
                  left: `${x}px`,
                  top: `${y}px`,
                  width: `${width}px`,
                  height: `${height}px`,
                  zIndex: 1000 + labelIndex,
                  pointerEvents: "auto",
                }}
                onMouseEnter={handleLabelMouseEnter}
                onMouseLeave={handleLabelMouseLeave}
                color={annotation.annotationLabel.color || "#cccccc"}
              >
                <Label
                  id={`label-${annotation.id}-${labelIndex}`}
                  data-testid={`annotation-label-${annotation.id}`}
                  color={annotation.annotationLabel.color || "#cccccc"}
                  $index={labelIndex}
                  onClick={(e: React.MouseEvent<HTMLSpanElement>) => {
                    e.stopPropagation();
                    handleLabelClick(annotation);
                  }}
                >
                  {annotation.annotationLabel.text}
                </Label>
                <RadialButtonCloud
                  parentBackgroundColor={
                    annotation.annotationLabel.color || "#cccccc"
                  }
                  actions={actions}
                />
              </LabelContainer>
            );
          }
        )}
      </PaperContainer>

      <Modal
        open={editModalOpen}
        onClose={() => {
          setEditModalOpen(false);
          setAnnotationToEdit(null);
        }}
      >
        <Modal.Header>Edit Annotation Label</Modal.Header>
        <Modal.Content>
          {annotationToEdit && (
            <Dropdown
              selection
              options={availableLabels.map((label) => ({
                key: label.id,
                text: label.text,
                value: label.id,
              }))}
              value={annotationToEdit.annotationLabel.id}
              onChange={(e, { value }) => {
                const newLabel = availableLabels.find(
                  (lbl) => lbl.id === value
                );
                if (newLabel) {
                  const updatedAnnotation = annotationToEdit.update({
                    annotationLabel: newLabel,
                  });
                  updateAnnotation(updatedAnnotation);
                }
                setEditModalOpen(false);
                setAnnotationToEdit(null);
              }}
            />
          )}
        </Modal.Content>
        <Modal.Actions>
          <Button
            onClick={() => {
              setEditModalOpen(false);
              setAnnotationToEdit(null);
            }}
          >
            Cancel
          </Button>
        </Modal.Actions>
      </Modal>
    </>
  );
};

export default React.memo(TxtAnnotator);
