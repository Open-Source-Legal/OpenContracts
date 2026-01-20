import React from "react";
import { Divider, List } from "semantic-ui-react";
import { Card, IconButton } from "@os-legal/ui";
import { Trash2 } from "lucide-react";
import styled from "styled-components";

import _ from "lodash";

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

      <List
        style={{ marginTop: "0px", marginBottom: "0px" }}
        celled
        size="mini"
      >
        {source_cards}
      </List>
      <Divider horizontal>
        <strong>{relation.label.text}:</strong>
      </Divider>
      <List
        style={{ marginTop: "0px", marginBottom: "0px" }}
        celled
        size="mini"
      >
        {target_cards}
      </List>
    </RelationCard>
  );
}
