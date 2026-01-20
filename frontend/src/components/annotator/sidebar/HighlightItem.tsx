import React from "react";
import { Popup, Icon as SemanticIcon } from "semantic-ui-react";
import { IconButton, Chip } from "@os-legal/ui";
import styled from "styled-components";
import {
  Trash2,
  ArrowRight,
  ArrowLeft,
  CheckSquare,
  Square,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { HorizontallyJustifiedDiv } from "./common";
import { useAnnotationRefs } from "../hooks/useAnnotationRefs";
import { useAnnotationSelection } from "../context/UISettingsAtom";
import { updateAnnotationSelectionParams } from "../../../utils/navigationUtils";
import { ServerTokenAnnotation } from "../types/annotations";
import { PermissionTypes } from "../../types";
import { ModalityBadge } from "./ModalityBadge";
import { AnnotationImagePreview } from "./AnnotationImagePreview";
import { useAnnotationImages } from "../hooks/useAnnotationImages";

interface HighlightContainerProps {
  color?: string;
  selected?: boolean;
}

const HighlightContainer = styled.div<HighlightContainerProps>`
  border-left: 4px solid ${(props) => props.color || "#e0e1e2"};
  background-color: ${(props) =>
    props.selected ? "rgba(46, 204, 113, 0.08)" : "white"};
  box-shadow: ${(props) =>
    props.selected
      ? "0 2px 8px rgba(46, 204, 113, 0.2)"
      : "0 1px 3px rgba(0, 0, 0, 0.08)"};
  border-radius: 6px;
  padding: 0.875rem 1rem;
  margin: 0.5rem 0.75rem;
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover {
    box-shadow: 0 3px 8px rgba(0, 0, 0, 0.12);
    transform: translateY(-1px);
    background-color: ${(props) =>
      props.selected ? "rgba(46, 204, 113, 0.08)" : "rgba(0, 0, 0, 0.01)"};
  }

  &:active {
    transform: translateY(0);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  }
`;

interface AnnotationChipProps {
  $labelColor?: string;
}

const AnnotationChip = styled.div<AnnotationChipProps>`
  background-color: ${(props) => props.$labelColor || "#e0e1e2"};
  color: white;
  margin: 0 0.5rem 0.5rem 0;
  padding: 0.5em 1em;
  font-weight: 500;
  font-size: 0.85rem;
  border-radius: 99px;
  display: inline-flex;
  align-items: center;
  gap: 0.4em;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
`;

const DeleteButtonWrapper = styled.div`
  margin-left: 0.5rem;

  button {
    padding: 0.4em;
    background-color: transparent;
    color: #99a1a7;
    transition: all 0.2s ease;

    &:hover {
      background-color: #fee2e2;
      color: #dc2626;
    }

    &:active {
      background-color: #fecaca;
    }
  }
`;

const BlockQuote = styled.blockquote`
  margin: 0.75rem 0;
  padding: 0.75rem 1rem;
  background-color: #f8fafc;
  border-left: 3px solid #e2e8f0;
  border-radius: 4px;
  font-style: italic;
  color: #475569;
  font-size: 0.9rem;
  line-height: 1.5;

  &:hover {
    background-color: #f1f5f9;
  }
`;

interface RelationshipChipProps {
  $direction: "right" | "left";
}

const RelationshipChip = styled.div<RelationshipChipProps>`
  margin-top: 0.75rem;
  font-size: 0.75rem;
  padding: 0.4em 0.8em;
  display: inline-flex;
  align-items: center;
  gap: 0.4em;
  border-radius: 4px;
  font-weight: 500;
  background-color: ${(props) =>
    props.$direction === "right" ? "#eff6ff" : "#f0fdf4"};
  color: ${(props) => (props.$direction === "right" ? "#3b82f6" : "#22c55e")};
  border: 1px solid
    ${(props) => (props.$direction === "right" ? "#bfdbfe" : "#bbf7d0")};
`;

const LocationText = styled.div`
  font-size: 0.75rem;
  color: #64748b;
  margin-top: 0.75rem;
  font-weight: 500;
`;

interface HighlightItemProps {
  annotation: ServerTokenAnnotation;
  className?: string;
  read_only: boolean;
  relations: Array<{ sourceIds: string[]; targetIds: string[] }>;
  onDelete?: (annotationId: string) => void;
  onSelect: (annotationId: string) => void;
  onToggleMultiSelect?: () => void;
  isMultiSelected?: boolean;
  contentModalities?: string[];
}

export const HighlightItem: React.FC<HighlightItemProps> = ({
  annotation,
  className,
  read_only,
  relations,
  onDelete,
  onSelect,
  onToggleMultiSelect,
  isMultiSelected = false,
  contentModalities,
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { selectedAnnotations } = useAnnotationSelection();
  const { annotationElementRefs } = useAnnotationRefs();

  // Fetch images if annotation has IMAGE modality
  const { images, loading, error } = useAnnotationImages(
    annotation.id,
    contentModalities
  );
  const selected = selectedAnnotations.includes(annotation.id);

  const my_output_relationships = relations.filter((relation) =>
    relation.sourceIds.includes(annotation.id)
  );
  const my_input_relationships = relations.filter((relation) =>
    relation.targetIds.includes(annotation.id)
  );
  const handleClick = () => {
    // Scroll to annotation in PDF
    annotationElementRefs.current[annotation.id]?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });

    // Update selection via URL - CentralRouteManager Phase 2 will set reactive var
    // Toggle behavior: if already selected, deselect; otherwise select
    const newSelection = selected ? [] : [annotation.id];
    updateAnnotationSelectionParams(location, navigate, {
      annotationIds: newSelection,
    });

    // Call optional onSelect callback
    if (onSelect) {
      onSelect(annotation.id);
    }
  };

  return (
    <HighlightContainer
      color={annotation?.annotationLabel?.color}
      selected={selected}
      className={`sidebar__annotation ${className || ""}`}
      data-annotation-id={annotation.id}
      onClick={handleClick}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        {onToggleMultiSelect &&
          (isMultiSelected ? (
            <CheckSquare
              size={20}
              style={{
                cursor: "pointer",
                color: "#3b82f6",
              }}
              onClick={(e: React.MouseEvent) => {
                e.stopPropagation();
                onToggleMultiSelect();
              }}
            />
          ) : (
            <Square
              size={20}
              style={{
                cursor: "pointer",
                color: "#94a3b8",
              }}
              onClick={(e: React.MouseEvent) => {
                e.stopPropagation();
                onToggleMultiSelect();
              }}
            />
          ))}
        <AnnotationChip $labelColor={annotation.annotationLabel.color}>
          {annotation.annotationLabel.icon && (
            <SemanticIcon name={annotation.annotationLabel.icon} />
          )}
          {annotation.annotationLabel.text}
        </AnnotationChip>
        <ModalityBadge modalities={contentModalities || []} />
        {!read_only &&
          !annotation.structural &&
          annotation.myPermissions.includes(PermissionTypes.CAN_REMOVE) &&
          onDelete && (
            <DeleteButtonWrapper>
              <IconButton
                variant="ghost"
                size="sm"
                aria-label="Delete annotation"
                onClick={(e: React.MouseEvent) => {
                  e.stopPropagation();
                  onDelete(annotation.id);
                }}
              >
                <Trash2 size={16} />
              </IconButton>
            </DeleteButtonWrapper>
          )}
      </div>
      {/* Show content based on modality:
          - IMAGE only: Featured image, no text
          - TEXT only: Text only, no images
          - MIXED/both: Featured image + text below */}
      {(() => {
        const hasImageModality = contentModalities?.includes("IMAGE");
        const hasTextModality = contentModalities?.includes("TEXT");
        const hasText = annotation?.rawText && annotation.rawText.trim() !== "";

        // IMAGE modality (with or without text) - show featured image first
        if (hasImageModality) {
          return (
            <>
              <AnnotationImagePreview
                images={images}
                loading={loading}
                error={error}
                compact={false}
              />
              {/* Show text below image if it's mixed content */}
              {hasTextModality && hasText && (
                <Popup
                  content={annotation.rawText}
                  trigger={
                    <BlockQuote style={{ marginTop: "0.5rem" }}>
                      {`${annotation.rawText.slice(0, 90)}…`}
                    </BlockQuote>
                  }
                />
              )}
            </>
          );
        }

        // TEXT only modality - just show text
        if (hasText) {
          return (
            <Popup
              content={annotation.rawText}
              trigger={
                <BlockQuote>{`${annotation.rawText.slice(0, 90)}…`}</BlockQuote>
              }
            />
          );
        }

        return null;
      })()}
      <HorizontallyJustifiedDiv>
        {my_output_relationships.length > 0 && (
          <RelationshipChip $direction="right">
            <ArrowRight size={14} />
            Points To {my_output_relationships.length}
          </RelationshipChip>
        )}
        {my_input_relationships.length > 0 && (
          <RelationshipChip $direction="left">
            <ArrowLeft size={14} />
            {my_input_relationships.length} Referencing
          </RelationshipChip>
        )}
      </HorizontallyJustifiedDiv>
      <LocationText>Page {annotation.page}</LocationText>
    </HighlightContainer>
  );
};
