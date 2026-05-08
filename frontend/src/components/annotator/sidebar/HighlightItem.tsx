import React from "react";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  Trash2,
  ArrowRight,
  ArrowLeft,
  CheckSquare,
  Square,
} from "lucide-react";
import { DynamicIcon } from "../../widgets/icon-picker/DynamicIcon";
import { useLocation, useNavigate } from "react-router-dom";
import { HorizontallyJustifiedDiv } from "./common";
import { useAnnotationRefs } from "../hooks/useAnnotationRefs";
import { useAnnotationSelection } from "../context/UISettingsAtom";
import { updateAnnotationSelectionParams } from "../../../utils/navigationUtils";
import { ServerTokenAnnotation, ServerAnnotation } from "../types/annotations";
import { canDeleteAnnotation } from "../../../utils/annotationPermissions";
import { ModalityBadge } from "./ModalityBadge";
import { AnnotationImagePreview } from "./AnnotationImagePreview";
import { useAnnotationImages } from "../hooks/useAnnotationImages";

interface HighlightContainerProps {
  color?: string;
  selected?: boolean;
}

const HighlightContainer = styled.div<HighlightContainerProps>`
  border-left: 4px solid ${(props) => props.color || OS_LEGAL_COLORS.border};
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

interface AnnotationLabelProps {
  $labelColor?: string;
}

const AnnotationLabel = styled.span<AnnotationLabelProps>`
  background-color: ${(props) => props.$labelColor || OS_LEGAL_COLORS.border};
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

const DeleteButton = styled.button`
  padding: 0.4em;
  margin-left: 0.5rem;
  background-color: transparent;
  color: ${OS_LEGAL_COLORS.textMuted};
  border: none;
  border-radius: 50%;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;

  &:hover {
    background-color: ${OS_LEGAL_COLORS.dangerSurfaceHover};
    color: ${OS_LEGAL_COLORS.danger};
  }

  &:active {
    background-color: ${OS_LEGAL_COLORS.dangerBorder};
  }
`;

const BlockQuote = styled.blockquote`
  margin: 0.75rem 0;
  padding: 0.75rem 1rem;
  background-color: ${OS_LEGAL_COLORS.surfaceHover};
  border-left: 3px solid ${OS_LEGAL_COLORS.border};
  border-radius: 4px;
  font-style: italic;
  color: ${OS_LEGAL_COLORS.textTertiary};
  font-size: 0.9rem;
  line-height: 1.5;

  &:hover {
    background-color: ${OS_LEGAL_COLORS.surfaceLight};
  }
`;

const RelationshipLabel = styled.span<{ $direction?: "right" | "left" }>`
  margin-top: 0.75rem;
  font-size: 0.75rem;
  padding: 0.4em 0.8em;
  display: inline-flex;
  align-items: center;
  gap: 0.4em;
  border-radius: 4px;
  font-weight: 500;
  background-color: ${(props) =>
    props.$direction === "left"
      ? OS_LEGAL_COLORS.successSurface
      : OS_LEGAL_COLORS.blueSurface};
  color: ${(props) =>
    props.$direction === "left"
      ? OS_LEGAL_COLORS.green
      : OS_LEGAL_COLORS.primaryBlue};
  border: 1px solid
    ${(props) =>
      props.$direction === "left"
        ? OS_LEGAL_COLORS.successBorder
        : OS_LEGAL_COLORS.blueBorder};
`;

const LocationText = styled.div`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.75rem;
  font-weight: 500;
`;

interface HighlightItemProps {
  annotation: ServerAnnotation;
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
  const { images, loading, error, hasFetchedEmpty } = useAnnotationImages(
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
    // Only use scrollIntoView for PDF token annotations. Text annotations
    // are scrolled by TxtAnnotator's own selectedAnnotations useEffect,
    // so calling scrollIntoView here would cause two competing scroll animations.
    if (annotation instanceof ServerTokenAnnotation) {
      annotationElementRefs.current[annotation.id]?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }

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
      data-testid="highlight-item"
      data-annotation-id={annotation.id}
      onClick={handleClick}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        {onToggleMultiSelect && (
          <span
            style={{
              cursor: "pointer",
              color: isMultiSelected
                ? OS_LEGAL_COLORS.primaryBlue
                : OS_LEGAL_COLORS.textMuted,
              display: "inline-flex",
            }}
            onClick={(e: React.MouseEvent) => {
              e.stopPropagation();
              onToggleMultiSelect();
            }}
          >
            {isMultiSelected ? <CheckSquare size={20} /> : <Square size={20} />}
          </span>
        )}
        <AnnotationLabel $labelColor={annotation.annotationLabel.color}>
          {annotation.annotationLabel.icon && (
            <DynamicIcon name={annotation.annotationLabel.icon} size={14} />
          )}
          {annotation.annotationLabel.text}
        </AnnotationLabel>
        <ModalityBadge modalities={contentModalities || []} />
        {canDeleteAnnotation(annotation, read_only) && onDelete && (
          <DeleteButton
            aria-label="Delete annotation"
            onClick={(e: React.MouseEvent) => {
              e.stopPropagation();
              onDelete(annotation.id);
            }}
          >
            <Trash2 size={16} />
          </DeleteButton>
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
                hasFetchedEmpty={hasFetchedEmpty}
                compact={false}
              />
              {/* Show text below image if it's mixed content */}
              {hasTextModality && hasText && (
                <BlockQuote
                  style={{ marginTop: "0.5rem" }}
                  title={annotation.rawText}
                >
                  {`${annotation.rawText.slice(0, 90)}…`}
                </BlockQuote>
              )}
            </>
          );
        }

        // TEXT only modality - just show text
        if (hasText) {
          return (
            <BlockQuote title={annotation.rawText}>
              {`${annotation.rawText.slice(0, 90)}…`}
            </BlockQuote>
          );
        }

        return null;
      })()}
      <HorizontallyJustifiedDiv>
        {my_output_relationships.length > 0 && (
          <RelationshipLabel $direction="right">
            <ArrowRight size={14} />
            Points To {my_output_relationships.length}
          </RelationshipLabel>
        )}
        {my_input_relationships.length > 0 && (
          <RelationshipLabel $direction="left">
            <ArrowLeft size={14} />
            {my_input_relationships.length} Referencing
          </RelationshipLabel>
        )}
      </HorizontallyJustifiedDiv>
      {(annotation instanceof ServerTokenAnnotation || annotation.page > 0) && (
        <LocationText>Page {annotation.page + 1}</LocationText>
      )}
    </HighlightContainer>
  );
};
