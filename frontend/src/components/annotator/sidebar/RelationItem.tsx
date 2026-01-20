import React from "react";
import { Card, IconButton } from "@os-legal/ui";
import { Trash2 } from "lucide-react";
import styled from "styled-components";

import "./AnnotatorSidebar.css";
import { RelationHighlightItem } from "./RelationHighlightItem";
import { RelationGroup, ServerTokenAnnotation } from "../types/annotations";

const DeleteButton = styled.div`
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 1;
`;

const RelationCard = styled(Card)<{ $selected?: boolean }>`
  position: relative;
  width: 100%;
  user-select: none;
  cursor: pointer;
  background-color: ${(props) => (props.$selected ? "#e2ffdb" : "#fff")};
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
`;

const RelationList = styled.div`
  margin: 0;
  font-size: 0.85rem;

  & > * {
    border-bottom: 1px solid rgba(34, 36, 38, 0.15);

    &:last-child {
      border-bottom: none;
    }
  }
`;

const HorizontalDivider = styled.div`
  display: flex;
  align-items: center;
  text-align: center;
  margin: 1rem 0;
  font-size: 0.85714286rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(0, 0, 0, 0.85);

  &::before,
  &::after {
    content: "";
    flex: 1;
    border-bottom: 1px solid rgba(34, 36, 38, 0.15);
  }

  &::before {
    margin-right: 1rem;
  }

  &::after {
    margin-left: 1rem;
  }
`;

export function RelationItem({
  relation,
  target_annotations,
  source_annotations,
  read_only,
  selected,
  onSelectAnnotation,
  onSelectRelation,
  onDeleteRelation,
  onRemoveAnnotationFromRelation,
}: {
  relation: RelationGroup;
  read_only: boolean;
  selected: boolean;
  target_annotations: ServerTokenAnnotation[];
  source_annotations: ServerTokenAnnotation[];
  onSelectRelation: () => void;
  onSelectAnnotation: (annotationId: string) => void;
  onDeleteRelation: (relationId: string) => void;
  onRemoveAnnotationFromRelation: (
    annotationId: string,
    relationId: string
  ) => void;
}) {
  let source_cards = source_annotations.map((source_annotation) => (
    <RelationHighlightItem
      key={`1_${source_annotation.id}`}
      type="SOURCE"
      annotation={source_annotation}
      onSelect={onSelectAnnotation}
      onRemoveAnnotationFromRelation={() =>
        onRemoveAnnotationFromRelation(source_annotation.id, relation.id)
      }
      read_only={read_only || relation.structural}
    />
  ));

  let target_cards = target_annotations.map((target_annotation) => (
    <RelationHighlightItem
      key={`2_${target_annotation.id}`}
      type="TARGET"
      annotation={target_annotation}
      onSelect={onSelectAnnotation}
      onRemoveAnnotationFromRelation={() =>
        onRemoveAnnotationFromRelation(target_annotation.id, relation.id)
      }
      read_only={read_only || relation.structural}
    />
  ));

  return (
    <RelationCard $selected={selected} onClick={onSelectRelation}>
      {!relation.structural && (
        <DeleteButton>
          <IconButton
            variant="danger"
            size="sm"
            aria-label="Delete relation"
            onClick={(e: React.MouseEvent) => {
              e.stopPropagation();
              onDeleteRelation(relation.id);
            }}
          >
            <Trash2 size={14} />
          </IconButton>
        </DeleteButton>
      )}

      <RelationList>{source_cards}</RelationList>
      <HorizontalDivider>
        <strong>{relation.label.text}:</strong>
      </HorizontalDivider>
      <RelationList>{target_cards}</RelationList>
    </RelationCard>
  );
}
