import React from "react";
import { Label, Button, Popup, Icon } from "semantic-ui-react";
import styled from "styled-components";
import { Trash2, ArrowRight, ArrowLeft } from "lucide-react";
import { HorizontallyJustifiedDiv } from "./common";
import { useAnnotationRefs } from "../hooks/useAnnotationRefs";
import { useAnnotationSelection } from "../hooks/useAnnotationSelection";
import { ServerTokenAnnotation } from "../types/annotations";
import { PermissionTypes } from "../../types";

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

const AnnotationLabel = styled(Label)`
  &&& {
    background-color: #${(props) => props.color || "e0e1e2"};
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
  }
`;

const DeleteButton = styled(Button)`
  &&& {
    padding: 0.4em;
    margin-left: 0.5rem;
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

const RelationshipLabel = styled(Label)`
  &&& {
    margin-top: 0.75rem;
    font-size: 0.75rem;
    padding: 0.4em 0.8em;
    display: inline-flex;
    align-items: center;
    gap: 0.4em;
    border-radius: 4px;
    font-weight: 500;

    &[pointing="right"] {
      background-color: #eff6ff;
      color: #3b82f6;
      border: 1px solid #bfdbfe;
    }

    &[pointing="left"] {
      background-color: #f0fdf4;
      color: #22c55e;
      border: 1px solid #bbf7d0;
    }
  }
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
}

export const HighlightItem: React.FC<HighlightItemProps> = ({
  annotation,
  className,
  read_only,
  relations,
  onDelete,
  onSelect,
}) => {
  const { selectedAnnotations, handleAnnotationSelect } =
    useAnnotationSelection();
  const { annotationElementRefs } = useAnnotationRefs();
  const selected = selectedAnnotations.includes(annotation.id);

  const my_output_relationships = relations.filter((relation) =>
    relation.sourceIds.includes(annotation.id)
  );
  const my_input_relationships = relations.filter((relation) =>
    relation.targetIds.includes(annotation.id)
  );
  return (
    <HighlightContainer
      color={annotation?.annotationLabel?.color}
      selected={selected}
      className={`sidebar__annotation ${className || ""}`}
      data-annotation-id={annotation.id}
      onClick={() => {
        annotationElementRefs.current[annotation.id]?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
        handleAnnotationSelect(annotation.id);
      }}
    >
      <div>
        <AnnotationLabel color={annotation.annotationLabel.color}>
          {annotation.annotationLabel.icon && (
            <Icon name={annotation.annotationLabel.icon} />
          )}
          {annotation.annotationLabel.text}
        </AnnotationLabel>
        {!read_only &&
          !annotation.structural &&
          annotation.myPermissions.includes(PermissionTypes.CAN_REMOVE) &&
          onDelete && (
            <DeleteButton
              icon={<Trash2 size={16} />}
              size="mini"
              circular
              onClick={(e: { stopPropagation: () => void }) => {
                e.stopPropagation();
                onDelete(annotation.id);
              }}
            />
          )}
      </div>
      {annotation?.rawText && (
        <Popup
          content={annotation.rawText}
          trigger={
            <BlockQuote>{`${annotation.rawText.slice(0, 90)}…`}</BlockQuote>
          }
        />
      )}
      <HorizontallyJustifiedDiv>
        {my_output_relationships.length > 0 && (
          <RelationshipLabel pointing="right" basic color="blue">
            <ArrowRight size={14} />
            Points To {my_output_relationships.length}
          </RelationshipLabel>
        )}
        {my_input_relationships.length > 0 && (
          <RelationshipLabel pointing="left" basic color="green">
            <ArrowLeft size={14} />
            {my_input_relationships.length} Referencing
          </RelationshipLabel>
        )}
      </HorizontallyJustifiedDiv>
      <LocationText>Page {annotation.page}</LocationText>
    </HighlightContainer>
  );
};
