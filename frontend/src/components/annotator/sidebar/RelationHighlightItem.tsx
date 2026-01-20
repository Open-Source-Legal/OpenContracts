import { List, Icon as SemanticIcon } from "semantic-ui-react";
import { IconButton, Chip } from "@os-legal/ui";
import styled from "styled-components";
import _ from "lodash";
import { X } from "lucide-react";

// Restore standard imports
import source_icon from "../../../assets/icons/noun-bow-and-arrow-559923.png";
import target_icon from "../../../assets/icons/noun-target-746597.png";

import "./AnnotatorSidebar.css";
import { ServerTokenAnnotation } from "../types/annotations";
import { TruncatedText } from "../../widgets/data-display/TruncatedText";

const AvatarImage = styled.img`
  width: 2em;
  height: 2em;
  border-radius: 50%;
  object-fit: cover;
  display: inline-block;
  vertical-align: middle;
  margin-right: 0.5em;
`;

interface HasColor {
  color: string;
}

export const RelationHighlightContainer = styled.div<HasColor>(
  ({ theme, color }) => `
    border: 2px solid ${color};
    border-bottom: 0px;
`
);

interface RelationHighlightItemProps {
  annotation: ServerTokenAnnotation;
  className?: string;
  type: "SOURCE" | "TARGET";
  read_only: boolean;
  onRemoveAnnotationFromRelation?: (annotationId: string) => void;
  onSelect: (annotationId: string) => void;
}

export const RelationHighlightItem = ({
  annotation,
  className,
  type,
  read_only,
  onRemoveAnnotationFromRelation,
  onSelect,
}: RelationHighlightItemProps) => {
  let prepared_className = "sidebar__relation__annotation";
  if (className) {
    prepared_className =
      prepared_className + ` sidebar__relation__annotation_${className}`;
  }

  return (
    <List.Item key={annotation.id} className={prepared_className}>
      {type === "SOURCE" ? (
        <AvatarImage src={source_icon} alt="Source" />
      ) : (
        <AvatarImage src={target_icon} alt="Target" />
      )}
      {!read_only && onRemoveAnnotationFromRelation ? (
        <IconButton
          variant="danger"
          size="sm"
          style={{ float: "right" }}
          aria-label="Remove from relation"
          onClick={() => onRemoveAnnotationFromRelation(annotation.id)}
        >
          <X size={12} />
        </IconButton>
      ) : (
        <></>
      )}
      <Chip
        onClick={() => {
          onSelect(annotation.id);
        }}
        style={{
          color: annotation.annotationLabel.color
            ? annotation.annotationLabel.color
            : "grey",
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          gap: "0.4em",
        }}
      >
        {annotation.annotationLabel.icon ? (
          <SemanticIcon name={annotation.annotationLabel.icon} />
        ) : null}
        <strong>{annotation.annotationLabel.text}</strong>
        <span style={{ marginLeft: "0.5em", opacity: 0.7 }}>
          | Page {annotation.page}
        </span>
      </Chip>
      <List.Content>
        <List.Header></List.Header>
        {annotation?.rawText ? (
          <TruncatedText
            text={annotation.rawText}
            limit={100}
            style={{ marginTop: "0.5rem" }}
          />
        ) : null}
      </List.Content>
    </List.Item>
  );
};
